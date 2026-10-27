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

    def test_no_daily_cap_only_a_reported_safety_limit_and_seen_and_id_clash(self):
        leads = [self.lead(f"https://s{i}.example.com/products/x") for i in range(14)]
        added, _, _ = discover.find_new_shops(leads, SHOPS, CONFIG, DATE, self.detector("shopify"))
        self.assertEqual(len(added), 14)                     # no quota on new shops
        stats = {}
        added, notes, seen = discover.find_new_shops(leads, SHOPS, {**CONFIG, "safety_max_probes_per_day": 3}, DATE,
                                                     self.detector("shopify"), stats=stats)
        self.assertEqual(len(added), 3)
        self.assertTrue(any("safety limit" in n for n in notes.values()))
        self.assertEqual(stats["safety_limit_hit"], "3 probes a day")
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
        config = {**CONFIG, "directories": [],
                  "feeds": [{"id": "reddit", "url": "https://r/feed", "enabled": True},
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


class Sellers(unittest.TestCase):
    """Seller leads (RPG news links, directory websites) must lead to a store that sells English RPGs."""

    def lead(self, url, feed="wikidata-rpg-publishers"):
        return {"url": url, "class": "new_shop", "feed": feed, "purpose": "sellers"}

    def entry(self, url, platform):
        host = url.split("//")[1].split("/")[0]
        return {"id": host.split(".")[0], "name": host, "store_url": url, "platform": platform, "status": "active",
                "currency": None, "recipe": {"api_base": url + "wp-json/wc/store/v1"} if platform == "woocommerce" else {},
                "recipe_confirmed": None, "added": "x", "added_via": "seed list", "notes": None}

    def test_store_links_on_a_home_page(self):
        from scraper import detect
        page = ('<a href="/about">About</a><a href="https://shop.acme-games.com/">Shop</a>'
                '<a href="/store/">Buy our books</a><a href="https://www.drivethrurpg.com/browse/pub/1">PDFs</a>'
                '<a href="https://twitter.com/acme">Twitter</a>')
        links = detect.store_links(page, "https://acme-games.com")
        self.assertEqual(links[0], "https://shop.acme-games.com/")
        self.assertIn("https://acme-games.com/store/", links)
        self.assertEqual(links[-1], "https://www.drivethrurpg.com/browse/pub/1")
        self.assertNotIn("https://acme-games.com/about", links)

    def test_rpg_store_needs_english_rpg_products(self):
        from scraper import detect
        shop = self.entry("https://acme.example.com/", "shopify")
        rpg = {"products": [{"title": t, "product_type": "", "tags": []} for t in
                            ("Core Rulebook", "Bestiary of the Deep", "GM Screen", "T-shirt", "Mug")]}
        self.assertTrue(detect.rpg_store(shop, lambda u: rpg)[0])
        socks = {"products": [{"title": t, "product_type": "Apparel", "tags": []} for t in ("Socks", "Hat", "Scarf")]}
        self.assertFalse(detect.rpg_store(shop, lambda u: socks)[0])
        few = {"products": [{"title": t, "product_type": "", "tags": []} for t in ["HackMaster Player's Handbook"] + ["Board game"] * 40]}
        self.assertFalse(detect.rpg_store(shop, lambda u: few)[0])
        self.assertTrue(detect.rpg_store(shop, lambda u: few, known=True)[0])      # a listed RPG publisher
        japanese = {"products": [{"title": "ドラゴン TRPG ルールブック", "product_type": "", "tags": []}] * 5}
        self.assertEqual(detect.rpg_store(shop, lambda u: japanese), (False, "products are not in English"))
        brazil = {"products": [{"title": t, "product_type": "", "tags": []} for t in   # Latin letters, Portuguese
                               ("Tormenta RPG", "Guia de Itens Mágicos RPG", "Templários 4ª Edição RPG", "Abismo RPG",
                                "Spiritum – O Reino dos Mortos RPG")]}
        self.assertEqual(detect.rpg_store(shop, lambda u: brazil, known=True), (False, "products are not in English"))
        accents = {"products": [{"title": t, "product_type": "", "tags": []} for t in
                                ("Pokémon-free Core Rulebook", "Bestiary of the Deep", "GM Screen", "Adventure Module", "Map Pack")]}
        self.assertTrue(detect.rpg_store(shop, lambda u: accents)[0])               # one accent is not a language

    def test_home_page_leads_to_its_shop(self):
        from scraper import detect
        products = {"products": [{"title": t, "product_type": "", "tags": []} for t in ("Core Rulebook", "Bestiary", "Quickstart")]}

        def detector(url):
            return self.entry(url, "shopify" if "shop." in url else "generic")
        entry, why = detect.find_seller(detector("https://acme-games.com/"), "https://acme-games.com", detector,
                                        get_json=lambda u: products,
                                        get_page=lambda u: '<a href="https://shop.acme-games.com/">Shop</a>')
        self.assertEqual(entry["store_url"], "https://shop.acme-games.com/")
        self.assertIn("found by discovery", entry["notes"])

    def test_seller_on_a_marketplace_we_read_is_not_added(self):
        from scraper import detect
        detector = lambda url: self.entry(url, "generic")
        entry, why = detect.find_seller(detector("https://author.example.com/"), "https://author.example.com", detector,
                                        get_page=lambda u: '<a href="https://www.drivethrurpg.com/browse/pub/9">Buy</a>')
        self.assertIsNone(entry)
        self.assertIn("drivethrurpg.com", why)

    def test_find_new_shops_uses_the_seller_check(self):
        calls = []

        def seller(entry, origin, detector, known=False):
            calls.append(origin)
            return (entry, "3 of 3 products name RPG words") if "good" in origin else (None, "not an RPG store")
        detector = lambda url: self.entry(url, "shopify")
        added, notes, seen = discover.find_new_shops([self.lead("https://good.example.com/"), self.lead("https://bad.example.com/")],
                                                     SHOPS, CONFIG, DATE, detector, seller=seller)
        self.assertEqual([s["id"] for s in added], ["good"])
        self.assertEqual(seen["bad.example.com"]["result"], "not a seller")
        self.assertIn("not an RPG store", notes["bad.example.com"])
        self.assertEqual(sorted(calls), ["https://bad.example.com", "https://good.example.com"])

    def test_wikipedia_category_becomes_seller_leads_and_is_cached(self):
        W = "https://en.wikipedia.org/wiki/"
        cat = ('<div id="mw-subcategories"><a href="/wiki/Category:Indie_role-playing_game_publishing_companies">Indie</a>'
               '<a href="/wiki/Category:Games_Workshop">GW</a></div>'
               '<div id="mw-pages"><li><a href="/wiki/Acme_Games" title="Acme Games">Acme</a></li>'
               '<li><a href="/wiki/No_Site_Press" title="No Site Press">x</a></li></div>')
        indie = '<div id="mw-pages"><li><a href="/wiki/Tiny_Press" title="Tiny Press">t</a></li></div>'
        box = lambda url: (f'<table class="infobox vcard"><tr><th>Founded</th><td>1999</td></tr><tr><th scope="row">Website</th>'
                           f'<td><span class="url"><a rel="nofollow" class="external text" href="{url}">site</a></span></td></tr></table>')
        table = {W + "Category:Role-playing_game_publishing_companies": cat,
                 W + "Category:Indie_role-playing_game_publishing_companies": indie,
                 W + "Acme_Games": box("https://acme-games.com/"), W + "Tiny_Press": box("https://tiny.example.com"),
                 W + "No_Site_Press": "<p>no infobox</p>"}
        calls = []

        def get(url):
            calls.append(url)
            return table[url].encode()
        config = {**CONFIG, "directories": [{"id": "wp", "type": "wikipedia_category", "follow": "role-playing game publishing",
                                             "categories": ["Category:Role-playing_game_publishing_companies"]}]}
        cache = pathlib.Path(tempfile.mkdtemp()) / "cache.json"
        leads, rows = discover.collect_directories(config, DATE, get, cache)
        self.assertEqual(sorted((l["url"], l["link_text"], l["purpose"]) for l in leads),
                         [("https://acme-games.com/", "Acme Games", "sellers"), ("https://tiny.example.com", "Tiny Press", "sellers")])
        self.assertNotIn(W + "Category:Games_Workshop", calls)          # subcategory not followed
        n = len(calls)
        again, rows = discover.collect_directories(config, "2026-10-20", get, cache)
        self.assertEqual((len(again), len(calls), rows[0]["cached_from"]), (2, n, DATE))   # cached: no new fetches

    def test_dedupe_keeps_deals_purpose(self):
        out = discover.dedupe([{"url": "https://a.example.com/products/x", "purpose": "sellers"},
                               {"url": "https://a.example.com/products/x", "purpose": "deals"}])
        self.assertEqual(out[0]["purpose"], "deals")


class SellerFeeds(unittest.TestCase):
    def test_a_news_site_links_to_itself_are_not_leads(self):
        rss = ('<?xml version="1.0"?><rss version="2.0"><channel><item><title>New zine out</title>'
               '<link>https://news.example.com/2026/10/zine</link><pubDate>Tue, 27 Oct 2026 08:00:00 GMT</pubDate>'
               '<description>&lt;a href="https://news.example.com/tag/zines"&gt;more&lt;/a&gt; '
               '&lt;a href="https://acme-games.com/shop/zine"&gt;buy&lt;/a&gt;</description></item></channel></rss>')
        config = {**CONFIG, "feeds": [{"id": "news", "url": "https://news.example.com/feed/", "purpose": "sellers"}]}
        leads, rows = discover.collect(config, "2026-10-27", lambda u: rss.encode())
        self.assertEqual([(l["url"], l["purpose"]) for l in leads], [("https://acme-games.com/shop/zine", "sellers")])
