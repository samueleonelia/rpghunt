import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scraper import agent, escalate
from scraper.agent import FakeAgent

FIX = pathlib.Path(__file__).parent / "fixtures"
DATE = "2026-10-17"
PAGE = (FIX / "check" / "page_ok.html").read_text()
URL = "https://shop.example/p/ember"
RAW_DEAL = {"type": "sale", "title": "Ember Hollow Core Book", "shop": "Shop", "shop_id": "shop", "url": URL,
            "price_now": 24.0, "price_was": 30.0, "currency": "USD", "ends": None, "found_via": "x", "source": "jsonld"}
SHOPS = [
    {"id": "gen0", "name": "Gen Zero", "store_url": "https://gen0.example/", "platform": "generic", "status": "active", "recipe": {}},
    {"id": "genok", "name": "Gen Ok", "store_url": "https://genok.example/", "platform": "generic", "status": "active", "recipe": {}},
    {"id": "shopi", "name": "Shopi", "store_url": "https://shopi.example/", "platform": "shopify", "status": "active", "recipe": {}},
    {"id": "paused", "name": "Paused", "store_url": "https://p.example/", "platform": "generic", "status": "paused", "recipe": {}},
]
ROWS = [{"id": "gen0", "platform": "generic", "status": "ok", "deals": 0, "no_sale_page": True, "errors": []},
        {"id": "genok", "platform": "generic", "status": "ok", "deals": 4, "errors": []},
        {"id": "shopi", "platform": "shopify", "status": "ok", "deals": 0, "errors": [], "break_alarm": DATE},
        {"id": "paused", "platform": "generic", "status": "ok", "deals": 0, "errors": []}]


class Candidates(unittest.TestCase):
    def test_which_shops_get_a_recipe_job(self):
        got = escalate.recipe_candidates(SHOPS, {"shops": ROWS}, {}, DATE)
        self.assertEqual([(s["id"], why) for s, why in got], [("shopi", "break alarm"), ("gen0", "no sale page")])

    def test_recent_attempt_blocks_a_retry_unless_forced(self):
        att = {"gen0": {"date": "2026-10-14", "outcome": "rejected"}}
        self.assertEqual([s["id"] for s, _ in escalate.recipe_candidates(SHOPS, {"shops": ROWS}, att, DATE)], ["shopi"])
        self.assertEqual(len(escalate.recipe_candidates(SHOPS, {"shops": ROWS}, att, DATE, retry=True)), 2)
        att = {"gen0": {"date": "2026-10-01", "outcome": "rejected"}}
        self.assertEqual(len(escalate.recipe_candidates(SHOPS, {"shops": ROWS}, att, DATE)), 2)


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        (self.tmp / "raw").mkdir()
        (self.tmp / "check-report-2026-10-17.json").write_text(json.dumps({
            "needs_agent": [{"url": URL, "title": "Ember Hollow Core Book", "shop": "Shop", "reasons": ["support_unsure: silent (0.6)"]}],
            "deals": [{"url": URL, "check": {"support": {"choice": "silent", "confidence": 0.6}}}]}))
        (self.tmp / "scrape-report-2026-10-17.json").write_text(json.dumps({"shops": ROWS}))
        (self.tmp / "raw" / "2026-10-17-scraper.json").write_text(json.dumps([RAW_DEAL]))
        patches = [mock.patch.object(escalate, "REPORTS", self.tmp), mock.patch.object(escalate, "RAW", self.tmp / "raw"),
                   mock.patch.object(escalate, "ATTEMPTS", self.tmp / "attempts.json")]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.load = lambda url: PAGE

    def go(self, ag, **kw):
        saved = []
        with mock.patch.object(agent, "save_recipe", lambda *a: saved.append(a) or True):
            out = escalate.run(DATE, ag, load=self.load, shops=SHOPS, **kw)
        return out, saved

    def good_recheck(self, job):
        return {"job": "recheck", "deal_url": URL, "verdict": "publish", "price_now_seen": "$24.00",
                "price_was_seen": "$30.00", "ends_seen": None, "reason": "sale", "notes": ""}

    def test_accepted_recheck_is_appended_as_published_with_agent_details(self):
        ag = FakeAgent(lambda job: self.good_recheck(job) if job["job"] == "recheck" else None)
        (esc, owner, new, counts), saved = self.go(ag, max_jobs=None)
        self.assertEqual(len(new), 1)
        checked = json.loads((self.tmp / "raw" / "2026-10-17-checked.json").read_text())
        c = checked[0]["check"]
        self.assertEqual((c["decision"], c["via"], c["agent"]["verdict"]), ("publish", "agent", "publish"))
        self.assertNotIn(URL, owner)
        # the recipe jobs failed to run (handler gave None): marked error, nothing to the owner list for them
        self.assertEqual({j["outcome"] for j in esc["jobs"] if j["job"] == "recipe"}, {"error"})

    def test_unsettled_goes_to_owner_file_with_a_question(self):
        (esc, owner, new, counts), saved = self.go(FakeAgent())      # FakeAgent says unsure to everything
        self.assertEqual(new, [])
        items = json.loads((self.tmp / "needs-owner-2026-10-17.json").read_text())
        self.assertEqual({i["key"] for i in items}, {URL, "recipe:gen0", "recipe:shopi"})
        deal = next(i for i in items if i["kind"] == "deal")
        self.assertEqual((deal["price_now"], deal["jev"]["support"]["choice"], deal["agent"]["verdict"]), (24.0, "silent", "unsure"))
        self.assertTrue(deal["question"].endswith("yes or no."))
        self.assertEqual(saved, [])

    def test_max_jobs_and_rerun_skips_finished_jobs(self):
        ag = FakeAgent()
        self.go(ag, max_jobs=1)
        self.assertEqual(len(ag.jobs), 1)
        self.go(ag)                                                  # two more, the first is already done
        self.assertEqual(len(ag.jobs), 3)
        self.go(ag)
        self.assertEqual(len(ag.jobs), 3)

    def test_accepted_recipe_is_saved_and_not_in_owner_list(self):
        good = {"accepted": True, "reasons": ["ok"], "recipe": {"sale_pages": ["u"]}, "deals": 3, "matched": [], "sample": []}
        ag = FakeAgent(lambda job: {"job": "recipe", "result": "recipe", "recipe": {}, "evidence": [], "notes": ""}
                       if job["job"] == "recipe" else None)
        saved = []
        with mock.patch.object(agent, "save_recipe", lambda *a: saved.append(a) or True):
            esc, owner, new, counts = escalate.run(DATE, ag, load=self.load, shops=SHOPS, validate_recipe=lambda s, a: good)
        self.assertEqual(sorted(a[0] for a in saved), ["gen0", "shopi"])
        self.assertNotIn("recipe:gen0", owner)
        self.assertEqual(json.loads((self.tmp / "attempts.json").read_text())["gen0"]["outcome"], "accepted")

    def day(self, date, deal=None):
        """Copy today's input files to another date, optionally with a changed deal."""
        for name in ("check-report-{}.json", "scrape-report-{}.json"):
            (self.tmp / name.format(date)).write_text((self.tmp / name.format(DATE)).read_text())
        (self.tmp / "raw" / f"{date}-scraper.json").write_text(json.dumps([deal or RAW_DEAL]))

    def rechecks(self, ag):
        return [j for j in ag.jobs if j["job"] == "recheck"]

    def test_same_link_and_price_reuses_the_verdict_next_day(self):
        ag = FakeAgent(lambda job: self.good_recheck(job) if job["job"] == "recheck" else None)
        self.go(ag)
        self.assertEqual(len(self.rechecks(ag)), 1)
        self.day("2026-10-18")
        esc, owner, new, counts = escalate.run("2026-10-18", ag, load=self.load, shops=SHOPS)
        self.assertEqual(len(self.rechecks(ag)), 1)                  # no second paid job
        self.assertEqual(esc["counts"]["reused_from_memory"], 1)
        self.assertEqual(new[0]["check"]["reused_from"], DATE)
        row = next(j for j in esc["jobs"] if j["job"] == "recheck")
        self.assertEqual((row["outcome"], row["agent_run"]), ("publish", None))

    def test_remembered_unsure_still_goes_to_the_owner(self):
        ag = FakeAgent()
        self.go(ag)
        self.day("2026-10-18")
        esc, owner, new, counts = escalate.run("2026-10-18", ag, load=self.load, shops=SHOPS)
        self.assertEqual(len(self.rechecks(ag)), 1)
        self.assertIn(URL, owner)

    def test_price_change_means_a_new_job_but_age_alone_does_not(self):
        ag = FakeAgent(lambda job: self.good_recheck(job) if job["job"] == "recheck" else None)
        self.go(ag)
        self.day("2026-10-18", dict(RAW_DEAL, price_now=20.0))
        escalate.run("2026-10-18", ag, load=self.load, shops=SHOPS)
        self.assertEqual(len(self.rechecks(ag)), 2)                  # price changed
        for date in ("2026-10-22", "2026-10-26", "2026-10-30"):      # still on sale, same price: no new job
            self.day(date, dict(RAW_DEAL, price_now=20.0))
            escalate.run(date, ag, load=self.load, shops=SHOPS)
        self.assertEqual(len(self.rechecks(ag)), 2)
        m = json.loads((self.tmp / "agent-memory.json").read_text())[escalate.memory_key(RAW_DEAL)]
        self.assertEqual((m["date"], m["last_seen"]), ("2026-10-18", "2026-10-30"))

    def test_failed_agent_run_is_not_remembered(self):
        self.go(FakeAgent(lambda job: None))                          # every job fails to run
        self.assertEqual(json.loads((self.tmp / "agent-memory.json").read_text()), {})

    def test_fake_mode_never_saves(self):
        (esc, owner, new, counts), saved = self.go(FakeAgent(), fake=True)
        self.assertEqual(saved, [])
        self.assertFalse((self.tmp / "attempts.json").exists())


if __name__ == "__main__":
    unittest.main()
