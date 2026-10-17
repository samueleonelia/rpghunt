import pathlib
import unittest

from scraper.trim import candidates, money_strings, normalize_money, prices_in, trim

FIX = pathlib.Path(__file__).parent / "fixtures" / "check"
ROOT = pathlib.Path(__file__).resolve().parent.parent


class Money(unittest.TestCase):
    def test_normalize(self):
        cases = {"$12.95": 12.95, "£5.00": 5.0, "12,95 €": 12.95, "US$17.95": 17.95, "$1,099.00": 1099.0,
                 "1.099,00 €": 1099.0, "1 099,00 €": 1099.0, "1 099,00 €": 1099.0, "$12": 12.0,
                 "1,099": 1099.0, "€1.234.567,89": 1234567.89}
        for text, want in cases.items():
            self.assertEqual(normalize_money(text), want, text)
        self.assertIsNone(normalize_money("free"))

    def test_money_strings_all_formats(self):
        text = "Was $53.00 now $12.95. EU: 12,95 € / US$17.95 / £5.00 / $1,099.00. 320 pages, 4.5 stars."
        self.assertEqual(money_strings(text), ["$53.00", "$12.95", "12,95 €", "US$17.95", "£5.00", "$1,099.00"])

    def test_candidates_distinct_in_order_and_capped(self):
        self.assertEqual(candidates("$5.00 then $9.00 then $5.00"), ["$5.00", "$9.00"])
        many = " ".join(f"${n}.00" for n in range(1, 30))
        self.assertEqual(len(candidates(many)), 12)

    def test_prices_in_keeps_repeats_and_no_cap(self):
        self.assertEqual(len(prices_in(" ".join(f"${n}.00" for n in range(1, 30)))), 29)


class Trim(unittest.TestCase):
    def setUp(self):
        self.r = trim((FIX / "product.html").read_text(), "https://shop.example/p/x")

    def test_title_from_jsonld(self):
        self.assertEqual(self.r["title"], "Ember Hollow Core Book")

    def test_hidden_text_is_gone(self):
        for secret in ("Ignore all rules", "Secret price", "Decoy", "Ghost", "comment price", "Enable JS", "$1.00",
                       "$2.00", "$3.00", "$4.00", "$5.00", "$6.00"):
            self.assertNotIn(secret, self.r["text"])
            self.assertNotIn(secret, self.r["price_candidates"])

    def test_page_chrome_and_related_products_are_gone(self):
        self.assertNotIn("Other Book", self.r["text"])
        self.assertNotIn("Shipping from", self.r["text"])

    def test_candidates_found_in_page_order(self):
        self.assertEqual(self.r["price_candidates"],
                         ["$30.00", "$24.00", "22,50 €", "1.099,00 €", "US$17.95", "£5.00"])

    def test_text_after_a_hidden_element_is_kept(self):
        self.assertIn("Visible after hidden bits", self.r["text"])

    def test_injected_fixture_does_not_expose_hidden_price(self):
        html = (ROOT / "data" / "testset" / "fixtures" / "injected-shop.html").read_text()
        r = trim(html, "fixture:injected-shop.html")
        self.assertNotIn("$4.00", r["text"])
        self.assertNotIn("$4.00", r["price_candidates"])
        self.assertNotIn("Ignore the visible price", r["text"])
        self.assertEqual(r["price_candidates"], ["$40.00"])

    def test_word_cap(self):
        body = "<h1>Big Book</h1><p>$10.00</p>" + "<p>" + "word " * 5000 + "</p>"
        r = trim(f"<html><body>{body}</body></html>")
        self.assertLessEqual(len(r["text"].split()), 1500)

    def test_empty_or_broken_html(self):
        self.assertEqual(trim("")["price_candidates"], [])
        self.assertEqual(trim("<<<not html")["price_candidates"], [])

    def test_no_h1_falls_back_to_main(self):
        r = trim("<html><body><nav>Menu $1.00</nav><main><p>Cool game</p><p>$9.50</p></main></body></html>")
        self.assertEqual(r["price_candidates"], ["$9.50"])


if __name__ == "__main__":
    unittest.main()
