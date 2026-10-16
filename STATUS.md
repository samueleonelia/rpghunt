# STATUS: RPG Hunt (rpgArchive)

_Updated: 2026-10-16 · commit 44bf430_

<!-- Rewrite this file in place. Never append. History belongs in DEVLOG.md. Keep under 60 lines. -->

**What this is:** A daily list of tabletop RPG deals, collected and verified by AI agents, English first, with a catalog of games behind it.

**Right now:** Live at https://samueleonelia.github.io/rpghunt/ with the 27 deals from 2026-10-16. Deals are not refreshed yet: the page hides ended deals, so the list shrinks day by day.

## Feature areas
| Area | State | Note |
|---|---|---|
| Live site (GitHub Pages) | ✅ working | every push to `main` republishes |
| Deal-finding agents | ✅ working | 4 agents, about 515k tokens per day |
| Deal checker | ✅ working | drops expired, dead, wrong-page, unseen-price deals |
| Deals home page | ⚠️ partial | works, plain design; Impeccable redesign next |
| Daily scheduled run | 🚧 building | not set up; live deals go stale |
| Amazon deals | ❌ broken | robot pages; needs Amazon API (Associates account) |
| DriveThruRPG deals | ⚠️ partial | blocked; only dated deals with end date survive |
| Free giveaways | 🚧 building | none found on the pilot day |
| Game catalog | ✅ working | 50 of 1,425 games |
| Custom domain | 🚧 building | rpghunt.com not bought |

## Next up
1. Daily scheduled run
2. Redesign deals home page with Impeccable
3. rpghunt.com pointed at GitHub Pages
4. Amazon API and DriveThruRPG affiliate feed

## Known bugs
- Archive page: cramped labels, faint search placeholder (Impeccable scan)

## Blocked on you
- Buy rpghunt.com (about $10 to $15 a year)
- Amazon Associates account (unlocks real Amazon deals and affiliate income)
- DriveThruRPG affiliate account
