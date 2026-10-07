import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))


class ActionsTest(unittest.TestCase):
    def setUp(self):
        import mm
        import actions
        self.tmp = tmp = tempfile.mkdtemp()
        mm.STATE_DIR, mm.STATE_FILE = tmp, os.path.join(tmp, "state.json")
        mm.INBOX_FILE, mm.LOCK_FILE = os.path.join(tmp, "inbox.jsonl"), os.path.join(tmp, ".lock")
        mm.LIVE_FILE = os.path.join(tmp, "live.json")
        actions.SITE = os.path.join(tmp, "site")
        os.makedirs(os.path.join(actions.SITE, "guida-crm", "public"))
        open(os.path.join(actions.SITE, "guida-crm", "public", "index.html"), "w").close()
        self.mm, self.actions = mm, actions

    def cli(self, *args):
        with redirect_stdout(StringIO()) as out:
            self.mm.main(list(args))
        return out.getvalue().strip()

    def ask(self, channel, target=None, opp=None, decision="approved", **extra):
        ap = {"kind": "publish", "title": f"Azione {channel} {target or opp}", "channel": channel, "target": target, "opportunity": opp, **extra}
        apr = json.loads(self.cli("approval", json.dumps(ap)))["id"]
        if decision:
            self.mm.enqueue({"op": "approval", "args": {"id": apr, "decision": decision}})
            self.cli("apply")
        return apr

    def run_(self):
        with redirect_stdout(StringIO()):
            return self.actions.run_approved()

    def approvals(self):
        with open(self.mm.STATE_FILE) as f:
            return {a["id"]: a for a in json.load(f)["approvals"]}

    def test_site_page_only_after_approval_and_only_once(self):
        pending = self.ask("site", "guida-crm", decision=None)
        rejected = self.ask("site", "guida-crm", decision="rejected")
        self.assertEqual(self.run_(), [])
        marker = os.path.join(self.actions.SITE, "guida-crm", ".approved")
        self.assertFalse(os.path.exists(marker))
        ok = self.ask("site", "guida-crm")
        out = self.run_()
        self.assertTrue(os.path.exists(marker), out)
        aps = self.approvals()
        self.assertTrue(aps[ok]["consumed"])
        self.assertFalse(aps[pending].get("consumed") or aps[rejected].get("consumed"))
        self.assertEqual(self.run_(), [])

    def test_bad_slug_or_missing_page_is_archived_not_published(self):
        a1 = self.ask("site", "../etc")
        a2 = self.ask("site", "non-esiste")
        out = self.run_()
        self.assertTrue(all("non eseguibile" in x for x in out), out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "etc", ".approved")))
        aps = self.approvals()
        self.assertTrue(aps[a1]["consumed"] and aps[a2]["consumed"])

    def test_golive_writes_live_json_only_after_approval_and_stop_removes_it(self):
        self.actions.ROOT = self.tmp
        d = os.path.join(self.tmp, "products", "opp_abc"); os.makedirs(d)
        open(os.path.join(d, "strategy.py"), "w").close()
        self.cli("opp", json.dumps({"id": "opp_abc", "title": "Trend BTC", "stage": "awaiting_approval"}))
        self.ask("golive", opp="opp_abc", decision="rejected", capital_eur=100)
        self.ask("golive", opp="opp_abc", decision=None, capital_eur=100, title="in attesa")
        self.assertEqual(self.run_(), [])
        self.assertFalse(os.path.exists(os.path.join(d, "live.json")))
        no_cap = self.ask("golive", opp="opp_abc", title="senza capitale")
        self.assertIn("non eseguibile", self.run_()[0])
        ok = self.ask("golive", opp="opp_abc", capital_eur=150, title="ok")
        self.assertIn("capitale massimo 150", self.run_()[0])
        with open(os.path.join(d, "live.json")) as f:
            self.assertEqual(json.load(f)["capital_eur"], 150)
        self.assertTrue(self.approvals()[ok]["consumed"] and self.approvals()[no_cap]["consumed"])
        self.ask("stop", opp="opp_abc")
        self.assertIn("fermata", self.run_()[0])
        self.assertFalse(os.path.exists(os.path.join(d, "live.json")))
        self.assertEqual(self.mm.find(self.mm.load()["opportunities"], "opp_abc")["stage"], "building")

    def test_linkedin_post_waits_for_connection_then_publishes_once(self):
        self.actions.ROOT = self.tmp
        target = "products/opp_xyz/social/2026-10-02-linkedin"
        d = os.path.join(self.tmp, target); os.makedirs(d)
        with open(os.path.join(d, "POST.md"), "w") as f:
            f.write("## Testo da incollare\nCiao\n")
        self.cli("blocker", json.dumps({"title": "Pubblica il post linkedin", "owner": "human", "how": f"testo in {target}/"}), "--agent", "social-lead")
        apr = self.ask("linkedin", target=target)
        with mock.patch.dict(os.environ, {"LINKEDIN_ACCESS_TOKEN": "", "LINKEDIN_PERSON_URN": ""}):
            self.assertIn("in attesa", self.run_()[0])
        self.assertFalse(self.approvals()[apr].get("consumed"))
        import linkedin
        with mock.patch.dict(os.environ, {"LINKEDIN_ACCESS_TOKEN": "t", "LINKEDIN_PERSON_URN": "urn:li:person:p"}), \
                mock.patch.object(linkedin, "publish", lambda folder, api: {"urn": "urn:li:share:1", "url": "https://www.linkedin.com/feed/update/urn:li:share:1/", "kind": "carosello", "published": "x"}):
            out = self.run_()
        self.assertIn("pubblicato su LinkedIn", out[0])
        self.assertTrue(self.approvals()[apr]["consumed"])
        self.assertTrue(os.path.exists(os.path.join(d, "published.json")))
        self.assertTrue(all(b["status"] == "done" for b in self.mm.load()["blockers"]))  # the manual reminder is closed


if __name__ == "__main__":
    unittest.main()
