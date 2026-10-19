"""Escalation (phase 3): hand what code could not settle to the browsing agent, then check its answers.

python -m scraper.escalate [--date D] [--max-jobs N] [--fake] [--retry]

Reads    data/deals/check-report-<date>.json     needs_agent -> `recheck` jobs
         data/deals/scrape-report-<date>.json    generic shops with no sale page / 0 deals, and shops with a
                                                 break_alarm -> `recipe` jobs
         data/deals/raw/<date>-scraper.json      the full deal records
Writes   data/deals/escalation-<date>.json       every job: agent answer summary, validation, outcome
         data/deals/raw/<date>-checked.json      accepted rechecks appended as published (check.agent block)
         data/deals/needs-owner-<date>.json      everything still unsettled, one line question each
         data/shops/shops.json                   accepted recipes (via scraper.agent.save_recipe)
         data/shops/recipe-attempts.json         last recipe attempt per shop (no new try for 7 days)
         data/deals/agent-memory.json            the agent's recheck verdicts by link and price (local, gitignored)
Agent memory: a deal the agent already judged at the same link and the same prices in the last
MEMORY_DAYS days gets that verdict again without a new agent job (no cost). A price change, an older
verdict or an agent failure means a fresh job.
--fake: FakeAgent (answers `unsure`), reads the -FAKE check report, every output gets a -FAKE suffix, and
shops.json / recipe-attempts.json are left alone.
Re-running a date skips jobs that already ended in a final outcome (so it costs nothing twice); --retry
also re-tries recipe jobs inside the 7-day window.
"""
import argparse
import datetime
import json

from scraper import agent as agent_mod
from scraper.common import RAW, ROOT, FetchError, fetch, load_shops, norm_url
from scraper.trim import trim

REPORTS = ROOT / "data" / "deals"
ATTEMPTS = ROOT / "data" / "shops" / "recipe-attempts.json"
RETRY_DAYS = 7
MEMORY_DAYS = 7          # an agent verdict is reused this long while the link and prices stay the same
MEMORY_OUTCOMES = {"publish", "drop", "needs_owner"}
FINAL = {"publish", "drop", "needs_owner", "accepted", "rejected"}   # not final: "error" (agent failed to run)
DEAL_FIELDS = ("title", "shop", "url", "price_now", "price_was", "currency", "ends", "type", "found_via", "source")


def _read(path, default):
    try:
        return json.loads(path.read_text()) if path.exists() else default
    except ValueError:
        return default


# ---------------------------------------------------------------- building jobs

def recipe_candidates(shops, scrape_report, attempts, date, retry=False):
    """-> list of (shop, why). Active generic shops with no sale page / 0 deals, and any shop with a break alarm."""
    by_id = {s["id"]: s for s in shops}
    out = []

    def recent_attempt(shop):
        last = attempts.get(shop["id"])
        return bool(last and not retry and
                    (datetime.date.fromisoformat(date) - datetime.date.fromisoformat(last["date"])).days < RETRY_DAYS)

    ran = set()
    for row in scrape_report.get("shops", []):
        ran.add(row["id"])
        shop = by_id.get(row["id"])
        if not shop or shop.get("status") != "active":
            continue
        alarm = row.get("break_alarm") == date
        generic_empty = (shop["platform"] == "generic" and row["deals"] == 0
                         and row["status"] in ("ok", "error") and row.get("errors") != ["no reader"])
        if not (alarm or generic_empty):
            continue
        if recent_attempt(shop):
            continue
        why = "break alarm" if alarm else "no sale page" if row.get("no_sale_page") else "reader returned 0 deals"
        out.append((shop, why))
    # shops found through a lead (scraper.discover) that today's run has not read yet
    for shop in shops:
        if (shop.get("needs_recipe") and shop.get("status") == "active" and shop["platform"] == "generic"
                and shop["id"] not in ran and not recent_attempt(shop)):
            out.append((shop, "new shop"))
    out.sort(key=lambda x: x[1] != "break alarm")      # alarms first
    return out


def page_for_job(url, load=agent_mod.load_page_html):
    """-> ({"text", "price_candidates"}, None) or (None, error kind)."""
    try:
        t = trim(load(url), url)
        return {"text": t["text"], "price_candidates": t["price_candidates"]}, None
    except (FetchError, OSError) as e:
        return None, getattr(e, "kind", type(e).__name__)


def deal_summary(d):
    return {k: d.get(k) for k in DEAL_FIELDS}


def owner_deal_item(deal, jev_reasons, jev_check, res, outcome):
    """One line for the owner's 'Needs your check' list."""
    ag = res.get("agent") or {}
    return {
        "kind": "deal", "key": deal["url"], "url": deal["url"], "title": deal["title"], "shop": deal["shop"],
        "price_now": deal["price_now"], "price_was": deal["price_was"], "currency": deal.get("currency"),
        "jev": {"reasons": jev_reasons,
                "support": (jev_check or {}).get("support"), "offer_kind": (jev_check or {}).get("offer_kind")},
        "agent": {"verdict": ag.get("verdict"), "price_now_seen": ag.get("price_now_seen"), "reason": ag.get("reason"),
                  "failed_checks": res.get("reasons")},
        "question": f"Does this page show {deal['title']} at {deal['price_now']} {deal.get('currency') or ''} "
                    f"on sale today? Open the link and tell me yes or no.".replace("  ", " "),
        "outcome": outcome,
    }


def owner_shop_item(shop, why, detail):
    return {
        "kind": "shop", "key": f"recipe:{shop['id']}", "url": shop["store_url"], "title": shop["name"], "shop": shop["name"],
        "price_now": None, "price_was": None, "currency": shop.get("currency"),
        "jev": None, "agent": detail,
        "question": f"The scraper cannot read {shop['name']}'s sales ({why}). Open {shop['store_url']} and tell me "
                    f"where its sale page is, or say 'pause it' if it has none.",
    }


# ---------------------------------------------------------------- agent memory

def memory_key(deal):
    return norm_url(deal["url"])


def _same_prices(deal, m):
    return (deal.get("price_now"), deal.get("price_was"), deal.get("currency")) == \
           (m.get("price_now"), m.get("price_was"), m.get("currency"))


def _age_days(date, then):
    return (datetime.date.fromisoformat(date) - datetime.date.fromisoformat(then)).days


def recall(memory, deal, date):
    """-> the remembered verdict for this deal at these prices, or None (new, changed, too old)."""
    m = memory.get(memory_key(deal)) if deal else None
    if not m or m.get("outcome") not in MEMORY_OUTCOMES or not _same_prices(deal, m):
        return None
    return m if 0 <= _age_days(date, m["date"]) < MEMORY_DAYS else None


def remember(memory, deal, date, res):
    memory[memory_key(deal)] = {"date": date, "price_now": deal.get("price_now"), "price_was": deal.get("price_was"),
                                "currency": deal.get("currency"), "outcome": res["outcome"],
                                "reasons": res.get("reasons") or [], "agent": res.get("agent") or {}}


def prune(memory, date):
    return {k: m for k, m in memory.items() if _age_days(date, m["date"]) < MEMORY_DAYS}


# ---------------------------------------------------------------- the run

def run(date, ag, fake=False, max_jobs=None, retry=False, load=agent_mod.load_page_html,
        validate_recipe=agent_mod.validate_recipe, shops=None, write=True):
    suffix = "-FAKE" if fake else ""
    check_rep = _read(REPORTS / f"check-report-{date}{suffix}.json", {})
    scrape_rep = _read(REPORTS / f"scrape-report-{date}.json", {})
    raw = {norm_url(d["url"]): d for d in _read(RAW / f"{date}-scraper.json", [])}
    esc_path = REPORTS / f"escalation-{date}{suffix}.json"
    owner_path = REPORTS / f"needs-owner-{date}{suffix}.json"
    memory_path = REPORTS / f"agent-memory{suffix}.json"
    memory = _read(memory_path, {})
    checked_path = RAW / f"{date}-checked{suffix}.json"
    esc = _read(esc_path, {"date": date, "fake": fake, "jobs": []})
    owner = {i["key"]: i for i in _read(owner_path, [])}
    done = {j["key"] for j in esc["jobs"] if j["outcome"] in FINAL}
    jev_by_url = {norm_url(d["url"]): d for d in check_rep.get("deals", [])}
    shops = shops if shops is not None else load_shops()
    attempts = _read(ATTEMPTS, {})

    jobs = [("recipe", s, why) for s, why in recipe_candidates(shops, scrape_rep, attempts, date, retry)]
    jobs += [("recheck", n, None) for n in check_rep.get("needs_agent", [])]
    todo = [j for j in jobs if (f"recipe:{j[1]['id']}" if j[0] == "recipe" else j[1]["url"]) not in done]
    skipped_done = len(jobs) - len(todo)
    reuse = [(j, recall(memory, raw.get(norm_url(j[1]["url"])), date)) for j in todo if j[0] == "recheck"]
    reuse = [(j, m) for j, m in reuse if m]
    reused_keys = {j[1]["url"] for j, _ in reuse}
    todo = [j for j in todo if not (j[0] == "recheck" and j[1]["url"] in reused_keys)]
    if max_jobs is not None:
        todo = todo[:max_jobs]

    new_checked, counts = [], {"recheck": {}, "recipe": {}}

    def put(row):
        esc["jobs"] = [j for j in esc["jobs"] if j["key"] != row["key"]] + [row]

    def settle(rec, row, res, jev_check, jev_reasons, extra=None):
        """Apply a recheck outcome (fresh or remembered) to the checked file and the owner list."""
        if res["outcome"] == "publish":
            new_checked.append(dict(rec, check={**jev_check, "decision": "publish", "via": "agent",
                                                "checked_on": date, "model": agent_mod.MODEL, "fake_agent": fake,
                                                "jev_reasons": jev_reasons, "agent": res["agent"], **(extra or {})}))
            owner.pop(row["key"], None)
        elif res["outcome"] == "needs_owner":
            owner[row["key"]] = owner_deal_item(rec, jev_reasons, jev_check, res, "needs_owner")
        else:
            owner.pop(row["key"], None)

    for (_, item, _), m in reuse:                 # remembered verdicts: no agent job, no cost
        rec = raw[norm_url(item["url"])]
        jev_entry = jev_by_url.get(norm_url(item["url"])) or {}
        res = {"outcome": m["outcome"], "reasons": m["reasons"], "agent": m["agent"]}
        row = {"job": "recheck", "key": item["url"], "title": item["title"], "shop": item["shop"],
               "outcome": m["outcome"], "reasons": m["reasons"], "agent": m["agent"], "agent_run": None,
               "reused_from": m["date"]}
        settle(rec, row, res, jev_entry.get("check") or {}, item.get("reasons") or [], {"reused_from": m["date"]})
        put(row)
        counts["recheck"]["reused"] = counts["recheck"].get("reused", 0) + 1

    for kind, item, why in todo:
        if kind == "recheck":
            rec = raw.get(norm_url(item["url"]))
            row = {"job": "recheck", "key": item["url"], "title": item["title"], "shop": item["shop"], "outcome": None}
            if rec is None:
                row.update(outcome="error", reasons=["deal not found in the raw scraper file"])
                put(row)
                continue
            jev_entry = jev_by_url.get(norm_url(item["url"])) or {}
            jev_check, jev_reasons = jev_entry.get("check") or {}, item.get("reasons") or []
            page, err = page_for_job(rec["url"], load)
            if page is None:       # no page for the agent either: do not spend a call
                res = {"outcome": "needs_owner", "reasons": [f"page_unreadable: {err}"], "agent": {}}
                row.update(outcome="needs_owner", reasons=res["reasons"], agent_run=None)
            else:
                job = {"job": "recheck", "deal": deal_summary(rec), "jev": {"reasons": jev_reasons, "answers": jev_check},
                       "page": page}
                r = ag.run(job, date)
                if r.answer is None:
                    row.update(outcome="error", reasons=[f"agent_failed: {r.error}"], agent_run=r.meta())
                    put(row)
                    continue
                res = agent_mod.validate_recheck(rec, r.answer, jev_check, date, load)
                row.update(outcome=res["outcome"], reasons=res["reasons"], agent=res["agent"], agent_run=r.meta())
                remember(memory, rec, date, res)      # only verdicts the agent was paid for
            settle(rec, row, res, jev_check, jev_reasons)
            put(row)
            counts["recheck"][row["outcome"]] = counts["recheck"].get(row["outcome"], 0) + 1
        else:
            shop = item
            key = f"recipe:{shop['id']}"
            row = {"job": "recipe", "key": key, "shop": shop["name"], "why": why, "outcome": None}
            r = ag.run(agent_mod.recipe_job(shop, why), date)
            row["agent_run"] = r.meta()
            if r.answer is None:
                row.update(outcome="error", reasons=[f"agent_failed: {r.error}"])
                put(row)
                continue
            v = validate_recipe(shop, r.answer)
            row.update(agent_result=r.answer.get("result"), agent_notes=r.answer.get("notes"),
                       proposed_recipe=r.answer.get("recipe"), validation=v, reasons=v["reasons"],
                       outcome="accepted" if v["accepted"] else "rejected")
            if v["accepted"]:
                owner.pop(key, None)
                if write and not fake:
                    agent_mod.save_recipe(shop["id"], v["recipe"], date)
            else:
                owner[key] = owner_shop_item(shop, why, {"result": r.answer.get("result"),
                                                         "notes": r.answer.get("notes"), "failed_checks": v["reasons"]})
            if write and not fake:
                attempts[shop["id"]] = {"date": date, "outcome": row["outcome"]}
            put(row)
            counts["recipe"][row["outcome"]] = counts["recipe"].get(row["outcome"], 0) + 1

    if write:
        esc["counts"] = {"jobs_found": len(jobs), "already_done": skipped_done, "run_now": len(todo),
                         "reused_from_memory": len(reuse),
                         "published_by_agent": sum(1 for j in esc["jobs"] if j["job"] == "recheck" and j["outcome"] == "publish"),
                         "needs_owner": len(owner)}
        esc_path.write_text(json.dumps(esc, ensure_ascii=False, indent=1) + "\n")
        owner_path.write_text(json.dumps(list(owner.values()), ensure_ascii=False, indent=1) + "\n")
        memory_path.write_text(json.dumps(prune(memory, date), ensure_ascii=False, indent=1, sort_keys=True) + "\n")
        if not fake:
            ATTEMPTS.write_text(json.dumps(attempts, indent=1, sort_keys=True) + "\n")
        if new_checked:
            have = _read(checked_path, [])
            seen = {norm_url(d["url"]) for d in have}
            have += [d for d in new_checked if norm_url(d["url"]) not in seen]
            checked_path.write_text(json.dumps(have, ensure_ascii=False, indent=1) + "\n")
    return esc, owner, new_checked, counts


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m scraper.escalate")
    ap.add_argument("--date", default=datetime.date.today().isoformat())
    ap.add_argument("--max-jobs", type=int, default=None)
    ap.add_argument("--fake", action="store_true", help="FakeAgent; -FAKE input and output files; shops.json untouched")
    ap.add_argument("--retry", action="store_true", help="also retry recipe jobs tried in the last 7 days")
    args = ap.parse_args(argv)
    ag = agent_mod.FakeAgent() if args.fake else agent_mod.ClaudeAgent()
    esc, owner, new_checked, counts = run(args.date, ag, args.fake, args.max_jobs, args.retry)
    c = esc["counts"]
    print(f"jobs found {c['jobs_found']}, already done {c['already_done']}, "
          f"reused from memory {c['reused_from_memory']}, run now {c['run_now']}")
    print(f"recheck: {counts['recheck'] or 'none'}; recipe: {counts['recipe'] or 'none'}")
    print(f"published by agent {len(new_checked)}; needs owner {c['needs_owner']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
