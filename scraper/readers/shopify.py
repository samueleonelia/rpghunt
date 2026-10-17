"""Shopify reader: /products.json (or a collection's products.json), paged.

A product is a deal when any variant has compare_at_price above price.
"""
import html
import re
import urllib.parse

from scraper.common import FetchError, fetch_json, is_discount, make_deal, money

PAGE_LIMIT = 250
MAX_PAGES = 40
MAX_PAGE_PRICE_CHECKS = 100   # opt-in recipe.page_prices: product pages read per shop


def _plain_text(markup):
    """Shop description HTML -> plain text (for the RPG check's evidence)."""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", markup or ""))).strip()


def _https(url):
    """Shopify image URLs can be protocol-relative (//cdn.shopify.com/...); the site needs https."""
    if not url:
        return None
    return "https:" + url if url.startswith("//") else "https://" + url[7:] if url.startswith("http://") else url


def _origin(shop):
    p = urllib.parse.urlsplit(shop["store_url"])
    return f"{p.scheme}://{p.netloc}"


def feed_urls(shop):
    """Paged product feeds to read: the recipe's collections, else the whole catalog."""
    origin = _origin(shop)
    cols = (shop.get("recipe") or {}).get("collections")
    if cols:
        return [f"{origin}/collections/{c}/products.json" for c in cols]
    return [f"{origin}/products.json"]


def best_discount_variant(product):
    """The on-sale variant with the lowest current price, as (variant, price, was); None if none."""
    best = None
    for v in product.get("variants") or []:
        now, was = money(v.get("price")), money(v.get("compare_at_price"))
        if is_discount(now, was) and (best is None or now < best[1]):
            best = (v, now, was)
    return best


def parse_product(shop, product, origin=None):
    """One Shopify product dict -> a deal, or None when no variant is discounted."""
    pick = best_discount_variant(product)
    if pick is None:
        return None
    variant, now, was = pick
    origin = origin or _origin(shop)
    if now == 0:
        kind = "free"
    elif variant.get("requires_shipping"):
        kind = "physical"
    else:
        kind = "sale"
    vtitle = variant.get("title")
    hints = {
        "product_type": product.get("product_type") or None,
        "tags": product.get("tags") or [],
        "vendor": product.get("vendor") or None,
        "variant": None if vtitle in (None, "Default Title") else vtitle,
        "description": _plain_text(product.get("body_html"))[:300] or None,
        "image": _https(((product.get("images") or [{}])[0] or {}).get("src")),
    }
    return make_deal(
        shop=shop, type=kind, title=product["title"],
        url=f"{origin}/products/{product['handle']}",
        price_now=now, price_was=was, currency=shop.get("currency"),
        source="shopify-api", found_via="/".join(feed_urls(shop)[:1]).replace(origin, ""),
        hints=hints,
    )


def parse_product_from_page(shop, product, origin=None):
    """Opt-in (recipe.page_prices): the feed has no compare_at_price, so read the product page.

    A deal only when the page shows a real discount and its current price is one of the
    product's own variant prices (so a misread page cannot invent a price).
    """
    from scraper.readers import generic  # late import: only shops that opt in need it
    origin = origin or _origin(shop)
    url = f"{origin}/products/{product['handle']}"
    info = generic.page_prices(url)
    if not info or not is_discount(info["price_now"], info["price_was"]):
        return None
    variants = product.get("variants") or []
    if info["price_now"] not in {money(v.get("price")) for v in variants}:
        return None
    ships = any(v.get("requires_shipping") for v in variants)
    kind = "free" if info["price_now"] == 0 else "physical" if ships else "sale"
    hints = {"product_type": product.get("product_type") or None, "tags": product.get("tags") or [],
             "vendor": product.get("vendor") or None, "variant": None, **info["hints"]}
    return make_deal(
        shop=shop, type=kind, title=product["title"], url=url,
        price_now=info["price_now"], price_was=info["price_was"],
        currency=info["currency"] or shop.get("currency"), ends=info["ends"],
        source="page-markup", found_via="/".join(feed_urls(shop)[:1]).replace(origin, ""), hints=hints,
    )


def read_with_stats(shop):
    """-> (deals, stats). stats: items_read, pages. Raises FetchError if the first page fails."""
    origin = _origin(shop)
    deals, seen, items = [], set(), 0
    pages = 0
    recipe = shop.get("recipe") or {}
    page_check = bool(recipe.get("page_prices") and recipe.get("collections"))
    checks = 0
    for feed in feed_urls(shop):
        for page in range(1, MAX_PAGES + 1):
            try:
                data = fetch_json(f"{feed}?limit={PAGE_LIMIT}&page={page}")
            except FetchError:
                if page == 1 and not pages:
                    raise
                break
            products = data.get("products") or []
            if not products:  # only an empty page ends the read: pages can be short
                break
            pages += 1
            items += len(products)
            for p in products:
                if p["id"] in seen:
                    continue
                seen.add(p["id"])
                deal = parse_product(shop, p, origin)
                if deal:
                    deals.append(deal)
                elif page_check and checks < MAX_PAGE_PRICE_CHECKS:
                    checks += 1
                    try:
                        deal = parse_product_from_page(shop, p, origin)
                    except FetchError:
                        continue
                    if deal:
                        deals.append(deal)
    stats = {"items_read": items, "pages": pages}
    if page_check:
        stats["page_price_checks"] = checks
    return deals, stats


def read(shop):
    return read_with_stats(shop)[0]
