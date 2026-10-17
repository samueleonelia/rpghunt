"""Publish (phase 4): turn the checked deals into the website's deals file.

python -m scraper.publish [--date D] [--out PATH] [--fake] [--no-images]

Input   data/deals/raw/<date>-checked.json    deals that passed the Jev check, plus the ones the browsing
                                              agent accepted (scraper.escalate appends them to the same file)
Output  --out, default data/deals/site-preview-<date>.json   same shape as docs/data/deals.json:
        {"date": ..., "deals": [...]}, every deal with exactly the old keys, best first (free first, then
        biggest discount), image from og:image, star rating from schema.org, link to docs/data/games.json,
        reviews by deal id.
Writing to docs/data/deals.json only happens with an explicit `--out docs/data/deals.json`. Anything built
with the fake Jev or the fake agent (--fake, or deals marked fake_jev / fake_agent) can only be written to a
file whose name ends in -FAKE.json.
Image and rating come from each deal's own page (one polite request through scraper.common.fetch(); answers
are cached in data/deals/page-meta-cache.json for 14 days). The helper functions of scripts/build_deals.py
are imported, not copied.
"""
import argparse
import concurrent.futures
import datetime
import json
import pathlib
import re
import sys
import time
import urllib.parse

from scraper.common import RAW, ROOT, FetchError, fetch, norm_url

sys.path.insert(0, str(ROOT / "scripts"))
import build_deals as old                    # noqa: E402  (image, rating, robot-check and name helpers)
from build_data import slugify               # noqa: E402

DEALS = ROOT / "data" / "deals"
META_CACHE = DEALS / "page-meta-cache.json"
CACHE_DAYS = 14                 # a page with an image is trusted this long
CACHE_DAYS_EMPTY = 2            # a page without one is tried again sooner
IMAGE_BUDGET_SECONDS = 900      # stop opening pages after this long; the rest get their picture on the next run
LAST_STATS = {}                 # numbers of the last main() run (scraper.daily reads them for its report)
SITE_KEYS = ("type", "title", "game", "shop", "url", "price_now", "price_was", "currency", "discount_pct",
             "format", "ends", "summary", "confidence", "notes", "verified", "price_seen", "image", "rating",
             "game_id", "id", "reviews")
WORKERS = 8


class PublishError(Exception):
    pass


# ---------------------------------------------------------------- catalog link

def guess_game(title, games):
    """The catalog game named in a title, or None. Whole words only, the longest name wins; names of four
    letters or fewer (Fate, Kult) must start the title. A wrong link is worse than none."""
    t = slugify(title or "").split("-")
    best = None
    for g in games:
        names = {slugify(g["name"])}
        if names and next(iter(names)).startswith("the-"):
            names.add(next(iter(names))[4:])
        for n in names:
            toks = n.split("-")
            if len(n) < 4:
                continue
            for i in range(len(t) - len(toks) + 1):
                if t[i:i + len(toks)] == toks and (len(n) > 4 or i == 0):
                    if best is None or (len(n), -i) > best[0]:
                        best = ((len(n), -i), g)
                    break
    return best[1] if best else None


# ---------------------------------------------------------------- page image and rating

def _load_cache(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def page_meta(url, load=None):
    """-> {"image", "rating", "error"} from the deal's own page."""
    if url.startswith("fixture:"):
        return {"image": None, "rating": None, "error": "fixture"}
    try:
        resp = (load or fetch)(url)
    except FetchError as e:
        return {"image": None, "rating": None, "error": e.kind}
    except Exception as e:
        return {"image": None, "rating": None, "error": type(e).__name__}
    body = resp.body.decode(getattr(resp, "encoding", None) or "utf-8", "ignore")
    if old.is_robot_check(body):
        return {"image": None, "rating": None, "error": "robot check"}
    return {"image": old.share_image(body, url), "rating": old.shop_rating(body), "error": None}


def metas_for(urls, date, cache_path=META_CACHE, load=None, workers=WORKERS, budget=None, clock=time.monotonic):
    """-> ({url: meta}, stats). One request per uncached URL, parallel across shops. URLs come in priority
    order; once `budget` seconds are used the rest are skipped (not cached, so the next run does them)."""
    cache = _load_cache(cache_path) if cache_path else {}
    today = datetime.date.fromisoformat(date)
    out, todo, stats = {}, [], {"cached": 0, "fetched": 0, "failed": 0, "skipped_for_time": 0}
    for u in urls:
        c = cache.get(norm_url(u))
        if c:
            age = (today - datetime.date.fromisoformat(c["date"])).days
            if 0 <= age < (CACHE_DAYS if c.get("image") else CACHE_DAYS_EMPTY):
                out[u] = c
                stats["cached"] += 1
                continue
        todo.append(u)
    start = clock()

    def one(u):
        if budget is not None and clock() - start > budget:
            return {"image": None, "rating": None, "error": "time budget"}
        return page_meta(u, load)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        for u, m in zip(todo, pool.map(one, todo)):
            out[u] = m
            if m["error"] == "time budget":
                stats["skipped_for_time"] += 1
                continue
            stats["fetched"] += 1
            stats["failed"] += 1 if m["error"] else 0
            if not m["error"]:
                cache[norm_url(u)] = {"date": date, "image": m["image"], "rating": m["rating"]}
    if cache_path and todo:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1) + "\n")
    return out, stats


# ---------------------------------------------------------------- one deal

def dedupe(deals):
    """Same product listed twice (sister domains such as modiphius.net / modiphius.us): keep the first.
    Same rule as scripts/build_deals.py: same URL, same page path and price, or same shop brand, title start and price."""
    out, seen = [], set()
    for d in deals:
        path = urllib.parse.urlsplit(d["url"]).path.rstrip("/")
        brand = old.plain(d.get("shop") or "").split()[:1]
        title = [w for w in old.plain(d["title"]).split() if w not in old.STOP][:6]
        keys = {("url", d["url"]), ("title", tuple(brand), tuple(title), d.get("price_now"))}
        if len(path) > 10:
            keys.add(("path", path, d.get("price_now")))
        if not keys & seen:
            seen |= keys
            out.append(d)
    return out


def site_deal(d, games, catalog, reviews, meta):
    """One checked scraper deal -> one entry in the site's deals file (exactly SITE_KEYS)."""
    chk = d.get("check") or {}
    title, shop = d["title"].strip(), (d.get("shop") or "")
    short = shop.split(" (")[0]
    if short and title.lower().startswith(short.lower() + ":"):
        title = title[len(short) + 1:].strip()          # the shop is shown once on the card
    pct = d.get("discount_pct")
    if not pct and d.get("price_now") is not None and d.get("price_was"):
        pct = round(100 * (1 - d["price_now"] / d["price_was"]))
    game = d.get("game")
    if not game:
        g = guess_game(title, games)
        game = g["name"] if g else None
    page_seen = bool(chk.get("price_now_in_text") or chk.get("via") == "agent")
    out = {
        "type": d["type"], "title": title, "game": game, "shop": shop, "url": d["url"],
        "price_now": d["price_now"], "price_was": d.get("price_was"), "currency": d.get("currency"),
        "discount_pct": pct, "format": d.get("format"), "ends": d.get("ends"), "summary": d.get("summary"),
        "confidence": d.get("confidence", "high"), "notes": d.get("notes"),
        "verified": "page" if page_seen else "source", "price_seen": True if page_seen else None,
        "image": meta.get("image") or (d.get("hints") or {}).get("image"), "rating": meta.get("rating"),
        "game_id": catalog.get(slugify(game)) if game else None,
        "id": slugify(f"{shop} {title}")[:80],
    }
    out["reviews"] = reviews.get(out["id"], [])
    return {k: out[k] for k in SITE_KEYS}


def build(date, checked, games, reviews, metas):
    """-> the site document {"date", "deals"} from checked deals. metas: {url: meta}."""
    catalog = {slugify(g["name"]): g["id"] for g in games}
    out, ids = [], set()
    for d in checked:
        entry = site_deal(d, games, catalog, reviews, metas.get(d["url"], {}))
        if entry["id"] in ids:
            continue
        ids.add(entry["id"])
        out.append(entry)
    out.sort(key=lambda d: (d["type"] != "free", -(d.get("discount_pct") or 0)))
    return {"date": date, "deals": out}


# ---------------------------------------------------------------- guard rails

def is_fake_input(deals):
    return any((d.get("check") or {}).get("fake_jev") or (d.get("check") or {}).get("fake_agent") for d in deals)


def resolve_out(out, date, fake):
    if out is None:
        return DEALS / f"site-preview-{date}{'-FAKE' if fake else ''}.json"
    p = pathlib.Path(out)
    return p if p.is_absolute() else pathlib.Path.cwd() / p


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m scraper.publish")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--out", default=None, help="default data/deals/site-preview-<date>.json; the live site file needs an explicit path")
    ap.add_argument("--fake", action="store_true", help="read the -FAKE checked file; output must end in -FAKE.json")
    ap.add_argument("--no-images", action="store_true", help="do not open the deals' pages (no image, no rating)")
    ap.add_argument("--image-budget", type=int, default=IMAGE_BUDGET_SECONDS,
                    help="seconds to spend opening pages for pictures (default 900); the rest wait for the next run")
    args = ap.parse_args(argv)

    src = RAW / f"{args.date}-checked{'-FAKE' if args.fake else ''}.json"
    if not src.exists():
        print(f"missing {src.relative_to(ROOT)}; run: python -m scraper.check --date {args.date}{' --fake' if args.fake else ''}")
        return 1
    checked = json.loads(src.read_text())
    fake = args.fake or is_fake_input(checked)
    out_path = resolve_out(args.out, args.date, fake)
    if fake and not out_path.name.endswith("-FAKE.json"):
        print(f"refused: these deals come from the fake Jev or fake agent, so the output must end in -FAKE.json (got {out_path.name})")
        return 2

    games = json.loads(old.GAMES.read_text())
    reviews = json.loads(old.REVIEWS.read_text()) if old.REVIEWS.exists() else {}
    deals = dedupe(checked)
    deals.sort(key=lambda d: (d["type"] != "free", -(d.get("discount_pct") or 0)))     # best deals get their picture first
    stats = {"cached": 0, "fetched": 0, "failed": 0, "skipped_for_time": 0}
    metas = {}
    if not args.no_images:
        # Deals whose shop data already carries a picture skip the page visit (they lose only the
        # star rating, which shop pages rarely have outside itch.io).
        need = [d["url"] for d in deals if not (d.get("hints") or {}).get("image")]
        metas, stats = metas_for(need, args.date, budget=args.image_budget)
    doc = build(args.date, deals, games, reviews, metas)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1))

    by_type = {}
    for d in doc["deals"]:
        by_type[d["type"]] = by_type.get(d["type"], 0) + 1
    n = doc["deals"]
    print(f"{len(checked)} checked deals, {len(deals)} after duplicates, {len(n)} published to "
          f"{out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path}")
    print("by type:", by_type, "| linked to catalog:", sum(1 for d in n if d["game_id"]),
          "| with image:", sum(1 for d in n if d["image"]), "| with rating:", sum(1 for d in n if d["rating"]),
          "| with reviews:", sum(1 for d in n if d["reviews"]))
    print(f"pages: {stats['fetched']} opened ({stats['failed']} failed), {stats['cached']} from cache"
          + (f", {stats['skipped_for_time']} left for the next run (time budget)" if stats["skipped_for_time"] else ""))
    LAST_STATS.clear()
    LAST_STATS.update(stats, published=len(n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
