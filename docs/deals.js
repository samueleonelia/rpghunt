// RPG Hunt: loads data/deals.json and renders today's deals with a type filter.

const TYPES = [
  ["all", "All deals"],
  ["bundle", "Bundles"],
  ["free", "Free"],
  ["sale", "Digital sales"],
  ["physical", "Print"],
];
const TYPE_LABEL = { bundle: "Bundle", free: "Free", sale: "Digital sale", physical: "Print deal" };
const SYMBOL = { USD: "$", EUR: "€", GBP: "£", CAD: "CA$", AUD: "A$" };

let deals = [];
let dataDate = null;
let filter = "all";

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

function ratingLine(d) {
  if (!d.rating) return null;
  return el("div", { class: "rating" },
    el("span", { class: "stars", "aria-hidden": "true" }, "★"),
    ` ${d.rating.value.toFixed(1)} · ${d.rating.count.toLocaleString("en-US")} ratings on ${siteName(d.url)}`);
}

function reviewList(d) {
  const reviews = d.reviews || [];
  if (!reviews.length) return null;
  return el("details", { class: "reviews" },
    el("summary", {}, `${reviews.length} review${reviews.length === 1 ? "" : "s"}`),
    el("ul", {}, ...reviews.map((r) => el("li", {},
      el("a", { href: r.url, target: "_blank", rel: "noopener" }, r.source),
      r.score ? el("span", { class: "score" }, ` ${r.score}`) : null,
      el("p", {}, r.verdict)))));
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

function card(d) {
  const now = money(d.price_now, d.currency);
  const was = d.price_was && d.price_was !== d.price_now ? money(d.price_was, d.currency) : null;
  const ends = endsText(d.ends);
  return el("article", { class: "card deal" },
    cover(d),
    el("div", { class: "deal-body" },
      el("h2", {}, d.title),
      now ? el("div", { class: "deal-price" },
        el("span", { class: "now" }, now),
        was ? el("span", { class: "was" }, was) : null,
        d.discount_pct ? el("span", { class: "off" }, `-${d.discount_pct}%`) : null) : null,
      ratingLine(d),
      d.summary ? el("p", { class: "desc" }, d.summary) : null,
      reviewList(d),
      ends ? el("div", { class: "ends" + (ends[1] ? " soon" : "") }, ends[0]) : null,
      el("div", { class: "deal-actions" },
        el("a", { class: "btn primary", href: d.url, target: "_blank", rel: "noopener" }, d.type === "free" ? "Get it free" : "Get the deal"),
        d.game_id ? el("a", { class: "btn", href: `games.html#${encodeURIComponent(d.game_id)}` }, `About ${d.game}`) : null),
      el("p", { class: "deal-source" }, siteName(d.url)),
    ),
  );
}

function render() {
  const list = deals.filter((d) => filter === "all" || d.type === filter);
  $("#grid").replaceChildren(...list.map(card));
  $("#count").textContent = `${list.length} deal${list.length === 1 ? "" : "s"}`;
  $("#empty").hidden = list.length > 0;
}

function renderTypes() {
  const present = new Set(deals.map((d) => d.type));
  $("#types").replaceChildren(...TYPES.filter(([k]) => k === "all" || present.has(k)).map(([key, label]) => {
    const n = key === "all" ? deals.length : deals.filter((d) => d.type === key).length;
    const b = el("button", { type: "button", class: "tag", "aria-pressed": String(filter === key) }, `${label} (${n})`);
    b.addEventListener("click", () => {
      filter = key;
      document.querySelectorAll("#types .tag").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      render();
    });
    return b;
  }));
}

async function init() {
  const res = await fetch("data/deals.json");
  const data = await res.json();
  // Until the daily run exists, the data can be days old: hide deals that have ended since.
  const d = new Date();
  const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  deals = data.deals.filter((x) => !x.ends || x.ends >= today);
  dataDate = data.date;
  $("#checked").textContent = `Last checked ${new Date(dataDate + "T12:00:00").toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}.`;
  renderTypes();
  render();
}

init();
