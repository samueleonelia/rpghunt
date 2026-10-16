"""Merge agent research into the website's data file, checking every link live.

Reads data/raw/batch-*.json (written by research agents) plus any
data/raw/fix-*.json (extra candidate links for existing games), opens every
URL, drops dead ones, and writes docs/data/games.json for the website plus
data/link-report.json listing what was dropped or looked suspicious.

Run: python3 scripts/build_data.py
"""
import concurrent.futures
import datetime
import json
import pathlib
import re
import ssl
import unicodedata
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
OUT = ROOT / "docs" / "data" / "games.json"
REPORT = ROOT / "data" / "link-report.json"

TAGS = set("""fantasy dark-fantasy sci-fi cyberpunk space horror cosmic-horror
post-apocalyptic superhero historical mythology steampunk western urban-fantasy
mystery comedy mecha cozy generic osr narrative crunchy""".split())
LINK_TYPES = {"official", "store", "free"}
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
# Sites behind bot protection answer these even when the page exists.
BLOCKED = {401, 403, 406, 429, 503}
SSL_CTX = ssl.create_default_context()


class Redirects(urllib.request.HTTPRedirectHandler):
    """Python 3.9 does not follow 308 redirects on its own."""
    def http_error_308(self, req, fp, code, msg, headers):
        return self.http_error_302(req, fp, 302, msg, headers)


OPENER = urllib.request.build_opener(Redirects, urllib.request.HTTPSHandler(context=SSL_CTX))


def slugify(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def name_words(game):
    """Distinctive words from the game's names, to spot links to the wrong page."""
    words = set()
    for n in (game.get("name"), game.get("name_it")):
        for w in re.findall(r"[a-z0-9]+", slugify(n or "").replace("-", " ")):
            if len(w) > 3 and w not in {"game", "role", "playing", "roleplaying", "edition", "gioco", "ruolo"}:
                words.add(w)
    return words


def check(url, words):
    """Return (status, reason). status: ok | unverified | dead."""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
        "Accept-Language": "en,it;q=0.8",
    })
    try:
        with OPENER.open(req, timeout=20) as resp:
            if "pdf" in resp.headers.get("Content-Type", ""):
                return "ok", ""  # a PDF that loads is fine; we cannot scan it for the name
            body = resp.read(400_000).decode("utf-8", "ignore").lower()
            final = resp.geturl().lower()
    except urllib.error.HTTPError as e:
        if e.code in BLOCKED:
            return "unverified", f"HTTP {e.code} (bot protection)"
        return "dead", f"HTTP {e.code}"
    except Exception as e:  # DNS failure, timeout, SSL error
        return "dead", type(e).__name__
    plain = re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", body + " " + final))
    if words and not any(w in plain for w in words):
        return "unverified", "page does not mention the game"
    return "ok", ""


def main():
    games = []
    for f in sorted(RAW.glob("batch-*.json")):
        games.extend(json.loads(f.read_text()))
    by_qid = {g["wikidata"]: g for g in games}
    for f in sorted(RAW.glob("fix-*.json")):
        for fix in json.loads(f.read_text()):
            g = by_qid[fix["wikidata"]]
            g.setdefault("candidate_links", []).extend(fix.get("candidate_links") or [])

    jobs = []
    for g in games:
        words = name_words(g)
        known = {l["url"] for l in g.get("links") or []}
        for link in g.get("links") or []:
            jobs.append((g, link, words))
        # Links agents saw in search results but could not open: keep only if they load.
        for link in g.pop("candidate_links", None) or []:
            if link.get("url") and link["url"] not in known:
                known.add(link["url"])
                link["_candidate"] = True
                g.setdefault("links", []).append(link)
                jobs.append((g, link, words))
        ie = g.get("italian_edition")
        if ie and ie.get("url"):
            jobs.append((g, ie, words))

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(lambda j: check(j[1]["url"], j[2]), jobs))

    report = {"dead": [], "unverified": [], "rejected_candidates": []}
    for (g, link, _), (status, reason) in zip(jobs, results):
        candidate = link.pop("_candidate", False)
        link["verified"] = status == "ok"
        if candidate and status != "ok":
            link["_drop"] = True  # a candidate must fully pass, no benefit of the doubt
            report["rejected_candidates"].append({"game": g["name"], "url": link["url"], "reason": reason})
            continue
        if status == "dead":
            link["_drop"] = True
        if status != "ok":
            report[status].append({"game": g["name"], "url": link["url"], "reason": reason})

    today = datetime.date.today().isoformat()
    out, problems = [], []
    for g in games:
        g["links"] = [l for l in g.get("links") or [] if not l.pop("_drop", False)
                      and l.get("type") in LINK_TYPES]
        ie = g.get("italian_edition")
        if ie and ie.pop("_drop", False):
            ie["url"] = None
        bad_tags = [t for t in g.get("tags") or [] if t not in TAGS]
        if bad_tags:
            problems.append(f"{g['name']}: unknown tags {bad_tags}")
        g["tags"] = [t for t in g.get("tags") or [] if t in TAGS]
        g["id"] = slugify(g["name"])
        g["checked"] = today
        g.pop("sources", None)  # research trail stays in data/raw, not on the site
        out.append(g)

    out.sort(key=lambda g: g["name"].lower())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1))

    ok = sum(1 for _, r in zip(jobs, results) if r[0] == "ok")
    print(f"{len(out)} games, {len(jobs)} links: {ok} ok, "
          f"{len(report['unverified'])} unverified (kept), {len(report['dead'])} dead (dropped), "
          f"{len(report['rejected_candidates'])} candidates rejected")
    no_links = [g["name"] for g in out if not g["links"]]
    if no_links:
        print("No working links:", ", ".join(no_links))
    for p in problems:
        print(p)


if __name__ == "__main__":
    main()
