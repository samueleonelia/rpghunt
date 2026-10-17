"""itch.io reader: TTRPG "on sale" RSS feeds -> deals.

The feed only tells us WHICH games are on sale. Every price fact comes from the
game's own data:
  1. <game>/data.json   -> current price, sale rate, sale end (UTC), sale id. Small, one call.
  2. the game page      -> "was" price (original_price span), currency and seller (schema.org JSON-LD).
A game with no sale, or a sale rate of 0 ("[0% Off]" in the feed), is NOT a deal.
A 0% game that sits inside an itch sale page (/s/<id>/...) is read as one bundle deal
("Buy everything for $X! Regularly $Y"), once per sale id.
"""
import html
import json
import logging
import re
import urllib.parse
import xml.etree.ElementTree as ET

from scraper.common import FetchError, fetch, fetch_json, is_discount, make_deal, money, norm_url

log = logging.getLogger(__name__)

SOURCE = "itch-data"
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
           "ends_raw": None, "seller_name": None}
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


def _feed_items(shop):
    """All feed items, de-duplicated across feeds, in first-seen order."""
    seen, items = set(), []
    for feed in (shop.get("recipe") or {}).get("feeds") or []:
        try:
            parsed = parse_feed(fetch(feed).body)
        except (FetchError, ET.ParseError) as e:
            log.warning("itch feed failed: %s (%s)", feed, e)
            continue
        for it in parsed:
            key = norm_url(it["url"])
            if key not in seen:
                seen.add(key)
                it["feed"] = feed
                items.append(it)
    return items


def _sale_deal(shop, item, gd, facts):
    now, was = facts["now"], facts["was"]
    if not is_discount(now, was):
        return None
    ends_src = facts["ends_raw"] or (gd or {}).get("end_date")
    ends, ends_utc = utc_iso(ends_src)
    url = item["url"]
    hints = {"seller": _subdomain(url), "seller_name": facts["seller_name"], "feed": item["feed"],
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
    deals = []
    sale_state = {}     # sale id -> "done", or the number of failed tries (a 429 gets one more try from the next game)
    for item in _feed_items(shop):
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
                    continue                                   # no sale at all
                if gd["rate"] == 0:                            # "[0% Off]": only discounted inside a bundle/sale page
                    state = sale_state.get(gd["sale_id"], 0)
                    if state == "done" or state >= 2:
                        continue
                    sale_state[gd["sale_id"]] = state + 1      # counts as a failed try until it finishes
                    page = _text(url)
                    link = find_sale_link(page, gd["sale_id"])
                    if link:
                        bundle = parse_bundle_page(_text(link))
                        if bundle:
                            d = _bundle_deal(shop, link, gd["sale_id"], gd["end_date"],
                                             parse_game_page(page)["currency"], item, bundle)
                            if d:
                                deals.append(d)
                    sale_state[gd["sale_id"]] = "done"
                    continue
            page = page or _text(url)
            facts = parse_game_page(page)
            d = _sale_deal(shop, item, gd, facts)
            if d:
                deals.append(d)
        except FetchError as e:
            log.warning("itch item failed: %s (%s)", url, e)
    return deals
