import copy
import pathlib
import tempfile
import unittest

from scraper import check
from scraper.common import FetchError
from scraper.history import History
from scraper.jev import FakeJev, JevError

FIX = pathlib.Path(__file__).parent / "fixtures" / "check"
TESTFIX = pathlib.Path(__file__).resolve().parent.parent / "data" / "testset" / "fixtures"
DATE = "2026-10-17"
T = check.THRESHOLDS


def feed_deal(**kw):
    d = {"type": "sale", "title": "Dungeon Delvers Core Rulebook", "game": None, "shop": "Shop", "shop_id": "shop",
         "url": "https://shop.example/products/delvers", "price_now": 15.0, "price_was": 30.0, "currency": "USD",
         "format": None, "ends": None, "found_via": "/collections/sale", "source": "shopify-api",
         "hints": {"product_type": "Books", "tags": ["rpg"]}}
    d.update(kw)
    return d


def page_deal(**kw):
    d = feed_deal(url="https://shop.example/p/ember", title="Ember Hollow Core Book", price_now=24.0, price_was=30.0,
                  source="jsonld", hints={})
    d.update(kw)
    return d


def choice(option, options, conf=0.9):
    rest = [o for o in options if o != option]
    return {"type": "choice", "choice": option, "confidence": conf,
            "probabilities": {o: (conf if o == option else (1 - conf) / max(1, len(rest))) for o in options}}


def script(**answers):
    """FakeJev whose answers are set per question id. Values: a number (noul) or (option, confidence)."""
    def forced(qid, q, state):
        key = qid if qid in answers else ("p*" if qid.startswith("p") and qid[1:].isdigit() else None)
        if key not in answers:
            return None
        v = answers[key]
        if q["type"] == "noul":
            return {"type": "noul", "noul": v}
        option, conf = v if isinstance(v, tuple) else (v, 0.9)
        return choice(option, list(q["criteria"]), conf)
    return FakeJev(forced=forced)


class Base(unittest.TestCase):
    def setUp(self):
        self.hist = History(tempfile.mkdtemp())
        self.page_html = (FIX / "page_ok.html").read_text()
        # Test deals come from shop "shop", treated as a retailer with everyday below-list
        # prices, so the offer_kind and history rules are exercised. Publisher shops: see below.
        check._everyday_shops = {"shop"}

    def tearDown(self):
        check._everyday_shops = None

    def load(self, deal):
        if isinstance(self.page_html, Exception):
            raise self.page_html
        return self.page_html

    def run_check(self, deals, jev, **kw):
        results, stats = check.check_deals(deals, DATE, jev, self.hist, load=self.load, **kw)
        return results, stats


class FeedDeals(Base):
    def test_promotion_is_published_without_page_fetch(self):
        (r,), stats = self.run_check([feed_deal()], script(**{"p*": 0.95, "offer_kind": "promotion"}))
        self.assertEqual((r["decision"], r["reasons"]), ("publish", ["ok"]))
        self.assertEqual(stats["page_fetches"], 0)
        self.assertEqual(stats["stage_a_requests"], 1)

    def test_not_rpg_dropped_at_stage_a_and_stage_b_never_runs(self):
        jev = script(**{"p*": 0.05})
        (r,), stats = self.run_check([feed_deal(title="Space Fleet Dice Tray")], jev)
        self.assertEqual((r["decision"], r["stage"]), ("drop", "A"))
        self.assertEqual(stats["stage_b_requests"], 0)
        self.assertEqual(jev.usage["requests"], 1)

    def test_unsure_rpg_reads_the_page_and_the_page_decides(self):
        (r,), stats = self.run_check([feed_deal()], script(**{"p*": 0.5, "rpg": 0.9, "offer_kind": "clearance"}))
        self.assertEqual(r["decision"], "publish")
        self.assertEqual(stats["page_fetches"], 1)
        (r,), _ = self.run_check([feed_deal()], script(**{"p*": 0.5, "rpg": 0.1, "offer_kind": "clearance"}))
        self.assertEqual((r["decision"], r["reasons"][0].split(":")[0]), ("drop", "rpg_no"))
        (r,), _ = self.run_check([feed_deal()], script(**{"p*": 0.5, "rpg": 0.5, "offer_kind": "clearance"}))
        self.assertEqual((r["decision"], r["reasons"][0].split(":")[0]), ("needs_agent", "rpg_unsure"))

    def test_unsure_rpg_with_unreadable_page_goes_to_needs_agent(self):
        self.page_html = FetchError("blocked", "u")
        (r,), _ = self.run_check([feed_deal()], script(**{"p*": 0.5}))
        self.assertEqual((r["decision"], r["reasons"][0]), ("needs_agent", "page_unreadable: blocked"))

    def test_everyday_without_history_is_not_published(self):
        (r,), _ = self.run_check([feed_deal()], script(**{"p*": 0.95, "offer_kind": "everyday"}))
        self.assertEqual((r["decision"], r["reasons"][0].split(":")[0]), ("wait", "everyday_no_drop"))

    def test_everyday_without_history_can_be_sent_to_needs_agent(self):
        (r,), _ = self.run_check([feed_deal()], script(**{"p*": 0.95, "offer_kind": "everyday"}),
                                 T={**T, "everyday_no_history": "needs_agent"})
        self.assertEqual(r["decision"], "needs_agent")

    def test_everyday_with_a_real_drop_in_our_history_is_published(self):
        self.hist.record([feed_deal(price_now=30.0)], "2026-10-14")
        self.hist.record([feed_deal(price_now=30.0)], "2026-10-15")
        (r,), _ = self.run_check([feed_deal()], script(**{"p*": 0.95, "offer_kind": "everyday"}))
        self.assertEqual(r["decision"], "publish")
        self.assertTrue(r["check"]["history_drop"])

    def test_everyday_at_its_usual_price_is_not_a_drop(self):
        self.hist.record([feed_deal(price_now=15.0)], "2026-10-15")
        (r,), _ = self.run_check([feed_deal()], script(**{"p*": 0.95, "offer_kind": "everyday"}))
        self.assertEqual(r["decision"], "wait")

    def test_unclear_or_low_confidence_offer_goes_to_needs_agent(self):
        (r,), _ = self.run_check([feed_deal()], script(**{"p*": 0.95, "offer_kind": "unclear"}))
        self.assertEqual((r["decision"], r["reasons"]), ("needs_agent", ["offer_unclear"]))
        (r,), _ = self.run_check([feed_deal()], script(**{"p*": 0.95, "offer_kind": ("promotion", 0.4)}))
        self.assertEqual(r["decision"], "needs_agent")

    def test_ended_and_non_discount_are_dropped_by_code_without_jev(self):
        jev = script()
        rs, _ = self.run_check([feed_deal(ends="2026-10-16"), feed_deal(price_now=30.0)], jev)
        self.assertEqual([(r["decision"], r["stage"]) for r in rs], [("drop", "code")] * 2)
        self.assertEqual(jev.usage["requests"], 0)
        (r,), _ = self.run_check([feed_deal(ends=DATE)], script(**{"p*": 0.95, "offer_kind": "promotion"}))
        self.assertEqual(r["decision"], "publish")      # ends today is still on

    def test_jev_error_goes_to_needs_agent(self):
        def boom(qid, q, state):
            raise JevError("APIError status=500")
        (r,), _ = self.run_check([feed_deal()], FakeJev(forced=boom))
        self.assertEqual((r["decision"], r["stage"]), ("needs_agent", "A"))
        self.assertIn("jev_error", r["reasons"][0])

    def test_batches_of_twenty(self):
        deals = [feed_deal(url=f"https://shop.example/products/{i}") for i in range(45)]
        _, stats = self.run_check(deals, script(**{"p*": 0.95, "offer_kind": "promotion"}))
        self.assertEqual((stats["stage_a_requests"], stats["stage_b_requests"]), (3, 45))


class PublisherFeedDeals(Base):
    def test_publisher_sale_in_its_own_data_needs_no_stage_b_question(self):
        (r,), stats = self.run_check([feed_deal(shop_id="publisher")], script(**{"p*": 0.95}))
        self.assertEqual((r["decision"], r["reasons"]), ("publish", ["ok"]))
        self.assertEqual((stats["page_fetches"], stats["stage_b_requests"]), (0, 0))

    def test_publisher_deal_still_dropped_when_not_rpg(self):
        (r,), _ = self.run_check([feed_deal(shop_id="publisher")], script(**{"p*": 0.1}))
        self.assertEqual(r["decision"], "drop")


class SafetyRules(Base):
    def test_implausible_discount_goes_to_the_agent(self):
        (r,), _ = self.run_check([feed_deal(shop_id="publisher", price_now=5.0, price_was=500.0)],
                                 script(**{"p*": 0.95}))
        self.assertEqual(r["decision"], "needs_agent")
        self.assertTrue(r["reasons"][0].startswith("suspect_discount"))

    def test_free_from_shop_data_must_prove_it_is_limited(self):
        deal = feed_deal(shop_id="publisher", type="free", price_now=0.0, price_was=5.99)
        (r,), _ = self.run_check([deal], script(**{"p*": 0.95, "offer_kind": "everyday"}))
        self.assertNotEqual(r["decision"], "publish")


class PageDeals(Base):
    def answers(self, **kw):
        base = {"p*": 0.95, "support": "supports", "price_now_pick": "$24.00", "price_was_pick": "$30.00",
                "offer_kind": "promotion"}
        base.update(kw)
        return script(**base)

    def test_all_good_is_published(self):
        (r,), stats = self.run_check([page_deal()], self.answers())
        self.assertEqual((r["decision"], r["reasons"]), ("publish", ["ok"]))
        self.assertEqual(stats["page_fetches"], 1)

    def test_contradicts_is_dropped(self):
        (r,), _ = self.run_check([page_deal()], self.answers(support="contradicts"))
        self.assertEqual((r["decision"], r["reasons"][0].split(":")[0]), ("drop", "contradicted"))

    def test_weak_contradiction_goes_to_needs_agent(self):
        (r,), _ = self.run_check([page_deal()], self.answers(support=("contradicts", 0.6)))
        self.assertEqual(r["decision"], "needs_agent")

    def test_silent_or_unsure_support_goes_to_needs_agent(self):
        (r,), _ = self.run_check([page_deal()], self.answers(support="silent"))
        self.assertEqual(r["decision"], "needs_agent")
        (r,), _ = self.run_check([page_deal()], self.answers(support=("supports", 0.7)))
        self.assertEqual(r["decision"], "needs_agent")

    def test_pick_disagreeing_with_the_claim_is_dropped(self):
        (r,), _ = self.run_check([page_deal()], self.answers(price_now_pick="$30.00"))
        self.assertEqual((r["decision"], r["reasons"][0].split(":")[0]), ("drop", "pick_mismatch"))
        (r,), _ = self.run_check([page_deal()], self.answers(price_was_pick="$24.00"))
        self.assertEqual(r["decision"], "drop")

    def test_pick_none_is_not_a_drop_but_not_published(self):
        (r,), _ = self.run_check([page_deal()], self.answers(price_now_pick="none"))
        self.assertEqual((r["decision"], r["reasons"][0].split(":")[0]), ("needs_agent", "pick_none"))

    def test_claimed_price_not_on_page_is_not_published_even_if_jev_says_supports(self):
        (r,), _ = self.run_check([page_deal(price_now=4.0)], self.answers(price_now_pick="$24.00"))
        self.assertNotEqual(r["decision"], "publish")
        self.assertFalse(r["check"]["price_now_in_text"])

    def test_page_unreadable_goes_to_needs_agent(self):
        self.page_html = FetchError("dead", "u")
        (r,), _ = self.run_check([page_deal()], self.answers())
        self.assertEqual((r["decision"], r["reasons"][0]), ("needs_agent", "page_unreadable: dead"))

    def test_everyday_page_deal_also_needs_a_history_drop(self):
        (r,), _ = self.run_check([page_deal()], self.answers(offer_kind="everyday"))
        self.assertEqual(r["decision"], "wait")

    def test_page_questions_are_asked_only_for_page_deals(self):
        asked = []
        jev = FakeJev(forced=lambda qid, q, s: asked.append(qid))
        self.run_check([feed_deal(), page_deal()], jev)
        self.assertEqual(asked.count("support"), 1)
        self.assertEqual(asked.count("price_now_pick"), 1)
        self.assertEqual(asked.count("offer_kind"), 2)


class Fakes(Base):
    """The planted fakes through the real code with the keyword test double."""

    def load(self, deal):
        if deal["url"].startswith("fixture:"):
            return (TESTFIX / deal["url"].split(":", 1)[1]).read_text()
        html = {"CthulhuAwakens": "<h1>Cthulhu Awakens</h1><p>RPG bundle $12.95, normally $53.00</p>",
                "homeworld": "<h1>Homeworld Fleet Command: Dice Tray</h1><p>$13.00 <s>$13.00</s></p>",
                "blades": "<h1>Blades in the Dark</h1><p>RPG rulebook $20.00</p>"}
        return next(v for k, v in html.items() if k in deal["url"])

    def test_all_five_fakes_are_rejected(self):
        fakes = check.load_fakes(DATE)
        self.assertEqual(len(fakes), 5)
        results, _ = self.run_check(fakes, FakeJev())
        for f, r in zip(fakes, results):
            self.assertNotEqual(r["decision"], "publish", f["_fake"])
        by_kind = {f["_fake_kind"]: r for f, r in zip(fakes, results)}
        self.assertEqual(by_kind["not_rpg"]["stage"], "A")
        self.assertEqual(by_kind["prompt_injection"]["decision"], "drop")
        self.assertEqual(by_kind["expired"]["decision"], "drop")
        self.assertFalse(by_kind["prompt_injection"]["check"]["price_now_in_text"])


class Report(Base):
    def test_report_counts_and_fakes(self):
        deals = [feed_deal(), feed_deal(url="https://shop.example/products/b", title="Space Fleet Dice Tray", hints={}),
                 feed_deal(url="https://shop.example/products/c", ends="2026-01-01")]
        results, stats = self.run_check(deals, FakeJev())
        rep = check.build_report(DATE, "fake", deals, results, stats, FakeJev(), T)
        c = rep["counts"]
        self.assertEqual(c["deals_in"], 3)
        self.assertEqual(c["dropped_by_code"], 1)
        self.assertEqual(c["rpg_dropped_stage_a"], 1)
        self.assertEqual(c["published"] + c["needs_agent"] + c["wait"] + c["dropped_total"], 3)
        self.assertEqual(len(rep["deals"]), 3)


class SelectAndEstimate(Base):
    def test_select_limit_is_even_and_deterministic(self):
        raw = [feed_deal(url=f"https://shop.example/products/{i}") for i in range(100)]
        a = check.select(raw, "1999-01-01", 10)
        self.assertEqual(len(a), 10)
        self.assertEqual(a, check.select(raw, "1999-01-01", 10))
        self.assertEqual(len(check.select(raw, "1999-01-01", 0)), 100)

    def test_estimate_counts_requests(self):
        deals = [feed_deal(url=f"https://shop.example/products/{i}") for i in range(41)] + [page_deal()]
        e = check.estimate(deals, DATE, T, self.hist)
        self.assertEqual(e["stage_a_requests"], 3)
        self.assertEqual(e["stage_b_requests"], 42)
        self.assertEqual(e["page_fetches_certain"], 1)
        self.assertGreater(e["input_tokens_estimate"], 0)


if __name__ == "__main__":
    unittest.main()
