# RPG Hunt (folder: rpgArchive)

## What this is
A daily list of tabletop RPG deals (sales, bundles, discounted books, free
giveaways), collected and verified by AI agents, English first. Each deal links
straight to the shop and to the game's page in a catalog of RPGs behind it.
Product truth lives in `PRODUCT.md` (written by Impeccable init).

## Decisions
- 2026-10-27: **No set list of shops.** Every day the run looks for new sellers by itself (`scraper/discover.py`):
  English RPG news feeds and English Wikipedia's RPG publisher/designer categories (Wikidata's robots.txt blocks bots), listed in `data/shops/lead-feeds.json`.
  A new site is added when it is a web store selling English tabletop RPGs. Add sources there, not shops by hand.
- 2026-10-27: **English products only, for now** (user). Non-English titles are dropped by a plain rule (`check.not_english`).
- 2026-10-16: pivot from pure archive to deals site, archive kept as the catalog behind the deals. English first, Italian later.
- 2026-10-16: name is **RPG Hunt**, domain rpghunt.com (free when checked, not bought yet). "rpgpromo" rejected: rpgpromo.com is an active indie RPG promo site.
- 2026-10-15: catalog scope is every RPG worldwide; agents fill it and auto-update on a schedule.
- Links: plain links now, Amazon affiliate later (needs an Amazon Associates account).
- First version: plain HTML/CSS/JS site reading a JSON file, hosted on GitHub Pages.
- Seed list: Wikidata (free, CC0 license), ~1,720 RPGs. Do not copy RPGGeek's database (their terms forbid it).

## Stack
Static HTML/CSS/JS in `docs/` reading `docs/data/*.json`; Python 3.9 stdlib scripts in `scripts/`; agent instructions in `agents/`. Preview: `.claude/launch.json` ("site", port 8420).

## Python environment
Venv at `.venv` (Python 3.14, Homebrew, gitignored). Install with
`.venv/bin/pip install -r requirements.txt` (Scrapling 0.4.15, `[fetchers]` extra).
Scrapling's browser fetchers are not installed yet (`scrapling install` not run; needs OK first).

## Design tool
Impeccable v4.6.0 (impeccable.style) is installed in this project only:
`.claude/skills/impeccable` + `.claude/agents/impeccable-*`. Use `/impeccable <command>`
(e.g. `audit`, `critique`, `polish`) on the site in `docs/`. Hooks are OFF (installed
with `--no-hooks`); turn on with `/impeccable hooks on`. Telemetry turned off.
Its 16 MB engine binary is gitignored; the launcher re-downloads it if missing.
Update with `npx impeccable update`.

## Online
- Live site: https://samueleonelia.github.io/rpghunt/ (GitHub Pages, `main` branch, `/docs` folder; every push to `main` republishes it)
- Repo: https://github.com/samueleonelia/rpghunt (public). Domain rpghunt.com not bought yet.

## Files
- `DEVLOG.md`: history of what was done, session by session
- `STATUS.md`: current state, rewritten in place

## Rules
- **The deal list must be as complete as possible.** We may not find every deal, but never limit
  deal finding on purpose (no job caps, page caps or daily quotas to save money or time). Cost is
  watched with an alarm in the daily report (`--cost-alarm`, default $5), never with a cap.
  A safety limit that only stops a runaway loop is allowed, set very high, and must be reported
  in the daily report when hit ("Safety limits hit"). Decided 2026-10-19.
- **Daily run: read everything, check only what's new.** The site lists every deal still on sale.
  Every shop is read in full each day, but only new or changed deals (new link, or new price) get
  paid checks (Jev, agent); an unchanged deal keeps its earlier verdict for as long as it stays on
  sale. Do not filter by "sale started in the last 24 hours": shops rarely say when a sale started.
  Decided 2026-10-19.
- **Good bot: never bypass a block.** The goal is a good relationship with the shops (future
  partners and affiliate programs). The scraper names itself (`RPGHuntBot`), obeys `robots.txt`,
  and never gets around a bot wall (no fake browser identity, no unblocker services, no proxies to
  hide). Reading a JavaScript page with a real browser is fine; that is not a block. Every site
  that blocks us is recorded in `data/shops/blocked-sites.json` and listed in the daily report.
  Decided by the user 2026-10-21 ("for now"; revisit case by case if a big shop blocks us).

## Remember
