"""Run every active shop's reader and write the raw deals plus a run report.

python -m scraper.run [--date YYYY-MM-DD] [--shop ID ...] [--platform P ...]

Outputs (see agents/scraper-spec.md):
  data/deals/raw/<date>-scraper.json         all deals, deduped by norm_url
  data/deals/scrape-report-<date>.json       per shop: status, items read, deals, errors, seconds
A partial run (--shop / --platform) replaces only those shops' deals and report rows;
everything else already in the files is kept.
"""
import argparse
import concurrent.futures
import datetime
import importlib
import json
import time

from scraper import alarm
from scraper.common import RAW, ROOT, FetchError, load_shops, norm_url, save_shops

REPORTS = ROOT / "data" / "deals"
MAX_WORKERS = 8
# platform -> (module, function names to try, in order)
READERS = {
    "shopify": ("shopify", ("read_with_stats", "read")),
    "woocommerce": ("woocommerce", ("read_with_stats", "read")),
    "itch": ("itch", ("read_with_stats", "read")),
    "bundleofholding": ("bundles", ("read_bundleofholding",)),
    "humble": ("bundles", ("read_humble",)),
    "generic": ("generic", ("read_with_stats", "read")),
    "drivethrurpg": ("drivethrurpg", ("read_with_stats", "read")),
    "bigcommerce": ("bigcommerce", ("read_with_stats", "read")),
}


def load_reader(platform):
    """-> callable(shop) or None when there is no reader module/function yet."""
    spec = READERS.get(platform)
    if not spec:
        return None
    try:
        mod = importlib.import_module(f"scraper.readers.{spec[0]}")
    except ModuleNotFoundError as e:
        if e.name == f"scraper.readers.{spec[0]}":
            return None
        raise
    for fn in spec[1]:
        if hasattr(mod, fn):
            return getattr(mod, fn)
    return None


def run_shop(shop):
    """-> (deals, report row). Never raises."""
    row = {"id": shop["id"], "platform": shop["platform"], "status": "ok", "items_read": None,
           "deals": 0, "errors": [], "seconds": 0}
    start = time.monotonic()
    deals = []
    reader = load_reader(shop["platform"])
    if reader is None:
        row.update(status="error", errors=["no reader"])
    else:
        try:
            result = reader(shop)
            stats = {}
            if isinstance(result, tuple):
                result, stats = result
            deals = list(result)
            row["items_read"] = stats.pop("items_read", None)
            row.update(stats)
        except FetchError as e:
            row.update(status="blocked" if e.kind in ("blocked", "robots") else "error", errors=[str(e)])
        except Exception as e:  # a reader bug on one shop must not stop the run
            row.update(status="error", errors=[f"{type(e).__name__}: {e}"])
    row["deals"] = len(deals)
    row["seconds"] = round(time.monotonic() - start, 1)
    return deals, row


def _read_json(path, default):
    return json.loads(path.read_text()) if path.exists() else default


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m scraper.run")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--shop", action="append", default=[], help="shop id (repeatable)")
    ap.add_argument("--platform", action="append", default=[], help="platform (repeatable)")
    args = ap.parse_args(argv)

    shops = load_shops()
    todo = [s for s in shops if s.get("status") == "active"
            and (not args.shop or s["id"] in args.shop)
            and (not args.platform or s["platform"] in args.platform)]
    if not todo:
        print("no active shops match")
        return 1

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(todo))) as pool:
        futures = {pool.submit(run_shop, s): s for s in todo}
        for fut in concurrent.futures.as_completed(futures):
            shop = futures[fut]
            results[shop["id"]] = fut.result()
            _, row = results[shop["id"]]
            print(f"  {shop['id']}: {row['status']}, {row['deals']} deals, "
                  f"{row['items_read'] if row['items_read'] is not None else '?'} items, {row['seconds']}s"
                  + (f", {row['errors'][0]}" if row["errors"] else ""))

    ran = set(results)
    RAW.mkdir(parents=True, exist_ok=True)
    raw_path = RAW / f"{args.date}-scraper.json"
    report_path = REPORTS / f"scrape-report-{args.date}.json"

    # keep what earlier partial runs wrote for shops not in this run
    kept_deals = [d for d in _read_json(raw_path, []) if d.get("shop_id") not in ran]
    kept_rows = [r for r in _read_json(report_path, {}).get("shops", []) if r["id"] not in ran]

    all_deals, seen = [], set()
    for d in kept_deals + [d for sid in sorted(ran) for d in results[sid][0]]:
        key = norm_url(d["url"])
        if key not in seen:
            seen.add(key)
            all_deals.append(d)
    new_rows = [results[sid][1] for sid in ran]
    flagged = alarm.apply(new_rows, args.date)      # break alarm: deals gone with no error
    rows = sorted(kept_rows + new_rows, key=lambda r: r["id"])
    report = {
        "date": args.date,
        "shops": rows,
        "totals": {
            "shops": len(rows),
            "ok": sum(r["status"] == "ok" for r in rows),
            "blocked": sum(r["status"] == "blocked" for r in rows),
            "error": sum(r["status"] == "error" for r in rows),
            "deals_raw": sum(r["deals"] for r in rows),
            "deals_unique": len(all_deals),
            "break_alarms": sum(1 for r in rows if r.get("break_alarm")),
        },
    }
    raw_path.write_text(json.dumps(all_deals, ensure_ascii=False, indent=1) + "\n")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")

    # shops that returned data: recipe works today. Failed ones: reset. Reload so we
    # never overwrite edits another process made to shops.json during the run.
    fresh = load_shops()
    for s in fresh:
        if s["id"] in ran:
            _, row = results[s["id"]]
            got = row["status"] == "ok" and (row["deals"] or row["items_read"])
            s["recipe_confirmed"] = args.date if got else None
    save_shops(fresh)

    t = report["totals"]
    for sid in flagged:
        r = next(r for r in rows if r["id"] == sid)
        print(f"  BREAK ALARM {sid}: {r['deals']} deals, recent average {r['alarm_average']}")
    print(f"{len(ran)} shops run: {t['ok']} ok, {t['blocked']} blocked, {t['error']} error; "
          f"{len(all_deals)} deals in {raw_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
