import base64
import json
import unittest
from unittest import mock

from scraper.common import FetchError
from scraper.readers import bigcommerce as bc

SHOP = {"id": "gamenerdz", "name": "GameNerdz", "currency": "USD", "recipe": {"deals_url": "https://www.gamenerdz.com/deals"}}


def page(items, key="bodl_v1_product_category_viewed"):
    blob = base64.b64encode(json.dumps({"events": [{key: {"line_items": items}}]}).encode()).decode()
    return f'<html><script>window.bodl = JSON.parse(decodeBase64("{blob}"));</script></html>'


def item(pid, name, now, was=None):
    return {"product_id": str(pid), "product_name": name, "purchase_price": now, "retail_price": was,
            "brand_name": "Brand", "sku": f"S{pid}", "category_names": ["Deals"], "currency": "USD"}


class Resp:
    def __init__(self, html):
        self.body = html.encode()


class BigCommerce(unittest.TestCase):
    def read(self, pages):
        def fake(url):
            n = int(url.rsplit("page=", 1)[1])
            if isinstance(pages.get(n), Exception):
                raise pages[n]
            return Resp(pages.get(n, page([])))
        with mock.patch.object(bc, "fetch", fake):
            return bc.read_with_stats(SHOP)

    def test_visible_discounts_become_deals_hidden_prices_never(self):
        deals, stats = self.read({1: page([
            item(1, "Village: Big Box (On Sale)", 59.97, 89.99),
            item(2, "Card Pack (2023) (Add to cart to see price)", 5.0),
            item(3, "Full price thing", 10.0, 10.0),
            item(4, "No normal price", 10.0)])})
        self.assertEqual([(d["title"], d["price_now"], d["price_was"]) for d in deals], [("Village: Big Box", 59.97, 89.99)])
        self.assertEqual(deals[0]["url"], "https://www.gamenerdz.com/products.php?productId=1")
        self.assertEqual(deals[0]["source"], "bigcommerce-data")
        self.assertEqual((stats["items_read"], stats["hidden_price"], stats["pages"]), (4, 1, 1))

    def test_reads_pages_until_an_empty_list(self):
        deals, stats = self.read({1: page([item(1, "A", 1.0, 2.0)]), 2: page([item(2, "B", 1.0, 2.0)]), 3: page([])})
        self.assertEqual((len(deals), stats["pages"]), (2, 2))
        self.assertNotIn("stopped_early", stats)

    def test_a_page_without_data_is_reported_not_silent(self):
        _, stats = self.read({1: page([item(1, "A", 1.0, 2.0)]), 2: "<html>no data</html>"})
        self.assertIn("no embedded product data", stats["stopped_early"])
        with self.assertRaises(FetchError):
            self.read({1: "<html>no data</html>"})

    def test_a_failed_later_page_is_reported(self):
        _, stats = self.read({1: page([item(1, "A", 1.0, 2.0)]), 2: FetchError("blocked", "u", "HTTP 403")})
        self.assertIn("could not be read", stats["stopped_early"])


if __name__ == "__main__":
    unittest.main()
