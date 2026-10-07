import json
import math
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

STRATEGY = '''
PAIR = "BTC-USD"
TIMEFRAME = "1d"
PARAMS = {"fast": 5, "slow": 20}
def target(c, p):
    cl = c["close"]
    if len(cl) < p["slow"]:
        return 0
    fast = sum(cl[-p["fast"]:]) / p["fast"]
    slow = sum(cl[-p["slow"]:]) / p["slow"]
    return 1.0 if fast > slow else 0.0
'''

PEEK = '''
PAIR = "BTC-USD"
TIMEFRAME = "1d"
seen = []
def target(c, p):
    seen.append(len(c["close"]))
    return 1.5   # out of range: clamped to 1
'''


def series(n=400, start=None, step=86400):
    """Waves on a rising trend: a trend-following strategy has something to do."""
    t0 = start or (int(time.time()) // step - n - 1) * step
    rows = []
    for i in range(n):
        p = 100 * (1 + i / 300) * (1 + 0.25 * math.sin(i / 15))
        rows.append((t0 + i * step, p, p * 1.01, p * 0.99, p, 1000))
    import market_data
    return market_data.from_rows(rows)


class MarketDataTest(unittest.TestCase):
    def test_closed_only_merge_and_fallback(self):
        import market_data
        sec = 86400
        now = 10 * sec + 100
        c = market_data.from_rows([(9 * sec, 1, 1, 1, 1, 1), (8 * sec, 1, 1, 1, 2, 1), (8 * sec, 1, 1, 1, 3, 1), (10 * sec, 1, 1, 1, 9, 1)])
        self.assertEqual(c["time"], [8 * sec, 9 * sec, 10 * sec])
        self.assertEqual(c["close"][0], 3)  # duplicates: the last one wins
        self.assertEqual(market_data.closed_only(c, "1d", now)["time"], [8 * sec, 9 * sec])  # 10*sec still open

        def broken(pair, tf, limit):
            raise RuntimeError("451")
        good = lambda pair, tf, limit: series(80)
        got = market_data.candles("btc/usd", "1d", 50, sources=[("a", broken), ("b", good)], use_cache=False)
        self.assertEqual(len(got["close"]), 50)
        with self.assertRaises(RuntimeError):
            market_data.candles("BTC-USD", "1d", 50, sources=[("a", broken)], use_cache=False)

    def test_coinbase_and_kraken_parsers(self):
        import market_data
        cb = [[200, 9, 11, 10, 10.5, 7], [100, 8, 10, 9, 9.5, 6]]  # [time, low, high, open, close, volume]
        calls = []
        def get(url):
            calls.append(url)
            return cb if len(calls) == 1 else []
        c = market_data.coinbase("BTC-USD", "1d", 5, get=get)
        self.assertEqual((c["time"], c["open"], c["high"], c["low"], c["close"]), ([100, 200], [9, 10], [10, 11], [8, 9], [9.5, 10.5]))
        kr = {"error": [], "result": {"XXBTZUSD": [[100, "9", "10", "8", "9.5", "9.4", "6", 3]], "last": 100}}
        c = market_data.kraken("BTC-USD", "1d", 5, get=lambda url: kr if "XBTUSD" in url else {})
        self.assertEqual((c["close"], c["volume"]), ([9.5], [6.0]))


class BacktestTest(unittest.TestCase):
    def folder(self, code):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "strategy.py"), "w") as f:
            f.write(code)
        return d

    def test_runs_writes_results_and_chart(self):
        import backtest
        d = self.folder(STRATEGY)
        res = backtest.backtest_folder(d, data=series())
        with open(os.path.join(d, "backtest.json")) as f:
            saved = json.load(f)
        self.assertNotIn("_curve", saved)
        self.assertIn(saved["verdict"], ("PASS", "FAIL"))
        self.assertEqual(set(saved["checks"]), {"oos_guadagna", "oos_sharpe", "drawdown", "operazioni", "meno_rischio_del_hold", "storia_1_anno", "vale_il_rischio"})
        self.assertEqual(saved["rules"], backtest.RULES_VERSION)
        self.assertGreater(res["trades"], 4)
        self.assertLess(res["full"]["max_dd"], res["buy_hold"]["max_dd"])  # sits in cash during the falls
        self.assertIn("operazioni", backtest.summary(res))
        try:
            import PIL  # noqa: F401
            self.assertTrue(os.path.exists(os.path.join(d, "media", "01-backtest.png")))
        except ImportError:
            pass

    def test_no_look_ahead_no_leverage_and_costs(self):
        import backtest
        mod = backtest.load_strategy(self.folder(PEEK))
        c = series(100)
        res = backtest.run(c, mod)
        self.assertEqual(mod.seen, list(range(1, 100)))  # at step i it saw only i+1 candles
        # always fully invested (1.5 clamped to 1): return = hold minus one entry cost
        hold = c["close"][-1] / c["close"][0]
        self.assertAlmostEqual(res["full"]["return"] + 1, hold * (1 - backtest.FEE - backtest.SLIPPAGE), places=3)
        self.assertEqual(res["trades"], 1)
        with self.assertRaises(ValueError):
            backtest.run(series(30), mod)  # too little data


class PaperTest(unittest.TestCase):
    def setUp(self):
        import mm
        import paper
        self.root = root = tempfile.mkdtemp()
        st = os.path.join(root, "state"); os.makedirs(st)
        mm.STATE_DIR, mm.STATE_FILE = st, os.path.join(st, "state.json")
        mm.INBOX_FILE, mm.LOCK_FILE, mm.LIVE_FILE = (os.path.join(st, n) for n in ("inbox.jsonl", ".lock", "live.json"))
        paper.ROOT = root
        self.mm, self.paper = mm, paper
        d = os.path.join(root, "products", "opp_trd"); os.makedirs(d)
        with open(os.path.join(d, "strategy.py"), "w") as f:
            f.write(STRATEGY)
        self.dir = d
        with redirect_stdout(StringIO()):
            mm.main(["opp", json.dumps({"id": "opp_trd", "title": "Trend BTC", "stage": "building"})])

    def run_(self, data):
        with redirect_stdout(StringIO()):
            return self.paper.run(fetch=lambda pair, tf: data)

    def test_paper_starts_now_then_follows_new_candles_and_signals_only_when_live(self):
        full = series(300)
        out = self.run_({k: v[:200] for k, v in full.items()})
        with open(os.path.join(self.dir, "paper.json")) as f:
            book = json.load(f)
        self.assertEqual(len(book["history"]), 1, out)  # no trades in the past: it starts from the last candle
        self.assertEqual(book["capital_usd"], 1000)
        self.run_({k: v[:200] for k, v in full.items()})  # same data: nothing new
        with open(os.path.join(self.dir, "paper.json")) as f:
            self.assertEqual(len(json.load(f)["history"]), 1)
        self.run_(full)
        with open(os.path.join(self.dir, "paper.json")) as f:
            book = json.load(f)
        self.assertEqual(len(book["history"]), 101)
        self.assertGreater(len(book["trades"]), 0)
        self.assertEqual(self.mm.load()["signals"], [])  # paper only: no signals for the owner
        # approved by the owner → signals (never orders)
        with open(os.path.join(self.dir, "live.json"), "w") as f:
            json.dump({"approved": True, "capital_eur": 300}, f)
        with redirect_stdout(StringIO()):
            self.mm.main(["stage", "opp_trd", "live"])
        more = series(450, start=full["time"][0])
        self.run_(more)
        sig = self.mm.load()["signals"]
        self.assertTrue(sig)
        self.assertRegex(sig[0]["text"], r"^(COMPRA|VENDI) · Trend BTC \(opp_trd\): porta BTC al \d+%")
        for g in sig:
            self.assertRegex(g["text"], r"dei 300 € approvati|tutto in cassa")

    def test_broken_strategy_does_not_stop_the_others(self):
        with open(os.path.join(self.dir, "strategy.py"), "w") as f:
            f.write("def target(c, p):\n    raise ValueError('boom')\n")
        out = self.run_(series(100))
        self.assertIn("errore", out[0])


class YieldsTest(unittest.TestCase):
    def test_prudent_filters(self):
        import yields
        pools = [
            {"project": "aave-v3", "chain": "Ethereum", "symbol": "USDC", "tvlUsd": 9e8, "apyMean30d": 4.2, "stablecoin": True, "ilRisk": "no", "exposure": "single"},
            {"project": "tiny", "chain": "X", "symbol": "USDT", "tvlUsd": 1e6, "apyMean30d": 9, "stablecoin": True, "ilRisk": "no", "exposure": "single"},
            {"project": "ponzi", "chain": "X", "symbol": "USDT", "tvlUsd": 9e8, "apyMean30d": 80, "stablecoin": True, "ilRisk": "no", "exposure": "single"},
            {"project": "lido", "chain": "Ethereum", "symbol": "STETH", "tvlUsd": 2e10, "apy": 2.9, "stablecoin": False, "ilRisk": "no", "exposure": "single"},
            {"project": "lp", "chain": "Ethereum", "symbol": "ETH-USDC", "tvlUsd": 2e9, "apyMean30d": 12, "stablecoin": False, "ilRisk": "yes", "exposure": "multi"},
        ]
        res = yields.pick(pools)
        self.assertEqual([r["project"] for r in res["stable"]], ["aave-v3"])
        self.assertEqual([r["project"] for r in res["majors"]], ["lido"])
        self.assertIn("| aave-v3 | Ethereum | USDC | 4.2% |", yields.markdown(res))


if __name__ == "__main__":
    unittest.main()


class UniverseTest(unittest.TestCase):
    """Six liquid majors only: agents are pointed at the ones not studied yet, the backtest refuses anything else."""

    def test_same_list_everywhere(self):
        import market_data
        import mm
        self.assertEqual(market_data.MARKETS, mm.MARKETS)
        self.assertEqual(market_data.MARKETS, ("BTC", "ETH", "SOL", "XRP", "ADA", "CRO"))
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
        import server
        self.assertTrue({"XRP-EUR", "ADA-EUR", "CRO-EUR", "CRO-USD"} <= server.CANDLE_PAIRS)
        self.assertNotIn("BONER-EUR", server.CANDLE_PAIRS)

    def test_backtest_refuses_coins_outside_the_universe(self):
        import backtest
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "strategy.py"), "w") as f:
            f.write('PAIR = "BONER-USD"\nTIMEFRAME = "1d"\nPARAMS = {}\ndef target(c, p):\n    return 1.0\n')
        with self.assertRaises(ValueError) as cm:
            backtest.backtest_folder(d, offline=True)
        self.assertIn("non ammessa", str(cm.exception))

    def test_brief_points_at_coins_not_studied(self):
        import mm
        s = mm.default_state()
        s["markets"] = [{"name": "BTC 1h mean reversion", "evidence": "ETH correlata", "updated": mm.now()}]
        s["opportunities"] = [{"id": "o", "title": "Trend SOL 1d", "stage": "idea", "score": 1, "updated": mm.now()}]
        self.assertEqual(mm.uncovered_markets(s), ["XRP", "ADA", "CRO"])
        self.assertIn("Da studiare (nessuna analisi negli ultimi 14 giorni): XRP, ADA, CRO", "\n".join(mm._universe_lines(s)))
        s["markets"][0]["updated"] = "2020-01-01T00:00:00+00:00"  # old analyses do not count
        self.assertIn("BTC", mm.uncovered_markets(s))


class StricterRulesTest(unittest.TestCase):
    """Rules v2: one year of prices, and out-of-sample the strategy must be worth its risk against buy & hold."""

    def test_worth_it(self):
        import backtest
        w = lambda r, s, hr, hs: backtest.worth_it({"return": r, "sharpe": s}, {"return": hr, "sharpe": hs})
        self.assertFalse(w(.0067, .65, .1069, 4.5))   # the BTC 1h case: +0,67% vs +10,7%, far worse Sharpe
        self.assertTrue(w(.06, .9, .1069, 4.5))       # keeps more than half of the gain
        self.assertTrue(w(.02, 2.1, .03, 1.5))        # less gain but better risk-adjusted
        self.assertTrue(w(-.02, -.3, -.15, -1))       # falling market: lost much less
        self.assertFalse(w(-.2, -1, -.15, -1))

    def test_short_history_fails(self):
        import backtest
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "strategy.py"), "w") as f:
            f.write(STRATEGY)
        res = backtest.backtest_folder(d, data=series(200))  # 200 daily candles < 1 year
        self.assertFalse(res["checks"]["storia_1_anno"])
        self.assertEqual(res["verdict"], "FAIL")
        self.assertGreaterEqual(backtest.LIMIT["1h"] / 24, 365)  # downloads more than a year for every timeframe

    def test_strategies_tested_with_old_rules_go_back_to_backtest(self):
        import mm
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "products", "opp_x"))
        with open(os.path.join(root, "products", "opp_x", "backtest.json"), "w") as f:
            json.dump({"verdict": "PASS"}, f)  # no "rules": version 1
        s = mm.default_state()
        s["opportunities"] = [{"id": "opp_x", "title": "Mean reversion BTC 1h", "stage": "building", "score": 1}]
        out = mm.housekeeping(s, root)
        self.assertEqual(s["opportunities"][0]["stage"], "validating")
        self.assertIn("regole più severe", s["opportunities"][0]["next_action"])
        self.assertTrue(any("regole vecchie" in x for x in out))
