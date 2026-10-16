# STATUS: RPG Hunt (rpgArchive)

_Updated: 2026-10-16 · commit 27649f2_

<!-- Rewrite this file in place. Never append. History belongs in DEVLOG.md. Keep under 60 lines. -->

**What this is:** A daily list of tabletop RPG deals, collected and verified by AI agents, English first, with a catalog of games behind it.

**Right now:** One day of deals works end to end on this Mac: 27 verified deals on the home page, catalog of 50 games behind it. Not online yet, plain design.

## Feature areas
| Area | State | Note |
|---|---|---|
| Deal-finding agents | ✅ working | 4 agents, about 515k tokens per day |
| Deal checker | ✅ working | drops expired, dead, wrong-page, unseen-price deals |
| Deals home page | ⚠️ partial | works, plain design; Impeccable redesign next |
| Bundles, digital sales, print deals | ✅ working | 4 + 14 + 9 on 2026-10-16 |
| Amazon deals | ❌ broken | robot pages; needs Amazon API (Associates account) |
| DriveThruRPG deals | ⚠️ partial | blocked; only dated deals with end date survive |
| Free giveaways | 🚧 building | none found on the pilot day |
| Game catalog | ✅ working | 50 of 1,425 games; 4 deals link to it |
| Going online (GitHub Pages) | 🚧 building | needs a GitHub repo, then the domain |
| Daily scheduled run | 🚧 building | not set up |

## Next up
1. Redesign deals home page with Impeccable
2. GitHub repo and Pages, then rpghunt.com
3. Daily scheduled run
4. Amazon API and DriveThruRPG affiliate feed

## Known bugs
- Archive page: cramped labels, faint search placeholder (Impeccable scan)

## Blocked on you
- Buy rpghunt.com (about $10 to $15 a year)
- OK to create a public GitHub repo
- Amazon Associates account (unlocks real Amazon deals and affiliate income)
- DriveThruRPG affiliate account
