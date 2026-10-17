# RPG Hunt (folder: rpgArchive)

## What this is
A daily list of tabletop RPG deals (sales, bundles, discounted books, free
giveaways), collected and verified by AI agents, English first. Each deal links
straight to the shop and to the game's page in a catalog of RPGs behind it.
Product truth lives in `PRODUCT.md` (written by Impeccable init).

## Decisions
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
TBD

## Remember
