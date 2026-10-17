"""itch reader: parsing on saved pages, and read() with the network replaced by fixtures."""
import json
import pathlib
import unittest
from unittest import mock

from scraper.common import FetchError
from scraper.readers import itch

FIX = pathlib.Path(__file__).parent / "fixtures" / "itch"
SHOP = {"id": "itch-io", "name": "itch.io", "store_url": "https://itch.io/", "platform": "itch",
        "recipe": {"feeds": ["https://itch.io/physical-games/on-sale/tag-ttrpg.xml",
                             "https://itch.io/games/on-sale/tag-ttrpg.xml"]}}
WITCH = "https://swashtalk.itch.io/the-magical-year-of-a-teenage-witch"
EA = "https://davidblandy.itch.io/ea-nasir-must-die"
MYSTERY = "https://odd.itch.io/mystery-zine"
BUNDLE = "https://itch.io/s/204632/weird-science-bundle"


def read_fix(name):
    return (FIX / name).read_text()


class FakeResp:
    def __init__(self, text):
        self.body = text.encode()


def fake_fetch(url):
    pages = {
        SHOP["recipe"]["feeds"][0]: "feed.xml", SHOP["recipe"]["feeds"][1]: "feed_dup.xml",
        WITCH: "game_sale.html", EA: "game_zero.html", MYSTERY: "game_noprice.html", BUNDLE: "bundle.html",
    }
    if url not in pages:
        raise FetchError("dead", url, "HTTP 404")
    return FakeResp(read_fix(pages[url]))


def fake_fetch_json(url):
    data = {WITCH + "/data.json": "game_sale.data.json", EA + "/data.json": "game_zero.data.json",
            MYSTERY + "/data.json": "game_noprice.data.json"}
    if url not in data:
        raise FetchError("dead", url, "HTTP 404")
    return json.loads(read_fix(data[url]))


class ParseTests(unittest.TestCase):
    def test_feed_gives_links_and_titles_only(self):
        items = itch.parse_feed(read_fix("feed.xml").encode())
        self.assertEqual([i["url"] for i in items], [WITCH, EA, MYSTERY])
        self.assertEqual(items[1]["title"], "Ea-nasir Must Die!")

    def test_game_page_facts(self):
        f = itch.parse_game_page(read_fix("game_sale.html"))
        self.assertEqual((f["now"], f["was"], f["currency"], f["rate"]), (8.0, 10.0, "USD", 20))
        self.assertEqual(f["ends_raw"], "2026-11-01T12:02:00Z")
        self.assertEqual(f["seller_name"], "swashtalk")

    def test_game_page_without_price(self):
        f = itch.parse_game_page(read_fix("game_noprice.html"))
        self.assertIsNone(f["now"])
        self.assertIsNone(f["was"])

    def test_data_json(self):
        gd = itch.parse_game_data(read_fix("game_sale.data.json"))
        self.assertEqual((gd["price"], gd["rate"], gd["end_date"]), (8.0, 20, "2026-11-01 12:02:00"))
        zero = itch.parse_game_data(read_fix("game_zero.data.json"))
        self.assertEqual((zero["rate"], zero["sale_id"]), (0, 204632))

    def test_utc_dates(self):
        self.assertEqual(itch.utc_iso("2026-10-18 16:21:00"), ("2026-10-18", "2026-10-18T16:21:00Z"))
        self.assertEqual(itch.utc_iso("2026-11-01T06:59:00Z"), ("2026-11-01", "2026-11-01T06:59:00Z"))
        self.assertEqual(itch.utc_iso(None), (None, None))

    def test_sale_link_found_not_built(self):
        self.assertEqual(itch.find_sale_link(read_fix("game_zero.html"), 204632), BUNDLE)
        self.assertIsNone(itch.find_sale_link(read_fix("game_zero.html"), 1))

    def test_bundle_page(self):
        b = itch.parse_bundle_page(read_fix("bundle.html"))
        self.assertEqual((b["title"], b["seller"], b["now"], b["was"]), ("Weird Science Bundle", "David Blandy", 9.99, 15.98))
        self.assertIsNone(itch.parse_bundle_page("<html>no bundle here</html>"))

    def test_bundle_title_from_page_title_when_og_is_odd(self):
        page = ('<html><head><title>EP SALE!! by Exeunt Press - itch.io</title></head><body>Buy everything for '
                '<strong class="bundle_price">$30.00</strong>! Regularly <span>$81.44</span></body></html>')
        b = itch.parse_bundle_page(page)
        self.assertEqual((b["title"], b["seller"], b["now"], b["was"]), ("EP SALE!!", "Exeunt Press", 30.0, 81.44))

    def test_amounts(self):
        self.assertEqual(itch.parse_amount("$1,234.50"), 1234.5)
        self.assertEqual(itch.parse_amount("€10,50"), 10.5)
        self.assertIsNone(itch.parse_amount("Free"))


class ReadTests(unittest.TestCase):
    def run_read(self):
        with mock.patch.object(itch, "fetch", fake_fetch), mock.patch.object(itch, "fetch_json", fake_fetch_json):
            return itch.read(SHOP)

    def test_read(self):
        deals = self.run_read()
        by_url = {d["url"]: d for d in deals}
        # real sale: kept, one copy even though two feeds list it
        self.assertEqual(len(deals), 2)
        d = by_url[WITCH]
        self.assertEqual((d["type"], d["price_now"], d["price_was"], d["currency"], d["discount_pct"]),
                         ("sale", 8.0, 10.0, "USD", 20))
        self.assertEqual(d["ends"], "2026-11-01")
        self.assertEqual(d["hints"]["ends_utc"], "2026-11-01T12:02:00Z")
        self.assertEqual(d["hints"]["seller"], "swashtalk")
        self.assertEqual((d["shop"], d["shop_id"], d["title"]), ("itch.io", "itch-io", "The Magical Year of a Teenage Witch"))
        # the "[0% Off]" game is not a deal; it only leads to its bundle, read once
        self.assertNotIn(EA, by_url)
        b = by_url[BUNDLE]
        self.assertEqual((b["type"], b["title"], b["price_now"], b["price_was"], b["currency"], b["ends"]),
                         ("bundle", "Weird Science Bundle", 9.99, 15.98, "USD", "2026-10-18"))
        self.assertEqual(b["hints"]["ends_utc"], "2026-10-18T16:21:00Z")
        # the item with no price: no deal, no crash
        self.assertNotIn(MYSTERY, by_url)

    def test_failed_feed_does_not_stop_the_reader(self):
        shop = dict(SHOP, recipe={"feeds": ["https://itch.io/gone.xml"] + SHOP["recipe"]["feeds"]})
        with mock.patch.object(itch, "fetch", fake_fetch), mock.patch.object(itch, "fetch_json", fake_fetch_json):
            self.assertEqual(len(itch.read(shop)), 2)

    def test_page_fallback_when_data_json_missing(self):
        def no_json(url):
            raise FetchError("dead", url, "HTTP 404")
        with mock.patch.object(itch, "fetch", fake_fetch), mock.patch.object(itch, "fetch_json", no_json):
            deals = itch.read(SHOP)
        self.assertEqual([d["url"] for d in deals], [WITCH])   # 0% and no-price items give nothing


if __name__ == "__main__":
    unittest.main()
