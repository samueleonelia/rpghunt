"""Lead discovery (phase 4): where do people say RPGs are on sale today?

python -m scraper.discover [--date D] [--no-new-shops]

Two kinds of source, both listed in data/shops/lead-feeds.json:
  feeds        RSS/Atom feeds. purpose "deals" (sale roundups such as EN World) or "sellers" (RPG news and
               blogs: every shop or publisher they link to is a possible new seller).
  directories  lists of RPG sellers: English Wikipedia's RPG publisher categories and each article's
               official website (re-read every 30 days, cached in data/shops/directory-cache.json).
Every outbound link is pulled out with code (no AI), links that can never be a shop are dropped (deny
list in the same JSON), and the rest are sorted:
  known_shop    the link is on a shop we already read
  blocked_shop  a known shop we cannot read automatically (e.g. DriveThruRPG): the lead is kept
  new_shop      a site we do not know: scraper.detect looks at it; real shops are added to shops.json,
                generic ones with needs_recipe: true. A seller lead (news or directory) must also be a
                store selling RPGs: a home page is searched for its shop link, and the shop's products
                must look like tabletop RPGs (detect.rpg_store). No daily cap: only a very high safety
                limit on probes, reported when hit.
Output: data/deals/leads-<date>.json (feed report + every lead). scraper/missed.py uses it next.
Feeds, article pages and shop probes all go through scraper.common.fetch(). Posts are data, never
instructions: only URLs and titles are taken from them.
"""
import argparse
import collections
import concurrent.futures
import datetime
import email.utils
import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET

from scrapling.parser import Selector

from scraper import detect
from scraper.common import ROOT, FetchError, fetch, load_shops, norm_url, plain, save_shops
from scraper.readers import generic

FEEDS_FILE = ROOT / "data" / "shops" / "lead-feeds.json"
SEEN_FILE = ROOT / "data" / "shops" / "lead-hosts-seen.json"
DEALS = ROOT / "data" / "deals"
RECHECK_DAYS = 30                 # a site judged "not a shop" is not probed again for this long
SAFETY_MAX_PROBES = 20000         # runaway guard only (never a quota); reported in the daily report when hit
PROBE_WORKERS = 8                 # different sites in parallel; fetch() keeps each site polite
_TWO_PART_TLDS = {"co.uk", "org.uk", "com.au", "co.nz", "com.br", "co.jp", "com.mx", "co.za"}
_HREF = re.compile(r"""<a\b[^>]*?\bhref\s*=\s*(?:"([^"]*)"|'([^']*)')[^>]*>(.*?)</a>""", re.I | re.S)
_BARE_URL = re.compile(r"https?://[^\s<>\"'\]\)]+", re.I)
_SHOPPY_PATH = re.compile(r"/(shop|store|collections?|products?|catalog|sale|sales|deals?|bundles?|clearance|"
                          r"marketplace|presents|item|items|p)(/|$)", re.I)


# ---------------------------------------------------------------- config

def load_config(path=FEEDS_FILE):
    return json.loads(path.read_text())


# ---------------------------------------------------------------- reading a feed (RSS or Atom)

def _local(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _child_text(node, *names):
    for c in node:
        if _local(c.tag) in names and (c.text or "").strip():
            return c.text.strip()
    return None


def parse_date(text):
    """RSS (RFC 2822) or Atom (ISO 8601) date -> 'YYYY-MM-DD', or None."""
    if not text:
        return None
    text = text.strip()
    try:
        return datetime.datetime.fromisoformat(text.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:
        return email.utils.parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        return None


def parse_feed(data):
    """RSS or Atom bytes/text -> list of {title, url, published, body}. body is the entry's HTML/text."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    root = ET.fromstring(data)
    entries = []
    for node in root.iter():
        if _local(node.tag) not in ("item", "entry"):
            continue
        link = None
        for c in node:
            if _local(c.tag) == "link":
                href = c.attrib.get("href")
                if href and c.attrib.get("rel", "alternate") == "alternate":
                    link = href
                elif not href and (c.text or "").strip():
                    link = c.text.strip()
        body = _child_text(node, "encoded", "content", "description", "summary") or ""
        entries.append({
            "title": html.unescape(_child_text(node, "title") or "").strip(),
            "url": link or _child_text(node, "guid", "id"),
            "published": parse_date(_child_text(node, "pubDate", "published", "updated", "date")),
            "body": body,
        })
    return entries


# ---------------------------------------------------------------- pulling links out of text

def _clean_url(u):
    u = html.unescape(u).strip().rstrip(".,;:!?)]}>\"'")
    return u.split("#")[0]


def extract_links(text):
    """-> [(url, link_text)] for every absolute http(s) link in an HTML or plain-text body.
    Handles bodies whose HTML is entity-escaped (Reddit Atom) and bare URLs in text."""
    if not text:
        return []
    s = html.unescape(text) if "&lt;" in text else text
    out = []
    for m in _HREF.finditer(s):
        href = m.group(1) if m.group(1) is not None else m.group(2)
        label = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", m.group(3)))).strip()
        out.append((_clean_url(href), label))
    bare = re.sub(r"<[^>]+>", " ", _HREF.sub(" ", s))     # text outside anchors and tags
    out += [(_clean_url(u), "") for u in _BARE_URL.findall(html.unescape(bare))]
    seen, result = set(), []
    for url, label in out:
        if url.lower().startswith(("http://", "https://")) and url not in seen:
            seen.add(url)
            result.append((url, label))
    return result


def article_links(page_html, selector=".message-body .bbWrapper"):
    """Outbound links of the first post on a forum/news article page (the article itself, not the
    replies). Falls back to the whole page when the selector finds nothing."""
    sel = Selector(page_html)
    blocks = sel.css(selector)
    if blocks:
        links = []
        for a in blocks[0].css("a[href]"):
            links.append((_clean_url(a.attrib["href"]), re.sub(r"\s+", " ", a.text or "").strip()))
        return [(u, t) for u, t in links if u.lower().startswith(("http://", "https://"))]
    return extract_links(page_html)


# ---------------------------------------------------------------- hosts and classes

def host_of(url):
    return urllib.parse.urlsplit(url).netloc.lower().split("@")[-1].split(":")[0].removeprefix("www.")


def registered_domain(host):
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in _TWO_PART_TLDS:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def is_denied(url, config):
    host = host_of(url)
    if not host or "." not in host:
        return True
    if any(host == d or host.endswith("." + d) for d in config["deny_domains"]):
        return True
    path = urllib.parse.urlsplit(url).path.lower()
    return path.endswith(tuple(config.get("deny_extensions", ())))


def shop_index(shops):
    """-> {registered domain: [shop, ...]} plus helper data for classify()."""
    by_reg = collections.defaultdict(list)
    for s in shops:
        by_reg[registered_domain(host_of(s["store_url"]))].append(s)
    return by_reg


def match_shop(url, shops, index=None):
    """The shop a URL belongs to, or None. Exact host first (modiphius.net and modiphius.us are two
    shops, matched by host only), then the same registered domain (store.paizo.com <-> paizo.com,
    anything.itch.io -> itch.io)."""
    index = index if index is not None else shop_index(shops)
    host = host_of(url)
    cands = index.get(registered_domain(host), [])
    for s in cands:
        if host_of(s["store_url"]) == host:
            return s
    base = [s for s in cands if host_of(s["store_url"]) == registered_domain(host)]
    if base:
        return base[0]
    if cands and len(cands) == 1:
        return cands[0]
    # several shops share the registered domain (e.g. itch.io storefronts): the platform home wins
    for s in cands:
        if s["platform"] == "itch" and host.endswith(".itch.io"):
            return next((x for x in cands if host_of(x["store_url"]) == "itch.io"), s)
    return cands[0] if cands else None


def classify(url, shops, index=None):
    """-> (class, shop or None)."""
    shop = match_shop(url, shops, index)
    if shop is None:
        return "new_shop", None
    return ("blocked_shop" if shop.get("status") == "blocked" else "known_shop"), shop


def looks_like_shop_url(url):
    return bool(_SHOPPY_PATH.search(urllib.parse.urlsplit(url).path) or generic.PRODUCT_PATH.search(urllib.parse.urlsplit(url).path))


def is_roundup_title(title, patterns):
    return any(re.search(p, title or "", re.I) for p in patterns)


# ---------------------------------------------------------------- reading all feeds

def collect(config, date, fetch_bytes=None):
    """Read every enabled feed. -> (leads, feed_report). Leads are not classified yet.
    fetch_bytes(url) -> bytes; the default goes through scraper.common.fetch()."""
    fetch_bytes = fetch_bytes or (lambda u: fetch(u).body)
    today = datetime.date.fromisoformat(date)
    leads, report = [], []
    for feed in config["feeds"]:
        max_age = feed.get("max_age_days", config.get("max_age_days", 14))
        purpose = feed.get("purpose", "deals")
        row = {"id": feed["id"], "url": feed["url"], "purpose": purpose, "status": "ok", "entries": 0, "in_window": 0,
               "articles_read": 0, "links": 0, "error": None}
        report.append(row)
        if not feed.get("enabled", True):
            row["status"] = "disabled"
            continue
        try:
            entries = parse_feed(fetch_bytes(feed["url"]))
        except FetchError as e:
            row.update(status="blocked" if e.kind in ("blocked", "robots") else "error", error=str(e))
            continue
        except ET.ParseError as e:
            row.update(status="error", error=f"feed is not readable XML: {e}")
            continue
        row["entries"] = len(entries)
        articles = 0
        for e in entries:
            if e["published"] and (today - datetime.date.fromisoformat(e["published"])).days > max_age:
                continue
            if e["published"] and e["published"] > date:
                continue
            row["in_window"] += 1
            found = [(u, t, "feed") for u, t in extract_links(e["body"])]
            # fetch_articles: true = sale roundups only (by title); "all" = every recent post (seller feeds,
            # whose RSS holds only a summary). The per-feed article limit is a runaway guard, set high.
            wanted = feed.get("fetch_articles") == "all" or (
                feed.get("fetch_articles") and is_roundup_title(e["title"], config["article_title_patterns"]))
            if wanted and e["url"] and articles < config.get("max_article_fetches_per_feed", 200):
                articles += 1
                try:
                    page = fetch_bytes(e["url"]).decode("utf-8", "ignore")
                    found += [(u, t, "article") for u, t in article_links(page, feed.get("article_selector", ".bbWrapper"))]
                    row["articles_read"] += 1
                except FetchError as err:
                    row.setdefault("article_errors", []).append(str(err))
            own = {registered_domain(host_of(u)) for u in (feed["url"], e["url"] or "") if u}
            for url, label, via in found:
                if is_denied(url, config) or (purpose == "sellers" and registered_domain(host_of(url)) in own):
                    continue                    # a news site's links to its own pages are not sellers
                row["links"] += 1
                leads.append({"url": url, "link_text": label, "post_title": e["title"], "post_url": e["url"],
                              "feed": feed["id"], "published": e["published"], "via": via, "purpose": purpose})
    return leads, report


DIRECTORY_CACHE = ROOT / "data" / "shops" / "directory-cache.json"
DIRECTORY_REFRESH_DAYS = 30       # a directory changes slowly: re-read it this often, not every day
WIKIPEDIA = "https://en.wikipedia.org"
_WIKI_LINK = re.compile(r'<li><a href="/wiki/([^"#:?]+)" title="([^"]*)"')
_WIKI_SUBCAT = re.compile(r'href="/wiki/(Category:[^"#?]+)"')
_INFOBOX = re.compile(r'<table class="infobox.*?</table>', re.S)
_WEBSITE_ROW = re.compile(r'>\s*Website\s*</th>\s*<td[^>]*>(.*?)</td>', re.S | re.I)
_HREF_EXT = re.compile(r'href="(https?://[^"]+)"')


def wiki_category(page):
    """Category page -> ([(article, title)], [subcategory]). Only what the page shows: the next-page link
    lives under /w/, which robots.txt does not allow."""
    pages_part = page.split('id="mw-pages"', 1)[1] if 'id="mw-pages"' in page else ""
    subs_part = page.split('id="mw-subcategories"', 1)[1].split('id="mw-pages"', 1)[0] if 'id="mw-subcategories"' in page else ""
    return _WIKI_LINK.findall(pages_part), _WIKI_SUBCAT.findall(subs_part)


def wiki_website(page):
    """An article's official website from its infobox ("Website" row), or None."""
    box = _INFOBOX.search(page or "")
    if not box:
        return None
    row = _WEBSITE_ROW.search(box.group(0))
    m = _HREF_EXT.search(row.group(1)) if row else None
    return html.unescape(m.group(1)) if m else None


def read_wikipedia_category(d, fetch_text):
    """-> [{site, label}] for every article in the categories (and the subcategories whose name matches
    d["follow"]) that has an official website in its infobox."""
    follow = re.compile(d.get("follow", "$^"), re.I)
    todo, done, articles = list(d["categories"]), set(), {}
    while todo:
        cat = todo.pop(0)
        if cat in done:
            continue
        done.add(cat)
        pages, subs = wiki_category(fetch_text(f"{WIKIPEDIA}/wiki/{cat}"))
        for slug, title in pages:
            articles.setdefault(slug, title)
        todo += [c for c in subs if follow.search(urllib.parse.unquote(c).replace("_", " ")) and c not in done]
    sites = []
    for slug, title in articles.items():
        try:
            site = wiki_website(fetch_text(f"{WIKIPEDIA}/wiki/{slug}"))
        except FetchError:
            continue
        if site:
            sites.append({"site": site, "label": html.unescape(title)})
    return sites


def collect_directories(config, date, fetch_bytes=None, cache_path=None):
    """Read every enabled directory. -> (leads, report rows). Each website listed becomes a seller lead.
    type "wikipedia_category": English Wikipedia category pages and their articles' infobox websites
    (robots.txt allows /wiki/ pages; Wikidata's query service and API are not allowed to bots).
    A directory is re-read every DIRECTORY_REFRESH_DAYS; in between, its cached list is used."""
    fetch_bytes = fetch_bytes or (lambda u: fetch(u).body)
    fetch_text = lambda u: fetch_bytes(u).decode("utf-8", "ignore")
    cache_path = cache_path or DIRECTORY_CACHE
    try:
        cache = json.loads(cache_path.read_text())
    except (OSError, ValueError):
        cache = {}
    leads, report, changed = [], [], False
    for d in config.get("directories", []):
        row = {"id": d["id"], "url": f"{WIKIPEDIA}/wiki/{d['categories'][0]}" if d.get("categories") else "",
               "purpose": "sellers", "status": "ok", "entries": 0, "in_window": 0, "articles_read": 0, "links": 0,
               "error": None, "kind": "directory"}
        report.append(row)
        if not d.get("enabled", True):
            row["status"] = "disabled"
            continue
        hit = cache.get(d["id"])
        fresh = hit and (datetime.date.fromisoformat(date) - datetime.date.fromisoformat(hit["date"])).days < DIRECTORY_REFRESH_DAYS
        if fresh:
            sites, row["cached_from"] = hit["sites"], hit["date"]
        else:
            try:
                if d.get("type") != "wikipedia_category":
                    raise ValueError(f"unknown directory type {d.get('type')!r}")
                sites = read_wikipedia_category(d, fetch_text)
            except FetchError as e:
                row.update(status="blocked" if e.kind in ("blocked", "robots") else "error", error=str(e))
                if not hit:
                    continue
                sites = hit["sites"]                      # an old list beats none
            except Exception as e:                       # one odd directory must not stop discovery
                row.update(status="error", error=f"directory not readable: {type(e).__name__}: {e}")
                if not hit:
                    continue
                sites = hit["sites"]
            else:
                cache[d["id"]] = {"date": date, "sites": sites}
                changed = True
        row["entries"] = row["in_window"] = len(sites)
        for r in sites:
            site = r.get("site")
            if not site or not site.lower().startswith(("http://", "https://")) or is_denied(site, config):
                continue
            row["links"] += 1
            leads.append({"url": site, "link_text": r.get("label") or "", "post_title": d.get("name", d["id"]),
                          "post_url": None, "feed": d["id"], "published": date, "via": "directory", "purpose": "sellers"})
    if changed:
        try:
            cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        except OSError:
            pass
    return leads, report


def dedupe(leads):
    """One lead per norm_url (first one wins); `mentions` counts the repeats."""
    seen, out = {}, []
    for l in leads:
        key = norm_url(l["url"])
        if key in seen:
            seen[key]["mentions"] += 1
            if l.get("purpose", "deals") == "deals":          # a sale roundup naming it counts for misses
                seen[key]["purpose"] = "deals"
            continue
        l = dict(l, mentions=1)
        seen[key] = l
        out.append(l)
    return out


# ---------------------------------------------------------------- new shops

def _load_seen():
    try:
        return json.loads(SEEN_FILE.read_text())
    except (OSError, ValueError):
        return {}


def unique_id(base, taken):
    cand, n = base or "shop", 2
    while cand in taken:
        cand, n = f"{base}-{n}", n + 1
    return cand


def find_new_shops(leads, shops, config, date, detector=detect.detect, seen=None, seller=detect.find_seller, stats=None):
    """Probe the sites behind new_shop leads. -> (entries to add, notes {host: text}, seen).
    Sale-roundup leads (purpose "deals"): a host is added when it is a real store (Shopify / WooCommerce /
    itch), or when its link path looks like a shop page.
    Seller leads (purpose "sellers": RPG news, directories): detect.find_seller must find a web store that
    sells English tabletop RPGs (a home page is searched for its shop link).
    Others are remembered as "not a shop" for RECHECK_DAYS and not probed again. Probes run in parallel
    (different sites; fetch() keeps each site polite). stats, when given, gets probes / safety_limit_hit."""
    seen = {} if seen is None else seen
    stats = {} if stats is None else stats
    by_host = collections.OrderedDict()
    for l in leads:
        if l["class"] == "new_shop":
            by_host.setdefault(host_of(l["url"]), []).append(l)
    ranked = sorted(by_host.items(), key=lambda kv: -len(kv[1]))
    notes, todo = {}, []
    limit = config.get("safety_max_probes_per_day", SAFETY_MAX_PROBES)
    for host, group in ranked:
        prev = seen.get(host)
        if prev and (datetime.date.fromisoformat(date) - datetime.date.fromisoformat(prev["date"])).days < RECHECK_DAYS:
            notes[host] = f"skipped: judged '{prev['result']}' on {prev['date']}"
            continue
        if len(todo) >= limit:
            notes[host] = f"skipped: safety limit of {limit} probes a day reached"
            stats["safety_limit_hit"] = f"{limit} probes a day"
            continue
        todo.append((host, group))
    stats["probes"] = len(todo)

    def probe(item):
        host, group = item
        sample = group[0]["url"]
        origin = f"{urllib.parse.urlsplit(sample).scheme}://{urllib.parse.urlsplit(sample).netloc}/"
        try:
            entry = detector(origin)
            if all(l.get("purpose") == "sellers" for l in group):
                known = any(l.get("via") == "directory" for l in group)
                entry, why = seller(entry, origin.rstrip("/"), detector, known=known)
                return host, group, entry, why, "added" if entry else "not a seller"
        except Exception as e:          # one odd site must not stop discovery
            return host, group, None, f"probe failed: {type(e).__name__}", "probe failed"
        shoppy = any(looks_like_shop_url(l["url"]) for l in group)
        real_store = entry["platform"] in ("shopify", "woocommerce", "itch", "bundleofholding", "humble")
        if not real_store and not shoppy:
            return host, group, None, f"not added: {entry['platform']} site and the link is not a shop page", "not a shop"
        return host, group, entry, None, "added"

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(PROBE_WORKERS, len(todo)))) as pool:
        results = list(pool.map(probe, todo))

    taken = {s["id"] for s in shops}
    added = []
    for host, group, entry, why, result in results:           # same order as `ranked`: ids stay stable
        store_host = host_of(entry["store_url"]) if entry is not None else None
        if entry is not None and (store_host in {host_of(s["store_url"]) for s in shops + added} or (
                store_host != host and match_shop(entry["store_url"], shops + added, shop_index(shops + added)))):
            # two links can lead to one store (a publisher's home page and its shop subdomain)
            notes[host] = f"not added: its store {entry['store_url']} is a shop we read already"
            seen[host] = {"date": date, "result": "known store"}
            continue
        if entry is None:
            notes[host] = why if why and why.startswith(("not added", "probe failed")) else f"not added: {why}"
            seen[host] = {"date": date, "result": result}
            continue
        feeds = sorted({l["feed"] for l in group})
        entry.update(id=unique_id(entry["id"], taken), added=date, added_via=f"lead {feeds[0]} {date}")
        if entry["platform"] == "generic":
            entry["needs_recipe"] = True
        taken.add(entry["id"])
        added.append(entry)
        notes[host] = f"added as {entry['id']} ({entry['platform']}, {entry['status']})" + (f": {why}" if why else "")
        seen[host] = {"date": date, "result": "added"}
    return added, notes, seen


# ---------------------------------------------------------------- the run

def run(date, config=None, fetch_bytes=None, save_new_shops=True, detector=detect.detect, shops=None, write=True,
        seller=None):
    """Whole discovery. -> the leads document (also written to data/deals/leads-<date>.json)."""
    config = config or load_config()
    shops = shops if shops is not None else load_shops()
    raw_leads, feeds = collect(config, date, fetch_bytes)
    dir_leads, dirs = collect_directories(config, date, fetch_bytes)
    leads = dedupe(raw_leads + dir_leads)
    feeds = feeds + dirs
    index = shop_index(shops)
    for l in leads:
        cls, shop = classify(l["url"], shops, index)
        l.update({"class": cls, "shop_id": shop["id"] if shop else None, "shop_status": shop.get("status") if shop else None})

    seen = _load_seen()
    stats = {}
    added, notes, seen = find_new_shops(leads, shops, config, date, detector, seen, stats=stats,
                                        **({} if seller is None else {"seller": seller}))
    if added:
        index = shop_index(shops + added)
        for l in leads:
            if l["class"] == "new_shop":
                shop = match_shop(l["url"], added, shop_index(added))
                if shop:
                    l["shop_id"], l["shop_status"] = shop["id"], shop["status"]
    for l in leads:
        if l["class"] == "new_shop" and not l["shop_id"]:
            l["note"] = notes.get(host_of(l["url"]))

    path = DEALS / f"leads-{date}.json"
    carried = []
    if write and path.exists():           # a second run the same day keeps the shops the first one added
        try:
            old = json.loads(path.read_text())
            have = {s["id"] for s in added}
            carried = [s for s in old.get("new_shops", []) if s["id"] not in have]
        except ValueError:
            pass
    new_shops = [{"id": s["id"], "name": s["name"], "store_url": s["store_url"], "platform": s["platform"],
                  "status": s["status"], "needs_recipe": bool(s.get("needs_recipe")), "added_via": s["added_via"],
                  "saved": save_new_shops}
                 for s in added] + carried
    counts = collections.Counter(l["class"] for l in leads)
    doc = {
        "date": date, "feeds": feeds,
        "counts": {"leads": len(leads), "known_shop": counts["known_shop"], "blocked_shop": counts["blocked_shop"],
                   "new_shop": counts["new_shop"], "new_shops_added": len(new_shops),
                   "seller_leads": sum(1 for l in leads if l.get("purpose") == "sellers"),
                   "new_sites": len({host_of(l["url"]) for l in leads if l["class"] == "new_shop"}),
                   "sites_probed": stats.get("probes", 0),
                   "per_feed": dict(collections.Counter(l["feed"] for l in leads))},
        "safety_limit_hit": stats.get("safety_limit_hit"),
        "new_shops": new_shops, "new_shop_notes": notes, "leads": leads,
    }
    if write:
        DEALS.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n")
        if save_new_shops:
            if added:
                fresh = load_shops()           # reload: never overwrite edits made during the run
                have = {s["id"] for s in fresh}
                save_shops(fresh + [s for s in added if s["id"] not in have])
            SEEN_FILE.write_text(json.dumps(seen, indent=1, sort_keys=True) + "\n")
    doc["_added_entries"] = added if save_new_shops else []
    return doc


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m scraper.discover")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--no-new-shops", action="store_true", help="look at new sites but do not save them to shops.json")
    args = ap.parse_args(argv)
    doc = run(args.date, save_new_shops=not args.no_new_shops)
    for f in doc["feeds"]:
        print(f"  feed {f['id']}: {f['status']}, {f['entries']} entries ({f['in_window']} recent), "
              f"{f['articles_read']} articles read, {f['links']} links" + (f", {f['error']}" if f["error"] else ""))
    c = doc["counts"]
    print(f"{c['leads']} leads: {c['known_shop']} known shop, {c['blocked_shop']} blocked shop, {c['new_shop']} new shop; "
          f"{c['new_shops_added']} new shops added")
    for s in doc["new_shops"]:
        print(f"  new shop {s['id']}: {s['platform']} ({s['status']}){' needs recipe' if s['needs_recipe'] else ''} {s['store_url']}")
    print(f"wrote data/deals/leads-{args.date}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
