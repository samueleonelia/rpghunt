# STATUS: RPG Hunt (rpgArchive)

_Updated: 2026-10-27 · branch main_

<!-- Rewrite this file in place. Never append. History belongs in DEVLOG.md. Keep under 60 lines. -->

**What this is:** A daily list of tabletop RPG deals, collected and verified by AI agents, English products only for now.

**Right now:** Live at https://samueleonelia.github.io/rpghunt/ with 455 checked deals (27 Oct). From 28 Oct the 07:30 run also looks for new sellers by itself (news feeds and Wikipedia) and reads every itch.io sale page (about 1,500 deals instead of 94).

## Feature areas
| Area | State | Note |
|---|---|---|
| Live site | ✅ working | paging, bot page; 455 deals |
| Finding new sellers | 🚧 first real day 28 Oct | 15 English RPG news feeds + Wikipedia RPG publishers/designers; no daily cap |
| Shop readers | ✅ working | 47 shops + new ones found daily |
| itch.io (indie authors) | 🚧 first real day 28 Oct | all sale pages, page cache; ~40 min on day 1 |
| English-only rule | ✅ working | non-English titles dropped |
| New-sale rule, Jev check, memory | ✅ working | only new or changed deals are paid for |
| Browsing agent | ✅ working | runs from launchd |
| Daily schedule | ✅ working | launchd 07:30; start-up catch-up written, not installed |
| Sites that block us | ✅ working | `data/shops/blocked-sites.json`, never bypassed |
| Deal alerts form | 🚧 building | Kit form; needs one real test signup |
| DMsGuild | ❌ closed | same catalog as DriveThruRPG |
| Amazon deals | ❌ broken | needs Amazon API (Associates account) |
| Custom domain | 🚧 building | rpghunt.com not bought |

## Next up
1. Check the 28 Oct report: "Leads and new sellers", "New shops", cost, run time
2. Stores on other platforms (BigCommerce, Squarespace, custom carts): found but not readable yet
3. Remember answers to "Needs your check" (the same questions come back daily)

## Known issues
- Same "Needs your check" questions every day (about 30 to 50, mostly DriveThruRPG, which the agent cannot open).
- 5 shops read nothing daily (Demiplane, Fanatical, Massif Press, Roll20, Monkey's Paw); weekly recipe retries fail.
- Modiphius US is set to GBP (it sells in USD).
- A day the Mac is off at 07:30 has no run until the new LaunchAgent is installed.

## Blocked on you
- OK to reinstall the LaunchAgent with the start-up catch-up
- Buy rpghunt.com; Amazon Associates and DriveThruRPG affiliate accounts
