import pathlib
import unittest
from unittest import mock

from scraper import agent
from scraper.common import FetchError

FIX = pathlib.Path(__file__).parent / "fixtures"
DATE = "2026-10-17"
PAGE = (FIX / "check" / "page_ok.html").read_text()      # shows $30.00 crossed out, $24.00 now


def deal(**kw):
    d = {"type": "sale", "title": "Ember Hollow Core Book", "shop": "Shop", "shop_id": "shop",
         "url": "https://shop.example/p/ember", "price_now": 24.0, "price_was": 30.0, "currency": "USD",
         "ends": None, "found_via": "https://shop.example/sale", "source": "jsonld"}
    d.update(kw)
    return d


def publish(**kw):
    a = {"job": "recheck", "deal_url": "https://shop.example/p/ember", "verdict": "publish",
         "price_now_seen": "$24.00", "price_was_seen": "$30.00", "ends_seen": None, "reason": "Autumn Sale", "notes": ""}
    a.update(kw)
    return a


def page_loader(html=PAGE):
    return lambda url: html


class Extract(unittest.TestCase):
    def test_last_object_wins_and_fences_are_fine(self):
        text = 'I looked.\n```json\n{"a": 1}\n```\nFinal:\n{"job": "recheck", "x": {"y": 2}}\nThanks'
        self.assertEqual(agent.extract_json(text), {"job": "recheck", "x": {"y": 2}})

    def test_no_object(self):
        self.assertIsNone(agent.extract_json("nothing here {not json"))


class Command(unittest.TestCase):
    def test_flags(self):
        cmd = agent.claude_command("BRIEF")
        self.assertEqual(cmd[:2], ["claude", "-p"])
        self.assertEqual(cmd[cmd.index("--model") + 1], "sonnet")
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "Bash(.venv/bin/python -m scraper.fetchpage:*)")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Bash")
        self.assertEqual(cmd[cmd.index("--append-system-prompt") + 1], "BRIEF")
        for forbidden in ("--bare", "--setting-sources", "--safe-mode", "--dangerously-skip-permissions"):
            self.assertNotIn(forbidden, cmd)

    def test_run_parses_cli_json(self):
        out = ('{"type":"result","is_error":false,"num_turns":4,"total_cost_usd":0.12,'
               '"result":"done\\n{\\"job\\": \\"recipe\\", \\"result\\": \\"unsure\\"}"}')
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout=out, stderr="")) as run:
            r = agent.ClaudeAgent().run({"job": "recipe", "shop": {"id": "x"}}, DATE)
        self.assertEqual((r.answer, r.turns, r.cost_usd, r.error), ({"job": "recipe", "result": "unsure"}, 4, 0.12, None))
        self.assertIn("fetchpage", run.call_args.kwargs["input"])     # the job goes in on stdin

    def test_cli_failure_is_an_error_not_a_crash(self):
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=1, stdout="", stderr="boom")):
            r = agent.ClaudeAgent().run({"job": "recipe", "shop": {"id": "x"}}, DATE)
        self.assertIsNone(r.answer)
        self.assertIn("boom", r.error)


class RecheckValidation(unittest.TestCase):
    def check(self, answer, d=None, jev=None, html=PAGE):
        return agent.validate_recheck(d or deal(), answer, jev, DATE, page_loader(html))

    def test_publish_accepted(self):
        r = self.check(publish())
        self.assertEqual((r["outcome"], r["reasons"]), ("publish", ["ok"]))
        self.assertEqual(r["agent"]["price_now_seen"], "$24.00")

    def test_publish_with_price_not_on_page_goes_to_owner(self):
        r = self.check(publish(price_now_seen="$19.00"), deal(price_now=19.0))
        self.assertEqual(r["outcome"], "needs_owner")
        self.assertTrue(any(x.startswith("price_not_on_page") for x in r["reasons"]))

    def test_agent_price_must_equal_claim(self):
        r = self.check(publish(price_now_seen="$30.00"))      # $30 is on the page, but not the claimed price
        self.assertEqual(r["outcome"], "needs_owner")
        self.assertTrue(any(x.startswith("price_mismatch") for x in r["reasons"]))

    def test_jev_contradicts_is_not_overruled(self):
        jev = {"support": {"choice": "contradicts", "confidence": 0.9}}
        r = self.check(publish(), jev=jev)
        self.assertEqual(r["outcome"], "needs_owner")
        self.assertTrue(r["reasons"][0].startswith("jev_contradicts"))

    def test_weak_jev_contradicts_does_not_block(self):
        jev = {"support": {"choice": "contradicts", "confidence": 0.5}}
        self.assertEqual(self.check(publish(), jev=jev)["outcome"], "publish")

    def test_unsure_goes_to_owner(self):
        r = self.check(publish(verdict="unsure", price_now_seen=None, reason="page is empty"))
        self.assertEqual(r["outcome"], "needs_owner")

    def test_drop_is_dropped(self):
        self.assertEqual(self.check(publish(verdict="drop", reason="sale ended"))["outcome"], "drop")

    def test_not_a_discount_or_ended_deal_fails_the_code_checks(self):
        self.assertEqual(self.check(publish(), deal(price_was=24.0))["outcome"], "needs_owner")
        self.assertEqual(self.check(publish(), deal(ends="2026-10-01"))["outcome"], "needs_owner")
        self.assertEqual(self.check(publish(ends_seen="Oct 1, 2026"))["outcome"], "needs_owner")

    def test_answer_about_another_url(self):
        r = self.check(publish(deal_url="https://shop.example/p/other"))
        self.assertEqual(r["outcome"], "needs_owner")
        self.assertTrue(r["reasons"][0].startswith("wrong_url"))

    def test_page_unreadable_and_no_answer(self):
        def gone(url):
            raise FetchError("blocked", url, "HTTP 403")
        r = agent.validate_recheck(deal(), publish(), None, DATE, gone)
        self.assertEqual(r["outcome"], "needs_owner")
        self.assertEqual(agent.validate_recheck(deal(), None, None, DATE, gone)["outcome"], "needs_owner")

    def test_date_text(self):
        self.assertEqual(agent.parse_date_text("Ends Nov 1, 2026"), "2026-11-01")
        self.assertEqual(agent.parse_date_text("1 November 2026"), "2026-11-01")
        self.assertEqual(agent.parse_date_text("2026-11-01T12:00Z"), "2026-11-01")
        self.assertIsNone(agent.parse_date_text("soon"))


SHOP = {"id": "demo", "name": "Demo", "store_url": "https://shop.example/", "platform": "generic",
        "currency": "USD", "recipe": {}, "notes": None}


def recipe_answer(**kw):
    a = {"job": "recipe", "shop_id": "demo", "result": "recipe",
         "recipe": {"sale_pages": ["https://shop.example/sale"], "product_link": "a.card-title",
                    "price_now": ".price-now", "price_was": ".price-was", "ends": None},
         "evidence": [{"url": "https://shop.example/products/ember-hollow", "price_now_text": "$24.00",
                       "price_was_text": "$30.00"}], "notes": ""}
    a.update(kw)
    return a


def fake_reader(deals):
    return lambda shop: (deals, {"items_read": len(deals)})


DEAL = {"title": "Ember", "url": "https://shop.example/products/ember-hollow", "price_now": 24.0, "price_was": 30.0}


class RecipeValidation(unittest.TestCase):
    def test_accepted_when_deals_match_evidence(self):
        v = agent.validate_recipe(SHOP, recipe_answer(), fake_reader([DEAL]))
        self.assertTrue(v["accepted"], v)
        self.assertEqual(v["recipe"]["product_link"], "a.card-title")
        self.assertTrue(v["matched"][0]["same_url"])

    def test_rejected_when_no_deals(self):
        v = agent.validate_recipe(SHOP, recipe_answer(), fake_reader([]))
        self.assertFalse(v["accepted"])
        self.assertTrue(v["reasons"][0].startswith("no_deals"))

    def test_rejected_when_evidence_prices_do_not_match(self):
        ev = [{"url": "u", "price_now_text": "$99.00", "price_was_text": "$120.00"}]
        v = agent.validate_recipe(SHOP, recipe_answer(evidence=ev), fake_reader([DEAL]))
        self.assertFalse(v["accepted"])
        self.assertTrue(v["reasons"][0].startswith("evidence_mismatch"))

    def test_rejected_without_evidence_or_with_other_results(self):
        self.assertFalse(agent.validate_recipe(SHOP, recipe_answer(evidence=[]), fake_reader([DEAL]))["accepted"])
        self.assertFalse(agent.validate_recipe(SHOP, {"result": "no_sales_found"}, fake_reader([DEAL]))["accepted"])
        self.assertFalse(agent.validate_recipe(SHOP, None, fake_reader([DEAL]))["accepted"])

    def test_off_site_sale_page_and_bad_selector_are_rejected_before_any_fetch(self):
        called = []
        reader = lambda shop: called.append(1) or ([DEAL], {})
        bad_page = recipe_answer(recipe={"sale_pages": ["https://evil.example/sale"], "product_link": "a"})
        bad_css = recipe_answer(recipe={"sale_pages": ["https://shop.example/sale"], "price_now": "a[["})
        self.assertFalse(agent.validate_recipe(SHOP, bad_page, reader)["accepted"])
        self.assertFalse(agent.validate_recipe(SHOP, bad_css, reader)["accepted"])
        self.assertEqual(called, [])

    def test_trial_runs_on_a_copy(self):
        seen = {}

        def reader(shop):
            seen.update(shop)
            return [DEAL], {}
        shop = dict(SHOP, platform="shopify", recipe={"collections": ["x"]})
        agent.validate_recipe(shop, recipe_answer(), reader)
        self.assertEqual(seen["platform"], "generic")
        self.assertEqual(shop["platform"], "shopify")
        self.assertEqual(shop["recipe"], {"collections": ["x"]})

    def test_real_generic_reader_on_a_listing_page(self):
        pages = {"https://shop.example/sale": (FIX / "agent" / "listing_page.html").read_text(),
                 "https://shop.example/products/ember-hollow": (FIX / "agent" / "product_ember.html").read_text(),
                 "https://shop.example/products/mist-marches": (FIX / "agent" / "product_mist.html").read_text()}
        def fetch(url):
            if url not in pages:                 # the recipe's CSS also matches the hidden card: a dead link
                raise FetchError("dead", url, "HTTP 404")
            return mock.Mock(body=pages[url].encode(), encoding="utf-8")
        with mock.patch("scraper.readers.generic.fetch", fetch):
            v = agent.validate_recipe(SHOP, recipe_answer())
        self.assertTrue(v["accepted"], v)
        self.assertEqual(v["deals"], 2)

    def test_save_recipe_writes_platform_recipe_date_and_note(self):
        shops = [dict(SHOP, platform="unknown", recipe_confirmed=None, notes="sale page: x"), {"id": "other"}]
        saved = []
        with mock.patch.object(agent, "load_shops", lambda: shops), \
                mock.patch.object(agent, "save_shops", lambda s: saved.append([dict(x) for x in s])):
            self.assertTrue(agent.save_recipe("demo", {"sale_pages": ["u"]}, DATE))
        s = saved[0][0]
        self.assertEqual((s["platform"], s["recipe"], s["recipe_confirmed"]), ("generic", {"sale_pages": ["u"]}, DATE))
        self.assertEqual(s["notes"], f"sale page: x; recipe by browsing agent {DATE}")
        self.assertEqual(saved[0][1], {"id": "other"})


if __name__ == "__main__":
    unittest.main()
