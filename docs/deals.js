// RPG Hunt: loads data/deals.json and renders the home page (top deals, rows by
// type) or a results grid (search, "View all", nav).

const TYPE_LABEL = { bundle: "Bundle", free: "Free", sale: "Digital sale", physical: "Print deal" };
// Home page rows, in order. "ending" is every deal with an end date, soonest first.
const ROWS = [
  { key: "ending", title: "Ending soon" },
  { key: "bundle", title: "Bundles" },
  { key: "free", title: "Free right now" },
  { key: "sale", title: "Digital sales" },
  { key: "physical", title: "Print deals" },
];
const SYMBOL = { USD: "$", EUR: "€", GBP: "£", CAD: "CA$", AUD: "A$" };

let deals = [];
let dataDate = null;

const $ = (sel) => document.querySelector(sel);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null && c !== false) node.append(c);
  return node;
}

function money(value, currency) {
  if (value == null) return null;
  if (value === 0) return "Free";
  const sym = SYMBOL[currency] || "";
  const num = Number.isInteger(value) ? String(value) : value.toFixed(2);
  return sym ? `${sym}${num}` : `${num} ${currency || ""}`.trim();
}

function endsText(ends) {
  if (!ends) return null;
  // Whole calendar days between the check date and the end date (both read as noon to dodge time zones).
  const days = Math.round((new Date(ends + "T12:00:00") - new Date(dataDate + "T12:00:00")) / 86400000);
  if (days <= 0) return ["Ends today", true];
  if (days === 1) return ["Ends tomorrow", true];
  if (days <= 7) return [`Ends in ${days} days`, days <= 3];
  return [`Until ${new Date(ends + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric" })}`, false];
}

// "store.paizo.com" -> "paizo.com", "blackwellwriter.itch.io" -> "itch.io"
function siteName(url) {
  const parts = new URL(url).hostname.split(".");
  const keep = /^(co|com|org|net)\.[a-z]{2}$/.test(parts.slice(-2).join(".")) ? 3 : 2;
  return parts.slice(-keep).join(".");
}

// A reviewer's own score converted to 5 stars. Only scores with a scale count
// ("8.5/10", "4 out of 5"); a bare "4.5" could mean anything, so it is skipped.
function criticStars(score) {
  const m = /([0-9]+(?:\.[0-9]+)?)\s*(?:\/|out of)\s*([0-9]+)/i.exec(score || "");
  return m && Number(m[2]) > 0 ? (Number(m[1]) / Number(m[2])) * 5 : null;
}

// One rating per deal: every shop rating and every scored review counts as one vote.
function aggregate(d) {
  let sum = 0;
  let count = 0;
  if (d.rating) {
    sum += d.rating.value * d.rating.count;
    count += d.rating.count;
  }
  for (const r of d.reviews || []) {
    const stars = criticStars(r.score);
    if (stars != null) {
      sum += stars;
      count += 1;
    }
  }
  return count ? { value: sum / count, count } : null;
}

function ratingLine(d) {
  const agg = aggregate(d);
  // Every card gets a star row so cards line up; unrated deals say so instead of looking badly rated.
  if (!agg) {
    return el("div", { class: "rating none", "aria-label": "No ratings yet" },
      el("span", { class: "stars", "aria-hidden": "true", style: "--fill: 0%" }, "★★★★★"), " No ratings yet");
  }
  const value = Math.round(agg.value * 10) / 10;
  return el("div", { class: "rating", "aria-label": `Rated ${value.toFixed(1)} out of 5 from ${agg.count} ratings` },
    el("span", { class: "stars", "aria-hidden": "true", style: `--fill: ${(agg.value / 5) * 100}%` }, "★★★★★"),
    ` ${value.toFixed(1)} from ${agg.count.toLocaleString("en-US")} rating${agg.count === 1 ? "" : "s"}`);
}

function cover(d) {
  const box = el("div", { class: "deal-cover" });
  const fallback = () => box.replaceChildren(el("div", { class: "fallback" }, d.game || d.title), kind);
  const kind = el("span", { class: "deal-kind" }, TYPE_LABEL[d.type] || d.type);
  if (d.image) {
    const img = el("img", { src: d.image, alt: `Cover of ${d.title}`, loading: "lazy", referrerpolicy: "no-referrer" });
    img.addEventListener("error", fallback);
    box.append(img, kind);
  } else {
    fallback();
  }
  return box;
}

// Every card has the same slots in the same order, even when a slot is empty,
// so titles, prices, stars, text and buttons line up across a row.
function card(d) {
  const ends = endsText(d.ends);
  return el("article", { class: "card deal" },
    cover(d),
    el("div", { class: "deal-body" },
      el("h3", { title: d.title }, d.title),
      priceRow(d),
      ratingLine(d),
      el("p", { class: "desc" }, d.summary || ""),
      el("div", { class: "ends" + (ends && ends[1] ? " soon" : "") }, ends ? ends[0] : ""),
      el("div", { class: "deal-actions" },
        el("a", { class: "btn primary", href: d.url, target: "_blank", rel: "noopener" }, d.type === "free" ? "Get it free" : "Get the deal")),
      el("p", { class: "deal-source" }, siteName(d.url)),
    ),
  );
}

const byDiscount = (a, b) => (b.type === "free") - (a.type === "free") || (b.discount_pct || 0) - (a.discount_pct || 0);
const byEnd = (a, b) => a.ends.localeCompare(b.ends) || byDiscount(a, b);

function rowDeals(key) {
  if (key === "ending") return deals.filter((d) => d.ends).sort(byEnd);
  return deals.filter((d) => d.type === key).sort(byDiscount);
}

function priceRow(d) {
  const now = money(d.price_now, d.currency);
  const was = now && d.price_was && d.price_was !== d.price_now ? money(d.price_was, d.currency) : null;
  // Some sales are "40% off everything" with no single price: show the discount in the price slot.
  const lead = now || (d.discount_pct ? `${d.discount_pct}% off` : "See price");
  return el("div", { class: "deal-price" },
    el("span", { class: "now" }, lead),
    was ? el("span", { class: "was" }, was) : null,
    now && d.discount_pct ? el("span", { class: "off" }, `-${d.discount_pct}%`) : null);
}

// Ranked list of the 9 biggest discounts, like a top-sellers board.
function topNine() {
  const top = deals.filter((d) => d.discount_pct).sort(byDiscount).slice(0, 9);
  return el("section", { class: "wrap top9" },
    el("div", { class: "section-head centered" },
      el("h2", {}, "Top 9 deals"),
      el("p", {}, "The biggest discounts today.")),
    el("ol", { class: "top9-list" }, ...top.map((d, i) => {
      const thumb = el("div", { class: "top9-thumb" });
      if (d.image) thumb.append(el("img", { src: d.image, alt: "", loading: "lazy", referrerpolicy: "no-referrer" }));
      return el("li", {},
        el("span", { class: "rank", "aria-hidden": "true" }, String(i + 1)),
        thumb,
        el("div", { class: "top9-body" },
          el("h3", {}, el("a", { href: d.url, target: "_blank", rel: "noopener" }, d.title)),
          d.summary ? el("p", { class: "desc" }, d.summary) : null,
          ratingLine(d),
          priceRow(d),
          el("p", { class: "deal-source" }, siteName(d.url))));
    })));
}

function row(def) {
  const list = rowDeals(def.key);
  if (!list.length) return null;
  const all = el("button", { type: "button", class: "btn" }, "View all →");
  all.addEventListener("click", () => showResults(def.key));
  return el("section", { class: "wrap row" },
    el("div", { class: "section-head" }, el("h2", {}, def.title), all),
    el("div", { class: "grid deals" }, ...list.slice(0, 4).map(card)));
}

function renderHome() {
  $("#sections").replaceChildren(topNine(), ...ROWS.map(row).filter(Boolean));
}

let current = null;
// Results grid: 24 cards at a time, "Show more" adds the next 24 (best discounts first).
const PAGE = 24;
let shown = [];

function updateMore() {
  const grid = $("#grid");
  const left = shown.length - grid.children.length;
  const more = $("#more");
  more.hidden = left <= 0;
  more.textContent = `Show ${Math.min(PAGE, left)} more (${left} left)`;
}

function showMore() {
  const grid = $("#grid");
  grid.append(...shown.slice(grid.children.length, grid.children.length + PAGE).map(card));
  updateMore();
}

function showResults(key, query = "") {
  current = key;
  let list;
  let title;
  if (query) {
    const q = query.toLowerCase();
    list = deals.filter((d) => [d.title, d.game, d.shop, d.summary].filter(Boolean).join(" ").toLowerCase().includes(q)).sort(byDiscount);
    title = `Results for "${query}"`;
  } else {
    list = rowDeals(key);
    title = (ROWS.find((r) => r.key === key) || {}).title;
  }
  $("#home").hidden = true;
  $("#results").hidden = false;
  $("#results-title").textContent = title;
  shown = list;
  $("#grid").replaceChildren(...list.slice(0, PAGE).map(card));
  updateMore();
  $("#count").textContent = `${list.length} deal${list.length === 1 ? "" : "s"}`;
  $("#empty").hidden = list.length > 0;
  document.querySelectorAll("#nav button").forEach((b) => b.setAttribute("aria-current", String(!query && b.dataset.key === key)));
  window.scrollTo(0, 0);
}

function showHome() {
  current = null;
  $("#q").value = "";
  $("#home").hidden = false;
  $("#results").hidden = true;
  document.querySelectorAll("#nav button").forEach((b) => b.setAttribute("aria-current", "false"));
}

function renderNav() {
  const buttons = ROWS.filter((r) => rowDeals(r.key).length).map((r) => {
    const b = el("button", { type: "button", "data-key": r.key, "aria-current": "false" }, r.key === "free" ? "Free" : r.title);
    b.addEventListener("click", () => showResults(r.key));
    return b;
  });
  $("#nav").replaceChildren(...buttons);
}

// Hero background: a wall of today's deal covers, repeated to fill 18 tiles.
function renderWall() {
  const wall = $("#hero-wall");
  const images = deals.map((d) => d.image).filter(Boolean);
  if (!wall || !images.length) return; // decoration only: never block the deals
  const tiles = Array.from({ length: 18 }, (_, i) => images[i % images.length]);
  wall.replaceChildren(...tiles.map((src) => el("img", { src, alt: "", loading: "lazy", referrerpolicy: "no-referrer" })));
}

// Thin bar on top: the deal that ends soonest.
function renderAnnounce() {
  const d = rowDeals("ending")[0];
  if (!d) return;
  const ends = endsText(d.ends);
  const bar = $("#announce");
  bar.replaceChildren(el("div", { class: "wrap" },
    el("span", {}, `${ends[0]}: ${d.title}${d.discount_pct ? `, ${d.discount_pct}% off` : ""}`),
    el("a", { href: d.url, target: "_blank", rel: "noopener" }, "Get it")));
  bar.hidden = false;
}

async function init() {
  const res = await fetch("data/deals.json", { cache: "no-cache" }); // always ask the server: the daily run replaces this file
  const data = await res.json();
  // Until the daily run exists, the data can be days old: hide deals that have ended since.
  const d = new Date();
  const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  deals = data.deals.filter((x) => !x.ends || x.ends >= today);
  dataDate = data.date;
  $("#checked").textContent = `${deals.length} deals · last checked ${new Date(dataDate + "T12:00:00").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}.`;
  renderAnnounce();
  renderWall();
  renderNav();
  renderHome();
  $("#back").addEventListener("click", showHome);
  $("#more").addEventListener("click", showMore);
  // Deal alerts: Kit form 10082554 (public form id, no key). If the background request fails,
  // the form posts normally and Kit shows its own confirmation page.
  $("#signup")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const form = e.currentTarget;
    const email = $("#signup-email");
    const note = $("#signup-note");
    const button = form.querySelector("button");
    if (!email.checkValidity()) {
      note.textContent = "Please enter a valid email address.";
      email.focus();
      return;
    }
    button.disabled = true;
    note.textContent = "Signing you up…";
    try {
      const res = await fetch(form.action, { method: "POST", body: new FormData(form), headers: { Accept: "application/json" } });
      const body = await res.json().catch(() => ({}));
      if (!res.ok || (body.status && body.status !== "success")) throw new Error(body.status || res.status);
      form.reset();
      note.textContent = "Almost done: check your inbox and confirm your email to get deal alerts.";
    } catch {
      form.submit();
    } finally {
      button.disabled = false;
    }
  });
  $("#q").addEventListener("input", (e) => (e.target.value.trim() ? showResults(null, e.target.value.trim()) : showHome()));
}

init();
