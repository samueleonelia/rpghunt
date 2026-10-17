# STATUS: RPG Hunt (rpgArchive)

_Updated: 2026-10-17 · branch scraper-v2 · commit 826a2c5_

<!-- Rewrite this file in place. Never append. History belongs in DEVLOG.md. Keep under 60 lines. -->

**What this is:** A daily list of tabletop RPG deals, collected and verified by AI agents, English first, with a catalog of games behind it.

**Right now:** Rebuilding the deal scraper on branch `scraper-v2` (phases 0 and 1 of 5 done). The live site still shows the 2026-10-16 deals. Plan doc: https://claude.ai/code/artifact/0bd90157-4e2b-4098-95e8-b66a7a3fb090

## Feature areas
| Area | State | Note |
|---|---|---|
| Live site (GitHub Pages) | ✅ working | every push to `main` republishes |
| Old deal-finding agents | ✅ working | 4 agents, about 515k tokens per run; being replaced |
| New scraper: setup + test set | ✅ working | Python 3.14 venv, Scrapling 0.4.15, 29 real deals + 5 fakes |
| New scraper: collectors (phase 1) | ✅ working | 45 shops in 6.4 min, 29/29 test deals found |
| New scraper: Jev check (phase 2) | 🚧 building | needs TypeSafe API key |
| New scraper: escalation (phase 3) | 🚧 building | Claude agent, then "Needs your check" list |
| New scraper: discovery + missed deals (phase 4) | 🚧 building | self-growing shop list |
| Deal checker | ✅ working | drops expired, dead, wrong-page, unseen-price deals |
| Deals home page | ✅ working | AppSumo-style layout |
| Daily scheduled run | 🚧 building | not set up; live deals go stale |
| Amazon, DriveThruRPG deals | ❌ broken | need official feeds (accounts) |
| Reviews and ratings | ✅ working | 17 of 28 deals have reviews |
| Game catalog | ✅ working | 50 of 1,425 games |
| Custom domain | 🚧 building | rpghunt.com not bought |

## Next up
1. Phase 2: Jev check (RPG filter, limited-time vs normal price, price history)
2. Phase 3: escalation (Claude, then you) and recipes for 8 shops with no sale page
3. Phase 4: self-growing shop list and missed-deal check

## Known issues
- Raw run has about 2,250 deals with many non-RPG items and everyday retailer prices; phase 2 filters them.
- `docs/deals.js`, `docs/games.html`, `docs/index.html`, `docs/style.css` have uncommitted changes from an earlier session; left untouched.
- Your safety guard may block price-reading commands; it blocked one Researcher pass today.

## Blocked on you
- TypeSafe API key in `.env` (before phase 2)
- Buy rpghunt.com
- Amazon Associates and DriveThruRPG affiliate accounts
