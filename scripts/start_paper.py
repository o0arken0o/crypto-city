#!/usr/bin/env python3
"""Avvio guidato del paper trading (0 token AI, funziona anche su Windows).

  python scripts/start_paper.py            crea una strategia di esempio, la prova (backtest) e, se passa, la mette in paper trading
  python scripts/start_paper.py --step     dopo l'avvio: un passo di paper trading con i prezzi di adesso

La strategia di esempio è un classico "trend following" su BTC (media veloce sopra media lenta = dentro, altrimenti in cassa).
Niente soldi veri: il paper trading usa prezzi veri e 1000 $ finti. Se il backtest non passa, la strategia NON va avanti.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FAST, SLOW = 20, 100
if "--slow" in sys.argv:   # una variante decisa PRIMA di vedere i risultati (es. --fast 50 --slow 200)
    FAST, SLOW = int(sys.argv[sys.argv.index("--fast") + 1]), int(sys.argv[sys.argv.index("--slow") + 1])
OPP_ID = "trend-btc" if (FAST, SLOW) == (20, 100) else f"trend-btc-{FAST}-{SLOW}"
STRATEGY = f'''PAIR = "BTC-USD"
TIMEFRAME = "1d"
PARAMS = {{"fast": {FAST}, "slow": {SLOW}}}


def target(c, p):
    cl = c["close"]
    if len(cl) < p["slow"]:
        return 0.0
    return 1.0 if sum(cl[-p["fast"]:]) / p["fast"] > sum(cl[-p["slow"]:]) / p["slow"] else 0.0
'''


ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")  # Windows consoles (cp1252) cannot print arrows etc.


def py(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", env=ENV)


def mm(*args: str) -> str:
    r = py(os.path.join("engine", "mm.py"), *args)
    return (r.stdout + r.stderr).strip()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    if "--step" in sys.argv:
        print(py(os.path.join("scripts", "paper.py"), "run").stdout.strip())
        print(py(os.path.join("scripts", "paper.py"), "status").stdout.strip())
        return 0
    folder = os.path.join(ROOT, "products", OPP_ID)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "strategy.py"), "w", encoding="utf-8") as f:
        f.write(STRATEGY)
    print("1/4 stato:", mm("init") or "ok")
    opp = {"id": OPP_ID, "title": f"Trend BTC (media {FAST}/{SLOW} giorni)", "strategy": "trend-following", "stage": "validating",
           "next_action": "backtest in corso"}
    print("2/4 strategia registrata:", mm("opp", json.dumps(opp), "--agent", "human"))
    print("3/4 backtest (scarica i prezzi pubblici, può volerci un minuto)...")
    r = py(os.path.join("scripts", "backtest.py"), os.path.join("products", OPP_ID))
    print((r.stdout + r.stderr).strip())
    try:
        with open(os.path.join(folder, "backtest.json"), encoding="utf-8") as f:
            bt = json.load(f)
        verdict = bt.get("verdict")
    except (OSError, ValueError):
        print("\nIl backtest non è riuscito (di solito manca internet). Riprova.")
        return 1
    if verdict != "PASS":
        bad = [k for k, ok in (bt.get("checks") or {}).items() if not ok]
        print("Controlli non superati:", ", ".join(bad) or "?")
        print(f"\nVerdetto: {verdict}. La strategia non passa la prova: NON va in paper trading. Questo è il sistema che funziona.")
        mm("stage", OPP_ID, "validating", "--next", "backtest FAIL", "--agent", "human")
        return 0
    print("4/4 backtest PASS: avvio il paper trading:", mm("stage", OPP_ID, "building", "--next", "paper trading in corso", "--agent", "human"))
    print(py(os.path.join("scripts", "paper.py"), "run").stdout.strip())
    print("\nFatto. Apri http://127.0.0.1:8787/plancia → Strategie per vedere i risultati. Per aggiornare: python scripts/start_paper.py --step")
    return 0


if __name__ == "__main__":
    sys.exit(main())
