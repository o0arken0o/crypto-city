#!/usr/bin/env python3
"""Adaptive AI Orchestrator: discovery, routing, health, quotas and learning."""
from __future__ import annotations
import json, os, re, time, urllib.error, urllib.request
from dataclasses import dataclass

@dataclass
class Model:
    provider: str
    id: str
    score: float
    context: int = 0
    capabilities: tuple = ()
    free: bool = False

class AIError(RuntimeError):
    def __init__(self, msg, status=None, retryable=False, headers=None):
        super().__init__(msg)
        self.status = status
        self.retryable = retryable
        self.headers = headers or {}

PROVIDERS = {
 "openai": ("OPENAI_API_KEY", "https://api.openai.com/v1", "openai"),
 "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1", "openai"),
 "cerebras": ("CEREBRAS_API_KEY", "https://api.cerebras.ai/v1", "openai"),
 "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1", "openai"),
 "gemini": ("GEMINI_API_KEY", "https://generativelanguage.googleapis.com/v1beta/openai", "openai"),
 "together": ("TOGETHER_API_KEY", "https://api.together.xyz/v1", "openai"),
 "mistral": ("MISTRAL_API_KEY", "https://api.mistral.ai/v1", "openai"),
 "deepseek": ("DEEPSEEK_API_KEY", "https://api.deepseek.com/v1", "openai"),
 "xai": ("XAI_API_KEY", "https://api.x.ai/v1", "openai"),
 "anthropic": ("ANTHROPIC_API_KEY", "https://api.anthropic.com", "anthropic"),
}
FREE_PROVIDERS = {"groq", "cerebras", "gemini", "openrouter"}
PATTERNS = [
 (r"opus|max|pro|reason|o[1-9]|gpt-5.*sol|gemini-.*pro", 100),
 (r"sonnet|gpt-5|terra|gemini-.*flash", 82),
 (r"120b|70b|72b|32b|27b|r1|reasoner", 72),
 (r"haiku|mini|flash-lite|8b|20b", 38),
]

def _keys(env):
    out = []
    for n in (env, *[f"{env}_{i}" for i in range(1, 21)]):
        k = os.getenv(n, "").strip()
        if k and k not in out:
            out.append(k)
    return out

def _score(mid, ctx=0):
    s, model_id = 10.0, mid.lower()
    for p, v in PATTERNS:
        if re.search(p, model_id):
            s = max(s, v)
    s += min(20, ctx / 100000)
    if any(kind in model_id for kind in ("embedding", "whisper", "tts", "image", "moderation", "guard")):
        s = -100
    return s

def _json(url, key, method="GET", body=None, headers=None):
    h = {"Authorization": "Bearer " + key, "Content-Type": "application/json",
         "User-Agent": "crypto-machine-orchestrator/2"}
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(
            url, data=json.dumps(body).encode() if body is not None else None,
            headers=h, method=method)
        with urllib.request.urlopen(req, timeout=float(os.getenv("MM_AI_TIMEOUT", "90"))) as r:
            return r.status, json.loads(r.read().decode("utf8", "replace") or "{}"), dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf8", "replace")
        try:
            d = json.loads(raw)
        except Exception:
            d = {}
        msg = (d.get("error") or {}).get("message") or raw[:500] or str(e)
        raise AIError(msg, e.code,
                      e.code in (408, 409, 425, 429) or e.code >= 500,
                      dict(e.headers or {}))
    except (urllib.error.URLError, TimeoutError) as e:
        raise AIError(str(e), None, True)

def _header(headers, *names):
    low = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    for n in names:
        if n.lower() in low:
            return low[n.lower()]
    return None

def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

class Orchestrator:
    def __init__(self):
        self.providers = {}
        self.catalog = []
        self.health = {}
        self.events = []
        self.state_path = os.getenv("MM_STATE_FILE", ".crypto-machine/orchestrator_state.json")
        self.state = self._load_state()
        self.refresh()

    def _load_state(self):
        if os.getenv("MM_PERSIST_STATE", "1").lower() in ("0", "false", "no"):
            return {"providers": {}, "models": {}}
        try:
            with open(self.state_path, "r", encoding="utf8") as f:
                data = json.load(f)
            return {"providers": data.get("providers", {}), "models": data.get("models", {})}
        except (OSError, ValueError, TypeError):
            return {"providers": {}, "models": {}}

    def _save_state(self):
        if os.getenv("MM_PERSIST_STATE", "1").lower() in ("0", "false", "no"):
            return
        directory = os.path.dirname(self.state_path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(self.state, f, separators=(",", ":"), sort_keys=True)
        os.replace(tmp, self.state_path)

    def _event(self, kind, **data):
        self.events.append({"ts": time.time(), "event": kind, **data})
        self.events = self.events[-100:]

    def _provider_health(self, provider):
        h = self.health.setdefault(provider, {
            "success": 0, "failure": 0, "cooldown_until": 0,
            "latency_ms": 0, "quota": {}
        })
        persisted = self.state["providers"].get(provider, {})
        for k in ("success", "failure", "latency_ms"):
            if persisted.get(k) is not None and not h.get(k):
                h[k] = persisted[k]
        return h

    def _model_stats(self, provider, model):
        key = provider + "/" + model
        return self.state["models"].setdefault(key, {
            "success": 0, "failure": 0, "latency_ms": 0,
            "prompt_tokens": 0, "completion_tokens": 0
        })

    def _record_quota(self, provider, key_index, headers):
        h = self._provider_health(provider)
        quota = h.setdefault("quota", {})
        provider_state = self.state["providers"].setdefault(provider, {})
        by_key = provider_state.setdefault("quota_by_key", {})
        key_quota = by_key.setdefault(str(key_index), {})
        names = {
            "requests_remaining": ("x-ratelimit-remaining-requests", "x-ratelimit-remaining-request"),
            "tokens_remaining": ("x-ratelimit-remaining-tokens",),
            "requests_reset": ("x-ratelimit-reset-requests",),
            "tokens_reset": ("x-ratelimit-reset-tokens",),
            "retry_after": ("retry-after",),
        }
        for field, candidates in names.items():
            value = _header(headers, *candidates)
            if value is not None:
                n = _number(value)
                quota[field] = n if n is not None else value
                key_quota[field] = quota[field]
        if quota:
            quota["key_index"] = key_index
            quota["observed_at"] = time.time()
            key_quota["observed_at"] = quota["observed_at"]
        return key_quota

    def _quota_ok(self, provider, key_index):
        quota = (self.state["providers"].get(provider, {})
                 .get("quota_by_key", {}).get(str(key_index), {}))
        for field in ("requests_remaining", "tokens_remaining"):
            value = quota.get(field)
            if isinstance(value, (int, float)) and value <= 0:
                return False
        return True

    def refresh(self):
        self.providers = {}
        self.catalog = []
        for name, (env, base, kind) in PROVIDERS.items():
            keys = _keys(env)
            if not keys:
                continue
            self.providers[name] = {"env": env, "base": base.rstrip("/"),
                                    "kind": kind, "keys": keys}
            self._provider_health(name)
            for ki, key in enumerate(keys):
                try:
                    if kind == "anthropic":
                        _, data, headers = _json(
                            base + "/v1/models?limit=1000", key,
                            headers={"anthropic-version": "2023-06-01"})
                    else:
                        _, data, headers = _json(base + "/models", key)
                    self._record_quota(name, ki, headers)
                    for row in data.get("data", []):
                        mid = str(row.get("id", ""))
                        if not mid:
                            continue
                        ctx = int(row.get("context_length") or row.get("context_window") or 0)
                        caps = tuple(row.get("capabilities") or ("tools",))
                        self.catalog.append(
                            (Model(name, mid, _score(mid, ctx), ctx, caps,
                                   name in FREE_PROVIDERS), ki))
                except AIError as e:
                    self._record_quota(name, ki, e.headers)
                    self._event("discovery_error", provider=name, key=ki, status=e.status)
        self._save_state()

    def available(self):
        return sorted({(m.provider, m.id): m for m, _ in self.catalog}.values(),
                      key=lambda m: -m.score)

    def _budget_ok(self, provider):
        budget = os.getenv("MM_PROVIDER_BUDGET_USD_" + provider.upper(), "")
        try:
            used = float(os.getenv("MM_PROVIDER_USED_USD_" + provider.upper(), "0") or 0)
            return not budget or used < float(budget)
        except ValueError:
            return False

    def _eligible(self, m, ki, failed, tier):
        thresholds = {1: 0, 2: 38, 3: 72, 4: 95}
        h = self._provider_health(m.provider)
        if m.score < thresholds.get(tier, 38) or (m.provider, m.id, ki) in failed:
            return False
        key_cooldown = self.state.get("providers", {}).get(
            m.provider, {}).get("key_cooldowns", {}).get(str(ki), 0)
        # Cooldowns are tracked per key; a 429 on key N must not block sibling keys.
        if float(key_cooldown or 0) > time.time():
            return False
        if not self._quota_ok(m.provider, ki) or not self._budget_ok(m.provider):
            return False
        if os.getenv("MM_FREE_ONLY", "").lower() in ("1", "true", "yes") and not m.free:
            return False
        return True

    def candidates(self, task="general", tier=2, failed=None):
        failed = set(failed or [])
        rows = [(m, k) for m, k in self.catalog if self._eligible(m, k, failed, tier)]
        order = [x.strip() for x in os.getenv(
            "MM_PROVIDER_ORDER",
            "groq,anthropic,openai,gemini,cerebras,openrouter,together,mistral,deepseek,xai"
        ).split(",")]
        rank = {p: i for i, p in enumerate(order)}
        boost = {"reasoning": 12, "coding": 10, "research": 8, "planning": 10,
                 "general": 0, "social": -5, "classification": -10}.get(task, 0)

        def route_score(row):
            m, _ = row
            stats = self._model_stats(m.provider, m.id)
            reliability = (stats["success"] + 1) / (stats["success"] + stats["failure"] + 2)
            latency = float(stats.get("latency_ms") or 0)
            latency_penalty = min(15, latency / 1000)
            return m.score + boost + reliability * 8 - latency_penalty

        rows.sort(key=lambda x: (-route_score(x), rank.get(x[0].provider, 999), x[1]))
        return rows

    def _remember(self, m, ki, success, latency_ms, usage):
        h = self._provider_health(m.provider)
        stats = self._model_stats(m.provider, m.id)
        key = str(ki)
        providers = self.state["providers"].setdefault(m.provider, {})
        cooldowns = providers.setdefault("key_cooldowns", {})
        if success:
            h["success"] += 1
            stats["success"] += 1
            cooldowns.pop(key, None)
        else:
            h["failure"] += 1
            stats["failure"] += 1
        h["latency_ms"] = latency_ms if not h["latency_ms"] else h["latency_ms"] * .8 + latency_ms * .2
        stats["latency_ms"] = latency_ms if not stats["latency_ms"] else stats["latency_ms"] * .8 + latency_ms * .2
        stats["prompt_tokens"] += int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        stats["completion_tokens"] += int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
        providers.update({"success": h["success"], "failure": h["failure"],
                          "latency_ms": h["latency_ms"]})
        self._save_state()

    def _cooldown_key(self, provider, ki, seconds):
        p = self.state["providers"].setdefault(provider, {})
        until = time.time() + seconds
        p.setdefault("key_cooldowns", {})[str(ki)] = until
        h = self._provider_health(provider)  # provider view: the latest moment one of its keys is cooling down
        h["cooldown_until"] = max(float(h.get("cooldown_until") or 0), until)
        self._save_state()

    def _next_wait(self):
        """Seconds until the first rate-limited key is usable again (None if no key is cooling down)."""
        now, ends = time.time(), []
        for p in self.providers:
            for until in self.state.get("providers", {}).get(p, {}).get("key_cooldowns", {}).values():
                if float(until or 0) > now:
                    ends.append(float(until) - now)
        return min(ends) if ends else None

    def call(self, messages, tools=None, tier=2, max_tokens=4096, temperature=.2, task="general"):
        """Best model first, falling back across models, keys and providers. When every candidate is only
        rate-limited ("try again in 20s"), wait for the first key to be free again instead of failing,
        up to MM_RATE_WAIT_MAX seconds in total (default 120)."""
        errors, waited = [], 0.0
        max_wait = float(os.getenv("MM_RATE_WAIT_MAX", "120") or 0)
        while True:
            result = self._attempt(messages, tools, tier, max_tokens, temperature, task, errors)
            if result is not None:
                return result
            wait = self._next_wait()
            if not any(e[3] == 429 for e in errors) or wait is None or waited + wait > max_wait:
                break
            pause = max(1.0, wait + 0.5)
            self._event("wait", seconds=round(pause, 1))
            self._sleep(pause)
            waited += pause
            errors = [e for e in errors if e[3] != 429]  # rate-limited models can be tried again
        raise AIError("Orchestrator: nessun candidato disponibile: " +
                      " | ".join(f"provider={p} model={m} key_index={k} http_status={s if s is not None else 'none'} reason={reason}" for p,m,k,s,reason in errors[-12:]))

    _sleep = staticmethod(time.sleep)

    def _attempt(self, messages, tools, tier, max_tokens, temperature, task, errors):
        requested = max(1, min(4, int(tier)))
        for current in range(requested, 0, -1):
            for m, ki in self.candidates(task, current, {e[:3] for e in errors}):
                p = self.providers[m.provider]
                key = p["keys"][ki]
                started = time.time()
                try:
                    result = (self._anthropic(p["base"], key, m, messages, tools, max_tokens, temperature)
                              if p["kind"] == "anthropic"
                              else self._openai(p["base"], key, m, messages, tools, max_tokens, temperature))
                    ms = (time.time() - started) * 1000
                    self._record_quota(m.provider, ki, result.get("headers", {}))
                    self._remember(m, ki, True, ms, result.get("usage") or {})
                    result["orchestration"] = {
                        "tier": current, "task": task, "latency_ms": round(ms, 1),
                        "health": self._provider_health(m.provider).copy(),
                        "adaptive": True
                    }
                    self._event("success", provider=m.provider, model=m.id,
                                tier=current, latency_ms=round(ms, 1))
                    return result
                except AIError as e:
                    ms = (time.time() - started) * 1000
                    self._record_quota(m.provider, ki, e.headers)
                    self._remember(m, ki, False, ms, {})
                    if e.status == 429:
                        retry = _number(_header(e.headers, "retry-after"))
                        if retry is None:
                            # Some providers (notably Groq) put the retry window only in
                            # the error message, e.g. "try again in 20.57s".
                            match = re.search(r"(?:try again in|retry in)\s+([0-9]+(?:\.[0-9]+)?)\s*s", str(e), re.I)
                            retry = _number(match.group(1)) if match else None
                        seconds = retry if retry is not None else float(os.getenv("MM_QUOTA_COOLDOWN", "60"))
                        # Back off only the failing key so another key can be used.
                        self._cooldown_key(m.provider, ki, max(1.0, seconds))
                    errors.append((m.provider, m.id, ki, e.status, str(e)))
                    self._event("fallback", provider=m.provider, model=m.id, status=e.status)
        return None

    def _openai(self, base, key, m, messages, tools, max_tokens, temp):
        body = {"model": m.id, "messages": messages, "max_tokens": max_tokens, "temperature": temp}
        if tools:
            body.update(tools=tools, tool_choice="auto")
        _, data, headers = _json(base + "/chat/completions", key, "POST", body)
        c = (data.get("choices") or [{}])[0]
        return {"provider": m.provider, "model": m.id, "message": c.get("message") or {},
                "usage": data.get("usage") or {}, "raw": data, "headers": headers}

    def _anthropic(self, base, key, m, messages, tools, max_tokens, temp):
        system, msgs = [], []
        for x in messages:
            role = x.get("role")
            if role == "system":
                system.append(x.get("content", ""))
                continue
            if role == "assistant" and x.get("tool_calls"):
                blocks = []
                if x.get("content"):
                    blocks.append({"type": "text", "text": x["content"]})
                for c in x["tool_calls"]:
                    f = c.get("function", {})
                    blocks.append({"type": "tool_use", "id": c.get("id") or f.get("name"),
                                   "name": f.get("name"),
                                   "input": json.loads(f.get("arguments") or "{}")})
                msgs.append({"role": "assistant", "content": blocks})
                continue
            if role == "tool":
                msgs.append({"role": "user", "content": [{
                    "type": "tool_result", "tool_use_id": x.get("tool_call_id"),
                    "content": x.get("content", "")}]})
                continue
            msgs.append({"role": role, "content": x.get("content", "")})
        body = {"model": m.id, "max_tokens": max_tokens, "messages": msgs}
        if system:
            body["system"] = "\n\n".join(system)
        if tools:
            body["tools"] = [{
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"]["parameters"]
            } for t in tools]
        _, data, headers = _json(base + "/v1/messages", key, "POST", body,
                                 {"anthropic-version": "2023-06-01"})
        blocks = data.get("content") or []
        texts, calls = [], []
        for b in blocks:
            if b.get("type") == "text":
                texts.append(b.get("text", ""))
            elif b.get("type") == "tool_use":
                calls.append({"id": b.get("id"), "type": "function",
                              "function": {"name": b.get("name"),
                                           "arguments": json.dumps(b.get("input") or {})}})
        u = data.get("usage") or {}
        return {"provider": m.provider, "model": m.id,
                "message": {"role": "assistant", "content": "\n".join(texts),
                            **({"tool_calls": calls} if calls else {})},
                "usage": {"prompt_tokens": u.get("input_tokens", 0),
                          "completion_tokens": u.get("output_tokens", 0)},
                "raw": data, "headers": headers}


# Backward-compatible public name used by the agent runner and integrations.
Router = Orchestrator
