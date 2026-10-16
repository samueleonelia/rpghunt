# rpgArchive

## What this is
A worldwide directory of tabletop RPGs (GdR), like Goodreads but for RPGs.
Built and kept up to date by AI agents. Each game links straight to the
publisher's site or Amazon.

## Decisions (2026-10-15)
- Scope: every RPG worldwide.
- Agents fill the catalog and auto-update it on a schedule.
- Links: plain links now, Amazon affiliate later (needs an Amazon Associates account).
- First version: plain HTML/CSS/JS site reading a JSON file, hosted on GitHub Pages.
- Seed list: Wikidata (free, CC0 license), ~1,720 RPGs. Do not copy RPGGeek's database (their terms forbid it).

## Stack
Planned: static HTML/CSS/JS + one JSON data file. No code yet.

## Design tool
Impeccable v4.6.0 (impeccable.style) is installed in this project only:
`.claude/skills/impeccable` + `.claude/agents/impeccable-*`. Use `/impeccable <command>`
(e.g. `audit`, `critique`, `polish`) on the site in `docs/`. Hooks are OFF (installed
with `--no-hooks`); turn on with `/impeccable hooks on`. Telemetry turned off.
Its 16 MB engine binary is gitignored; the launcher re-downloads it if missing.
Update with `npx impeccable update`.

## Files
- `DEVLOG.md`: history of what was done, session by session
- `STATUS.md`: current state, rewritten in place

## Rules
TBD

## Remember
