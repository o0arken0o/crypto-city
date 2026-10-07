#!/usr/bin/env python3
"""Rendimenti DeFi/staking dai dati pubblici di DefiLlama (0 token AI, nessuna chiave).

  python3 scripts/yields.py             scrive state/research/yields-<data>.md e state/market/yields.json
  python3 scripts/yields.py --print     stampa soltanto

Filtri prudenti (il team rendite parte da qui, non dal marketing dei protocolli):
- solo pool con TVL ≥ 50 milioni $, esposizione a un solo asset, senza rischio di impermanent loss;
- rendimento medio 30 giorni tra 1% e 25% (sopra il 25% quasi sempre è inflazione di token o rischio nascosto);
- due liste: stablecoin (USDC, USDT, DAI, …) e asset principali (BTC, ETH, SOL e i loro liquid staking).
I numeri cambiano ogni giorno e NON sono garantiti: sono il punto di partenza della ricerca, non una promessa.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.environ.get("MM_STATE_DIR", os.path.join(ROOT, "state"))
URL = "https://yields.llama.fi/pools"
MIN_TVL = 50e6
APY_MIN, APY_MAX = 1.0, 25.0
MAJORS = ("BTC", "ETH", "SOL", "ADA", "CRO")  # XRP has no native staking


def fetch(get=None) -> list[dict]:
    if get:
        return get(URL)
    req = urllib.request.Request(URL, headers={"User-Agent": "crypto-machine/1.0"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.loads(r.read().decode()).get("data") or []


def _apy(p: dict) -> float:
    v = p.get("apyMean30d")
    return float(v if v is not None else p.get("apy") or 0)


def pick(pools: list[dict], n: int = 12) -> dict:
    ok = [p for p in pools if float(p.get("tvlUsd") or 0) >= MIN_TVL and p.get("exposure") == "single"
          and str(p.get("ilRisk", "no")).lower() == "no" and APY_MIN <= _apy(p) <= APY_MAX]
    stable = sorted((p for p in ok if p.get("stablecoin")), key=_apy, reverse=True)[:n]
    sym = lambda p: str(p.get("symbol") or "").upper()
    majors = sorted((p for p in ok if not p.get("stablecoin") and any(m in sym(p) for m in MAJORS)), key=_apy, reverse=True)[:n]
    row = lambda p: {"project": p.get("project"), "chain": p.get("chain"), "symbol": p.get("symbol"),
                     "apy_30d": round(_apy(p), 2), "apy_base": p.get("apyBase"), "apy_reward": p.get("apyReward"),
                     "tvl_musd": round(float(p.get("tvlUsd") or 0) / 1e6, 1), "pool": p.get("pool")}
    return {"date": dt.date.today().isoformat(), "stable": [row(p) for p in stable], "majors": [row(p) for p in majors]}


def markdown(res: dict) -> str:
    L = [f"# Rendimenti DeFi/staking · {res['date']} (DefiLlama, filtri prudenti)",
         "", "Fonte: https://defillama.com/yields · TVL ≥ 50 M$, un solo asset, niente impermanent loss, APY medio 30gg 1-25%.",
         "Numeri variabili e non garantiti. Rischi sempre presenti: smart contract, depeg, piattaforma, regole del paese.", ""]
    for key, title in (("stable", "Stablecoin"), ("majors", "BTC / ETH / SOL / ADA / CRO")):
        L += [f"## {title}", "| progetto | rete | asset | APY 30gg | di cui premi | TVL M$ |", "|---|---|---|---|---|---|"]
        L += [f"| {r['project']} | {r['chain']} | {r['symbol']} | {r['apy_30d']}% | {r['apy_reward'] or 0}% | {r['tvl_musd']} |"
              for r in res[key]] or ["| — | | | | | |"]
        L.append("")
    return "\n".join(L)


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        res = pick(fetch())
    except Exception as e:  # never break the workflow
        print(f"yields: dati non disponibili ({e})")
        return 0
    md = markdown(res)
    if "--print" in argv:
        print(md)
        return 0
    os.makedirs(os.path.join(STATE, "research"), exist_ok=True)
    os.makedirs(os.path.join(STATE, "market"), exist_ok=True)
    with open(os.path.join(STATE, "research", f"yields-{res['date']}.md"), "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(STATE, "market", "yields.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print(f"yields: {len(res['stable'])} pool stablecoin e {len(res['majors'])} pool BTC/ETH/SOL salvati")
    return 0


if __name__ == "__main__":
    sys.exit(main())
