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

## 2026-10-16: Name chosen

- Name: **RPG Hunt**, domain rpghunt.com. Checked: .com/.net/.io unregistered, no existing site or brand with that name (only small itch.io games called "Hunt"). Not bought yet; the user buys it.
- Site title and logo text updated. Folder and repo name stay `rpgArchive` for now.

## 2026-10-16: Deals pilot, one day end to end

**Status:** deals pilot works locally, merged to `main`, tag `v0.2-deals-pilot`. No GitHub remote yet.

**Done**
- `agents/deals-brief.md`: instruction sheet for deal-finding agents (4 types, confidence levels, link rules).
- 4 Sonnet agents in parallel: bundles, digital sales, publisher/VTT stores, print discounts + freebies.
- `scripts/build_deals.py`: drops expired, dead, wrong-page and low-confidence deals; drops deals whose price is not on the loaded page; deals on robot-blocking shops kept only with a known end date; dedupes across agents and sister domains; links deals to catalog games.
- Home page is now today's deals (`docs/index.html` + `docs/deals.js`), archive moved to `docs/games.html`. Deals link to `games.html#<id>`.

**Results**
- 39 deals found, 27 published: 4 bundles (all Bundle of Holding), 14 digital sales (mostly itch.io indies, Kobold Press, Month of Darkness), 9 print deals (Modiphius clearance, Paizo clearance, Barnes & Noble, Evil Hat).
- 0 free giveaways: none genuinely limited-time and recent.
- 25 of 27 published deals had their price confirmed on the shop page.
- Cost: about 515k agent tokens, about 19 minutes (slowest agent).

**Key learnings**
- Amazon shows robot-check pages to scripts; all 5 Amazon deals were dropped. Real Amazon deals need the Product Advertising API (requires an Amazon Associates account).
- DriveThruRPG blocks everything automated; only deals with a dated source and end date survive. Its affiliate program may offer a feed.
- itch.io and Bundle of Holding are easy to verify; Bundle of Holding end dates come from countdown timestamps in the page.
- A deals blog page (Tabletop Bellhop) contained text addressed to AI agents; the agent ignored it. Keep treating fetched pages as data.
- Agents overlap (the Modiphius clearance was found twice), so dedupe is required.
- EN World's weekly column is the best lead source, but its latest issue was 11 days old.

**Next**
- Design the deals home page with Impeccable (new-work).
- Fill the gaps: Amazon via the official API, DriveThruRPG via affiliate feed, a freebies source.
- Daily scheduled run.

## 2026-10-16: Site online

**Status:** live at https://samueleonelia.github.io/rpghunt/, repo https://github.com/samueleonelia/rpghunt (public), branch `main`.

**Done**
- Scanned the repo for secrets and emails before publishing: none.
- Added Impeccable's Apache 2.0 LICENSE and NOTICE (required to redistribute its files publicly).
- Created the public repo `rpghunt`, pushed `main` and tags, turned on GitHub Pages from `main` `/docs`. Build took under a minute; live site checked in the browser (27 deals, games page, no console errors).
- Deals page now hides deals whose end date has passed, since data is not refreshed daily yet.

**Decisions**
- Repo named `rpghunt` (local folder stays `rpgArchive`). Project notes (CLAUDE.md, DEVLOG, STATUS, PRODUCT.md) are public too.

**Next**
- Daily scheduled run, otherwise the live deals go stale.
- Buy rpghunt.com and point it at GitHub Pages.
- Redesign with Impeccable.

## 2026-10-16: Dark theme

- Site is now always dark (user request). Palette checked for contrast: every text/background pair at 6:1 or better.
- Fixed Impeccable scan findings: label padding (3px to 4-5px), faint search placeholder. Themed selection, focus ring, caret and scrollbar.
- Fixed phone header on the games page (logo, menu and EN/IT switch overflowed): menu moves to its own row under 560px.
- Impeccable detector: 0 findings on both pages (was 10).

## 2026-10-16: Deals page redesign (cover images, ochre, sans)

**Status:** live, branch `main`.

**Done**
- Ran Impeccable's direction round (roll: "Hunter's Notice Board", pick: "Module Loot Table", challenger: "Tabbed Manual", plus the standard). The user steered in chat instead of picking: ochre accent, images required, no serif, shop named once. Applied as a refinement of the existing layout; no new visual world, so no DESIGN.md yet.
- `build_deals.py` now saves each deal's share image (og:image, forced to https): 26 of 28 deals have a cover. Deals without one show the game name.
- Best deals first: free, then biggest discount. The top deal leads at double width with its cover beside the details.
- One shop mention per card, as small text under the button ("at Modiphius · PRINT"); shop prefixes stripped from titles ("Bundle of Holding: X" becomes "X").
- Font: Archivo (sans, Google Fonts) everywhere, tabular figures. Accent ochre #d9a033 (8:1 contrast); urgent hue #ff7a59 only for "ends soon".
- Fixed a checker bug: itch.io rate-limited us (HTTP 429) and 9 deals were wrongly dropped. Now one request at a time per site, 1.5 s apart, retry after 429.
- Impeccable detector: 0 findings on both pages.

**Ideas raised by the user**
- Aggregate reviews from other sites: plan is scores where public (itch.io stars, RPGGeek API needs approval) plus 2-3 linked reviews per game with a one-line summary in our own words. No copied review text.

**Next**
- Daily scheduled run.
- Review aggregation.
