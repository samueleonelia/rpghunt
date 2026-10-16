"""Download the seed list of tabletop RPGs from Wikidata into data/seed.json.

Wikidata is CC0 (free to reuse). This gives us names, publishers, designers,
years and official websites. Agents fill in the rest later.

Run: python3 scripts/fetch_seed.py
"""
import json
import pathlib
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "seed.json"

# Q1643932 = "tabletop role-playing game". Includes its subclasses.
QUERY = """
SELECT ?g ?en ?it ?links ?article
  (GROUP_CONCAT(DISTINCT ?pubL; separator="|") AS ?publishers)
  (GROUP_CONCAT(DISTINCT ?desL; separator="|") AS ?designers)
  (GROUP_CONCAT(DISTINCT ?genL; separator="|") AS ?genres)
  (GROUP_CONCAT(DISTINCT STR(?site); separator="|") AS ?sites)
  (MIN(YEAR(?date)) AS ?year)
WHERE {
  ?g wdt:P31/wdt:P279* wd:Q1643932 ;
     wikibase:sitelinks ?links .
  OPTIONAL { ?g rdfs:label ?en FILTER(lang(?en) = "en") }
  OPTIONAL { ?g rdfs:label ?it FILTER(lang(?it) = "it") }
  OPTIONAL { ?article schema:about ?g ; schema:isPartOf <https://en.wikipedia.org/> }
  OPTIONAL { ?g wdt:P123 ?pub . ?pub rdfs:label ?pubL FILTER(lang(?pubL) = "en") }
  OPTIONAL { ?g wdt:P287|wdt:P50|wdt:P170 ?des . ?des rdfs:label ?desL FILTER(lang(?desL) = "en") }
  OPTIONAL { ?g wdt:P136 ?gen . ?gen rdfs:label ?genL FILTER(lang(?genL) = "en") }
  OPTIONAL { ?g wdt:P856 ?site }
  OPTIONAL { ?g wdt:P577|wdt:P571 ?date }
}
GROUP BY ?g ?en ?it ?links ?article
"""


def split(value):
    return [v for v in value.split("|") if v] if value else []


def main():
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode({"query": QUERY})
    req = urllib.request.Request(url, headers={
        "Accept": "application/sparql-results+json",
        "User-Agent": "rpgArchive/0.1 (personal RPG directory project)",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        rows = json.load(resp)["results"]["bindings"]

    games = {}
    for r in rows:
        get = lambda k: r[k]["value"] if k in r else None
        qid = get("g").rsplit("/", 1)[-1]
        name = get("en") or get("it")
        if not name or qid in games:
            continue
        year = get("year")
        games[qid] = {
            "wikidata": qid,
            "name": name,
            "name_it": get("it"),
            "year": int(year) if year else None,
            "publishers": split(get("publishers")),
            "designers": split(get("designers")),
            "genres": split(get("genres")),
            "official_sites": split(get("sites")),
            "wikipedia": get("article"),
            "popularity": int(get("links")),  # number of Wikipedia languages covering it
        }

    seed = sorted(games.values(), key=lambda g: -g["popularity"])
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(seed, ensure_ascii=False, indent=1))
    print(f"Saved {len(seed)} games to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
