"""Score a scraper run against the hand-checked test set.

python -m scraper.score [--date YYYY-MM-DD] [--testset path]
Writes data/deals/score-<date>.json and prints a short summary.
"""
import argparse
import datetime
import json
import re

from scraper.common import RAW, ROOT, TESTSET, load_shops, norm_url, plain

STOP = {"the", "and", "for", "with", "of", "a", "an", "in", "to", "pdf", "edition"}
# sister domains, one shop (the DriveThruRPG API reader lives on api., its product links on www.)
ALIASES = {"modiphius.us": "modiphius.net", "api.drivethrurpg.com": "drivethrurpg.com"}


def host(url):
    h = norm_url(url).split("/")[0]
    return ALIASES.get(h, h)


def words(title):
    return {w for w in plain(re.sub(r"['\u2019]", "", title or "")).split() if len(w) > 2 and w not in STOP}


def matches(test, deal):
    """Same URL, or same shop host and every significant test-title word in the run title."""
    if norm_url(test["url"]) == norm_url(deal["url"]):
        return True
    if host(test["url"]) != host(deal["url"]):
        return False
    need = words(test["title"])
    return bool(need) and need <= words(deal["title"])


def shop_for(url, shops):
    h = host(url)
    for s in shops:
        sh = host(s["store_url"])
        if h == sh or h.endswith("." + sh):
            return s
    return None


def miss_reason(test, shops, rows):
    shop = shop_for(test["url"], shops)
    if shop is None:
        return "shop not in list"
    row = rows.get(shop["id"])
    if row is None:
        return "shop not run"
    if row["status"] != "ok":
        return f"shop {row['status']}: {(row['errors'] or [''])[0]}"
    return "reader skipped it"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m scraper.score")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--testset", default=None)
    args = ap.parse_args(argv)

    testset_path = args.testset or str(TESTSET / f"{args.date}.json")
    tests = json.load(open(testset_path))
    fakes_path = TESTSET / f"{args.date}-fakes.json"
    fakes = json.load(open(fakes_path)) if fakes_path.exists() else []
    deals = json.load(open(RAW / f"{args.date}-scraper.json"))
    report_path = ROOT / "data" / "deals" / f"scrape-report-{args.date}.json"
    rows = {r["id"]: r for r in json.load(open(report_path))["shops"]} if report_path.exists() else {}
    shops = load_shops()

    per_platform, missed, matched_ids = {}, [], set()
    for t in tests:
        hit = next((d for d in deals if matches(t, d)), None)
        p = per_platform.setdefault(t["platform"], {"found": 0, "missed": 0})
        if hit:
            p["found"] += 1
            matched_ids.add(id(hit))
        else:
            p["missed"] += 1
            missed.append({"id": t["id"], "platform": t["platform"], "title": t["title"], "url": t["url"],
                           "reason": miss_reason(t, shops, rows)})

    # A fake gets through only if the run repeats its false claim: for price fakes the run must
    # show the fake price (the real product at its real price is a correct find); for the
    # other kinds (not an RPG, expired, injected page) any deal at that URL counts.
    by_url = {}
    for d in deals:
        by_url.setdefault(norm_url(d["url"]), []).append(d)
    fakes_present = []
    for f in fakes:
        if f["url"].startswith("fixture:"):
            continue
        hits = by_url.get(norm_url(f["url"]), [])
        if f["fake_kind"] in ("wrong_price", "normal_price"):
            hits = [d for d in hits if d.get("price_now") == f["price_now"]]
        if hits:
            fakes_present.append({"id": f["id"], "fake_kind": f["fake_kind"], "url": f["url"]})
    result = {
        "date": args.date,
        "testset": testset_path,
        "found": sum(p["found"] for p in per_platform.values()),
        "total": len(tests),
        "per_platform": per_platform,
        "missed": missed,
        "fakes_present_in_run": fakes_present,
        "run_deals_total": len(deals),
        "run_deals_not_in_testset": sum(1 for d in deals if id(d) not in matched_ids),
    }
    out = ROOT / "data" / "deals" / f"score-{args.date}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n")

    print(f"found {result['found']}/{result['total']} test-set deals")
    for plat, p in sorted(per_platform.items()):
        print(f"  {plat}: {p['found']} found, {p['missed']} missed")
    for m in missed:
        print(f"  MISSED [{m['platform']}] {m['title']}: {m['reason']}")
    print(f"fakes present in run: {len(fakes_present)}" + "".join(f"\n  {f['id']}" for f in fakes_present))
    print(f"run deals not in test set: {result['run_deals_not_in_testset']} of {len(deals)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
