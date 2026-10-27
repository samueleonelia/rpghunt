"""itch.io reader: TTRPG "on sale" RSS feeds -> deals.

The feed only tells us WHICH games are on sale. Every price fact comes from the
game's own data:
  1. <game>/data.json   -> current price, sale rate, sale end (UTC), sale id. Small, one call.
  2. the game page      -> "was" price (original_price span), currency and seller (schema.org JSON-LD).
A game with no sale, or a sale rate of 0 ("[0% Off]" in the feed), is NOT a deal.
A 0% game that sits inside an itch sale page (/s/<id>/...) is read as one bundle deal
("Buy everything for $X! Regularly $Y"), once per sale id.
"""
import concurrent.futures
import html
import json
import logging
import re
import threading
import urllib.parse
import xml.etree.ElementTree as ET

from scraper.common import ROOT, FetchError, fetch, fetch_json, is_discount, make_deal, money, norm_url

log = logging.getLogger(__name__)

SOURCE = "itch-data"
WORKERS = 4           # games read at once (different creator sites; 8 got itch rate limits, 2026-10-27)
# A game's page facts (was price, currency, seller) are kept while its sale and price stay the same, so an
# unchanged game costs one small data.json call a day instead of two. Games no longer in the feeds drop out.
PAGE_CACHE = ROOT / "data" / "deals" / "itch-pages.json"
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}

_LD_RE = re.compile(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_ORIG_RE = re.compile(r'original_price"[^>]*>\s*([^<]+?)\s*<')
_RATE_RE = re.compile(r'class="sale_rate"[^>]*>\s*(\d+)\s*%')
_BUNDLE_PRICE_RE = re.compile(r'Buy everything for\s*<strong[^>]*class="bundle_price"[^>]*>\s*([^<]+?)\s*</strong>')
_BUNDLE_WAS_RE = re.compile(r'Regularly\s*<span[^>]*>\s*([^<]+?)\s*</span>')
_OG_TITLE_RE = re.compile(r'<meta\b(?=[^>]*property="og:title")[^>]*?content="([^"]*)"')
_PAGE_TITLE_RE = re.compile(r"<title>([^<]*)</title>")


# ---------- small parsers (pure, tested on saved fixtures) ----------

def parse_amount(text):
    """'$10.00', '€10,50', '1,234.50' -> float; None if no number."""
    if not text:
        return None
    m = re.search(r"\d[\d.,]*", text)
    if not m:
        return None
    s = m.group(0).rstrip(".,")
    if re.search(r",\d{2}$", s) and "." not in s:      # decimal comma
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    return money(s)


def currency_from_text(text):
    for sym, code in CURRENCY_SYMBOLS.items():
        if sym in (text or ""):
            return code
    return None


def parse_feed(xml_bytes):
    """RSS -> list of {url, title} (link and plain title only; prices are NOT taken from the feed)."""
    root = ET.fromstring(xml_bytes)
    items = []
    for it in root.iter("item"):
        link = (it.findtext("link") or it.findtext("guid") or "").strip()
        if not link:
            continue
        title = (it.findtext("plainTitle") or it.findtext("title") or "").strip()
        items.append({"url": link, "title": title})
    return items


def parse_game_data(raw):
    """<game>/data.json text/dict -> {price, rate, sale_id, sale_title, end_date} (None when absent)."""
    d = json.loads(raw) if isinstance(raw, (str, bytes)) else raw
    sale = d.get("sale") or {}
    return {
        "price": parse_amount(d.get("price")) if d.get("price") else None,
        "rate": sale.get("rate"),
        "sale_id": sale.get("id"),
        "sale_title": sale.get("title"),
        "end_date": sale.get("end_date"),
    }


def utc_iso(end_date):
    """'2026-10-18 16:21:00' or '2026-11-01T12:02:00Z' (itch = UTC) -> ('2026-10-18', '2026-10-18T16:21:00Z')."""
    if not end_date:
        return None, None
    m = re.match(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}(?::\d{2})?)", end_date)
    if not m:
        return None, None
    t = m.group(2) if len(m.group(2)) == 8 else m.group(2) + ":00"
    return m.group(1), f"{m.group(1)}T{t}Z"


def parse_game_page(page):
    """Game page HTML -> {title, now, was, currency, rate, ends_raw, seller_name} (missing parts are None)."""
    out = {"title": None, "now": None, "was": None, "currency": None, "rate": None,
           "ends_raw": None, "seller_name": None, "description": None, "genre": None}
    m = re.search(r'<meta[^>]+(?:name|property)=["\'](?:og:)?description["\'][^>]*content=["\']([^"\']*)', page, re.I)
    if m:
        out["description"] = html.unescape(m.group(1)).strip()[:300] or None
    # itch's own "More information" table: Genre / Tags rows (the seller's own labels)
    m = re.search(r'<td>\s*Genre\s*</td>\s*<td>(.*?)</td>', page, re.S | re.I)
    if m:
        out["genre"] = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(1)))).strip() or None
    for raw in _LD_RE.findall(page):
        try:
            ld = json.loads(raw)
        except ValueError:
            continue
        for node in (ld if isinstance(ld, list) else [ld]):
            if not isinstance(node, dict) or node.get("@type") != "Product":
                continue
            out["title"] = html.unescape(node.get("name") or "") or None
            offer = node.get("offers")
            if isinstance(offer, list):
                offer = offer[0] if offer else None
            if isinstance(offer, dict):
                out["now"] = money(offer.get("price"))
                out["currency"] = offer.get("priceCurrency")
                out["ends_raw"] = offer.get("priceValidUntil")
                seller = offer.get("seller")
                if isinstance(seller, dict):
                    out["seller_name"] = html.unescape(seller.get("name") or "") or None
    m = _ORIG_RE.search(page)
    out["was"] = parse_amount(html.unescape(m.group(1))) if m else None
    m = _RATE_RE.search(page)
    out["rate"] = int(m.group(1)) if m else None
    return out


def find_sale_link(page, sale_id):
    """The /s/<id>/<slug> link a game page shows for its sale, or None. Never built by hand."""
    m = re.search(r'href="((?:https://itch\.io)?/s/%s/[^"#?]+)"' % re.escape(str(sale_id)), page)
    if not m:
        return None
    return urllib.parse.urljoin("https://itch.io/", html.unescape(m.group(1)))


def parse_bundle_page(page):
    """Sale/bundle page HTML -> {title, now, was, seller} or None if it is not a "Buy everything" bundle."""
    pm, wm = _BUNDLE_PRICE_RE.search(page), _BUNDLE_WAS_RE.search(page)
    if not (pm and wm):
        return None
    title, seller = None, None
    om = _OG_TITLE_RE.search(page) or _PAGE_TITLE_RE.search(page)
    if om:
        og = re.sub(r"\s*-\s*itch\.io$", "", html.unescape(om.group(1)).strip())
        title, _, seller = og.rpartition(" by ")
        if not title:
            title, seller = og, None
    return {"title": title, "seller": seller,
            "now": parse_amount(html.unescape(pm.group(1))), "was": parse_amount(html.unescape(wm.group(1))),
            "symbol_text": html.unescape(pm.group(1))}


# ---------- network side ----------

def _text(url):
    return fetch(url).body.decode("utf-8", "replace")


def _subdomain(url):
    host = urllib.parse.urlsplit(url).netloc.lower()
    return host.split(".")[0] if host.endswith(".itch.io") else host


MAX_FEED_PAGES = 500     # per feed: a runaway guard only (itch has ~40 pages of TTRPG sales); reported when hit


def _feed_items(shop, stats=None):
    """All feed items over every page of every feed (?page=2, 3... until a page is empty or repeats),
    de-duplicated across feeds, in first-seen order."""
    stats = {} if stats is None else stats
    seen, items, stopped = set(), [], []
    for feed in (shop.get("recipe") or {}).get("feeds") or []:
        for page in range(1, MAX_FEED_PAGES + 1):
            url = feed if page == 1 else f"{feed}{'&' if '?' in feed else '?'}page={page}"
            try:
                parsed = parse_feed(fetch(url).body)
            except (FetchError, ET.ParseError) as e:
                log.warning("itch feed failed: %s (%s)", url, e)
                if page > 1 and not (isinstance(e, FetchError) and e.kind == "dead"):
                    stopped.append(f"{feed} page {page} could not be read; later pages were skipped")
                break
            fresh = 0
            for it in parsed:
                key = norm_url(it["url"])
                if key not in seen:
                    seen.add(key)
                    it["feed"] = feed
                    items.append(it)
                    fresh += 1
            if not fresh:                    # an empty page (or one that repeats) is the end of the listing
                break
        else:
            stopped.append(f"{feed} stopped at the {MAX_FEED_PAGES}-page safety limit; more pages may exist")
    if stopped:
        stats["stopped_early"] = "; ".join(stopped)
    stats["items_read"] = len(items)
    return items


def _sale_deal(shop, item, gd, facts):
    now, was = facts["now"], facts["was"]
    if not is_discount(now, was):
        return None
    ends_src = facts["ends_raw"] or (gd or {}).get("end_date")
    ends, ends_utc = utc_iso(ends_src)
    url = item["url"]
    hints = {"seller": _subdomain(url), "seller_name": facts["seller_name"], "feed": item["feed"],
             "description": facts.get("description"), "categories": [facts["genre"]] if facts.get("genre") else [],
             "ends_utc": ends_utc, "sale_rate": facts["rate"] if facts["rate"] is not None else (gd or {}).get("rate")}
    if gd and gd.get("sale_title"):
        hints["sale_title"] = gd["sale_title"]
    if gd and gd.get("price") is not None and gd["price"] != now:
        hints["data_json_price"] = gd["price"]          # disagreement between the two sources
    return make_deal(
        shop=shop, type="free" if now == 0 else "sale",
        title=facts["title"] or item["title"], url=url,
        price_now=now, price_was=was, currency=facts["currency"], source=SOURCE,
        found_via=item["feed"], ends=ends, hints=hints)


def _bundle_deal(shop, sale_url, sale_id, end_date, currency, game_item, bundle):
    if not is_discount(bundle["now"], bundle["was"]):
        return None
    ends, ends_utc = utc_iso(end_date)
    cur = currency or currency_from_text(bundle["symbol_text"])
    if not cur:
        return None
    return make_deal(
        shop=shop, type="bundle", title=bundle["title"] or f"itch.io sale {sale_id}", url=sale_url,
        price_now=bundle["now"], price_was=bundle["was"], currency=cur, source=SOURCE,
        found_via=game_item["url"], ends=ends,
        hints={"seller": bundle["seller"], "ends_utc": ends_utc, "sale_id": sale_id,
               "seen_on_game": game_item["url"], "feed": game_item["feed"]})


def read(shop):
    return read_with_stats(shop)[0]


def read_with_stats(shop):
    """-> (deals, stats). stats: items_read (games in the sale feeds), stopped_early when a limit was hit.
    Games are read WORKERS at a time: each creator is its own *.itch.io site, and fetch() keeps every
    site polite. Deals keep the feed order."""
    stats = {}
    items = _feed_items(shop, stats)
    try:
        cache = json.loads(PAGE_CACHE.read_text())
    except (OSError, ValueError):
        cache = {}
    fresh_cache = {}
    sale_state = {}     # sale id -> "done", or the number of failed tries (a 429 gets one more try from the next game)
    lock = threading.Lock()

    def claim(sale_id):
        """True when this thread should read the sale page for sale_id (one at a time per sale)."""
        with lock:
            state = sale_state.get(sale_id, 0)
            if state == "done" or state == "busy" or state >= 2:
                return False
            sale_state[sale_id] = "busy"
            sale_state[f"{sale_id}:tries"] = state + 1
            return True

    def one(item):
        url = item["url"].rstrip("/")
        try:
            gd = None
            try:
                gd = parse_game_data(fetch_json(url + "/data.json"))
            except (FetchError, ValueError) as e:
                log.info("itch data.json unavailable for %s (%s); using the page", url, e)
            page = None
            if gd is not None:
                if not gd["sale_id"]:
                    return None                                # no sale at all
                if gd["rate"] == 0:                            # "[0% Off]": only discounted inside a bundle/sale page
                    if not claim(gd["sale_id"]):
                        return None
                    done = False
                    try:
                        page = _text(url)
                        link = find_sale_link(page, gd["sale_id"])
                        d = None
                        if link:
                            bundle = parse_bundle_page(_text(link))
                            if bundle:
                                d = _bundle_deal(shop, link, gd["sale_id"], gd["end_date"],
                                                 parse_game_page(page)["currency"], item, bundle)
                        done = True
                        return d
                    finally:
                        with lock:                             # a failed try lets a later game retry the sale
                            sale_state[gd["sale_id"]] = "done" if done else sale_state[f"{gd['sale_id']}:tries"]
            hit = cache.get(url)
            if page is None and gd and hit and hit["sale_id"] == gd["sale_id"] and hit["price"] == gd["price"]:
                facts = hit["facts"]                           # same sale, same price: the page has not changed
            else:
                facts = parse_game_page(page or _text(url))
            if gd and gd["sale_id"]:
                with lock:
                    fresh_cache[url] = {"sale_id": gd["sale_id"], "price": gd["price"], "facts": facts}
            return _sale_deal(shop, item, gd, facts)
        except FetchError as e:
            log.warning("itch item failed: %s (%s)", url, e)
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(WORKERS, len(items)))) as pool:
        deals = [d for d in pool.map(one, items) if d]
    stats["pages_from_cache"] = sum(1 for u, v in fresh_cache.items() if cache.get(u) == v)
    try:
        PAGE_CACHE.write_text(json.dumps(fresh_cache, ensure_ascii=False) + "\n")
    except OSError:
        pass
    return deals, stats
