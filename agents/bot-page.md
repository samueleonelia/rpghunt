# RPGHuntBot (text for https://samueleonelia.github.io/rpghunt/bot.html)

The Lead publishes this as `docs/bot.html`. Replace `CONTACT_EMAIL` with the real address first.

---

## Who we are

RPGHuntBot belongs to RPG Hunt (https://samueleonelia.github.io/rpghunt/), a free, non-commercial daily list of tabletop RPG deals: sales, bundles, discounted books and free giveaways. Every deal on our site links straight to the shop that sells it. We send shoppers to you; we do not resell anything.

Our bot's name in your logs is:

`RPGHuntBot/1.0 (+https://samueleonelia.github.io/rpghunt/bot.html)`

## What we read

- Public product data: title, current price, normal price, the product link. In practice this is a shop's public product feed (for example a Shopify `/products.json`, a WooCommerce store API, an itch.io feed, or a public product API) or, when there is no feed, the public product page.
- Nothing behind a login. No carts, no checkout, no customer data, no forms.
- We do not try to get around bot walls, CAPTCHAs or blocks. If a shop blocks us, we leave it alone.

## How politely

- We read your `robots.txt` first and follow it. If it disallows us (by the name `RPGHuntBot` or `*`), we do not fetch those pages.
- One request at a time per site, at most one request every 1.5 seconds.
- We stop and back off when a site answers "429 Too Many Requests".
- We read each shop about once a day.

## Ask us to stop

Email CONTACT_EMAIL with your shop's address and we will stop reading it and remove it from our list. You can also block us yourself with this in your `robots.txt`:

```
User-agent: RPGHuntBot
Disallow: /
```

If we read too much, too often, or something looks wrong in your logs, tell us at the same address and we will fix it.
