"""Shared pieces for every shop reader: paths, polite fetching, the deal record.

Every reader returns a list of deals built with make_deal(). run.py writes them to
data/deals/raw/<date>-scraper.json, the same place and shape the old agents used,
so scripts/build_deals.py checks them unchanged.
"""
import datetime
import json
import pathlib
import re
import threading
import time
import unicodedata
import urllib.parse
import urllib.robotparser

from scrapling.fetchers import Fetcher

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHOPS = ROOT / "data" / "shops" / "shops.json"
RAW = ROOT / "data" / "deals" / "raw"
TESTSET = ROOT / "data" / "testset"

# Honest bot name, the only place it is defined. The page explains who we are and how to ask us to stop
# (text in agents/bot-page.md). robotparser matches the part before the "/", so a shop's robots.txt
# rules for "RPGHuntBot" apply to us.
UA = "RPGHuntBot/1.0 (+https://samueleonelia.github.io/rpghunt/bot.html)"
# Hosts we never request, whatever the caller asks: DriveThruRPG's website sits behind a bot wall we do not
# try to pass. Its data comes from api.drivethrurpg.com only (scraper/readers/drivethrurpg.py).
NEVER_FETCH = {"www.drivethrurpg.com", "drivethrurpg.com"}
DELAY = 1.5          # seconds between two requests to the same site
BLOCKED = {401, 403, 406, 503}
TYPES = {"sale", "bundle", "physical", "free"}
# Plain requests: our own User-Agent, no made-up Google referer, no browser impersonation,
# retries handled in fetch(). Impersonation is off on purpose: with it, Shopify served
# Exalted Funeral's products.json without compare-at prices (0 sale items instead of 213).
_OPTS = {"headers": {"User-Agent": UA}, "stealthy_headers": False, "impersonate": None,
         "retries": 1, "timeout": 30}


class FetchError(Exception):
    """A page we could not read. kind: blocked | dead | robots | error."""
    def __init__(self, kind, url, detail=""):
        super().__init__(f"{kind}: {url} {detail}".strip())
        self.kind, self.url, self.detail = kind, url, detail


# One lock and one clock per site, so a site never gets two requests at once
# and always gets DELAY seconds of rest. Different sites run in parallel.
_host_locks, _host_last, _robots = {}, {}, {}
_guard = threading.Lock()


def _host(url):
    return urllib.parse.urlsplit(url).netloc.lower()


_robots_locks = {}


def _allowed(url):
    host = _host(url)
    with _guard:
        lock = _robots_locks.setdefault(host, threading.Lock())
    with lock:  # one robots.txt fetch per site, even when many threads start at once
        return _allowed_locked(url, host)


def _allowed_locked(url, host):
    with _guard:
        rp = _robots.get(host)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = Fetcher.get(f"https://{host}/robots.txt", **_OPTS)
            rp.parse(r.body.decode("utf-8", "ignore").splitlines() if r.status == 200 else [])
        except Exception:
            rp.parse([])  # no robots.txt readable: nothing is disallowed
        with _guard:
            _robots[host] = rp
    return rp.can_fetch(UA, url)


def fetch(url, tries=3):
    """GET a page politely. Returns a Scrapling Response (.status, .body, .json(), .css()).

    Respects robots.txt, waits DELAY between requests to one site, backs off on HTTP 429.
    Raises FetchError when the page is blocked, gone, or disallowed.
    """
    host = _host(url)
    if host in NEVER_FETCH:
        raise FetchError("blocked", url, "never fetched: this host serves a bot wall")
    if not _allowed(url):
        raise FetchError("robots", url, "disallowed by robots.txt")
    with _guard:
        lock = _host_locks.setdefault(host, threading.Lock())
    with lock:
        for attempt in range(tries):
            wait = DELAY - (time.monotonic() - _host_last.get(host, 0))
            if wait > 0:
                time.sleep(wait)
            try:
                resp = Fetcher.get(url, **_OPTS)
            except Exception as e:
                _host_last[host] = time.monotonic()
                if attempt == tries - 1:
                    raise FetchError("error", url, type(e).__name__)
                continue
            _host_last[host] = time.monotonic()
            if resp.status == 429:
                time.sleep(15 * (attempt + 1))
                continue
            if resp.status in BLOCKED:
                raise FetchError("blocked", url, f"HTTP {resp.status}")
            if resp.status >= 400:
                raise FetchError("dead", url, f"HTTP {resp.status}")
            return resp
        raise FetchError("blocked", url, "HTTP 429 after retries")


def fetch_json(url):
    return fetch(url).json()


def plain(text):
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def norm_url(url):
    """Comparable form of a URL: no scheme, no www, no query, no trailing slash."""
    p = urllib.parse.urlsplit(url or "")
    host = p.netloc.lower().removeprefix("www.")
    return host + p.path.rstrip("/")


_DTRPG_PRODUCT = re.compile(r"^/(?:[a-z]{2}/)?product/(\d+)(?:/|$)")


def drivethru_product_id(url):
    """Product id from a www.drivethrurpg.com product link (/product/<id>/<slug>, also /en/product/...);
    None for anything else. The API reader and EN World links both carry this id, the slug may differ."""
    p = urllib.parse.urlsplit(url or "")
    host = p.netloc.lower().split(":")[0]
    if host not in ("drivethrurpg.com", "www.drivethrurpg.com"):
        return None
    m = _DTRPG_PRODUCT.match(p.path)
    return int(m.group(1)) if m else None


def money(value, minor_unit=None):
    """'12.50', 1250 (with minor_unit=2) or 12.5 -> 12.5; None when missing or not a number."""
    if value in (None, ""):
        return None
    try:
        n = float(value)
    except (TypeError, ValueError):
        return None
    return round(n / 10 ** minor_unit, 2) if minor_unit else round(n, 2)


def make_deal(*, shop, type, title, url, price_now, price_was, currency, source,
              found_via, game=None, format=None, ends=None, hints=None, notes=None):
    """One deal in the raw format build_deals.py reads.

    shop: the shop entry from shops.json (its id and name are copied).
    source: which reader saw it (shopify-api, woocommerce-api, itch-data, drivethrurpg-api, bundle-page, jsonld, recipe).
    hints: free facts for later checks (product type, tags, variant name...). Never a verdict.
    Prices come only from the shop's own data; a reader never guesses them.
    """
    assert type in TYPES, type
    pct = None
    if price_now is not None and price_was:
        pct = round(100 * (1 - price_now / price_was))
    return {
        "type": type,
        "title": title.strip(),
        "game": game,
        "shop": shop["name"],
        "shop_id": shop["id"],
        "url": url,
        "price_now": price_now,
        "price_was": price_was,
        "currency": currency,
        "discount_pct": pct,
        "format": format,
        "ends": ends,
        "summary": None,
        "found_via": found_via,
        "source": source,
        "confidence": "high",
        "hints": hints or {},
        "notes": notes,
        "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    }


def is_discount(price_now, price_was):
    """A real discount: both prices known and the current one lower."""
    return price_now is not None and price_was is not None and price_now < price_was


def load_shops():
    return json.loads(SHOPS.read_text()) if SHOPS.exists() else []


def save_shops(shops):
    SHOPS.parent.mkdir(parents=True, exist_ok=True)
    SHOPS.write_text(json.dumps(shops, ensure_ascii=False, indent=1) + "\n")
