"""Jev check (phase 2): which raw deals are real, current, tabletop RPG deals?

python -m scraper.check [--date D] [--fake | --dry-run] [--limit N] [--include-fakes] [--fetch-pages]

Spec: agents/jev-check-spec.md. Jev only judges meaning (RPG or not, does the page back the
claim, which amount on the page is the current price). Code keeps every number, date and the
final decision.

Input   data/deals/raw/<date>-scraper.json
Output  data/deals/raw/<date>-checked.json         published deals (+ a "check" block)
        data/deals/check-report-<date>.json        counts, per-deal reasons, needs_agent, Jev tokens
With --fake the files get a -FAKE suffix: FakeJev is a keyword test double, never for publishing.
--dry-run makes no Jev call and writes no output; it prints what a real run would ask and cost.
"""
import argparse
import collections
import concurrent.futures
import datetime
import json
import threading
import urllib.parse

from scraper.common import RAW, ROOT, TESTSET, FetchError, fetch, load_shops, norm_url, plain
from scraper.history import History
from scraper.jev import MODEL, FakeJev, Jev, JevError, load_env_key, request_chars
from scraper.score import matches as testset_matches
from scraper.trim import normalize_money, prices_in, trim

REPORTS = ROOT / "data" / "deals"
FIXTURES = TESTSET / "fixtures"

# All tunable numbers live here (tuned in step 2.3; these are the spec's start values).
THRESHOLDS = {
    "rpg_yes": 0.70,            # stage A / rpg question: p >= this is an RPG product
    "rpg_no": 0.30,             # p < this is dropped; between the two is "unsure"
    "support_conf": 0.80,       # `supports` needs this confidence to publish
    "contradict_conf": 0.80,    # `contradicts` at this confidence drops the deal
    "pick_conf": 0.60,          # a price pick that disagrees with the claim drops the deal at this confidence
    "offer_conf": 0.60,         # promotion / clearance / everyday need this confidence
    "history_min_days": 1,      # days of earlier history needed before an everyday price may count as a drop
    "everyday_no_history": "wait",  # what an everyday deal without a history drop becomes: "wait" or "needs_agent"
    "batch_size": 20,           # stage A products per request
}
FEED_SOURCES = {"shopify-api", "woocommerce-api", "itch-data", "bundle-page"}   # the shop's own data feed
COST_PER_M_INPUT = 0.042        # dollars per million input tokens (output tokens not priced here)
WORKERS = 8
# dry-run assumptions (only used where the real number needs Jev answers or page fetches)
DRY_PAGE_CHARS = 6000           # about 1,000 words of trimmed page
DRY_PAGE_CANDIDATES = 6
DRY_UNSURE_RATE = 0.10          # share of feed deals stage A leaves "unsure" (they need a page fetch)
FETCH_SECONDS = 2.2             # 1.5 s polite delay + about 0.7 s for the request itself

RPG_CRITERIA = {
    "true": ("A rulebook, core book, adventure, campaign, supplement, setting book, bestiary, zine, "
             "quickstart, starter set, or a bundle of these, in print, PDF or as a VTT module, used to "
             "play a tabletop roleplaying game."),
    "false": ("Anything else: miniatures and wargame models or rules, board games, card games, dice, "
              "dice trays, GM screens, maps, tokens, card decks, apparel, pins, posters, art books, "
              "novels and fiction, video games, STL files, gift cards, software, or books about other "
              "subjects."),
}
SUPPORT_CRITERIA = {
    "supports": "The page shows this product currently priced at `claimed_deal.price_now`, below a normal, list or original price.",
    "contradicts": ("The page shows a different current price, says the sale or offer has ended, shows no "
                    "discount, or is about a different product."),
    "silent": "The page does not show enough to tell.",
}
OFFER_CRITERIA = {
    "promotion": "A sale, discount, deal, bundle offer or coupon that is temporary or promotional.",
    "clearance": "Clearance, outlet, warehouse sale, reduced or last-chance stock.",
    "everyday": "The shop's normal everyday price shown below a list price, RRP or MSRP, with no sale wording.",
    "unclear": "Can't tell.",
}


# ---------------------------------------------------------------- state and questions

def _list(v, n):
    if isinstance(v, str):
        v = [v]
    return [str(x) for x in (v or [])][:n]


def product_row(deal):
    h = deal.get("hints") or {}
    return {"title": deal["title"], "shop": deal["shop"], "product_type": h.get("product_type"),
            "tags": _list(h.get("tags"), 12), "categories": _list(h.get("categories"), 8),
            "vendor": h.get("vendor"), "format": deal.get("format")}


def rpg_question(subject, extra=""):
    return {"type": "noul", "instructions": f"Is {subject} a tabletop roleplaying game product?{extra}",
            "criteria": dict(RPG_CRITERIA)}


def build_stage_a(deals):
    """One request for up to batch_size deals: one Noul per product."""
    state = {"products": [product_row(d) for d in deals]}
    questions = {f"p{i}": rpg_question(f"`products[{i}]`") for i in range(len(deals))}
    return state, questions


def claimed_deal(d):
    # found_via is an addition to the spec's list: it is the only evidence about the offer for
    # deals that skip the page (e.g. a Shopify "reduced-price" collection).
    return {"title": d["title"], "shop": d["shop"], "price_now": d["price_now"], "price_was": d["price_was"],
            "currency": d.get("currency"), "ends": d.get("ends"), "type": d.get("type"),
            "found_via": d.get("found_via")}


def shop_data(d):
    h = d.get("hints") or {}
    return {"product_type": h.get("product_type"), "tags": _list(h.get("tags"), 12),
            "categories": _list(h.get("categories"), 8)}


def build_stage_b(deal, facts, page, ask_rpg, ask_page):
    """-> (state, questions) for one deal. page may be None (feed deal that was not fetched)."""
    state = {"claimed_deal": claimed_deal(deal), "shop_data": shop_data(deal), "price_history": facts}
    if page is not None:
        state["page"] = page
    q = {}
    if ask_rpg:
        q["rpg"] = rpg_question("`claimed_deal`", " Use `page` as extra evidence.")
    if ask_page:
        cands = page["price_candidates"] if page else []
        q["support"] = {"type": "choice", "instructions": "How does `page` relate to `claimed_deal`?",
                        "criteria": dict(SUPPORT_CRITERIA)}
        q["price_now_pick"] = {
            "type": "choice",
            "instructions": "Which amount in `page.price_candidates` is the product's current selling price?",
            "criteria": {**{c: None for c in cands}, "none": "None of the amounts is the current selling price."}}
        q["price_was_pick"] = {
            "type": "choice",
            "instructions": ("Which amount in `page.price_candidates` is the normal, list or original price "
                             "the current selling price is compared against?"),
            "criteria": {**{c: None for c in cands}, "none": "None of the amounts is that normal, list or original price."}}
    if not needs_offer_check(deal):
        return state, q
    q["offer_kind"] = {
        "type": "choice",
        "instructions": ("How is the lower price presented?" if page is not None
                         else "How is the lower price in `claimed_deal` presented?"),
        "criteria": dict(OFFER_CRITERIA)}
    return state, q


# ---------------------------------------------------------------- pages

def load_page(deal):
    """Raw HTML of the deal's page. `fixture:<file>` reads data/testset/fixtures/<file>."""
    url = deal["url"]
    if url.startswith("fixture:"):
        return (FIXTURES / url.split(":", 1)[1]).read_text()
    resp = fetch(url)
    return resp.body.decode(resp.encoding or "utf-8", "ignore")


def is_page_sourced(deal):
    return deal.get("source") not in FEED_SOURCES


_everyday_shops = None


def everyday_shop(deal):
    """Shops flagged `everyday_discounts` (retailers whose normal prices sit below list price)."""
    global _everyday_shops
    if _everyday_shops is None:
        _everyday_shops = {s["id"] for s in load_shops() if s.get("everyday_discounts")}
    return deal.get("shop_id") in _everyday_shops


def needs_offer_check(deal):
    """A publisher's own sale price in its own shop data is the promotion itself. Only page-read
    deals and retailers with everyday below-list prices need Jev's offer_kind (and history)."""
    return is_page_sourced(deal) or everyday_shop(deal)


# ---------------------------------------------------------------- decisions (pure code)

def code_check(deal, date):
    """Reason string when plain code already rejects the deal, else None."""
    now, was = deal.get("price_now"), deal.get("price_was")
    if now is None or was is None or not now < was:
        return "not_a_discount: price_now is not below price_was"
    ends = (deal.get("ends") or "")[:10]
    if ends and ends < date:
        return f"ended: ends {ends} is before {date}"
    return None


def rpg_status(p, T):
    return "rpg" if p >= T["rpg_yes"] else "drop" if p < T["rpg_no"] else "unsure"


def _same(pick, value):
    v = normalize_money(pick)
    return v is not None and value is not None and abs(v - float(value)) < 0.005


def decide(deal, rpg_p, answers, page, facts, T=THRESHOLDS):
    """-> (decision, reasons, check). decision: publish | drop | needs_agent | wait.

    answers: Jev's stage B answers (None when no Jev call was made); page: the trimmed page or None.
    Drop beats everything; then anything missing goes to needs_agent; an everyday price with no
    drop in our history only waits (T["everyday_no_history"]).
    """
    drops, blockers, wait = [], [], []
    ans = answers or {}
    check = {"rpg_p": round(rpg_p, 3), "history": facts, "page_fetched": page is not None}

    if rpg_p < T["rpg_no"]:
        drops.append(f"rpg_no: p={rpg_p:.2f}")
    elif rpg_p < T["rpg_yes"]:
        blockers.append(f"rpg_unsure: p={rpg_p:.2f}")

    if is_page_sourced(deal):
        in_text = page is not None and any(abs(v - deal["price_now"]) < 0.005 for v in prices_in(page["text"]))
        check["price_now_in_text"] = in_text
        if page is None:
            blockers.append("no_page: page could not be read")
        elif not in_text:
            blockers.append(f"price_not_in_text: {deal['price_now']} is not shown on the page")
        sup = ans.get("support")
        if sup:
            check["support"] = {"choice": sup["choice"], "confidence": round(sup["confidence"], 3)}
            if sup["choice"] == "contradicts" and sup["confidence"] >= T["contradict_conf"]:
                drops.append(f"contradicted: page contradicts the claim ({sup['confidence']:.2f})")
            elif sup["choice"] == "supports" and sup["confidence"] >= T["support_conf"]:
                pass
            else:
                blockers.append(f"support_unsure: {sup['choice']} ({sup['confidence']:.2f})")
        for key, field in (("price_now_pick", "price_now"), ("price_was_pick", "price_was")):
            pick = ans.get(key)
            if not pick:
                continue
            check[key] = {"choice": pick["choice"], "confidence": round(pick["confidence"], 3)}
            if pick["choice"] == "none":
                if key == "price_now_pick":
                    blockers.append("pick_none: no amount picked as the current price")
            elif not _same(pick["choice"], deal[field]):
                reason = f"pick_mismatch: {key} {pick['choice']} is not the claimed {deal[field]}"
                (drops if pick["confidence"] >= T["pick_conf"] else blockers).append(reason)

    off = ans.get("offer_kind")
    if off:
        check["offer_kind"] = {"choice": off["choice"], "confidence": round(off["confidence"], 3)}
        kind, conf = off["choice"], off["confidence"]
        if kind in ("promotion", "clearance"):
            if conf < T["offer_conf"]:
                blockers.append(f"offer_unsure: {kind} ({conf:.2f})")
        elif kind == "everyday":
            usual = facts.get("usual_price")
            if conf < T["offer_conf"]:
                blockers.append(f"offer_unsure: everyday ({conf:.2f})")
            elif facts.get("days_seen", 0) >= T["history_min_days"] and usual is not None and deal["price_now"] < usual:
                check["history_drop"] = True
            else:
                wait.append("everyday_no_drop: everyday price with no drop in our price history")
        else:
            blockers.append("offer_unclear")
    elif not drops and needs_offer_check(deal):
        blockers.append("offer_not_asked")

    if drops:
        return "drop", drops, check
    if blockers:
        return "needs_agent", blockers, check
    if wait:
        return T["everyday_no_history"], wait, check
    return "publish", ["ok"], check


# ---------------------------------------------------------------- the run

def check_deals(deals, date, jev, history, load=load_page, T=THRESHOLDS, workers=WORKERS):
    """Run both stages. -> (results, stats). results[i] = {"decision", "stage", "reasons", "check"}."""
    results = [None] * len(deals)
    stats = collections.Counter()
    lock = threading.Lock()

    def put(i, decision, stage, reasons, check=None):
        results[i] = {"decision": decision, "stage": stage, "reasons": reasons, "check": check or {}}

    todo = []
    for i, d in enumerate(deals):
        why = code_check(d, date)
        if why:
            put(i, "drop", "code", [why])
        else:
            todo.append(i)

    # ---- stage A: triage in batches, no page fetch
    size = T["batch_size"]
    batches = [todo[k:k + size] for k in range(0, len(todo), size)]
    stage_p = {}

    def run_a(batch):
        state, questions = build_stage_a([deals[i] for i in batch])
        try:
            ans = jev.ask(state, questions)
            return batch, [ans[f"p{k}"]["noul"] for k in range(len(batch))], None
        except (JevError, KeyError) as e:
            return batch, None, f"jev_error: stage A {type(e).__name__} {e}"[:200]

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(4, max(1, len(batches)))) as pool:
        for batch, ps, err in pool.map(run_a, batches):
            stats["stage_a_requests"] += 1
            for k, i in enumerate(batch):
                if err:
                    put(i, "needs_agent", "A", [err])
                    continue
                stage_p[i] = ps[k]
                if rpg_status(ps[k], T) == "drop":
                    put(i, "drop", "A", [f"rpg_no: p={ps[k]:.2f}"], {"rpg_p": round(ps[k], 3)})

    # ---- stage B: one request per deal that is RPG or unsure
    pending = [i for i in todo if results[i] is None]

    def run_b(i):
        d, p_a = deals[i], stage_p[i]
        status = rpg_status(p_a, T)
        page_sourced = is_page_sourced(d)
        facts = history.facts(d, date)
        page = None
        if page_sourced or status == "unsure":
            try:
                page = {"url": d["url"], **trim(load(d), d["url"])}
                with lock:
                    stats["page_fetches"] += 1
            except (FetchError, OSError) as e:
                with lock:
                    stats["page_failures"] += 1
                kind = getattr(e, "kind", type(e).__name__)
                if page_sourced or status == "unsure":
                    put(i, "needs_agent", "B", [f"page_unreadable: {kind}"], {"rpg_p": round(p_a, 3), "history": facts})
                    return
        state, questions = build_stage_b(d, facts, page, ask_rpg=(status == "unsure"), ask_page=page_sourced)
        if not questions:  # a publisher's own sale, clearly an RPG: nothing left for Jev to judge
            decision, reasons, check = decide(d, p_a, {}, page, facts, T)
            check["rpg_stage_a"] = round(p_a, 3)
            put(i, decision, "B", reasons, check)
            return
        try:
            ans = jev.ask(state, questions)
        except JevError as e:
            put(i, "needs_agent", "B", [f"jev_error: stage B {e}"[:200]], {"rpg_p": round(p_a, 3), "history": facts})
            return
        with lock:
            stats["stage_b_requests"] += 1
        rpg_p = ans["rpg"]["noul"] if "rpg" in ans else p_a
        decision, reasons, check = decide(d, rpg_p, ans, page, facts, T)
        check["rpg_stage_a"] = round(p_a, 3)
        put(i, decision, "B", reasons, check)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run_b, pending))
    stats["stage_b_deals"] = len(pending)
    return results, stats


# ---------------------------------------------------------------- inputs

def load_fakes(date):
    """The planted fakes as deals that go through the same checker (all read as page deals)."""
    path = TESTSET / f"{date}-fakes.json"
    if not path.exists():
        return []
    out = []
    for f in json.loads(path.read_text()):
        d = {k: f[k] for k in ("type", "title", "game", "shop", "url", "price_now", "price_was", "currency", "ends",
                               "found_via") if k in f}
        d.update(shop_id=plain(f["shop"]).replace(" ", "-"), source="planted", hints={}, format=None,
                 _fake=f["id"], _fake_kind=f.get("fake_kind"))
        out.append(d)
    return out


def select(raw, date, limit):
    """All deals, or with a limit: the test-set deals first, then an evenly spaced sample."""
    if not limit or limit >= len(raw):
        return list(raw)
    tpath = TESTSET / f"{date}.json"
    tests = json.loads(tpath.read_text()) if tpath.exists() else []
    pick = [i for i, d in enumerate(raw) if any(testset_matches(t, d) for t in tests)][:limit]
    rest = [i for i in range(len(raw)) if i not in set(pick)]
    room = limit - len(pick)
    if room > 0 and rest:
        step = len(rest) / room
        pick += [rest[int(k * step)] for k in range(room)]
    return [raw[i] for i in sorted(pick)]


# ---------------------------------------------------------------- reports

def build_report(date, mode, deals, results, stats, jev, T):
    cnt = collections.Counter(r["decision"] for r in results)
    reasons = collections.Counter(r["reasons"][0].split(":")[0] for r in results if r["decision"] != "publish")
    real = [i for i, d in enumerate(deals) if not d.get("_fake")]
    fakes = [i for i, d in enumerate(deals) if d.get("_fake")]
    by_stage_drop = collections.Counter(results[i]["stage"] for i in real if results[i]["decision"] == "drop")
    usage = dict(jev.usage)
    report = {
        "date": date, "mode": mode, "fake_jev": mode == "fake", "model": MODEL, "thresholds": T,
        "counts": {
            "deals_in": len(real),
            "dropped_by_code": by_stage_drop["code"],
            "rpg_dropped_stage_a": by_stage_drop["A"],
            "stage_b_deals": stats["stage_b_deals"],
            "published": sum(results[i]["decision"] == "publish" for i in real),
            "dropped_total": sum(results[i]["decision"] == "drop" for i in real),
            "needs_agent": sum(results[i]["decision"] == "needs_agent" for i in real),
            "wait": sum(results[i]["decision"] == "wait" for i in real),
            "not_published_by_reason": dict(reasons.most_common()),
        },
        "requests": {"stage_a": stats["stage_a_requests"], "stage_b": stats["stage_b_requests"],
                     "page_fetches": stats["page_fetches"], "page_failures": stats["page_failures"]},
        "jev": {**usage, "estimated_cost_usd": round(usage["input_tokens"] / 1e6 * COST_PER_M_INPUT, 4),
                "cost_note": f"input tokens only, ${COST_PER_M_INPUT} per million"},
        "needs_agent": [{"url": deals[i]["url"], "title": deals[i]["title"], "shop": deals[i]["shop"],
                         "source": deals[i].get("source"), "reasons": results[i]["reasons"]}
                        for i in real if results[i]["decision"] == "needs_agent"],
        "deals": [{"url": deals[i]["url"], "title": deals[i]["title"], "shop": deals[i]["shop"],
                   "source": deals[i].get("source"), "decision": results[i]["decision"],
                   "stage": results[i]["stage"], "reasons": results[i]["reasons"],
                   "check": results[i]["check"]} for i in real],
    }
    if fakes:
        report["fakes"] = [{"id": deals[i]["_fake"], "kind": deals[i]["_fake_kind"],
                            "decision": results[i]["decision"], "rejected": results[i]["decision"] != "publish",
                            "reasons": results[i]["reasons"]} for i in fakes]
    tpath = TESTSET / f"{date}.json"
    if tpath.exists():
        tests, rows = json.loads(tpath.read_text()), []
        for t in tests:
            hit = next((i for i in real if testset_matches(t, deals[i])), None)
            rows.append({"id": t["id"], "decision": results[hit]["decision"] if hit is not None else "not_in_run",
                         "reasons": results[hit]["reasons"] if hit is not None else []})
        c = collections.Counter(r["decision"] for r in rows)
        report["testset"] = {"total": len(rows), "published": c["publish"], "needs_agent": c["needs_agent"],
                             "wait": c["wait"], "dropped": c["drop"], "not_in_run": c["not_in_run"],
                             "deals": rows}
    return report


def estimate(deals, date, T, history, fetch_pages=False, load=load_page):
    """Dry-run: what a real run would ask. Builds the real requests; pages are placeholders
    (or fetched for real with fetch_pages, page-sourced deals only)."""
    todo = [d for d in deals if code_check(d, date) is None]
    size = T["batch_size"]
    a_chars = sum(request_chars(*build_stage_a(todo[k:k + size])) for k in range(0, len(todo), size))
    a_req = -(-len(todo) // size)
    feed = [d for d in todo if not is_page_sourced(d)]
    paged = [d for d in todo if is_page_sourced(d)]
    b_chars = real_pages = 0
    hosts = collections.Counter()
    for d in paged:
        facts = history.facts(d, date)
        if fetch_pages:
            try:
                page = {"url": d["url"], **trim(load(d), d["url"])}
                real_pages += 1
            except (FetchError, OSError):
                page = None
        else:
            page = {"url": d["url"], "title": d["title"], "text": "x" * DRY_PAGE_CHARS,
                    "price_candidates": [f"${k}.99" for k in range(DRY_PAGE_CANDIDATES)]}
        if page is not None:
            hosts[urllib.parse.urlsplit(d["url"]).netloc] += 1
        b_chars += request_chars(*build_stage_b(d, facts, page, False, True))
    unsure = int(len(feed) * DRY_UNSURE_RATE)
    unsure_page = {"url": "", "title": "", "text": "x" * DRY_PAGE_CHARS,
                   "price_candidates": [f"${k}.99" for k in range(DRY_PAGE_CANDIDATES)]}
    if feed:
        fh = collections.Counter(urllib.parse.urlsplit(d["url"]).netloc for d in feed)
        for host, n in fh.items():
            hosts[host] += round(n * DRY_UNSURE_RATE)
        sample = feed[0]
        plain_chars = request_chars(*build_stage_b(sample, history.facts(sample, date), None, False, False))
        unsure_chars = request_chars(*build_stage_b(sample, history.facts(sample, date), unsure_page, True, False))
        b_chars += (len(feed) - unsure) * plain_chars + unsure * unsure_chars
    fetches = sum(hosts.values())
    secs_total = fetches * FETCH_SECONDS
    secs = max(max(hosts.values(), default=0) * FETCH_SECONDS, secs_total / WORKERS)
    tokens = (a_chars + b_chars) // 4
    return {
        "deals_after_code_checks": len(todo), "page_sourced": len(paged), "feed_sourced": len(feed),
        "stage_a_requests": a_req, "stage_b_requests": len(todo),
        "total_requests": a_req + len(todo),
        "input_tokens_stage_a": a_chars // 4, "input_tokens_stage_b": b_chars // 4,
        "input_tokens_estimate": tokens,
        "estimated_cost_usd_per_run": round(tokens / 1e6 * COST_PER_M_INPUT, 4),
        "page_fetches_certain": len(paged), "page_fetches_assumed_for_unsure_feed_deals": unsure,
        "page_fetches_total": fetches, "busiest_host_fetches": max(hosts.values(), default=0),
        "fetch_minutes_estimate": round(secs / 60, 1),
        "pages_really_fetched": real_pages,
        "assumptions": f"stage B asked for every deal stage A could pass (upper bound); chars/4 per token; "
                       f"pages {'fetched' if fetch_pages else f'{DRY_PAGE_CHARS} chars'}; "
                       f"{int(DRY_UNSURE_RATE * 100)}% of feed deals unsure and fetched; {FETCH_SECONDS}s per fetch per host; "
                       f"{WORKERS} hosts in parallel; Jev response time not counted",
    }


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m scraper.check")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--fake", action="store_true", help="FakeJev keyword test double instead of real Jev")
    mode.add_argument("--dry-run", action="store_true", help="no Jev calls; print requests, tokens and cost")
    ap.add_argument("--limit", type=int, default=0, help="check only N deals (test-set deals first, then an even sample)")
    ap.add_argument("--include-fakes", action="store_true", help="also run the planted fakes through the checker")
    ap.add_argument("--fetch-pages", action="store_true", help="with --dry-run: really fetch the page-sourced pages")
    args = ap.parse_args(argv)

    raw_path = RAW / f"{args.date}-scraper.json"
    if not raw_path.exists():
        print(f"missing {raw_path.relative_to(ROOT)}; run: python -m scraper.run --date {args.date}")
        return 1
    raw = json.loads(raw_path.read_text())
    history = History()
    history.record(raw, args.date)          # every raw deal, every run (idempotent per date)
    deals = select(raw, args.date, args.limit)
    if args.include_fakes:
        deals += load_fakes(args.date)
    print(f"{len(raw)} raw deals, {len(deals)} to check")

    if args.dry_run:
        for k, v in estimate(deals, args.date, THRESHOLDS, history, args.fetch_pages).items():
            print(f"  {k}: {v}")
        return 0

    if args.fake:
        jev, label, suffix = FakeJev(), "fake", "-FAKE"
    else:
        if not load_env_key():
            print("TYPESAFE_API_KEY is not set. Use --dry-run or --fake, or add the key to the environment.")
            return 2
        jev, label, suffix = Jev(), "real", ""

    results, stats = check_deals(deals, args.date, jev, history)
    report = build_report(args.date, label, deals, results, stats, jev, THRESHOLDS)
    published = [dict(d, check={**results[i]["check"], "decision": "publish", "checked_on": args.date,
                                "model": MODEL, "fake_jev": label == "fake"})
                 for i, d in enumerate(deals) if results[i]["decision"] == "publish" and not d.get("_fake")]
    out = RAW / f"{args.date}-checked{suffix}.json"
    rep = REPORTS / f"check-report-{args.date}{suffix}.json"
    out.write_text(json.dumps(published, ensure_ascii=False, indent=1) + "\n")
    rep.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")

    c, j = report["counts"], report["jev"]
    print(f"in {c['deals_in']}: code-dropped {c['dropped_by_code']}, not RPG {c['rpg_dropped_stage_a']}, "
          f"dropped total {c['dropped_total']}, published {c['published']}, needs_agent {c['needs_agent']}, wait {c['wait']}")
    print(f"requests: A {stats['stage_a_requests']}, B {stats['stage_b_requests']}, pages {stats['page_fetches']} "
          f"({stats['page_failures']} failed); Jev tokens in {j['input_tokens']} out {j['output_tokens']}, "
          f"cache hits {j['cache_hits']}, about ${j['estimated_cost_usd']}")
    for f in report.get("fakes", []):
        print(f"  fake {f['id']}: {f['decision']} ({f['reasons'][0]})")
    if "testset" in report:
        t = report["testset"]
        print(f"test set: {t['published']} published, {t['needs_agent']} needs_agent, {t['wait']} wait, "
              f"{t['dropped']} dropped, {t['not_in_run']} not in run (of {t['total']})")
    print(f"wrote {out.relative_to(ROOT)} and {rep.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
