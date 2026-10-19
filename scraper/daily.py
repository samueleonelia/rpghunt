"""The whole scraper day, in order (phase 4).

python -m scraper.daily [--date D] [--fake] [--skip-run] [--baseline | --preview] [--max-agent-jobs N] [--cost-alarm USD]

  1. run        every active shop's reader                      (scraper.run)
  2. discover   lead feeds -> links by shop, new shops           (scraper.discover; new shops are read at once)
                + misses: leads our readers did not find        (scraper.missed; their candidates join the raw file)
  3. check      Jev check on run deals + candidates              (scraper.check)
  4. escalate   browsing agent for what Jev could not settle     (scraper.escalate, every job)
  5. publish    the site's deals file, as a PREVIEW              (scraper.publish; never docs/data/deals.json)
  6. report     data/deals/daily-report-<date>.md, plain English

A stage that fails is written down in the report and the day goes on with the next one.
--fake   FakeJev and FakeAgent: every output gets a -FAKE name (report included); new shops are not saved.
--skip-run  reuse today's raw file instead of reading the shops again.
--baseline  first day only: every deal on sale is saved as already seen (no Jev, no agent, nothing
            published). From the next run only new or changed deals are checked.
--preview   test run: read the shops and list what a real run would pay for (new-deals-<date>.json);
            no Jev, no agent, nothing published, memory unchanged.

Rule: finding deals is never capped on purpose. The agent runs every job; the cost alarm only
warns in the report. Safety limits that stop a runaway loop are reported when hit.
"""
import argparse
import datetime
import json
import time
import types

from scraper import check, discover, escalate, missed, publish
from scraper import run as run_mod
from scraper.common import ROOT

REPORTS = ROOT / "data" / "deals"
COST_ALARM_USD = 5.0     # the report warns when a day costs more than this; nothing is stopped
STAGE_ORDER = ["run", "discover", "missed", "check", "escalate", "publish"]
STAGE_LABEL = {"run": "Read the shops", "discover": "Find leads and new shops", "missed": "Look for misses",
               "check": "Jev check", "escalate": "Browsing agent", "publish": "Build the site file"}
REASON_LABEL = {
    "shop_blocked": "the shop blocks robots (cannot be checked automatically)",
    "not_a_product_page": "the link is a home, blog or collection page",
    "shop_not_read_today": "the shop was not read today",
    "reader_gap": "the shop was read but our reader missed it",
    "not_on_sale_anymore": "the page shows no discount",
    "page_unreadable": "the page could not be opened or has no price",
    "fetch_cap": "over today's page limit",
    "not_checked": "pages were not opened",
}


# ---------------------------------------------------------------- the stages

def _rc(rc, what):
    return {"status": "ok"} if rc in (0, None) else {"status": "error", "note": f"{what} stopped with code {rc}"}


def stage_run(ctx):
    if ctx.skip_run:
        return {"status": "skipped", "note": "--skip-run: today's raw file is reused"}
    return _rc(run_mod.main(["--date", ctx.date]), "the shop run")


def stage_discover(ctx):
    doc = discover.run(ctx.date, save_new_shops=not ctx.fake)
    note = (f"{doc['counts']['leads']} leads, {doc['counts']['new_shops_added']} new shops"
            + ("" if not ctx.fake else " (fake run: new shops not saved)"))
    added = [s["id"] for s in doc.get("_added_entries", [])]
    if added and not ctx.skip_run:        # a shop found today is read today
        run_mod.main(["--date", ctx.date] + [x for i in added for x in ("--shop", i)])
        note += f"; read {len(added)} new shop(s) at once"
    bad = [f["id"] for f in doc["feeds"] if f["status"] not in ("ok", "disabled")]
    if bad:
        note += f"; feeds that could not be read: {', '.join(bad)}"
    return {"status": "ok", "note": note}


def stage_missed(ctx):
    doc = missed.run(ctx.date)
    c = doc["counts"]
    return {"status": "ok", "note": f"{c['misses']} misses, {c['candidates']} became candidate deals"}


def stage_check(ctx):
    if getattr(ctx, "baseline", False):
        return _rc(check.main(["--date", ctx.date, "--baseline"]), "the baseline")
    if getattr(ctx, "preview", False):
        return _rc(check.main(["--date", ctx.date, "--list-new"]), "the new-deals list")
    return _rc(check.main(["--date", ctx.date] + (["--fake"] if ctx.fake else [])), "the Jev check")


def stage_escalate(ctx):
    if getattr(ctx, "baseline", False):
        return {"status": "skipped", "note": "--baseline: no agent on the first day"}
    if getattr(ctx, "preview", False):
        return {"status": "skipped", "note": "--preview: test run, nothing paid"}
    args = ["--date", ctx.date] + (["--max-jobs", str(ctx.max_agent_jobs)] if ctx.max_agent_jobs is not None else []) \
        + (["--fake"] if ctx.fake else [])
    return _rc(escalate.main(args), "the browsing agent")


def stage_publish(ctx):
    if getattr(ctx, "preview", False):
        return {"status": "skipped", "note": "--preview: test run, nothing published"}
    publish.LAST_STATS.clear()
    res = _rc(publish.main(["--date", ctx.date] + (["--fake"] if ctx.fake else [])), "publish")
    st = publish.LAST_STATS
    if st:
        res["note"] = (f"{st['published']} deals; pages opened {st['fetched']}, from cache {st['cached']}"
                       + (f", {st['skipped_for_time']} left for the next run" if st["skipped_for_time"] else ""))
    return res


DEFAULT_STAGES = {"run": stage_run, "discover": stage_discover, "missed": stage_missed, "check": stage_check,
                  "escalate": stage_escalate, "publish": stage_publish}


# ---------------------------------------------------------------- the report

def _read(path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {} if default is None else default


def _money(x):
    return f"${x:.2f}" if x is not None else "unknown"


def _price(d):
    cur = d.get("currency") or ""
    was = f", was {d['price_was']}" if d.get("price_was") else ""
    pct = f", {d['discount_pct']}% off" if d.get("discount_pct") else ""
    return f"{d['price_now']} {cur}{was}{pct}".replace("  ", " ").strip()


def build_report(ctx, results, folder=REPORTS):
    """-> the daily report as Markdown text. Reads the day's output files from `folder`."""
    date, sfx = ctx.date, "-FAKE" if ctx.fake else ""
    scrape = _read(folder / f"scrape-report-{date}.json")
    leads = _read(folder / f"leads-{date}.json")
    miss = _read(folder / f"missed-{date}.json")
    chk = _read(folder / f"check-report-{date}{sfx}.json")
    esc = _read(folder / f"escalation-{date}{sfx}.json")
    owner = _read(folder / f"needs-owner-{date}{sfx}.json", [])
    site = _read(folder / f"site-preview-{date}{sfx}.json")
    st, cc = scrape.get("totals", {}), chk.get("counts", {})
    is_baseline = chk.get("mode") == "baseline"
    deals = site.get("deals", [])
    by_type = {}
    for d in deals:
        by_type[d["type"]] = by_type.get(d["type"], 0) + 1
    types_txt = ", ".join(f"{n} {t}" for t, n in sorted(by_type.items(), key=lambda kv: -kv[1])) or "none"
    jobs = esc.get("jobs", [])
    runs = [j["agent_run"] for j in jobs if j.get("agent_run")]
    agent_cost = sum(r.get("cost_usd") or 0 for r in runs)
    jev = chk.get("jev", {})
    day_cost = (jev.get("estimated_cost_usd") or 0) + agent_cost
    alarm_usd = getattr(ctx, "cost_alarm", COST_ALARM_USD)
    stopped = [r for r in scrape.get("shops", []) if r.get("stopped_early")]
    L = []

    L.append(f"# RPG Hunt daily report, {date}")
    if getattr(ctx, "preview", False):
        new = _read(folder / f"new-deals-{date}.json", [])
        by_shop, by_why = {}, {}
        for r in new:
            by_shop[r["shop"]] = by_shop.get(r["shop"], 0) + 1
            by_why[r["why"]] = by_why.get(r["why"], 0) + 1
        L += ["", f"**TEST RUN (--preview): nothing was paid or published.** {len(new)} deal(s) are new or changed "
                  f"since the last check and would be checked by a real run "
                  f"({', '.join(f'{n} {w}' for w, n in by_why.items()) or 'none'}).", ""]
        L += [f"- {s}: {n}" for s, n in sorted(by_shop.items(), key=lambda kv: -kv[1])]
        L += ["", "Full list: `data/deals/new-deals-" + date + ".json`. First 30:", ""]
        for r in new[:30]:
            was = f" (was {r['before']['price_now']})" if r.get("before") else ""
            L.append(f"- [{r['title']}]({r['url']}) at {r['shop']}: {r['price_now']} {r.get('currency') or ''}{was}, {r['why']}")
        return "\n".join(L) + "\n"
    if is_baseline:
        L += ["", f"**Baseline day: {cc.get('baseline', 0)} deals on sale today were saved as already seen, with no paid "
                  f"checks and nothing published. From the next run, only new or changed deals are checked.**"]
    if ctx.fake:
        L += ["", "**This is a TEST run with fake checkers (a keyword stand-in for Jev, a stand-in for the agent). "
                  "The numbers show that the pipes work, not how good the answers are. Do not publish anything from it.**"]
    failed = [n for n in STAGE_ORDER if results.get(n, {}).get("status") == "error"]
    L += ["", "## The short version", "",
          f"- {len(deals)} deals would go on the site ({types_txt}).",
          f"- {cc.get('needs_agent', 0)} deals were left for the browsing agent; it handled "
          f"{len([j for j in jobs if j['job'] == 'recheck'])} of them today.",
          f"- {len(owner)} item(s) need your check.",
          f"- {len(scrape.get('shops', []))} shops read; {len(miss.get('misses', []))} sale links in the lead posts "
          f"were not found by our readers.",
          ("- Everything ran." if not failed else "- These steps failed: " + ", ".join(STAGE_LABEL[n] for n in failed) + ".")]
    if stopped:
        L.append(f"- **{len(stopped)} shop(s) hit a safety limit and may be missing deals** (see below).")
    if not ctx.fake and day_cost > alarm_usd:
        L.append(f"- **Cost alarm: today cost about {_money(day_cost)}, over the {_money(alarm_usd)} alarm.** "
                 f"Nothing was stopped; check the Cost section.")

    L += ["", "## Numbers by step", ""]
    L.append(f"1. **Shops:** {st.get('shops', 0)} shops, {st.get('ok', 0)} read fine, {st.get('blocked', 0)} blocked us, "
             f"{st.get('error', 0)} had errors. They gave {st.get('deals_unique', 0)} possible deals.")
    lc = leads.get("counts", {})
    feeds = leads.get("feeds", [])
    L.append(f"2. **Leads:** {lc.get('leads', 0)} shop links from {len([f for f in feeds if f['status'] == 'ok'])} of "
             f"{len(feeds)} feeds ({lc.get('known_shop', 0)} on shops we read, {lc.get('blocked_shop', 0)} on shops that block robots, "
             f"{lc.get('new_shop', 0)} on unknown sites).")
    mc = miss.get("counts", {})
    L.append(f"3. **Misses:** {mc.get('misses', 0)} leads were not in today's run; {mc.get('candidates', 0)} turned into candidate deals.")
    L.append(f"4. **Jev check:** {cc.get('deals_in', 0)} deals in, {cc.get('reused_from_memory', 0)} unchanged since an earlier run "
             f"(verdict reused, no cost), {cc.get('dropped_by_code', 0)} dropped by plain rules "
             f"(not a discount, ended), {cc.get('rpg_dropped_stage_a', 0)} dropped as not RPG, {cc.get('published', 0)} passed, "
             f"{cc.get('needs_agent', 0)} sent to the agent, {cc.get('wait', 0)} waiting for price history.")
    ec = esc.get("counts", {})
    L.append(f"5. **Browsing agent:** {ec.get('jobs_found', 0)} jobs found, {ec.get('run_now', 0)} run now, "
             f"{ec.get('reused_from_memory', 0)} answered from memory (same link and price, no cost), "
             f"{ec.get('published_by_agent', 0)} deals it published.")
    L.append(f"6. **Site file:** {len(deals)} deals "
             f"({sum(1 for d in deals if d.get('image'))} with a picture, {sum(1 for d in deals if d.get('game_id'))} linked to the game list).")

    L += ["", "## Published by type", ""]
    L.append(", ".join(f"{t}: {n}" for t, n in sorted(by_type.items(), key=lambda kv: -kv[1])) or "Nothing published.")

    L += ["", "## Top 10 deals", ""]
    if deals:
        for i, d in enumerate(deals[:10], 1):
            L.append(f"{i}. [{d['title']}]({d['url']}) at {d['shop']}: {_price(d)}")
    else:
        L.append("None.")

    L += ["", "## New shops", ""]
    new = leads.get("new_shops", [])
    if new:
        for s in new:
            L.append(f"- **{s['name']}** ({s['platform']}, {s['status']}){', needs a recipe' if s.get('needs_recipe') else ''}: {s['store_url']}")
    else:
        L.append("None today.")

    L += ["", "## Shops that look broken", ""]
    alarms = [r for r in scrape.get("shops", []) if r.get("break_alarm") == date]
    if alarms:
        for r in alarms:
            L.append(f"- **{r['id']}**: {r['deals']} deals today, usually about {r.get('alarm_average')}. Its reader may have stopped working.")
    else:
        L.append("None.")

    L += ["", "## Safety limits hit", ""]
    if stopped:
        for r in stopped:
            L.append(f"- **{r['id']}**: {r['stopped_early']}.")
    else:
        L.append("None. Every shop was read to the end.")

    L += ["", "## Misses", ""]
    ms = miss.get("misses", [])
    if ms:
        reasons = miss.get("counts", {}).get("by_reason", {})
        L.append("Why we missed them: " + "; ".join(f"{n} x {REASON_LABEL.get(r, r)}" for r, n in sorted(reasons.items(), key=lambda kv: -kv[1])) + ".")
        L.append("")
        order = {"reader_gap": 0, "shop_not_read_today": 1, "not_on_sale_anymore": 2, "page_unreadable": 3,
                 "not_a_product_page": 4, "shop_blocked": 5}
        for m in sorted(ms, key=lambda m: order.get(m["reason"], 9))[:5]:
            L.append(f"- {m.get('title') or m['url']} at {m['shop']}: {REASON_LABEL.get(m['reason'], m['reason'])}"
                     + (" (now a candidate deal)" if m.get("candidate") else "") + f". {m['url']}")
    else:
        L.append("None.")

    L += ["", "## Needs your check", ""]
    waiting = cc.get("needs_agent", 0) - len([j for j in jobs if j["job"] == "recheck"])
    if owner:
        for o in owner:
            L.append(f"- **{o['title']}** ({o['shop']}): {o['url']}")
            L.append(f"  Question: {o['question']}")
    else:
        L.append("Nothing.")
    if waiting > 0 and ctx.max_agent_jobs is not None:
        L.append(f"\n{waiting} more deal(s) are waiting for the browsing agent (job limit was {ctx.max_agent_jobs}, set by hand).")

    L += ["", "## Time per step", ""]
    total = 0.0
    for n in STAGE_ORDER:
        r = results.get(n)
        if not r:
            continue
        total += r["seconds"]
        L.append(f"- {STAGE_LABEL[n]}: {r['seconds']} s ({r['status']}){': ' + r['note'] if r.get('note') else ''}")
    L.append(f"- **Total: {round(total, 1)} s ({round(total / 60, 1)} min)**")

    L += ["", "## Cost", ""]
    if jev:
        L.append(f"- Jev{' (FAKE, no real money)' if ctx.fake else ''}: {jev.get('requests', 0)} requests, "
                 f"{jev.get('input_tokens', 0)} tokens in, {jev.get('output_tokens', 0)} tokens out, "
                 f"{jev.get('cache_hits', 0)} answers reused from cache, about {_money(jev.get('estimated_cost_usd'))}.")
    else:
        L.append("- Jev: not run.")
    L.append(f"- Browsing agent{' (FAKE)' if ctx.fake else ''}: {len(runs)} job(s), {_money(agent_cost) if runs else '$0.00'}.")
    L.append(f"- **Day total: about {_money(day_cost)}** (alarm at {_money(alarm_usd)}).")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- the day

def run_day(ctx, stages=None, folder=REPORTS, clock=time.monotonic):
    """Run the stages in order, write the report. -> (results, report_path)."""
    stages = {**DEFAULT_STAGES, **(stages or {})}
    results = {}
    for name in STAGE_ORDER:
        print(f"\n== {STAGE_LABEL[name]} ==")
        start = clock()
        try:
            res = dict(stages[name](ctx) or {})
        except (Exception, SystemExit) as e:          # one broken step must not stop the day
            res = {"status": "error", "note": f"{type(e).__name__}: {e}"[:300]}
        res.setdefault("status", "ok")
        res["seconds"] = round(clock() - start, 1)
        results[name] = res
        print(f"-- {name}: {res['status']} in {res['seconds']} s" + (f" ({res['note']})" if res.get("note") else ""))
    text = build_report(ctx, results, folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"daily-report-{ctx.date}{'-FAKE' if ctx.fake else ''}.md"
    path.write_text(text)
    return results, path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m scraper.daily")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--fake", action="store_true", help="fake Jev and fake agent; every output gets a -FAKE name")
    ap.add_argument("--skip-run", action="store_true", help="reuse today's raw file instead of reading the shops")
    ap.add_argument("--baseline", action="store_true",
                    help="first day only: save every deal as already seen; no Jev, no agent, nothing published")
    ap.add_argument("--preview", action="store_true",
                    help="test run: read the shops and list the new deals; no Jev, no agent, nothing published")
    ap.add_argument("--max-agent-jobs", type=int, default=None,
                    help="for tests by hand only: most browsing-agent jobs (default: every job; 0 = none)")
    ap.add_argument("--cost-alarm", type=float, default=COST_ALARM_USD,
                    help=f"warn in the report when the day costs more than this many dollars (default {COST_ALARM_USD}); nothing is stopped")
    args = ap.parse_args(argv)
    ctx = types.SimpleNamespace(date=args.date, fake=args.fake, skip_run=args.skip_run, baseline=args.baseline,
                                preview=args.preview,
                                max_agent_jobs=args.max_agent_jobs, cost_alarm=args.cost_alarm)
    results, path = run_day(ctx)
    total = round(sum(r["seconds"] for r in results.values()), 1)
    print(f"\nreport: {path.relative_to(ROOT)} (total {total} s)")
    return 0 if all(r["status"] != "error" for r in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
