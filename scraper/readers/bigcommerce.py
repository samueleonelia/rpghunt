"""BigCommerce reader (GameNerdz): the deals listing's own embedded product data, no browser needed.

The deals page draws its grid with JavaScript, but its plain HTML carries the listing's data for the
shop's analytics: `window.bodl = JSON.parse(decodeBase64("..."))`, whose first event holds
`line_items` (product_id, product_name, purchase_price = current price, retail_price = normal price).
recipe.deals_url is the listing; pages are ?page=N and an empty list ends the read.

A deal needs a visible normal price above the current one. Items named "(Add to cart to see price)"
show their real price only in the cart, which robots.txt closes to us: they are counted, never guessed.
Deal links use /products.php?productId=<id>, which the shop serves as the product page.
"""
import base64
import json
import re
import urllib.parse

from scraper.common import FetchError, fetch, is_discount, make_deal, money

MAX_PAGES = 500          # only stops a runaway loop; reported when hit
SOURCE = "bigcommerce-data"
_BODL = re.compile(r'window\.bodl\s*=\s*JSON\.parse\(\s*decodeBase64\(\s*"([A-Za-z0-9+/=]+)"')
_HIDDEN = re.compile(r"\(\s*add to cart to see price\s*\)", re.I)
_SUFFIX = re.compile(r"\s*\((?:on sale[^)]*|add to cart to see price)\)\s*$", re.I)


def line_items(html):
    """-> the listing's line_items from window.bodl, or None when the page carries no such data."""
    m = _BODL.search(html)
    if not m:
        return None
    try:
        data = json.loads(base64.b64decode(m.group(1)))
        event = (data.get("events") or [{}])[0]
    except (ValueError, TypeError):
        return None
    for key, value in event.items():
        if key.startswith("bodl_") and isinstance(value, dict) and "line_items" in value:
            return value["line_items"] or []
    return None


def clean_title(name):
    return _SUFFIX.sub("", (name or "").strip()).strip()


def parse_item(shop, item, origin):
    """One line item -> a deal, or None (hidden price, no visible discount)."""
    name = item.get("product_name") or ""
    if _HIDDEN.search(name) or not item.get("product_id"):
        return None
    now, was = money(item.get("purchase_price")), money(item.get("retail_price"))
    if not is_discount(now, was):
        return None
    title = clean_title(name)
    if not title:
        return None
    return make_deal(
        shop=shop, type="free" if now == 0 else "physical", title=title,
        url=f"{origin}/products.php?productId={item['product_id']}",
        price_now=now, price_was=was, currency=item.get("currency") or shop.get("currency") or "USD",
        source=SOURCE, found_via=urllib.parse.urlsplit(shop["recipe"]["deals_url"]).path,
        hints={"vendor": item.get("brand_name"), "sku": item.get("sku"),
               "categories": item.get("category_names") or [], "product_id": item["product_id"]},
    )


def read_with_stats(shop):
    """-> (deals, stats). stats: items_read, pages, hidden_price. Raises FetchError if page 1 fails."""
    base = shop["recipe"]["deals_url"]
    p = urllib.parse.urlsplit(base)
    origin = f"{p.scheme}://{p.netloc}"
    deals, seen, items, hidden, pages = [], set(), 0, 0, 0
    stats = {}
    for page in range(1, MAX_PAGES + 1):
        sep = "&" if "?" in base else "?"
        try:
            html = fetch(f"{base}{sep}page={page}").body.decode("utf-8", "ignore")
        except FetchError:
            if page == 1:
                raise
            stats["stopped_early"] = f"page {page} could not be read; later pages were skipped"
            break
        batch = line_items(html)
        if batch is None:
            if page == 1:
                raise FetchError("error", base, "no embedded product data (window.bodl) on the deals page")
            stats["stopped_early"] = f"page {page} had no embedded product data; later pages were skipped"
            break
        if not batch:                       # an empty list is the end of the listing
            break
        pages += 1
        for item in batch:
            pid = item.get("product_id")
            if pid in seen:
                continue
            seen.add(pid)
            items += 1
            if _HIDDEN.search(item.get("product_name") or ""):
                hidden += 1
                continue
            deal = parse_item(shop, item, origin)
            if deal:
                deals.append(deal)
    else:
        stats["stopped_early"] = f"stopped at the {MAX_PAGES}-page safety limit; more pages may exist"
    return deals, {"items_read": items, "pages": pages, "hidden_price": hidden, **stats}


def read(shop):
    return read_with_stats(shop)[0]
