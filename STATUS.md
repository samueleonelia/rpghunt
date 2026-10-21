# STATUS: RPG Hunt (rpgArchive)

_Updated: 2026-10-21 · branch main_

<!-- Rewrite this file in place. Never append. History belongs in DEVLOG.md. Keep under 60 lines. -->

**What this is:** A daily list of tabletop RPG deals, collected and verified by AI agents, English first, with a catalog of games behind it.

**Right now:** Baseline saved on 2026-10-19: 3,918 deals already on sale count as "seen" and won't be published while unchanged. From 2026-10-20 each daily run reads all 47 shops (about 10 minutes) and pays only for new or changed deals. The report warns when a day costs more than $5. The live site still shows the 2026-10-16 deals. The homepage redesign sits uncommitted in `docs/`.

## Feature areas
| Area | State | Note |
|---|---|---|
| Live site (GitHub Pages) | ✅ working | every push to `main` republishes; still old deals |
| Homepage redesign + email form | 🚧 building | uncommitted; loads a localhost script; form not connected (Kit suggested) |
| Shop readers (47 shops) | ✅ working | limits only stop runaway loops; hits shown in the report |
| Jev check | ✅ working | only new or changed deals; others keep their verdict |
| Browsing agent (Claude) | ✅ working | no job cap; verdict kept while link and price unchanged |
| Cost alarm | ✅ working | warns over $5 a day (`--cost-alarm`) |
| New shops and missed deals | ✅ working | EN World leads, no page limit |
| Break alarm | ✅ working | needs 3 runs of history |
| Site preview + daily report | ✅ working | `data/deals/site-preview-<date>.json`, `daily-report-<date>.md` |
| Daily scheduled run | 🚧 building | not set up |
| DriveThruRPG | ✅ working | deals appear on real price drops from day 2 |
| Amazon deals | ❌ broken | needs Amazon API (Associates account) |
| JavaScript-only shops | ❌ broken | GameNerdz, Demiplane, Fanatical; treg page reader is the candidate fix |
| Sites that block us | ✅ working | `data/shops/blocked-sites.json` (9 known), report section; never bypassed |
| Game catalog | ✅ working | 50 of 1,425 games |
| Custom domain | 🚧 building | rpghunt.com not bought |

## Next up
1. Spot-check the 2026-10-21 preview (167 new or changed), then paid run: `.venv/bin/python -m scraper.daily --skip-run`
2. GameNerdz via treg page reader (test under 1 cent); check DMsGuild on the DriveThruRPG data server
3. Finish the redesign (remove localhost script, email form decision)
4. Paging or stronger ranking for about 1,000 deals a day
5. Go live with the new deals (your OK)
6. Daily scheduled run

## Known issues
- Real daily cost is unknown until the 2026-10-20 run.
- Deals already on sale on 2026-10-19 (baseline) are never shown unless their price changes or EN World names them.
- About 1,000 deals a day is far more than the 27 the site was designed for.
- Humble Bundle "worth" figures are inflated; those bundles go to the agent.
- Variant deals ("My Jam"): our reader takes the cheapest on-sale variant; the page may show another.
- Generic shops with no usable sale page (CoolStuffInc, Noble Knight, Massif, Roll20) need recipes.

## Blocked on you
- Contact email for the bot page
- Email service for the signup form (Kit or other), or drop the form
- Decide: go live with the new deals
- Buy rpghunt.com
- Amazon Associates account; DriveThruRPG affiliate account
