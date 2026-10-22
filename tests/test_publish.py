import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scraper import publish
from scraper.common import FetchError

ROOT = pathlib.Path(__file__).resolve().parent.parent
REAL = json.loads((ROOT / "docs" / "data" / "deals.json").read_text())      # read only
DATE = "2026-10-17"
GAMES = [{"name": "Ars Magica", "id": "ars-magica"}, {"name": "Fate", "id": "fate"},
         {"name": "The One Ring", "id": "the-one-ring"}, {"name": "Mörk Borg", "id": "mork-borg"}]


def checked(**kw):
    d = {"type": "physical", "title": "Atlas Games: AG0317 Mythic Europe Fabric Map (Ars Magica 5E)", "game": None,
         "shop": "Atlas Games", "shop_id": "atlas", "url": "https://shop.atlas-games.com/products/ag0317",
         "price_now": 17.48, "price_was": 34.95, "currency": "USD", "discount_pct": 50, "format": None, "ends": None,
         "summary": None, "found_via": "/products.json", "source": "shopify-api", "confidence": "high",
         "hints": {"tags": []}, "notes": None, "checked_at": "2026-10-17T00:00:00+00:00",
         "check": {"decision": "publish", "rpg_p": 0.9}}
    d.update(kw)
    return d


class Shape(unittest.TestCase):
    def test_keys_and_order_match_the_live_site_file(self):
        doc = publish.build(DATE, [checked()], GAMES, {}, {})
        live = REAL["deals"][0]
        self.assertEqual(list(doc.keys()), list(REAL.keys()))
        self.assertEqual(list(doc["deals"][0].keys()), list(live.keys()))
        self.assertEqual(list(publish.SITE_KEYS), list(live.keys()))

    def test_every_real_entry_has_the_same_keys(self):
        for d in REAL["deals"]:
            self.assertEqual(list(d.keys()), list(publish.SITE_KEYS))

    def test_fields(self):
        meta = {"https://shop.atlas-games.com/products/ag0317": {"image": "https://img/x.jpg", "rating": {"value": 4.5, "count": 12}}}
        d = publish.build(DATE, [checked()], GAMES, {"atlas-games-ag0317-mythic-europe-fabric-map-ars-magica-5e": [{"source": "s"}]},
                          meta)["deals"][0]
        self.assertEqual(d["title"], "AG0317 Mythic Europe Fabric Map (Ars Magica 5E)")      # shop name not repeated
        self.assertEqual((d["game"], d["game_id"]), ("Ars Magica", "ars-magica"))
        self.assertEqual(d["image"], "https://img/x.jpg")
        self.assertEqual(d["rating"]["count"], 12)
        self.assertEqual(d["id"], "atlas-games-ag0317-mythic-europe-fabric-map-ars-magica-5e")
        self.assertEqual(d["reviews"], [{"source": "s"}])
        self.assertEqual((d["verified"], d["price_seen"]), ("source", None))
        for gone in ("found_via", "shop_id", "source", "hints", "check", "checked_at"):
            self.assertNotIn(gone, d)

    def test_page_checked_and_agent_deals_are_marked_page(self):
        a = publish.build(DATE, [checked(check={"price_now_in_text": True})], GAMES, {}, {})["deals"][0]
        b = publish.build(DATE, [checked(check={"via": "agent"})], GAMES, {}, {})["deals"][0]
        self.assertEqual([(x["verified"], x["price_seen"]) for x in (a, b)], [("page", True)] * 2)

    def test_sort_free_first_then_biggest_discount(self):
        deals = [checked(url="https://a/1", title="A one", discount_pct=20), checked(url="https://a/2", title="B two", discount_pct=70),
                 checked(url="https://a/3", title="C three", type="free", price_now=0, discount_pct=100, price_was=5),
                 checked(url="https://a/4", title="D four", discount_pct=None, price_was=None)]
        out = publish.build(DATE, deals, GAMES, {}, {})["deals"]
        self.assertEqual([d["title"] for d in out], ["C three", "B two", "A one", "D four"])

    def test_discount_is_computed_when_missing(self):
        d = publish.build(DATE, [checked(discount_pct=None, price_now=10.0, price_was=40.0)], GAMES, {}, {})["deals"][0]
        self.assertEqual(d["discount_pct"], 75)


class Games(unittest.TestCase):
    def test_guess(self):
        g = lambda t: (publish.guess_game(t, GAMES) or {}).get("name")
        self.assertEqual(g("Mythic Europe Map (Ars Magica 5E)"), "Ars Magica")
        self.assertEqual(g("The One Ring Starter Set"), "The One Ring")
        self.assertEqual(g("One Ring Adventures"), "The One Ring")        # a leading "The" is optional
        self.assertEqual(g("Fate Core Rulebook"), "Fate")
        self.assertIsNone(g("The Fate of Cthulhu Dice"))                  # a short name must start the title
        self.assertIsNone(g("Arsenal Magic Cards"))                       # whole words only
        self.assertEqual(g("MÖRK BORG - Cult Feretory"), "Mörk Borg")


class Duplicates(unittest.TestCase):
    def test_sister_domain_duplicate_is_dropped(self):
        a = checked(shop="Modiphius", url="https://modiphius.net/products/dune-core-rulebook", title="Dune Core Rulebook", price_now=5.0)
        b = checked(shop="Modiphius US", url="https://modiphius.us/products/dune-core-rulebook", title="Dune Core Rulebook", price_now=5.0)
        c = checked(shop="Modiphius", url="https://modiphius.net/products/other-book", title="Other Book", price_now=5.0)
        self.assertEqual([d["url"] for d in publish.dedupe([a, b, c])], [a["url"], c["url"]])


class PageMeta(unittest.TestCase):
    HTML = ('<html><head><meta property="og:image" content="http://cdn.example/x.jpg">'
            '<script type="application/ld+json">{"aggregateRating": {"ratingValue": "4.5", "ratingCount": "20"}}</script>'
            '</head><body>hi</body></html>')

    def resp(self, html):
        return mock.Mock(body=html.encode(), encoding="utf-8")

    def test_image_and_rating(self):
        m = publish.page_meta("https://shop.example/p/x", lambda u: self.resp(self.HTML))
        self.assertEqual(m["image"], "https://cdn.example/x.jpg")
        self.assertEqual(m["rating"], {"value": 4.5, "count": 20})

    def test_robot_check_and_errors_give_no_image(self):
        self.assertIsNone(publish.page_meta("https://s/p", lambda u: self.resp("<title>Just a moment...</title>"))["image"])

        def boom(u):
            raise FetchError("blocked", u, "HTTP 403")
        self.assertEqual(publish.page_meta("https://s/p", boom)["error"], "blocked")
        self.assertEqual(publish.page_meta("fixture:x.html")["error"], "fixture")

    def test_cache_saves_requests(self):
        cache = pathlib.Path(tempfile.mkdtemp()) / "c.json"
        calls = []

        def load(u):
            calls.append(u)
            return self.resp(self.HTML)
        urls = ["https://shop.example/p/a", "https://shop.example/p/b"]
        m1, s1 = publish.metas_for(urls, DATE, cache, load, workers=1)
        m2, s2 = publish.metas_for(urls, "2026-10-18", cache, load, workers=1)
        self.assertEqual((s1["fetched"], s2["fetched"], s2["cached"]), (2, 0, 2))
        self.assertEqual(len(calls), 2)
        self.assertEqual(m2[urls[0]]["image"], "https://cdn.example/x.jpg")


class Budget(unittest.TestCase):
    def test_pages_over_the_time_budget_are_skipped_and_not_cached(self):
        cache = pathlib.Path(tempfile.mkdtemp()) / "c.json"
        t = iter([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])        # clock: start=0, then +1 per check
        html = mock.Mock(body=b'<meta property="og:image" content="https://cdn/x.jpg">', encoding="utf-8")
        urls = [f"https://shop.example/p/{i}" for i in range(6)]
        out, st = publish.metas_for(urls, DATE, cache, lambda u: html, workers=1, budget=3, clock=lambda: next(t))
        self.assertEqual(st["fetched"] + st["skipped_for_time"], 6)
        self.assertGreater(st["skipped_for_time"], 0)
        self.assertEqual(sum(1 for m in out.values() if m["error"] == "time budget"), st["skipped_for_time"])
        self.assertEqual(len(json.loads(cache.read_text())), st["fetched"])


class Guard(unittest.TestCase):
    def run_main(self, deals, argv):
        tmp = pathlib.Path(tempfile.mkdtemp())
        raw = tmp / "raw"
        raw.mkdir()
        (raw / f"{DATE}-checked.json").write_text(json.dumps(deals))
        (raw / f"{DATE}-checked-FAKE.json").write_text(json.dumps(deals))
        with mock.patch.object(publish, "RAW", raw), mock.patch.object(publish, "DEALS", tmp):
            rc = publish.main(["--date", DATE, "--no-images"] + [a.replace("TMP", str(tmp)) for a in argv])
        return rc, tmp

    def test_default_output_is_a_preview_next_to_the_data(self):
        rc, tmp = self.run_main([checked()], [])
        self.assertEqual(rc, 0)
        self.assertTrue((tmp / f"site-preview-{DATE}.json").exists())

    def test_fake_runs_only_write_fake_files(self):
        rc, tmp = self.run_main([checked()], ["--fake"])
        self.assertTrue((tmp / f"site-preview-{DATE}-FAKE.json").exists())
        rc, tmp = self.run_main([checked()], ["--fake", "--out", "TMP/deals.json"])
        self.assertEqual(rc, 2)
        self.assertFalse((tmp / "deals.json").exists())

    def test_deals_marked_fake_cannot_go_to_a_real_file_even_without_the_flag(self):
        rc, tmp = self.run_main([checked(check={"fake_jev": True})], ["--out", "TMP/deals.json"])
        self.assertEqual(rc, 2)
        rc, tmp = self.run_main([checked(check={"fake_agent": True})], [])
        self.assertEqual(rc, 0)                                          # default name gets -FAKE
        self.assertTrue((tmp / f"site-preview-{DATE}-FAKE.json").exists())

    def test_never_writes_the_live_site_file_by_default(self):
        self.assertFalse(str(publish.resolve_out(None, DATE, False)).endswith("docs/data/deals.json"))


if __name__ == "__main__":
    unittest.main()


class Summary(unittest.TestCase):
    def test_first_sentence_of_the_shop_text(self):
        d = {"hints": {"description": "Even the mightiest wizard once cast his very first spell. Second sentence here."}}
        self.assertEqual(publish.shop_summary(d), "Even the mightiest wizard once cast his very first spell.")

    def test_long_text_without_a_full_stop_is_cut_at_a_word(self):
        d = {"hints": {"description": "word " * 60}}
        s = publish.shop_summary(d)
        self.assertTrue(s.endswith("…") and len(s) <= publish.SUMMARY_CHARS + 1 and "  " not in s)

    def test_itch_blurb_and_no_text(self):
        self.assertEqual(publish.shop_summary({"hints": {"blurb": "A tiny horror zine"}}), "A tiny horror zine")
        self.assertIsNone(publish.shop_summary({"hints": {}}))


class FactsSummary(unittest.TestCase):
    def test_lines_from_shop_facts_when_there_is_no_text(self):
        self.assertEqual(publish.shop_summary({"hints": {"bundle_slug": "X", "level_up_price": "30.67"}}),
                         "PDF bundle. Pay $30.67 or more to add the bonus collection.")
        self.assertEqual(publish.shop_summary({"hints": {"sale_title": "Spooky Sale", "seller_name": "BlackwellWriter"}}),
                         "Spooky Sale by BlackwellWriter.")
        self.assertEqual(publish.shop_summary({"hints": {"categories": "['5.5E', '5th Edition', 'Classes', 'Maps']"}}),
                         "5.5E, 5th Edition, Classes.")
        self.assertIsNone(publish.shop_summary({"hints": {"categories": "not a list"}}))
