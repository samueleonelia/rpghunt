"""Price history, kept by us (see agents/jev-check-spec.md, "Price history").

data/prices/<shop_id>.json: {url: [[date, price_now, price_was], ...]}, last WINDOW_DAYS days.
record(deals, date) adds today's prices (re-running the same date replaces that date's rows,
so it is idempotent). facts(deal, today) tells the checker what we saw BEFORE today:
  days_seen     how many earlier days this URL was recorded
  lowest_before lowest price_now on those days (None when never seen)
  usual_price   the most common price_now on those days; on a tie the lowest (None when never seen)
Only days before `today` count, so recording today first or last gives the same facts.
"""
import collections
import datetime
import json
import os
import pathlib

from scraper.common import ROOT

PRICES = ROOT / "data" / "prices"
WINDOW_DAYS = 120


class History:
    def __init__(self, directory=PRICES, window_days=WINDOW_DAYS):
        self.dir = pathlib.Path(directory)
        self.window = window_days
        self._cache = {}

    def _path(self, shop_id):
        return self.dir / f"{shop_id}.json"

    def _load(self, shop_id):
        if shop_id not in self._cache:
            p = self._path(shop_id)
            try:
                self._cache[shop_id] = json.loads(p.read_text()) if p.exists() else {}
            except ValueError:
                self._cache[shop_id] = {}   # unreadable file: start again rather than stop the run
        return self._cache[shop_id]

    def record(self, deals, date):
        """Add one row per deal for `date` (YYYY-MM-DD), drop rows older than the window."""
        day = datetime.date.fromisoformat(date)
        oldest = (day - datetime.timedelta(days=self.window)).isoformat()
        by_shop = collections.defaultdict(list)
        for d in deals:
            by_shop[d["shop_id"]].append(d)
        self.dir.mkdir(parents=True, exist_ok=True)
        for shop_id, items in by_shop.items():
            data = self._load(shop_id)
            for d in items:
                rows = [r for r in data.get(d["url"], []) if r[0] != date and r[0] >= oldest]
                rows.append([date, d.get("price_now"), d.get("price_was")])
                rows.sort(key=lambda r: r[0])
                data[d["url"]] = rows
            for url in list(data):          # URLs not seen for the whole window disappear
                kept = [r for r in data[url] if r[0] >= oldest]
                if kept:
                    data[url] = kept
                else:
                    del data[url]
            self._write(shop_id, data)

    def _write(self, shop_id, data):
        tmp = self._path(shop_id).with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n")
        os.replace(tmp, self._path(shop_id))

    def facts(self, deal, today):
        rows = [r for r in self._load(deal["shop_id"]).get(deal["url"], []) if r[0] < today and r[1] is not None]
        if not rows:
            return {"days_seen": 0, "lowest_before": None, "usual_price": None}
        prices = [r[1] for r in rows]
        counts = collections.Counter(prices)
        top = max(counts.values())
        return {"days_seen": len({r[0] for r in rows}),
                "lowest_before": min(prices),
                "usual_price": min(p for p, c in counts.items() if c == top)}


_default = None


def _hist():
    global _default
    if _default is None:
        _default = History()
    return _default


def record(deals, date):
    _hist().record(deals, date)


def facts(deal, today=None):
    return _hist().facts(deal, today or datetime.date.today().isoformat())
