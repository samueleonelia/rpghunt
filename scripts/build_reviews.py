"""Verify agent-found reviews and store them for the deals page.

Reads data/reviews/raw/batch-*.json (written by review agents), opens every
review link, keeps only links that load and mention the product, and merges
them into data/reviews/reviews.json (deal id -> reviews). build_deals.py then
attaches them to each deal. Reviews are kept across days: a product reviewed
once does not need new research tomorrow.

Run: python3 scripts/build_reviews.py
"""
import collections
import concurrent.futures
import json
import pathlib
import sys
import time
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_deals import fetch, key_words  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "reviews" / "raw"
OUT = ROOT / "data" / "reviews" / "reviews.json"
KINDS = {"article", "video", "forum"}


def main():
    inputs = {}
    for f in RAW.glob("input-*.json"):
        for item in json.loads(f.read_text()):
            inputs[item["key"]] = item

    jobs = []  # (deal key, review)
    for f in sorted(RAW.glob("batch-*.json")):
        for entry in json.loads(f.read_text()):
            for r in entry.get("reviews") or []:
                if r.get("url") and r.get("kind") in KINDS and r.get("verdict"):
                    jobs.append((entry["key"], r))

    # One request at a time per site, so nobody rate-limits us.
    by_host = collections.defaultdict(list)
    for i, (_, r) in enumerate(jobs):
        by_host[urllib.parse.urlsplit(r["url"]).netloc].append(i)
    results = [None] * len(jobs)

    def crawl(indices):
        for i in indices:
            results[i] = fetch(jobs[i][1]["url"])
            time.sleep(1.5)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(crawl, by_host.values()))

    stored = json.loads(OUT.read_text()) if OUT.exists() else {}
    kept, dropped = collections.Counter(), []
    for (key, r), (status, reason, text, _image, _rating) in zip(jobs, results):
        item = inputs.get(key, {})
        words = key_words({"title": item.get("title"), "game": item.get("game")})
        if status != "ok":
            dropped.append((item.get("title", key), r["url"], reason or status))
            continue
        if words and not any(w in text for w in words):
            dropped.append((item.get("title", key), r["url"], "page does not mention the product"))
            continue
        review = {k: r.get(k) for k in ("source", "url", "kind", "verdict", "score", "date")}
        existing = stored.setdefault(key, [])
        if all(x["url"] != review["url"] for x in existing):
            existing.append(review)
        kept[key] += 1

    OUT.write_text(json.dumps(stored, ensure_ascii=False, indent=1))
    print(f"{len(jobs)} review links found, {sum(kept.values())} kept, {len(dropped)} dropped; "
          f"{len(kept)} of {len(inputs)} deals have at least one review")
    for title, url, why in dropped:
        print(f"  dropped | {title[:40]} | {why} | {url[:80]}")


if __name__ == "__main__":
    main()
