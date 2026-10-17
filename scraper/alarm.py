"""Break alarm (phase 3.4): a shop whose reader quietly stopped finding deals.

Per shop, data/shops/run-history.json keeps the deal counts of the last HISTORY_RUNS runs:
{shop_id: [[date, deals], ...]}. After a run, a shop is flagged when it ran WITHOUT error and
  - its deals fell to 0 from a recent average of at least MIN_AVERAGE, or
  - its deals fell by at least DROP_SHARE against that average.
The average uses the runs BEFORE today, so running the same date twice gives the same answer.
Needs at least MIN_RUNS earlier runs: a new shop never alarms. Runs that errored or were blocked
are not recorded (they have their own status in the run report and would poison the average).
Flagged rows get `break_alarm: <date>`; scraper/escalate.py turns them into recipe jobs.
"""
import json

from scraper.common import ROOT

HISTORY_FILE = ROOT / "data" / "shops" / "run-history.json"
HISTORY_RUNS = 7
MIN_AVERAGE = 3.0
DROP_SHARE = 0.70
MIN_RUNS = 3


def _load(path):
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def is_break(prior_counts, deals):
    """-> (flagged, average). prior_counts: deal counts of earlier runs, oldest first."""
    prior = prior_counts[-HISTORY_RUNS:]
    if len(prior) < MIN_RUNS:
        return False, None
    avg = sum(prior) / len(prior)
    if avg < MIN_AVERAGE:
        return False, round(avg, 2)
    return deals == 0 or deals <= (1 - DROP_SHARE) * avg, round(avg, 2)


def apply(rows, date, path=HISTORY_FILE):
    """Check every row of this run against its history, then record today's counts.
    Sets row['break_alarm'] = date (and row['alarm_average']) on flagged rows. -> list of flagged shop ids."""
    hist = _load(path)
    flagged = []
    for row in rows:
        if row.get("status") != "ok":
            continue
        entries = [e for e in hist.get(row["id"], []) if e[0] != date]
        bad, avg = is_break([e[1] for e in entries], row["deals"])
        if bad:
            row["break_alarm"] = date
            row["alarm_average"] = avg
            flagged.append(row["id"])
        else:
            row.pop("break_alarm", None)
            row.pop("alarm_average", None)
        hist[row["id"]] = (entries + [[date, row["deals"]]])[-HISTORY_RUNS:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hist, indent=1, sort_keys=True) + "\n")
    return flagged
