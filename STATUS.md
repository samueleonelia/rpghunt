# STATUS: RPG Hunt (rpgArchive)

_Updated: 2026-10-27 · branch main_

<!-- Rewrite this file in place. Never append. History belongs in DEVLOG.md. Keep under 60 lines. -->

**What this is:** A daily list of tabletop RPG deals, collected and verified by AI agents, English products only for now.

**Right now:** Live at https://samueleonelia.github.io/rpghunt/ with 2,175 checked deals (28 Oct run, 56 min, $2.35). Every day the run looks for new sellers by itself (news feeds and Wikipedia) and reads every itch.io sale page. First real run added 7 shops.

## Feature areas
| Area | State | Note |
|---|---|---|
| Live site | ✅ working | paging, bot page; 2,175 deals |
| Finding new sellers | ✅ working | 15 news feeds + Wikipedia RPG publishers/designers; 7 shops added on day 1; no daily cap |
| Shop readers | ✅ working | 53 shops (Shopify, WooCommerce, itch, BigCommerce and others) |
| itch.io (indie authors) | ✅ working | all sale pages, 1,807 deals (42 min); page cache; 4 games at a time |
| English-only rule | ✅ working | non-English titles dropped; non-English shops not added |
| New-sale rule, Jev check, memory | ✅ working | only new or changed deals are paid for |
| Browsing agent | ✅ working | runs from launchd |
| Daily schedule | ✅ working | launchd 07:30, plus at start-up if the Mac was off (installed 28 Oct) |
| Sites that block us | ✅ working | `data/shops/blocked-sites.json`, never bypassed |
| Deal alerts form | 🚧 building | Kit form; needs one real test signup |
| Amazon deals | ❌ broken | needs Amazon API (Associates account) |
| Custom domain | 🚧 building | rpghunt.com not bought |

## Next up
1. Make itch faster (42 of the 56 minutes) without hitting its rate limit
2. Stores on other platforms (BigCommerce, Squarespace, custom carts): found but not readable yet
3. Remember answers to "Needs your check" (the same questions come back daily)

## Known issues
- "Sites that block us" lists news-post link targets that are not shops (ad trackers, newsrooms): noise.
- 94 items in "Needs your check"; the same questions come back daily.
- 5 shops read nothing daily (Demiplane, Fanatical, Massif Press, Roll20, Monkey's Paw).
- Modiphius US is set to GBP (it sells in USD).

## Blocked on you
- Buy rpghunt.com; Amazon Associates and DriveThruRPG affiliate accounts
