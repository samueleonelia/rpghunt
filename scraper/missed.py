"""Misses (phase 4): sales people point to that our shop readers did not find.

python -m scraper.missed [--date D] [--no-fetch]

Takes the leads from data/deals/leads-<date>.json that sit on a shop we know, keeps the ones that look
like a product or bundle page, and compares them with today's raw run (data/deals/raw/<date>-scraper.json):
same URL (collections prefix and www ignored), or same shop and the link text's words all in a deal title.
A lead with no match is a miss and gets a reason guess:
  not_a_product_page   the link goes to a home, blog, category or collection page
  shop_blocked         a shop we cannot read automatically (DriveThruRPG...): kept, never fetched
  shop_not_read_today  the shop was not read today (blocked, error, paused or not run)
  reader_gap           the shop was read, the page shows a real discount, the reader missed it
  not_on_sale_anymore  the page shows no discount (prices are never invented)
  page_unreadable      the page could not be opened or has no price
  fetch_cap            more misses than the daily fetch cap
A miss whose page shows a real discount (found by scraper.readers.generic.page_prices, the shop's own
page) becomes a candidate deal: source "lead", appended to the raw file, so the Jev check judges it like
any page-read deal. Output: data/deals/missed-<date>.json
"""
import argparse
import concurrent.futures
import datetime
import json
import re
import urllib.parse

from scraper.common import (RAW, ROOT, FetchError, drivethru_product_id, fetch_json, is_discount, load_shops,
                            make_deal, money, norm_url)
from scraper.readers import generic, shopify
from scraper.score import host as alias_host
from scraper.score import words

DEALS = ROOT / "data" / "deals"
MAX_FETCHES = 60            # lead pages fetched per day
WORKERS = 8

_PRODUCT = re.compile(
    r"/(products?|p|item|items|presents|bundles?|bundle|game|games|books|software|shop/p|store/p|"
    r"tabletop-role-playing-games)/[^/?#]+", re.I)
_NOT_PRODUCT = re.compile(r"/(cart|checkout|account|login|search|blogs?|news|tag|tags|pages?|category|categories|"
                          r"collections?)(/|$)", re.I)
_COLLECTION_PREFIX = re.compile(r"^/collections?/[^/]+(?=/products?/)", re.I)


def looks_like_product(url):
    """A product or bundle page rather than a home, blog, category or collection page."""
    p = urllib.parse.urlsplit(url)
    path = p.path
    if _COLLECTION_PREFIX.sub("", path) != path:
        path = _COLLECTION_PREFIX.sub("", path)
    if _PRODUCT.search(path):
        return True
    host = p.netloc.lower()
    if host.endswith(".itch.io") and host not in ("www.itch.io",):     # a game page: one path segment
        segs = [s for s in path.split("/") if s]
        return len(segs) == 1
    return False


def match_key(url):
    """Comparable form of a product URL: alias host (modiphius.us = modiphius.net), no collections prefix."""
    p = urllib.parse.urlsplit(url)
    host = alias_host(url)
    dtrpg = drivethru_product_id(url)
    if dtrpg is not None:       # DriveThruRPG: the product id is the key, the slug and /en/ may differ
        return f"{host}/product/{dtrpg}"
    path = _COLLECTION_PREFIX.sub("", p.path).rstrip("/")
    return host + path.lower()


def lead_words(lead):
    """Words that should appear in the deal's title: the link text, else the last part of the path."""
    w = words(lead.get("link_text") or "")
    if len(w) >= 2:
        return w
    slug = urllib.parse.urlsplit(lead["url"]).path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
    return words(slug)


def in_raw(lead, raw_by_key, raw_by_host):
    """The raw deal that matches this lead, or None."""
    hit = raw_by_key.get(match_key(lead["url"]))
    if hit:
        return hit
    need = lead_words(lead)
    if len(need) < 2:
        return None
    for d in raw_by_host.get(alias_host(lead["url"]), []):
        if need <= words(d["title"]):
            return d
    return None


def index_raw(raw):
    by_key, by_host = {}, {}
    for d in raw:
        by_key.setdefault(match_key(d["url"]), d)
        by_host.setdefault(alias_host(d["url"]), []).append(d)
    return by_key, by_host


def shop_read_ok(shop, rows):
    row = rows.get(shop["id"])
    return shop.get("status") == "active" and row is not None and row.get("status") == "ok"


_SHOPIFY_HANDLE = re.compile(r"/products/([^/?#]+)", re.I)


def read_lead_page(url, shop):
    """Prices of one lead page, from the shop's own data. -> info dict (as generic.page_prices) or None.
    Shopify product pages carry no list price in their markup, so a Shopify shop is asked for the product's
    own JSON first (same data its products.json feed gives); anything else, and Shopify products whose JSON
    shows no discounted variant, go through generic.page_prices."""
    if shop.get("platform") == "shopify":
        m = _SHOPIFY_HANDLE.search(urllib.parse.urlsplit(url).path)
        if m:
            origin = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url))
            try:
                product = fetch_json(f"{origin}/products/{m.group(1)}.json").get("product") or {}
            except (FetchError, ValueError, AttributeError):
                product = {}
            pick = shopify.best_discount_variant(product)
            if pick:
                variant, now, was = pick
                vt = variant.get("title")
                return {"title": product.get("title"), "price_now": now, "price_was": was,
                        "currency": shop.get("currency"), "ends": None, "source": "shopify-product-json",
                        "hints": {"product_type": product.get("product_type") or None, "tags": product.get("tags") or [],
                                  "vendor": product.get("vendor") or None,
                                  "variant": None if vt in (None, "Default Title") else vt,
                                  "requires_shipping": bool(variant.get("requires_shipping"))}}
    return generic.page_prices(url, shop.get("recipe") or {})


def lead_info(lead):
    return {k: lead.get(k) for k in ("feed", "post_title", "post_url", "published", "link_text")}


def make_candidate(shop, lead, info):
    kind, why = generic.guess_type(info["title"], info["price_now"])
    if info["hints"].get("requires_shipping") and kind == "sale":
        kind, why = "physical", "shop data says it ships"
    if shop["platform"] in ("bundleofholding", "humble"):
        kind, why = "bundle", "bundle shop"
    hints = {"type_guess": why, "lead": lead_info(lead), "read_via": info.get("source"), **info["hints"]}
    return make_deal(
        shop=shop, type=kind, title=info["title"] or lead["url"], url=lead["url"],
        price_now=info["price_now"], price_was=info["price_was"],
        currency=info["currency"] or shop.get("currency"), source="lead",
        found_via=f"lead {lead['feed']}", ends=info["ends"], hints=hints,
        notes="Found through a lead post, not by the shop reader; prices read from the shop's own page.")


def triage(leads, shops, raw, scrape_rows):
    """Split leads into matched / misses with the reasons that need no page fetch.
    -> (misses, matched_count). A miss is a dict; those with reason None still need their page read."""
    by_id = {s["id"]: s for s in shops}
    rows = {r["id"]: r for r in scrape_rows}
    by_key, by_host = index_raw(raw)
    misses, matched = [], 0
    for lead in leads:
        shop = by_id.get(lead.get("shop_id"))
        if shop is None:
            continue                                      # an unknown site: nothing to compare with
        product = looks_like_product(lead["url"])
        if product and in_raw(lead, by_key, by_host):
            matched += 1
            continue
        m = {"url": lead["url"], "title": lead.get("link_text") or None, "shop_id": shop["id"], "shop": shop["name"],
             "class": lead["class"], "lead": lead_info(lead), "reason": None, "detail": None, "candidate": False,
             "_shop_read": shop_read_ok(shop, rows)}
        if shop.get("status") == "blocked" or lead["class"] == "blocked_shop":
            m.update(reason="shop_blocked", detail="the shop cannot be read automatically")
        elif not product:
            m.update(reason="not_a_product_page", detail="the link goes to a home, blog or collection page")
        elif shop.get("platform") == "drivethrurpg":
            # The API lists every product on sale; www.drivethrurpg.com is a bot wall we never fetch.
            m.update(reason="not_on_sale_anymore", detail="not on sale in the DriveThruRPG API today (website not fetched)")
        misses.append(m)
    return misses, matched


def read_pages(misses, shops, page_info, today, max_fetches=MAX_FETCHES):
    """Fetch the page of every miss that still needs it; sets reason / detail / candidate. -> candidates."""
    by_id = {s["id"]: s for s in shops}
    todo = [m for m in misses if m["reason"] is None]
    for m in todo[max_fetches:]:
        m.update(reason="fetch_cap", detail=f"more than {max_fetches} lead pages today")
    todo = todo[:max_fetches]

    def one(m):
        shop = by_id[m["shop_id"]]
        try:
            return m, page_info(m["url"], shop), None
        except FetchError as e:
            return m, None, e
        except Exception as e:                            # a parser bug on one page must not stop the day
            return m, None, e

    candidates = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for m, info, err in pool.map(one, todo):
            shop = by_id[m["shop_id"]]
            if err is not None:
                m.update(reason="page_unreadable", detail=str(err)[:200])
            elif info is None:
                m.update(reason="page_unreadable", detail="no readable price on the page")
            elif not is_discount(info["price_now"], info["price_was"]):
                m.update(reason="not_on_sale_anymore", title=info.get("title") or m["title"],
                         detail=f"page shows {info['price_now']}" + (f", was {info['price_was']}" if info["price_was"] else ", no list price"))
                if not m["_shop_read"]:
                    m["detail"] += " (shop not read today)"
            else:
                reason = "reader_gap" if m["_shop_read"] else "shop_not_read_today"
                lead = {"url": m["url"], "link_text": m["title"], **m["lead"]}
                cand = make_candidate(shop, lead, info)
                m.update(reason=reason, title=cand["title"], candidate=True,
                         price_now=cand["price_now"], price_was=cand["price_was"], currency=cand["currency"],
                         detail=f"page shows {cand['price_now']} now, {cand['price_was']} before")
                candidates.append(cand)
    return candidates


def run(date, leads_doc=None, raw=None, shops=None, scrape_rows=None, page_info=read_lead_page,
        fetch_pages=True, write=True, append_to_raw=True, max_fetches=MAX_FETCHES):
    """-> the missed document. Candidates are appended to the raw file unless append_to_raw is False."""
    def load(path, default):
        try:
            return json.loads(path.read_text()) if path.exists() else default
        except ValueError:
            return default

    leads_doc = leads_doc if leads_doc is not None else load(DEALS / f"leads-{date}.json", {"leads": []})
    raw_path = RAW / f"{date}-scraper.json"
    raw = raw if raw is not None else load(raw_path, [])
    raw = [d for d in raw if d.get("source") != "lead"]       # recomputed below; keeps re-runs stable
    shops = shops if shops is not None else load_shops()
    scrape_rows = scrape_rows if scrape_rows is not None else load(DEALS / f"scrape-report-{date}.json", {}).get("shops", [])

    misses, matched = triage(leads_doc["leads"], shops, raw, scrape_rows)
    candidates = []
    if fetch_pages:
        candidates = read_pages(misses, shops, page_info, datetime.date.fromisoformat(date), max_fetches)
    else:
        for m in misses:
            if m["reason"] is None:
                m.update(reason="not_checked", detail="page fetch skipped")
    for m in misses:
        m.pop("_shop_read", None)
    by_reason = {}
    for m in misses:
        by_reason[m["reason"]] = by_reason.get(m["reason"], 0) + 1
    considered = sum(1 for l in leads_doc["leads"] if l.get("shop_id"))
    doc = {"date": date,
           "counts": {"leads_on_known_shops": considered, "matched_in_run": matched, "misses": len(misses),
                      "candidates": len(candidates), "by_reason": by_reason},
           "misses": misses, "candidates": candidates}
    if write:
        DEALS.mkdir(parents=True, exist_ok=True)
        (DEALS / f"missed-{date}.json").write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        if append_to_raw and (candidates or raw_path.exists()):
            seen = {norm_url(d["url"]) for d in raw}
            merged = raw + [c for c in candidates if norm_url(c["url"]) not in seen]
            RAW.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(merged, ensure_ascii=False, indent=1) + "\n")
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m scraper.missed")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--no-fetch", action="store_true", help="sort the misses but read no pages")
    args = ap.parse_args(argv)
    if not (DEALS / f"leads-{args.date}.json").exists():
        print(f"missing data/deals/leads-{args.date}.json; run: python -m scraper.discover --date {args.date}")
        return 1
    doc = run(args.date, fetch_pages=not args.no_fetch)
    c = doc["counts"]
    print(f"{c['leads_on_known_shops']} leads on known shops: {c['matched_in_run']} found in the run, "
          f"{c['misses']} misses ({c['candidates']} became candidate deals)")
    for reason, n in sorted(c["by_reason"].items(), key=lambda kv: -kv[1]):
        print(f"  {reason}: {n}")
    print(f"wrote data/deals/missed-{args.date}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
