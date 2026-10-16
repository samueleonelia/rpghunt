"""Verify today's agent-found deals and write the website's deals file.

Reads data/deals/raw/<date>-*.json, drops deals that ended or whose shop page
is dead or about something else, checks whether the price appears on the page,
links each deal to its game in docs/data/games.json, and writes
docs/data/deals.json plus data/deals/report-<date>.json.

Run: python3 scripts/build_deals.py [YYYY-MM-DD]   (default: today)
"""
import concurrent.futures
import datetime
import json
import pathlib
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_data import BLOCKED, OPENER, UA, slugify  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "deals" / "raw"
GAMES = ROOT / "docs" / "data" / "games.json"
OUT = ROOT / "docs" / "data" / "deals.json"
TYPES = {"sale", "bundle", "physical", "free"}
STOP = {"the", "and", "for", "with", "pdf", "edition", "bundle", "of", "rpg", "roleplaying",
        "game", "core", "rulebook", "book", "set", "box", "boxed", "print", "hardcover"}


def plain(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9.]+", " ", text)


def key_words(deal):
    words = set()
    for src in (deal.get("title"), deal.get("game")):
        for w in plain(src or "").replace(".", " ").split():
            if len(w) > 3 and w not in STOP:
                words.add(w)
    return words


IMG_RE = [
    re.compile(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)(?::src)?["\'][^>]*content=["\']([^"\']+)', re.I),
    re.compile(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\'](?:og:image|twitter:image)', re.I),
]


def share_image(html, page_url):
    """The product image the shop publishes for social sharing (og:image), as https."""
    for rx in IMG_RE:
        m = rx.search(html)
        if m:
            url = urllib.parse.urljoin(page_url, m.group(1).replace("&amp;", "&"))
            return "https://" + url[len("http://"):] if url.startswith("http://") else url
    return None


def fetch(url):
    """Return (status, reason, page_text, image_url). status: ok | blocked | dead."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
    })
    try:
        with OPENER.open(req, timeout=20) as resp:
            body = resp.read(800_000).decode("utf-8", "ignore")
            low = body.lower()
            if "captcha" in low and ("robot" in low or "automated access" in low):
                return "blocked", "robot check page", "", None
            return "ok", "", plain(body + " " + resp.geturl()), share_image(body, resp.geturl())
    except urllib.error.HTTPError as e:
        if e.code in BLOCKED:
            return "blocked", f"HTTP {e.code} (bot protection)", "", None
        return "dead", f"HTTP {e.code}", "", None
    except Exception as e:  # DNS failure, timeout, SSL error
        return "dead", type(e).__name__, "", None


def price_on_page(price, text):
    if price is None:
        return None
    if price == 0:
        return any(w in text for w in ("free", " 0.00", "$0 "))
    return f"{price:.2f}" in text or (float(price).is_integer() and f" {int(price)} " in text)


def main():
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    today = datetime.date.fromisoformat(day)

    # Two agents can report the same deal, sometimes on sister domains
    # (modiphius.net vs modiphius.us): dedupe on URL, page path + price, or
    # shop brand + first title words + price.
    deals, seen = [], set()
    for f in sorted(RAW.glob(f"{day}-*.json")):
        for d in json.loads(f.read_text()):
            if not d.get("url") or d.get("type") not in TYPES:
                continue
            path = urllib.parse.urlsplit(d["url"]).path.rstrip("/")
            brand = plain(d.get("shop") or "").split()[:1]
            title = [w for w in plain(d["title"]).split() if w not in STOP][:6]
            keys = {("url", d["url"]), ("title", tuple(brand), tuple(title), d.get("price_now"))}
            if len(path) > 10:
                keys.add(("path", path, d.get("price_now")))
            if not keys & seen:
                seen |= keys
                deals.append(d)

    report = {"kept": 0, "expired": [], "dead": [], "wrong_page": [], "blocked_dropped": [], "price_not_seen": []}

    # One request at a time per site, with a pause, so shops like itch.io do not
    # rate-limit us (HTTP 429); different sites still run in parallel.
    def polite(url, tries=3):
        for attempt in range(tries):
            result = fetch(url)
            if not result[1].startswith("HTTP 429"):
                return result
            time.sleep(15 * (attempt + 1))
        return result

    by_host = {}
    for i, d in enumerate(deals):
        by_host.setdefault(urllib.parse.urlsplit(d["url"]).netloc, []).append(i)

    def crawl(indices):
        out = []
        for i in indices:
            out.append((i, polite(deals[i]["url"])))
            time.sleep(1.5)
        return out

    fetched = [None] * len(deals)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for chunk in pool.map(crawl, by_host.values()):
            for i, result in chunk:
                fetched[i] = result

    catalog = {slugify(g["name"]): g["id"] for g in json.loads(GAMES.read_text())}
    out = []
    for d, (status, reason, text, image) in zip(deals, fetched):
        entry = {"title": d["title"], "shop": d.get("shop"), "url": d["url"], "reason": reason}
        ends = d.get("ends")
        if ends and datetime.date.fromisoformat(ends) < today:
            report["expired"].append(entry)
            continue
        if d.get("confidence") not in ("high", "medium"):
            report["blocked_dropped"].append({**entry, "reason": "low confidence"})
            continue
        if status == "dead":
            report["dead"].append(entry)
            continue
        if status == "ok":
            words = key_words(d)
            if words and not any(w in text for w in words):
                report["wrong_page"].append({**entry, "reason": "page does not mention the product"})
                continue
            seen_price = price_on_page(d.get("price_now"), text)
            if seen_price is False:
                # Page loads but does not show the price we claim: do not publish it.
                report["price_not_seen"].append(entry)
                continue
            d["verified"] = "page"
            d["price_seen"] = seen_price
        else:
            # Shop blocks robots: keep only if the agent saw it on the shop page or
            # a recent source confirms it AND we know when it ends.
            if not ends:
                report["blocked_dropped"].append({**entry, "reason": reason + ", no end date"})
                continue
            d["verified"] = "source"
            d["price_seen"] = None

        if d.get("price_now") is not None and d.get("price_was") and not d.get("discount_pct"):
            d["discount_pct"] = round(100 * (1 - d["price_now"] / d["price_was"]))
        d["image"] = image
        # The shop is shown once on the card; do not repeat it in the title.
        shop = (d.get("shop") or "").split(" (")[0]
        if shop and d["title"].lower().startswith(shop.lower() + ":"):
            d["title"] = d["title"][len(shop) + 1:].strip()
        d["game_id"] = catalog.get(slugify(d["game"])) if d.get("game") else None
        d["id"] = slugify(f"{d.get('shop', '')} {d['title']}")[:80]
        d.pop("found_via", None)
        out.append(d)

    # Best deals first: free, then biggest discount; deals with no known discount last.
    out.sort(key=lambda d: (d["type"] != "free", -(d.get("discount_pct") or 0)))
    OUT.write_text(json.dumps({"date": day, "deals": out}, ensure_ascii=False, indent=1))
    report["kept"] = len(out)
    (RAW.parent / f"report-{day}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))

    print(f"{len(deals)} deals found, {len(out)} kept: "
          f"{len(report['expired'])} expired, {len(report['dead'])} dead, "
          f"{len(report['wrong_page'])} wrong page, {len(report['blocked_dropped'])} unconfirmable, "
          f"{len(report['price_not_seen'])} price not seen on page")
    by_type = {}
    for d in out:
        by_type[d["type"]] = by_type.get(d["type"], 0) + 1
    print("by type:", by_type, "| linked to catalog:", sum(1 for d in out if d["game_id"]),
          "| with image:", sum(1 for d in out if d["image"]))


if __name__ == "__main__":
    main()
