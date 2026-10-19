"""Generic reader: shops with no product API. Reads sale pages, then each product page.

Order of trust for one product page (page_prices):
  1. JSON-LD Product/Offer (price, priceCurrency, priceValidUntil, ListPrice specs)
  2. common platform sale markup for the was-price (Shopify themes, WooCommerce <del>,
     BigCommerce price--non-sale / price--rrp, generic <s>/<del>/.was-price)
  3. recipe CSS selectors (price_now / price_was / ends), which override both
Hidden elements (inline display:none, hidden attribute) are never a price source.
A deal is made only when both prices are known and the current one is lower.
"""
import datetime
import json
import re
import threading
import urllib.parse

from scrapling.parser import Selector

from scraper.common import FetchError, fetch, is_discount, load_shops, make_deal, money, save_shops

_shops_lock = threading.Lock()   # shops run in parallel threads; shops.json is one file
MAX_PAGES = 500          # sale-page pagination; only stops a runaway loop, reported when hit
MAX_PRODUCTS = 5000      # per shop; only stops a runaway loop, reported when hit
END_WINDOW_DAYS = 120    # a valid-until further away than this is a default, not a sale end

PRODUCT_PATH = re.compile(r"/(products?|p|item|items|shop/p)/[^/?#]+", re.I)
_SKIP_PATH = re.compile(r"/(cart|checkout|account|login|search|collections?|category|categories|blog|tag)(/|$)", re.I)
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.I)
_NUM = re.compile(r"\d[\d.,   ]*")
# A money amount, not just any number: a currency sign or code next to it, or cents ("12.50").
# Keeps "save 20%", "3 issues" or "2026" from ever being read as a price.
_MONEY = re.compile(r"(?:US\$|[$£€¥]|\b(?:USD|EUR|GBP|CAD|AUD)\b)\s?\d[\d,]*(?:\.\d{1,2})?(?![\d%])"
                    r"|\d[\d.,]*\s?(?:[$£€]|\b(?:USD|EUR|GBP|CAD|AUD)\b)"
                    r"|\b\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\b(?!\s*%)")

# was-price candidates: (css, what it means). Order = most specific first.
WAS_CSS = [
    ".price__sale s", ".price__sale .price-item--regular", "s.price-item--regular",   # Shopify Dawn-like
    ".price--non-sale", ".price--rrp", ".price--was",                                  # BigCommerce
    ".price del", ".price del .amount", "p.price del", "span.price del",               # WooCommerce
    "[class*='compare-at']", "[class*='compare_at']", "[class*='was-price']",
    "[class*='was_price']", "[class*='old-price']", "[class*='old_price']",
    "[class*='price-was']", "[class*='list-price']", "[class*='original-price']",
    "[class*='regular-price']", "[class*='strike']",
    "del", "s", "strike",
]
NOW_CSS = [
    ".price__sale .price-item--sale", ".price-item--sale", ".price--withoutTax", ".price--main",
    ".price ins .amount", ".price ins", "[class*='sale-price']", "[class*='sale_price']",
    "[class*='price-now']", "[class*='special-price']", "[class*='current-price']",
    "[class*='price--sale']",
]
# Words that suggest a physical product (shipped book/box/dice) vs a digital one.
_DIGITAL = re.compile(r"\b(pdf|digital|vtt|foundry|roll20|ebook|e-book|download|fantasy grounds)\b", re.I)
_PHYSICAL = re.compile(r"\b(hardcover|softcover|hardback|paperback|box set|boxed|deck|dice|screen|miniatures?|"
                       r"print|book|zine|map pack|slipcase|tarot|cards)\b", re.I)


# ---------------------------------------------------------------- helpers

def parse_amount(text):
    """'$1,299.00' -> 1299.0, '12,50 EUR' -> 12.5, 'Free' -> 0.0, junk -> None."""
    if not text:
        return None
    t = text.strip()
    if re.fullmatch(r"(?i)free", t):
        return 0.0
    m = _MONEY.search(t)
    if not m:  # a bare number or a percentage is never a price
        return None
    t = m.group(0)
    m = _NUM.search(t)
    if not m:
        return None
    s = m.group(0).strip().replace(" ", "").replace(" ", "").replace(" ", "").rstrip(".,")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        thou = "." if dec == "," else ","
        s = s.replace(thou, "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".") if re.search(r",\d{1,2}$", s) and s.count(",") == 1 else s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    return money(s)


def hidden(el):
    """True when the element or an ancestor is hidden by inline style or the hidden attribute."""
    node = el
    while node is not None:
        attrs = getattr(node, "attrib", None) or {}
        if "hidden" in attrs or _HIDDEN_STYLE.search(attrs.get("style") or ""):
            return True
        node = node.parent
    return False


def visible(sel, css):
    return [e for e in sel.css(css) if not hidden(e)]


def _vtext(node):
    """Text of an lxml node without hidden subtrees, scripts or styles."""
    if not isinstance(node.tag, str) or node.tag in ("script", "style", "noscript", "template"):
        return ""
    if "hidden" in node.attrib or _HIDDEN_STYLE.search(node.attrib.get("style") or ""):
        return ""
    parts = [node.text or ""]
    for child in node:
        parts.append(_vtext(child))
        parts.append(child.tail or "")
    return " ".join(parts)


def _text(el):
    """Visible text of a Scrapling element (hidden children are left out)."""
    return re.sub(r"\s+", " ", _vtext(el._root)).strip()


def _first_amount(els):
    for e in els:
        v = parse_amount(_text(e))
        if v is not None:
            return v
    return None


def _jsonld_nodes(sel):
    out = []
    for s in sel.css("script[type='application/ld+json']"):
        raw = (s.text or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        stack = [data]
        while stack:
            n = stack.pop()
            if isinstance(n, list):
                stack.extend(n)
            elif isinstance(n, dict):
                out.append(n)
                stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
    return out


def _is_type(node, name):
    t = node.get("@type")
    return name in (t if isinstance(t, list) else [t])


def _jsonld_product(sel):
    """-> dict(title, now, was, currency, valid_until) from the first Product with an Offer, else None."""
    for n in _jsonld_nodes(sel):
        if not (_is_type(n, "Product") or _is_type(n, "ProductGroup")):
            continue
        offers = n.get("offers")
        offers = offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []
        best = None
        for o in offers:
            if not isinstance(o, dict):
                continue
            now = money(o.get("price")) if o.get("price") not in (None, "") else money(o.get("lowPrice"))
            if now is None:
                specs = o.get("priceSpecification")
                for sp in (specs if isinstance(specs, list) else [specs]):
                    if isinstance(sp, dict) and money(sp.get("price")) is not None \
                            and not re.search(r"list|strike|srp", str(sp.get("priceType", "")), re.I):
                        now = money(sp["price"])
                        break
            if now is None:
                continue
            was = None
            for key in ("listPrice", "priceBeforeDiscount", "strikethroughPrice"):
                was = was or money(o.get(key))
            specs = o.get("priceSpecification")
            for sp in (specs if isinstance(specs, list) else [specs]):
                if isinstance(sp, dict) and re.search(r"list|strike|srp", str(sp.get("priceType", "")), re.I):
                    was = was or money(sp.get("price"))
            cand = {"title": n.get("name"), "now": now, "was": was,
                    "currency": o.get("priceCurrency"), "valid_until": o.get("priceValidUntil")}
            if best is None or now < best["now"]:
                best = cand
        if best:
            return best
    return None


def _meta(sel, prop):
    for m in sel.css("meta"):
        a = m.attrib
        if a.get("property") == prop or a.get("name") == prop:
            return a.get("content")
    return None


def _title(sel, ld):
    if ld and ld.get("title"):
        return str(ld["title"]).strip()
    og = _meta(sel, "og:title")
    if og:
        return og.strip()
    h1 = visible(sel, "h1")
    if h1:
        return _text(h1[0])
    t = sel.css("title")
    return _text(t[0]) if t else None


def sale_end(value, today=None):
    """-> (iso date or None, hint or None). A machine date counts as a sale end only when it is
    within END_WINDOW_DAYS ahead (and not already past); anything else is a shop default."""
    if not value:
        return None, None
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(value))
    if not m:
        return None, f"validUntil unreadable: {value}"
    try:
        d = datetime.date.fromisoformat(m.group(1))
    except ValueError:
        return None, f"validUntil unreadable: {value}"
    today = today or datetime.date.today()
    if d < today:
        return None, f"validUntil {d} already past, not used as an end date"
    if (d - today).days > END_WINDOW_DAYS:
        return None, f"validUntil {d} is over {END_WINDOW_DAYS} days away: treated as a default, not a sale end"
    return d.isoformat(), None


def _price_boxes(el):
    """Ancestors to search for the current price, innermost first: the parent, then up to
    4 levels of price-looking blocks. Wide blocks (long text) are skipped."""
    node, boxes = el.parent, []
    for level in range(5):
        if node is None or node.tag in ("body", "html"):
            break
        cls = (node.attrib.get("class") or "") + " " + (node.attrib.get("id") or "")
        if level == 0 or re.search(r"price|pricing|amount", cls, re.I):
            if len(_text(node)) < 250:
                boxes.append(node)
        node = node.parent
    return boxes


def _amounts(text):
    return [a for a in (parse_amount(m.group(0)) for m in _MONEY.finditer(text)) if a is not None]


def _markup_prices(sel, ld_now):
    """-> (now, was) from sale markup. When ld_now is known, only a was-price whose price block
    also shows that current price counts (so related-product carousels cannot leak in)."""
    now_css = ", ".join(NOW_CSS)
    seen = set()
    for css in WAS_CSS:
        for el in visible(sel, css):
            if id(el._root) in seen:
                continue
            seen.add(id(el._root))
            was = parse_amount(_text(el))
            if not was:
                continue
            for box in _price_boxes(el):
                if ld_now is not None:
                    if ld_now < was and ld_now in _amounts(_text(box)):
                        return ld_now, was
                    continue
                cands = [a for a in (parse_amount(_text(e)) for e in visible(box, now_css)) if a is not None and a < was]
                now = min(cands) if cands else None
                if now is None:  # last resort: the lowest other amount in the same small block
                    others = [a for a in _amounts(_text(box)) if a != was]
                    now = min(others) if others else None
                if now is not None and now < was:
                    return now, was
    return None, None


def _plain_now(sel):
    """Current price when there is no was-price: first short, visible price element."""
    for css in NOW_CSS + ["[itemprop='price']", ".price", "[class*='price']"]:
        for el in visible(sel, css):
            v = parse_amount(el.attrib.get("content")) if el.attrib.get("itemprop") == "price" else None
            if v is None:
                t = _text(el)
                v = parse_amount(t) if len(t) < 60 else None
            if v is not None:
                return v
    return None


def parse_page(html, url="", recipe=None):
    """Product page HTML -> {title, price_now, price_was, currency, ends, source, hints} or None.

    price_was is None when the page shows no reliable was-price. None only when no price at all.
    """
    sel = Selector(html)
    recipe = recipe or {}
    hints = {}
    ld = _jsonld_product(sel)
    now = was = None
    source = None
    currency = None

    if recipe.get("price_now") or recipe.get("price_was"):
        now = _first_amount(visible(sel, recipe["price_now"])) if recipe.get("price_now") else None
        was = _first_amount(visible(sel, recipe["price_was"])) if recipe.get("price_was") else None
        if now is not None and was is not None:
            source = "recipe"
    if source is None:
        now, was = (None, None)
        if ld:
            now, was, currency = ld["now"], ld["was"], ld["currency"]
            if was is not None and not is_discount(now, was):
                was = None
            source = "jsonld"
        if was is None:
            m_now, m_was = _markup_prices(sel, now)
            if m_was is not None:
                now, was, source = m_now, m_was, "page-markup"
        if now is None:
            now = _plain_now(sel)
            source = "page-markup" if now is not None else source
        if now is None:
            meta_now = money(_meta(sel, "product:price:amount") or _meta(sel, "og:price:amount"))
            if meta_now is not None:
                now, source = meta_now, "page-markup"
                currency = currency or _meta(sel, "product:price:currency") or _meta(sel, "og:price:currency")
    if now is None:
        return None

    ends = None
    if recipe.get("ends"):
        els = visible(sel, recipe["ends"])
        ends, hint = sale_end(_text(els[0]) if els else None)
        if hint:
            hints["ends"] = hint
    elif ld:
        ends, hint = sale_end(ld["valid_until"])
        if hint:
            hints["ends"] = hint
    return {"title": _title(sel, ld), "price_now": now, "price_was": was, "currency": currency,
            "ends": ends, "source": source, "hints": hints}


def page_prices(url, recipe=None):
    """Fetch one product page and read it. None when the page has no readable price."""
    resp = fetch(url)
    return parse_page(resp.body.decode(resp.encoding or "utf-8", "ignore"), url, recipe)


# ---------------------------------------------------------------- sale pages

def _same_host(a, b):
    return urllib.parse.urlsplit(a).netloc.lower().removeprefix("www.") == \
        urllib.parse.urlsplit(b).netloc.lower().removeprefix("www.")


def product_links(sel, page_url, recipe=None):
    """Product URLs on a listing page: recipe CSS, else same-host links that look like products."""
    recipe = recipe or {}
    out, seen = [], set()

    def add(href):
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            return
        full = urllib.parse.urljoin(page_url, href).split("#")[0]
        key = full.split("?")[0].rstrip("/")
        if key not in seen:
            seen.add(key)
            out.append(full)

    if recipe.get("product_link"):
        for a in sel.css(recipe["product_link"]):
            if hidden(a):
                continue
            add(a.attrib.get("href") or (a.css("a")[0].attrib.get("href") if a.css("a") else None))
        return out
    for a in sel.css("a[href]"):
        href = a.attrib["href"]
        full = urllib.parse.urljoin(page_url, href)
        path = urllib.parse.urlsplit(full).path
        if not _same_host(full, page_url) or hidden(a):
            continue
        if PRODUCT_PATH.search(path) and not _SKIP_PATH.search(path):
            add(href)
    # card-based themes (BigCommerce, WooCommerce loops): product links sit in the card title
    for a in sel.css(".card-title a, .productCard-title a, li.product a.woocommerce-LoopProduct-link"):
        if not hidden(a) and _same_host(urllib.parse.urljoin(page_url, a.attrib.get("href", "")), page_url):
            add(a.attrib.get("href"))
    return out


def next_page(sel, page_url):
    for css in ("a[rel='next']", "link[rel='next']", ".pagination-item--next a", "a.next", "a.next.page-numbers",
                "li.next a", "a[aria-label='Next']", "a[aria-label='Next page']"):
        for e in sel.css(css):
            href = e.attrib.get("href")
            if href and not hidden(e):
                full = urllib.parse.urljoin(page_url, href)
                if full != page_url:
                    return full
    return None


def guess_type(title, price_now):
    """-> (type, hint). Words in the title only; a guess, recorded as hints.type_guess."""
    if price_now == 0:
        return "free", "price 0"
    t = title or ""
    if _DIGITAL.search(t):
        return "sale", "digital word in title"
    if _PHYSICAL.search(t):
        return "physical", "physical word in title"
    return "sale", "no format word in title (default)"


def sale_page_urls(shop):
    """Recipe sale pages; falls back to the 'sale page: <url>' note and moves it into the recipe."""
    recipe = shop.get("recipe") or {}
    pages = list(recipe.get("sale_pages") or [])
    if not pages:
        m = re.search(r"sale page:\s*(\S+)", shop.get("notes") or "")
        if m:
            pages = [m.group(1)]
            _store_sale_page(shop, pages)
    return pages


def _store_sale_page(shop, pages):
    shop.setdefault("recipe", {})["sale_pages"] = pages
    try:  # persist: reload under a lock so edits made elsewhere in the file are not lost
        with _shops_lock:
            fresh = load_shops()
            for s in fresh:
                if s["id"] == shop["id"]:
                    s.setdefault("recipe", {}).setdefault("sale_pages", pages)
            save_shops(fresh)
    except Exception:
        pass


def read_with_stats(shop):
    """-> (deals, stats). stats: items_read (products checked), sale_pages, errors-as-text in 'skipped'."""
    recipe = shop.get("recipe") or {}
    pages = sale_page_urls(shop)
    if not pages:
        return [], {"items_read": 0, "no_sale_page": True}

    links, listing_errors, stopped = [], [], []
    for start in pages:
        url, seen_pages = start, set()
        for _ in range(MAX_PAGES):
            if url in seen_pages:
                break
            seen_pages.add(url)
            try:
                resp = fetch(url)
            except FetchError as e:
                if url == start and not links:
                    raise
                listing_errors.append(str(e))
                break
            sel = Selector(resp.body.decode(resp.encoding or "utf-8", "ignore"))
            for l in product_links(sel, url, recipe):
                if l not in links:
                    links.append(l)
            if len(links) >= MAX_PRODUCTS:
                break
            url = next_page(sel, url)
            if not url:
                break
        else:
            stopped.append(f"stopped at the {MAX_PAGES}-page safety limit on {start}; more sale pages may exist")
    if len(links) >= MAX_PRODUCTS:
        stopped.append(f"stopped at the {MAX_PRODUCTS}-product safety limit; some products may not be checked")
    links = links[:MAX_PRODUCTS]

    deals, checked, failed = [], 0, 0
    for link in links:
        try:
            info = page_prices(link, recipe)
        except FetchError as e:
            failed += 1
            if e.kind in ("blocked", "robots") and checked == 0 and failed >= 3:
                raise  # the product pages are closed to us: stop wasting requests
            continue
        checked += 1
        if not info or not is_discount(info["price_now"], info["price_was"]):
            continue
        kind, why = guess_type(info["title"], info["price_now"])
        hints = {"type_guess": why, **info["hints"]}
        deals.append(make_deal(
            shop=shop, type=kind, title=info["title"] or link, url=link,
            price_now=info["price_now"], price_was=info["price_was"],
            currency=info["currency"] or shop.get("currency"),
            source=info["source"], found_via=pages[0], ends=info["ends"], hints=hints))
    stats = {"items_read": checked, "sale_pages": len(pages), "links_found": len(links), "failed_pages": failed}
    if listing_errors:
        stats["listing_errors"] = listing_errors[:3]
    if stopped:
        stats["stopped_early"] = "; ".join(stopped)
    return deals, stats


def read(shop):
    return read_with_stats(shop)[0]
