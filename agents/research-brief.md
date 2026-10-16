# Research brief: enrich RPG entries

You are filling entries for rpgArchive, a worldwide directory of tabletop RPGs.
Each entry must help a reader decide if the game is for them, then send them
straight to where they can buy it.

## Input
A JSON file with a list of games from Wikidata (name, year, publishers,
designers, genres, official_sites, wikipedia). Wikidata can be wrong or old:
check it, do not trust it.

## For each game, research with WebSearch and WebFetch, then fill:

| Field | Rule |
|---|---|
| `wikidata` | copy from input, unchanged |
| `name` | the name the game is best known by today (fix Wikidata if needed, e.g. drop "(rpg family)") |
| `name_it` | Italian title if an Italian edition exists, else `null` |
| `year` | year of the first edition |
| `current_edition` | latest edition and its year, e.g. `"5th Edition revised (2024)"`, or `null` |
| `in_print` | `true` if the current edition can be bought new today, else `false` |
| `publishers` | current publisher first, then past ones |
| `designers` | original designers |
| `tags` | 1 to 4 from this list only: fantasy, dark-fantasy, sci-fi, cyberpunk, space, horror, cosmic-horror, post-apocalyptic, superhero, historical, mythology, steampunk, western, urban-fantasy, mystery, comedy, mecha, cozy, generic, osr, narrative, crunchy |
| `description_en` | 2 to 3 sentences, **your own words**: what you play, the tone, what makes it different. No marketing copy, no copying from the publisher. |
| `description_it` | the same in natural Italian (not a literal translation). No em dashes. |
| `italian_edition` | `{"publisher": "...", "url": "..."}` if an Italian edition exists, else `null` |
| `links` | list of `{"type", "label", "url"}`, see below |
| `candidate_links` | links you found in search results but could not open, see below |
| `amazon_query` | the search words that find the current core book on Amazon, e.g. `"Call of Cthulhu 7th Edition Keeper Rulebook"` |
| `sources` | the URLs you actually used |
| `notes` | anything uncertain, or `null` |

### Links: the most important part
- `type` is one of: `official` (the game's page on the publisher's site), `store` (publisher's own shop, DriveThruRPG, itch.io, Backerkit store), `free` (free rules / SRD / quickstart).
- 1 to 4 links per game. Prefer the publisher's own page.
- **Only include a URL you opened with WebFetch and saw this game on.** Never guess or build a URL. If you cannot confirm one, leave it out and say so in `notes`.
- Many shops block your fetch tool (403) but work in a real browser. When a
  page blocks you, put its URL in `candidate_links` (same shape as `links`)
  **only if it appeared as a result URL in WebSearch**. Never build a URL by hand.
  A script opens every candidate with a real browser identity and keeps it
  only if the page loads and names the game.
- No Amazon links: the site builds those from `amazon_query`.
- No piracy sites, no fan wikis as links (fan wikis are fine as `sources`).

## Output
Write a JSON array (same order as input) to the output path you were given.
Valid JSON only, UTF-8, no comments. Then reply with one line per game:
name, number of links, and anything you could not confirm.
