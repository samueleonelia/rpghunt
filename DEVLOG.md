# DEVLOG

## 2026-10-15: Project setup + first research

**Status:** setup done, branch `main`, no code yet.

**Done**
- Initialized git repo, `.gitignore`, `CLAUDE.md`, `STATUS.md`, `DEVLOG.md`.
- Web search: does an online directory of Italian tabletop RPGs exist?

**Findings**
- **GdR Players** (gdrplayers.it): the closest thing to a national directory. Player/master ads by province, online vs in-person, a map of players, sections for associations, events, buy/sell. ~36,500 registered players, active (posts dated Oct 2026). Shops are not covered.
- **La Tana dei Goblin** (goblins.net): network of ~15 affiliated gaming associations across Italy; forum has a (dated, incomplete) thread listing RPGs by Italian authors.
- **Darkshire RPG Company List, Italy** (darkshire.net/~jhkim): fan list of Italian RPG publishers, old.
- **Archivio Italiano dei Giochi** (Udine): documentation center for all games made in Italy, not RPG-only; current online status unverified.
- **Not found:** a single, up-to-date catalog of Italian RPG titles/publishers, or a map of RPG shops. Shop catalogs (Dragonstore, Terra dei Giochi) only list what they sell.

**Decisions**
- None yet on what to build.

**Next**
- Decide the project's goal (e.g. fill the gap: catalog of Italian RPGs, or a map of shops/associations).

## 2026-10-15: Project goal decided

**Status:** planning, branch `main`, no code yet.

**Done**
- Checked for a "Goodreads for RPGs": RPGGeek is the closest (English, worldwide). No Italian equivalent exists.
- Checked Wikidata as a free seed list: 1,720 RPGs, only 122 with an official website, 217 with an Italian name.

**Decisions**
- Worldwide directory of all RPGs, filled and auto-updated by AI agents.
- Plain vendor/Amazon links now, affiliate links later.
- Static website (HTML/CSS/JS + JSON) on GitHub Pages.
- Start from Wikidata, agents add descriptions and shop links, and every link gets checked live (agents can invent links).

**Next**
- Pilot: 50 games end to end, to test data quality and cost before the full run.

## 2026-10-16: Pilot, 50 games end to end

**Status:** pilot works locally, merged to `main`, tag `v0.1-pilot`. No GitHub remote yet.

**Done**
- `scripts/fetch_seed.py`: 1,425 RPGs from Wikidata into `data/seed.json`.
- `agents/research-brief.md`: the instruction sheet every research agent follows.
- 5 Sonnet agents researched 10 games each (descriptions EN + IT, edition, in print, Italian edition, links).
- `scripts/build_data.py`: merges agent output, opens every link with a real browser identity, drops dead ones, writes `docs/data/games.json` and `data/link-report.json`.
- Website in `docs/` (plain HTML/CSS/JS): search, genre filters, "available in Italian", "in print", EN/IT switch, Amazon.com/.it search links. Tested in the browser pane, desktop and phone.

**Results**
- 48 of 50 games have at least one working link; 110 links verified, 3 kept but unverified (bot protection).
- 23 of 50 games have an Italian edition.
- Cost: about 810k agent tokens for 50 games (about 16k per game), about 10 minutes with 5 agents in parallel.

**Key learnings**
- Many shops (Free League, DriveThruRPG, Palladium, Pelgrane) block the agents' web reader. Free League opens fine for the Python checker; DriveThruRPG and Palladium block everything automated.
- The user's money-page safety hook blocks agents from opening "buy" pages. Respected, not bypassed.
- Fix adopted: agents may suggest `candidate_links` copied from search results; the checker keeps them only if the page loads and names the game.
- Python 3.9 needs a manual 308-redirect handler and an Accept header (Kult's site returned 406 without it).
- Wikidata `name_it` is often wrong (old or fan titles); agents correct it.

**Next**
- Create the GitHub repo and turn on GitHub Pages (site goes live).
- Full run on the remaining 1,375 Wikidata games, with candidate links from the start.
- Discovery agent for games missing from Wikidata (e.g. Fabula Ultima).
- Scheduled agent for new releases.

## 2026-10-16: Impeccable installed, pivot to deals site

**Status:** branch `main`, pilot site still the archive. Direction changed, no deals code yet.

**Done**
- Installed Impeccable v4.6.0 (design skill) in this project only, no hooks, telemetry off, engine binary gitignored. First scan of the site: 10 issues (cramped label padding, cream background, faint search placeholder).
- Researched two alternatives: daily RPG deals vs "Product Hunt for RPGs".
- Wrote `PRODUCT.md` via Impeccable init.

**Findings**
- RPG deals happen daily (DriveThruRPG sales incl. one-day deals, Bundle of Holding, Humble Bundle, itch.io, publisher sales). Only aggregator found: EN World's weekly hand-made roundup. No daily one, nothing in Italian.
- Product Hunt for RPGs needs a voting community that agents cannot create; Product Hunt already has an RPG topic (mostly apps).
- rpgpromo.com is taken by an active indie RPG promo site; .net and .io free.

**Decisions**
- Deals site on top of the archive. English first.
- Track all 4 deal types: digital sales, bundles, physical book discounts, free giveaways.
- Main visitor: active players and GMs.
- Name undecided.

**Next**
- Design the deal data format and a deal-finding agent; pilot one day of deals.
- Run `/impeccable` new-work for the deals home page.
