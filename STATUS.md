# STATUS: rpgArchive

_Updated: 2026-10-16 · commit 4ffa05c_

<!-- Rewrite this file in place. Never append. History belongs in DEVLOG.md. Keep under 60 lines. -->

**What this is:** A worldwide directory of tabletop RPGs, built and updated by AI agents, with direct links to publishers, shops and Amazon.

**Right now:** Pilot works on this Mac: 50 games, 48 with verified links, searchable website in English and Italian. Not online yet.

## Feature areas
| Area | State | Note |
|---|---|---|
| Seed list from Wikidata | ✅ working | 1,425 games in `data/seed.json` |
| Agent research | ✅ working | 50 of 1,425 games done |
| Link checker | ✅ working | drops dead links, verifies agent suggestions |
| Website | ✅ working | `docs/`, search, filters, EN/IT, phone layout |
| Going online (GitHub Pages) | 🚧 building | needs a GitHub repo |
| Full catalog run | 🚧 building | about 16k agent tokens per game |
| Games missing from Wikidata | 🚧 building | e.g. Fabula Ultima |
| Scheduled auto-update | 🚧 building | after the full run |

## Next up
1. Create GitHub repo, turn on Pages
2. Full run on the remaining 1,375 games
3. Discovery agent for games not on Wikidata
4. Scheduled agent for new releases

## Known bugs
- DriveThruRPG and Palladium block every automated visitor, so their links can't be verified
- Rifts and Inferno have no working link

## Blocked on you
- OK to create a public GitHub repo for the site
- OK to spend about 23M agent tokens on the full run
- Later: Amazon Associates account for affiliate links
