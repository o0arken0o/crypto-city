import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))


class SalesRoomTest(unittest.TestCase):
    def setUp(self):
        import mm
        import server
        self.root = root = tempfile.mkdtemp()
        st = os.path.join(root, "state")
        os.makedirs(st)
        mm.STATE_DIR, mm.STATE_FILE = st, os.path.join(st, "state.json")
        mm.INBOX_FILE, mm.LOCK_FILE, mm.LIVE_FILE = (os.path.join(st, n) for n in ("inbox.jsonl", ".lock", "live.json"))
        server.ROOT, server.GH_MODE = root, False
        server._site_cache.clear()
        os.makedirs(os.path.join(root, "products", "opp_a"))
        with open(os.path.join(root, "products", "opp_a", "polar.json"), "w") as f:
            json.dump({"checkout_url": "https://buy.polar.sh/x", "price_eur": 12}, f)
        os.makedirs(os.path.join(root, "site", "opp_a", "public"))
        with open(os.path.join(root, "site", "opp_a", "public", "index.html"), "w") as f:
            f.write("<title>Pagina CRM</title>")
        open(os.path.join(root, "site", "opp_a", ".approved"), "w").close()
        self.mm, self.server = mm, server
        self.cli("opp", json.dumps({"id": "opp_a", "title": "CRM", "stage": "live", "price_eur": 17}))
        self.cli("ledger", json.dumps({"type": "revenue", "amount_eur": 10.9, "source": "polar", "opportunity": "opp_a"}))
        self.cli("blocker", json.dumps({"title": "Pubblica il post su r/freelance", "owner": "human", "blocks": ["opp_a"]}), "--agent", "yield-lead")
        self.cli("blocker", json.dumps({"title": "Token Polar", "owner": "human"}), "--agent", "ceo")
        self.cli("approval", json.dumps({"kind": "publish", "title": "Pagina planner", "channel": "site", "target": "planner"}), "--agent", "yield-lead")
        self.cli("report", json.dumps({"headline": "trading"}))
        self.cli("report", json.dumps({"headline": "rendite", "team": "rendite"}))

    def cli(self, *args):
        with redirect_stdout(StringIO()):
            self.mm.main(list(args))

    def test_sales_world(self):
        """The yield room: public yields in the vending machine, research notes on the wall, owner to-dos, real results."""
        os.makedirs(os.path.join(self.root, "state", "market"), exist_ok=True)
        with open(os.path.join(self.root, "state", "market", "yields.json"), "w") as f:
            json.dump({"date": "2026-10-01", "stable": [{"project": "aave-v3", "chain": "Ethereum", "symbol": "USDC", "apy_30d": 4.1,
                       "apy_reward": 0, "tvl_musd": 900}], "majors": [{"project": "lido", "chain": "Ethereum", "symbol": "STETH",
                       "apy_30d": 2.9, "apy_reward": 0, "tvl_musd": 20000}]}, f)
        os.makedirs(os.path.join(self.root, "state", "research"), exist_ok=True)
        with open(os.path.join(self.root, "state", "research", "yields-2026-10-01.md"), "w") as f:
            f.write("# Rendimenti DeFi del 1 ottobre\n")
        with open(os.path.join(self.root, "state", "research", "market-btc.md"), "w") as f:
            f.write("# altro team\n")
        self.server._site_cache.clear()
        snap = self.server.live_snapshot("rendite")
        w = snap["world"]
        self.assertEqual([(p["title"], p["apy"], p["kind"]) for p in w["products"]],
                         [("aave-v3 · USDC", 4.1, "stablecoin"), ("lido · STETH", 2.9, "crypto principali")])
        self.assertEqual([(p["slug"], p["title"]) for p in w["pages"]], [("yields-2026-10-01", "Rendimenti DeFi del 1 ottobre")])
        self.assertEqual([p["title"] for p in w["posts"]], ["Pubblica il post su r/freelance", "Pagina planner"])  # only the yield team's
        self.assertEqual((w["revenue_eur"], w["orders"], w["pending_approvals"]), (10.9, 1, 1))
        self.assertEqual(snap["report"]["headline"], "rendite")
        self.assertEqual(self.server.live_snapshot()["report"]["headline"], "trading")

    def test_each_room_lights_up_only_for_its_team(self):
        self.mm.live_begin("r1", "", "rendite")
        sales, product = self.server.live_snapshot("rendite"), self.server.live_snapshot("trading")
        self.assertEqual(sales["phase"], "working")
        self.assertEqual(product["phase"], "idle")
        self.assertEqual(product["other_team"], "rendite")
        self.assertEqual(self.mm.live_load()["agents"]["yield-lead"]["status"], "working")
        self.assertEqual(self.mm.live_load()["events"][0]["agent"], "yield-lead")


if __name__ == "__main__":
    unittest.main()


class ShopNameAndSocialTest(SalesRoomTest):
    """Rooms show the shop name, count every social post the owner marked done, and show the real slides."""

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.root, "products", "opp_abc123"))
        with open(os.path.join(self.root, "products", "opp_abc123", "polar.json"), "w") as f:
            json.dump({"checkout_url": "https://buy.polar.sh/y", "price_eur": 8}, f)
        self.cli("opp", json.dumps({"id": "opp_abc123", "title": "Late payment pack", "stage": "live", "price_eur": 8}))

    def test_shop_name_replaces_the_working_title(self):
        with open(os.path.join(self.root, "products", "opp_abc123", "store.json"), "w") as f:
            json.dump({"name": "CRM Excel per freelance"}, f)
        self.server._site_cache.clear()
        opps = {o["id"]: o for o in self.server.snapshot()["state"]["opportunities"]}
        self.assertEqual((opps["opp_abc123"]["title"], opps["opp_abc123"]["work_title"]), ("CRM Excel per freelance", "Late payment pack"))

    def test_owner_post_counts_whoever_opened_the_reminder(self):
        self.cli("blocker", json.dumps({"title": "Pubblica su LinkedIn il carosello", "owner": "human", "blocks": ["opp_abc123"],
                                        "how": "products/opp_abc123/social/2026-09-28-linkedin/"}), "--agent", "assistente")
        with open(self.mm.STATE_FILE) as f:
            bid = [b for b in json.load(f)["blockers"] if "LinkedIn" in b["title"]][0]["id"]
        self.cli("unblock", bid)
        d = os.path.join(self.root, "products", "opp_abc123", "social", "2026-09-28-linkedin"); os.makedirs(d)
        with open(os.path.join(d, "slide-01.png"), "wb") as f:
            f.write(b"\x89PNG slide")
        self.server._site_cache.clear()
        w = self.server.social_world(self.mm.load())
        self.assertEqual(w["platforms"]["linkedin"]["published"], 1)
        self.assertEqual(w["gallery"], [{"img": "/p/opp_abc123/2026-09-28-linkedin/slide-01.png", "platform": "linkedin",
                                         "date": "2026-09-28", "status": "pubblicato"}])
        self.assertEqual(self.server.social_file(["opp_abc123", "2026-09-28-linkedin", "slide-01.png"])[0], b"\x89PNG slide")
        self.assertIsNone(self.server.social_file(["opp_abc123", "2026-09-28-linkedin", "../polar.json"]))
        self.assertIsNone(self.server.social_file(["opp_abc123", "drafts", "slide-01.png"]))
