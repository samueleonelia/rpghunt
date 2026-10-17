import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scraper import discover
from scraper.common import FetchError

FIX = pathlib.Path(__file__).parent / "fixtures" / "discover"
DATE = "2026-10-17"

SHOPS = [
    {"id": "modiphius", "name": "Modiphius", "store_url": "https://modiphius.net/", "platform": "shopify", "status": "active"},
    {"id": "modiphius-us", "name": "Modiphius US", "store_url": "https://modiphius.us/", "platform": "shopify", "status": "active"},
    {"id": "paizo", "name": "Paizo", "store_url": "https://store.paizo.com", "platform": "generic", "status": "active"},
    {"id": "itch", "name": "itch.io", "store_url": "https://itch.io/", "platform": "itch", "status": "active"},
    {"id": "mp", "name": "Monkey's Paw", "store_url": "https://monkeys-paw-games.itch.io", "platform": "itch", "status": "active"},
    {"id": "drivethrurpg", "name": "DriveThruRPG", "store_url": "https://www.drivethrurpg.com/", "platform": "unknown", "status": "blocked"},
    {"id": "exalted", "name": "Exalted Funeral", "store_url": "https://www.exaltedfuneral.com/", "platform": "shopify", "status": "active"},
]
CONFIG = json.loads((pathlib.Path(__file__).resolve().parent.parent / "data" / "shops" / "lead-feeds.json").read_text())


def fake_fetch(table):
    def get(url):
        v = table[url]
        if isinstance(v, Exception):
            raise v
        return v if isinstance(v, bytes) else v.encode()
    return get


class Parsing(unittest.TestCase):
    def test_reddit_atom_entries_and_links(self):
        entries = discover.parse_feed((FIX / "reddit_atom.xml").read_bytes())
        self.assertEqual(len(entries), 2)
        e = entries[0]
        self.assertEqual(e["title"], "Ember Hollow bundle sale this week")
        self.assertEqual(e["url"], "https://www.reddit.com/r/rpg/comments/abc123/ember_hollow_sale/")
        self.assertEqual(e["published"], "2026-10-16")
        self.assertEqual(entries[1]["published"], "2026-08-01")         # only <updated>
        links = dict(discover.extract_links(e["body"]))
        self.assertIn("https://shop.example-games.com/products/ember-hollow-core-book", links)
        self.assertIn("https://www.drivethrurpg.com/product/111111/ember-hollow?affiliate_id=1", links)
        self.assertEqual(links["https://www.drivethrurpg.com/product/111111/ember-hollow?affiliate_id=1"], "DriveThru")
        self.assertIn("https://i.imgur.com/abc.png", links)             # bare URL in the text
        self.assertIn("https://www.reddit.com/user/dicefan", links)     # found, dropped later by the deny list

    def test_enworld_rss_cdata_links(self):
        entries = discover.parse_feed((FIX / "enworld_rss.xml").read_text())
        self.assertEqual([e["published"] for e in entries], ["2026-10-16", "2026-10-15", "2026-09-14"])
        urls = [u for u, _ in discover.extract_links(entries[1]["body"])]
        self.assertEqual(urls, ["https://www.backerkit.com/c/projects/x/y", "https://modiphius.net/products/dune-core"])

    def test_article_links_take_only_the_first_post(self):
        links = discover.article_links((FIX / "enworld_article.html").read_text())
        urls = [u for u, _ in links]
        self.assertIn("https://modiphius.net/products/dune-core", urls)
        self.assertNotIn("https://spam.example.biz/products/win-big", urls)     # a reply
        self.assertNotIn("https://www.facebook.com/enworld", urls)              # page chrome
        self.assertFalse(any(u.startswith("/") for u in urls))                  # relative links are not leads


class DenyList(unittest.TestCase):
    def test_denied(self):
        for url in ("https://www.reddit.com/r/rpg/x", "https://old.reddit.com/r/rpg", "https://redd.it/abc",
                    "https://i.imgur.com/a.png", "https://www.youtube.com/watch?v=1", "https://youtu.be/1",
                    "https://en.wikipedia.org/wiki/X", "https://twitter.com/a", "https://x.com/a", "https://bsky.app/profile/a",
                    "https://www.facebook.com/a", "https://www.instagram.com/a", "https://discord.gg/abc",
                    "https://www.patreon.com/a", "https://www.kickstarter.com/projects/a", "https://www.backerkit.com/c/a",
                    "https://www.google.com/search", "https://amzn.to/3xyz", "https://www.enworld.org/threads/x",
                    "https://humblebundleinc.sjv.io/KB3LNN", "https://example.org/pic.png", "http://localhost/x"):
            self.assertTrue(discover.is_denied(url, CONFIG), url)

    def test_shops_are_not_denied(self):
        for url in ("https://modiphius.net/products/x", "https://www.drivethrurpg.com/product/1/x",
                    "https://someone.itch.io/game", "https://enpublishingrpg.com/collections/all",
                    "https://www.amazon.com/dp/B000"):          # only amazon SHORT links are on the list
            self.assertFalse(discover.is_denied(url, CONFIG), url)

    def test_a_lookalike_domain_is_not_denied(self):
        self.assertFalse(discover.is_denied("https://notreddit.com/x", CONFIG))
        self.assertFalse(discover.is_denied("https://myx.com/x", CONFIG))


class Classes(unittest.TestCase):
    def c(self, url):
        cls, shop = discover.classify(url, SHOPS)
        return cls, shop["id"] if shop else None

    def test_known_shop_by_host_with_and_without_www(self):
        self.assertEqual(self.c("https://exaltedfuneral.com/products/x"), ("known_shop", "exalted"))
        self.assertEqual(self.c("https://www.exaltedfuneral.com/products/x"), ("known_shop", "exalted"))

    def test_sister_domains_are_matched_by_host_only(self):
        self.assertEqual(self.c("https://modiphius.net/products/x"), ("known_shop", "modiphius"))
        self.assertEqual(self.c("https://www.modiphius.us/products/x"), ("known_shop", "modiphius-us"))

    def test_shop_on_a_subdomain_matches_its_main_site(self):
        self.assertEqual(self.c("https://paizo.com/products/btq01"), ("known_shop", "paizo"))
        self.assertEqual(self.c("https://store.paizo.com/x"), ("known_shop", "paizo"))

    def test_itch_storefronts(self):
        self.assertEqual(self.c("https://monkeys-paw-games.itch.io/some-game"), ("known_shop", "mp"))
        self.assertEqual(self.c("https://anotherdev.itch.io/some-game"), ("known_shop", "itch"))

    def test_blocked_shop_keeps_the_lead(self):
        self.assertEqual(self.c("https://www.drivethrurpg.com/product/584963/root?affiliate_id=1"), ("blocked_shop", "drivethrurpg"))

    def test_unknown_site_is_a_new_shop(self):
        self.assertEqual(self.c("https://enpublishingrpg.com/collections/all"), ("new_shop", None))

    def test_two_part_tld(self):
        self.assertEqual(discover.registered_domain("shop.example.co.uk"), "example.co.uk")
        self.assertEqual(discover.registered_domain("store.paizo.com"), "paizo.com")


class Collect(unittest.TestCase):
    def config(self, **kw):
        return {**CONFIG, "feeds": [
            {"id": "reddit", "url": "https://r/feed", "enabled": True, "fetch_articles": False},
            {"id": "enworld", "url": "https://e/feed", "enabled": True, "fetch_articles": True},
        ], **kw}

    def table(self):
        return {"https://r/feed": (FIX / "reddit_atom.xml").read_bytes(),
                "https://e/feed": (FIX / "enworld_rss.xml").read_bytes(),
                "https://www.enworld.org/threads/freebies-sales-and-charity-bundles-for-october-16-2026.1/":
                    (FIX / "enworld_article.html").read_bytes()}

    def test_collect_reads_feeds_articles_and_applies_the_deny_list_and_age(self):
        leads, report = discover.collect(self.config(), DATE, fake_fetch(self.table()))
        urls = [l["url"] for l in leads]
        self.assertIn("https://shop.example-games.com/products/ember-hollow-core-book", urls)
        self.assertIn("https://newstore.example.com/collections/sale", urls)       # from the roundup article
        self.assertIn("https://modiphius.net/products/dune-core", urls)
        self.assertNotIn("https://oldshop.example.org/products/old-thing", urls)   # post older than 14 days
        self.assertNotIn("https://stale.example.net/products/x", urls)
        self.assertFalse([u for u in urls if "reddit.com" in u or "imgur" in u or "backerkit" in u])
        by = {r["id"]: r for r in report}
        self.assertEqual(by["enworld"]["articles_read"], 1)                         # only the weekly column
        self.assertEqual(by["reddit"]["in_window"], 1)
        art = [l for l in leads if l["via"] == "article"]
        self.assertTrue(art and all(l["feed"] == "enworld" and l["post_title"].startswith("Freebies") for l in art))

    def test_blocked_feed_is_reported_not_fatal(self):
        table = self.table()
        table["https://r/feed"] = FetchError("robots", "https://r/feed", "disallowed by robots.txt")
        leads, report = discover.collect(self.config(), DATE, fake_fetch(table))
        by = {r["id"]: r for r in report}
        self.assertEqual(by["reddit"]["status"], "blocked")
        self.assertTrue(leads)

    def test_broken_xml_is_an_error_row(self):
        table = self.table()
        table["https://r/feed"] = b"<html>not a feed"
        _, report = discover.collect(self.config(), DATE, fake_fetch(table))
        self.assertEqual({r["id"]: r for r in report}["reddit"]["status"], "error")

    def test_dedupe_counts_mentions(self):
        a = {"url": "https://a.com/products/x?ref=1", "feed": "f"}
        b = {"url": "https://www.a.com/products/x", "feed": "g"}
        out = discover.dedupe([a, b])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["mentions"], 2)

    def test_roundup_title(self):
        pats = CONFIG["article_title_patterns"]
        self.assertTrue(discover.is_roundup_title("Freebies, Sales, and Charity Bundles for October 5, 2026", pats))
        self.assertTrue(discover.is_roundup_title("50% sale on hundreds of PDFs", pats))
        self.assertFalse(discover.is_roundup_title("Dragon Reflections #106", pats))


class NewShops(unittest.TestCase):
    def lead(self, url, feed="enworld"):
        return {"url": url, "feed": feed, "class": "new_shop"}

    def detector(self, platform, status="active"):
        def detect(origin):
            host = origin.split("//")[1].strip("/")
            return {"id": host.split(".")[0], "name": host, "store_url": origin, "platform": platform, "status": status,
                    "currency": None, "recipe": {}, "recipe_confirmed": None, "added": "x", "added_via": "seed list", "notes": None}
        return detect

    def test_real_store_is_added(self):
        added, notes, seen = discover.find_new_shops([self.lead("https://newstore.example.com/blogs/news/x")], SHOPS,
                                                     CONFIG, DATE, self.detector("shopify"))
        self.assertEqual([(s["id"], s["added_via"]) for s in added], [("newstore", "lead enworld 2026-10-17")])
        self.assertNotIn("needs_recipe", added[0])

    def test_generic_site_needs_a_shop_looking_link(self):
        added, notes, seen = discover.find_new_shops([self.lead("https://blog.example.com/post/about-games")], SHOPS,
                                                     CONFIG, DATE, self.detector("generic"))
        self.assertEqual(added, [])
        self.assertEqual(seen["blog.example.com"]["result"], "not a shop")
        added, _, _ = discover.find_new_shops([self.lead("https://shop2.example.com/collections/sale")], SHOPS,
                                              CONFIG, DATE, self.detector("generic"))
        self.assertEqual(len(added), 1)
        self.assertTrue(added[0]["needs_recipe"])

    def test_blocked_shop_is_added_as_blocked(self):
        added, _, _ = discover.find_new_shops([self.lead("https://closed.example.com/shop/x")], SHOPS, CONFIG, DATE,
                                              self.detector("unknown", "blocked"))
        self.assertEqual((added[0]["platform"], added[0]["status"]), ("unknown", "blocked"))

    def test_cap_and_seen_and_id_clash(self):
        leads = [self.lead(f"https://s{i}.example.com/products/x") for i in range(14)]
        added, notes, seen = discover.find_new_shops(leads, SHOPS, {**CONFIG, "max_new_shops_per_day": 3}, DATE,
                                                     self.detector("shopify"))
        self.assertEqual(len(added), 3)
        self.assertTrue(any("cap" in n for n in notes.values()))
        # a host judged "not a shop" yesterday is not probed again
        calls = []

        def spy(origin):
            calls.append(origin)
            return self.detector("shopify")(origin)
        discover.find_new_shops([self.lead("https://s1.example.com/products/x")], SHOPS, CONFIG, DATE, spy,
                                {"s1.example.com": {"date": "2026-10-10", "result": "not a shop"}})
        self.assertEqual(calls, [])
        # id clash with an existing shop id gets a suffix
        added, _, _ = discover.find_new_shops([self.lead("https://itch.example.com/products/x")], SHOPS, CONFIG, DATE,
                                              self.detector("shopify"))
        self.assertEqual(added[0]["id"], "itch-2")

    def test_a_probe_that_crashes_does_not_stop_discovery(self):
        def boom(origin):
            raise RuntimeError("x")
        added, notes, _ = discover.find_new_shops([self.lead("https://a.example.com/products/x")], SHOPS, CONFIG, DATE, boom)
        self.assertEqual(added, [])
        self.assertIn("probe failed", notes["a.example.com"])


class Run(unittest.TestCase):
    def test_whole_discovery_writes_leads_and_new_shops(self):
        tmp = pathlib.Path(tempfile.mkdtemp())
        saved = []
        table = {"https://r/feed": (FIX / "reddit_atom.xml").read_bytes(),
                 "https://e/feed": (FIX / "enworld_rss.xml").read_bytes(),
                 "https://www.enworld.org/threads/freebies-sales-and-charity-bundles-for-october-16-2026.1/":
                     (FIX / "enworld_article.html").read_bytes()}
        config = {**CONFIG, "feeds": [{"id": "reddit", "url": "https://r/feed", "enabled": True},
                                      {"id": "enworld", "url": "https://e/feed", "enabled": True, "fetch_articles": True}]}

        def detector(origin):
            host = origin.split("//")[1].strip("/")
            return {"id": host.split(".")[0], "name": host, "store_url": origin, "platform": "shopify",
                    "status": "active", "currency": "USD", "recipe": {}, "recipe_confirmed": DATE, "added": "x",
                    "added_via": "seed list", "notes": None}
        with mock.patch.object(discover, "DEALS", tmp), mock.patch.object(discover, "SEEN_FILE", tmp / "seen.json"), \
                mock.patch.object(discover, "load_shops", lambda: list(SHOPS)), \
                mock.patch.object(discover, "save_shops", lambda s: saved.append(s)):
            doc = discover.run(DATE, config, fake_fetch(table), True, detector, list(SHOPS))
            again = discover.run(DATE, config, fake_fetch(table), True, lambda o: 1 / 0,
                                 list(SHOPS) + [detector("https://newstore.example.com/"), detector("https://shop.example-games.com/")])
        classes = {l["url"]: (l["class"], l["shop_id"]) for l in doc["leads"]}
        self.assertEqual(classes["https://modiphius.net/products/dune-core"], ("known_shop", "modiphius"))
        self.assertEqual(classes["https://www.drivethrurpg.com/product/222222/some-adventure?affiliate_id=9"],
                         ("blocked_shop", "drivethrurpg"))
        self.assertEqual(classes["https://newstore.example.com/collections/sale"], ("new_shop", "newstore"))
        self.assertEqual(doc["counts"]["new_shops_added"], 2)         # newstore.example.com and shop.example-games.com
        self.assertEqual(sorted(s["id"] for s in saved[0][len(SHOPS):]), ["newstore", "shop"])
        written = json.loads((tmp / f"leads-{DATE}.json").read_text())
        self.assertEqual({"url", "post_title", "post_url", "feed", "published", "class", "shop_id"} <= set(written["leads"][0]), True)
        # a second run the same day (shop now known) keeps the first run's new-shop list
        self.assertEqual(sorted(s["id"] for s in again["new_shops"]), ["newstore", "shop"])
        self.assertEqual(again["counts"]["new_shops_added"], 2)         # counted from the day's list, not only this run


if __name__ == "__main__":
    unittest.main()
