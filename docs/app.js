// RPG Archive: loads data/games.json and renders a searchable, filterable list.

const TEXT = {
  en: {
    tagline: "Every tabletop role-playing game, with direct links to where you can get it.",
    search: "Search games, publishers, designers...",
    sortName: "A to Z", sortNew: "Newest first", sortOld: "Oldest first",
    itOnly: "Available in Italian", printOnly: "In print",
    count: (n, total) => `${n} of ${total} games`,
    empty: "No games match these filters.",
    by: "by", inPrint: "In print", outOfPrint: "Out of print",
    italian: "Italian edition", current: "Current",
    official: "Official site", store: "Shop", free: "Free rules",
    footer: "Data researched by AI agents, links checked automatically. Game info from Wikidata (CC0). Prices and availability may change.",
  },
  it: {
    tagline: "Tutti i giochi di ruolo da tavolo, con i link diretti per comprarli.",
    search: "Cerca giochi, editori, autori...",
    sortName: "Dalla A alla Z", sortNew: "Più recenti", sortOld: "Più vecchi",
    itOnly: "Disponibile in italiano", printOnly: "In commercio",
    count: (n, total) => `${n} giochi su ${total}`,
    empty: "Nessun gioco corrisponde ai filtri.",
    by: "di", inPrint: "In commercio", outOfPrint: "Fuori catalogo",
    italian: "Edizione italiana", current: "Attuale",
    official: "Sito ufficiale", store: "Negozio", free: "Regole gratis",
    footer: "Dati raccolti da agenti AI, link controllati in automatico. Info sui giochi da Wikidata (CC0). Prezzi e disponibilità possono cambiare.",
  },
};

const TAG_NAMES = {
  it: {
    fantasy: "fantasy", "dark-fantasy": "dark fantasy", "sci-fi": "fantascienza", cyberpunk: "cyberpunk",
    space: "spazio", horror: "horror", "cosmic-horror": "orrore cosmico", "post-apocalyptic": "post-apocalittico",
    superhero: "supereroi", historical: "storico", mythology: "mitologia", steampunk: "steampunk",
    western: "western", "urban-fantasy": "urban fantasy", mystery: "mistero", comedy: "comico",
    mecha: "mecha", cozy: "cozy", generic: "generico", osr: "OSR", narrative: "narrativo", crunchy: "regole dettagliate",
  },
};

const state = { lang: "en", q: "", tags: new Set(), sort: "name", itOnly: false, printOnly: false };
let games = [];

const $ = (sel) => document.querySelector(sel);
const t = (key) => TEXT[state.lang][key];
const tagName = (tag) => (TAG_NAMES[state.lang] || {})[tag] || tag.replace(/-/g, " ");

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const c of children) if (c != null && c !== false) node.append(c);
  return node;
}

function amazonUrl(domain, query) {
  return `https://www.${domain}/s?k=${encodeURIComponent(query)}`;
}

function card(g) {
  const desc = (state.lang === "it" && g.description_it) || g.description_en;
  const title = (state.lang === "it" && g.name_it) || g.name;
  const altTitle = title !== g.name ? g.name : (state.lang === "en" && g.name_it && g.name_it !== g.name ? g.name_it : null);

  const meta = [g.year, g.publishers && g.publishers[0]].filter(Boolean).join(" · ");
  const badges = el("div", { class: "badges" },
    g.current_edition ? el("span", { class: "badge" }, `${t("current")}: ${g.current_edition}`) : null,
    el("span", { class: "badge" + (g.in_print ? " ok" : "") }, g.in_print ? t("inPrint") : t("outOfPrint")),
    g.italian_edition ? el("span", { class: "badge ok" }, `🇮🇹 ${t("italian")}: ${g.italian_edition.publisher}`) : null,
  );
  const tags = el("div", { class: "badges" }, ...(g.tags || []).map((tag) => el("span", { class: "badge" }, tagName(tag))));

  const links = el("div", { class: "links" });
  (g.links || []).forEach((l, i) => {
    links.append(el("a", { class: "btn" + (i === 0 ? " primary" : ""), href: l.url, target: "_blank", rel: "noopener" }, l.label || t(l.type)));
  });
  if (g.italian_edition && g.italian_edition.url) {
    links.append(el("a", { class: "btn", href: g.italian_edition.url, target: "_blank", rel: "noopener" }, `🇮🇹 ${g.italian_edition.publisher}`));
  }
  if (g.amazon_query) {
    const itQuery = g.name_it ? `${g.name_it} gioco di ruolo` : g.amazon_query;
    links.append(el("a", { class: "btn", href: amazonUrl("amazon.com", g.amazon_query), target: "_blank", rel: "noopener" }, "Amazon.com"));
    links.append(el("a", { class: "btn", href: amazonUrl("amazon.it", itQuery), target: "_blank", rel: "noopener" }, "Amazon.it"));
  }

  return el("article", { class: "card" },
    el("h2", {}, title),
    altTitle ? el("div", { class: "alt" }, altTitle) : null,
    meta ? el("div", { class: "meta" }, meta) : null,
    tags,
    desc ? el("p", { class: "desc" }, desc) : null,
    badges,
    links,
  );
}

function haystack(g) {
  return [g.name, g.name_it, ...(g.publishers || []), ...(g.designers || []), ...(g.tags || [])]
    .filter(Boolean).join(" ").toLowerCase();
}

function render() {
  const q = state.q.trim().toLowerCase();
  let list = games.filter((g) =>
    (!q || g._hay.includes(q)) &&
    (!state.itOnly || g.italian_edition) &&
    (!state.printOnly || g.in_print) &&
    [...state.tags].every((tag) => (g.tags || []).includes(tag)));

  const byName = (a, b) => a.name.localeCompare(b.name);
  if (state.sort === "new") list.sort((a, b) => (b.year || 0) - (a.year || 0) || byName(a, b));
  else if (state.sort === "old") list.sort((a, b) => (a.year || 9999) - (b.year || 9999) || byName(a, b));
  else list.sort(byName);

  $("#grid").replaceChildren(...list.map(card));
  $("#count").textContent = t("count")(list.length, games.length);
  $("#empty").hidden = list.length > 0;
}

function renderTags() {
  const all = [...new Set(games.flatMap((g) => g.tags || []))].sort();
  $("#tags").replaceChildren(...all.map((tag) => {
    const b = el("button", { type: "button", class: "tag", "aria-pressed": String(state.tags.has(tag)) }, tagName(tag));
    b.addEventListener("click", () => {
      state.tags.has(tag) ? state.tags.delete(tag) : state.tags.add(tag);
      b.setAttribute("aria-pressed", String(state.tags.has(tag)));
      render();
    });
    return b;
  }));
}

function applyLang() {
  document.documentElement.lang = state.lang;
  document.querySelectorAll("[data-t]").forEach((n) => { n.textContent = t(n.dataset.t); });
  document.querySelectorAll("[data-t-placeholder]").forEach((n) => { n.placeholder = t(n.dataset.tPlaceholder); });
  document.querySelectorAll(".lang button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === state.lang)));
  renderTags();
  render();
}

function setLang(lang) {
  state.lang = lang;
  try { localStorage.setItem("lang", lang); } catch (e) { /* storage blocked: fine */ }
  applyLang();
}

async function init() {
  let saved = null;
  try { saved = localStorage.getItem("lang"); } catch (e) { /* ignore */ }
  state.lang = saved || (navigator.language.startsWith("it") ? "it" : "en");

  document.querySelectorAll(".lang button").forEach((b) => b.addEventListener("click", () => setLang(b.dataset.lang)));
  $("#q").addEventListener("input", (e) => { state.q = e.target.value; render(); });
  $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
  $("#itOnly").addEventListener("change", (e) => { state.itOnly = e.target.checked; render(); });
  $("#printOnly").addEventListener("change", (e) => { state.printOnly = e.target.checked; render(); });

  const res = await fetch("data/games.json");
  games = await res.json();
  games.forEach((g) => { g._hay = haystack(g); });
  applyLang();
}

init();
