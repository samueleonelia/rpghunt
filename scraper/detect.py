"""Work out a shop's platform and recipe from its address.

detect(store_url, name=None) -> shop entry (see agents/scraper-spec.md).
CLI: python -m scraper.detect <seed.json>
     seed.json is an array of {name, store_url, sale_page_url}; results merge into data/shops/shops.json.
"""
import datetime
import json
import re
import sys
import urllib.parse

from scraper.common import FetchError, fetch, load_shops, plain, save_shops


def _origin(url):
    p = urllib.parse.urlsplit(url)
    return f"{p.scheme}://{p.netloc}"


def _host(url):
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def slug(name):
    return plain(name).replace(" ", "-")


def _json(url):
    """Parsed JSON from url, or None when the page is missing or not JSON.
    Blocked / robots-disallowed pages raise FetchError."""
    try:
        return fetch(url).json()
    except FetchError as e:
        if e.kind in ("blocked", "robots"):
            raise
        return None
    except Exception:
        return None


def _try_shopify(origin):
    data = _json(f"{origin}/products.json?limit=1")
    return isinstance(data, dict) and isinstance(data.get("products"), list)


def shopify_currency(html):
    m = re.search(r'Shopify\.currency\s*=\s*\{\s*"active"\s*:\s*"([A-Z]{3})"', html or "")
    return m.group(1) if m else None


def _woo_candidates(store_url, html):
    cands = []
    m = re.search(r'<link[^>]+rel=["\']https://api\.w\.org/["\'][^>]*href=["\']([^"\']+)', html or "")
    if not m:
        m = re.search(r'<link[^>]+href=["\']([^"\']+)["\'][^>]*rel=["\']https://api\.w\.org/', html or "")
    if m:
        cands.append(m.group(1).rstrip("/") + "/wc/store/v1")
    cands.append(store_url.rstrip("/") + "/wp-json/wc/store/v1")
    cands.append(_origin(store_url) + "/wp-json/wc/store/v1")
    return list(dict.fromkeys(cands))


def _try_woocommerce(store_url, html):
    """-> (api_base, currency) or None."""
    for base in _woo_candidates(store_url, html):
        data = _json(f"{base}/products?per_page=1")
        if isinstance(data, list) and data and "prices" in data[0]:
            return base, data[0]["prices"].get("currency_code")
    return None


def detect(store_url, name=None):
    """Return a shop entry. platform 'unknown' + status 'blocked' when the site refuses us."""
    host = _host(store_url)
    today = datetime.date.today().isoformat()
    entry = {
        "id": slug(name) if name else slug(host.rsplit(".", 1)[0]),
        "name": name or host,
        "store_url": store_url,
        "platform": "generic",
        "status": "active",
        "currency": None,
        "recipe": {},
        "recipe_confirmed": None,
        "added": today,
        "added_via": "seed list",
        "notes": None,
    }
    # Platforms known by host: no probing needed.
    if host == "itch.io" or host.endswith(".itch.io"):
        entry.update(platform="itch", currency="USD")
        return entry
    if host == "bundleofholding.com":
        entry.update(platform="bundleofholding", currency="USD")
        return entry
    if host == "humblebundle.com":
        entry.update(platform="humble")
        return entry

    html = ""
    try:
        html = fetch(store_url).body.decode("utf-8", "ignore")
    except FetchError as e:
        if e.kind in ("blocked", "robots"):
            entry.update(platform="unknown", status="blocked", notes=str(e))
            return entry
        entry["notes"] = f"home page: {e}"
    try:
        if _try_shopify(_origin(store_url)):
            # /meta.json gives the shop's own currency; the homepage currency follows the
            # visitor's location (Modiphius shows EUR to us, but products.json is GBP).
            meta = _json(_origin(store_url) + "/meta.json")
            cur = meta.get("currency") if isinstance(meta, dict) else None
            entry.update(platform="shopify", currency=cur or shopify_currency(html), recipe_confirmed=today)
            return entry
        woo = _try_woocommerce(store_url, html)
        if woo:
            entry.update(platform="woocommerce", currency=woo[1], recipe={"api_base": woo[0]},
                         recipe_confirmed=today)
            return entry
    except FetchError as e:
        entry.update(platform="unknown", status="blocked", notes=str(e))
    return entry


def merge(shops, found):
    """Add found entries to shops, deduped by store host. Existing entries keep their recipes."""
    have = {_host(s["store_url"]) for s in shops}
    added = []
    for e in found:
        if _host(e["store_url"]) in have:
            continue
        have.add(_host(e["store_url"]))
        shops.append(e)
        added.append(e)
    return added


def main(argv):
    if len(argv) != 1:
        print("usage: python -m scraper.detect <seed.json>")
        return 2
    with open(argv[0]) as f:
        seeds = json.load(f)
    shops = load_shops()
    known = {_host(s["store_url"]) for s in shops}
    found = []
    for s in seeds:
        if _host(s["store_url"]) in known:
            continue
        e = detect(s["store_url"], s.get("name"))
        if s.get("sale_page_url"):
            e["notes"] = ((e["notes"] + "; ") if e["notes"] else "") + "sale page: " + s["sale_page_url"]
        found.append(e)
        print(f"{e['id']}: {e['platform']} ({e['status']}) {e['currency'] or ''}")
    added = merge(shops, found)
    save_shops(shops)
    print(f"{len(added)} shops added, {len(shops)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
