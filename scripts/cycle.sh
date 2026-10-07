#!/usr/bin/env bash
# Runs ONE Crypto Machine cycle headless.
# Engine (MM_ENGINE): "claude" = Claude Code with the plugin and its sub-agents (needs CLAUDE_CODE_OAUTH_TOKEN
# or ANTHROPIC_API_KEY and the `claude` CLI); "router" = the provider-neutral AI orchestrator (engine/agent_runner.py);
# "auto" (default) = Claude when its credentials and CLI are there, otherwise the orchestrator.
# If Claude is out of quota the same cycle falls back to the orchestrator (MM_FALLBACK=off to skip instead).
# Env: MM_MODEL (default sonnet), MM_MAX_TURNS (default 40), CLAUDE (default claude), MM_COMMAND.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$ROOT/bin:$PATH" MM_ROOT="$ROOT"
E=(python3 "$ROOT/engine/mm.py")
CLAUDE="${CLAUDE:-claude}"

# Secrets pasted with line breaks/spaces break the auth header: strip them; drop empty ones.
for v in CLAUDE_CODE_OAUTH_TOKEN ANTHROPIC_API_KEY; do
  val="$(printf '%s' "${!v:-}" | tr -d '[:space:]')"
  if [ -n "$val" ]; then export "$v=$val"; else unset "$v"; fi
done
ENGINE="${MM_ENGINE:-auto}"
if [ "$ENGINE" = auto ]; then
  if { [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || [ -n "${ANTHROPIC_API_KEY:-}" ]; } && command -v "$CLAUDE" >/dev/null 2>&1; then
    ENGINE=claude
  else
    ENGINE=router
  fi
fi
echo "motore AI: $ENGINE"

"${E[@]}" apply >/dev/null
TEAM=trading
case "${MM_COMMAND:-}" in
  /crypto-machine:growth*) TEAM=rendite ;;
  /crypto-machine:social*) TEAM=social ;;
esac
FORCE=()
[ -n "${MM_FORCE:-}" ] && FORCE=(--force)
if ! msg=$("${E[@]}" can-run --team "$TEAM" "${FORCE[@]}"); then
  echo "skip: $msg"
  "${E[@]}" end-cycle --summary "saltato: $msg" >/dev/null
  exit 0
fi

RUN_URL=""
[ -n "${GITHUB_RUN_ID:-}" ] && RUN_URL="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY}/actions/runs/${GITHUB_RUN_ID}"
"${E[@]}" live begin --run "${GITHUB_RUN_ID:-local-$$}" --url "$RUN_URL" --team "$TEAM"
LIVEPID=""
if [ -n "${MM_LIVE_TOKEN:-}" ] && [ -n "${GITHUB_REPOSITORY:-}" ]; then
  GITHUB_TOKEN="$MM_LIVE_TOKEN" python3 "$ROOT/scripts/live_push.py" loop 8 &
  LIVEPID=$!
fi
LIVE_TOKEN="${MM_LIVE_TOKEN:-}"
unset MM_LIVE_TOKEN

GUARD="$(mktemp -d)"
cp "$ROOT/scripts/guard.py" "$GUARD/" && cp -r "$ROOT/engine" "$GUARD/"
python3 "$GUARD/guard.py" snapshot "$GUARD/snap.json"

OUT="$(mktemp)"
PLUG=""
if [ "$ENGINE" = claude ]; then
  CAP=$("${E[@]}" cycle-cap)  # per-cycle budget, capped by what is left today (savings mode included)
  # Load the plugin from a temp copy: when the plugin dir is the repo itself, Claude Code
  # protects every file in it and quant-dev/risk-manager cannot write products/ or site/.
  PLUG="$(mktemp -d)/crypto-machine"
  mkdir -p "$PLUG" && cp -r "$ROOT"/.claude-plugin "$ROOT"/agents "$ROOT"/commands "$ROOT"/skills \
    "$ROOT"/hooks "$ROOT"/bin "$ROOT"/engine "$PLUG"/
  "$CLAUDE" -p "${MM_COMMAND:-/crypto-machine:cycle}" < /dev/null \
    --plugin-dir "$PLUG" \
    --model "${MM_MODEL:-sonnet}" \
    --max-turns "${MM_MAX_TURNS:-40}" \
    --max-budget-usd "$CAP" \
    --output-format json \
    --permission-mode acceptEdits \
    --allowedTools "Bash(mm:*)" "Bash(python3:*)" "Bash(ls:*)" "Bash(mkdir:*)" "Read" "Write" "Edit" "Glob" "Grep" "WebSearch" "WebFetch" "Agent" "Task" \
    >"$OUT" 2>"$OUT.err"
  rc=$?
else
  MM_ROOT="$ROOT" python3 "$ROOT/engine/agent_runner.py" \
    --command "${MM_COMMAND:-/crypto-machine:cycle}" >"$OUT" 2>"$OUT.err"
  rc=$?
fi

# Claude out of quota (429, e.g. the weekly limit): instead of skipping the cycle, run it with the AI router
# when at least one of its provider keys is configured. MM_FALLBACK=off keeps the old behaviour (skip).
router_ready() {
  for k in GROQ_API_KEY CEREBRAS_API_KEY GEMINI_API_KEY OPENROUTER_API_KEY TOGETHER_API_KEY MISTRAL_API_KEY DEEPSEEK_API_KEY XAI_API_KEY OPENAI_API_KEY; do
    [ -n "$(printf '%s' "${!k:-}" | tr -d '[:space:]')" ] && return 0
  done
  return 1
}
if [ "$ENGINE" = claude ] && [ $rc -ne 0 ] && grep -q '"api_error_status":429' "$OUT" && [ "${MM_FALLBACK:-router}" != off ] && router_ready; then
  why=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('result','limite')[:150])" "$OUT" 2>/dev/null || echo limite)
  echo "Claude ha finito la quota ($why): il ciclo continua con il router AI"
  "${E[@]}" log engine "Claude senza quota ($why): ciclo eseguito con il router AI" >/dev/null
  MM_ROOT="$ROOT" python3 "$ROOT/engine/agent_runner.py" \
    --command "${MM_COMMAND:-/crypto-machine:cycle}" >"$OUT" 2>"$OUT.err"
  rc=$?
  ENGINE=router
fi

python3 "$GUARD/guard.py" verify "$GUARD/snap.json" || echo "guardia: verifica non riuscita"

if [ "$ENGINE" = claude ] && [ $rc -ne 0 ] && grep -q '"subtype":"error_max_budget_usd"' "$OUT"; then
  # Per-cycle spend cap reached: the planned stop, work done so far is already saved.
  echo "stop: tetto di spesa per ciclo raggiunto (lavoro salvato)"
  "${E[@]}" log engine "ciclo fermato al tetto di spesa per ciclo" >/dev/null
  rc=0
elif [ "$ENGINE" = claude ] && [ $rc -ne 0 ] && grep -q '"api_error_status":429' "$OUT"; then
  # Usage/rate limit: not a failure, just skip this cycle; the next scheduled one retries.
  why=$(python3 -c "import json,sys;print(json.load(open(sys.argv[1])).get('result','limite')[:150])" "$OUT" 2>/dev/null || echo limite)
  echo "skip: limite di utilizzo Claude raggiunto ($why)"
  "${E[@]}" end-cycle --summary "saltato: limite di utilizzo ($why)" >/dev/null
  LIVE_SKIPPED=1
  rc=0
elif [ "$ENGINE" = claude ] && [ $rc -ne 0 ]; then
  echo "claude exit $rc"; tail -n 20 "$OUT.err"; tail -c 1500 "$OUT"; echo
  "${E[@]}" log engine "ciclo terminato con errore Claude $rc" >/dev/null
elif [ $rc -ne 0 ] && grep -qiE 'quota|rate.?limit|429|resource.?exhausted|too many requests' "$OUT.err"; then
  echo "skip: limite provider/quota raggiunto"
  grep -E "Orchestrator:|AIError|provider=.*key_index=" "$OUT.err" | tail -n 5 || tail -n 5 "$OUT.err"
  "${E[@]}" end-cycle --summary "saltato: limite provider/quota" >/dev/null
  LIVE_SKIPPED=1
  rc=0
elif [ $rc -ne 0 ]; then
  echo "AI runner exit $rc"
  tail -n 30 "$OUT.err"
  tail -c 3000 "$OUT"
  "${E[@]}" log engine "ciclo terminato con errore AI runner $rc" >/dev/null
fi

if [ -z "${LIVE_SKIPPED:-}" ]; then
  "${E[@]}" usage-from-result "$OUT" || true
fi
python3 -c 'import json,sys;r=json.load(open(sys.argv[1]));print(r.get("result","")[:5000])' "$OUT" 2>/dev/null || cat "$OUT"

if [ $rc -ne 0 ]; then LIVE_RESULT=error
elif [ -n "${LIVE_SKIPPED:-}" ]; then LIVE_RESULT=skip
else LIVE_RESULT=ok
fi
"${E[@]}" live end --result "$LIVE_RESULT"

if [ -n "$LIVEPID" ]; then
  kill "$LIVEPID" 2>/dev/null || true
  wait "$LIVEPID" 2>/dev/null || true
  GITHUB_TOKEN="$LIVE_TOKEN" python3 "$ROOT/scripts/live_push.py" once
fi

rm -rf "$OUT" "$OUT.err" "$GUARD"
[ -n "$PLUG" ] && rm -rf "$(dirname "$PLUG")"
exit $rc
