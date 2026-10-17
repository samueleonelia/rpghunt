"""DriveThruRPG reader: the public JSON API at api.drivethrurpg.com (never www, which is a bot wall).

GET /api/vBeta/products?onSale=1&pageSize=50&page=N  (JSON:API) -> data[] of ProductSummary.
Each product has options[] (a PDF, a print book...). An option's `price` is its current price and
`msrp` its normal price (a string such as "4.9500", or the number 0 when unknown). Prices come only
from the options; the product-level `price` / `specialPrice` fields are not used for the deal.

No sale end date exists in the API, and some products have been "on sale" for years, so this shop
is flagged `everyday_discounts` in shops.json (see scraper/check.py).
"""
import html
import re
import urllib.parse

from scraper.common import FetchError, fetch_json, is_discount, make_deal, money

API = "https://api.drivethrurpg.com/api/vBeta/products"
SITE = "https://www.drivethrurpg.com"
PAGE_SIZE = 50          # the API caps it at 50
MAX_PAGES = 80          # the sale list was ~49 pages on 2026-10-17; this is the safety cap


# DriveThruRPG's image server. The API gives only relative paths ("62/2727.jpg"); this base
# served them as real images when checked on 2026-10-17 (it is a CDN, not the bot-walled site).
IMAGE_BASE = "https://d1vzi28wh99zvq.cloudfront.net/images/"

def _plain_text(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def product_url(product_id, slug):
    """The site's own product URL, the form EN World links use: /product/<id>/<slug> (no /en/)."""
    return f"{SITE}/product/{product_id}/{slug}" if slug else f"{SITE}/product/{product_id}"


def option_discount(option):
    """-> (price, msrp, pct) when this option is really discounted, else None."""
    price, msrp = money(option.get("price")), money(option.get("msrp"))
    if not msrp or not is_discount(price, msrp):
        return None
    return price, msrp, (msrp - price) / msrp


def pick_option(options):
    """The option with the biggest real discount (percent; ties go to the lower price).
    -> (option, price, msrp) or None."""
    best = None
    for o in options or []:
        d = option_discount(o)
        if d is None:
            continue
        price, msrp, pct = d
        if best is None or (pct, -price) > (best[3], -best[1]):
            best = (o, price, msrp, pct)
    return None if best is None else best[:3]


def _publishers(page):
    """{publisher id: name} from the page's `included` list."""
    out = {}
    for inc in page.get("included") or []:
        if inc.get("type") == "Publisher":
            a = inc.get("attributes") or {}
            if a.get("publisherId") is not None:
                out[a["publisherId"]] = a.get("name")
    return out


def _date(text):
    """'2026-03-01T00:00:00-06:00' -> '2026-03-01'; the API's 'never' value (1969/1970) -> None."""
    day = (text or "")[:10]
    return day if re.match(r"(19[89]\d|20\d\d)-\d\d-\d\d$", day) else None


def parse_product(shop, item, publishers=None):
    """One ProductSummary -> a deal, or None (not on sale, PWYW, no real discount)."""
    a = item.get("attributes") or {}
    if a.get("isPwyw") or not a.get("productId"):
        return None
    pick = pick_option(a.get("options"))
    if pick is None:
        return None
    option, now, was = pick
    desc = a.get("description") or {}
    title = (desc.get("name") or "").strip()
    if not title:
        return None
    printed = option.get("type") != "digital"
    kind = "free" if now == 0 else "physical" if printed else "sale"
    hints = {
        "description": _plain_text(desc.get("shortDescription"))[:300] or None,
        "option": option.get("optionValueName"),
        "variant": option.get("optionValueName"),
        "promo_text": (a.get("promoText") or "").strip() or None,
        "publisher_id": a.get("publisherId"),
        "vendor": (publishers or {}).get(a.get("publisherId")),
        "is_community_content": bool(a.get("isCommunityContent")),
        "is_ai": bool(a.get("isAi")),
        "is_bundle": bool(a.get("isBundle")),
        "date_available": _date(a.get("dateAvailable")),
        "product_id": a["productId"],
        "rating": a.get("rating"),
        "rating_count": money(a.get("ratingCount")),
        "image": (IMAGE_BASE + a["image"]) if a.get("image") else None,
    }
    return make_deal(
        shop=shop, type=kind, title=title, url=product_url(a["productId"], desc.get("slug")),
        price_now=now, price_was=was, currency=shop.get("currency") or "USD",
        source="drivethrurpg-api", found_via="/api/vBeta/products?onSale=1",
        format=option.get("optionValueName"), hints=hints,
    )


def read_with_stats(shop):
    """-> (deals, stats). stats: items_read, pages, community, ai. Raises FetchError if page 1 fails."""
    deals, seen, items, pages = [], set(), 0, 0
    url = f"{API}?onSale=1&pageSize={PAGE_SIZE}&page=1"
    while url and pages < MAX_PAGES:
        try:
            page = fetch_json(url)
        except FetchError:
            if not pages:
                raise
            break
        data = page.get("data") or []
        if not data:          # only an empty page ends the read: pages can be short
            break
        pages += 1
        items += len(data)
        publishers = _publishers(page)
        for item in data:
            pid = (item.get("attributes") or {}).get("productId")
            if pid in seen:
                continue
            seen.add(pid)
            deal = parse_product(shop, item, publishers)
            if deal:
                deals.append(deal)
        nxt = (page.get("links") or {}).get("next")
        url = urllib.parse.urljoin(API, nxt) if nxt else None
        if url and urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(API).netloc:
            break             # never follow a link off the API host
    stats = {"items_read": items, "pages": pages,
             "community_content": sum(d["hints"]["is_community_content"] for d in deals),
             "ai_flagged": sum(d["hints"]["is_ai"] for d in deals)}
    return deals, stats


def read(shop):
    return read_with_stats(shop)[0]
