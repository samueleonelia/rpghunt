# RPG Hunt daily report, 2026-10-29

## Alerts

- **Deals NOT put on the site: the site file has no deals.**
- **Shops that look broken (deals collapsed): bundle-of-holding, humble-bundle, itch.**

## The short version

- 0 deals would go on the site (none).
- 0 deals were left for the browsing agent; it handled 0 of them today.
- 2 item(s) need your check.
- 53 shops read; 0 sale links in the lead posts were not found by our readers.
- Everything ran.

## Numbers by step

1. **Shops:** 53 shops, 8 read fine, 0 blocked us, 45 had errors. They gave 0 possible deals.
2. **Leads and new sellers:** 72 links from 2 of 18 sources (13 on shops we read, 1 on shops that block robots, 58 on unknown sites). 58 unknown sites, 0 checked today (the rest were checked in the last 30 days), 0 new shops added.
3. **Misses:** 0 leads were not in today's run; 0 turned into candidate deals.
4. **Jev check:** 0 deals in, 0 unchanged since an earlier run (verdict reused, no cost), 0 dropped by plain rules (not a discount, ended), 0 dropped as not RPG, 0 passed, 0 sent to the agent, 0 waiting for price history.
5. **Browsing agent:** 6 jobs found, 6 run now, 0 answered from memory (same link and price, no cost), 0 deals it published.
6. **Site file:** 0 deals (0 with a picture, 0 linked to the game list).

## Published by type

Nothing published.

## Top 10 deals

None.

## New shops

None today.

## Shops that look broken

- **bundle-of-holding**: 0 deals today, usually about 4.57. Its reader may have stopped working.
- **humble-bundle**: 0 deals today, usually about 26.71. Its reader may have stopped working.
- **itch**: 0 deals today, usually about 530.0. Its reader may have stopped working.

## Sites that block us

None today.

All sites that ever blocked us: 47 (`data/shops/blocked-sites.json`). We never get around a block (good-bot rule).

## Safety limits hit

None. Every shop was read to the end.

## Misses

None.

## Needs your check

- **Bundle of Holding** (Bundle of Holding): https://bundleofholding.com/
  Question: The scraper cannot read Bundle of Holding's sales (break alarm). Open https://bundleofholding.com/ and tell me where its sale page is, or say 'pause it' if it has none.
- **Humble Bundle** (Humble Bundle): https://www.humblebundle.com/books
  Question: The scraper cannot read Humble Bundle's sales (break alarm). Open https://www.humblebundle.com/books and tell me where its sale page is, or say 'pause it' if it has none.

## Time per step

- Read the shops: 22.0 s (ok)
- Find leads and new shops: 51.9 s (ok): 72 leads, 0 new shops; feeds that could not be read: enworld, enworld-news, rascal, geeknative, tribality, ttrpgkids, gnomestew, cannibal-halfling, tenfootpole, tabletopgaming, icv2, wargamer, gamingtrend, questingbeast, boardgamewire, slyflourish
- Look for misses: 0.1 s (ok): 0 misses, 0 became candidate deals
- Jev check: 1.7 s (ok)
- Browsing agent: 947.6 s (ok)
- Build the site file: 0.0 s (ok): 0 deals; pages opened 0, from cache 0
- Put the deals on the site: 0.0 s (refused): the site file has no deals
- **Total: 1023.3 s (17.1 min)**

## Cost

- Jev: 0 requests, 0 tokens in, 0 tokens out, 0 answers reused from cache, about $0.00.
- Browsing agent: 6 job(s), $0.66.
- **Day total: about $0.66** (alarm at $5.00).
