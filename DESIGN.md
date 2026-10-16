---
name: RPG Hunt
description: Today's tabletop RPG deals, checked every day.
colors:
  hunt-ochre: "#e6af3e"
  ochre-ink: "#1a1205"
  ember: "#ff7a59"
  sage: "#8ccf98"
  night-bg: "#14120f"
  lamp-card: "#1c1a16"
  chip-umber: "#2a2620"
  line-umber: "#332f29"
  rank-umber: "#6e6659"
  parchment-ink: "#f0ebe2"
  dust-muted: "#aea596"
typography:
  display:
    fontFamily: "Archivo, system-ui, -apple-system, Segoe UI, Roboto, sans-serif"
    fontSize: "clamp(2rem, 4.5vw, 3.2rem)"
    fontWeight: 800
    lineHeight: 1.05
    letterSpacing: "-0.02em"
    fontVariation: "'wdth' 90"
  headline:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 800
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 90"
  price:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 800
    lineHeight: 1
    fontVariation: "'wdth' 85"
    fontFeature: "'tnum' 1"
  rank:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "5.2rem"
    fontWeight: 800
    lineHeight: 1
    fontVariation: "'wdth' 75"
  brand:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.6rem"
    fontWeight: 800
    letterSpacing: "-0.01em"
    fontVariation: "'wdth' 112"
  title:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1.15rem"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "'tnum' 1"
  label:
    fontFamily: "Archivo, system-ui, sans-serif"
    fontSize: "0.82rem"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  tag: "6px"
  control: "8px"
  thumb: "10px"
  card: "12px"
  pill: "999px"
spacing:
  xs: "6px"
  sm: "8px"
  md: "14px"
  lg: "16px"
  xl: "48px"
  xxl: "56px"
components:
  button-primary:
    backgroundColor: "{colors.hunt-ochre}"
    textColor: "{colors.ochre-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "6px 11px"
  button-secondary:
    backgroundColor: "{colors.night-bg}"
    textColor: "{colors.parchment-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "6px 11px"
  deal-card:
    backgroundColor: "{colors.lamp-card}"
    textColor: "{colors.parchment-ink}"
    rounded: "{rounded.card}"
    padding: "14px 16px 16px"
  discount-badge:
    backgroundColor: "{colors.hunt-ochre}"
    textColor: "{colors.ochre-ink}"
    rounded: "{rounded.tag}"
    padding: "4px 8px"
  deal-kind-label:
    textColor: "{colors.parchment-ink}"
    rounded: "{rounded.tag}"
    padding: "4px 9px"
  search-field:
    backgroundColor: "{colors.night-bg}"
    textColor: "{colors.parchment-ink}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
  chip-tag:
    backgroundColor: "{colors.chip-umber}"
    textColor: "{colors.parchment-ink}"
    rounded: "{rounded.pill}"
    padding: "5px 11px"
  chip-tag-selected:
    backgroundColor: "{colors.hunt-ochre}"
    textColor: "{colors.ochre-ink}"
  badge:
    backgroundColor: "{colors.chip-umber}"
    textColor: "{colors.dust-muted}"
    rounded: "{rounded.tag}"
    padding: "4px 9px"
  announce-bar:
    backgroundColor: "{colors.hunt-ochre}"
    textColor: "{colors.ochre-ink}"
    padding: "8px 16px"
  site-header:
    backgroundColor: "{colors.lamp-card}"
    textColor: "{colors.parchment-ink}"
    padding: "14px 16px"
---

# Design System: RPG Hunt

## Overview

**Creative North Star: "The Evening Deal Board"**

RPG Hunt is a deal board read after dark: warm near-black surfaces, parchment-colored text, and one ochre accent that marks only what earns a click (the discount, the buy button, the selected filter, the stars). It is browsed in the evening, between sessions, often on a phone, so the page is always dark and dense enough to scan in seconds.

The structure is a marketplace front page in the AppSumo mould: a thin ochre announcement bar, a sticky header with a pill search, a centered headline, a short trust row, a ranked Top 9 list, then rows of four deal cards each with a View all button. Every deal card has the same layout and always shows a cover image, so the eye learns one card and reads the rest.

Type is a single family, Archivo, used across its width axis: condensed and heavy for prices, rank numerals and headlines; wide for the wordmark; normal width for reading. There are no serif faces anywhere. Depth comes from tonal steps between three dark surfaces and hairline borders, not from shadows.

**Key Characteristics:**
- Always dark, warm umber-tinted neutrals.
- One accent (ochre), used sparingly for price, action and selection.
- One typeface (Archivo), with personality carried by width and weight, not by a second family.
- Flat surfaces separated by 1px warm borders; no drop shadows.
- Identical deal cards: cover, title, rating, price, summary, end date, buttons, shop domain.

## Colors

A warm, low-chroma umber dark palette with a single ochre accent and two small signal colors.

### Primary
- **Hunt Ochre** (`--accent`): the only accent. Primary buttons, discount badges, the announcement bar, selected chips and language toggle, rating stars, review links, trust-row icons, focus outlines, text selection and the input caret.
- **Ochre Ink** (`--accent-ink`): the near-black text placed on ochre, never used on its own.

### Tertiary
- **Ember** (`--urgent`): only for "ends soon" deadlines (with weight 600). It is a signal, not a second accent.
- **Sage** (`--ok`): only for positive status badges (in print, Italian edition available) on the game catalog.

### Neutral
- **Night Background** (`--bg`): the page background, and the fill of inputs and secondary buttons so they read as sunk into the surface.
- **Lamp Card** (`--card`): cards and the header band, one tonal step above the page.
- **Chip Umber** (`--chip`): chips, badges, and the empty cover/thumbnail box behind images.
- **Line Umber** (`--line`): every 1px border and divider, and the scrollbar thumb.
- **Rank Umber**: the oversized Top 9 rank numerals only; decorative and low-contrast on purpose.
- **Parchment Ink** (`--ink`): primary text.
- **Dust Muted** (`--muted`): secondary text: summaries, meta, was-prices, shop domain, nav links at rest, placeholders.

### Named Rules
**The Always Dark Rule.** The site has no light theme. `color-scheme: dark` is set on the root; every new surface uses the night, lamp and chip steps.

**The One Accent Rule.** Ochre is the only accent color. Red is not the accent; Ember appears only for an urgent deadline.

## Typography

**Display Font:** Archivo (variable width 62 to 125, weight 400 to 800), with system-ui fallback
**Body Font:** Archivo
**Label/Mono Font:** Archivo; numbers use tabular figures site-wide

**Character:** One grotesque stretched to do every job. Condensed heavy numerals make prices and ranks punch; the wide wordmark gives the brand a stance; regular width keeps reading calm.

### Hierarchy
- **Display** (800, clamp(2rem, 4.5vw, 3.2rem), 1.05, width 90%): the single home headline, centered, max 18ch, balanced wrap.
- **Headline** (800, 1.6rem, width 90%): section titles ("Top 9 deals", row titles, results).
- **Price** (800, 1.6rem, 1, width 85%): the current price on a deal card; 1.15rem in the Top 9 list.
- **Rank** (800, 5.2rem, 1, width 75%): Top 9 position numerals behind the thumbnail.
- **Brand** (800, 1.6rem, width 112%): the "RPG Hunt" wordmark, "Hunt" in ochre.
- **Title** (700, 1.15rem, 1.25): card titles, balanced wrap; 1.02rem in the Top 9 list.
- **Body** (400, 1rem, 1.5): running text; hero subline at 1.05rem, max 56ch. Card summaries at 0.93rem, clamped to 3 lines (2 in Top 9).
- **Label** (400, 0.78 to 0.9rem): buttons (0.82rem), meta, rating line (0.85rem), shop domain (0.78rem), nav (0.92rem).

### Named Rules
**The No Serif Rule.** Archivo is the only family. Do not introduce a serif or a second display face; vary width and weight instead.

**The Rating Wording Rule.** Ratings read exactly "★ 4.9 from 393 ratings": an ochre star, one decimal, the count with thousands separators, the word "ratings".

## Layout

A centered container (max 1180px, 16px side gutter). The home page follows a fixed order: announcement bar, sticky header (wordmark, search up to 520px wide, deal-type nav), centered hero (56px top), trust row of three icon items, Top 9 section, then deal rows. Each section starts 48px below the previous one.

Deal rows show four cards from an auto-fill grid (min 240px columns, 14px gap); View all opens the full results grid with the same cards. The Top 9 list is an auto-fill grid of 320px minimum columns (28px by 32px gap), each item a 76px square thumbnail beside a text stack, with the rank numeral tucked behind on the left. The footer sits 56px below the content.

Below 720px the header stops being sticky and the nav drops to its own full-width row, scrolling sideways with the scrollbar hidden.

## Elevation & Depth

Flat. Depth is three tonal steps (night background, lamp card, chip umber) plus 1px warm borders. The only overlay is the deal-kind label, a translucent night chip (`rgba(20, 18, 15, .85)`) sitting on the cover image.

### Named Rules
**The Flat Board Rule.** No drop shadows. The only box-shadow in the system is a 2px ochre ring marking a focused card, a state signal, not elevation.

## Shapes

Soft rectangles and pills. Cards are gently rounded (12px), thumbnails slightly less (10px), buttons and selects 8px, small badges 6px. Anything you type into or toggle in a group (search field, filter chips, language switch) is a full pill. Covers are clipped to the card's corners at a 4:3 ratio with the image contained, never cropped; Top 9 thumbnails are square and cropped to fill.

## Components

### Buttons
Compact and quiet; the ochre one is the only loud thing on a card.
- **Shape:** gently rounded (8px).
- **Primary:** ochre fill, ochre-ink text, weight 700 on deal cards ("Get the deal", "Get it free"), 6px by 11px padding, 0.82rem.
- **Secondary:** night fill, parchment text, 1px line border ("About [game]", "View all", "All deals").
- **Hover / Focus:** the border turns ochre on hover; keyboard focus gets a 2px ochre outline, offset 2px.

### Chips
- **Style:** pill, chip-umber fill, 1px line border, 0.8rem.
- **State:** selected chips (and the active language toggle) switch to ochre fill with ochre-ink text.

### Cards / Containers
- **Corner Style:** 12px.
- **Background:** lamp card on the night page.
- **Shadow Strategy:** none (see Elevation & Depth).
- **Border:** 1px line umber.
- **Internal Padding:** cover flush to the edges, body 14px 16px 16px, 8px gap between lines.

### Inputs / Fields
- **Style:** pill, night fill, 1px line border, muted search icon (18px stroke SVG), muted placeholder, ochre caret.
- **Focus:** the whole pill border turns ochre (focus-within).

### Navigation
- **Style:** text links and buttons in dust muted, 0.92rem, no fill. Hover and current item turn parchment with an underline offset 4px. On narrow screens the row scrolls sideways.

### Deal Card (signature)
Every deal uses this one layout, in this order: 4:3 cover image (game title in condensed heavy muted text as fallback) with the deal-type label top left; title; rating line; price row (current price, struck-through was price, ochre "-NN%" badge); summary clamped to 3 lines; end date (ember and bold when ending soon); actions (primary buy button, secondary "About" button); then the shop's bare domain (e.g. amazon.com) in 0.78rem muted text under the buttons. The shop appears once, there.

### Top 9 Ranked List (signature)
Nine biggest discounts as a numbered board: an oversized condensed rank numeral in rank umber, a 76px rounded thumbnail, then title link, 2-line summary, rating, compact price row and shop domain.

### Announcement Bar
A thin full-width ochre strip above the header carrying the deal that ends soonest, with a bold underlined "Get it" link.

## Do's and Don'ts

### Do:
- **Do** keep every surface dark: night background, lamp card, chip umber.
- **Do** reserve ochre for price badges, the main action, selection, stars and focus.
- **Do** show a cover image on every deal and keep every deal card in the same order.
- **Do** show the shop once per card, as its bare domain in small muted text under the buttons.
- **Do** write ratings as "★ 4.9 from 393 ratings".
- **Do** use Archivo's width axis (condensed for numbers, wide for the wordmark) instead of adding fonts.
- **Do** keep the AppSumo-style home order: announcement bar, header with search, headline, trust row, Top 9, rows of 4 with View all.

### Don't:
- **Don't** add a light theme or light surfaces.
- **Don't** use red or any second hue as the accent.
- **Don't** use serif fonts anywhere.
- **Don't** repeat information on a card (no shop name in two places, no duplicated price or label).
- **Don't** add drop shadows to cards or buttons.
