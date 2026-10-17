"""Thin wrapper around the TypeSafe SDK (Jev), plus a test double.

ask(state, questions) -> answers
  state      the content Jev reads (a dict, as in agents/jev-check-spec.md)
  questions  {id: {"type": "noul"|"choice", "instructions": ..., "criteria": ...}}
  answers    {id: {"type": "noul", "noul": p}
              | {"type": "choice", "choice": option, "probabilities": {...}, "confidence": c}}

Every call is cached on disk by a hash of (state, questions, model), so re-runs and threshold
tuning cost nothing. Retries (429, 529, timeouts) follow the SDK's own RetryPolicy. Token usage
is added up in `.usage` for the report.

The API key comes only from the environment (TYPESAFE_API_KEY). If it is not set, a tiny loader
reads that one line from the project's .env file at runtime, only when a real call is about to
be made. The key is never printed, logged or written anywhere.
"""
import hashlib
import json
import os
import re
import threading

from scraper.common import ROOT

CACHE = ROOT / "data" / "jev-cache"
MODEL = "jev-latest"
ENV_FILE = ROOT / ".env"
KEY_NAME = "TYPESAFE_API_KEY"


class JevError(Exception):
    """A Jev call that failed after the SDK's retries. The message never contains the key."""


def load_env_key():
    """Make TYPESAFE_API_KEY available in os.environ. Returns True when it is set afterwards.
    Reads only that one line of .env, only when the variable is missing."""
    if os.environ.get(KEY_NAME, "").strip():
        return True
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith(KEY_NAME + "="):
                value = line.split("=", 1)[1].strip().strip("'\"")
                if value:
                    os.environ[KEY_NAME] = value
                    return True
    except OSError:
        pass
    return False


def cache_key(state, questions, model):
    blob = json.dumps({"state": state, "questions": questions, "model": model},
                      sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def request_chars(state, questions, model=MODEL):
    """Size of the request body in characters (the dry-run token estimate is this / 4)."""
    return len(json.dumps({"state": state, "model": model, "questions": questions}, ensure_ascii=False))


class _Tally:
    """Request and token counters shared by Jev and FakeJev."""
    def __init__(self):
        self._lock = threading.Lock()
        self.usage = {"requests": 0, "cache_hits": 0, "input_tokens": 0, "output_tokens": 0, "errors": 0}

    def _add(self, **kw):
        with self._lock:
            for k, v in kw.items():
                self.usage[k] += v


class Jev(_Tally):
    def __init__(self, model=MODEL, cache_dir=CACHE, client=None):
        super().__init__()
        self.model = model
        self.cache_dir = cache_dir
        self._client = client
        self._client_lock = threading.Lock()

    # -- cache
    def _path(self, key):
        return self.cache_dir / key[:2] / f"{key}.json"

    def _cache_get(self, key):
        try:
            return json.loads(self._path(key).read_text())["answers"]
        except (OSError, ValueError, KeyError):
            return None

    def _cache_put(self, key, answers, usage):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps({"model": self.model, "answers": answers, "usage": usage}))
        os.replace(tmp, p)

    # -- client
    def _get_client(self):
        with self._client_lock:
            if self._client is None:
                from typesafe_sdk import RetryPolicy, TypeSafeClient
                load_env_key()
                try:
                    # Python's standard certificate check: the SDK's default (macOS native
                    # trust) fails inside sandboxed shells; this one works everywhere.
                    import ssl
                    import httpx2
                    http = httpx2.Client(verify=ssl.create_default_context(), timeout=60.0)
                    self._client = TypeSafeClient(
                        model=self.model, http_client=http,
                        retry=RetryPolicy(max_retries=4, backoff_initial=1.0, backoff_max=20.0, timeout=60.0))
                except Exception as e:
                    raise JevError(f"cannot start the client: {type(e).__name__}") from None
            return self._client

    @staticmethod
    def _sdk_questions(questions):
        from typesafe_sdk import Choice, Noul
        out = {}
        for qid, q in questions.items():
            if q["type"] == "noul":
                out[qid] = Noul(instructions=q["instructions"], criteria=q.get("criteria"))
            elif q["type"] == "choice":
                out[qid] = Choice(instructions=q["instructions"], criteria=q["criteria"])
            else:
                raise ValueError(f"unsupported question type {q['type']!r}")
        return out

    @staticmethod
    def _plain_answers(response):
        out = {}
        for qid, a in response.answers.items():
            if a.type == "noul":
                out[qid] = {"type": "noul", "noul": float(a.noul)}
            elif a.type == "choice":
                out[qid] = {"type": "choice", "choice": a.choice,
                            "probabilities": {k: float(v) for k, v in a.probabilities.items()},
                            "confidence": float(a.confidence)}
            else:
                out[qid] = {"type": a.type}
        return out

    def ask(self, state, questions):
        key = cache_key(state, questions, self.model)
        hit = self._cache_get(key)
        if hit is not None:
            self._add(cache_hits=1)
            return hit
        from typesafe_sdk import TypeSafeError
        client = self._get_client()
        try:
            resp = client.system_one(state, self._sdk_questions(questions), model=self.model)
        except TypeSafeError as e:   # includes API errors after the SDK's retries
            self._add(errors=1)
            raise JevError(f"{type(e).__name__} status={getattr(e, 'status', None)}") from None
        answers = self._plain_answers(resp)
        usage = {"input_tokens": resp.usage.input_tokens or 0, "output_tokens": resp.usage.output_tokens or 0}
        self._add(requests=1, **usage)
        self._cache_put(key, answers, usage)
        return answers


# ---------------------------------------------------------------- test double

class FakeJev(_Tally):
    """TEST DOUBLE. Answers from simple keyword rules, no AI, no network. Used by the tests and
    by `check.py --fake` to prove the plumbing. Its answers say nothing about real Jev quality,
    so fake runs are written to *-FAKE.json files and must never be used for publishing.

    rules: optional dict that replaces entries of DEFAULT_RULES (keyword lists, lower case).
    forced: optional callable(qid, question, state) -> answer dict or None; wins over the rules
            (tests use it to script a particular answer).
    """
    DEFAULT_RULES = {
        "not_rpg": ["miniature", "miniatures", "dice tray", "dice", "board game", "card game", "wargame",
                    "gift card", "t-shirt", "tee", "hoodie", "enamel pin", "poster", "stl", "playmat",
                    "novel", "sleeves", "paint set", "terrain"],
        "rpg": ["rpg", "role-playing", "roleplaying", "rulebook", "core book", "adventure", "campaign",
                "supplement", "sourcebook", "bestiary", "zine", "quickstart", "starter set", "bundle",
                "module", "tabletop", "dungeon", "player's guide", "gamemaster"],
        "ended": ["has ended", "sale ended", "expired", "no longer available", "offer ended"],
        "clearance": ["clearance", "outlet", "warehouse", "last chance", "reduced price", "restock"],
        "promotion": ["sale", "% off", "off ", "deal", "bundle", "save ", "discount", "coupon", "promo"],
        "everyday": ["rrp", "msrp", "list price"],
    }

    def __init__(self, rules=None, forced=None):
        super().__init__()
        self.rules = {**self.DEFAULT_RULES, **(rules or {})}
        self.forced = forced

    @staticmethod
    def _choice(option, options, conf=0.9):
        rest = [o for o in options if o != option]
        share = round((1 - conf) / len(rest), 4) if rest else 0.0
        probs = {o: (conf if o == option else share) for o in options}
        return {"type": "choice", "choice": option, "probabilities": probs, "confidence": conf}

    def _has(self, text, group):
        # whole words / phrases only ("tee" must not match "teenage")
        return any(re.search(rf"(?<!\w){re.escape(k.strip())}(?!\w)", text) for k in self.rules[group])

    def ask(self, state, questions):
        answers = {}
        for qid, q in questions.items():
            a = self.forced(qid, q, state) if self.forced else None
            answers[qid] = a if a is not None else self._answer(qid, q, state)
        chars = request_chars(state, questions)
        self._add(requests=1, input_tokens=chars // 4, output_tokens=20 * len(questions))
        return answers

    def _answer(self, qid, q, state):
        if q["type"] == "noul":
            if qid.startswith("p") and qid[1:].isdigit():       # stage A: products[i]
                prod = state["products"][int(qid[1:])]
                text = _flat(prod).lower()
            else:                                               # stage B: claimed deal (+ page)
                claimed = state.get("claimed_deal", {})
                text = " ".join([str(claimed.get("title") or ""), _flat(state.get("shop_data", {})),
                                 (state.get("page") or {}).get("text", "")]).lower()
            if self._has(text, "not_rpg") and not self._has(text, "rpg"):
                return {"type": "noul", "noul": 0.05}
            if self._has(text, "rpg"):
                return {"type": "noul", "noul": 0.9}
            return {"type": "noul", "noul": 0.5}
        claimed = state.get("claimed_deal", {})
        page = state.get("page") or {}
        text = ((page.get("text") or "") + " " + (claimed.get("title") or "")).lower()
        if qid == "support":
            cands = page.get("price_candidates") or []
            now = _find_amount(cands, claimed.get("price_now"))
            if self._has(text, "ended"):
                return self._choice("contradicts", list(q["criteria"]), 0.95)
            if not cands:
                return self._choice("silent", list(q["criteria"]), 0.9)
            if now is None:
                return self._choice("contradicts", list(q["criteria"]), 0.9)
            return self._choice("supports", list(q["criteria"]), 0.9)
        if qid in ("price_now_pick", "price_was_pick"):
            cands = page.get("price_candidates") or []
            want = claimed.get("price_now" if qid == "price_now_pick" else "price_was")
            hit = _find_amount(cands, want)
            if hit is None and qid == "price_now_pick" and cands:
                hit = cands[0]                      # no claimed price on the page: first amount shown
            return self._choice(hit or "none", list(q["criteria"]), 0.9)
        if qid == "offer_kind":
            text += " " + str(claimed.get("found_via") or "").lower()
            for kind in ("clearance", "everyday", "promotion"):
                if self._has(text, kind):
                    return self._choice(kind, list(q["criteria"]), 0.85)
            return self._choice("unclear", list(q["criteria"]), 0.7)
        first = next(iter(q["criteria"]))
        return self._choice(first, list(q["criteria"]), 0.5)


def _find_amount(candidates, value):
    """The candidate string whose amount equals value (to the cent), else None."""
    from scraper.trim import normalize_money
    if value is None:
        return None
    for c in candidates:
        v = normalize_money(c)
        if v is not None and abs(v - float(value)) < 0.005:
            return c
    return None


def _flat(obj):
    """All the values of a dict or list as one string (keys left out)."""
    if isinstance(obj, dict):
        return " ".join(_flat(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return " ".join(_flat(v) for v in obj)
    return "" if obj is None else str(obj)
