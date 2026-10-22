# STATUS: RPG Hunt (rpgArchive)

_Updated: 2026-10-22 · branch main_

<!-- Rewrite this file in place. Never append. History belongs in DEVLOG.md. Keep under 60 lines. -->

**What this is:** A daily list of tabletop RPG deals, collected and verified by AI agents, English first.

**Right now:** Live at https://samueleonelia.github.io/rpghunt/ with 230 checked deals from 22 Oct. The daily run can publish by itself (`--go-live`) but is not scheduled yet: waiting on your OK. Launch checklist: https://claude.ai/artifact/UYzdxWJQE8Z2cbNRbFUrX3

## Feature areas
| Area | State | Note |
|---|---|---|
| Live site | ✅ working | new homepage, paging, bot page; 230 deals |
| Deal alerts form | 🚧 building | wired to Kit form 10082554; needs one real test signup |
| Shop readers (47 shops) | ✅ working | about 10 min; limits reported when hit |
| New-sale rule | ✅ working | not on sale at the last read = new sale; partial-read guard |
| Jev check + memory | ✅ working | only new or changed deals are paid for |
| Browsing agent | ✅ working | runs from a normal terminal or launchd, not inside Claude |
| Go-live + alerts | ✅ working | `daily --go-live --notify` |
| Daily schedule | ⏸ blocked | launchd files written in `scripts/`, not installed (your OK) |
| Sites that block us | ✅ working | `data/shops/blocked-sites.json`, never bypassed |
| GameNerdz | ⏸ blocked | JavaScript-only; needs Scrapling's browser download (your OK) |
| DMsGuild | ❌ closed | its API is DriveThruRPG's catalog; own deals unreachable without bypassing |
| Amazon deals | ❌ broken | needs Amazon API (Associates account) |
| Custom domain | 🚧 building | rpghunt.com not bought |

## Next up
1. Install the daily schedule (your OK)
2. Test signup on the live form with your email; confirm it lands in Kit
3. GameNerdz via Scrapling's browser (your OK to download it)

## Known issues
- About 20 unsure DriveThruRPG deals a day go to "Needs your check" (the agent can't open the DriveThruRPG website).
- Hit Point Press lowers prices by $1 daily: about 8 re-checks a day.
- Deals on sale before 19 Oct (baseline) show only if their price changes or EN World names them.

## Blocked on you
- OK to install the launchd daily job
- OK to download Scrapling's browser (GameNerdz)
- Buy rpghunt.com; Amazon Associates and DriveThruRPG affiliate accounts
