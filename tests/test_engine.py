import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        import mm
        mm.STATE_DIR = self.tmp
        mm.STATE_FILE = os.path.join(self.tmp, "state.json")
        mm.INBOX_FILE = os.path.join(self.tmp, "inbox.jsonl")
        mm.LOCK_FILE = os.path.join(self.tmp, ".lock")
        mm.LIVE_FILE = os.path.join(self.tmp, "live.json")
        self.mm = mm

    def run_cli(self, *args):
        buf = StringIO()
        with redirect_stdout(buf):
            rc = self.mm.main(list(args))
        return rc, buf.getvalue().strip()

    def state(self):
        with open(self.mm.STATE_FILE) as f:
            return json.load(f)

    def test_scores_are_bounded_and_monotonic(self):
        lo = self.mm.market_score({"demand": 1, "ticket": 1, "speed": 1, "competition": 5, "confidence": 0})
        hi = self.mm.market_score({"demand": 5, "ticket": 5, "speed": 5, "competition": 1, "confidence": 1})
        self.assertTrue(0 <= lo < hi <= 100)
        cheap = self.mm.opp_score({"expected_eur": 300, "confidence": .5, "effort_h": 4, "days_to_cash": 3})
        slow = self.mm.opp_score({"expected_eur": 300, "confidence": .5, "effort_h": 4, "days_to_cash": 90})
        self.assertGreater(cheap, slow)

    def test_full_flow(self):
        self.run_cli("init")
        _, out = self.run_cli("market", json.dumps({"name": "Notion per dentisti", "strategy": "trend-following",
                                                    "demand": 4, "ticket": 3, "speed": 5, "competition": 2, "confidence": .6}))
        mid = json.loads(out)["id"]
        _, out = self.run_cli("opp", json.dumps({"title": "Kit Notion", "market": mid, "strategy": "trend-following",
                                                 "expected_eur": 400, "confidence": .5, "effort_h": 3, "days_to_cash": 5}))
        oid = json.loads(out)["id"]
        _, out = self.run_cli("approval", json.dumps({"kind": "publish", "title": "Pubblica kit", "opportunity": oid}))
        aid = json.loads(out)["id"]
        _, dup = self.run_cli("approval", json.dumps({"kind": "publish", "title": "Pubblica kit", "opportunity": oid}))
        self.assertTrue(json.loads(dup)["duplicate"])
        self.assertEqual(self.state()["opportunities"][0]["stage"], "awaiting_approval")

        self.mm.enqueue({"op": "approval", "args": {"id": aid, "decision": "approved"}})
        self.mm.enqueue({"op": "ledger", "args": {"type": "revenue", "amount_eur": 29, "source": "Gumroad", "opportunity": oid}})
        self.mm.enqueue({"op": "agent", "args": {"name": "risk-manager", "status": "paused"}})
        self.mm.enqueue({"op": "bogus"})
        self.mm.enqueue({"op": "directive_add", "args": {"text": "solo B2B"}})
        self.run_cli("apply")
        s = self.state()
        self.assertEqual(s["approvals"][0]["status"], "approved")
        self.assertEqual(s["agents"]["risk-manager"]["status"], "paused")
        self.assertEqual(self.mm.kpis(s)["revenue_eur"], 29)
        _, brief = self.run_cli("brief")
        self.assertIn("solo B2B", brief)
        self.assertIn("risk-manager", brief)
        self.assertIn("APPROVED", brief)
        with open(self.mm.INBOX_FILE) as f:
            self.assertEqual(f.read(), "")

    def test_budget_and_pause_gate(self):
        self.run_cli("init")
        self.assertEqual(self.run_cli("can-run")[0], 0)
        self.run_cli("usage", "--usd", "2.98")
        self.assertEqual(self.run_cli("can-run")[0], 1)
        self.mm.enqueue({"op": "budget", "args": {"usd_per_day": 10}})
        self.mm.enqueue({"op": "system", "args": {"state": "paused"}})
        self.run_cli("apply")
        rc, out = self.run_cli("can-run")
        self.assertEqual((rc, out), (1, "PAUSED"))

    def test_cycle_cap_uses_what_is_left_today(self):
        # regression: per-cycle == per-day used to block every cycle after the first spend
        self.run_cli("init")
        self.mm.enqueue({"op": "budget", "args": {"usd_per_day": 20, "usd_per_cycle": 20}})
        self.run_cli("apply")
        self.run_cli("usage", "--usd", "5.07")
        self.assertEqual(self.run_cli("can-run")[0], 0)
        self.assertEqual(self.run_cli("cycle-cap")[1], "6.6667")  # never more than 1/3 of the day
        self.mm.enqueue({"op": "budget", "args": {"usd_per_cycle": 2}})
        self.run_cli("apply")
        self.assertEqual(self.run_cli("cycle-cap")[1], "2.0000")
        self.run_cli("usage", "--usd", "14.90")
        rc, out = self.run_cli("can-run")
        self.assertEqual(rc, 1)
        self.assertIn("BUDGET esaurito", out)

    def test_bandit_prefers_revenue_and_respects_weight(self):
        self.run_cli("init")
        s = self.mm.load()
        for st in s["strategies"].values():
            st["pulls"] = 10
        s["ledger"].append({"id": "t", "date": "2026-01-01", "type": "revenue", "amount_eur": 800,
                            "strategy": "mean-reversion", "source": "x"})
        self.assertEqual(self.mm.allocate(s, 1)[0]["strategy"], "mean-reversion")
        s["strategies"]["mean-reversion"]["weight"] = 0
        self.assertNotIn("mean-reversion", [r["strategy"] for r in self.mm.allocate(s, 0)])

    def test_begin_cycle_brief_matches_pulls(self):
        self.run_cli("init")
        s = self.mm.load()
        s["ledger"].append({"id": "t", "date": "2026-01-01", "type": "revenue", "amount_eur": 50,
                            "strategy": "smart-dca", "source": "x"})
        self.mm.save(s)
        _, out = self.run_cli("begin-cycle")
        pulled = [n for n, st in self.state()["strategies"].items() if st["pulls"]]
        self.assertIn("smart-dca", pulled)
        for n in pulled:
            self.assertIn(n, out)
        self.assertIn("ciclo 1", out)

    def test_ceo_report(self):
        self.run_cli("init")
        self.run_cli("begin-cycle")
        rc, out = self.run_cli("report", json.dumps({"done": ["x"]}))
        self.assertEqual(rc, 1)  # headline is mandatory
        rep = {"headline": "Pubblicato il kit Notion", "done": ["a", "", "b"], "next": "c", "needs_you": []}
        self.assertEqual(self.run_cli("report", json.dumps(rep))[0], 0)
        self.run_cli("report", json.dumps(dict(rep, headline="corretto")))  # same cycle: replaced
        self.run_cli("usage", "--usd", "0.3")
        s = self.state()
        self.assertEqual(len(s["reports"]), 1)
        r = s["reports"][0]
        self.assertEqual((r["cycle"], r["headline"], r["done"], r["next"], r["usd"]), (1, "corretto", ["a", "b"], ["c"], 0.3))
        self.assertIsNotNone(s["last_cycle"])
        self.run_cli("end-cycle", "--summary", "saltato: BUDGET esaurito")
        self.assertEqual(self.state()["last_skip"]["reason"], "BUDGET esaurito")
        for _ in range(40):
            self.run_cli("begin-cycle")
            self.run_cli("report", json.dumps({"headline": "h"}))
        self.assertEqual(len(self.state()["reports"]), 30)

    def hook(self, payload):
        import io
        old = sys.stdin
        sys.stdin = io.StringIO(json.dumps(payload))
        try:
            self.run_cli("live", "hook")
        finally:
            sys.stdin = old

    def test_live_view_follows_subagents(self):
        self.run_cli("init")
        self.hook({"hook_event_name": "SubagentStart", "agent_type": "crypto-machine:quant-dev"})
        self.assertIsNone(self.mm.live_load())  # no cycle running: hooks do nothing
        self.run_cli("live", "begin", "--run", "123", "--url", "https://x/runs/123")
        self.run_cli("begin-cycle")  # idempotent with the same running view
        L = self.mm.live_load()
        self.assertEqual((L["running"], L["run_id"], L["agents"]["ceo"]["status"]), (True, "123", "working"))
        # payloads as captured from Claude Code 2.1
        self.hook({"hook_event_name": "PreToolUse", "tool_name": "Agent",
                   "tool_input": {"description": "Costruisci la checklist", "subagent_type": "crypto-machine:quant-dev"}})
        self.hook({"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "crypto-machine:quant-dev"})
        b = self.mm.live_load()["agents"]["quant-dev"]
        self.assertEqual((b["status"], b["task"]), ("working", "Costruisci la checklist"))
        self.run_cli("log", "quant-dev", "file creati")
        self.hook({"hook_event_name": "SubagentStop", "agent_id": "a1", "agent_type": "crypto-machine:quant-dev",
                   "last_assistant_message": "Checklist pronta\nin products/"})
        L = self.mm.live_load()
        self.assertEqual(L["agents"]["quant-dev"]["status"], "idle")
        self.assertEqual(L["agents"]["quant-dev"]["last"], "Checklist pronta in products/")
        msgs = [e["msg"] for e in L["events"]]
        self.assertIn("delega a quant-dev: Costruisci la checklist", msgs)
        self.assertIn("file creati", msgs)
        self.run_cli("live", "end", "--result", "ok")
        L = self.mm.live_load()
        self.assertFalse(L["running"])
        self.assertTrue(all(a["status"] == "idle" for a in L["agents"].values()))
        # a broken payload must never raise
        import io
        old = sys.stdin
        sys.stdin = io.StringIO("not json")
        try:
            self.assertEqual(self.run_cli("live", "hook")[0], 0)
        finally:
            sys.stdin = old

    def test_ledger_ref_is_idempotent_and_fiscal_year_counts(self):
        self.run_cli("init")
        sale = {"type": "revenue", "amount_eur": 10.5, "source": "gumroad", "kind": "trading",
                "ref": "gumroad:abc", "date": "2026-03-02"}
        self.run_cli("ledger", json.dumps(sale))
        _, out = self.run_cli("ledger", json.dumps(sale))
        self.assertIn("già registrato", out)
        self.run_cli("ledger", json.dumps({"type": "revenue", "amount_eur": 6000, "source": "upwork",
                                           "kind": "staking", "date": "2026-05-10"}))
        self.run_cli("ledger", json.dumps({"type": "revenue", "amount_eur": 99, "source": "gumroad",
                                           "date": "2025-12-31"}))
        led = self.state()["ledger"]
        self.assertEqual(len(led), 3)
        _, out = self.run_cli("fisco", "--year", "2026", "--json")
        f = json.loads(out)
        self.assertEqual(f["revenue_eur"], 6010.5)
        self.assertEqual(f["transactions"], 2)
        self.assertEqual(f["active_months"], 2)
        self.assertEqual(f["by_kind"], {"trading": 10.5, "staking": 6000})
        _, txt = self.run_cli("fisco", "--year", "2025")
        self.assertIn("99.00€", txt)
        self.assertIn("non indicato", txt)

    def test_blockers_lifecycle_and_brief(self):
        self.run_cli("init")
        _, out = self.run_cli("blocker", json.dumps({"title": "Token Gumroad mancante", "blocks": ["opp_a", "incassi automatici"],
                                                     "owner": "human", "how": "crea il token", "link": "javascript:x",
                                                     "id": "blk_gumroad_token"}))
        self.assertIn("blk_gumroad_token", out)
        _, dup = self.run_cli("blocker", json.dumps({"title": "Token Gumroad mancante"}))
        self.assertIn("già aperto", dup)
        b = self.state()["blockers"][0]
        self.assertEqual((b["owner"], b["link"], b["blocks"]), ("human", "", ["opp_a", "incassi automatici"]))
        _, brief = self.run_cli("brief")
        self.assertIn("Blocchi aperti", brief)
        self.assertIn("blk_gumroad_token [umano] Token Gumroad mancante", brief)
        self.mm.enqueue({"op": "blocker_done", "args": {"id": "blk_gumroad_token"}})
        self.mm.enqueue({"op": "blocker_add", "args": {"title": "Iscrizione Xero", "owner": "agent"}})
        self.run_cli("apply")
        bl = self.state()["blockers"]
        self.assertEqual(bl[0]["status"], "done")
        self.assertTrue(bl[1]["id"].startswith("blk_") and bl[1]["owner"] == "agent")
        _, brief = self.run_cli("brief")
        self.assertNotIn("[umano] Token Gumroad", brief)
        self.run_cli("unblock", bl[1]["id"])
        _, brief = self.run_cli("brief")
        self.assertNotIn("Blocchi aperti", brief)

    def test_sales_team_reports_brief_and_agent_migration(self):
        self.run_cli("init")
        st = self.state()
        del st["agents"]["yield-scout"]  # an older state without the sales team
        with open(self.mm.STATE_FILE, "w") as f:
            json.dump(st, f)
        self.run_cli("report", json.dumps({"headline": "prodotto ok"}))
        self.run_cli("report", json.dumps({"headline": "vendite ok", "team": "rendite"}))
        self.run_cli("report", json.dumps({"headline": "vendite ok 2", "team": "rendite"}))
        s = self.state()
        self.assertIn("yield-scout", s["agents"])
        self.assertEqual([(r["team"], r["headline"]) for r in s["reports"]], [("trading", "prodotto ok"), ("rendite", "vendite ok 2")])
        root = tempfile.mkdtemp()
        os.makedirs(os.path.join(root, "products", "opp_a"))
        with open(os.path.join(root, "products", "opp_a", "paper.json"), "w") as f:
            json.dump({"metrics": {"return": 0.052, "hold_return": 0.01, "days": 20}}, f)
        os.makedirs(os.path.join(root, "state", "market"))
        with open(os.path.join(root, "state", "market", "yields.json"), "w") as f:
            json.dump({"date": "2026-10-01", "stable": [{"project": "aave-v3", "chain": "Ethereum", "symbol": "USDC",
                       "apy_30d": 4.1, "apy_reward": 0, "tvl_musd": 900}], "majors": []}, f)
        s["opportunities"].append({"id": "opp_a", "title": "Trend BTC", "stage": "live", "score": 1})
        s["ledger"].append({"type": "revenue", "amount_eur": 10.9, "opportunity": "opp_a", "date": self.mm.today(), "kind": "staking"})
        txt = self.mm.growth_brief(s, root)
        self.assertIn("opp_a [live] Trend BTC · paper +5.2% vs hold +1.0% in 20g", txt)
        self.assertIn("[stable] aave-v3 Ethereum USDC APY30g 4.1%", txt)
        self.assertIn("staking/airdrop registrati dal proprietario: 1 voci, 10.90€", txt)
        _, out = self.run_cli("approval", json.dumps({"kind": "publish", "title": "Pagina CRM", "channel": "site", "target": "opp_a"}))
        ap = self.state()["approvals"][-1]
        self.assertEqual((ap["channel"], ap["target"]), ("site", "opp_a"))

    def test_quality_factor_rewards_paying_demand_niche_and_portfolio(self):
        base = {"expected_eur": 150, "confidence": .4, "effort_h": 4, "days_to_cash": 7}
        plain = self.mm.opp_score(base)
        self.assertEqual(self.mm.quality_factor(base), 1.0)  # old opportunities keep their score
        strong = self.mm.opp_score({**base, "evidence_score": .9, "niche_specificity": .9, "related_to": ["opp_a"], "bundle_potential": .8})
        weak = self.mm.opp_score({**base, "evidence_score": .1, "niche_specificity": .1, "competitors": 20})
        self.assertTrue(weak < plain < strong <= 100)
        self.assertEqual(self.mm.quality_factor({"evidence_score": "boh"}), 1.0)

    def test_attribution_learnings_and_focus(self):
        self.run_cli("init")
        self.run_cli("opp", json.dumps({"id": "opp_a", "title": "CRM", "strategy": "trend-following", "stage": "live"}))
        for amt in (10.9, 5):
            self.run_cli("ledger", json.dumps({"type": "revenue", "amount_eur": amt, "source": "polar", "opportunity": "opp_a"}))
        self.run_cli("ledger", json.dumps({"type": "revenue", "amount_eur": 3, "source": "affiliazione"}))
        att = self.mm.attribution(self.state())
        self.assertEqual([(r["title"], r["revenue_eur"], r["orders"], r["strategy"]) for r in att],
                         [("CRM", 15.9, 2, "trend-following"), ("affiliazione", 3, 1, None)])
        _, out = self.run_cli("learn", "Su r/freelance i link diretti sono vietati: solo nel profilo", "--agent", "airdrop-scout")
        self.assertIn("registrata", out)
        _, dup = self.run_cli("learn", "su r/freelance i link diretti sono vietati: solo nel profilo")
        self.assertIn("già", dup)
        self.mm.enqueue({"op": "focus", "args": {"strategies": ["trend-following", "nonexistent"]}})
        self.run_cli("apply")
        st = self.state()
        self.assertEqual(st["focus"]["strategies"], ["trend-following"])
        self.assertEqual({r["strategy"] for r in self.mm.allocate(st, 0)}, {"trend-following"})
        _, brief = self.run_cli("brief")
        self.assertIn("FOCUS del proprietario: lavora solo su trend-following", brief)
        self.assertIn("i link diretti sono vietati", brief)
        self.mm.enqueue({"op": "focus", "args": {"strategies": []}})
        self.run_cli("apply")
        st = self.state()
        self.assertIsNone(st["focus"])
        self.assertTrue(all(v["weight"] == 1.0 for v in st["strategies"].values()))

    def test_cycles_are_skipped_only_while_waiting_with_nothing_new(self):
        self.run_cli("init")
        rc, out = self.run_cli("can-run")  # first run ever: runs
        self.assertEqual(rc, 0, out)
        rc, _ = self.run_cli("can-run")  # nothing pending: runs
        self.assertEqual(rc, 0)
        self.run_cli("approval", json.dumps({"kind": "publish", "title": "Pubblica X"}), "--agent", "ceo")
        rc, out = self.run_cli("can-run")
        self.assertEqual(rc, 1)
        self.assertIn("NIENTE DA FARE", out)
        self.assertEqual(self.run_cli("can-run", "--team", "rendite")[0], 0)  # the other team is not waiting on it
        self.assertEqual(self.run_cli("can-run", "--force")[0], 0)  # manual runs never skip
        self.run_cli("approval", json.dumps({"kind": "publish", "title": "Pubblica Y"}), "--agent", "ceo")
        for _ in range(self.mm.MAX_SKIPS):
            self.assertEqual(self.run_cli("can-run")[0], 1)
        self.assertEqual(self.run_cli("can-run")[0], 0)  # after MAX_SKIPS it runs anyway
        self.mm.enqueue({"op": "directive_add", "args": {"text": "nuova direttiva"}})
        self.run_cli("apply")  # the owner did something: next cycle runs
        self.assertEqual(self.run_cli("can-run")[0], 0)

    def test_usage_from_result(self):
        self.run_cli("init")
        f = os.path.join(self.tmp, "r.json")
        with open(f, "w") as fh:
            json.dump({"type": "result", "total_cost_usd": 0.12, "usage": {"input_tokens": 100, "output_tokens": 50}}, fh)
        self.run_cli("usage-from-result", f)
        b = self.state()["budget"]
        self.assertAlmostEqual(b["usd_today"], 0.12)
        self.assertEqual(b["tokens_total"], 150)


if __name__ == "__main__":
    unittest.main()


class ConsistencyAndWipTest(unittest.TestCase):
    def setUp(self):
        import mm
        self.tmp = tempfile.mkdtemp()
        mm.STATE_DIR = os.path.join(self.tmp, "state")
        os.makedirs(mm.STATE_DIR)
        mm.STATE_FILE = os.path.join(mm.STATE_DIR, "state.json")
        mm.INBOX_FILE = os.path.join(mm.STATE_DIR, "inbox.jsonl")
        mm.LOCK_FILE = os.path.join(mm.STATE_DIR, ".lock")
        mm.LIVE_FILE = os.path.join(mm.STATE_DIR, "live.json")
        mm.REPO_ROOT = None  # the folder that contains state/
        self.mm = mm

    def tearDown(self):
        self.mm.REPO_ROOT = None

    def write(self, rel, text="x"):
        p = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)

    def cli(self, *args):
        with redirect_stdout(StringIO()) as out:
            rc = self.mm.main(list(args))
        return rc, out.getvalue().strip()

    def stage(self, opp):
        with open(self.mm.STATE_FILE) as f:
            return self.mm.find(json.load(f)["opportunities"], opp)["stage"]

    def test_live_means_buyable_and_checks_find_forgotten_work(self):
        """live = approved by the owner (live.json); paper only with a backtest PASS; ready work is reported."""
        os.makedirs(os.path.join(self.tmp, "products"))
        for oid, st in (("opp_ok", "validating"), ("opp_nolive", "live"), ("opp_app", "awaiting_approval"),
                        ("opp_fail", "building"), ("opp_old", "building")):
            self.cli("opp", json.dumps({"id": oid, "title": oid, "stage": st}))
        self.write("products/opp_ok/backtest.json", '{"verdict": "PASS", "rules": 2}')
        self.write("products/opp_nolive/backtest.json", '{"verdict": "PASS", "rules": 2}')
        self.write("products/opp_app/live.json", '{"approved": true, "capital_eur": 200}')
        self.write("products/opp_fail/backtest.json", '{"verdict": "FAIL"}')
        self.write("products/opp_old/backtest.json", '{"verdict": "PASS", "rules": 2}')
        self.write("products/opp_old/paper.json", '{"metrics": {"return": 0.03, "hold_return": 0.01, "days": 15}}')
        rc, out = self.cli("apply")
        self.assertEqual(self.stage("opp_nolive"), "building")  # not approved by the owner
        self.assertEqual(self.stage("opp_app"), "live")          # live.json from an approval
        self.assertEqual(self.stage("opp_fail"), "validating")   # no paper trading without PASS
        self.assertEqual(self.stage("opp_ok"), "validating")
        rc, brief = self.cli("brief")
        self.assertIn("opp_ok ha un backtest PASS", brief)
        self.assertIn("opp_old è in paper trading da 15 giorni", brief)
        self.assertIn("LIMITE LAVORI IN CORSO", brief)
        # asking for the go-live approval clears the item
        self.cli("approval", json.dumps({"kind": "golive", "channel": "golive", "title": "Live opp_old", "opportunity": "opp_old", "capital_eur": 100}))
        self.cli("apply")
        rc, brief = self.cli("brief")
        self.assertNotIn("opp_old è in paper", brief)

    def test_wip_limit_refuses_new_research_but_not_the_owner(self):
        for i in range(3):
            self.cli("opp", json.dumps({"id": f"opp_{i}", "title": f"idea {i}", "stage": "validating"}))
        rc, out = self.cli("market", json.dumps({"name": "nuovo", "demand": 3}), "--agent", "market-scanner")
        self.assertEqual(rc, 1)
        self.assertIn("RIFIUTATO", out)
        rc, out = self.cli("opp", json.dumps({"title": "altra idea"}), "--agent", "quant-analyst")
        self.assertEqual(rc, 1)
        rc, out = self.cli("opp", json.dumps({"id": "opp_0", "confidence": 0.5}), "--agent", "quant-analyst")
        self.assertEqual(rc, 0)  # updating existing work is always allowed
        rc, out = self.cli("market", json.dumps({"name": "idea del proprietario"}), "--agent", "human")
        self.assertEqual(rc, 0)
        self.cli("stage", "opp_1", "killed")
        rc, out = self.cli("market", json.dumps({"name": "nuovo", "demand": 3}), "--agent", "market-scanner")
        self.assertEqual(rc, 0)


class WeakModelGuardTest(ConsistencyAndWipTest):
    """A weak AI model must not be able to dirty the state with empty shells or made-up stages."""

    def test_empty_or_invalid_opportunities_are_refused(self):
        os.makedirs(os.path.join(self.tmp, "products"))
        rc, out = self.cli("opp", json.dumps({"stage": "idea", "strategy": "trend-following"}), "--agent", "ceo")
        self.assertEqual(rc, 1)
        self.assertIn("titolo", out)
        rc, out = self.cli("opp", json.dumps({"title": "Trend BTC", "stage": "*"}), "--agent", "ceo")
        self.assertEqual(rc, 1)
        self.assertIn("non valida", out)
        rc, out = self.cli("opp", json.dumps({"id": "../etc", "title": "Trend BTC"}), "--agent", "ceo")
        self.assertEqual(rc, 1)
        with open(self.mm.STATE_FILE) as f:
            self.assertEqual(json.load(f)["opportunities"], [])
        rc, out = self.cli("opp", json.dumps({"id": "opp_ok", "title": "Trend BTC"}), "--agent", "ceo")
        self.assertEqual(rc, 0)
        rc, out = self.cli("opp", json.dumps({"id": "opp_ok", "confidence": 0.4}), "--agent", "ceo")  # update keeps the title
        self.assertEqual(rc, 0)

    def test_waiting_for_an_ok_nobody_asked_for_is_undone(self):
        os.makedirs(os.path.join(self.tmp, "products"))
        self.cli("opp", json.dumps({"id": "opp_w", "title": "Trend BTC", "stage": "awaiting_approval"}))
        self.cli("apply")
        self.assertEqual(self.stage("opp_w"), "validating")
        self.write("products/opp_w/backtest.json", '{"verdict": "PASS", "rules": 2}')
        self.cli("approval", json.dumps({"kind": "golive", "title": "Live Trend BTC", "opportunity": "opp_w", "channel": "golive"}))
        self.cli("apply")
        self.assertEqual(self.stage("opp_w"), "awaiting_approval")  # a real request keeps it waiting


class CostPerAgentTest(unittest.TestCase):
    def test_real_cost_is_split_among_the_agents_that_used_it(self):
        import mm
        tmp = tempfile.mkdtemp()
        mm.STATE_DIR, mm.STATE_FILE = tmp, os.path.join(tmp, "state.json")
        mm.INBOX_FILE, mm.LOCK_FILE, mm.LIVE_FILE = (os.path.join(tmp, n) for n in ("inbox.jsonl", ".lock", "live.json"))
        tr = os.path.join(tmp, "agent-1.jsonl")
        with open(tr, "w") as f:
            u = {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
            for _ in range(2):  # the same API message is written once per content block: count it once
                f.write(json.dumps({"type": "assistant", "message": {"id": "m1", "model": "claude-haiku-4-5", "usage": u}}) + "\n")
            f.write("not json\n")
        with redirect_stdout(StringIO()):
            mm.main(["live", "begin", "--run", "r1"])
            mm.live_hook({"hook_event_name": "SubagentStart", "agent_type": "crypto-machine:market-scanner"})
            mm.live_hook({"hook_event_name": "SubagentStop", "agent_type": "crypto-machine:market-scanner", "agent_transcript_path": tr})
        res = {"type": "result", "total_cost_usd": 1.0, "usage": {"input_tokens": 10},
               "modelUsage": {"claude-haiku-4-5": {"inputTokens": 4000, "outputTokens": 800, "cacheReadInputTokens": 0,
                                                   "cacheCreationInputTokens": 0, "costUSD": 0.2},
                              "claude-sonnet-4-5": {"inputTokens": 5000, "outputTokens": 1000, "costUSD": 0.8}}}
        out = os.path.join(tmp, "res.json")
        with open(out, "w") as f:
            json.dump(res, f)
        with redirect_stdout(StringIO()):
            mm.main(["usage-from-result", out])
        with open(mm.STATE_FILE) as f:
            s = json.load(f)
        self.assertAlmostEqual(s["agents"]["market-scanner"]["usd"], 0.05, places=4)  # 1/4 of haiku's cost
        self.assertAlmostEqual(s["agents"]["ceo"]["usd"], 0.95, places=4)          # the rest
        self.assertEqual((s["agents"]["market-scanner"]["runs"], s["agents"]["ceo"]["runs"]), (1, 1))
        self.assertEqual(s["budget"]["tokens_total"], 10800)  # whole tree, not just the top-level "usage"
        self.assertAlmostEqual(s["budget"]["usd_total"], 1.0)


class LiteVariantTest(ConsistencyAndWipTest):
    def test_lite_version_of_a_product_on_sale_skips_the_wip_limit(self):
        self.cli("opp", json.dumps({"id": "opp_full", "title": "completo", "stage": "live"}))
        for i in range(3):
            self.cli("opp", json.dumps({"id": f"opp_{i}", "title": f"idea {i}", "stage": "validating"}))
        rc, _ = self.cli("opp", json.dumps({"title": "altro"}), "--agent", "ceo")
        self.assertEqual(rc, 1)
        rc, _ = self.cli("opp", json.dumps({"title": "completo lite", "variant_of": "opp_full"}), "--agent", "ceo")
        self.assertEqual(rc, 0)
        rc, _ = self.cli("opp", json.dumps({"title": "lite di niente", "variant_of": "opp_0"}), "--agent", "ceo")
        self.assertEqual(rc, 1)  # opp_0 is not on sale
