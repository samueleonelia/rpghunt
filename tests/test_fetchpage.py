import json
import pathlib
import unittest
from unittest import mock

from scraper import fetchpage
from scraper.common import FetchError

FIX = pathlib.Path(__file__).parent / "fixtures"
URL = "https://shop.example/sale"


class Describe(unittest.TestCase):
    def setUp(self):
        self.d = fetchpage.describe((FIX / "agent" / "listing_page.html").read_text(), URL, 200)

    def test_shape(self):
        self.assertEqual(set(self.d), {"url", "status", "title", "text", "price_candidates", "price_elements", "links"})
        self.assertEqual((self.d["url"], self.d["status"]), (URL, 200))
        self.assertIn("Sale", self.d["title"])
        json.dumps(self.d)    # must be printable

    def test_price_candidates_and_hidden_text_left_out(self):
        self.assertEqual(self.d["price_candidates"], ["$30.00", "$24.00", "$40.00", "$28.00"])
        self.assertNotIn("$1.00", self.d["text"])
        self.assertNotIn("Hidden Ghost", self.d["text"])

    def test_price_elements_show_markup_for_recipes(self):
        rows = {r["text"]: r for r in self.d["price_elements"]}
        self.assertTrue(rows["$30.00"]["struck"])
        self.assertFalse(rows["$24.00"]["struck"])
        self.assertEqual(rows["$24.00"]["css"], "span.price-now")
        self.assertIn("li.product-card", rows["$24.00"]["path"])
        self.assertNotIn("$1.00", rows)

    def test_links_same_site_deduped_without_cart_login_or_hidden(self):
        hrefs = [l["href"] for l in self.d["links"]]
        self.assertEqual(hrefs, ["https://shop.example/", "https://shop.example/products/ember-hollow",
                                 "https://shop.example/products/mist-marches"])
        first = self.d["links"][1]
        self.assertEqual((first["text"], first["css"]), ("Ember Hollow Core Book", "a.card-title"))

    def test_links_capped(self):
        html = "<body>" + "".join(f'<a href="/products/p{i}">p{i}</a>' for i in range(400)) + "</body>"
        self.assertEqual(len(fetchpage.describe(html, URL)["links"]), fetchpage.MAX_LINKS)

    def test_css_matches_skip_hidden(self):
        d = fetchpage.describe((FIX / "agent" / "listing_page.html").read_text(), URL, 200, "a.card-title")
        self.assertEqual([m["href"] for m in d["css_matches"]], ["/products/ember-hollow", "/products/mist-marches"])

    def test_bad_selector_is_reported_not_raised(self):
        d = fetchpage.describe("<body><p>x</p></body>", URL, 200, "a[[")
        self.assertEqual(d["css_matches"], [])
        self.assertIn("css_error", d)


class Main(unittest.TestCase):
    def run_main(self, fetcher, url):
        with mock.patch.object(fetchpage, "fetch", fetcher), mock.patch("builtins.print") as pr:
            code = fetchpage.main([url])
        return code, json.loads(pr.call_args[0][0])

    def test_goes_through_fetch_and_prints_json(self):
        html = (FIX / "agent" / "listing_page.html").read_text()
        resp = mock.Mock(body=html.encode(), encoding="utf-8", status=200, url="https://shop.example/sale?x=1")
        code, out = self.run_main(lambda u: resp, URL)
        self.assertEqual((code, out["url"], out["status"]), (0, "https://shop.example/sale?x=1", 200))

    def test_blocked_page_is_an_error_json(self):
        def blocked(url):
            raise FetchError("blocked", url, "HTTP 403")
        code, out = self.run_main(blocked, URL)
        self.assertEqual((code, out["error"]), (1, "blocked"))

    def test_only_http_urls(self):
        code, out = self.run_main(lambda u: None, "file:///etc/passwd")
        self.assertEqual((code, out["error"]), (1, "bad_url"))


if __name__ == "__main__":
    unittest.main()
