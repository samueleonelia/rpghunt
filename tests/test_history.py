import json
import pathlib
import tempfile
import unittest

from scraper.history import History


def deal(price_now, price_was=30.0, url="https://s.example/p/a", shop="s"):
    return {"shop_id": shop, "url": url, "price_now": price_now, "price_was": price_was}


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.h = History(self.dir)

    def test_no_history(self):
        self.assertEqual(self.h.facts(deal(10), "2026-10-17"),
                         {"days_seen": 0, "lowest_before": None, "usual_price": None})

    def test_usual_price_and_lowest_before(self):
        for day, price in [("2026-10-10", 20.0), ("2026-10-11", 20.0), ("2026-10-12", 18.0), ("2026-10-13", 20.0)]:
            self.h.record([deal(price)], day)
        f = self.h.facts(deal(15), "2026-10-17")
        self.assertEqual(f, {"days_seen": 4, "lowest_before": 18.0, "usual_price": 20.0})

    def test_usual_price_tie_takes_the_lower(self):
        self.h.record([deal(20.0)], "2026-10-10")
        self.h.record([deal(15.0)], "2026-10-11")
        self.assertEqual(self.h.facts(deal(15), "2026-10-17")["usual_price"], 15.0)

    def test_today_is_not_counted_so_order_does_not_matter(self):
        self.h.record([deal(20.0)], "2026-10-16")
        before = self.h.facts(deal(15), "2026-10-17")
        self.h.record([deal(15.0)], "2026-10-17")
        self.assertEqual(self.h.facts(deal(15), "2026-10-17"), before)

    def test_record_is_idempotent_for_the_same_date(self):
        self.h.record([deal(20.0)], "2026-10-17")
        first = (self.dir / "s.json").read_text()
        self.h.record([deal(20.0)], "2026-10-17")
        self.assertEqual((self.dir / "s.json").read_text(), first)
        self.h.record([deal(19.0)], "2026-10-17")      # same day, new price replaces the row
        rows = json.loads((self.dir / "s.json").read_text())["https://s.example/p/a"]
        self.assertEqual(rows, [["2026-10-17", 19.0, 30.0]])

    def test_window_drops_old_rows(self):
        self.h.record([deal(20.0)], "2026-05-01")
        self.h.record([deal(18.0)], "2026-10-17")
        rows = json.loads((self.dir / "s.json").read_text())["https://s.example/p/a"]
        self.assertEqual([r[0] for r in rows], ["2026-10-17"])

    def test_persists_between_instances_and_shops_are_separate(self):
        self.h.record([deal(20.0), deal(5.0, url="https://t.example/p/b", shop="t")], "2026-10-10")
        h2 = History(self.dir)
        self.assertEqual(h2.facts(deal(1), "2026-10-17")["usual_price"], 20.0)
        self.assertEqual(h2.facts(deal(1, url="https://t.example/p/b", shop="t"), "2026-10-17")["usual_price"], 5.0)
        self.assertTrue((self.dir / "t.json").exists())

    def test_broken_file_is_ignored(self):
        (self.dir / "s.json").write_text("{not json")
        self.assertEqual(self.h.facts(deal(1), "2026-10-17")["days_seen"], 0)


if __name__ == "__main__":
    unittest.main()
