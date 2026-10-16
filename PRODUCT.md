# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack
Static HTML/CSS/vanilla JS reading JSON data files, hosted on GitHub Pages. No framework, no build step. Data is produced offline by AI agents and Python scripts (`scripts/`), then committed.

## Users
Active tabletop RPG players and game masters, English-speaking, who already play and own some books. They check in regularly to grow their collection cheaply: a sale on a game they have been eyeing, a bundle worth grabbing, a free adventure for next session.

## Product Purpose
A daily list of the tabletop RPG deals active today, collected and checked by AI agents. Each deal links straight to the shop selling it. A visit succeeds when the visitor finds a deal they want and clicks out to buy (or download, if free).

Behind the deals sits a catalog of games (started as the "RPG Archive" pilot: 50 researched games, 1,425 in the Wikidata seed). Each deal links to its game's page so the visitor can judge the game, not just the price.

## Positioning
Today's RPG deals in one place, refreshed every day and verified. What exists now is weekly and hand-made (EN World's roundup) or one store at a time. Deals that have ended are removed, not left to rot.

## Operating Context
- Deal types tracked: digital sales (PDF/VTT on DriveThruRPG, itch.io, publisher webstores, Roll20/Foundry), bundles (Bundle of Holding, Humble Bundle), physical book discounts (Amazon, large shops), and limited-time free giveaways.
- Visitors arrive from a bookmark, a newsletter or social post, or a search like "RPG sale today"; most visits are short, scan-then-click.
- Deals expire: every deal has an end date when the source gives one.

## Capabilities and Constraints
- English first. Italian later (the pilot UI already has an EN/IT switch and Italian descriptions).
- Every link is opened by a script before it is published; links that fail are dropped.
- DriveThruRPG and Palladium block automated visitors; DriveThruRPG may need its affiliate program or another feed.
- Links are plain for now; affiliate links (Amazon Associates, DriveThruRPG) come later and need accounts only the owner can create.
- Name: **RPG Hunt** (rpghunt.com). On 2026-10-16 rpghunt.com/.net/.io were unregistered and no site or brand named "RPG Hunt" was found. "rpgpromo" was rejected: rpgpromo.com is an active indie RPG promotion site.
- Undecided: refresh frequency (daily is the goal) and where the scheduled agents run.

## Evidence on Hand
- `docs/data/games.json`: 50 games with verified publisher/shop links, descriptions in English and Italian.
- `data/seed.json`: 1,425 games from Wikidata (CC0).
- No deals data, users, testimonials, traffic or affiliate income exist yet. Do not invent any.

## Product Principles
1. A dead deal is worse than no deal: freshness and verified links come before volume.
2. The price is the hook, the game is the reason: every deal shows what the game is in one glance.
3. One click to the shop: no detours, no sign-up walls.
4. Honest about what it is: say when data was last checked and that agents collect it.
