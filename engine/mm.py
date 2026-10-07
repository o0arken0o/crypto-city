#!/usr/bin/env python3
"""Crypto Machine engine — deterministic core (stdlib only).

Crypto version of the Money Machine: the pipeline is idea → backtest ("validating") → paper trading
("building") → awaiting_approval → live (owner-approved signals, executed by hand) → scaling, or killed.

Everything that does not need an LLM lives here: state, scoring, strategy
allocation (UCB1 bandit), budget, approvals, ledger, command inbox.
The agents only read `brief` and write results through this CLI, which keeps
each cycle cheap in tokens.

State:  $MM_STATE_DIR (default ./state)
  state.json   single source of truth
  inbox.jsonl  commands from dashboard / GitHub issues, consumed by `apply`
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
import os
import sys
import tempfile
import uuid
from contextlib import contextmanager

STATE_DIR = os.environ.get("MM_STATE_DIR", os.path.join(os.getcwd(), "state"))
STATE_FILE = os.path.join(STATE_DIR, "state.json")
INBOX_FILE = os.path.join(STATE_DIR, "inbox.jsonl")
LOCK_FILE = os.path.join(STATE_DIR, ".lock")
LIVE_FILE = os.path.join(STATE_DIR, "live.json")  # real-time view for the 3D office (not committed)
LIVE_EVENTS_CAP = 40

LOG_CAP = 300
REPORT_CAP = 30
STAGES = ["idea", "validating", "building", "awaiting_approval", "live", "scaling", "killed"]
STAGE_NAME = {"validating": "backtest", "building": "paper", "awaiting_approval": "attesa-ok"}
MIN_CYCLE_USD = 0.05  # below this a cycle can't do useful work
REWARD_REF_EUR = 100.0  # 100 € attributed revenue per pull == reward 1.0
UCB_C = 0.8

AGENTS = {
    "ceo": "Capo del team trading: legge il brief, decide, delega",
    "market-scanner": "Scansiona mercati crypto: trend, volatilità, liquidità, regimi di mercato",
    "quant-analyst": "Trasforma un'idea in una strategia testabile e le dà un punteggio prudente",
    "onchain-analyst": "Dati on-chain, funding, flussi, sentiment: contesto e rischi per le strategie",
    "quant-dev": "Scrive strategy.py, lancia backtest e paper trading, prepara i grafici",
    "risk-manager": "Rischio: drawdown, dimensione delle posizioni, capitale massimo, stop delle strategie",
    "ethics-guard": "Verifica ogni azione rispetto a POLICY.md",
    # team rendite (workflow "Crypto rendite")
    "yield-lead": "Team rendite: legge il brief rendite, decide e delega",
    "yield-scout": "Team rendite: staking e rendimenti su stablecoin/asset principali, con i rischi",
    "airdrop-scout": "Team rendite: airdrop e programmi legittimi (un solo account, niente farming vietato)",
    "portfolio-analyst": "Team rendite: portafoglio del proprietario, ribilanciamento, DCA, risultati reali",
    # team social (workflow "Crypto social"): prepara i post, li pubblica il proprietario
    "social-lead": "Team social: legge il brief social, decide quali post preparare e delega",
    "social-writer": "Team social: testi dei post, caption, hashtag e testo alternativo",
    "visual-designer": "Team social: immagini e caroselli dai grafici veri (backtest, paper trading)",
}
TEAMS = ("trading", "rendite", "social")
SOCIAL_PLATFORMS = ("instagram", "tiktok", "linkedin", "facebook")
SOCIAL_PER_WEEK = 3  # posts prepared for the owner per week, all platforms together
ACTION_CHANNELS = ("golive", "stop", "site", "linkedin")  # executed automatically once the owner approves

STRATEGIES = {
    "trend-following": "Seguire i trend di BTC/ETH/major (medie mobili, breakout) con uscita in cassa",
    "mean-reversion": "Comprare gli eccessi di ribasso e vendere i rimbalzi su timeframe brevi",
    "momentum-rotation": "Ruotare tra le crypto principali più forti, cassa quando tutto scende",
    "smart-dca": "Accumulo periodico (DCA) che compra di più quando il prezzo è basso",
    "volatility-regime": "Esposizione ridotta quando la volatilità esplode, piena quando è calma",
    "yield-staking": "Rendimenti di staking e stablecoin su piattaforme solide (team rendite)",
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).date().isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------- storage

@contextmanager
def locked():
    os.makedirs(STATE_DIR, exist_ok=True)
    fh = open(LOCK_FILE, "w")
    try:
        try:
            import fcntl
            fcntl.flock(fh, fcntl.LOCK_EX)
        except ImportError:  # Windows: best effort
            pass
        yield
    finally:
        fh.close()


def default_state() -> dict:
    return {
        "version": 1,
        "mission": "Trovare e validare strategie crypto con rischio controllato; soldi veri solo dopo backtest, paper trading e ok del proprietario.",
        "status": "running",
        "cycle": 0,
        "last_cycle": None,
        "budget": {
            "usd_per_day": 3.0,
            "usd_per_cycle": 0.5,
            "usd_today": 0.0,
            "usd_total": 0.0,
            "tokens_total": 0,
            "day": today(),
            "cash_spend_limit_eur": 0.0,
            "saver": True,  # savings mode: see saver_active()
        },
        "agents": {
            k: {"desc": v, "status": "active", "weight": 1.0, "runs": 0, "usd": 0.0, "last_run": None, "note": ""}
            for k, v in AGENTS.items()
        },
        "strategies": {
            k: {"desc": v, "status": "active", "weight": 1.0, "pulls": 0}
            for k, v in STRATEGIES.items()
        },
        "markets": [],
        "opportunities": [],
        "approvals": [],
        "ledger": [],
        "directives": [],
        "blockers": [],
        "log": [],
        "reports": [],
        "learnings": [],
        "focus": None,
        "last_run": {},  # team -> ts of the last cycle that actually ran
        "skips": {},     # team -> consecutive cycles skipped because nothing changed
        "last_skip": None,
        "checks": {"ts": None, "items": []},
        "signals": [],     # live strategy signals for the owner (scripts/paper.py → mm signal)
        "traffic": {"boots": {}},  # site visits/clicks per panel process (scripts/traffic_sync.py)  # automatic consistency checks (see housekeeping)
    }


def load() -> dict:
    if not os.path.exists(STATE_FILE):
        return default_state()
    with open(STATE_FILE, encoding="utf-8") as f:
        s = json.load(f)
    # forward-compatible: add missing top-level keys and newly added agents
    fresh = default_state()
    for k, v in fresh.items():
        s.setdefault(k, v)
    for k, v in fresh["agents"].items():
        s["agents"].setdefault(k, v)
    return s


def save(s: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def log(s: dict, agent: str, msg: str) -> None:
    s["log"].append({"ts": now(), "agent": agent, "msg": msg[:400]})
    s["log"] = s["log"][-LOG_CAP:]
    if agent not in ("engine",):
        live_update(lambda L: live_event(L, agent, msg))


# ---------------------------------------------------------------- live (3D office)

def live_load() -> dict | None:
    try:
        with open(LIVE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def live_save(L: dict) -> None:
    L["updated"] = now()
    os.makedirs(STATE_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=STATE_DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(L, f, ensure_ascii=False)
    os.replace(tmp, LIVE_FILE)


def live_update(fn) -> None:
    """Apply fn to the live view only while a cycle is running. Never raises."""
    try:
        L = live_load()
        if L and L.get("running"):
            fn(L)
            live_save(L)
    except Exception:
        pass


def live_event(L: dict, agent: str, msg: str) -> None:
    L.setdefault("events", []).append({"ts": now(), "agent": agent, "msg": str(msg)[:200]})
    L["events"] = L["events"][-LIVE_EVENTS_CAP:]


def agent_short(name: str) -> str:
    return str(name or "").split(":")[-1]  # "crypto-machine:builder" -> "quant-dev"


TEAM_HEAD = {"trading": "ceo", "rendite": "yield-lead", "social": "social-lead"}


def live_begin(run_id: str = "", run_url: str = "", team: str = "trading") -> dict:
    L = live_load() or {}
    if L.get("running") and (not run_id or L.get("run_id") == run_id):
        return L  # idempotent: cycle.sh and begin-cycle both call it
    team = team if team in TEAM_HEAD else "trading"
    head = TEAM_HEAD[team]
    L = {"running": True, "run_id": run_id, "run_url": run_url, "started": now(), "ended": None, "result": None,
         "team": team, "head": head, "agents": {k: {"status": "idle"} for k in AGENTS}, "events": []}
    L["agents"][head] = {"status": "working", "task": "legge il brief e decide", "since": now()}
    live_event(L, head, "ciclo avviato")
    live_save(L)
    return L


def live_end(result: str = "ok") -> None:
    L = live_load()
    if not L:
        return
    for a in L.get("agents", {}).values():
        a["status"], a["task"] = "idle", None
    if L.get("running"):
        live_event(L, L.get("head", "ceo"), {"ok": "ciclo terminato", "skip": "ciclo saltato"}.get(result, f"ciclo terminato ({result})"))
    L["running"], L["ended"], L["result"] = False, now(), result
    live_save(L)


# Relative price of each kind of token (same for every Claude model): used to split a model's real cost
# among the agents that used it.
TOKEN_WEIGHTS = {"input_tokens": 1.0, "cache_creation_input_tokens": 1.25, "cache_read_input_tokens": 0.1, "output_tokens": 5.0}


def _model_key(m: str) -> str:
    return re.sub(r"\[.*?\]", "", str(m or "")).strip().lower()


def transcript_usage(path) -> dict:
    """{model: weighted tokens} of a sub-agent transcript (JSONL). Each API message counted once."""
    msgs = {}
    try:
        with open(os.path.expanduser(path), encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                m = e.get("message") if isinstance(e, dict) else None
                if isinstance(m, dict) and m.get("usage") and e.get("type") == "assistant":
                    msgs[m.get("id") or len(msgs)] = (_model_key(m.get("model")), m["usage"])
    except (OSError, TypeError):
        return {}
    out = {}
    for model, u in msgs.values():
        out[model] = out.get(model, 0) + sum(float(u.get(k, 0) or 0) * w for k, w in TOKEN_WEIGHTS.items())
    return out


def split_cost(total_usd: float, model_usage: dict, agents_usage: dict, head: str) -> dict:
    """{agent: usd}: each model's real cost goes to the sub-agents in proportion to their tokens; the rest
    (the team head's own reasoning) to the head. Sums to total_usd."""
    out = {}
    for m, mu in (model_usage or {}).items():
        cost = float(mu.get("costUSD", 0) or 0)
        tot = (float(mu.get("inputTokens", 0) or 0) + 1.25 * float(mu.get("cacheCreationInputTokens", 0) or 0)
               + 0.1 * float(mu.get("cacheReadInputTokens", 0) or 0) + 5 * float(mu.get("outputTokens", 0) or 0))
        if cost <= 0 or tot <= 0:
            continue
        for name, u in agents_usage.items():
            w = u.get("models", {}).get(_model_key(m), 0)
            if w:
                out[name] = out.get(name, 0) + cost * min(1.0, w / tot)
    spent = sum(out.values())
    if spent > total_usd > 0:  # rounding or missing data: scale down
        out = {k: v * total_usd / spent for k, v in out.items()}
    out[head] = out.get(head, 0) + max(0.0, total_usd - sum(out.values()))
    return {k: round(v, 4) for k, v in out.items() if v > 0}


def live_hook(h: dict) -> None:
    """Claude Code hook payloads: PreToolUse(Agent/Task), SubagentStart, SubagentStop."""
    ev = h.get("hook_event_name")

    def apply(L):
        agents = L.setdefault("agents", {})
        if ev == "PreToolUse":
            ti = h.get("tool_input") or {}
            name = agent_short(ti.get("subagent_type"))
            if name:
                L.setdefault("pending", {})[name] = str(ti.get("description") or ti.get("prompt") or "")[:140]
        elif ev == "SubagentStart":
            name = agent_short(h.get("agent_type"))
            task = (L.get("pending") or {}).pop(name, "") or "al lavoro"
            agents[name] = {"status": "working", "task": task, "since": now(), "agent_id": h.get("agent_id")}
            live_event(L, L.get("head", "ceo"), f"delega a {name}: {task}")
        elif ev == "SubagentStop":
            name = agent_short(h.get("agent_type"))
            if name:
                use = L.setdefault("usage", {}).setdefault(name, {"runs": 0, "models": {}})
                use["runs"] += 1
                for m, w in transcript_usage(h.get("agent_transcript_path")).items():
                    use["models"][m] = use["models"].get(m, 0) + w
            done = str(h.get("last_assistant_message") or "").strip().replace("\n", " ")
            agents[name] = {"status": "idle", "task": None, "last": done[:160], "since": now()}
            live_event(L, name, f"ha finito: {done[:120]}" if done else "ha finito")
    live_update(apply)


TEAM_AGENTS = {
    "trading": {"ceo", "market-scanner", "quant-analyst", "onchain-analyst", "quant-dev", "risk-manager", "ethics-guard"},
    "rendite": {"yield-lead", "yield-scout", "airdrop-scout", "portfolio-analyst", "ethics-guard"},
    "social": {"social-lead", "social-writer", "visual-designer", "ethics-guard"},
}
MAX_SKIPS = 3  # after 3 skipped cycles the next one runs anyway


def should_skip(s: dict, team: str) -> str:
    """Reason to skip this team's cycle, or "" to run it. Skips only while the team is waiting on the
    owner (pending approvals it asked for) and nothing new happened since its last run."""
    if team == "social":  # nothing to post about, or this week's posts are already prepared: no AI spend
        if not any(o["stage"] in ("building", "live", "scaling") for o in s["opportunities"]):
            return "nessuna strategia in paper trading o live di cui parlare"
        week = (dt.date.today() - dt.timedelta(days=6)).isoformat()
        drafts = social_drafts(os.path.dirname(STATE_DIR))
        n = sum(1 for d in drafts if d["date"] >= week)
        if n >= SOCIAL_PER_WEEK and all(d["images"] for d in drafts):  # an unfinished post is always worth finishing
            return f"già {n} post preparati questa settimana (limite {SOCIAL_PER_WEEK})"
    last = (s.get("last_run") or {}).get(team)
    if not last or (s.get("skips") or {}).get(team, 0) >= MAX_SKIPS:
        return ""
    mine = [a for a in s["approvals"] if a["status"] == "pending" and a.get("by") in TEAM_AGENTS.get(team, set())]
    if not mine:
        return ""
    news = [l for l in s["log"] if l["ts"] >= last and l["agent"] in ("human", "paper", "signal")]
    if news:
        return ""
    return f"in attesa di {len(mine)} approvazion{'e' if len(mine) == 1 else 'i'} e nessuna novità dall'ultimo ciclo"


SAVER_DAY_USD = 2.0     # savings mode: AI spend per day until the first real revenue
SAVER_AFTER_USD = 10.0  # ...once this much AI has already been spent without earning anything


def saver_active(s: dict) -> bool:
    """Savings mode (on by default, the owner can switch it off): no real revenue in the last 30 days after
    SAVER_AFTER_USD of AI spend → at most SAVER_DAY_USD a day. Spending more does not bring the first sale:
    customers finding the products does."""
    b = s["budget"]
    if not b.get("saver", True) or b.get("usd_total", 0) < SAVER_AFTER_USD:
        return False
    since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    return not any(e["type"] == "revenue" and str(e.get("date", "")) >= since for e in s["ledger"])


def effective_day(s: dict) -> float:
    """Daily AI budget actually applied today (the owner's, or the savings-mode one if lower)."""
    d = s["budget"]["usd_per_day"]
    return min(d, SAVER_DAY_USD) if saver_active(s) else d


def saver_note(s: dict) -> str:
    return f" (modalità risparmio: max {SAVER_DAY_USD:.0f}$/giorno finché non arriva un incasso)" if effective_day(s) < s["budget"]["usd_per_day"] else ""


def cycle_cap(s: dict) -> float:
    """Spend cap for the next cycle: per-cycle budget, never more than a third of the daily budget (one runaway
    cycle must not burn the whole day) nor more than what is left today."""
    b, day = s["budget"], effective_day(s)
    return round(max(0.0, min(b["usd_per_cycle"], day / 3, day - b["usd_today"])), 4)


def make_report(s: dict, r: dict) -> dict:
    """CEO's end-of-cycle report for the owner: plain language, short lists."""
    def items(key, n):
        v = r.get(key) or []
        if isinstance(v, str):
            v = [v]
        return [str(x).strip()[:200] for x in v if str(x).strip()][:n]
    team = r.get("team") if r.get("team") in TEAMS else "trading"
    rep = {"cycle": s["cycle"], "team": team, "ts": now(), "headline": str(r.get("headline", "")).strip()[:160],
           "done": items("done", 6), "next": items("next", 4), "needs_you": items("needs_you", 4), "usd": None}
    if not rep["headline"]:
        raise ValueError("headline obbligatoria")
    same = lambda x: x.get("cycle") == rep["cycle"] and x.get("team", "trading") == team
    s["reports"] = [x for x in s["reports"] if not same(x)] + [rep]
    s["reports"] = s["reports"][-REPORT_CAP:]
    return rep


def roll_day(s: dict) -> None:
    b = s["budget"]
    if b.get("day") != today():
        b["day"] = today()
        b["usd_today"] = 0.0


# ---------------------------------------------------------------- scoring

def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def market_score(m: dict) -> float:
    """0-100. demand/ticket/speed/competition on 1-5, confidence 0-1."""
    d = clamp(float(m.get("demand", 3)), 1, 5)
    t = clamp(float(m.get("ticket", 3)), 1, 5)
    sp = clamp(float(m.get("speed", 3)), 1, 5)
    c = clamp(float(m.get("competition", 3)), 1, 5)
    conf = clamp(float(m.get("confidence", 0.5)), 0, 1)
    raw = (d * t * sp) / c  # 0.2 .. 125
    return round(100 * math.log1p(raw) / math.log1p(125) * (0.5 + 0.5 * conf), 1)


def _unit(o: dict, key: str):
    """Optional 0-1 field; None when absent (neutral in the score)."""
    try:
        return clamp(float(o[key]), 0, 1) if o.get(key) is not None else None
    except (TypeError, ValueError):
        return None


def quality_factor(o: dict) -> float:
    """Multiplier from the validation evidence; 1.0 when an opportunity has none of these fields.
    evidence_score: proof of PAYING demand (sales, reviews, recurring paid requests) 0-1
    niche_specificity: 0 generic ("templates") .. 1 precise ("CRM Excel for Italian photographers")
    competitors: direct competitors found; beyond 3, each one lowers the score a little
    bundle_potential / related_to: fits a portfolio with products already on sale."""
    f = 1.0
    e = _unit(o, "evidence_score")
    if e is not None:
        f *= 0.4 + 1.2 * e  # 0.4 .. 1.6: paying demand matters most
    sp = _unit(o, "niche_specificity")
    if sp is not None:
        f *= 0.75 + 0.5 * sp  # 0.75 .. 1.25
    try:
        n = max(0, int(o.get("competitors") or 0))
    except (TypeError, ValueError):
        n = 0
    f /= 1 + max(0, n - 3) * 0.06
    bp = _unit(o, "bundle_potential")
    if bp is not None:
        f *= 1 + 0.25 * bp
    if o.get("related_to"):
        f *= 1.1
    return f


def opp_score(o: dict) -> float:
    """Risk-adjusted return per unit of cost and time, 0-100."""
    exp = max(0.0, float(o.get("expected_eur", 0)))
    conf = clamp(float(o.get("confidence", 0.3)), 0, 1)
    cost = max(0.0, float(o.get("cost_eur", 0)))
    effort = max(0.0, float(o.get("effort_h", 4)))
    days = max(0.0, float(o.get("days_to_cash", 14)))
    value = exp * conf * quality_factor(o)
    denom = cost + effort * 15 + 1  # 15 €/h opportunity cost of agent+human time
    speed = 30 / (days + 30)
    roi = value / denom * speed
    return round(100 * (1 - math.exp(-roi / 2)), 1)


def strategy_revenue(s: dict) -> dict:
    opp_strat = {o["id"]: o.get("strategy") for o in s["opportunities"]}
    rev = {k: 0.0 for k in s["strategies"]}
    for e in s["ledger"]:
        st = e.get("strategy") or opp_strat.get(e.get("opportunity"))
        if st in rev:
            rev[st] += e["amount_eur"] if e["type"] == "revenue" else -e["amount_eur"]
    return rev


def allocate(s: dict, k: int = 2) -> list[dict]:
    """UCB1 with an optimistic prior from market scores, times human weight."""
    rev = strategy_revenue(s)
    total = sum(v["pulls"] for v in s["strategies"].values())
    rows = []
    for name, st in s["strategies"].items():
        if st["status"] != "active" or st["weight"] <= 0:
            continue
        ms = [m["score"] for m in s["markets"] if m.get("strategy") == name]
        prior = (sum(ms) / len(ms) / 200) if ms else 0.2  # estimates weigh less than real revenue
        pulls = st["pulls"]
        mean_rev = rev[name] / max(pulls, 1)
        observed = clamp(mean_rev / REWARD_REF_EUR, -1, 1)
        n = max(pulls, 1) if rev[name] else pulls  # revenue counts even before the first pull
        mean = (observed * n + prior * 2) / (n + 2)
        bonus = UCB_C * math.sqrt(math.log(total + 2) / (pulls + 1))
        rows.append({"strategy": name, "value": round((mean + bonus) * st["weight"], 3),
                     "mean": round(mean, 3), "pulls": pulls, "revenue_eur": round(rev[name], 2)})
    rows.sort(key=lambda r: r["value"], reverse=True)
    return rows[:k] if k else rows


# ---------------------------------------------------------------- commands

def find(items, _id):
    for it in items:
        if it["id"] == _id:
            return it
    return None


def apply_command(s: dict, c: dict) -> str:
    """Commands from the dashboard / GitHub issues. Returns a log line."""
    op = c.get("op")
    a = c.get("args", {}) or {}
    if op == "linkedin":  # {expires: YYYY-MM-DD}: sent by the panel when the owner connects LinkedIn
        exp = str(a.get("expires", ""))[:10]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", exp):
            return f"linkedin: data non valida {a}"
        s["linkedin"] = {"expires": exp, "connected": now()}
        for b in s["blockers"]:  # reconnected: the reminder is done
            if b["status"] == "open" and b["title"].startswith(LI_RENEW):
                set_blocker(s, b["id"], "done", "human")
        return f"linkedin: collegamento valido fino al {exp}"
    if op == "traffic":  # the panel's counts, sent by the panel itself just before it restarts (see dashboard/server.py)
        return add_traffic(s, a)
    if op == "system":  # {state: running|paused}
        s["status"] = "paused" if a.get("state") == "paused" else "running"
        return f"sistema → {s['status']}"
    if op in ("agent", "strategy"):  # {name, status?, weight?, note?}
        coll = s["agents"] if op == "agent" else s["strategies"]
        it = coll.get(a.get("name"))
        if not it:
            return f"{op} sconosciuto: {a.get('name')}"
        if "status" in a:
            it["status"] = "paused" if a["status"] == "paused" else "active"
        if "weight" in a:
            it["weight"] = clamp(float(a["weight"]), 0, 5)
        if "note" in a:
            it["note"] = str(a["note"])[:300]
        return f"{op} {a['name']} → {it['status']} w={it['weight']}"
    if op == "approval":  # {id, decision: approved|rejected, note?}
        ap = find(s["approvals"], a.get("id"))
        if not ap or ap["status"] != "pending":
            return f"approvazione non trovata/già risolta: {a.get('id')}"
        ap["status"] = "approved" if a.get("decision") == "approved" else "rejected"
        ap["resolved"] = now()
        ap["note"] = str(a.get("note", ""))[:300]
        return f"approvazione {ap['id']} → {ap['status']}"
    if op == "opportunity":  # {id, stage}
        o = find(s["opportunities"], a.get("id"))
        if not o or a.get("stage") not in STAGES:
            return f"opportunità/stage non valido: {a}"
        o["stage"], o["updated"] = a["stage"], now()
        return f"opportunità {o['id']} → {o['stage']}"
    if op == "directive_add":
        d = {"id": new_id("dir"), "text": str(a.get("text", ""))[:500], "created": now()}
        if d["text"]:
            s["directives"].append(d)
        return f"direttiva aggiunta: {d['text'][:80]}"
    if op == "directive_remove":
        s["directives"] = [d for d in s["directives"] if d["id"] != a.get("id")]
        return f"direttiva rimossa {a.get('id')}"
    if op == "learning_remove":  # {id}
        n = len(s["learnings"])
        s["learnings"] = [x for x in s["learnings"] if x["id"] != a.get("id")]
        return f"lezione rimossa {a.get('id')}" if len(s["learnings"]) < n else f"lezione non trovata: {a.get('id')}"
    if op == "focus":  # {strategies: [...]} ; [] ends the focus and restores the weights
        return set_focus(s, a.get("strategies") or [])
    if op == "budget":  # any of usd_per_day, usd_per_cycle, cash_spend_limit_eur, saver (true/false)
        for key in ("usd_per_day", "usd_per_cycle", "cash_spend_limit_eur"):
            if key in a:
                s["budget"][key] = max(0.0, float(a[key]))
        if "saver" in a:
            s["budget"]["saver"] = bool(a["saver"])
        return f"budget aggiornato {a}"
    if op == "ledger":  # {type, amount_eur, source, opportunity?, strategy?, note?}
        return add_ledger(s, a, agent="human")
    if op == "blocker_add":  # {title, blocks:[opp_id|testo], owner: human|agent, how?, link?, id?}
        return add_blocker(s, a, agent="human")
    if op in ("blocker_done", "blocker_reopen"):  # {id}
        return set_blocker(s, a.get("id"), "done" if op == "blocker_done" else "open", "human")
    if op == "blocker_remove":  # {id}
        n = len(s["blockers"])
        s["blockers"] = [b for b in s["blockers"] if b["id"] != a.get("id")]
        return f"blocco rimosso {a.get('id')}" if len(s["blockers"]) < n else f"blocco non trovato: {a.get('id')}"
    return f"comando sconosciuto: {op}"


SIGNALS_CAP = 60


def add_signal(s: dict, a: dict) -> str:
    """A live strategy changed its exposure: the owner gets it on Telegram and in the panel, and decides."""
    o = find(s["opportunities"], str(a.get("opportunity") or ""))
    text = str(a.get("text") or "").strip()[:400]
    if not o or not text:
        return f"segnale non valido: {a}"
    sig = {"id": new_id("sig"), "ts": now(), "opportunity": o["id"], "text": text,
           "pair": str(a.get("pair") or "")[:20], "to": a.get("to"), "price": a.get("price")}
    s.setdefault("signals", []).append(sig)
    s["signals"] = s["signals"][-SIGNALS_CAP:]
    log(s, "signal", text[:200])
    return f"segnale {sig['id']}: {text[:80]}"


LEARNINGS_CAP = 40


def add_learning(s: dict, text: str, agent: str) -> str:
    """Something the agents found out and must not rediscover (what sells, what failed, community rules)."""
    text = " ".join(str(text or "").split())[:280]
    if len(text) < 8:
        return "lezione troppo corta"
    if any(x["text"].lower() == text.lower() for x in s["learnings"]):
        return "lezione già registrata"
    s["learnings"].append({"id": new_id("lrn"), "ts": now(), "agent": agent, "text": text})
    s["learnings"] = s["learnings"][-LEARNINGS_CAP:]
    return f"lezione registrata: {text[:80]}"


def set_focus(s: dict, names: list) -> str:
    names = [n for n in names if n in s["strategies"]]
    focus = s.get("focus")
    if not names:
        if not focus:
            return "nessun focus attivo"
        for n, w in focus.get("prev_weights", {}).items():
            if n in s["strategies"]:
                s["strategies"][n]["weight"] = w
        s["focus"] = None
        return "focus terminato: pesi ripristinati"
    prev = focus["prev_weights"] if focus else {n: st["weight"] for n, st in s["strategies"].items()}
    for n, st in s["strategies"].items():
        st["weight"] = max(1.0, prev.get(n, 1.0)) if n in names else 0.0
    s["focus"] = {"strategies": names, "since": now(), "prev_weights": prev}
    return f"focus su: {', '.join(names)}"


BLOCKER_OWNERS = ("human", "agent")
BLOCKER_ID = re.compile(r"^blk_[a-z0-9_]{3,40}$")


def add_blocker(s: dict, a: dict, agent: str) -> str:
    """Something that stands between an opportunity (or a goal) and revenue, and who must remove it."""
    title = str(a.get("title", "")).strip()[:160]
    if not title:
        return f"blocco non valido: {a}"
    how = str(a.get("how", ""))[:300]
    if agent in TEAM_AGENTS["social"] and title.lower().startswith("pubblica"):  # a post goes to the owner only when complete
        m = re.search(r"products/[\w.-]+/social/[\w.-]+", how)
        folder = os.path.join(os.path.dirname(STATE_DIR), m.group(0)) if m else ""
        if not (m and os.path.isfile(os.path.join(folder, "POST.md"))
                and any(f.startswith("slide-") and f.endswith(".png") for f in os.listdir(folder))):
            return "RIFIUTATO: il post non è completo. Nel campo how serve la cartella products/<id>/social/<data>-<piattaforma>/ con POST.md e le immagini slide-NN.png (visual-designer)."
    dup = next((b for b in s["blockers"] if b["status"] == "open" and b["title"] == title), None)
    if dup:
        if agent in TEAM_AGENTS["social"] and dup.get("by") in TEAM_AGENTS["social"]:  # the social team refreshes its own post
            link = str(a.get("link") or "")[:300]
            dup["how"] = how or dup["how"]
            if link.startswith(("https://", "http://")):
                dup["link"] = link
            return f"blocco {dup['id']} aggiornato: {title[:80]}"
        return f"blocco già aperto {dup['id']}"
    blocks = a.get("blocks") or []
    blocks = [str(x)[:120] for x in (blocks if isinstance(blocks, list) else [blocks]) if str(x).strip()][:10]
    link = str(a.get("link") or "")[:300]
    bid = a.get("id") if BLOCKER_ID.match(str(a.get("id", ""))) and not find(s["blockers"], a["id"]) else new_id("blk")
    b = {"id": bid, "title": title, "blocks": blocks,
         "owner": a.get("owner") if a.get("owner") in BLOCKER_OWNERS else "human",
         "how": how, "link": link if link.startswith(("https://", "http://")) else "",
         "status": "open", "created": now(), "by": agent, "resolved": None}
    s["blockers"].append(b)
    return f"blocco {b['id']} aperto: {title[:80]}"


def set_blocker(s: dict, bid: str, status: str, agent: str) -> str:
    b = find(s["blockers"], bid or "")
    if not b:
        return f"blocco non trovato: {bid}"
    b["status"], b["resolved"] = status, (now() if status == "done" else None)
    return f"blocco {b['id']} → {'risolto' if status == 'done' else 'riaperto'} ({agent})"


LEDGER_KINDS = ("trading", "staking", "airdrop", "altro")


def add_ledger(s: dict, a: dict, agent: str) -> str:
    """`ref` (e.g. "kraken:<trade_id>") makes imports idempotent; `kind` feeds the fiscal counter."""
    typ = a.get("type")
    amt = float(a.get("amount_eur", 0))
    if typ not in ("revenue", "cost") or amt <= 0:
        return f"voce ledger non valida: {a}"
    ref = str(a.get("ref") or "")[:120] or None
    if ref and any(e.get("ref") == ref for e in s["ledger"]):
        return f"ledger già registrato: {ref}"
    kind = a.get("kind") if a.get("kind") in LEDGER_KINDS else None
    e = {"id": new_id("tx"), "date": a.get("date") or today(), "type": typ, "amount_eur": round(amt, 2),
         "source": str(a.get("source", ""))[:120], "opportunity": a.get("opportunity"),
         "strategy": a.get("strategy"), "note": str(a.get("note", ""))[:300], "by": agent}
    if ref:
        e["ref"] = ref
    if kind:
        e["kind"] = kind
    s["ledger"].append(e)
    return f"ledger {typ} {amt:.2f}€ ({e['source']})"


def enqueue(cmd: dict) -> dict:
    cmd = {"id": new_id("cmd"), "ts": now(), **cmd}
    with locked():
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(INBOX_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(cmd, ensure_ascii=False) + "\n")
    return cmd


def drain_inbox(s: dict) -> list[str]:
    if not os.path.exists(INBOX_FILE):
        return []
    out = []
    with open(INBOX_FILE, encoding="utf-8") as f:
        lines = [ln for ln in f if ln.strip()]
    for ln in lines:
        try:
            msg = apply_command(s, json.loads(ln))
        except Exception as e:  # malformed command must not stop the machine
            msg = f"comando scartato: {e}"
        log(s, "human", msg)
        out.append(msg)
    open(INBOX_FILE, "w").close()
    return out


# ---------------------------------------------------------------- metrics / brief

def attribution(s: dict) -> list[dict]:
    """Real revenue per product (opportunity) and strategy, best first."""
    opps = {o["id"]: o for o in s["opportunities"]}
    rows = {}
    for e in s["ledger"]:
        if e["type"] != "revenue":
            continue
        key = e.get("opportunity") or "—"
        o = opps.get(key, {})
        r = rows.setdefault(key, {"opportunity": e.get("opportunity"), "title": o.get("title") or e.get("source") or "altro",
                                  "strategy": e.get("strategy") or o.get("strategy"), "revenue_eur": 0.0, "orders": 0, "last": None})
        r["revenue_eur"] = round(r["revenue_eur"] + e["amount_eur"], 2)
        r["orders"] += 1
        r["last"] = max(r["last"] or "", str(e.get("date", "")))
    return sorted(rows.values(), key=lambda r: -r["revenue_eur"])


def kpis(s: dict) -> dict:
    rev = sum(e["amount_eur"] for e in s["ledger"] if e["type"] == "revenue")
    cost = sum(e["amount_eur"] for e in s["ledger"] if e["type"] == "cost")
    ai_eur = s["budget"]["usd_total"] * 0.92
    net = rev - cost - ai_eur
    spent = cost + ai_eur
    stages = {st: 0 for st in STAGES}
    for o in s["opportunities"]:
        stages[o.get("stage", "idea")] = stages.get(o.get("stage", "idea"), 0) + 1
    return {"saver": {"active": saver_active(s), "day_usd": effective_day(s), "max_usd": SAVER_DAY_USD, "after_usd": SAVER_AFTER_USD},
            "revenue_eur": round(rev, 2), "cost_eur": round(cost, 2), "ai_cost_eur": round(ai_eur, 2),
            "net_eur": round(net, 2), "roi": round(net / spent, 2) if spent else None,
            "pipeline": stages, "pending_approvals": sum(a["status"] == "pending" for a in s["approvals"]),
            "fiscal": fiscal_year(s), "attribution": attribution(s), "traffic": traffic_summary(s), "week": weekly(s)}


def fiscal_year(s: dict, year: int | None = None) -> dict:
    """Per-calendar-year totals for the tax return / accountant. Italy has no revenue threshold that
    decides the P.IVA obligation (habitual activity does); 5,000 € only concerns INPS on occasional
    self-employment, i.e. the `servizio` kind."""
    year = year or dt.date.today().year
    rows = [e for e in s["ledger"] if str(e.get("date", ""))[:4] == str(year)]
    rev = [e for e in rows if e["type"] == "revenue"]
    by_source, by_kind = {}, {}
    for e in rev:
        src = e.get("source") or "?"
        by_source[src] = round(by_source.get(src, 0) + e["amount_eur"], 2)
        k = e.get("kind") or "non indicato"
        by_kind[k] = round(by_kind.get(k, 0) + e["amount_eur"], 2)
    services = by_kind.get("servizio", 0.0)
    return {"year": year,
            "revenue_eur": round(sum(e["amount_eur"] for e in rev), 2),
            "cost_eur": round(sum(e["amount_eur"] for e in rows if e["type"] == "cost"), 2),
            "transactions": len(rev),
            "active_months": len({str(e["date"])[:7] for e in rev}),
            "by_source": by_source, "by_kind": by_kind,
            "services_eur": services,
            "services_over_5000": services > 5000}


def fiscal_text(f: dict) -> str:
    L = [f"# Fisco {f['year']} (anno solare, solo risultati reali nel ledger)",
         f"guadagni registrati {f['revenue_eur']:.2f}€ · perdite/costi {f['cost_eur']:.2f}€ · {f['transactions']} voci in {f['active_months']} mesi"]
    if f["by_source"]:
        L.append("per piattaforma: " + ", ".join(f"{k} {v:.2f}€" for k, v in sorted(f["by_source"].items())))
    if f["by_kind"]:
        L.append("per tipo: " + ", ".join(f"{k} {v:.2f}€" for k, v in sorted(f["by_kind"].items())))
    L += ["",
          "Promemoria cripto-attività in Italia (non è consulenza fiscale, verifica con il commercialista):",
          "- Dal 2026 le plusvalenze su cripto-attività sono tassate al 33% (26% nel 2025), senza franchigia;",
          "  le minusvalenze si possono compensare con le plusvalenze della stessa categoria.",
          "- Le crypto vanno indicate nel quadro RW (monitoraggio) anche senza vendite; c'è l'imposta di bollo/IVCA.",
          "- Lo scambio crypto→crypto ha regole proprie (permute): conserva lo storico completo delle operazioni.",
          "- Staking e airdrop possono essere redditi: registra data, quantità e valore in euro al momento della ricezione.",
          "- Dal 2026 gli exchange UE comunicano le operazioni al Fisco (DAC8)."]
    return "\n".join(L)


MARKETS = ("BTC", "ETH", "SOL", "XRP", "ADA", "CRO")  # keep in sync with scripts/market_data.py MARKETS


def uncovered_markets(s: dict, days: int = 14) -> list[str]:
    """Coins of the universe with no market or strategy mentioning them in the last `days` days."""
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    seen = " ".join(f"{m.get('name', '')} {m.get('evidence', '')}" for m in s.get("markets", []) if str(m.get("created", m.get("updated", ""))) >= since)
    seen += " " + " ".join(f"{o.get('title', '')} {o.get('rules', '')}" for o in s.get("opportunities", []) if str(o.get("updated", o.get("created", ""))) >= since)
    return [a for a in MARKETS if not re.search(rf"\b{a}\b", seen.upper())]


def _universe_lines(s: dict) -> list[str]:
    todo = uncovered_markets(s)
    out = [f"## Mercati ammessi: {', '.join(f'{a}-USD/EUR' for a in MARKETS)} (nient'altro: niente memecoin né token piccoli)"]
    if todo:
        out.append(f"Da studiare (nessuna analisi negli ultimi 14 giorni): {', '.join(todo)} → il market-scanner ne copre almeno uno in questo ciclo")
    return out


def brief(s: dict, alloc: list | None = None) -> str:
    """Compact context for the CEO (~40 lines). The only thing it must read."""
    roll_day(s)
    b, k = s["budget"], kpis(s)
    L = [f"# BRIEF TRADING ciclo {s['cycle'] + 1} · {now()}",
         f"stato={s['status']} · budget oggi {b['usd_today']:.2f}/{effective_day(s):.2f}${saver_note(s)} · ciclo max {cycle_cap(s):.2f}$ · spesa cash max {b['cash_spend_limit_eur']:.0f}€",
         f"KPI ricavi={k['revenue_eur']}€ costi={k['cost_eur']}€ AI={k['ai_cost_eur']}€ netto={k['net_eur']}€",
         "pipeline " + " ".join(f"{STAGE_NAME.get(a, a)}={n}" for a, n in k["pipeline"].items() if n)]
    if s["directives"]:
        L.append("## DIRETTIVE UMANE (priorità massima)")
        L += [f"- [{d['id']}] {d['text']}" for d in s["directives"]]
    L += _checks_lines(s)
    opn = [b for b in s["blockers"] if b["status"] == "open"]
    if opn:
        L.append("## Blocchi aperti (non ripeterli nei report; chiudi con `unblock <id>` se li risolvi tu)")
        L += [f"- {b['id']} [{'umano' if b['owner'] == 'human' else 'agenti'}] {b['title'][:90]} → blocca {', '.join(b['blocks']) or '—'}" for b in opn[:8]]
    L += _focus_and_learnings(s)
    L += _universe_lines(s)
    paused = [n for n, a in s["agents"].items() if a["status"] != "active"]
    if paused:
        L.append(f"## Agenti in pausa (NON usarli): {', '.join(paused)}")
    boosted = [f"{n}×{a['weight']}" for n, a in s["agents"].items() if a["status"] == "active" and a["weight"] != 1]
    if boosted:
        L.append(f"pesi agenti: {', '.join(boosted)}")
    L.append("## Strategie scelte per questo ciclo (UCB)")
    L += [f"- {r['strategy']} v={r['value']} pulls={r['pulls']} ricavi={r['revenue_eur']}€" for r in (alloc or allocate(s, 2))]
    decided = [a for a in s["approvals"] if a["status"] in ("approved", "rejected") and not a.get("consumed")]
    if decided:
        L.append("## Decisioni umane da eseguire/archiviare")
        L += [f"- {a['id']} {a['status'].upper()}: {a['title']} (opp {a.get('opportunity')}) {a.get('note', '')}" for a in decided]
    pend = [a for a in s["approvals"] if a["status"] == "pending"]
    if pend:
        L.append(f"## In attesa di approvazione ({len(pend)}) — non ripetere richieste")
        L += [f"- {a['id']} {a['title']}" for a in pend[:5]]
    ops = sorted([o for o in s["opportunities"] if o["stage"] not in ("killed",)], key=lambda o: -o["score"])[:6]
    if ops:
        L.append("## Top opportunità")
        L += [f"- {o['id']} [{o['stage']}] {o['title']} score={o['score']} exp={o.get('expected_eur')}€"
              + (f" prove={o['evidence_score']}" if o.get("evidence_score") is not None else " prove=?")
              + (f" prezzi-concorrenti={o['competitor_price_range']}" if o.get("competitor_price_range") else "")
              + (f" · {perf_line(strategy_files(repo_root(), o['id']))}" if o["stage"] != "idea" else "")
              + f" next: {o.get('next_action', '')[:90]}" for o in ops]
    mk = sorted(s["markets"], key=lambda m: -m["score"])[:5]
    if mk:
        L.append("## Top mercati")
        L += [f"- {m['id']} {m['name']} ({m.get('strategy')}) score={m['score']} agg={m.get('updated', '')[:10]}" for m in mk]
    recent = [l for l in s["log"] if l["agent"] != "engine"][-5:]
    if recent:
        L.append("## Ultimi eventi")
        L += [f"- {l['ts'][5:16]} {l['agent']}: {l['msg'][:110]}" for l in recent]
    return "\n".join(L)


# ---------------------------------------------------------------- consistency + work in progress
# "live" must mean "a customer can buy it now". The engine checks it on the repo files instead of
# trusting whoever moved the card: finished products that nobody asked to publish and draft pages
# without an approval request are reported to the agents first, before any new research.

REPO_ROOT = None  # tests override; default: the folder that contains state/
WIP_MAX = 3       # strategies in backtest before new research is refused (paper trading costs nothing)
PLACEHOLDER = re.compile(r"\[LINK|DA_INSERIRE|DA INSERIRE|TODO", re.I)


def repo_root() -> str:
    return REPO_ROOT or os.path.dirname(os.path.abspath(STATE_DIR))


def _files(d: str) -> list[str]:
    return [n for n in os.listdir(d) if not n.startswith(".") and os.path.isfile(os.path.join(d, n))] if os.path.isdir(d) else []


def is_live(s: dict, o: dict, root: str) -> str:
    """Why the strategy counts as live ("" if it does not): the owner approved it (products/<id>/live.json,
    written only by scripts/actions.py) or it already produced real results in the ledger."""
    lv = _read_json(os.path.join(root, "products", o["id"], "live.json"))
    if lv.get("approved"):
        return f"approvata dal proprietario ({lv.get('capital_eur', '?')} € max)"
    if any(e.get("opportunity") == o["id"] for e in s["ledger"]):
        return "ha già risultati reali nel ledger"
    return ""


def strategy_files(root: str, oid: str) -> dict:
    """What exists for a strategy: code, backtest result, paper trading book."""
    d = os.path.join(root, "products", oid)
    bt = _read_json(os.path.join(d, "backtest.json"))
    pp = _read_json(os.path.join(d, "paper.json"))
    verdict = bt.get("verdict")
    if bt and int(bt.get("rules", 1) or 1) < BACKTEST_RULES:
        verdict = "OLD"  # tested with older, looser rules: it must be tested again
    return {"code": os.path.isfile(os.path.join(d, "strategy.py")), "backtest": bt, "paper": pp,
            "verdict": verdict, "paper_days": float((pp.get("metrics") or {}).get("days") or 0)}


PAPER_DAYS_MIN = 14  # paper trading before the owner can be asked to go live
BACKTEST_RULES = 2   # = scripts/backtest.py RULES_VERSION


def perf_line(f: dict) -> str:
    bt, pp = f["backtest"], (f["paper"].get("metrics") or {})
    out = []
    if bt:
        o = bt.get("out_of_sample") or {}
        out.append(f"backtest {bt.get('verdict')} oos {float(o.get('return', 0)) * 100:+.1f}% sharpe {o.get('sharpe')} DD {float((bt.get('full') or {}).get('max_dd', 0)) * 100:.0f}%")
    if pp:
        out.append(f"paper {float(pp.get('return', 0)) * 100:+.1f}% vs hold {float(pp.get('hold_return', 0)) * 100:+.1f}% in {pp.get('days', 0):.0f}g")
    return " · ".join(out)


def _asked(s: dict, channel: str, key: str, field: str = "opportunity") -> bool:
    """An approval for this object is pending, approved and not yet executed, or was rejected by the owner."""
    return any(a.get("channel") == channel and (a.get(field) or (a.get("opportunity") if field == "target" else None)) == key
               and (a["status"] in ("pending", "rejected") or (a["status"] == "approved" and not a.get("consumed")))
               for a in s["approvals"])


LI_RENEW = "Ricollega LinkedIn"


def linkedin_reminder(s: dict, today: dt.date | None = None) -> list[str]:
    """A week before the LinkedIn token expires (60 days), ask the owner to reconnect: an open "tocca a te"
    block, so it shows in the panel and on Telegram. Without it the approved posts would stop going out."""
    exp = str((s.get("linkedin") or {}).get("expires") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", exp):
        return []
    left = (dt.date.fromisoformat(exp) - (today or dt.date.today())).days
    if left > 7 or any(b["status"] == "open" and b["title"].startswith(LI_RENEW) for b in s["blockers"]):
        return []
    when = f"scade il {exp[8:10]}/{exp[5:7]}" if left >= 0 else f"è scaduto il {exp[8:10]}/{exp[5:7]}"
    return [add_blocker(s, {"title": f"{LI_RENEW}: il collegamento {when}", "blocks": ["post LinkedIn"], "owner": "human",
                            "how": "Plancia → Impostazioni → Collega LinkedIn (2 minuti). Senza, i post approvati non escono."}, "engine")]


def housekeeping(s: dict, root: str | None = None) -> list[str]:
    """Align stages with the files and refresh s["checks"]. Returns what it changed.
    validating = backtest · building = paper trading · live = approved by the owner (live.json)."""
    root = root or repo_root()
    if not os.path.isdir(os.path.join(root, "products")):
        return []  # not the repo (e.g. plugin copy): never guess
    changed, items = [], []
    for o in s["opportunities"]:
        if o["stage"] == "killed":
            continue
        f = strategy_files(root, o["id"])
        live = is_live(s, o, root)
        if o["stage"] in ("live", "scaling") and not live:
            o["stage"], o["updated"] = ("building" if f["verdict"] == "PASS" else "validating"), now()
            o["next_action"] = "Non è approvata per il live: serve l'ok del proprietario (approvazione channel golive)."
            changed.append(f"{o['id']} non era approvata per il live → {o['stage']}")
        elif live and o["stage"] not in ("live", "scaling"):
            o["stage"], o["updated"] = "live", now()
            changed.append(f"{o['id']} approvata dal proprietario → live")
        elif o["stage"] == "awaiting_approval" and not any(x.get("opportunity") == o["id"] and x["status"] in ("pending", "approved")
                                                           for x in s["approvals"]):
            o["stage"], o["updated"] = ("building" if f["verdict"] == "PASS" else "validating"), now()
            o["next_action"] = "Nessuna richiesta di approvazione aperta: si chiede l'ok con `mm approval` (channel golive)."
            changed.append(f"{o['id']} in attesa di un ok mai chiesto → {o['stage']}")
        elif o["stage"] in ("building", "awaiting_approval") and f["verdict"] == "OLD":
            o["stage"], o["updated"] = "validating", now()
            o["next_action"] = "quant-dev: ripeti il backtest con le regole più severe (1 anno di dati, deve valere il rischio rispetto al buy & hold)."
            changed.append(f"{o['id']} testata con le regole vecchie → di nuovo in backtest")
        elif o["stage"] == "building" and f["verdict"] != "PASS":
            o["stage"], o["updated"] = "validating", now()
            o["next_action"] = "Il paper trading parte solo con un backtest PASS (scripts/backtest.py)."
            changed.append(f"{o['id']} senza backtest PASS → validating")
        if o["stage"] == "validating" and f["verdict"] == "PASS":
            items.append({"kind": "to_paper", "opportunity": o["id"],
                          "text": f"{o['id']} ha un backtest PASS: risk-manager la controlla e poi `mm stage {o['id']} building` (parte il paper trading)"})
        if (o["stage"] == "building" and f["paper_days"] >= PAPER_DAYS_MIN and not _asked(s, "golive", o["id"])):
            items.append({"kind": "unpublished", "opportunity": o["id"],
                          "text": f"{o['id']} è in paper trading da {f['paper_days']:.0f} giorni ({perf_line(f)}): "
                                  "risk-manager decide se proporla per il live (approvazione channel golive) o scartarla"})
    s["checks"] = {"ts": now(), "items": items}
    changed += linkedin_reminder(s)
    for c in changed:
        log(s, "engine", c)
    return changed


def opp_problem(o: dict, old: dict | None) -> str:
    """Why an `mm opp` payload is refused ("" if fine): weak models sometimes send empty shells or made-up stages."""
    if "stage" in o and o["stage"] not in STAGES:
        return f"fase '{o['stage']}' non valida (usa: {', '.join(STAGES)})"
    title = str(o.get("title", old.get("title", "") if old else "")).strip()
    if not title:
        return "serve un titolo che dica cosa si testa, es. \"Trend BTC 50/200\""
    if o.get("id") is not None and not re.fullmatch(r"[A-Za-z0-9_-]{2,60}", str(o["id"])):
        return f"id '{o['id']}' non valido (lettere, numeri, - e _)"
    return ""


def wip_full(s: dict) -> str:
    """Reason why new research/opportunities are refused now, or ""."""
    waiting = [i for i in (s.get("checks") or {}).get("items", []) if i["kind"] in ("unpublished", "to_paper")]
    if waiting:
        return f"{len(waiting)} strategia/e pronte per il passo successivo"
    busy = [o for o in s["opportunities"] if o["stage"] == "validating"]
    if len(busy) >= WIP_MAX:
        return f"{len(busy)} strategie già in backtest (max {WIP_MAX})"
    return ""


def _checks_lines(s: dict) -> list[str]:
    L = []
    items = (s.get("checks") or {}).get("items", [])
    if items:
        L.append("## DA SISTEMARE PRIMA DI TUTTO (controlli automatici)")
        L += [f"- {i['text']}" for i in items[:6]]
    why = wip_full(s)
    if why:
        L.append(f"## LIMITE LAVORI IN CORSO: {why}. Niente market-scanner né nuove strategie: "
                 "porta avanti quelle che ci sono (il motore rifiuta nuovi mercati e opportunità).")
    return L


# ---------------------------------------------------------------- traffic
# The panel counts visits (bots excluded) in memory and restarts from zero on every deploy: we keep the
# latest snapshot of each process ("boot") and sum them, so nothing is counted twice or lost on restart.

TRAFFIC_DAYS = 60


def add_traffic(s: dict, snap: dict) -> str:
    boot = str(snap.get("boot") or "")[:40]
    counts = snap.get("counts") or {}
    if not boot or not isinstance(counts, dict):
        return "traffico: dati non validi"
    clean = {}
    for k, v in list(counts.items())[:5000]:
        if not isinstance(v, dict) or "|" not in str(k):
            continue
        clean[str(k)[:90]] = {"v": max(0, int(v.get("v", 0) or 0)), "c": max(0, int(v.get("c", 0) or 0)),
                              "r": {str(h)[:60]: int(n) for h, n in list((v.get("r") or {}).items())[:30]},
                              "p": {str(h)[:60]: int(n) for h, n in list((v.get("p") or {}).items())[:30]}}
    tr = s.setdefault("traffic", {"boots": {}})
    tr["boots"][boot] = {"seen": now(), "counts": clean}
    cutoff = (dt.date.today() - dt.timedelta(days=TRAFFIC_DAYS)).isoformat()
    for b in list(tr["boots"]):
        cs = {k: v for k, v in tr["boots"][b]["counts"].items() if k.split("|")[0] >= cutoff}
        if cs or b == boot:
            tr["boots"][b]["counts"] = cs
        else:
            del tr["boots"][b]
    return f"traffico: {sum(v['v'] for v in clean.values())} visite, {sum(v['c'] for v in clean.values())} clic dal riavvio della plancia"


def weekly(s: dict, days: int = 7) -> dict:
    """The week in numbers, only from real data: AI spend, cycles, what was done and published, visits,
    sales, and the next move. `prev_*` are the same numbers for the week before, to compare."""
    today_d = dt.date.today()
    start = (today_d - dt.timedelta(days=days - 1)).isoformat()
    prev = (today_d - dt.timedelta(days=2 * days - 1)).isoformat()
    in_week = lambda d: str(d or "")[:10] >= start
    in_prev = lambda d: prev <= str(d or "")[:10] < start
    led = [e for e in s.get("ledger", []) if e.get("type") == "revenue"]
    visits = {"w": [0, 0], "p": [0, 0]}  # [views, clicks]
    for b in (s.get("traffic") or {}).get("boots", {}).values():
        for k, v in b.get("counts", {}).items():
            day = k.split("|", 1)[0]
            slot = "w" if in_week(day) else "p" if in_prev(day) else None
            if slot:
                visits[slot][0] += v.get("v", 0); visits[slot][1] += v.get("c", 0)
    hist = s["budget"].get("usd_by_day") or {}
    reps = [r for r in s.get("reports", []) if in_week(r.get("ts"))]
    done = [{"team": r.get("team", "trading"), "headline": r.get("headline", ""), "ts": r.get("ts")} for r in reps]
    published = [a["title"] for a in s.get("approvals", []) if a.get("status") == "approved" and in_week(a.get("consumed"))
                 and a.get("channel") in ("site", "golive", "stop")]
    last = (s.get("reports") or [{}])[-1]
    return {"from": start, "to": today_d.isoformat(),
            "ai_usd": round(sum(v for d, v in hist.items() if in_week(d)), 2) if hist else round(sum(r.get("usd") or 0 for r in reps), 2),
            "cycles": len(reps), "skipped": sum(1 for l in s.get("log", []) if in_week(l.get("ts")) and ": saltato" in l.get("msg", "")),
            "done": done[-6:], "published": published[-6:],
            "revenue_eur": round(sum(e["amount_eur"] for e in led if in_week(e.get("date"))), 2),
            "sales": sum(1 for e in led if in_week(e.get("date"))),
            "prev_revenue_eur": round(sum(e["amount_eur"] for e in led if in_prev(e.get("date"))), 2),
            "visits": visits["w"][0], "clicks": visits["w"][1], "prev_visits": visits["p"][0],
            "next": (last.get("next") or [None])[0] or "", "needs_you": len([a for a in s.get("approvals", []) if a.get("status") == "pending"])
            + len([b for b in s.get("blockers", []) if b.get("status") == "open" and b.get("owner") != "agent"])}


def traffic_summary(s: dict, days: int = 14) -> list[dict]:
    """Per page: views, clicks to checkout/affiliate links, top referring sites. Busiest first."""
    since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    pages = {}
    for b in (s.get("traffic") or {}).get("boots", {}).values():
        for k, v in b["counts"].items():
            day, page = k.split("|", 1)
            if day < since:
                continue
            p = pages.setdefault(page, {"page": page, "views": 0, "clicks": 0, "refs": {}, "products": {}})
            p["views"] += v["v"]; p["clicks"] += v["c"]
            for h, n in v["r"].items():
                p["refs"][h] = p["refs"].get(h, 0) + n
            for h, n in v["p"].items():
                p["products"][h] = p["products"].get(h, 0) + n
    out = sorted(pages.values(), key=lambda p: -(p["views"] + p["clicks"]))
    for p in out:
        p["refs"] = sorted(p["refs"].items(), key=lambda x: -x[1])[:5]
        p["ctr"] = round(p["clicks"] / p["views"], 3) if p["views"] else None
    return out


def _traffic_lines(s: dict) -> list[str]:
    rows = traffic_summary(s)
    if not (s.get("traffic") or {}).get("boots"):
        return ["## Traffico: non ancora misurato (serve la plancia online; i dati arrivano col workflow)"]
    L = ["## Traffico sito ultimi 14 giorni (visite reali, bot esclusi; clic = link /go/ verso il pagamento)"]
    L += [f"- {r['page']}: {r['views']} visite, {r['clicks']} clic" + (f" ({r['ctr'] * 100:.0f}%)" if r["ctr"] is not None else "")
          + (" · da " + ", ".join(f"{h} {n}" for h, n in r["refs"]) if r["refs"] else "") for r in rows[:8]]
    if not rows:
        L.append("- nessuna visita: il problema è farsi trovare, non la pagina")
    return L


def _read_json(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _focus_and_learnings(s: dict) -> list[str]:
    L = []
    if s.get("focus"):
        L.append(f"## FOCUS del proprietario: lavora solo su {', '.join(s['focus']['strategies'])}")
    if s.get("learnings"):
        L.append("## Lezioni imparate (non ripetere gli errori; aggiungi con `learn \"...\"`)")
        L += [f"- {x['text']}" for x in s["learnings"][-6:]]
    return L


def growth_brief(s: dict, root: str | None = None) -> str:
    """Compact context for the yield team (yield-lead): staking/yield research, airdrops, owner portfolio, results."""
    roll_day(s)
    root = root or os.getcwd()
    b, k = s["budget"], kpis(s)
    L = [f"# BRIEF RENDITE · {now()}",
         f"stato={s['status']} · budget oggi {b['usd_today']:.2f}/{effective_day(s):.2f}${saver_note(s)} · ciclo max {cycle_cap(s):.2f}$",
         f"KPI risultati reali={k['revenue_eur']}€ perdite/costi={k['cost_eur']}€ AI={k['ai_cost_eur']}€ netto={k['net_eur']}€"]
    if s["directives"]:
        L.append("## DIRETTIVE UMANE (priorità massima)")
        L += [f"- [{d['id']}] {d['text']}" for d in s["directives"]]
    L += _focus_and_learnings(s)
    paused = [n for n, a in s["agents"].items() if a["status"] != "active"]
    if paused:
        L.append(f"## Agenti in pausa (NON usarli): {', '.join(paused)}")
    yj = _read_json(os.path.join(root, "state", "market", "yields.json"))
    if yj:
        L.append(f"## Rendimenti dai dati pubblici (DefiLlama, {yj.get('date')}, filtri prudenti; dettagli in state/research/yields-*.md)")
        for key, name in (("stable", "stable"), ("majors", "crypto principali")):
            L += [f"- [{name}] {r['project']} {r['chain']} {r['symbol']} APY30g {r['apy_30d']}% (premi {r.get('apy_reward') or 0}%) TVL {r['tvl_musd']}M$"
                  for r in (yj.get(key) or [])[:4]]
    else:
        L.append("## Rendimenti: nessun dato ancora (scripts/yields.py gira nel workflow prima del ciclo)")
    L.append("## Strategie del team trading (solo per contesto: non toccarle)")
    act = [o for o in s["opportunities"] if o["stage"] in ("building", "live", "scaling")]
    L += [f"- {o['id']} [{STAGE_NAME.get(o['stage'], o['stage'])}] {o['title'][:60]} · {perf_line(strategy_files(root, o['id']))}" for o in act[:5]] or ["- nessuna in paper trading o live"]
    led = [e for e in s["ledger"] if e.get("kind") in ("staking", "airdrop")]
    L.append(f"## Risultati reali di staking/airdrop registrati dal proprietario: {len(led)} voci, "
             f"{sum(e['amount_eur'] if e['type'] == 'revenue' else -e['amount_eur'] for e in led):.2f}€")
    pend = [a for a in s["approvals"] if a["status"] == "pending"]
    if pend:
        L.append(f"## In attesa di approvazione ({len(pend)}) — non ripetere richieste")
        L += [f"- {a['id']} [{a.get('channel') or a['kind']}] {a['title']}" for a in pend[:8]]
    decided = [a for a in s["approvals"] if a["status"] in ("approved", "rejected") and not a.get("consumed") and a.get("by") in TEAM_AGENTS["rendite"]]
    if decided:
        L.append("## Decisioni del proprietario (prendine atto e archivia con `consume <id>`)")
        L += [f"- {a['id']} {a['status'].upper()} {a['title']} {a.get('note', '')}" for a in decided[:5]]
    opn = [x for x in s["blockers"] if x["status"] == "open"]
    if opn:
        L.append("## Blocchi aperti")
        L += [f"- {x['id']} [{'umano' if x['owner'] == 'human' else 'agenti'}] {x['title'][:90]}" for x in opn[:8]]
    res = os.path.join(root, "state", "research")
    notes = sorted(n for n in os.listdir(res) if n.startswith(("yield", "staking", "airdrop", "portfolio"))) if os.path.isdir(res) else []
    if notes:
        L.append("## Note di ricerca del team: " + ", ".join(notes[-8:]))
    team = TEAM_AGENTS["rendite"]
    recent = [l for l in s["log"] if l["agent"] in team][-5:]
    if recent:
        L.append("## Ultimi eventi del team rendite")
        L += [f"- {l['ts'][5:16]} {l['agent']}: {l['msg'][:110]}" for l in recent]
    return "\n".join(L)


def social_drafts(root: str) -> list[dict]:
    """Posts prepared by the social team: products/<id>/social/<YYYY-MM-DD>-<platform>/POST.md (+ images)."""
    out, base = [], os.path.join(root, "products")
    if not os.path.isdir(base):
        return out
    for opp in sorted(os.listdir(base)):
        sd = os.path.join(base, opp, "social")
        if not os.path.isdir(sd):
            continue
        for d in sorted(os.listdir(sd)):
            m = re.match(r"(\d{4}-\d{2}-\d{2})-([a-z]+)", d)
            if m and os.path.isfile(os.path.join(sd, d, "POST.md")):
                imgs = [f for f in os.listdir(os.path.join(sd, d)) if f.lower().endswith((".png", ".jpg", ".jpeg"))]
                out.append({"opp": opp, "dir": f"products/{opp}/social/{d}", "date": m.group(1), "platform": m.group(2),
                            "images": sum(1 for f in imgs if f.startswith("slide-"))})
    return out


def social_brief(s: dict, root: str | None = None) -> str:
    """Compact context for the social team (social-lead): strategies with real results, what was already prepared, what the owner published."""
    roll_day(s)
    root = root or os.getcwd()
    b, k = s["budget"], kpis(s)
    site_url = os.environ.get("MM_SITE_URL", "").rstrip("/")
    week = (dt.date.today() - dt.timedelta(days=6)).isoformat()
    drafts = social_drafts(root)
    this_week = [d for d in drafts if d["date"] >= week]
    L = [f"# BRIEF SOCIAL · {now()}",
         f"stato={s['status']} · budget oggi {b['usd_today']:.2f}/{effective_day(s):.2f}${saver_note(s)} · ciclo max {cycle_cap(s):.2f}$",
         f"KPI ricavi={k['revenue_eur']}€ · sito: {site_url + '/s/' if site_url else 'MM_SITE_URL non impostato'}",
         f"Post preparati negli ultimi 7 giorni: {len(this_week)}/{SOCIAL_PER_WEEK}"
         + (" → LIMITE RAGGIUNTO: niente post nuovi, al massimo migliora quelli ancora da pubblicare" if len(this_week) >= SOCIAL_PER_WEEK else "")]
    todo_open = [x for x in s["blockers"] if x["status"] == "open" and x.get("by") in TEAM_AGENTS["social"]]
    incomplete = [d for d in drafts if not d["images"]]
    if incomplete:
        L.append("## DA COMPLETARE PRIMA DI TUTTO (post senza immagini: visual-designer, poi ethics-guard, poi il blocco)")
        for d in incomplete:
            stale = next((x for x in todo_open if d["dir"] in x.get("how", "")), None)
            L.append(f"- {d['dir']}/ · manca slide-NN.png" + (f" · il blocco {stale['id']} va AGGIORNATO: stesso titolo con `mm blocker`, how corretto" if stale else ""))
    if s["directives"]:
        L.append("## DIRETTIVE UMANE (priorità massima)")
        L += [f"- [{d['id']}] {d['text']}" for d in s["directives"]]
    L += _focus_and_learnings(s)
    paused = [n for n, a in s["agents"].items() if a["status"] != "active"]
    if paused:
        L.append(f"## Agenti in pausa (NON usarli): {', '.join(paused)}")
    L.append("## Strategie di cui si può parlare (solo risultati veri, sempre \"non è un consiglio finanziario\")")
    live = [o for o in s["opportunities"] if o["stage"] in ("building", "live", "scaling")]
    for o in live:
        media = os.path.join(root, "products", o["id"], "media")
        imgs = sorted(f for f in os.listdir(media) if f.lower().endswith(".png")) if os.path.isdir(media) else []
        mine = [d for d in drafts if d["opp"] == o["id"]]
        L.append(f"- {o['id']} [{STAGE_NAME.get(o['stage'], o['stage'])}] {o['title'][:70]} · {perf_line(strategy_files(root, o['id']))}"
                 f" · grafici veri: {len(imgs)} in products/{o['id']}/media/ · post già preparati: {len(mine)}"
                 + (f" (ultimo {mine[-1]['date']} {mine[-1]['platform']})" if mine else ""))
    if not live:
        L.append("- nessuna: senza strategie in paper trading o live non si prepara nessun post. Chiudi il ciclo.")
    team = TEAM_AGENTS["social"]
    todo = [x for x in s["blockers"] if x["status"] == "open" and x.get("by") in team]
    todo += [a for a in s["approvals"] if a.get("channel") == "linkedin" and (a["status"] == "pending" or (a["status"] == "approved" and not a.get("consumed")))]
    if todo:
        L.append(f"## Post pronti che il proprietario deve ancora pubblicare ({len(todo)}) — non prepararne altri uguali")
        L += [f"- {x['id']} {x['title'][:90]}" for x in todo[:8]]
    if os.environ.get("MM_LINKEDIN") == "true":
        L.append("## LinkedIn COLLEGATO: per i post LinkedIn NON aprire il blocco; chiedi l'approvazione e alla conferma "
                 "la macchina li pubblica da sola sul profilo del proprietario:")
        L.append('`mm approval \'{"kind":"publish","channel":"linkedin","target":"products/<id>/social/<cartella>","opportunity":"<id>",'
                 '"title":"Pubblica su LinkedIn: <di cosa parla il post>","detail":"<prime righe del testo>"}\' --agent social-lead`')
    since = (dt.date.today() - dt.timedelta(days=30)).isoformat()
    done = [x for x in s["blockers"] if x["status"] == "done" and x.get("by") in team and str(x.get("resolved") or "") >= since]
    done += [a for a in s["approvals"] if a.get("channel") == "linkedin" and a.get("consumed") and str(a.get("resolved") or "") >= since]
    L.append(f"## Pubblicati dal proprietario negli ultimi 30 giorni: {len(done)}")
    L += [f"- {x['title'][:90]}" for x in done[-5:]]
    L += _traffic_lines(s)
    recent = [l for l in s["log"] if l["agent"] in team][-5:]
    if recent:
        L.append("## Ultimi eventi del team social")
        L += [f"- {l['ts'][5:16]} {l['agent']}: {l['msg'][:110]}" for l in recent]
    return "\n".join(L)


# ---------------------------------------------------------------- CLI

def parse_json(txt: str) -> dict:
    if txt == "-":
        txt = sys.stdin.read()
    return json.loads(txt)


def main(argv=None):
    p = argparse.ArgumentParser(prog="mm", description="Crypto Machine engine")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("brief")
    sub.add_parser("growth-brief", help="contesto compatto per il team vendite")
    sub.add_parser("social-brief", help="contesto compatto per il team social")
    sub.add_parser("kpis")
    sp = sub.add_parser("signal", help="segnale di una strategia live per il proprietario (lo scrive scripts/paper.py)")
    sp.add_argument("json")
    sub.add_parser("apply", help="consuma i comandi in inbox")
    sp = sub.add_parser("allocate"); sp.add_argument("-k", type=int, default=0)
    sp = sub.add_parser("can-run", help="exit 0 se stato=running, budget disponibile e c'è qualcosa da fare")
    sp.add_argument("--team", default="trading", choices=TEAMS)
    sp.add_argument("--force", action="store_true", help="non saltare anche se non c'è niente di nuovo")
    sp = sub.add_parser("learn", help="registra una lezione imparata (cosa vende, cosa è fallito, regole)")
    sp.add_argument("text"); sp.add_argument("--agent", default="ceo")
    sub.add_parser("cycle-cap", help="tetto di spesa del prossimo ciclo in $")
    sp = sub.add_parser("begin-cycle")
    sp = sub.add_parser("end-cycle"); sp.add_argument("--summary", default="")
    sp = sub.add_parser("live", help="vista in tempo reale per l'ufficio 3D")
    sp.add_argument("action", choices=["begin", "end", "hook", "show"])
    sp.add_argument("--run", default=""); sp.add_argument("--url", default=""); sp.add_argument("--result", default="ok")
    sp.add_argument("--team", default="trading", choices=TEAMS)
    sp = sub.add_parser("report", help="resoconto del CEO per il proprietario; chiude il ciclo")
    sp.add_argument("json", help='{"headline","done":[],"next":[],"needs_you":[]} o \'-\' per stdin')
    sp = sub.add_parser("traffic", help="registra i conteggi di /api/traffic della plancia (JSON o '-')")
    sp.add_argument("json")
    for name in ("market", "opp", "approval", "ledger", "enqueue"):
        sp = sub.add_parser(name); sp.add_argument("json", help="oggetto JSON o '-' per stdin")
        sp.add_argument("--agent", default="ceo")
    sp = sub.add_parser("blocker", help="apre un blocco: cosa impedisce di incassare e cosa blocca")
    sp.add_argument("json", help='{"title","blocks":["opp_x"],"owner":"human|agent","how","link"}'); sp.add_argument("--agent", default="ceo")
    sp = sub.add_parser("unblock", help="segna un blocco come risolto"); sp.add_argument("id"); sp.add_argument("--agent", default="ceo")
    sp = sub.add_parser("stage"); sp.add_argument("id"); sp.add_argument("stage", choices=STAGES)
    sp.add_argument("--next", default=None); sp.add_argument("--agent", default="ceo")
    sp = sub.add_parser("consume", help="archivia una decisione umana già eseguita"); sp.add_argument("id")
    sp = sub.add_parser("notified", help="ricorda cosa è già stato avvisato su Telegram (JSON: ts, sent, chat_id, week, traffic)"); sp.add_argument("json")
    sp = sub.add_parser("fisco", help="totali dell'anno solare per la dichiarazione"); sp.add_argument("--year", type=int)
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("log"); sp.add_argument("agent"); sp.add_argument("msg")
    sp = sub.add_parser("usage", help="registra costo AI"); sp.add_argument("--usd", type=float, required=True)
    sp.add_argument("--tokens", type=int, default=0); sp.add_argument("--agent", default="ceo")
    sp = sub.add_parser("export", help="snapshot per la plancia statica"); sp.add_argument("dir")
    sp.add_argument("--repo", default="")
    sp = sub.add_parser("usage-from-result", help="legge il JSON di `claude -p --output-format json`")
    sp.add_argument("file")
    a = p.parse_args(argv)

    if a.cmd == "live":  # separate file, no state lock needed; hooks must never fail
        try:
            if a.action == "begin":
                live_begin(a.run, a.url, a.team)
            elif a.action == "end":
                live_end(a.result)
            elif a.action == "hook":
                live_hook(json.loads(sys.stdin.read() or "{}"))
            else:
                print(json.dumps(live_load(), ensure_ascii=False))
        except Exception as e:
            print(f"live: {e}", file=sys.stderr)
        return 0

    if a.cmd == "enqueue":
        print(json.dumps(enqueue(parse_json(a.json)), ensure_ascii=False))
        return 0

    with locked():
        s = load()
        roll_day(s)
        out, rc = None, 0

        if a.cmd == "init":
            out = f"stato in {STATE_FILE}"
        elif a.cmd == "brief":
            out = brief(s)
        elif a.cmd == "growth-brief":
            housekeeping(s)
            out = growth_brief(s)
            log(s, "engine", "inizio ciclo vendite")
        elif a.cmd == "social-brief":
            housekeeping(s)
            out = social_brief(s)
            log(s, "engine", "inizio ciclo social")
        elif a.cmd == "signal":
            out = add_signal(s, parse_json(a.json))
        elif a.cmd == "kpis":
            out = json.dumps(kpis(s), ensure_ascii=False)
        elif a.cmd == "apply":
            out = "\n".join(drain_inbox(s) + housekeeping(s)) or "inbox vuota"
        elif a.cmd == "allocate":
            out = json.dumps(allocate(s, a.k), ensure_ascii=False)
        elif a.cmd == "can-run":
            b = s["budget"]
            why = "" if a.force else should_skip(s, a.team)
            if s["status"] != "running":
                out, rc = "PAUSED", 1
            elif cycle_cap(s) < MIN_CYCLE_USD:
                out, rc = f"BUDGET esaurito ({b['usd_today']:.2f}/{effective_day(s):.2f}$){saver_note(s)}", 1
            elif why:
                s["skips"][a.team] = s["skips"].get(a.team, 0) + 1
                out, rc = f"NIENTE DA FARE: {why}", 1
            else:
                s["skips"][a.team] = 0
                s["last_run"][a.team] = now()
                out = f"OK residuo {b['usd_per_day'] - b['usd_today']:.2f}$, tetto ciclo {cycle_cap(s):.2f}$"
        elif a.cmd == "cycle-cap":
            out = f"{cycle_cap(s):.4f}"
        elif a.cmd == "begin-cycle":
            housekeeping(s)
            chosen = allocate(s, 2)
            live_begin()
            out = brief(s, chosen)
            s["cycle"] += 1
            for r in chosen:
                s["strategies"][r["strategy"]]["pulls"] += 1
            log(s, "engine", f"inizio ciclo {s['cycle']}")
        elif a.cmd == "end-cycle":
            s["last_cycle"] = now()
            if a.summary.startswith("saltato"):
                s["last_skip"] = {"ts": now(), "reason": a.summary[len("saltato"):].lstrip(": ")[:200]}
            log(s, "ceo", f"fine ciclo {s['cycle']}: {a.summary}")
            out = "ok"
        elif a.cmd == "report":
            try:
                rep = make_report(s, parse_json(a.json))
            except (ValueError, json.JSONDecodeError) as e:
                out, rc = f"report non valido: {e}", 1
            else:
                s["last_cycle"] = now()
                log(s, TEAM_HEAD.get(rep["team"], "ceo"), f"fine ciclo {s['cycle']}: {rep['headline']}")
                live_update(lambda L: L.update(report=rep["headline"]))
                out = "ok"
        elif a.cmd == "market":
            m = parse_json(a.json)
            m.setdefault("id", new_id("mkt"))
            old = find(s["markets"], m["id"]) or next((x for x in s["markets"] if x["name"].lower() == str(m.get("name", "")).lower()), None)
            if not old and a.agent != "human" and wip_full(s):
                out, rc = f"RIFIUTATO: limite lavori in corso ({wip_full(s)}). Prima porta avanti le strategie che ci sono.", 1
            else:
                if old:
                    old.update({k: v for k, v in m.items() if k != "id"}); m = old
                else:
                    s["markets"].append(m)
                m["score"], m["updated"] = market_score(m), now()
                log(s, a.agent, f"mercato {m['name']} score={m['score']}")
                out = json.dumps({"id": m["id"], "score": m["score"]})
        elif a.cmd == "opp":
            o = parse_json(a.json)
            old = find(s["opportunities"], o.get("id", ""))
            bad = opp_problem(o, old)
            parent = find(s["opportunities"], str(o.get("variant_of") or ""))
            lite = bool(parent and parent["stage"] in ("live", "scaling"))  # variant of a live strategy (new parameters/pair)
            if bad:
                out, rc = f"RIFIUTATO: {bad}", 1
            elif not old and a.agent != "human" and not lite and wip_full(s):
                out, rc = f"RIFIUTATO: limite lavori in corso ({wip_full(s)}). Prima porta avanti le strategie che ci sono.", 1
            else:
                if old:
                    old.update(o); o = old
                else:
                    o.setdefault("id", new_id("opp")); o.setdefault("stage", "idea"); o["created"] = now()
                    s["opportunities"].append(o)
                if o.get("strategy") not in s["strategies"]:
                    o["strategy"] = "trend-following"
                o["score"], o["updated"] = opp_score(o), now()
                log(s, a.agent, f"opportunità {o['id']} '{o.get('title', '')[:60]}' score={o['score']} [{o['stage']}]")
                out = json.dumps({"id": o["id"], "score": o["score"], "stage": o["stage"]})
        elif a.cmd == "approval":
            ap = ap_in = parse_json(a.json)
            dup = next((x for x in s["approvals"] if x["status"] == "pending" and x["title"] == ap.get("title")), None)
            if dup:
                out = json.dumps({"id": dup["id"], "duplicate": True})
            else:
                ap = {"id": new_id("apr"), "kind": ap.get("kind", "action"), "title": str(ap.get("title", ""))[:160],
                      "detail": str(ap.get("detail", ""))[:3000], "opportunity": ap.get("opportunity"),
                      "cost_eur": float(ap.get("cost_eur", 0)), "ethics": ap.get("ethics", ""),
                      "status": "pending", "created": now(), "by": a.agent}
                if ap_in.get("channel"):  # e.g. "golive": executed automatically once approved
                    ap["channel"] = str(ap_in["channel"])[:40]
                if ap_in.get("target"):  # e.g. the site page slug for channel "site"
                    ap["target"] = str(ap_in["target"])[:80]
                if ap_in.get("capital_eur") is not None:  # "golive": max real capital the owner puts on it
                    ap["capital_eur"] = max(0.0, float(ap_in["capital_eur"]))
                s["approvals"].append(ap)
                o = find(s["opportunities"], ap["opportunity"] or "")
                if o and o["stage"] in ("idea", "validating", "building"):
                    o["stage"] = "awaiting_approval"
                log(s, a.agent, f"richiesta approvazione {ap['id']}: {ap['title']}")
                out = json.dumps({"id": ap["id"]})
        elif a.cmd == "ledger":
            out = add_ledger(s, parse_json(a.json), a.agent); log(s, a.agent, out)
        elif a.cmd == "stage":
            o = find(s["opportunities"], a.id)
            if not o:
                out, rc = "opportunità non trovata", 1
            else:
                o["stage"], o["updated"] = a.stage, now()
                if a.next is not None:
                    o["next_action"] = a.next
                log(s, a.agent, f"{o['id']} → {a.stage}")
                out = "ok"
        elif a.cmd == "export":
            os.makedirs(a.dir, exist_ok=True)
            snap = dict(s, _kpis=kpis(s), _allocation=allocate(s, 0))
            with open(os.path.join(a.dir, "state.json"), "w", encoding="utf-8") as f:
                json.dump(snap, f, ensure_ascii=False)
            with open(os.path.join(a.dir, "config.json"), "w", encoding="utf-8") as f:
                json.dump({"repo": a.repo}, f)
            out = f"esportato in {a.dir}"
        elif a.cmd == "blocker":
            out = add_blocker(s, parse_json(a.json), a.agent); log(s, a.agent, out)
        elif a.cmd == "unblock":
            out = set_blocker(s, a.id, "done", a.agent); log(s, a.agent, out)
        elif a.cmd == "traffic":
            out = add_traffic(s, parse_json(a.json))
        elif a.cmd == "learn":
            out = add_learning(s, a.text, a.agent)
            if out.startswith("lezione registrata"):
                log(s, a.agent, out)
        elif a.cmd == "fisco":
            f = fiscal_year(s, a.year)
            out = json.dumps(f, ensure_ascii=False) if a.json else fiscal_text(f)
        elif a.cmd == "notified":
            d, t = parse_json(a.json), s.setdefault("notify", {}).setdefault("telegram", {})
            if d.get("ts"):
                t["ts"] = str(d["ts"])[:40]
            if isinstance(d.get("sent"), list):
                t["sent"] = [str(x)[:40] for x in d["sent"]][-200:]  # ids of approvals/blocks already announced
            if d.get("chat_id"):
                t["chat_id"] = str(d["chat_id"])[:40]
            if d.get("week"):
                t["week"] = str(d["week"])[:10]
            if isinstance(d.get("traffic"), dict):  # site counts already announced (buy clicks, visits from socials)
                t["traffic"] = {k: {str(kk)[:160]: int(v) for kk, v in list((d["traffic"].get(k) or {}).items())[-400:]
                                    if isinstance(v, (int, float))} for k in ("clicks", "social")}
            out = "ok"
        elif a.cmd == "consume":
            ap = find(s["approvals"], a.id)
            if ap:
                ap["consumed"] = now()
            out = "ok" if ap else "non trovata"
        elif a.cmd == "log":
            if a.agent in s["agents"]:
                ag = s["agents"][a.agent]; ag["runs"] += 1; ag["last_run"] = now()
            log(s, a.agent, a.msg); out = "ok"
        elif a.cmd in ("usage", "usage-from-result"):
            if a.cmd == "usage":
                usd, tok, agent = a.usd, a.tokens, a.agent
            else:
                usd, tok, agent, res = 0.0, 0, "ceo", {}
                try:
                    with open(a.file, encoding="utf-8") as f:
                        txt = f.read().strip()
                    res = json.loads(txt.splitlines()[-1] if not txt.startswith("{") else txt)
                    if isinstance(res, list):
                        res = next((r for r in reversed(res) if r.get("type") == "result"), {})
                    usd = float(res.get("total_cost_usd", 0) or 0)
                    u = res.get("usage", {}) or {}
                    tok = sum(int(u.get(x, 0) or 0) for x in ("input_tokens", "output_tokens",
                              "cache_creation_input_tokens", "cache_read_input_tokens"))
                    if res.get("modelUsage"):  # "usage" leaves out the sub-agents; modelUsage covers the whole tree
                        tok = sum(int(mu.get(x, 0) or 0) for mu in res["modelUsage"].values() for x in
                                  ("inputTokens", "outputTokens", "cacheCreationInputTokens", "cacheReadInputTokens"))
                except Exception as e:
                    print(f"usage non leggibile: {e}", file=sys.stderr)
            if s["reports"] and s["reports"][-1]["cycle"] == s["cycle"] and s["reports"][-1]["usd"] is None:
                s["reports"][-1]["usd"] = round(usd, 4)
            b = s["budget"]
            b["usd_today"] = round(b["usd_today"] + usd, 4)
            b["usd_total"] = round(b["usd_total"] + usd, 4)
            hist = b.setdefault("usd_by_day", {})  # daily AI spend, for the weekly summary (last 60 days)
            hist[today()] = round(hist.get(today(), 0) + usd, 4)
            for d in sorted(hist)[:-60]:
                del hist[d]
            b["tokens_total"] += tok
            if a.cmd == "usage-from-result":
                L = live_load() or {}
                head = TEAM_HEAD.get(L.get("team"), "ceo")
                usage = L.get("usage") or {}
                split = split_cost(usd, res.get("modelUsage") or {}, usage, head)
                for name in set(split) | set(usage) | {head}:
                    if name in s["agents"]:
                        ag = s["agents"][name]
                        ag["usd"] = round(ag["usd"] + split.get(name, 0), 4)
                        ag["runs"] += usage.get(name, {}).get("runs", 0) + (1 if name == head else 0)
                        ag["last_run"] = now()
                parts = ", ".join(f"{k} {v:.2f}$" for k, v in sorted(split.items(), key=lambda x: -x[1]))
                log(s, "engine", f"costo AI {usd:.4f}$ / {tok} token" + (f" ({parts})" if parts else ""))
            else:
                if agent in s["agents"]:
                    s["agents"][agent]["usd"] = round(s["agents"][agent]["usd"] + usd, 4)
                log(s, "engine", f"costo AI {usd:.4f}$ / {tok} token")
            out = f"{usd:.4f}$"
        save(s)
    if out is not None:
        print(out)
    return rc


if __name__ == "__main__":
    sys.exit(main())
