#!/usr/bin/env python3
"""Paper trading e segnali (0 token AI): fa girare le strategie con prezzi veri e soldi finti.

  python3 scripts/paper.py run        un passo per ogni strategia in paper trading o live
  python3 scripts/paper.py status     riepilogo, senza scaricare niente

Per ogni opportunità in fase "building" (= paper trading), "live" o "scaling" con products/<id>/strategy.py:
- scarica le candele chiuse (scripts/market_data.py) e, se ce n'è una nuova, chiede a target() l'esposizione;
- ribilancia un portafoglio VIRTUALE da 1000 $ con commissioni e slittamento come nel backtest;
- scrive products/<id>/paper.json (equity, operazioni, confronto con il buy & hold) e media/02-paper.png.

Strategie LIVE (products/<id>/live.json, scritto SOLO da scripts/actions.py dopo l'ok del proprietario):
nessun ordine viene mai inviato a un exchange. Quando l'esposizione cambia, la macchina registra un
SEGNALE (mm signal) che arriva al proprietario su Telegram e in plancia: "porta BTC al 60% dei 300 € approvati".
Il proprietario decide se eseguirlo a mano sul suo exchange e registra i risultati reali nel ledger.
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("MM_ROOT") or os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "engine"))
import backtest  # noqa: E402
import market_data  # noqa: E402
import mm  # noqa: E402

START_USD = 1000.0
HISTORY_CAP = 2000
TRADES_CAP = 300
RUN_STAGES = ("building", "live", "scaling")


def _read(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write(path: str, data: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def fresh_book(price: float, t: int) -> dict:
    return {"start": mm.now(), "start_time": t, "start_price": price, "capital_usd": START_USD,
            "cash": START_USD, "units": 0.0, "exposure": 0.0, "last_time": None,
            "equity": START_USD, "history": [], "trades": []}


def step(book: dict, c: dict, mod) -> list[dict]:
    """Process every closed candle not seen yet. Returns the trades made (usually 0 or 1)."""
    made = []
    for i, t in enumerate(c["time"]):
        if book["last_time"] is not None and t <= book["last_time"]:
            continue
        price = c["close"][i]
        want = backtest.clamp_exposure(mod.target(backtest.view(c, i), mod.PARAMS))
        equity = book["cash"] + book["units"] * price
        if abs(want - book["exposure"]) >= backtest.MIN_CHANGE:
            cost = abs(want - book["exposure"]) * equity * (backtest.FEE + backtest.SLIPPAGE)
            equity -= cost
            book["units"] = equity * want / price if price else 0.0
            book["cash"] = equity - book["units"] * price
            tr = {"time": t, "price": price, "from": round(book["exposure"], 3), "to": round(want, 3),
                  "cost_usd": round(cost, 4), "equity": round(equity, 2)}
            book["trades"].append(tr)
            made.append(tr)
            book["exposure"] = want
        book["equity"] = round(book["cash"] + book["units"] * price, 4)
        book["last_time"] = t
        book["last_price"] = price
        book["history"].append([t, round(book["equity"], 2), round(price, 8), round(book["exposure"], 3)])
    book["history"] = book["history"][-HISTORY_CAP:]
    book["trades"] = book["trades"][-TRADES_CAP:]
    return made


def metrics(book: dict) -> dict:
    eq = book["equity"] / book["capital_usd"] - 1
    hold = (book.get("last_price") or book["start_price"]) / book["start_price"] - 1 if book["start_price"] else 0
    curve = [h[1] for h in book["history"]] or [book["capital_usd"]]
    peak, dd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        dd = max(dd, 1 - v / peak if peak else 0)
    days = (book["last_time"] - book["start_time"]) / 86400 if book.get("start_time") and book.get("last_time") else 0
    return {"return": round(eq, 4), "hold_return": round(hold, 4), "max_dd": round(dd, 4),
            "days": round(days, 1), "trades": len(book["trades"]), "exposure": book["exposure"]}


def paper_chart(book: dict, path: str, title: str) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    hist = book["history"]
    if len(hist) < 2:
        return
    W, H, P = 1200, 675, 70
    img = Image.new("RGB", (W, H), (12, 16, 28))
    d = ImageDraw.Draw(img)
    big, mid, small = backtest._fonts()
    eq = [h[1] / book["capital_usd"] for h in hist]
    hold = [h[2] / hist[0][2] if hist[0][2] else 1 for h in hist]
    lo, hi = min(eq + hold), max(eq + hold)
    hi = hi if hi > lo else lo + 0.01
    sx = lambda i: P + (W - 2 * P) * i / (len(hist) - 1)
    sy = lambda v: H - P - (H - 2 * P) * (v - lo) / (hi - lo)
    d.line([(sx(i), sy(v)) for i, v in enumerate(hold)], fill=(120, 130, 150), width=2)
    d.line([(sx(i), sy(v)) for i, v in enumerate(eq)], fill=(62, 207, 178), width=3)
    m = metrics(book)
    d.text((P, 10), title[:70], fill=(240, 240, 250), font=big)
    d.text((P, H - 34), f"paper trading (soldi finti, prezzi veri) da {m['days']:.0f} giorni · strategia {m['return'] * 100:+.1f}% · "
                    f"buy & hold {m['hold_return'] * 100:+.1f}% · DD {m['max_dd'] * 100:.0f}%", fill=(200, 205, 220), font=mid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def signal_text(oid: str, title: str, mod, tr: dict, live: dict) -> str:
    cap = float(live.get("capital_eur") or 0)
    base = mod.PAIR.split("-")[0]
    pct = round(tr["to"] * 100)
    amount = (f" (≈ {cap * tr['to']:.0f} € dei {cap:.0f} € approvati)" if tr["to"] > 0 else " (tutto in cassa)") if cap else ""
    verb = "COMPRA" if tr["to"] > tr["from"] else "VENDI"
    return (f"{verb} · {title[:50]} ({oid}): porta {base} al {pct}%{amount}. Prezzo {tr['price']:.6g} "
            f"{mod.PAIR.split('-')[1]}. Prima era al {round(tr['from'] * 100)}%. Esegui solo se sei d'accordo.")


def run(fetch=None) -> list[str]:
    """One pass over every strategy that should be running. `fetch(pair, tf)` is injectable for tests."""
    fetch = fetch or (lambda pair, tf: market_data.candles(pair, tf, 400))
    with mm.locked():
        s = mm.load()
    out = []
    for o in s["opportunities"]:
        if o.get("stage") not in RUN_STAGES:
            continue
        folder = os.path.join(ROOT, "products", o["id"])
        if not os.path.isfile(os.path.join(folder, "strategy.py")):
            continue
        try:
            mod = backtest.load_strategy(folder)
            c = fetch(mod.PAIR, mod.TIMEFRAME)
            path = os.path.join(folder, "paper.json")
            book = _read(path)
            if not book or book.get("pair") != mod.PAIR or book.get("timeframe") != mod.TIMEFRAME:
                # start now: the previous candles only warm up the indicators, no trades in the past
                book = fresh_book(c["close"][-1], c["time"][-1])
                book.update(pair=mod.PAIR, timeframe=mod.TIMEFRAME, last_time=c["time"][-2] if len(c["time"]) > 1 else None)
            made = step(book, c, mod)
            book["metrics"] = metrics(book)
            book["updated"] = mm.now()
            _write(path, book)
            paper_chart(book, os.path.join(folder, "media", "02-paper.png"), f"{o['title'][:60]} · {mod.PAIR} {mod.TIMEFRAME}")
            live = _read(os.path.join(folder, "live.json"))
            for tr in made:
                if live and o["stage"] in ("live", "scaling"):
                    mm.main(["signal", json.dumps({"opportunity": o["id"], "text": signal_text(o["id"], o["title"], mod, tr, live),
                                                   "pair": mod.PAIR, "to": tr["to"], "price": tr["price"]})])
                else:
                    mm.main(["log", "paper", f"{o['id']}: esposizione {tr['from']:.0%} → {tr['to']:.0%} a {tr['price']:.6g} (paper)"])
            m = book["metrics"]
            out.append(f"{o['id']} {mod.PAIR} {mod.TIMEFRAME}: paper {m['return'] * 100:+.1f}% vs hold {m['hold_return'] * 100:+.1f}% "
                       f"in {m['days']:.0f}g, {len(made)} operazioni nuove")
        except Exception as e:  # one broken strategy must not stop the others
            out.append(f"{o['id']}: errore ({e})")
            mm.main(["log", "paper", f"{o['id']}: paper trading in errore ({str(e)[:150]})"])
    return out


def status() -> list[str]:
    with mm.locked():
        s = mm.load()
    out = []
    for o in s["opportunities"]:
        book = _read(os.path.join(ROOT, "products", o["id"], "paper.json"))
        if book.get("metrics"):
            m = book["metrics"]
            out.append(f"{o['id']} [{o['stage']}] {book.get('pair')} paper {m['return'] * 100:+.1f}% vs hold "
                       f"{m['hold_return'] * 100:+.1f}% · DD {m['max_dd'] * 100:.0f}% · {m['days']:.0f} giorni · {m['trades']} operazioni")
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        try:
            print("\n".join(run()) or "paper: nessuna strategia in paper trading o live")
        except Exception as e:  # never break the workflow
            print(f"paper: errore ({e})")
        return 0
    if argv[:1] == ["status"]:
        print("\n".join(status()) or "paper: nessun paper trading avviato")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
