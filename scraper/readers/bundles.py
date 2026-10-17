"""Bundle-site readers: Bundle of Holding and Humble Bundle (books page).

Both read the shop's own page data. Neither filters to RPGs: phase 2's check does that,
so every deal carries the shop's own words (title, blurb, category) in `hints`.
read(shop) dispatches on shop["platform"].
"""
import datetime
import html
import json
import logging
import re
import urllib.parse

from scraper.common import FetchError, fetch, is_discount, make_deal, money

log = logging.getLogger(__name__)

BOH_HOME = "https://bundleofholding.com/"
HUMBLE_BOOKS = "https://www.humblebundle.com/books"
HUMBLE_BASE = "https://www.humblebundle.com"


def _text(url):
    return fetch(url).body.decode("utf-8", "replace")


def _strip_tags(s, limit=None):
    s = re.sub(r"<[^>]+>", " ", html.unescape(s or ""))
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit] if limit else s


def _attrs(tag):
    return {k: html.unescape(v) for k, v in re.findall(r'([\w:-]+)="([^"]*)"', tag)}


def _ts_to_utc(ts):
    """Unix seconds -> ('YYYY-MM-DD', ISO-8601 UTC)."""
    dt = datetime.datetime.fromtimestamp(int(ts), datetime.timezone.utc)
    return dt.strftime("%Y-%m-%d"), dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------- Bundle of Holding ----------

_BOH_PRICE = re.compile(r"For just\s*(?:<[^>]+>\s*)*US\$\s*([\d,]+(?:\.\d+)?)")
_BOH_RETAIL = re.compile(r"retail value\s*(?:<[^>]+>\s*)*\$\s*([\d,]+(?:\.\d+)?)", re.I)
_BOH_THRESHOLD = re.compile(r"Threshold \(level-up\) price\s*(?:<[^>]+>\s*)*US\$\s*([\d,]+(?:\.\d+)?)", re.I)


def boh_home_bundles(page):
    """Home page -> [{url, ends_ts, name, featured}]. The featured bundle is the home page itself
    (its canonical/og:url); the others are the /presents/ links in the bundle bar, each with its own data-ends."""
    out, seen = [], set()
    m = re.search(r'property="og:url"\s+content="([^"]+)"', page) or \
        re.search(r'<link rel="canonical" href="([^"]+)"', page)
    if m:
        # the header counter (not an inline link button) is the featured bundle's own countdown
        ends = None
        for tag in re.findall(r"<[^>]*data-component=\"bundle-countdown\"[^>]*>", page):
            a = _attrs(tag)
            if "data-inline-mode" not in a and a.get("data-ends"):
                ends = a["data-ends"]
                break
        out.append({"url": m.group(1), "ends_ts": ends, "name": None, "featured": True})
        seen.add(m.group(1).rstrip("/"))
    for mm in re.finditer(r"<a\b[^>]*>([^<]*)", page):
        a = _attrs(mm.group(0))
        href = a.get("href", "")
        if "/presents/" not in href or not a.get("data-ends"):
            continue
        url = urllib.parse.urljoin(BOH_HOME, href)
        if url.rstrip("/") in seen:
            continue
        seen.add(url.rstrip("/"))
        out.append({"url": url, "ends_ts": a["data-ends"], "name": mm.group(1).strip() or None, "featured": False})
    return out


def parse_boh_bundle(page):
    """One bundle page -> {title, now, was, ends_ts, threshold} (None for what is not on the page)."""
    t = re.search(r"<title>([^<]*)</title>", page)
    pm, rm, thr = _BOH_PRICE.search(page), _BOH_RETAIL.search(page), _BOH_THRESHOLD.search(page)
    ends = None
    for tag in re.findall(r"<[^>]*data-component=\"bundle-countdown\"[^>]*>", page):
        a = _attrs(tag)
        if "data-inline-mode" not in a and a.get("data-ends"):
            ends = a["data-ends"]
            break
    return {
        "title": html.unescape(t.group(1)).strip() if t else None,
        "now": money(pm.group(1).replace(",", "")) if pm else None,
        "was": money(rm.group(1).replace(",", "")) if rm else None,
        "ends_ts": ends,
        "threshold": money(thr.group(1).replace(",", "")) if thr else None,
    }


def read_bundleofholding(shop):
    home_url = shop.get("store_url") or BOH_HOME
    try:
        home = _text(home_url)
    except FetchError as e:
        log.warning("bundleofholding home failed: %s", e)
        return []
    now_ts = datetime.datetime.now(datetime.timezone.utc).timestamp()
    deals = []
    for b in boh_home_bundles(home):
        try:
            p = parse_boh_bundle(home if b["featured"] else _text(b["url"]))
        except FetchError as e:
            log.warning("bundleofholding page failed: %s (%s)", b["url"], e)
            continue
        ends_ts = p["ends_ts"] or b["ends_ts"]
        if ends_ts and int(ends_ts) < now_ts:
            continue                                           # already ended
        if not is_discount(p["now"], p["was"]):
            log.warning("bundleofholding: no usable price/retail on %s", b["url"])
            continue
        ends, ends_utc = _ts_to_utc(ends_ts) if ends_ts else (None, None)
        hints = {"bundle_slug": b["url"].rstrip("/").rsplit("/", 1)[-1], "ends_utc": ends_utc,
                 "level_up_price": p["threshold"], "home_url": home_url}
        if b["ends_ts"] and p["ends_ts"] and b["ends_ts"] != p["ends_ts"]:
            hints["ends_link_ts"] = int(b["ends_ts"])           # the bar link disagreed with the page's own counter
        deals.append(make_deal(
            shop=shop, type="bundle", title=p["title"] or b["name"] or b["url"], url=b["url"],
            price_now=p["now"], price_was=p["was"], currency="USD", source="bundle-page",
            found_via=home_url, ends=ends, hints=hints,
            notes="price_was is the bundle's own 'retail value' for the starter collection"))
    return deals


# ---------- Humble Bundle ----------

def _script_json(page, script_id):
    m = re.search(r'<script[^>]*id="%s"[^>]*>(.*?)</script>' % re.escape(script_id), page, re.S)
    return json.loads(m.group(1)) if m else None


def humble_tiles(page):
    """Landing page -> unique bundle tiles (dicts) from every section of the embedded JSON."""
    lp = _script_json(page, "landingPage-json-data") or {}
    tiles, seen = [], set()
    for section, body in (lp.get("data") or {}).items():
        for mosaic in body.get("mosaic", []):
            for t in mosaic.get("products", []):
                url = t.get("product_url")
                if not url or url in seen or t.get("category", t.get("type")) != "bundle":
                    continue
                seen.add(url)
                t["_section"] = section
                tiles.append(t)
    return tiles


def parse_humble_bundle(page):
    """Bundle page -> {currency, tiers:[{id,price}], msrp, end, name, media_type, description} or None."""
    data = _script_json(page, "webpack-bundle-page-data")
    bd = (data or {}).get("bundleData")
    if not bd:
        return None
    basic = bd.get("basic_data") or {}
    tiers = []
    for tid, t in (bd.get("tier_pricing_data") or {}).items():
        price = money((t.get("price|money") or {}).get("amount"))
        if price is None or t.get("should_be_included_in_tier_list") is False:
            continue
        tiers.append({"id": tid, "price": price, "initial": bool(t.get("is_initial_tier"))})
    tiers.sort(key=lambda t: t["price"])
    return {
        "currency": basic.get("currency") or ((basic.get("msrp|money") or {}).get("currency")),
        "tiers": tiers,
        "msrp": money((basic.get("msrp|money") or {}).get("amount")),
        "end": basic.get("end_time|datetime"),
        "name": basic.get("human_name"),
        "media_type": basic.get("media_type"),
        "description": _strip_tags(basic.get("description"), 600),
        "short_blurb": basic.get("short_marketing_blurb"),
    }


def read_humble(shop):
    url = (shop.get("recipe") or {}).get("page") or shop.get("store_url") or HUMBLE_BOOKS
    try:
        tiles = humble_tiles(_text(url))
    except (FetchError, ValueError) as e:
        log.warning("humble landing failed: %s", e)
        return []
    deals = []
    for t in tiles:
        burl = urllib.parse.urljoin(HUMBLE_BASE, t["product_url"])
        try:
            p = parse_humble_bundle(_text(burl))
        except (FetchError, ValueError) as e:
            log.warning("humble bundle failed: %s (%s)", burl, e)
            continue
        if not p or not p["tiers"]:
            continue
        lowest = next((x for x in p["tiers"] if x["initial"]), p["tiers"][0])
        if not is_discount(lowest["price"], p["msrp"]):
            continue
        end_raw = p["end"] or t.get("end_date|datetime")
        ends = end_raw[:10] if end_raw else None
        if ends and ends < datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d"):
            continue                                           # ended before today
        hints = {
            "tiers": [x["price"] for x in p["tiers"]],
            "category": t.get("category"), "stamp": t.get("tile_stamp"), "media_type": p["media_type"],
            "section": t["_section"], "author": t.get("author"),
            "tags": t.get("highlights") or [],
            "blurb": _strip_tags(t.get("marketing_blurb"), 400),
            "short_blurb": p["short_blurb"], "description": p["description"],
            "ends_raw": end_raw,            # Humble gives no zone; same value as the landing page's end_date
            "machine_name": t.get("machine_name"),
        }
        deals.append(make_deal(
            shop=shop, type="bundle", title=p["name"] or t.get("tile_name") or burl, url=burl,
            price_now=lowest["price"], price_was=p["msrp"], currency=p["currency"], source="bundle-page",
            found_via=url, ends=ends, hints=hints,
            notes="price_now is the lowest tier (pay-what-you-want minimum); price_was is Humble's own MSRP"))
    return deals


# ---------- dispatcher ----------

def read(shop):
    platform = shop.get("platform")
    if platform == "bundleofholding":
        return read_bundleofholding(shop)
    if platform == "humble":
        return read_humble(shop)
    raise ValueError(f"bundles.read: unsupported platform {platform!r}")
