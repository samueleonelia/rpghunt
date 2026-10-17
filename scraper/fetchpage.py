"""Open one page for the browsing agent and print what a shopper sees, as JSON.

python -m scraper.fetchpage <url> [--css "<selector>"]

This is the ONLY way the browsing agent opens pages (agents/browsing-agent-brief.md). It goes
through scraper.common.fetch(): robots.txt, one request at a time per site, 1.5 s apart, no
anti-bot tricks. The text is the trimmed visible text (scraper.trim): hidden elements are gone.

Output keys
  url, status, title, text, price_candidates   what the page says
  price_elements   visible short elements holding a price: text, css (tag.class), path (3 levels
                   up), struck (looks like a normal price crossed out). For writing recipes.
  links            up to 150 links to the same site: text, href, css, path
  css_matches      only with --css: the first 20 visible elements the selector matches
  error, detail    instead of all of the above when the page could not be read (exit code 1)
"""
import argparse
import json
import logging
import re
import sys
import urllib.parse

import lxml.html
from scrapling.parser import Selector

from scraper.common import FetchError, fetch
from scraper.readers.generic import _text, visible
from scraper.trim import is_hidden, money_strings, trim

MAX_LINKS = 150
MAX_PRICE_ELEMENTS = 25
MAX_CSS_MATCHES = 20
_SKIP_LINK = re.compile(r"/(cart|checkout|account|login|log-in|signin|sign-in|register|wishlist)(\.php|\.aspx)?(/|$|\?)", re.I)
_STRUCK_TAGS = {"s", "del", "strike"}
_STRUCK_CLASS = re.compile(r"strike|was|old|compare|regular|original|list|rrp|non-sale|msrp", re.I)
_SKIP_TAGS = {"script", "style", "noscript", "template", "head", "svg"}


def _site(url):
    return urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.")


def _classes(el, limit=3):
    cls = [c for c in (el.attrib.get("class") or "").split() if re.fullmatch(r"[A-Za-z_][\w-]*", c)][:limit]
    return "".join("." + c for c in cls)


def _label(el):
    ident = el.attrib.get("id")
    ident = f"#{ident}" if ident and re.fullmatch(r"[A-Za-z_][\w-]*", ident) else ""
    return f"{el.tag}{ident}{_classes(el)}"


def _path(el, depth=3):
    """'div.product-card > span.price > s.was' (outermost first), at most `depth` levels."""
    chain, node = [], el
    while node is not None and len(chain) < depth and isinstance(node.tag, str) and node.tag not in ("html", "body"):
        chain.append(_label(node))
        node = node.getparent()
    return " > ".join(reversed(chain))


def _hidden_chain(el):
    node = el
    while node is not None:
        if isinstance(node.tag, str) and (node.tag in _SKIP_TAGS or is_hidden(node)):
            return True
        node = node.getparent()
    return False


def _squash(text, n=80):
    return re.sub(r"\s+", " ", text or "").strip()[:n]


def price_elements(doc):
    """Innermost visible elements whose own text holds a price and is short."""
    out, seen = [], set()
    for el in doc.iter():
        if not isinstance(el.tag, str) or el.tag in _SKIP_TAGS:
            continue
        text = _squash(el.text_content(), 60)
        if not money_strings(text) or len(el.text_content().strip()) > 60:
            continue
        if any(isinstance(c.tag, str) and money_strings(c.text_content()) for c in el):
            continue                                     # a child is the innermost holder
        if _hidden_chain(el):
            continue
        chain_struck = False
        node = el
        for _ in range(2):
            if node is None:
                break
            if node.tag in _STRUCK_TAGS or _STRUCK_CLASS.search(node.attrib.get("class") or ""):
                chain_struck = True
            node = node.getparent()
        key = (text, _path(el))
        if key in seen:
            continue
        seen.add(key)
        out.append({"text": text, "css": _label(el), "path": _path(el), "struck": chain_struck})
        if len(out) == MAX_PRICE_ELEMENTS:
            break
    return out


def page_links(doc, base_url):
    out, seen = [], set()
    for a in doc.iter("a"):
        href = (a.attrib.get("href") or "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")) or _hidden_chain(a):
            continue
        full = urllib.parse.urljoin(base_url, href).split("#")[0]
        if urllib.parse.urlsplit(full).scheme not in ("http", "https") or _site(full) != _site(base_url):
            continue
        parts = urllib.parse.urlsplit(full)
        if _SKIP_LINK.search(parts.path + ("?" + parts.query if parts.query else "/")):
            continue
        if full in seen:
            continue
        seen.add(full)
        out.append({"text": _squash(a.text_content()), "href": full, "css": _label(a), "path": _path(a)})
        if len(out) == MAX_LINKS:
            break
    return out


def css_matches(html, selector):
    sel = Selector(html)
    out = []
    for el in visible(sel, selector)[:MAX_CSS_MATCHES]:
        row = {"text": _text(el)[:120]}
        href = el.attrib.get("href") or (el.css("a")[0].attrib.get("href") if el.css("a") else None)
        if href:
            row["href"] = href
        out.append(row)
    return out


def describe(html, url, status=200, selector=None):
    """Page HTML -> the JSON-able dict printed by main(). Pure: no network."""
    t = trim(html, url)
    try:
        doc = lxml.html.fromstring(html or "<html></html>")
    except (ValueError, lxml.etree.ParserError):
        doc = lxml.html.fromstring("<html></html>")
    out = {"url": url, "status": status, "title": t["title"], "text": t["text"],
           "price_candidates": t["price_candidates"], "price_elements": price_elements(doc),
           "links": page_links(doc, url)}
    if selector:
        try:
            out["css_matches"] = css_matches(html, selector)
        except Exception as e:  # a bad selector is an answer, not a crash
            out["css_matches"] = []
            out["css_error"] = f"{type(e).__name__}: {e}"[:200]
    return out


def main(argv=None):
    logging.getLogger("scrapling").setLevel(logging.ERROR)
    ap = argparse.ArgumentParser(prog="python -m scraper.fetchpage")
    ap.add_argument("url")
    ap.add_argument("--css", help="also list what this CSS selector matches on the page")
    args = ap.parse_args(argv)
    if not re.match(r"https?://", args.url):
        print(json.dumps({"url": args.url, "error": "bad_url", "detail": "only http(s) URLs"}))
        return 1
    try:
        resp = fetch(args.url)
    except FetchError as e:
        print(json.dumps({"url": args.url, "error": e.kind, "detail": e.detail}, ensure_ascii=False))
        return 1
    html = resp.body.decode(resp.encoding or "utf-8", "ignore")
    print(json.dumps(describe(html, str(getattr(resp, "url", None) or args.url), resp.status, args.css),
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
