import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scraper import missed
from scraper.common import FetchError, is_discount

DATE = "2026-10-17"
SHOPS = [
    {"id": "modiphius", "name": "Modiphius", "store_url": "https://modiphius.net/", "platform": "shopify",
     "status": "active", "currency": "GBP"},
    {"id": "atlas", "name": "Atlas Games", "store_url": "https://shop.atlas-games.com/", "platform": "shopify",
     "status": "active", "currency": "USD"},
    {"id": "paused", "name": "Paused Shop", "store_url": "https://paused.example.com/", "platform": "generic",
     "status": "active", "currency": "USD", "recipe": {"price_now": ".now"}},
    {"id": "drivethrurpg", "name": "DriveThruRPG", "store_url": "https://www.drivethrurpg.com/", "platform": "unknown",
     "status": "blocked"},
]
ROWS = [{"id": "modiphius", "status": "ok"}, {"id": "atlas", "status": "ok"}, {"id": "paused", "status": "error"}]
RAW = [
    {"url": "https://modiphius.net/products/dune-core-rulebook", "title": "Dune Core Rulebook", "shop_id": "modiphius", "source": "shopify-api"},
    {"url": "https://shop.atlas-games.com/products/ag0317-mythic-europe-fabric-map", "title": "AG0317 Mythic Europe Fabric Map", "shop_id": "atlas", "source": "shopify-api"},
]


def lead(url, text="", shop_id=None, cls="known_shop"):
    return {"url": url, "link_text": text, "post_title": "Weekly sales", "post_url": "https://x/post", "feed": "enworld",
            "published": "2026-10-16", "class": cls, "shop_id": shop_id}


def info(now, was, title="Some Product", cur="USD"):
    return {"title": title, "price_now": now, "price_was": was, "currency": cur, "ends": None, "source": "jsonld", "hints": {}}


class Recognise(unittest.TestCase):
    def test_product_pages(self):
        for u in ("https://modiphius.net/products/x", "https://modiphius.us/collections/sale/products/x",
                  "https://bundleofholding.com/presents/BlueFox", "https://dev.itch.io/some-game",
                  "https://www.drivethrurpg.com/product/584963/root", "https://shop.example.com/p/thing-1"):
            self.assertTrue(missed.looks_like_product(u), u)
        for u in ("https://modiphius.us/collections/warehouse-clearance-sale", "https://modiphius.net/",
                  "https://shop.example.com/blogs/news/50-sale", "https://itch.io/", "https://dev.itch.io/"):
            self.assertFalse(missed.looks_like_product(u), u)

    def test_match_key_ignores_collection_www_and_sister_domain(self):
        a = missed.match_key("https://www.modiphius.us/collections/sale/products/dune-core-rulebook")
        b = missed.match_key("https://modiphius.net/products/dune-core-rulebook?variant=1")
        self.assertEqual(a, b)


class Triage(unittest.TestCase):
    def go(self, leads):
        return missed.triage(leads, SHOPS, RAW, ROWS)

    def test_same_url_is_found(self):
        misses, matched = self.go([lead("https://modiphius.net/products/dune-core-rulebook", "Dune", "modiphius")])
        self.assertEqual((misses, matched), ([], 1))

    def test_same_shop_and_title_words_is_found(self):
        misses, matched = self.go([lead("https://shop.atlas-games.com/products/some-other-slug", "Mythic Europe Fabric Map", "atlas")])
        self.assertEqual((misses, matched), ([], 1))

    def test_not_found_is_a_miss_with_early_reasons(self):
        misses, matched = self.go([
            lead("https://www.drivethrurpg.com/product/1/x", "x", "drivethrurpg", "blocked_shop"),
            lead("https://modiphius.us/collections/sale", "sale", "modiphius"),
            lead("https://modiphius.net/products/something-new", "Something New", "modiphius"),
            lead("https://enpublishingrpg.com/x", "x", None, "new_shop"),            # unknown site: ignored
        ])
        self.assertEqual(matched, 0)
        self.assertEqual([(m["reason"]) for m in misses], ["shop_blocked", "not_a_product_page", None])

    def test_seller_leads_from_news_are_not_misses(self):
        news = dict(lead("https://modiphius.net/products/something-new", "Something New", "modiphius"), purpose="sellers")
        self.assertEqual(self.go([news]), ([], 0))


class Pages(unittest.TestCase):
    def read(self, leads, page_info, **kw):
        misses, _ = missed.triage(leads, SHOPS, RAW, ROWS)
        return misses, missed.read_pages(misses, SHOPS, page_info, None, **kw)

    def test_real_discount_becomes_a_candidate_deal(self):
        misses, cands = self.read([lead("https://modiphius.net/products/new-thing", "New Thing", "modiphius")],
                                  lambda url, shop: info(10.0, 20.0, "New Thing (PDF)", "GBP"))
        self.assertEqual(misses[0]["reason"], "reader_gap")
        self.assertTrue(misses[0]["candidate"])
        c = cands[0]
        self.assertEqual((c["source"], c["price_now"], c["price_was"], c["shop_id"]), ("lead", 10.0, 20.0, "modiphius"))
        self.assertTrue(is_discount(c["price_now"], c["price_was"]))
        self.assertEqual(c["hints"]["lead"]["feed"], "enworld")
        self.assertIn(c["type"], ("sale", "physical", "free", "bundle"))

    def test_shop_not_read_today_is_a_candidate_too(self):
        misses, cands = self.read([lead("https://paused.example.com/products/a-thing", "A Thing", "paused")],
                                  lambda url, shop: info(5.0, 9.0))
        self.assertEqual(misses[0]["reason"], "shop_not_read_today")
        self.assertEqual(len(cands), 1)

    def test_no_discount_is_logged_and_never_invented(self):
        for page in (info(20.0, None), info(20.0, 20.0)):
            misses, cands = self.read([lead("https://modiphius.net/products/new-thing", "New Thing", "modiphius")],
                                      lambda url, shop, p=page: p)
            self.assertEqual(misses[0]["reason"], "not_on_sale_anymore")
            self.assertEqual(cands, [])

    def test_unreadable_pages(self):
        def boom(url, shop):
            raise FetchError("dead", url, "HTTP 404")
        misses, cands = self.read([lead("https://modiphius.net/products/gone", "Gone", "modiphius")], boom)
        self.assertEqual((misses[0]["reason"], cands), ("page_unreadable", []))
        misses, cands = self.read([lead("https://modiphius.net/products/gone", "Gone", "modiphius")], lambda u, s: None)
        self.assertEqual(misses[0]["reason"], "page_unreadable")

    def test_the_shop_is_passed_to_the_page_reader(self):
        seen = []
        self.read([lead("https://paused.example.com/products/a-thing", "A Thing", "paused")],
                  lambda url, shop: seen.append(shop["id"]) or None)
        self.assertEqual(seen, ["paused"])

    def test_fetch_cap(self):
        leads = [lead(f"https://modiphius.net/products/new-{i}", f"New {i}", "modiphius") for i in range(5)]
        misses, cands = self.read(leads, lambda u, s: info(1.0, 2.0), max_fetches=2)
        self.assertEqual(sorted(m["reason"] for m in misses), ["fetch_cap"] * 3 + ["reader_gap"] * 2)
        self.assertEqual(len(cands), 2)


class LeadPage(unittest.TestCase):
    PRODUCT = {"title": "Mythic Map", "product_type": "Maps", "tags": ["ars"], "vendor": "Atlas",
               "variants": [{"title": "Default Title", "price": "17.48", "compare_at_price": "34.95", "requires_shipping": True}]}

    def test_shopify_product_json_gives_the_shops_own_prices(self):
        with mock.patch.object(missed, "fetch_json", lambda u: {"product": self.PRODUCT}) as fj, \
                mock.patch.object(missed.generic, "page_prices", side_effect=AssertionError("page must not be read")):
            info = missed.read_lead_page("https://shop.atlas-games.com/collections/x/products/mythic-map?v=1", SHOPS[1])
        self.assertEqual((info["price_now"], info["price_was"], info["currency"]), (17.48, 34.95, "USD"))
        c = missed.make_candidate(SHOPS[1], lead("https://shop.atlas-games.com/products/mythic-map", "", "atlas"), info)
        self.assertEqual((c["type"], c["source"], c["hints"]["read_via"]), ("physical", "lead", "shopify-product-json"))

    def test_shopify_json_url_is_the_products_path(self):
        urls = []
        with mock.patch.object(missed, "fetch_json", lambda u: urls.append(u) or {"product": self.PRODUCT}):
            missed.read_lead_page("https://shop.atlas-games.com/collections/x/products/mythic-map?v=1", SHOPS[1])
        self.assertEqual(urls, ["https://shop.atlas-games.com/products/mythic-map.json"])

    def test_no_discounted_variant_falls_back_to_the_page(self):
        flat = {**self.PRODUCT, "variants": [{"title": "Default Title", "price": "17.48", "compare_at_price": None}]}
        with mock.patch.object(missed, "fetch_json", lambda u: {"product": flat}), \
                mock.patch.object(missed.generic, "page_prices", lambda u, r: "page") as pp:
            self.assertEqual(missed.read_lead_page("https://shop.atlas-games.com/products/x", SHOPS[1]), "page")
        with mock.patch.object(missed, "fetch_json", side_effect=FetchError("dead", "u")), \
                mock.patch.object(missed.generic, "page_prices", lambda u, r: "page"):
            self.assertEqual(missed.read_lead_page("https://shop.atlas-games.com/products/x", SHOPS[1]), "page")

    def test_other_platforms_use_the_generic_page_reader_with_the_recipe(self):
        with mock.patch.object(missed.generic, "page_prices", lambda u, r: ("page", r)):
            self.assertEqual(missed.read_lead_page("https://paused.example.com/products/x", SHOPS[2]),
                             ("page", {"price_now": ".now"}))


class Run(unittest.TestCase):
    def test_candidates_are_appended_to_the_raw_file_once(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        raw_dir = tmp / "raw"
        raw_dir.mkdir()
        (raw_dir / f"{DATE}-scraper.json").write_text(json.dumps(RAW))
        leads_doc = {"leads": [lead("https://modiphius.net/products/new-thing", "New Thing", "modiphius"),
                               lead("https://www.drivethrurpg.com/product/1/x", "x", "drivethrurpg", "blocked_shop")]}
        with mock.patch.object(missed, "DEALS", tmp), mock.patch.object(missed, "RAW", raw_dir):
            for _ in range(2):                                   # a second run must not duplicate
                doc = missed.run(DATE, leads_doc, shops=SHOPS, scrape_rows=ROWS, page_info=lambda u, s: info(10.0, 20.0))
        raw = json.loads((raw_dir / f"{DATE}-scraper.json").read_text())
        self.assertEqual([d["source"] for d in raw], ["shopify-api", "shopify-api", "lead"])
        written = json.loads((tmp / f"missed-{DATE}.json").read_text())
        self.assertEqual(written["counts"]["misses"], 2)
        self.assertEqual(written["counts"]["candidates"], 1)
        self.assertEqual(written["counts"]["by_reason"], {"shop_blocked": 1, "reader_gap": 1})


if __name__ == "__main__":
    unittest.main()
