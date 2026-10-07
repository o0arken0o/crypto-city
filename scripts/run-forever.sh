#!/usr/bin/env bash
# Local non-stop loop. Pauses/budget are respected via `mm can-run` inside cycle.sh.
# Usage: scripts/run-forever.sh [intervallo_minuti=60]
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVERY=$(( ${1:-60} * 60 ))
while true; do
  echo "== $(date -Is) ciclo"
  bash "$ROOT/scripts/cycle.sh"
  [ -n "${MM_GIT_SYNC:-}" ] && (cd "$ROOT" && git add state products site && git commit -qm "mm: ciclo $(date -Is)" && git push -q) || true
  sleep "$EVERY"
done
