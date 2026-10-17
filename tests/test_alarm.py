import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scraper import alarm, run
from scraper.common import FetchError
from scraper.readers import itch
from tests.test_itch import EA, MYSTERY, SHOP, WITCH, fake_fetch, fake_fetch_json, read_fix


def seven(count):
    return [[f"2026-10-{10 + i:02d}", count] for i in range(7)]


class IsBreak(unittest.TestCase):
    def test_zero_after_healthy_average(self):
        self.assertEqual(alarm.is_break([5] * 7, 0), (True, 5.0))

    def test_seventy_percent_drop(self):
        self.assertTrue(alarm.is_break([10] * 7, 3)[0])        # exactly -70%
        self.assertFalse(alarm.is_break([10] * 7, 4)[0])       # -60%

    def test_low_average_never_alarms(self):
        self.assertFalse(alarm.is_break([2] * 7, 0)[0])

    def test_new_shop_with_no_or_thin_history(self):
        self.assertEqual(alarm.is_break([], 0), (False, None))
        self.assertFalse(alarm.is_break([9, 9], 0)[0])

    def test_only_last_seven_runs_count(self):
        self.assertFalse(alarm.is_break([30] * 5 + [0] * 7, 0)[0])


class Apply(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "run-history.json"

    def test_flags_records_and_is_idempotent(self):
        self.path.write_text(json.dumps({"a": seven(5), "b": seven(5)}))
        rows = [{"id": "a", "status": "ok", "deals": 0}, {"id": "b", "status": "ok", "deals": 5},
                {"id": "new", "status": "ok", "deals": 0}, {"id": "c", "status": "error", "deals": 0}]
        for _ in range(2):                     # same date twice: same answer
            rows = [dict(r) for r in rows]
            self.assertEqual(alarm.apply(rows, "2026-10-18", self.path), ["a"])
        self.assertEqual(rows[0]["break_alarm"], "2026-10-18")
        self.assertNotIn("break_alarm", rows[1])
        self.assertNotIn("break_alarm", rows[2])         # no history
        hist = json.loads(self.path.read_text())
        self.assertEqual(len(hist["a"]), 7)              # capped at the last 7 runs
        self.assertEqual(hist["a"][-1], ["2026-10-18", 0])
        self.assertEqual(hist["new"], [["2026-10-18", 0]])
        self.assertNotIn("c", hist)                      # errored runs are not recorded


class ItchLayoutChange(unittest.TestCase):
    """The simulated layout change: itch changes its game pages and data.json, no error is raised."""

    def moved(self, url):
        return read_fix("game_sale.html").replace("original_price", "old_cost").replace("sale_rate", "discount")

    def changed_fetch(self, url):
        if url.endswith(".xml"):
            return fake_fetch(url)                          # the feed still works
        return mock.Mock(body=self.moved(url).replace("application/ld+json", "text/plain").encode())

    def changed_json(self, url):
        return {"price": "$8.00", "promo": {"id": 5, "rate": 20}}     # "sale" renamed to "promo"

    def run_itch(self, fetch, fetch_json):
        with mock.patch.object(itch, "fetch", fetch), mock.patch.object(itch, "fetch_json", fetch_json):
            return run.run_shop(dict(SHOP, status="active"))

    def test_changed_markup_gives_zero_deals_without_error_and_the_alarm_fires(self):
        _, healthy = self.run_itch(fake_fetch, fake_fetch_json)
        self.assertEqual((healthy["status"], healthy["deals"]), ("ok", 2))
        deals, broken = self.run_itch(self.changed_fetch, self.changed_json)
        self.assertEqual((deals, broken["status"], broken["deals"], broken["errors"]), ([], "ok", 0, []))

        path = pathlib.Path(tempfile.mkdtemp()) / "run-history.json"
        path.write_text(json.dumps({"itch-io": [[f"2026-10-{10 + i:02d}", healthy["deals"] + 3] for i in range(7)]}))
        self.assertEqual(alarm.apply([broken], "2026-10-18", path), ["itch-io"])
        self.assertEqual(broken["break_alarm"], "2026-10-18")

    def test_healthy_run_does_not_alarm(self):
        _, healthy = self.run_itch(fake_fetch, fake_fetch_json)
        path = pathlib.Path(tempfile.mkdtemp()) / "run-history.json"
        path.write_text(json.dumps({"itch-io": [[f"2026-10-{10 + i:02d}", 2] for i in range(7)]}))
        self.assertEqual(alarm.apply([healthy], "2026-10-18", path), [])


if __name__ == "__main__":
    unittest.main()
