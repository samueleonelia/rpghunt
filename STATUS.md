# STATUS: RPG Hunt (rpgArchive)

_Updated: 2026-10-17 · branch main · commit dc29537_

<!-- Rewrite this file in place. Never append. History belongs in DEVLOG.md. Keep under 60 lines. -->

**What this is:** A daily list of tabletop RPG deals, collected and verified by AI agents, English first, with a catalog of games behind it.

**Right now:** The new scraper is built and merged: one command (`.venv/bin/python -m scraper.daily`) reads 47 shops (DriveThruRPG included), checks every deal with Jev, and writes a site preview of about 1,000 deals for about $0.06 a day. The live site still shows the 2026-10-16 deals until you decide to go live. Plan doc: https://claude.ai/code/artifact/0bd90157-4e2b-4098-95e8-b66a7a3fb090

## Feature areas
| Area | State | Note |
|---|---|---|
| Live site (GitHub Pages) | ✅ working | every push to `main` republishes; still old deals |
| Shop readers (46 shops) | ✅ working | Shopify, WooCommerce, itch.io, bundles, generic; about 8 min |
| Jev check | ✅ working | 5/5 fakes rejected, 28/29 test deals published, about $0.06 a day |
| Browsing agent (Claude) | ⚠️ partial | starts from your terminal; network filter blocks shop sites (your choice pending) |
| New shops and missed deals | ✅ working | EN World leads (Reddit removed) |
| Break alarm | ✅ working | unit-tested; needs 3 runs of history |
| Site preview + daily report | ✅ working | `data/deals/site-preview-<date>.json`, `daily-report-<date>.md` |
| Daily scheduled run | 🚧 building | not set up |
| DriveThruRPG | ✅ working | public data server; deals appear on real price drops from day 2 |
| Amazon deals | ❌ broken | needs Amazon API (Associates account) |
| JavaScript-only shops | ❌ broken | GameNerdz, Demiplane, Fanatical need a browser |
| Reviews and ratings | ✅ working | ratings from itch.io pages |
| Game catalog | ✅ working | 50 of 1,425 games |
| Custom domain | 🚧 building | rpghunt.com not bought |

## Next up
1. Run the daily command once from a normal terminal (checks the browsing agent)
2. Go live with the new deals (your OK)
3. Daily scheduled run
4. Recipes for CoolStuffInc, Noble Knight, Massif, Roll20

## Known issues
- `docs/deals.js`, `docs/games.html`, `docs/index.html`, `docs/style.css` have uncommitted changes from an earlier session; left untouched.
- About 1,000 deals a day is far more than the 27 the site was designed for; the page may need paging or stronger ranking.
- Humble Bundle "worth" figures are inflated; those bundles go to the agent.

## Blocked on you
- Browsing agent network: shop sites only (1) or Python fetches for it (2)
- Contact email for the bot page
- Decide: go live with the new deals
- Buy rpghunt.com
- Amazon Associates account; DriveThruRPG affiliate account (commission)
