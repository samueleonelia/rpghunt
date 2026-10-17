import datetime
import pathlib
import unittest
from unittest import mock

from scrapling.parser import Selector

from scraper.readers import generic, shopify

FIX = pathlib.Path(__file__).parent / "fixtures" / "generic"
ROOT = pathlib.Path(__file__).resolve().parent.parent


def page(name, **subs):
    html = (FIX / name).read_text()
    for k, v in subs.items():
        html = html.replace(f"%{k}%", v)
    return generic.parse_page(html, "https://shop.example/p/x")


class PageParsing(unittest.TestCase):
    def test_jsonld_offer_with_list_price(self):
        soon = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
        r = page("jsonld.html", DATE_SOON=soon)
        self.assertEqual((r["price_now"], r["price_was"], r["currency"]), (24.0, 30.0, "USD"))
        self.assertEqual((r["source"], r["ends"]), ("jsonld", soon))
        self.assertEqual(r["title"], "Ember Hollow Core Book")

    def test_woocommerce_del(self):
        r = page("woo_del.html")
        self.assertEqual((r["price_now"], r["price_was"]), (28.0, 40.0))   # not the related-products block
        self.assertEqual(r["source"], "page-markup")

    def test_bigcommerce_non_sale(self):
        r = page("bigcommerce.html")
        self.assertEqual((r["price_now"], r["price_was"]), (15.0, 20.0))   # hidden $99 with-tax ignored

    def test_shopify_theme_regular_and_sale_price(self):
        r = page("shopify_theme.html")
        self.assertEqual((r["price_now"], r["price_was"]), (24.0, 30.0))

    def test_hidden_fake_price_is_ignored(self):
        r = page("hidden_fake.html")
        self.assertIsNotNone(r)
        self.assertIsNone(r["price_was"])
        self.assertFalse(generic.is_discount(r["price_now"], r["price_was"]))

    def test_far_future_valid_until_is_not_an_end_date(self):
        r = page("far_future.html")
        self.assertIsNone(r["ends"])
        self.assertIn("default", r["hints"]["ends"])
        self.assertEqual((r["price_now"], r["price_was"]), (20.0, 25.0))

    def test_sale_end_window(self):
        today = datetime.date(2026, 10, 17)
        self.assertEqual(generic.sale_end("2026-11-01T00:00:00Z", today)[0], "2026-11-01")
        self.assertIsNone(generic.sale_end("2027-12-31", today)[0])
        self.assertIsNone(generic.sale_end("2026-01-01", today)[0])

    def test_injected_shop_fixture(self):
        html = (ROOT / "data" / "testset" / "fixtures" / "injected-shop.html").read_text()
        r = generic.parse_page(html, "https://lantern.example/p/starfall")
        self.assertEqual(r["price_now"], 40.0)
        self.assertFalse(generic.is_discount(r["price_now"], r["price_was"]))

    def test_recipe_selectors_override(self):
        html = '<html><body><span id="n">$9.00</span><span id="w">$12.00</span><s>$99.00</s></body></html>'
        r = generic.parse_page(html, "", {"price_now": "#n", "price_was": "#w"})
        self.assertEqual((r["price_now"], r["price_was"], r["source"]), (9.0, 12.0, "recipe"))

    def test_no_price_at_all(self):
        self.assertIsNone(generic.parse_page("<html><body><h1>Hi</h1></body></html>"))


class Helpers(unittest.TestCase):
    def test_parse_amount(self):
        self.assertEqual(generic.parse_amount("$1,299.00"), 1299.0)
        self.assertEqual(generic.parse_amount("12,50 EUR"), 12.5)
        self.assertEqual(generic.parse_amount("1.234,56"), 1234.56)
        self.assertEqual(generic.parse_amount("Free"), 0.0)
        self.assertIsNone(generic.parse_amount("Sold out"))

    def test_product_links_and_next(self):
        sel = Selector((FIX / "listing.html").read_text())
        links = generic.product_links(sel, "https://shop.example/collections/sale")
        self.assertEqual(links, ["https://shop.example/products/alpha", "https://shop.example/products/beta?variant=1"])
        self.assertEqual(generic.next_page(sel, "https://shop.example/collections/sale"),
                         "https://shop.example/collections/sale?page=2")

    def test_guess_type(self):
        self.assertEqual(generic.guess_type("Core Book PDF", 5)[0], "sale")
        self.assertEqual(generic.guess_type("Core Rulebook Hardcover", 5)[0], "physical")
        self.assertEqual(generic.guess_type("Anything", 0)[0], "free")


class ReadShop(unittest.TestCase):
    SHOP = {"id": "demo", "name": "Demo", "store_url": "https://shop.example/", "platform": "generic",
            "currency": "USD", "recipe": {"sale_pages": ["https://shop.example/sale"]}}

    def test_no_sale_page(self):
        deals, stats = generic.read_with_stats({**self.SHOP, "recipe": {}, "notes": None})
        self.assertEqual(deals, [])
        self.assertTrue(stats["no_sale_page"])

    def test_read_makes_deals_only_for_real_discounts(self):
        pages = {
            "https://shop.example/sale": '<a href="/products/a">a</a><a href="/products/b">b</a>',
            "https://shop.example/products/a": (FIX / "woo_del.html").read_text(),
            "https://shop.example/products/b": (FIX / "hidden_fake.html").read_text(),
        }

        def fake_fetch(url):
            return mock.Mock(body=pages[url].encode(), encoding="utf-8")

        with mock.patch.object(generic, "fetch", fake_fetch):
            deals, stats = generic.read_with_stats(self.SHOP)
        self.assertEqual(len(deals), 1)
        d = deals[0]
        self.assertEqual((d["price_now"], d["price_was"], d["source"], d["currency"]), (28.0, 40.0, "page-markup", "USD"))
        self.assertEqual(stats["items_read"], 2)


class ExaltedFuneralOptIn(unittest.TestCase):
    SHOP = {"id": "exalted-funeral", "name": "Exalted Funeral", "store_url": "https://www.exaltedfuneral.com/",
            "platform": "shopify", "currency": "USD",
            "recipe": {"collections": ["halloween-sale"], "page_prices": True}}

    def test_page_prices_fill_in_missing_compare_at(self):
        product = {"id": 1, "title": "Dolmenwood Monster Book", "handle": "dm", "variants": [
            {"title": "Default Title", "price": "24.00", "compare_at_price": None, "requires_shipping": True}]}
        info = {"title": "Dolmenwood Monster Book", "price_now": 24.0, "price_was": 30.0, "currency": "USD",
                "ends": None, "source": "page-markup", "hints": {}}
        with mock.patch("scraper.readers.generic.page_prices", return_value=info):
            deal = shopify.parse_product_from_page(self.SHOP, product, "https://www.exaltedfuneral.com")
        self.assertEqual((deal["price_now"], deal["price_was"], deal["source"]), (24.0, 30.0, "page-markup"))
        self.assertEqual(deal["type"], "physical")

    def test_page_without_discount_is_no_deal(self):
        product = {"id": 1, "title": "T", "handle": "t", "variants": [
            {"title": "Default Title", "price": "24.00", "compare_at_price": None}]}
        info = {"title": "T", "price_now": 24.0, "price_was": None, "currency": "USD", "ends": None,
                "source": "jsonld", "hints": {}}
        with mock.patch("scraper.readers.generic.page_prices", return_value=info):
            self.assertIsNone(shopify.parse_product_from_page(self.SHOP, product, "https://www.exaltedfuneral.com"))


if __name__ == "__main__":
    unittest.main()
