"""Page trimmer for the Jev check (see agents/jev-check-spec.md).

trim(html, url) -> {"title", "text", "price_candidates"}

Jev only sees what a shopper sees: hidden elements are dropped first (so text hidden in a
page cannot talk to the checker), then the product area is kept, at most MAX_WORDS words.
Money amounts are found by code (price_candidates); Jev only picks among them.
"""
import html as html_lib
import json
import re

import lxml.html

MAX_WORDS = 1500
MAX_CANDIDATES = 12
# short pages: climb one more level so the description start is included
MIN_AREA_WORDS = 120

_DROP_TAGS = {"script", "style", "noscript", "template", "svg", "iframe", "object", "embed",
              "head", "meta", "link", "select", "option", "button", "input", "textarea"}
_SKIP_AREAS = {"nav", "footer", "aside"}
_HIDDEN_STYLE = re.compile(
    r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?![.\d])|font-size\s*:\s*0(?![.\d%a-z])|"
    r"(?:text-indent|left|top)\s*:\s*-\d{3,}", re.I)
_NOISE_CLASS = re.compile(r"related|recommend|upsell|cross-?sell|you-?may-?also|recently-?viewed|"
                          r"also-?bought|carousel|newsletter|cookie|modal|popup", re.I)
_BLOCK = {"p", "div", "li", "ul", "ol", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section",
          "article", "tr", "table", "dl", "dt", "dd", "header", "main", "form"}

# ---------------------------------------------------------------- money

_SYMBOL = r"(?:US\$|CA\$|CAD\$|AU\$|AUD\$|NZ\$|C\$|A\$|R\$|\$|£|€|¥|USD|EUR|GBP|CAD|AUD|NZD)"
_AMOUNT = (r"(?:\d{1,3}(?:[.,  ]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
           r"(?![\d])")
_MONEY = re.compile(rf"(?:{_SYMBOL}\s?{_AMOUNT}|{_AMOUNT}\s?{_SYMBOL})", re.I)


def normalize_money(s):
    """'$1,099.00' -> 1099.0, '12,95 €' -> 12.95, 'US$17.95' -> 17.95, '1.099,00 €' -> 1099.0.
    None when there is no number in the string."""
    m = re.search(r"\d[\d.,   ]*", s or "")
    if not m:
        return None
    t = re.sub(r"[\s  ]", "", m.group(0)).rstrip(".,")
    if not t:
        return None
    if "," in t and "." in t:
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        thou = "." if dec == "," else ","
        t = t.replace(thou, "").replace(dec, ".")
    elif "," in t or "." in t:
        sep = "," if "," in t else "."
        parts = t.split(sep)
        if len(parts) > 2:                                  # 1,234,567 -> thousands
            t = "".join(parts)
        elif len(parts[1]) == 3 and parts[0] not in ("0", ""):  # 1,099 -> thousands
            t = "".join(parts)
        else:                                               # 12,95 / 12.95 -> decimal
            t = parts[0] + "." + parts[1]
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def money_strings(text):
    """Every money string in the text, in page order, exact spelling, repeats kept."""
    return [m.group(0).strip() for m in _MONEY.finditer(text or "")]


def prices_in(text):
    """All amounts (floats) shown in the text, order kept, no cap."""
    out = []
    for s in money_strings(text):
        v = normalize_money(s)
        if v is not None:
            out.append(v)
    return out


def candidates(text):
    """Distinct money strings in page order, at most MAX_CANDIDATES."""
    seen, out = set(), []
    for s in money_strings(text):
        if s not in seen:
            seen.add(s)
            out.append(s)
            if len(out) == MAX_CANDIDATES:
                break
    return out


# ---------------------------------------------------------------- hiding

def is_hidden(el):
    a = el.attrib
    if "hidden" in a or (a.get("aria-hidden") or "").strip().lower() == "true":
        return True
    if (a.get("type") or "").lower() == "hidden":
        return True
    return bool(_HIDDEN_STYLE.search(a.get("style") or ""))


def _prune(root, keep=None):
    """Remove hidden elements, scripts, styles, comments and page chrome in place.
    keep=None: only hidden things and chrome go. keep=set: also related-product / popup blocks,
    except the product's own ancestors (listed in keep)."""

    def walk(el):
        for child in list(el):
            tag = child.tag
            if not isinstance(tag, str) or tag in _DROP_TAGS or tag in _SKIP_AREAS or is_hidden(child):
                _remove(child)
            elif keep is not None and child not in keep and _NOISE_CLASS.search(
                    (child.attrib.get("class") or "") + " " + (child.attrib.get("id") or "")):
                _remove(child)
            else:
                walk(child)
    walk(root)


def _remove(el):
    """Drop el but keep its tail text (text after the element belongs to the parent)."""
    parent = el.getparent()
    if parent is None:
        return
    tail = el.tail
    if tail:
        prev = el.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(el)


# ---------------------------------------------------------------- text

def _lines(el):
    """Visible text of el, one block per line."""
    out = []

    def walk(n):
        if isinstance(n.tag, str):
            block = n.tag in _BLOCK
            if block:
                out.append("\n")
            out.append(n.text or "")
            for c in n:
                walk(c)
                out.append(c.tail or "")
            if block:
                out.append("\n")
    walk(el)
    text = "".join(out)
    lines = (re.sub(r"[ \t\r\f\v  ]+", " ", l).strip() for l in text.split("\n"))
    return [l for l in lines if l]


def _words(lines):
    return sum(len(l.split()) for l in lines)


def _cap(lines, limit=MAX_WORDS):
    out, n = [], 0
    for l in lines:
        w = l.split()
        if n + len(w) > limit:
            out.append(" ".join(w[:limit - n]))
            break
        out.append(l)
        n += len(w)
    return out


# ---------------------------------------------------------------- product area

def _jsonld_name(doc):
    for s in doc.iter("script"):
        if (s.attrib.get("type") or "").lower() != "application/ld+json":
            continue
        try:
            data = json.loads(s.text or "")
        except ValueError:
            continue
        stack = [data]
        while stack:
            n = stack.pop()
            if isinstance(n, list):
                stack.extend(n)
            elif isinstance(n, dict):
                t = n.get("@type")
                if "Product" in (t if isinstance(t, list) else [t]) and n.get("name"):
                    return str(n["name"]).strip()
                stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
    return None


def _norm(s):
    return re.sub(r"\W+", " ", html_lib.unescape(s or "")).strip().lower()


def _anchor(root, name):
    """The element that names the product: <h1> matching the JSON-LD name, else the first <h1>,
    else the first element whose own text equals the name."""
    h1s = list(root.iter("h1"))
    if name:
        for h in h1s:
            if _norm(h.text_content()) == _norm(name):
                return h
    if h1s:
        return h1s[0]
    if name:
        for el in root.iter():
            if isinstance(el.tag, str) and _norm(el.text_content()) == _norm(name):
                return el
    return None


def _product_area(body, name):
    """Smallest block around the product name that also holds a price, widened until it has
    MIN_AREA_WORDS words. Falls back to <main> or the whole body."""
    anchor = _anchor(body, name)
    if anchor is not None:
        node = anchor
        while node is not None and node is not body:
            lines = _lines(node)
            if money_strings(" ".join(lines)) and _words(lines) >= MIN_AREA_WORDS:
                return node
            if node.getparent() is None:
                break
            node = node.getparent()
            if _words(_lines(node)) > MAX_WORDS * 2:
                break
        # no ancestor met both tests: take the smallest ancestor that has a price
        node = anchor
        while node is not None and node is not body:
            if money_strings(" ".join(_lines(node))):
                return node
            node = node.getparent()
    mains = list(body.iter("main")) or [e for e in body.iter() if isinstance(e.tag, str)
                                          and e.attrib.get("role") == "main"]
    return mains[0] if mains else body


def trim(html, url=""):
    """Product page HTML -> {"title", "text", "price_candidates"} (see module docstring)."""
    try:
        doc = lxml.html.fromstring(html or "<html></html>")
    except (ValueError, lxml.etree.ParserError):
        return {"title": None, "text": "", "price_candidates": []}
    name = _jsonld_name(doc)
    title_el = doc.find(".//title")
    page_title = re.sub(r"\s+", " ", title_el.text_content()).strip() if title_el is not None else None
    body = doc.find(".//body")
    body = body if body is not None else doc
    _prune(body)                     # pass 1: hidden, scripts, page chrome
    anchor = _anchor(body, name)
    ancestors = set()
    node = anchor
    while node is not None:
        ancestors.add(node)
        node = node.getparent()
    _prune(body, keep=ancestors)     # pass 2: related-product / popup blocks (never the product's own ancestors)
    area = _product_area(body, name)
    lines = _cap(_lines(area))
    text = "\n".join(lines)
    h1 = next(iter(body.iter("h1")), None)
    title = name or (re.sub(r"\s+", " ", h1.text_content()).strip() if h1 is not None else None) or page_title
    return {"title": title, "text": text, "price_candidates": candidates(text)}
