"""Bundle readers on saved pages (network replaced by fixtures)."""
import json
import pathlib
import unittest
from unittest import mock

from scraper.common import FetchError
from scraper.readers import bundles

FIX = pathlib.Path(__file__).parent / "fixtures" / "bundles"
HOME = "https://bundleofholding.com/"
BOH_SHOP = {"id": "bundle-of-holding", "name": "Bundle of Holding", "store_url": HOME, "platform": "bundleofholding"}
HUMBLE_SHOP = {"id": "humble-bundle", "name": "Humble Bundle", "store_url": "https://www.humblebundle.com/books", "platform": "humble"}


class FakeResp:
    def __init__(self, text):
        self.body = text.encode()


def make_fetch(mapping):
    def fake(url):
        if url not in mapping:
            raise FetchError("dead", url, "HTTP 404")
        return FakeResp((FIX / mapping[url]).read_text())
    return fake


BOH_PAGES = {HOME: "boh_home.html",
             "https://bundleofholding.com/presents/BlueFox": "boh_bluefox.html",
             "https://bundleofholding.com/presents/Knock2026": "boh_knock.html"}
HUMBLE_PAGES = {
    "https://www.humblebundle.com/books": "humble_landing.html",
    "https://www.humblebundle.com/books/urban-shadows-physical-collection-books": "humble_urban.html",
    # the Castles & Crusades page is deliberately missing: a failing bundle must not stop the reader
}


class BundleOfHoldingTests(unittest.TestCase):
    def test_home_lists_featured_and_linked_bundles(self):
        found = bundles.boh_home_bundles((FIX / "boh_home.html").read_text())
        self.assertEqual([b["url"] for b in found], [
            "https://bundleofholding.com/presents/MotW2026",
            "https://bundleofholding.com/presents/BlueFox",
            "https://bundleofholding.com/presents/Knock2026"])
        self.assertTrue(found[0]["featured"])
        self.assertEqual(found[1]["ends_ts"], "4102358399")

    def test_bundle_page(self):
        p = bundles.parse_boh_bundle((FIX / "boh_home.html").read_text())
        self.assertEqual((p["title"], p["now"], p["was"], p["threshold"], p["ends_ts"]),
                         ("Monster Hunters", 14.95, 60.0, 29.34, "4102444799"))

    def test_read(self):
        with mock.patch.object(bundles, "fetch", make_fetch(BOH_PAGES)):
            deals = bundles.read(BOH_SHOP)          # dispatcher
        by_title = {d["title"]: d for d in deals}
        self.assertEqual(set(by_title), {"Monster Hunters", "Blue Fox Cthulhu", "Knock!"})
        d = by_title["Monster Hunters"]
        self.assertEqual((d["type"], d["price_now"], d["price_was"], d["currency"], d["discount_pct"]),
                         ("bundle", 14.95, 60.0, "USD", 75))
        self.assertEqual(d["url"], "https://bundleofholding.com/presents/MotW2026")
        self.assertEqual((d["ends"], d["hints"]["ends_utc"]), ("2099-12-31", "2099-12-31T23:59:59Z"))
        k = by_title["Knock!"]
        self.assertEqual((k["price_now"], k["price_was"], k["ends"]), (17.95, 72.0, "2099-12-29"))
        self.assertEqual(by_title["Blue Fox Cthulhu"]["price_was"], 87.0)

    def test_ended_bundle_is_skipped(self):
        pages = {k: v for k, v in BOH_PAGES.items()}
        text = (FIX / "boh_home.html").read_text().replace("4102444799", "1000000000")
        fake = make_fetch(pages)
        def fetch(url):
            return FakeResp(text) if url == HOME else fake(url)
        with mock.patch.object(bundles, "fetch", fetch):
            titles = {d["title"] for d in bundles.read_bundleofholding(BOH_SHOP)}
        self.assertNotIn("Monster Hunters", titles)


class HumbleTests(unittest.TestCase):
    def test_landing_tiles_unique_and_bundles_only(self):
        tiles = bundles.humble_tiles((FIX / "humble_landing.html").read_text())
        self.assertEqual([t["tile_name"] for t in tiles],
                         ["Castles & Crusades RPG Experience", "Urban Shadows Physical Collection"])

    def test_bundle_page_tiers_and_msrp(self):
        p = bundles.parse_humble_bundle((FIX / "humble_urban.html").read_text())
        self.assertEqual([t["price"] for t in p["tiers"]], [35.98, 54.44])
        self.assertEqual((p["currency"], round(p["msrp"], 2), p["end"]), ("EUR", 123.52, "2099-11-06T19:00:00"))

    def test_read(self):
        with mock.patch.object(bundles, "fetch", make_fetch(HUMBLE_PAGES)):
            deals = bundles.read(HUMBLE_SHOP)
        self.assertEqual(len(deals), 1)
        d = deals[0]
        self.assertEqual((d["type"], d["title"], d["price_now"], d["price_was"], d["currency"], d["ends"]),
                         ("bundle", "Urban Shadows Physical Collection", 35.98, 123.52, "EUR", "2099-11-06"))
        self.assertEqual(d["url"], "https://www.humblebundle.com/books/urban-shadows-physical-collection-books")
        self.assertEqual(d["hints"]["tiers"], [35.98, 54.44])
        self.assertEqual(d["hints"]["author"], "Magpie Games")
        self.assertIn("Pay What You Want", d["hints"]["tags"])

    def test_unknown_platform(self):
        with self.assertRaises(ValueError):
            bundles.read({"platform": "shopify"})


if __name__ == "__main__":
    unittest.main()
