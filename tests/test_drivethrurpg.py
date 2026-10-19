import copy
import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scraper import check, missed, score
from scraper.common import FetchError, drivethru_product_id, fetch
from scraper.history import History
from scraper.readers import drivethrurpg as dt

FIX = pathlib.Path(__file__).parent / "fixtures" / "drivethrurpg"
PAGE = json.loads((FIX / "products_onsale_page1.json").read_text())
SHOP = {"id": "drivethrurpg", "name": "DriveThruRPG", "store_url": "https://api.drivethrurpg.com/",
        "platform": "drivethrurpg", "status": "active", "currency": "USD", "recipe": {}, "everyday_discounts": True}
DATE = "2026-10-17"


def item(pid):
    return copy.deepcopy(next(x for x in PAGE["data"] if x["attributes"]["productId"] == pid))


def deals_by_id():
    pubs = dt._publishers(PAGE)
    out = {}
    for x in PAGE["data"]:
        d = dt.parse_product(SHOP, x, pubs)
        if d:
            out[x["attributes"]["productId"]] = d
    return out


class OptionPick(unittest.TestCase):
    def test_biggest_percent_discount_wins(self):
        # 81232: PDF 1.20 vs 9.95 (88% off) and softcover 16 vs 22 (27% off)
        opt, now, was = dt.pick_option(item(81232)["attributes"]["options"])
        self.assertEqual((opt["optionValueName"], now, was), ("PDF", 1.2, 9.95))

    def test_option_without_msrp_is_not_a_discount(self):
        # 15815: watermarked PDF 4.50 vs "8.9900"; the softcover has msrp 0 (unknown)
        opt, now, was = dt.pick_option(item(15815)["attributes"]["options"])
        self.assertEqual((opt["optionValueName"], now, was), ("Watermarked PDF", 4.5, 8.99))
        self.assertIsNone(dt.pick_option([{"price": 19.99, "msrp": 0, "type": "book"}]))

    def test_msrp_string_parsing(self):
        self.assertEqual(dt.option_discount({"price": 3.96, "msrp": "4.9500"})[:2], (3.96, 4.95))
        self.assertIsNone(dt.option_discount({"price": 3.96, "msrp": "3.9600"}))     # equal: no deal
        self.assertIsNone(dt.option_discount({"price": 3.96, "msrp": None}))
        self.assertIsNone(dt.option_discount({"price": 3.96, "msrp": "abc"}))
        self.assertIsNone(dt.option_discount({"price": 5, "msrp": "4.0000"}))        # price went up

    def test_same_percent_goes_to_the_lower_price(self):
        opts = [{"price": 10, "msrp": "20", "type": "book", "optionValueName": "Print"},
                {"price": 5, "msrp": "10", "type": "digital", "optionValueName": "PDF"}]
        self.assertEqual(dt.pick_option(opts)[0]["optionValueName"], "PDF")


class Deals(unittest.TestCase):
    def test_fixture_deal(self):
        d = deals_by_id()[2013]
        self.assertEqual((d["type"], d["price_now"], d["price_was"], d["discount_pct"], d["currency"]),
                         ("sale", 3.96, 4.95, 20, "USD"))
        self.assertEqual(d["source"], "drivethrurpg-api")
        self.assertEqual(d["hints"]["vendor"], "Battlefield Press")
        self.assertEqual(d["hints"]["option"], "Watermarked PDF")
        self.assertEqual(d["hints"]["product_id"], 2013)
        self.assertEqual(d["hints"]["image"], "https://d1vzi28wh99zvq.cloudfront.net/images/62/2013.jpg")
        self.assertFalse(d["hints"]["is_ai"])
        self.assertIsNone(d["hints"]["date_available"])                # 1969-12-31 means "never set"
        self.assertLessEqual(len(d["hints"]["description"]), 300)

    def test_url_is_the_sites_own_product_form(self):
        d = deals_by_id()[2013]
        self.assertEqual(d["url"], "https://www.drivethrurpg.com/product/2013/"
                                   "eric-flint-s-1632-resource-guide-and-role-playing-game-flaws-and-all-edition")
        self.assertEqual(dt.product_url(5, None), "https://www.drivethrurpg.com/product/5")

    def test_print_option_is_physical(self):
        x = item(81232)
        x["attributes"]["options"] = [o for o in x["attributes"]["options"] if o["type"] != "digital"]
        d = dt.parse_product(SHOP, x)
        self.assertEqual((d["type"], d["price_now"], d["price_was"]), ("physical", 16, 22))

    def test_free_when_price_zero_and_msrp_above_zero(self):
        x = item(2013)
        x["attributes"]["options"][0].update(price=0, msrp="4.9500")
        self.assertEqual(dt.parse_product(SHOP, x)["type"], "free")

    def test_always_free_item_is_no_deal(self):
        self.assertNotIn(79842, deals_by_id())       # price 0, msrp 0

    def test_pwyw_is_skipped(self):
        x = item(2013)
        self.assertIsNotNone(dt.parse_product(SHOP, x))
        x["attributes"]["isPwyw"] = True
        self.assertIsNone(dt.parse_product(SHOP, x))

    def test_flags_are_hints(self):
        x = item(2013)
        x["attributes"].update(isCommunityContent=True, isAi=True, isBundle=True, promoText=" 20% off ",
                               dateAvailable="2026-03-01T00:00:00-06:00")
        h = dt.parse_product(SHOP, x)["hints"]
        self.assertEqual((h["is_community_content"], h["is_ai"], h["is_bundle"], h["promo_text"], h["date_available"]),
                         (True, True, True, "20% off", "2026-03-01"))


class Paging(unittest.TestCase):
    def pages(self, n_full, last_next=True):
        base = PAGE["data"][:2]

        def make(page, empty=False):
            data = [] if empty else [copy.deepcopy(base[i]) for i in range(2)]
            for i, x in enumerate(data):       # distinct ids per page
                x["attributes"]["productId"] = page * 100 + i
            nxt = {"next": f"/api/vBeta/products?onSale=1&pageSize=50&page={page + 1}"} if (last_next or not empty) else {}
            return {"links": nxt, "data": data, "included": PAGE["included"]}
        return make

    def test_stops_on_empty_page_and_follows_next(self):
        make = self.pages(3)
        urls = []

        def fake(url):
            urls.append(url)
            page = int(url.rsplit("page=", 1)[1])
            return make(page, empty=page > 3)
        with mock.patch.object(dt, "fetch_json", fake):
            deals, stats = dt.read_with_stats(SHOP)
        self.assertEqual(stats["pages"], 3)
        self.assertEqual(stats["items_read"], 6)
        self.assertEqual(len(deals), 6)
        self.assertEqual(len(urls), 4)                        # the 4th (empty) page ended it
        self.assertTrue(all(u.startswith("https://api.drivethrurpg.com/") for u in urls))

    def test_short_page_does_not_end_the_read(self):
        make = self.pages(3)

        def fake(url):
            page = int(url.rsplit("page=", 1)[1])
            r = make(page, empty=page > 2)
            if page == 1:
                r["data"] = r["data"][:1]                     # a short page in the middle
            return r
        with mock.patch.object(dt, "fetch_json", fake):
            _, stats = dt.read_with_stats(SHOP)
        self.assertEqual((stats["pages"], stats["items_read"]), (2, 3))

    def test_page_cap(self):
        make = self.pages(1)
        with mock.patch.object(dt, "fetch_json", lambda url: make(int(url.rsplit("page=", 1)[1]))), \
                mock.patch.object(dt, "MAX_PAGES", 5):
            _, stats = dt.read_with_stats(SHOP)
        self.assertEqual(stats["pages"], 5)
        self.assertIn("5-page safety limit", stats["stopped_early"])

    def test_never_follows_a_link_to_another_host(self):
        calls = []

        def fake(url):
            calls.append(url)
            r = copy.deepcopy(PAGE)
            r["links"] = {"next": "https://www.drivethrurpg.com/evil"}
            return r
        with mock.patch.object(dt, "fetch_json", fake):
            dt.read_with_stats(SHOP)
        self.assertEqual(len(calls), 1)

    def test_first_page_failure_raises_later_failure_keeps_what_was_read(self):
        with mock.patch.object(dt, "fetch_json", side_effect=FetchError("blocked", "u")):
            with self.assertRaises(FetchError):
                dt.read_with_stats(SHOP)
        make = self.pages(2)

        def fake(url):
            page = int(url.rsplit("page=", 1)[1])
            if page == 2:
                raise FetchError("error", url)
            return make(page)
        with mock.patch.object(dt, "fetch_json", fake):
            deals, stats = dt.read_with_stats(SHOP)
        self.assertEqual((stats["pages"], len(deals)), (1, 2))


class SisterDomain(unittest.TestCase):
    def test_product_id_from_links(self):
        for u in ("https://www.drivethrurpg.com/product/584963/root?affiliate_id=36142",
                  "https://www.drivethrurpg.com/en/product/584963/other-slug",
                  "https://drivethrurpg.com/product/584963"):
            self.assertEqual(drivethru_product_id(u), 584963, u)
        for u in ("https://api.drivethrurpg.com/api/vBeta/products/584963", "https://www.drivethrurpg.com/browse",
                  "https://www.drivethrurpg.com/product/abc", "https://example.com/product/584963/x"):
            self.assertIsNone(drivethru_product_id(u), u)

    def test_lead_matches_run_deal_by_product_id(self):
        deal = deals_by_id()[2013]
        raw = [dict(deal, shop_id="drivethrurpg")]
        lead = {"url": "https://www.drivethrurpg.com/product/2013/a-different-slug?affiliate_id=1",
                "link_text": "1632", "feed": "enworld", "class": "known_shop", "shop_id": "drivethrurpg"}
        by_key, by_host = missed.index_raw(raw)
        self.assertIs(missed.in_raw(lead, by_key, by_host), raw[0])
        other = dict(lead, url="https://www.drivethrurpg.com/en/product/9999/whatever")
        self.assertIsNone(missed.in_raw(other, by_key, by_host))

    def test_alias_host_and_shop_lookup(self):
        self.assertEqual(score.host("https://api.drivethrurpg.com/"), score.host("https://www.drivethrurpg.com/product/1/x"))
        self.assertIs(score.shop_for("https://www.drivethrurpg.com/product/1/x", [SHOP]), SHOP)

    def test_lead_for_unmatched_product_is_not_fetched(self):
        lead = {"url": "https://www.drivethrurpg.com/product/9999/not-on-sale", "link_text": "X", "feed": "enworld",
                "post_title": "p", "post_url": "u", "published": DATE, "class": "known_shop", "shop_id": "drivethrurpg"}
        misses, matched = missed.triage([lead], [SHOP], [], [{"id": "drivethrurpg", "status": "ok"}])
        self.assertEqual(matched, 0)
        self.assertEqual(misses[0]["reason"], "not_on_sale_anymore")        # decided without any page fetch

    def test_classify_treats_www_links_as_this_shop(self):
        from scraper import discover
        cls, shop = discover.classify("https://www.drivethrurpg.com/product/2013/x", [SHOP])
        self.assertEqual((cls, shop["id"]), ("known_shop", "drivethrurpg"))


class NeverFetchWww(unittest.TestCase):
    def test_fetch_refuses_the_website(self):
        for u in ("https://www.drivethrurpg.com/product/1/x", "https://drivethrurpg.com/"):
            with self.assertRaises(FetchError) as cm:
                fetch(u)
            self.assertEqual(cm.exception.kind, "blocked")


class LeadCountsAsFirstDayDrop(unittest.TestCase):
    def setUp(self):
        self.hist = History(tempfile.mkdtemp())
        check._everyday_shops = {"drivethrurpg"}
        self.deal = dict(deals_by_id()[2013])
        self.deal["shop_id"] = "drivethrurpg"

    def tearDown(self):
        check._everyday_shops = None

    def run_check(self, leads):
        from tests.test_check import script
        (r,), _ = check.check_deals([self.deal], DATE, script(**{"p*": 0.95, "offer_kind": "everyday"}), self.hist,
                                    leads=leads)
        return r

    def test_without_a_lead_the_first_day_waits(self):
        self.assertEqual(self.run_check({})["decision"], "wait")

    def test_with_a_trusted_lead_the_first_day_publishes(self):
        key = check.lead_key("https://www.drivethrurpg.com/product/2013/other-slug?affiliate_id=1")
        r = self.run_check({key: "https://www.drivethrurpg.com/product/2013/other-slug"})
        self.assertEqual(r["decision"], "publish")
        self.assertIn("lead_drop", r["check"])

    def test_lead_for_another_product_does_not_help(self):
        key = check.lead_key("https://www.drivethrurpg.com/product/777/x")
        self.assertEqual(self.run_check({key: "u"})["decision"], "wait")

    def test_lead_does_not_replace_history_after_day_one(self):
        self.hist.record([dict(self.deal, price_now=3.96)], "2026-10-15")
        key = check.lead_key(self.deal["url"])
        self.assertEqual(self.run_check({key: "u"})["decision"], "wait")      # seen before, no drop

    def test_load_trusted_leads_only_takes_trusted_feeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp)
            (p / f"leads-{DATE}.json").write_text(json.dumps({"leads": [
                {"url": "https://www.drivethrurpg.com/product/2013/a", "feed": "enworld"},
                {"url": "https://www.drivethrurpg.com/product/55/b", "feed": "somewhere-else"}]}))
            with mock.patch.object(check, "REPORTS", p):
                got = check.load_trusted_leads(DATE)
        self.assertEqual(list(got), ["drivethrurpg:2013"])


if __name__ == "__main__":
    unittest.main()
