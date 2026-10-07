import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))


class GuardTest(unittest.TestCase):
    def setUp(self):
        import mm
        import guard
        self.root = root = tempfile.mkdtemp()
        st = os.path.join(root, "state")
        os.makedirs(st)
        mm.STATE_DIR, mm.STATE_FILE = st, os.path.join(st, "state.json")
        mm.INBOX_FILE, mm.LOCK_FILE = os.path.join(st, "inbox.jsonl"), os.path.join(st, ".lock")
        mm.LIVE_FILE = os.path.join(st, "live.json")
        os.makedirs(os.path.join(root, "site", "vecchia"))
        open(os.path.join(root, "site", "vecchia", ".approved"), "w").close()
        self.mm, self.guard = mm, guard

    def cli(self, *args):
        with redirect_stdout(StringIO()) as out:
            self.mm.main(list(args))
        return out.getvalue().strip()

    def state(self):
        with open(self.mm.STATE_FILE) as f:
            return json.load(f)

    def test_agents_cannot_approve_publish_or_book_revenue(self):
        human_ok = json.loads(self.cli("approval", json.dumps({"kind": "publish", "title": "Già decisa"})))["id"]
        self.mm.enqueue({"op": "approval", "args": {"id": human_ok, "decision": "approved"}})
        self.cli("apply")  # decided BEFORE the agents' turn: legitimate
        self.cli("ledger", json.dumps({"type": "revenue", "amount_eur": 5, "source": "kraken"}))
        snap = os.path.join(self.root, "snap.json")
        self.guard.snapshot(snap, self.root)

        # --- agents' turn: they try every shortcut
        sneaky = json.loads(self.cli("approval", json.dumps({"kind": "publish", "title": "Pubblica pagina", "channel": "site"})))["id"]
        self.mm.enqueue({"op": "approval", "args": {"id": sneaky, "decision": "approved"}})
        self.cli("apply")
        os.makedirs(os.path.join(self.root, "site", "nuova"))
        open(os.path.join(self.root, "site", "nuova", ".approved"), "w").close()
        os.makedirs(os.path.join(self.root, "products", "opp_x"))
        open(os.path.join(self.root, "products", "opp_x", "live.json"), "w").close()
        self.cli("opp", json.dumps({"id": "opp_x", "title": "x", "stage": "live"}))
        self.cli("signal", json.dumps({"opportunity": "opp_x", "text": "COMPRA tutto"}))
        self.cli("ledger", json.dumps({"type": "revenue", "amount_eur": 999, "source": "inventato"}))
        self.cli("ledger", json.dumps({"type": "cost", "amount_eur": 3, "source": "dominio"}))

        alarms = self.guard.verify(snap, self.root)
        self.assertEqual(len(alarms), 5, alarms)
        s = self.state()
        aps = {a["id"]: a for a in s["approvals"]}
        self.assertEqual(aps[sneaky]["status"], "pending")
        self.assertEqual(aps[human_ok]["status"], "approved")
        self.assertFalse(os.path.exists(os.path.join(self.root, "site", "nuova", ".approved")))
        self.assertFalse(os.path.exists(os.path.join(self.root, "products", "opp_x", "live.json")))
        self.assertEqual(s["signals"], [])
        self.assertTrue(os.path.exists(os.path.join(self.root, "site", "vecchia", ".approved")))
        self.assertEqual(sorted((e["type"], e["amount_eur"]) for e in s["ledger"]), [("cost", 3), ("revenue", 5)])
        self.assertTrue(any("GUARDIA POLICY" in l["msg"] for l in s["log"]))

    def test_clean_turn_changes_nothing(self):
        snap = os.path.join(self.root, "snap.json")
        self.guard.snapshot(snap, self.root)
        self.cli("approval", json.dumps({"kind": "publish", "title": "Chiedo soltanto"}))
        self.assertEqual(self.guard.verify(snap, self.root), [])


if __name__ == "__main__":
    unittest.main()
