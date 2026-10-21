import pathlib
import tempfile

from scraper import common

# Tests never write to the real list of sites that block us.
common.BLOCKED_SITES = pathlib.Path(tempfile.mkdtemp()) / "blocked-sites.json"
