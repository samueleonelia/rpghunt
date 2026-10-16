# Deals brief: find today's tabletop RPG deals

You find tabletop RPG deals that are **active today** for RPG Hunt, a daily
deals site for players and game masters. Only tabletop RPGs (rulebooks,
adventures, supplements, bundles, RPG VTT modules). No video games, no board
games, no dice or accessories.

A dead or expired deal is worse than no deal. Prefer 10 solid deals over 40 shaky ones.

## Deal types
- `sale`: a digital product (PDF, VTT module) discounted below its normal price
- `bundle`: many products for one price, time-limited (Bundle of Holding, Humble Bundle...)
- `physical`: a print book or boxed set discounted below its normal price
- `free`: normally paid, free for a limited time (also permanent free items only if newly released this week)

## How to research
- Use WebSearch and WebFetch. Good discovery sources: the store's own sale/deals pages, EN World's weekly "freebies, sales and charity bundles" column, publisher news posts, r/rpg deal threads. **Always link the shop page itself, never the roundup article.**
- Many shops block your fetch tool (403). Rules for links are the same as in `agents/research-brief.md`:
  only URLs you opened, or URLs copied exactly from WebSearch results. Never build a URL by hand.
- Confirm the deal is still running today (today's date is in your task). If an end date
  has passed, or you only see it in an article older than 14 days with no end date, skip it.
- The site's tool guard may block "buy"/checkout pages. Do not work around it; use the product page, or skip.

## Output: one JSON object per deal

| Field | Rule |
|---|---|
| `type` | `sale`, `bundle`, `physical` or `free` |
| `title` | what is on sale, as the shop names it, e.g. `"Blades in the Dark (PDF)"` or `"Bundle of Holding: Traveller Classic"` |
| `game` | the RPG it belongs to, e.g. `"Blades in the Dark"`, `"Call of Cthulhu"`; `null` for multi-game bundles or system-neutral items |
| `shop` | store name, e.g. `"DriveThruRPG"`, `"Bundle of Holding"`, `"Free League webstore"` |
| `url` | the shop page for this deal (rules above) |
| `price_now` | number, `0` for free; `null` if unknown |
| `price_was` | number, normal price; `null` if unknown |
| `currency` | `"USD"`, `"EUR"`, `"GBP"`... |
| `discount_pct` | integer if stated or computable, else `null` |
| `format` | `pdf`, `print`, `vtt`, or `mixed` |
| `ends` | end date `YYYY-MM-DD` if known, else `null` |
| `summary` | one sentence, your own words: what you get and why it is a good deal |
| `found_via` | the URL where you learned about the deal (can be a roundup) |
| `confidence` | `high` (you saw the price and dates on the shop page), `medium` (shop page blocked, but a source from the last 7 days confirms it), `low` (do not include `low` deals: skip them) |
| `notes` | anything uncertain, else `null` |

Write a JSON array of deals to the output path you were given. Valid JSON only.
Then reply with one line per deal: title, shop, price, confidence.
