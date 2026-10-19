import json
import pathlib
import tempfile
import types
import unittest

from scraper import daily

DATE = "2026-10-17"


def ctx(**kw):
    return types.SimpleNamespace(**{"date": DATE, "fake": False, "skip_run": False, "max_agent_jobs": None, **kw})


def stubs(log, fail=None, raise_in=None):
    def make(name):
        def stage(c):
            log.append(name)
            if name == raise_in:
                raise RuntimeError("boom")
            return {"status": "error", "note": "rc 2"} if name == fail else {"note": f"{name} done"}
        return stage
    return {n: make(n) for n in daily.STAGE_ORDER}


class Order(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def test_stages_run_in_the_documented_order_then_the_report(self):
        log = []
        results, path = daily.run_day(ctx(), stubs(log), self.tmp)
        self.assertEqual(log, ["run", "discover", "missed", "check", "escalate", "publish"])
        self.assertEqual(daily.STAGE_ORDER, log)
        self.assertTrue(path.exists())
        self.assertEqual(path.name, f"daily-report-{DATE}.md")
        self.assertTrue(all(r["status"] == "ok" and "seconds" in r for r in results.values()))

    def test_a_failing_or_crashing_stage_does_not_stop_the_day(self):
        log = []
        results, path = daily.run_day(ctx(), stubs(log, fail="check", raise_in="missed"), self.tmp)
        self.assertEqual(len(log), 6)
        self.assertEqual((results["check"]["status"], results["missed"]["status"]), ("error", "error"))
        self.assertIn("RuntimeError", results["missed"]["note"])
        text = path.read_text()
        self.assertIn("These steps failed", text)

    def test_fake_run_writes_a_fake_report(self):
        _, path = daily.run_day(ctx(fake=True), stubs([]), self.tmp)
        self.assertEqual(path.name, f"daily-report-{DATE}-FAKE.md")
        self.assertIn("TEST run", path.read_text())

    def test_timing_uses_the_clock(self):
        ticks = iter(range(0, 1000, 5))
        results, _ = daily.run_day(ctx(), stubs([]), self.tmp, clock=lambda: next(ticks))
        self.assertEqual([r["seconds"] for r in results.values()], [5.0] * 6)


class Wiring(unittest.TestCase):
    def test_default_stages_call_the_right_modules(self):
        calls = []
        from unittest import mock
        with mock.patch.object(daily.run_mod, "main", lambda a: calls.append(("run", a)) or 0), \
                mock.patch.object(daily.check, "main", lambda a: calls.append(("check", a)) or 0), \
                mock.patch.object(daily.escalate, "main", lambda a: calls.append(("escalate", a)) or 0), \
                mock.patch.object(daily.publish, "main", lambda a: calls.append(("publish", a)) or 0):
            c = ctx(fake=True, max_agent_jobs=0)
            for n in ("run", "check", "escalate", "publish"):
                daily.DEFAULT_STAGES[n](c)
        d = dict(calls)
        self.assertEqual(d["run"], ["--date", DATE])
        self.assertEqual(d["check"], ["--date", DATE, "--fake"])
        self.assertEqual(d["escalate"], ["--date", DATE, "--max-jobs", "0", "--fake"])
        self.assertEqual(d["publish"], ["--date", DATE, "--fake"])

    def test_skip_run_skips_only_the_shop_run(self):
        r = daily.stage_run(ctx(skip_run=True))
        self.assertEqual(r["status"], "skipped")


class Report(unittest.TestCase):
    def test_report_reads_the_day_files(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        w = lambda name, data: (tmp / name).write_text(json.dumps(data))
        w(f"scrape-report-{DATE}.json", {"shops": [{"id": "a", "break_alarm": DATE, "deals": 0, "alarm_average": 12.5}],
                                         "totals": {"shops": 1, "ok": 1, "blocked": 0, "error": 0, "deals_unique": 7}})
        w(f"leads-{DATE}.json", {"counts": {"leads": 9, "known_shop": 2, "blocked_shop": 5, "new_shop": 2},
                                 "feeds": [{"id": "f", "status": "ok"}, {"id": "g", "status": "blocked"}],
                                 "new_shops": [{"id": "n", "name": "New Shop", "platform": "generic", "status": "active",
                                                "needs_recipe": True, "store_url": "https://n.example"}]})
        w(f"missed-{DATE}.json", {"counts": {"misses": 2, "by_reason": {"reader_gap": 1, "shop_blocked": 1}}, "misses": [
            {"title": "Lost Thing", "shop": "Shop", "url": "https://s/p/lost", "reason": "reader_gap", "candidate": True},
            {"title": None, "shop": "DriveThruRPG", "url": "https://d/p/1", "reason": "shop_blocked", "candidate": False}]})
        w(f"check-report-{DATE}.json", {"counts": {"deals_in": 7, "published": 3, "needs_agent": 2, "rpg_dropped_stage_a": 1},
                                        "jev": {"requests": 4, "input_tokens": 1000, "output_tokens": 50, "cache_hits": 1,
                                                "estimated_cost_usd": 0.0004}})
        w(f"escalation-{DATE}.json", {"counts": {"jobs_found": 2, "run_now": 1, "published_by_agent": 0},
                                      "jobs": [{"job": "recheck", "agent_run": {"cost_usd": 0.12}}]})
        w(f"needs-owner-{DATE}.json", [{"title": "Odd Deal", "shop": "Shop", "url": "https://s/p/odd", "question": "Is it on sale?"}])
        w(f"site-preview-{DATE}.json", {"date": DATE, "deals": [
            {"type": "free", "title": "Free One", "url": "https://s/f", "shop": "S", "price_now": 0, "price_was": 5,
             "currency": "USD", "discount_pct": 100, "image": "x", "game_id": None}]})
        results = {n: {"status": "ok", "seconds": 1.5} for n in daily.STAGE_ORDER}
        text = daily.build_report(ctx(max_agent_jobs=1), results, tmp)
        for needle in ("Top 10 deals", "[Free One](https://s/f)", "New Shop", "needs a recipe", "a: 0 deals today",
                       "Lost Thing", "Odd Deal", "Is it on sale?", "Total: 9.0 s", "$0.12", "1000 tokens in",
                       "1 more deal(s) are waiting"):
            self.assertIn(needle.replace("a: 0", "**a**: 0"), text)

    def test_agent_runs_every_job_by_default(self):
        seen = {}
        orig = daily.escalate.main
        daily.escalate.main = lambda args: seen.setdefault("args", args) and 0
        try:
            daily.stage_escalate(ctx())
        finally:
            daily.escalate.main = orig
        self.assertEqual(seen["args"], ["--date", DATE])
        self.assertIsNone(daily.missed.MAX_FETCHES)

    def test_cost_alarm_and_safety_limits_in_report(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / f"scrape-report-{DATE}.json").write_text(json.dumps({"shops": [
            {"id": "bigshop", "deals": 3, "stopped_early": "stopped at the 500-page safety limit"},
            {"id": "fine", "deals": 2}]}))
        (tmp / f"check-report-{DATE}.json").write_text(json.dumps({"jev": {"estimated_cost_usd": 0.5}}))
        (tmp / f"escalation-{DATE}.json").write_text(json.dumps(
            {"jobs": [{"job": "recheck", "agent_run": {"cost_usd": 3.0}}] * 2}))
        text = daily.build_report(ctx(cost_alarm=5.0), {}, tmp)
        self.assertIn("1 shop(s) hit a safety limit", text)
        self.assertIn("**bigshop**: stopped at the 500-page safety limit.", text)
        self.assertIn("Cost alarm: today cost about $6.50", text)
        self.assertIn("Day total: about $6.50", text)
        quiet = daily.build_report(ctx(cost_alarm=10.0), {}, tmp)
        self.assertNotIn("Cost alarm", quiet)
        self.assertNotIn("waiting for the browsing agent", quiet)

    def test_empty_day_does_not_crash(self):
        text = daily.build_report(ctx(), {}, pathlib.Path(tempfile.mkdtemp()))
        self.assertIn("RPG Hunt daily report", text)


if __name__ == "__main__":
    unittest.main()
