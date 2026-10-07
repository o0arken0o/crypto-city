#!/usr/bin/env python3
"""Backtest deterministico di una strategia (0 token AI): il quant-dev lo lancia, nessuno lo "interpreta".

  python3 scripts/backtest.py products/<id>            scarica i prezzi, simula, scrive backtest.json e media/equity.png
  python3 scripts/backtest.py products/<id> --offline  usa solo la cache in state/market/

La strategia è products/<id>/strategy.py:

    PAIR = "BTC-USD"          # coppia spot (Coinbase), solo BTC ETH SOL XRP ADA CRO (market_data.MARKETS)
    TIMEFRAME = "1d"          # 1h, 6h, 1d
    PARAMS = {"fast": 20, "slow": 100}
    def target(c, p):          # c = candele CHIUSE fino ad adesso (dict di liste: time/open/high/low/close/volume)
        ...                    # ritorna l'esposizione voluta, 0.0 (tutto in cassa) .. 1.0 (tutto nella crypto)

Regole fisse (POLICY e risk-manager): solo spot, niente leva né short, esposizione tagliata a 0..1.
La funzione riceve SOLO il passato (le liste sono tagliate alla candela corrente): niente sbirciate nel futuro.
Commissioni 0,10% + slittamento 0,05% a ogni cambio di esposizione.
Il periodo è diviso in "in-sample" (primo 70%) e "out-of-sample" (ultimo 30%): conta soprattutto il secondo.

Esito (campo "verdict"): PASS solo se nell'out-of-sample la strategia guadagna, ha Sharpe ≥ 0,5,
drawdown massimo ≤ 35% e su tutto il periodo fa almeno 8 operazioni e ha un drawdown più basso del buy & hold.
Regole più severe (versione 2): almeno 1 anno di prezzi, e nell'out-of-sample deve tenere almeno metà del guadagno del
buy & hold oppure avere uno Sharpe migliore (se il mercato è sceso, deve aver perso meno).
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import market_data  # noqa: E402

FEE = 0.001
SLIPPAGE = 0.0005
MIN_CHANGE = 0.02      # exposure changes smaller than 2% are ignored (no dust trades)
IS_SHARE = 0.7
PERIODS_PER_YEAR = {"1h": 24 * 365, "6h": 4 * 365, "1d": 365}
RULES = {"oos_return_min": 0.0, "oos_sharpe_min": 0.5, "max_dd_max": 0.35, "trades_min": 8,
         "history_days_min": 365,   # at least one year of prices: 80 days of 1h candles prove nothing
         "hold_capture_min": 0.5}   # out-of-sample: at least half of the buy & hold gain, or a better Sharpe than buy & hold
RULES_VERSION = 2  # bump when the rules get stricter: strategies tested with older rules go back to backtest
LIMIT = {"1h": 9000, "6h": 1600, "1d": 1500}  # candles to download: > 1 year for every timeframe


def load_strategy(folder: str):
    path = os.path.join(folder, "strategy.py")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"manca {path}")
    spec = importlib.util.spec_from_file_location(f"strategy_{abs(hash(path))}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not callable(getattr(mod, "target", None)):
        raise ValueError("strategy.py deve definire target(c, p)")
    mod.PAIR = str(getattr(mod, "PAIR", "BTC-USD")).upper().replace("/", "-")
    if mod.PAIR.split("-")[0] not in market_data.MARKETS:
        raise ValueError(f"coppia {mod.PAIR} non ammessa: solo {', '.join(market_data.MARKETS)} (POLICY: niente memecoin o token piccoli)")
    mod.TIMEFRAME = str(getattr(mod, "TIMEFRAME", "1d"))
    mod.PARAMS = dict(getattr(mod, "PARAMS", {}) or {})
    if mod.TIMEFRAME not in market_data.TIMEFRAMES:
        raise ValueError(f"TIMEFRAME non valido: {mod.TIMEFRAME}")
    return mod


def view(c: dict, i: int) -> dict:
    """Candles 0..i only: the strategy cannot see the future."""
    return {k: v[: i + 1] for k, v in c.items()}


def clamp_exposure(x) -> float:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(x) else max(0.0, min(1.0, x))


def simulate(c: dict, target_fn, params: dict, warmup: int = 0) -> dict:
    """Decide on the close of candle i, trade at that close (with costs), hold until the next close."""
    closes = c["close"]
    n = len(closes)
    equity, expo = 1.0, 0.0
    curve, expos, trades = [1.0], [0.0], 0
    for i in range(n - 1):
        if i >= warmup:
            want = clamp_exposure(target_fn(view(c, i), params))
            if abs(want - expo) >= MIN_CHANGE:
                equity *= 1 - abs(want - expo) * (FEE + SLIPPAGE)
                expo = want
                trades += 1
        r = closes[i + 1] / closes[i] - 1 if closes[i] else 0.0
        equity *= 1 + expo * r
        curve.append(equity)
        expos.append(expo)
    return {"curve": curve, "exposure": expos, "trades": trades}


def stats(curve: list, tf: str) -> dict:
    if len(curve) < 2:
        return {"return": 0.0, "max_dd": 0.0, "sharpe": 0.0, "cagr": 0.0}
    rets = [curve[i + 1] / curve[i] - 1 for i in range(len(curve) - 1) if curve[i]]
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / max(1, len(rets) - 1))
    ppy = PERIODS_PER_YEAR[tf]
    peak, dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        dd = max(dd, 1 - v / peak if peak else 0)
    years = len(rets) / ppy
    total = curve[-1] / curve[0] - 1
    cagr = (curve[-1] / curve[0]) ** (1 / years) - 1 if years > 0 and curve[-1] > 0 else -1.0
    return {"return": round(total, 4), "max_dd": round(dd, 4),
            "sharpe": round(mean / sd * math.sqrt(ppy), 2) if sd > 0 else 0.0, "cagr": round(cagr, 4)}


def segment(curve: list, a: int, b: int) -> list:
    seg = curve[a:b + 1]
    return [v / seg[0] for v in seg] if seg and seg[0] else seg


def worth_it(oos: dict, hold_oos: dict) -> bool:
    """Out-of-sample the strategy must be worth its trouble against simply holding: when the market rose, it keeps
    at least half of that gain or has a better risk-adjusted return (Sharpe); when the market fell, it lost less."""
    if hold_oos["return"] <= 0:
        return oos["return"] > hold_oos["return"]
    return oos["return"] >= RULES["hold_capture_min"] * hold_oos["return"] or oos["sharpe"] >= hold_oos["sharpe"]


def run(c: dict, mod, warmup: int | None = None) -> dict:
    n = len(c["close"])
    if n < 60:
        raise ValueError(f"troppi pochi dati: {n} candele (servono almeno 60)")
    warmup = int(getattr(mod, "WARMUP", 0) or 0) if warmup is None else warmup
    sim = simulate(c, mod.target, mod.PARAMS, warmup)
    curve, tf = sim["curve"], mod.TIMEFRAME
    hold = [x / c["close"][0] for x in c["close"]]
    cut = int(n * IS_SHARE)
    full, bh = stats(curve, tf), stats(hold, tf)
    ins, oos = stats(segment(curve, 0, cut), tf), stats(segment(curve, cut, n - 1), tf)
    bh_oos = stats(segment(hold, cut, n - 1), tf)
    checks = {
        "oos_guadagna": oos["return"] > RULES["oos_return_min"],
        "oos_sharpe": oos["sharpe"] >= RULES["oos_sharpe_min"],
        "drawdown": full["max_dd"] <= RULES["max_dd_max"],
        "operazioni": sim["trades"] >= RULES["trades_min"],
        "meno_rischio_del_hold": full["max_dd"] < bh["max_dd"],
        "storia_1_anno": (c["time"][-1] - c["time"][0]) >= RULES["history_days_min"] * 86400 * 0.97,
        "vale_il_rischio": worth_it(oos, bh_oos),
    }
    fmt = lambda t: time.strftime("%Y-%m-%d", time.gmtime(t))
    return {
        "pair": mod.PAIR, "timeframe": tf, "params": mod.PARAMS, "candles": n,
        "from": fmt(c["time"][0]), "to": fmt(c["time"][-1]), "split": fmt(c["time"][cut]),
        "costs": {"fee": FEE, "slippage": SLIPPAGE},
        "full": full, "in_sample": ins, "out_of_sample": oos,
        "buy_hold": bh, "buy_hold_oos": bh_oos,
        "trades": sim["trades"],
        "time_in_market": round(sum(1 for e in sim["exposure"] if e > 0) / len(sim["exposure"]), 3),
        "checks": checks, "verdict": "PASS" if all(checks.values()) else "FAIL", "rules": RULES_VERSION,
        "ran": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "_curve": curve, "_hold": hold, "_time": c["time"],
    }


def _fonts():
    try:
        from cover import font
        return font("bold", 30), font("regular", 21), font("regular", 18)
    except Exception:  # no cover.py / fonts: Pillow's default
        from PIL import ImageFont
        f = ImageFont.load_default()
        return f, f, f


def chart(res: dict, path: str, title: str = "") -> str | None:
    """Equity curve vs buy & hold, real numbers only. Needs Pillow; without it, no image."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    W, H, P = 1200, 675, 64
    img = Image.new("RGB", (W, H), (12, 16, 28))
    d = ImageDraw.Draw(img)
    big, mid, small = _fonts()
    curve, hold = res["_curve"], res["_hold"]
    lo, hi = min(min(curve), min(hold)), max(max(curve), max(hold))
    hi = hi if hi > lo else lo + 1
    sx = lambda i: P + (W - 2 * P) * i / max(1, len(curve) - 1)
    sy = lambda v: H - P - (H - 2 * P) * (v - lo) / (hi - lo)
    sx = lambda i: P + 10 + (W - 2 * P - 10) * i / max(1, len(curve) - 1)
    for k in range(5):
        y = P + (H - 2 * P) * k / 4
        d.line([(P, y), (W - P, y)], fill=(34, 42, 60))
        d.text((6, y - 10), f"{(hi - (hi - lo) * k / 4 - 1) * 100:+.0f}%", fill=(140, 150, 170), font=small)
    cut = int(len(curve) * IS_SHARE)
    d.line([(sx(cut), P), (sx(cut), H - P)], fill=(90, 90, 120))
    d.text((sx(cut) + 8, P + 4), "out-of-sample", fill=(150, 150, 190), font=small)
    d.line([(sx(i), sy(v)) for i, v in enumerate(hold)], fill=(120, 130, 150), width=2)
    d.line([(sx(i), sy(v)) for i, v in enumerate(curve)], fill=(247, 183, 49), width=3)
    d.text((P, 10), (title or f"{res['pair']} {res['timeframe']}")[:70], fill=(240, 240, 250), font=big)
    d.text((P, H - 34), f"■ strategia {res['full']['return'] * 100:+.1f}% (DD {res['full']['max_dd'] * 100:.0f}%)  ·  "
                    f"buy & hold {res['buy_hold']['return'] * 100:+.1f}% (DD {res['buy_hold']['max_dd'] * 100:.0f}%)  ·  "
                    f"{res['from']} / {res['to']}  ·  backtest: simulazione, non risultati reali", fill=(200, 205, 220), font=mid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)
    return path


def public(res: dict) -> dict:
    return {k: v for k, v in res.items() if not k.startswith("_")}


def backtest_folder(folder: str, offline: bool = False, data: dict | None = None) -> dict:
    mod = load_strategy(folder)
    limit = LIMIT[mod.TIMEFRAME]
    if data is None:
        data = market_data.candles(mod.PAIR, mod.TIMEFRAME, limit, sources=[] if offline else None)
    res = run(data, mod)
    with open(os.path.join(folder, "backtest.json"), "w", encoding="utf-8") as f:
        json.dump(public(res), f, ensure_ascii=False, indent=1)
    chart(res, os.path.join(folder, "media", "01-backtest.png"), f"{os.path.basename(folder)} · {mod.PAIR} {mod.TIMEFRAME}")
    return res


def summary(res: dict) -> str:
    o, f, b = res["out_of_sample"], res["full"], res["buy_hold"]
    failed = [k for k, ok in res["checks"].items() if not ok]
    return (f"{res['verdict']} · {res['pair']} {res['timeframe']} {res['from']}→{res['to']} · "
            f"totale {f['return'] * 100:+.1f}% DD {f['max_dd'] * 100:.0f}% Sharpe {f['sharpe']} · "
            f"out-of-sample {o['return'] * 100:+.1f}% Sharpe {o['sharpe']} · "
            f"hold {b['return'] * 100:+.1f}% DD {b['max_dd'] * 100:.0f}% · {res['trades']} operazioni"
            + (f" · non superati: {', '.join(failed)}" if failed else ""))


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    folder = os.path.join(ROOT, argv[0]) if not os.path.isabs(argv[0]) else argv[0]
    try:
        res = backtest_folder(folder, offline="--offline" in argv)
    except Exception as e:
        print(f"backtest: errore ({e})")
        return 1
    print(summary(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
