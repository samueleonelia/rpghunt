"""WooCommerce reader: Store API /products?on_sale=true, paged until an empty page.

Prices in the Store API are minor units (currency_minor_unit decimals).
"""
import html
import re

from scraper.common import FetchError, fetch_json, is_discount, make_deal, money

PER_PAGE = 100
MAX_PAGES = 500         # only stops a runaway loop; reported when hit
PHYSICAL_WORDS = ("hardcover", "hardback", "softcover", "paperback", "print", "boxed", "box set",
                  "miniature", "dice")


def _names(items):
    return [html.unescape(i.get("name", "")) for i in items or [] if i.get("name")]


def guess_type(title, categories, tags):
    """Store API has no shipping flag, so this is a guess from names; hints say so."""
    blob = " ".join([title] + categories + tags).lower()
    if "bundle" in blob:
        return "bundle"
    if "pdf" in blob:
        return "sale"
    if any(w in blob for w in PHYSICAL_WORDS):
        return "physical"
    return "sale"


def parse_product(shop, product):
    """-> (deal or None, variant_only: bool). variant_only: on_sale but no product-level discount."""
    prices = product.get("prices") or {}
    unit = prices.get("currency_minor_unit", 2)
    now = money(prices.get("price"), unit)
    was = money(prices.get("regular_price"), unit)
    if not is_discount(now, was):
        return None, product.get("type") in ("variable", "grouped")
    title = html.unescape(product["name"])
    cats, tags = _names(product.get("categories")), _names(product.get("tags"))
    kind = "free" if now == 0 else guess_type(title, cats, tags)
    desc = product.get("short_description") or product.get("description") or ""
    desc = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", desc))).strip()[:300] or None
    image = ((product.get("images") or [{}])[0] or {}).get("src")
    hints = {"categories": cats, "tags": tags, "type": product.get("type"), "description": desc, "image": image,
             "type_guess": kind != "free"}
    deal = make_deal(
        shop=shop, type=kind, title=title, url=product["permalink"],
        price_now=now, price_was=was, currency=prices.get("currency_code") or shop.get("currency"),
        source="woocommerce-api", found_via=(shop.get("recipe") or {}).get("api_base", ""),
        hints=hints,
    )
    return deal, False


def read_with_stats(shop):
    """-> (deals, stats). stats: items_read, pages, skipped_variant_only."""
    base = shop["recipe"]["api_base"].rstrip("/")
    deals, seen, items, skipped, pages = [], set(), 0, 0, 0
    stopped = None
    for page in range(1, MAX_PAGES + 1):
        try:
            data = fetch_json(f"{base}/products?on_sale=true&per_page={PER_PAGE}&page={page}")
        except FetchError:
            if page == 1:
                raise
            break
        if not isinstance(data, list) or not data:
            break
        pages += 1
        items += len(data)
        for p in data:
            if p["id"] in seen:
                continue
            seen.add(p["id"])
            deal, variant_only = parse_product(shop, p)
            if deal:
                deals.append(deal)
            elif variant_only:
                skipped += 1
    else:
        stopped = f"stopped at the {MAX_PAGES}-page safety limit; more sale pages may exist"
    stats = {"items_read": items, "pages": pages, "skipped_variant_only": skipped}
    if stopped:
        stats["stopped_early"] = stopped
    return deals, stats


def read(shop):
    return read_with_stats(shop)[0]
