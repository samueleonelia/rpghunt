import json
import pathlib
import tempfile
import unittest
from unittest import mock

from scraper import common


class NoteBlock(unittest.TestCase):
    def setUp(self):
        self.path = pathlib.Path(tempfile.mkdtemp()) / "blocked-sites.json"
        p = mock.patch.object(common, "BLOCKED_SITES", self.path)
        p.start()
        self.addCleanup(p.stop)

    def test_one_row_per_host_with_first_and_last_seen(self):
        common.note_block("https://www.dmsguild.com/product/1/x", "HTTP 403", "2026-10-20")
        common.note_block("https://dmsguild.com/product/2/y", "robots.txt disallows us", "2026-10-21")
        row = json.loads(self.path.read_text())["dmsguild.com"]
        self.assertEqual((row["first_seen"], row["last_seen"]), ("2026-10-20", "2026-10-21"))
        self.assertEqual(row["reasons"], {"HTTP 403": "2026-10-20", "robots.txt disallows us": "2026-10-21"})

    def test_never_fetched_host_is_noted_without_a_request(self):
        with mock.patch.object(common.Fetcher, "get", side_effect=AssertionError("no request")):
            with self.assertRaises(common.FetchError):
                common.fetch("https://www.drivethrurpg.com/product/1")
        self.assertIn("drivethrurpg.com", json.loads(self.path.read_text()))

    def test_bot_wall_page_served_with_200_is_a_block(self):
        self.assertEqual(common.bot_wall_title(b"<html><title>Just a moment...</title>"), "just a moment...")
        self.assertIsNone(common.bot_wall_title(b"<html><title>Dungeon Delvers Core Rulebook</title>"))
        self.assertIsNone(common.bot_wall_title(b'{"products": []}'))


if __name__ == "__main__":
    unittest.main()
