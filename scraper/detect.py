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


# ---------------------------------------------------------------- is this site an RPG seller? (discovery)

STORE_PLATFORMS = ("shopify", "woocommerce", "itch", "bundleofholding", "humble")
# Marketplaces we already read as a whole: a seller whose shop link points there is covered already.
MARKETPLACES = ("drivethrurpg.com", "dmsguild.com", "itch.io", "bundleofholding.com", "humblebundle.com",
                "storytellersvault.com", "wargamevault.com", "pathfindertales.com")
_STORE_WORDS = re.compile(r"\b(shop|store|webstore|web store|online store|buy|catalog|products?)\b", re.I)
_STORE_PATH = re.compile(r"/(shop|store|collections?|products?|catalog|buy)(/|$|\?)", re.I)
# English tabletop RPG words (English products only for now, decided by the user 2026-10-27).
RPG_WORDS = re.compile(
    r"\b(t?t?rpgs?|role[- ]?playing|roleplaying|d&d|dnd|dungeons (?:&|and) dragons|5e|5th edition|pathfinder|"
    r"starfinder|osr|old[- ]school essentials|call of cthulhu|mothership|shadowdark|savage worlds|gm screen|"
    r"game ?master|dungeon ?master|sourcebook|bestiary|core rule ?book|rulebook|quick ?start|character sheets?|"
    r"one[- ]shot|pbta|powered by the apocalypse|forged in the dark|blades in the dark|cypher system|fate core|"
    r"dungeon crawl classics|dcc|m[öo]rk borg|cairn|into the odd|year zero|tabletop adventure|adventure module|"
    r"setting book|campaign setting|monster manual|grimoire|zine)\b", re.I)
RPG_MIN_PRODUCTS = 3          # products whose text names RPG words
RPG_MIN_SHARE = 0.05          # ... or this share of the store's products
ENGLISH_MIN_SHARE = 0.8       # share of Latin letters that are plain ASCII in product titles


def store_links(html, origin):
    """Links on a home page that look like the site's web store: same site (or a subdomain) with a shop
    path or shop words, or a marketplace / storefront elsewhere. -> list of absolute URLs, best first."""
    base = _host(origin)
    root = ".".join(base.split(".")[-2:])
    out = []
    for href, text in re.findall(r"<a\b[^>]*?href=[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", html or "", re.I | re.S):
        url = urllib.parse.urljoin(origin + "/", href.strip())
        if not url.startswith(("http://", "https://")):
            continue
        host = _host(url)
        label = re.sub(r"<[^>]+>|\s+", " ", text).strip()
        same = host == base or host.endswith("." + root)
        if any(host == m or host.endswith("." + m) for m in MARKETPLACES):
            out.append((2, url))
        elif same and host != base and re.match(r"(shop|store|buy|webstore)\.", host):
            out.append((0, url))
        elif same and (_STORE_PATH.search(urllib.parse.urlsplit(url).path) or _STORE_WORDS.search(label)):
            out.append((1, url))
        elif not same and (_STORE_WORDS.search(label) or "myshopify.com" in host):
            out.append((1, url))
    seen, best = set(), []
    for _, u in sorted(out, key=lambda t: t[0]):
        if u not in seen:
            seen.add(u)
            best.append(u)
    return best


def _english(texts):
    letters = [c for t in texts for c in t if c.isalpha()]
    return not letters or sum(c.isascii() for c in letters) / len(letters) >= ENGLISH_MIN_SHARE


def product_texts(entry, get_json=None):
    """Titles (plus type and tags) of a store's products, for the RPG check. None when unknown."""
    get_json = get_json or _json
    origin = _origin(entry["store_url"])
    if entry["platform"] == "shopify":
        data = get_json(f"{origin}/products.json?limit=250")
        if isinstance(data, dict) and isinstance(data.get("products"), list):
            return [" ".join([p.get("title") or "", p.get("product_type") or "",
                              " ".join(p.get("tags") or []) if isinstance(p.get("tags"), list) else str(p.get("tags") or "")])
                    for p in data["products"]]
    if entry["platform"] == "woocommerce":
        data = get_json(f"{entry['recipe']['api_base']}/products?per_page=100")
        if isinstance(data, list):
            return [" ".join([p.get("name") or ""] + [c.get("name") or "" for c in p.get("categories") or []]) for p in data]
    return None


def rpg_store(entry, get_json=None):
    """-> (yes, why). Does this store sell English-language tabletop RPG products?"""
    if entry["platform"] in ("itch", "bundleofholding", "humble"):
        return True, entry["platform"]
    texts = product_texts(entry, get_json)
    if texts is None:
        return False, "products not readable"
    if not texts:
        return False, "no products"
    hits = sum(1 for t in texts if RPG_WORDS.search(t))
    if hits < RPG_MIN_PRODUCTS and hits < RPG_MIN_SHARE * len(texts):
        return False, f"not an RPG store ({hits} of {len(texts)} products name RPG words)"
    if not _english([t.split("  ")[0] for t in texts]):
        return False, "products are not in English"
    return True, f"{hits} of {len(texts)} products name RPG words"


def find_seller(entry, origin, detector=None, get_json=None, get_page=None):
    """A seller lead (RPG news link or directory website) -> (store entry or None, note).
    entry is detector(origin). A home page that is not a store is searched for its shop link."""
    detector = detector or detect
    get_page = get_page or (lambda u: fetch(u).body.decode("utf-8", "ignore"))
    if entry["status"] == "blocked":
        return None, "the site blocks robots"
    tried, last = [], "the store blocks robots"
    cands = [entry]
    if entry["platform"] not in STORE_PLATFORMS:
        try:
            links = store_links(get_page(origin), origin)
        except FetchError as e:
            return None, f"home page not readable: {e.kind}"
        market = next((u for u in links if any(_host(u) == m or _host(u).endswith("." + m) for m in MARKETPLACES)), None)
        own = [u for u in links if u != market][:5]     # a few shop links per site: a runaway guard, not a quota
        for u in own:
            try:
                e = detector(u)
            except Exception:
                continue
            e["store_url"] = _origin(u) + "/" if e["platform"] == "shopify" else u
            cands.append(e)
            tried.append(u)
        if not any(c["platform"] in STORE_PLATFORMS for c in cands):
            if market:
                return None, f"sells through {_host(market)}, which we read already"
            return None, "no web store found" + (f" (tried {len(tried)} shop links)" if tried else "")
    for c in cands:
        if c["platform"] in STORE_PLATFORMS and c["status"] != "blocked":
            ok, why = rpg_store(c, get_json)
            if ok:
                c["notes"] = f"found by discovery: {why}"
                return c, why
            last = why
    return None, last


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
