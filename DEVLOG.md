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

## 2026-10-16: Simpler cards, accent test

- User feedback: the wide "best deal" card looked unboxed and the source line was overcomplicated. Now every card has the same layout (best deal is simply first) and the source line is only "at <shop>".
- Accent test: the first card's button uses a reddish #d9653a; everything else stays ochre #d9a033. Waiting for the user's pick.
- Accent decided: ochre, slightly brighter (#e6af3e, 9:1 on the dark ground). Red test removed.

## 2026-10-16: Reviews pilot

**Done**
- `agents/reviews-brief.md`: agents find 0-3 independent reviews per deal (blogs, review sites, YouTube, Reddit), one-line verdict in their own words, reviewer's own score only. No copied review text.
- 4 Sonnet agents on 28 deals: 31 review links found, about 370k agent tokens.
- `scripts/build_reviews.py`: opens every review link (one request per site at a time), keeps only pages that load and mention the product; stores them in `data/reviews/reviews.json` by deal id so they persist across days.
- `build_deals.py` reads shop star ratings from schema.org data (itch.io publishes them); ratings under 5 votes hidden.
- Cards show "★ 4.9 · 393 ratings on itch.io" and a collapsible "3 reviews" list (source, score, verdict, link).

**Results**
- 29 of 31 review links verified; 17 of 28 deals have reviews; 8 have star ratings.
- Kobold Press, the Modiphius toolkit and new indie titles have no independent reviews online.

**Bug fixed**
- The robot-page detector matched "captcha" + "robot" anywhere (comment-form captchas, the "Roboto" font, meta robots), wrongly dropping blogs and 2 real deals. Now it judges by page title (Robot Check, Just a moment...) and Amazon's own robot-test wording.

**Next**
- Daily scheduled run (deals + reviews for new deals only).

## 2026-10-16: Home page on an AppSumo-style layout

- User asked for appsumo.com as the layout reference. Studied it (declined its non-essential cookies) and rebuilt the deals home on the same structure, in our own dark/ochre/sans style; no AppSumo branding or copy.
- Structure: ochre announcement bar (deal ending soonest), header with search and section links, headline, 3 honest trust points, "Top 9 deals" ranked by discount, rows of 4 (Ending soon, Bundles, Free, Digital sales, Print deals) with "View all", results grid for search and "View all". Skipped AppSumo's email signup (no newsletter exists).
- Phone: header scrolls away (was 193px sticky), nav scrolls sideways without a scrollbar.
- Impeccable detector: 0 findings (faint rank numerals raised to 3.3:1).
- User idea: a short, easy-to-say brand word like "sumo" instead of "Hunt". Not done yet.

## 2026-10-17: Scraper rebuild planned, phase 0 done

**Status:** branch `scraper-v2`, phase 0 of 5 done. `main` untouched.

**Plan** (doc: https://claude.ai/code/artifact/0bd90157-4e2b-4098-95e8-b66a7a3fb090)
- Replace the 4 web-searching agents (about 515k tokens a day) with a ladder: code reads shop data (Shopify, WooCommerce, itch.io, bundle sites, product data in pages), Scrapling reads other pages with a saved per-shop recipe, Jev (TypeSafe) checks every deal, a browsing Claude agent steps in only when code fails or Jev is unsure, and the user decides when Claude is still unsure.
- Shop list grows by itself from Reddit, EN World, bundles, itch.io and catalog publishers. A daily missed-deal check adds shops we missed.
- Build: 5 phases with gates. Lead = main session (Opus 5.5); Builder = executor-sonnet-high; Researcher = researcher-high.

**Done (phase 0)**
- `.venv` with Python 3.14 (Homebrew) and `scrapling[fetchers]==0.4.15` (`requirements.txt`). No browsers downloaded yet.
- Test set `data/testset/2026-10-17.json`: 29 hand-verified live deals (itch 10, Shopify 8, bundle sites 6, WooCommerce 5), plus 5 planted fakes (wrong price, not an RPG, normal price, expired, hidden AI instruction) with 2 local fixture pages.

**Decisions**
- Scrapling's anti-bot bypass stays off; blocked shops (DriveThruRPG, Amazon) go through official feeds.
- Claude's verdicts must still pass code checks and can't overrule a Jev "contradicts".

**Learnings**
- Store APIs work: Modiphius and Exalted Funeral (Shopify), Evil Hat and Kobold (WooCommerce, Kobold under `/kpstore/wp-json/`). Pelgrane, Goodman Games, Cubicle 7: HTTP 403.
- Traps for the scraper: itch feed lists "0% off" items; sale collections mix in minis, board games, dice; feed and page lists disagree; currency follows the visitor (GBP, EUR).
- The user's safety guard blocked the first Researcher pass on price pages, and blocks commands that mention it by name.

**Next**
- Phase 1: collectors (shop list and recipe formats, seed list, Shopify/WooCommerce/itch/bundle readers, generic reader). Gate: run over the seed list, score against the test set.

## 2026-10-17: Scraper phase 1 done (collectors)

**Status:** branch `scraper-v2`, phase 1 of 5 done (commit 826a2c5). Gate 1 passed.

**Done**
- `scraper/`: readers for Shopify (`products.json`), WooCommerce (Store API), itch.io (feeds + `data.json` + game page), Bundle of Holding, Humble, and a generic reader (product data in the page, sale-page markup, recipe selectors). Plus `detect.py` (platform finder), `run.py` (parallel runner, run report), `score.py` (test-set scorer). 56 unit tests with saved fixtures.
- Seed list of 60 shops (`data/shops/seed-2026-10-17.json`) by the Researcher; 53 detected into `data/shops/shops.json`: about 25 Shopify, 8 WooCommerce, 10 generic, 9 blocked.
- Built by: Lead (spec, `common.py`, fixes), Builder A (Shopify, WooCommerce, detect, run, score), Builder B (itch, bundles), Builder C (generic), Researcher (seed list).

**Gate 1 results**
- Full run: 45 shops, 0 errors, 6.4 minutes, about 2,250 raw deals.
- Test set: 29 of 29 real deals found (itch 10, Shopify 8, bundle sites 6, WooCommerce 5).
- Fakes: wrong-price fake kept out (run shows the real price); not-an-RPG fake (Modiphius dice tray) still in, as expected until phase 2.
- Old checker (`build_deals.py`) on a 40-deal sample: 36 kept, 0 dead or wrong pages, 4 dropped because it can't spot some prices on the page (likely "$1,099" formatting). Dropping is safe.

**Decisions and learnings**
- Browser impersonation is off: with it, Shopify served Exalted Funeral without compare-at prices (0 sale items instead of 213).
- Modiphius and Exalted Funeral read their full catalog; Leisure Games (retailer) only its "reduced price" collection.
- itch reads 3 feeds; "0% off" items never become deals.
- Raw daily output (about 2 MB) is gitignored; run report and score are committed.
- Precision is the next problem: about 2,250 raw deals include miniatures, board games, dice and retailers' everyday below-list prices. Phase 2 must filter: Jev "is this an RPG?" and "limited-time or normal price?", plus a price-history check (a real deal is a drop from the price we saw before).
- Generic shops with no usable sale page (Chaosium, Noble Knight, GameNerdz, CoolStuffInc, Roll20, Demiplane, Fanatical, Massif) need recipes from the phase 3 agent.

**Next**
- Phase 2: Jev check. Needs the TypeSafe API key in `.env`.

## 2026-10-17: Scraper phases 2 to 4 done, merged to main (v0.3-scraper)

**Status:** new scraper merged to `main`, tag `v0.3-scraper`. The live site still shows the 2026-10-16 deals: going live with the new deals is the user's call.

**Done**
- Phase 2 (Jev check): `check.py` (RPG triage, then page questions for page-read deals), `trim.py` (visible text only, price candidates), `history.py` (120-day price record, local), `jev.py` (typesafe-sdk with answer cache). Code owns every number, date and the final decision.
- Phase 3 (escalation): `fetchpage.py` (the agent's only way to open pages), `agent.py` (headless browsing agent, user's hooks active, only fetchpage allowed), `escalate.py` (rechecks and recipe jobs; unsettled items go to `needs-owner-<date>.json`), `alarm.py` (break alarm when a shop's deals collapse with no error). First agent recipe: Chaosium.
- Phase 4 (discovery): `discover.py` (EN World leads; new shops detected and added), `missed.py` (leads vs run), `publish.py` (site preview, never `docs/` unless asked), `daily.py` (whole day in one command + plain report).
- Gates: Gate 2 (all 5 fakes rejected, 28/29 test deals published), Gate 3 (break tests in unit tests; Chaosium recipe live), Gate 4 (full day ran end to end: 46 shops, 2,250 raw deals, 1,073 in the preview, 28/29 test deals published, Jev about $0.06).

**Decisions**
- A publisher's own sale price in its own shop data counts as the promotion; only page-read deals, retailers flagged `everyday_discounts` and free items need the offer question.
- Jev triages one product per request (batching made answers depend on neighbours) and sees description, genre and where the item was listed.
- Safety rules in code: 95%+ discounts go to the agent; products the shop names "free" are permanently free, not deals; only real money amounts are prices ("save 20%" is not).
- Bundle of Holding is `rpg_only` (skips triage). Leisure Games reads only its "reduced" collection.
- Price history (`data/prices/`), raw run output, checked output and site preview are gitignored; reports are committed.

**Learnings**
- Jev from inside this sandboxed session needed Python's standard certificate check (the SDK default failed); fixed in `jev.py`.
- Scrapling's browser impersonation made Shopify hide sale prices; turned off.
- Reddit refuses robots (feeds skipped). Most EN World sale links point at DriveThruRPG (blocked).
- Browsing-agent jobs can't start their own sandbox when launched from inside a sandboxed Claude session; they answered "unsure" instead of working around it. They need a run from a normal terminal or a scheduled task.

**Next**
- User: run the daily command once from a normal terminal to confirm the browsing agent works there.
- User decision: put the new deals live (writes `docs/data/deals.json`).
- Then: daily scheduled run; recipes for CoolStuffInc, Noble Knight, Massif, Roll20; GameNerdz, Demiplane, Fanatical are JavaScript-only.

## 2026-10-17: DriveThruRPG added, honest bot name

**Status:** `main` (dc29537), pushed. Live site still shows the 2026-10-16 deals.

**Done**
- DriveThruRPG via its public data server `api.drivethrurpg.com` (its robots.txt: `Allow: /`); `www.drivethrurpg.com` (bot wall) is never fetched, enforced in `fetch()`. 1,708 on-sale products, 1,616 deals, under 2 minutes. Pictures from its image server.
- Bot renamed to `RPGHuntBot/1.0` with a bot page link; no shop started blocking it. Bot page text in `agents/bot-page.md` (needs a contact email before publishing).
- Reddit removed from lead feeds (not a shop; its robots refuse us).
- Browsing agent tested from the user's terminal: it starts, but Claude's own network filter blocks shop sites, so it answered "unsure" on all 6 jobs. Waiting on the user's choice: allow shop domains, or have Python fetch for it.

**Decisions**
- Shops with everyday markdowns (DriveThruRPG, retailers) publish only on a price drop we saw ourselves or a trusted roundup (EN World) naming the deal; Jev's "promotion" wording alone is not enough. Day 1 of DriveThruRPG history: 1,114 deals wait; real drops show from the next run.
- Unsure deals on bot-walled sites are judged from shop data, not the page.
- Legal note given to the user: facts and prices are low risk; EU database right, shop terms and images are gray areas; honest bot, opt-out, affiliate feeds and a lawyer before monetizing.

**Next**
- User: agent network choice; contact email for the bot page; go-live decision.
- Daily scheduled run (needed for DriveThruRPG price drops to appear).

## 2026-10-18: Browsing agent working (shop sites only)

- User chose option 1: the agent may reach only the shop sites. `agent.py` writes a per-run settings file (`data/shops/agent-sandbox.json`, gitignored, rebuilt from `shops.json` every run): sandbox on, `allowUnsandboxedCommands: false`, `strictAllowlist: true`, about 84 shop hosts. The user's own settings are untouched; `www.drivethrurpg.com` is never allowed.
- Test from the user's terminal: 8 rechecks: 2 published (Malleus Monstrorum slipcase $59.99 vs $89.99, Dolmenwood Maps Book $16 vs $20, both confirmed on the page by code), 4 dropped (picture book, USB key, no real discount, price mismatch), 2 to the owner (grab bag, coloring book). About $0.08 per job.
- Cost note: the agent is the expensive part. `daily` caps it at 20 jobs a day (about $1.60). The 360 stuck DriveThruRPG items are fixed (judged from shop data), so the daily queue should be far smaller.
- Open: "My Jam" mismatch: our reader took the cheapest on-sale variant; the page shows another variant's price. Variant deals may need the variant in the title.
