import json
import pathlib
import unittest
from unittest import mock

from scraper import score
from scraper.common import is_discount, make_deal, money, norm_url
from scraper.detect import merge, shopify_currency
from scraper.readers import shopify, woocommerce

FIX = pathlib.Path(__file__).parent / "fixtures"
SHOP_S = {"id": "modiphius", "name": "Modiphius Entertainment", "store_url": "https://modiphius.net/",
          "platform": "shopify", "currency": "GBP", "recipe": {}}
SHOP_W = {"id": "evil-hat", "name": "Evil Hat Productions", "store_url": "https://evilhat.com/",
          "platform": "woocommerce", "currency": "USD", "recipe": {"api_base": "https://evilhat.com/wp-json/wc/store/v1"}}


def variant(price, was, title="Default Title", ships=True):
    return {"title": title, "price": price, "compare_at_price": was, "requires_shipping": ships}


def product(*variants, **extra):
    return {"id": 1, "title": "Thing", "handle": "thing", "vendor": "V", "product_type": "Book",
            "tags": ["a"], "variants": list(variants), **extra}


class IsDiscount(unittest.TestCase):
    def test_cases(self):
        self.assertTrue(is_discount(5.0, 10.0))
        self.assertFalse(is_discount(10.0, 10.0))      # equal prices
        self.assertFalse(is_discount(10.0, None))      # no was-price
        self.assertFalse(is_discount(None, 10.0))
        self.assertFalse(is_discount(12.0, 10.0))      # price went up
        self.assertTrue(is_discount(0.0, 5.0))         # free is a discount

    def test_zero_percent_off_is_no_deal(self):
        deal = shopify.parse_product(SHOP_S, product(variant("9.99", "9.99")))
        self.assertIsNone(deal)

    def test_money(self):
        self.assertEqual(money("12.50"), 12.5)
        self.assertEqual(money(1250, 2), 12.5)
        self.assertEqual(money("1000", 2), 10.0)
        self.assertEqual(money("1000", 0), 1000.0)
        self.assertIsNone(money(None))
        self.assertIsNone(money(""))
        self.assertIsNone(money("abc"))


class ShopifyParsing(unittest.TestCase):
    def test_fixture(self):
        products = json.loads((FIX / "shopify_products.json").read_text())["products"]
        deals = [shopify.parse_product(SHOP_S, p) for p in products]
        got = [d for d in deals if d]
        self.assertEqual(len(got), 2)                  # last fixture product has no compare_at_price
        self.assertIsNone(deals[-1])
        d = got[0]
        self.assertEqual((d["price_now"], d["price_was"], d["discount_pct"]), (9.95, 36.95, 73))
        self.assertEqual(d["type"], "physical")
        self.assertEqual(d["currency"], "GBP")
        self.assertEqual(d["url"], "https://modiphius.net/products/" + products[0]["handle"])
        self.assertEqual(d["source"], "shopify-api")
        self.assertIn("Fallout: Miniatures", d["hints"]["tags"])
        self.assertIsNone(d["hints"]["variant"])       # "Default Title" is not a variant name

    def test_variant_pick_lowest_price_among_discounted(self):
        p = product(variant("60.00", "75.00", "Hardcover"), variant("48.00", "60.00", "PDF", ships=False),
                    variant("30.00", None, "Cheap but no was-price"))
        d = shopify.parse_product(SHOP_S, p)
        self.assertEqual((d["price_now"], d["price_was"]), (48.0, 60.0))
        self.assertEqual(d["hints"]["variant"], "PDF")
        self.assertEqual(d["type"], "sale")            # digital variant: does not ship

    def test_free(self):
        d = shopify.parse_product(SHOP_S, product(variant("0.00", "5.00", ships=False)))
        self.assertEqual(d["type"], "free")

    def test_no_compare_at(self):
        self.assertIsNone(shopify.parse_product(SHOP_S, product(variant("5.00", None))))

    def test_feed_urls(self):
        self.assertEqual(shopify.feed_urls(SHOP_S), ["https://modiphius.net/products.json"])
        col = {**SHOP_S, "recipe": {"collections": ["warehouse-clearance-sale"]}}
        self.assertEqual(shopify.feed_urls(col),
                         ["https://modiphius.net/collections/warehouse-clearance-sale/products.json"])

    def test_paging_stops_only_on_empty_page(self):
        pages = {1: [product(variant("5", "10"), id=1)], 2: [product(variant("5", "10"), id=2)], 3: []}
        urls = []

        def fake(url):
            urls.append(url)
            return {"products": pages[int(url.rsplit("page=", 1)[1])]}
        with mock.patch.object(shopify, "fetch_json", fake):
            deals, stats = shopify.read_with_stats(SHOP_S)
        self.assertEqual(len(deals), 2)                # page 1 was short (1 < 250) but we went on
        self.assertEqual(stats["items_read"], 2)
        self.assertEqual(len(urls), 3)


class WooParsing(unittest.TestCase):
    def setUp(self):
        self.items = json.loads((FIX / "woocommerce_products.json").read_text())

    def test_minor_units_and_currency(self):
        deal, variant_only = woocommerce.parse_product(SHOP_W, self.items[0])
        self.assertFalse(variant_only)
        self.assertEqual((deal["price_now"], deal["price_was"]), (10.0, 12.0))
        self.assertEqual(deal["currency"], "USD")
        self.assertEqual(deal["url"], self.items[0]["permalink"])
        self.assertEqual(deal["source"], "woocommerce-api")

    def test_minor_unit_zero_decimals(self):
        p = json.loads(json.dumps(self.items[0]))
        p["prices"].update(price="1000", regular_price="1500", currency_minor_unit=0, currency_code="JPY")
        deal, _ = woocommerce.parse_product(SHOP_W, p)
        self.assertEqual((deal["price_now"], deal["price_was"], deal["currency"]), (1000.0, 1500.0, "JPY"))

    def test_variable_equal_prices_counted_not_recorded(self):
        deal, variant_only = woocommerce.parse_product(SHOP_W, self.items[2])
        self.assertIsNone(deal)
        self.assertTrue(variant_only)

    def test_bundle_type_guess(self):
        deal, _ = woocommerce.parse_product(SHOP_W, self.items[3])
        self.assertEqual(deal["type"], "bundle")
        self.assertTrue(deal["hints"]["type_guess"])

    def test_read_counts_skipped(self):
        pages = {1: self.items, 2: []}
        with mock.patch.object(woocommerce, "fetch_json",
                               lambda url: pages[int(url.rsplit("page=", 1)[1])]):
            deals, stats = woocommerce.read_with_stats(SHOP_W)
        self.assertEqual(len(deals), 3)
        self.assertEqual(stats["skipped_variant_only"], 1)
        self.assertEqual(stats["items_read"], 4)


class Helpers(unittest.TestCase):
    def test_norm_url(self):
        self.assertEqual(norm_url("https://www.Modiphius.net/products/x/?a=1"), "modiphius.net/products/x")

    def test_shopify_currency(self):
        self.assertEqual(shopify_currency('Shopify.currency = {"active":"GBP","rate":"1.0"};'), "GBP")
        self.assertIsNone(shopify_currency("<html></html>"))

    def test_merge_dedupes_by_host_and_keeps_recipe(self):
        have = [{"id": "a", "store_url": "https://www.a.com/", "recipe": {"collections": ["x"]}}]
        added = merge(have, [{"id": "a2", "store_url": "https://a.com/", "recipe": {}},
                             {"id": "b", "store_url": "https://b.com/", "recipe": {}}])
        self.assertEqual([e["id"] for e in added], ["b"])
        self.assertEqual(have[0]["recipe"], {"collections": ["x"]})

    def test_make_deal_rejects_bad_type(self):
        with self.assertRaises(AssertionError):
            make_deal(shop=SHOP_S, type="nope", title="t", url="u", price_now=1, price_was=2,
                      currency="GBP", source="s", found_via="f")


class Score(unittest.TestCase):
    def test_match_by_title_words_across_sister_domains(self):
        t = {"url": "https://modiphius.net/products/x", "title": "Star Trek Adventures Player's Guide"}
        d = {"url": "https://modiphius.us/products/y", "title": "Star Trek Adventures - Players Guide (PDF)"}
        self.assertTrue(score.matches(t, d))
        d["title"] = "Star Trek Adventures Core"
        self.assertFalse(score.matches(t, d))


if __name__ == "__main__":
    unittest.main()
