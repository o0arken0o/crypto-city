#!/usr/bin/env python3
"""Prezzi storici delle crypto da API pubbliche, senza chiavi e senza account (0 token AI).

  python3 scripts/market_data.py BTC-USD 1d [--limit 1000]   stampa un riepilogo e aggiorna la cache

Fonti, in ordine: Coinbase Exchange (storico lungo, paginato) e Kraken (fino a 720 candele).
Binance non è usata: risponde 451 ai server USA, dove girano le GitHub Actions.
Cache in state/market/<PAIR>-<TF>.json: le candele chiuse non cambiano, si scaricano solo le nuove.

Formato delle candele: dict di liste parallele {"time": [...], "open": [...], "high": [...],
"low": [...], "close": [...], "volume": [...]}, in ordine di tempo, solo candele CHIUSE.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(os.environ.get("MM_STATE_DIR", os.path.join(ROOT, "state")), "market")
TIMEFRAMES = {"1h": 3600, "6h": 21600, "1d": 86400}
KRAKEN_TF = {"1h": 60, "6h": None, "1d": 1440}
KRAKEN_ASSET = {"BTC": "XBT", "DOGE": "XDG"}
# The only coins the machine studies and tests: large, liquid, listed for years (POLICY: no memecoins, no new or illiquid
# tokens). Add one here only after checking it meets those rules; engine/mm.py and the panel read this list.
MARKETS = ("BTC", "ETH", "SOL", "XRP", "ADA", "CRO")
UA = {"User-Agent": "crypto-machine/1.0 (+github actions)"}
FIELDS = ("time", "open", "high", "low", "close", "volume")


def _get(url: str, timeout: int = 20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def empty() -> dict:
    return {k: [] for k in FIELDS}


def from_rows(rows) -> dict:
    """rows: [(time, open, high, low, close, volume), ...] in any order, duplicates allowed."""
    uniq = {}
    for r in rows:
        uniq[int(r[0])] = tuple(float(x) for x in r[1:6])
    c = empty()
    for t in sorted(uniq):
        c["time"].append(t)
        for k, v in zip(FIELDS[1:], uniq[t]):
            c[k].append(v)
    return c


def rows_of(c: dict) -> list:
    return list(zip(*(c[k] for k in FIELDS)))


def closed_only(c: dict, tf: str, now: float | None = None) -> dict:
    """Drop the candle still forming: it would change after the decision (look-ahead in the paper trading)."""
    sec = TIMEFRAMES[tf]
    now = now if now is not None else time.time()
    rows = [r for r in rows_of(c) if r[0] + sec <= now]
    return from_rows(rows)


def coinbase(pair: str, tf: str, limit: int, get=_get) -> dict:
    sec = TIMEFRAMES[tf]
    end = int(time.time())
    rows = []
    while len(rows) < limit:
        start = end - 300 * sec
        q = urllib.parse.urlencode({"granularity": sec, "start": start, "end": end})
        data = get(f"https://api.exchange.coinbase.com/products/{pair}/candles?{q}")
        if not isinstance(data, list) or not data:
            break
        rows += [(r[0], r[3], r[2], r[1], r[4], r[5]) for r in data]  # [time, low, high, open, close, volume]
        end = start
        time.sleep(0.25)
    return from_rows(rows[-limit * 2:])


def kraken(pair: str, tf: str, limit: int, get=_get) -> dict:
    iv = KRAKEN_TF.get(tf)
    if not iv:
        raise ValueError(f"Kraken non ha il timeframe {tf}")
    base, quote = pair.split("-")
    kp = KRAKEN_ASSET.get(base, base) + quote
    data = get(f"https://api.kraken.com/0/public/OHLC?pair={kp}&interval={iv}")
    if data.get("error"):
        raise RuntimeError(f"Kraken: {data['error']}")
    res = next(v for k, v in data["result"].items() if k != "last")
    return from_rows([(r[0], r[1], r[2], r[3], r[4], r[6]) for r in res])


def _cache_path(pair: str, tf: str) -> str:
    return os.path.join(CACHE, f"{pair}-{tf}.json")


def load_cache(pair: str, tf: str) -> dict:
    try:
        with open(_cache_path(pair, tf), encoding="utf-8") as f:
            c = json.load(f)
        return c if all(k in c for k in FIELDS) else empty()
    except (OSError, ValueError):
        return empty()


def save_cache(pair: str, tf: str, c: dict, keep: int = 10000) -> None:
    os.makedirs(CACHE, exist_ok=True)
    c = from_rows(rows_of(c)[-keep:])
    tmp = _cache_path(pair, tf) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(c, f, separators=(",", ":"))
    os.replace(tmp, _cache_path(pair, tf))


def candles(pair: str = "BTC-USD", tf: str = "1d", limit: int = 1000, sources=None, use_cache: bool = True) -> dict:
    """Closed candles, oldest first. Tries each source; merges with the cache; raises if nothing at all."""
    pair = pair.upper().replace("/", "-")
    if tf not in TIMEFRAMES:
        raise ValueError(f"timeframe non supportato: {tf} (usa {', '.join(TIMEFRAMES)})")
    cached = load_cache(pair, tf) if use_cache else empty()
    errors = []
    fresh = empty()
    for name, fn in (sources or [("coinbase", coinbase), ("kraken", kraken)]):
        try:
            fresh = fn(pair, tf, limit)
            if fresh["time"]:
                break
        except Exception as e:  # network, rate limit, unknown pair: try the next source
            errors.append(f"{name}: {e}")
    merged = closed_only(from_rows(rows_of(cached) + rows_of(fresh)), tf)
    if not merged["time"]:
        raise RuntimeError("nessun dato di mercato (" + "; ".join(errors) + ")")
    if use_cache and fresh["time"]:
        save_cache(pair, tf, merged)
    n = len(merged["time"])
    return {k: v[max(0, n - limit):] for k, v in merged.items()}


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 2
    pair = argv[0]
    tf = argv[1] if len(argv) > 1 else "1d"
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 1000
    c = candles(pair, tf, limit)
    t0 = time.strftime("%Y-%m-%d", time.gmtime(c["time"][0]))
    t1 = time.strftime("%Y-%m-%d %H:%M", time.gmtime(c["time"][-1]))
    print(f"{pair} {tf}: {len(c['time'])} candele chiuse dal {t0} al {t1} UTC · ultimo prezzo {c['close'][-1]:.6g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
