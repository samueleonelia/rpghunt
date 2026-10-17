# Jev check spec (phase 2)

Jev (TypeSafe, model `jev-latest`, HTTP `POST https://api.typesafe.ai/v1/systemone`, Python SDK `typesafe-sdk`) answers fixed questions with probabilities. It never writes text, so a page can't make it do anything. Code keeps every number, date and final decision; Jev only judges meaning.

Input: `data/deals/raw/<date>-scraper.json` (phase 1). Output: `data/deals/raw/<date>-checked.json` (deals that passed, same shape plus a `check` block) and `data/deals/check-report-<date>.json`.
Code: `scraper/check.py` (runner), `scraper/jev.py` (client wrapper), `scraper/history.py` (price history), `scraper/trim.py` (page trimmer + price candidates).

## Rules
- API key only from the environment (`TYPESAFE_API_KEY`, loaded from `.env` by the SDK or by `os.environ`); never printed, logged or written anywhere. Agents never open `.env`.
- Every Jev call goes through `scraper/jev.py`, which caches answers by a hash of (state, questions, model) in `data/jev-cache/` (gitignored), so re-runs and tuning cost nothing.
- Without a key, `check.py --dry-run` runs everything except the Jev calls and reports what it would ask (counts and token estimate).
- Pages are trimmed before Jev sees them: hidden elements dropped (inline `display:none`, `visibility:hidden`, `hidden`, `<script>`, `<style>`, `<noscript>`, `aria-hidden`), then the product area kept (title, price block, description start), at most about 1,500 words.

## Stage A: RPG triage (no page fetch)
One request per batch of 20 deals. State: `{"products": [{"title", "shop", "product_type", "tags", "categories", "vendor", "format"}...]}` (from the deal and its `hints`). One Noul per product:

- instructions: "Is `products[i]` a tabletop roleplaying game product?"
- criteria.true: "A rulebook, core book, adventure, campaign, supplement, setting book, bestiary, zine, quickstart, starter set, or a bundle of these, in print, PDF or as a VTT module, used to play a tabletop roleplaying game."
- criteria.false: "Anything else: miniatures and wargame models or rules, board games, card games, dice, dice trays, GM screens, maps, tokens, card decks, notebooks, journals and stationery, apparel, pins, posters, art books, novels and fiction, video games, STL files, gift cards, software, or books about other subjects."

Policy (code): p >= 0.70 RPG; p < 0.30 drop; between: stage B decides with the page (ask again with page text).

## Stage B: deal check
For every deal that is RPG or unsure after stage A. Deals from the shop's own data feed (`source` in `shopify-api`, `woocommerce-api`, `itch-data`, `drivethrurpg-api`, `bundle-page`) skip the page questions 2 and 3; their prices are the shop's own data. Deals from page reading (`jsonld`, `page-markup`, `recipe`) or any lead/agent source get all questions.

State: `{"claimed_deal": {title, shop, price_now, price_was, currency, ends, type}, "shop_data": {product_type, tags, categories}, "price_history": {"days_seen": n, "lowest_before": x, "usual_price": y}, "page": {"url", "title", "text", "price_candidates": ["$12.95", "$53.00", ...]}}`

1. `rpg` (only for stage A unsure): the stage A Noul, with `page.text` as extra evidence.
2. `support` Choice: "How does `page` relate to `claimed_deal`?"
   - `supports`: "The page shows this product currently priced at `claimed_deal.price_now`, below a normal, list or original price."
   - `contradicts`: "The page shows a different current price, says the sale or offer has ended, shows no discount, or is about a different product."
   - `silent`: "The page does not show enough to tell."
3. `price_now_pick` / `price_was_pick` Choice: "Which amount in `page.price_candidates` is the product's current selling price?" / "...the normal, list or original price it is compared against?" Options: each candidate string plus `none`. Code compares the picks with the claimed prices (exact match after normalizing); Jev never computes.
4. `offer_kind` Choice: "How is the lower price presented?"
   - `promotion`: "A sale, discount, deal, bundle offer or coupon that is temporary or promotional."
   - `clearance`: "Clearance, outlet, warehouse sale, reduced or last-chance stock."
   - `everyday`: "The shop's normal everyday price shown below a list price, RRP or MSRP, with no sale wording."
   - `unclear`: "Can't tell."

## Price history (code, `data/prices/<shop_id>.json`, committed)
Every run records `{url: [[date, price_now, price_was], ...]}` for every deal seen (last 120 days). `usual_price` = most common price over the window; `lowest_before` = lowest before today. Code rule: a deal whose `offer_kind` is `everyday` is published only if `price_now` is below `usual_price` (a real drop we saw ourselves). Day 1 has no history, so everyday deals wait.

## Decision (code, thresholds tuned in step 2.3; start values)
Publish when all hold:
- code checks: `is_discount`, `ends` not past, and for page-sourced deals `price_now` appears in the visible trimmed text
- RPG: p >= 0.70
- feed-sourced: `offer_kind` in promotion/clearance with confidence >= 0.6, or `everyday` with a history drop
- page-sourced: `support` = supports with confidence >= 0.80, AND `price_now_pick` equals the claimed price
Drop when: RPG p < 0.30, `support` = contradicts with confidence >= 0.80, or picks disagree with the claim.
Everything else goes to `needs_agent` in the report (phase 3: Claude rechecks; still unsure goes to "Needs your check").

## Gate 2
- all 5 fakes rejected (the 2 fixture pages are served locally for the test)
- at least 27 of the 29 test-set deals published, the rest in `needs_agent`, none dropped as contradicted
- report: deals in, RPG dropped, published, needs_agent, Jev tokens used and cost
