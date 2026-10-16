# Reviews brief: find independent reviews for deals

RPG Hunt shows, next to each deal, what other people think of the product.
You find **independent reviews** and summarize each verdict in one line, in
your own words. We link to the review; we never copy its text.

## Input
A JSON list of deals: `key`, `title`, `game`, `shop`, `type`, `url`, `summary`.
For bundles and multi-book deals, review the main game or line it contains
(e.g. "Cthulhu Awakens" for a Cthulhu Awakens bundle).

## For each deal, find 0 to 3 reviews
- Good sources: review blogs and sites (Rascal, EN World, Cannibal Halfling Gaming,
  Bell of Lost Souls, Geek Native, Tabletop Gaming magazine, independent RPG blogs),
  YouTube review videos, and substantive Reddit review posts.
- Not reviews: the publisher's own site, shop product pages, press releases,
  Kickstarter pages, "news: X is out" posts, AI-generated SEO pages.
- The review must be about **this product** (or, for a bundle, its main game),
  not a different edition unless nothing else exists (then say so in `notes`).
- Prefer recent, substantive reviews. 0 is a fine answer for obscure items.
- Links: only URLs you opened with WebFetch, or copied exactly from WebSearch
  results. Never build a URL by hand. A script will open every link and drop
  any that fail or do not mention the product.

## Output
One JSON object per input deal, same order:

```json
{"key": "...", "reviews": [
  {"source": "Cannibal Halfling Gaming", "url": "https://...", "kind": "article",
   "verdict": "Praises the tight investigation rules, finds the setting thin.",
   "score": "8/10", "date": "2024-03"}
], "notes": null}
```

- `kind`: `article`, `video` or `forum`.
- `verdict`: max 20 words, your own words, what the reviewer concluded. No quotes.
- `score`: the reviewer's own score as written ("4/5", "8/10"), or `null`. Never invent one.
- `date`: `YYYY-MM` or `YYYY` if known, else `null`.

Write the JSON array to the output path you were given. Valid JSON only.
Reply with one line per deal: title and number of reviews found.
