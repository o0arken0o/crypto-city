import datetime as dt
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))


def issue(n, op, args, hours_ago, state="open", assoc="OWNER"):
    ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"number": n, "state": state, "title": f"mm: {op}", "author_association": assoc, "created_at": ts,
            "body": "```json\n" + json.dumps({"op": op, "args": args}) + "\n```"}


class ApplyIssuesTest(unittest.TestCase):
    def setUp(self):
        import mm
        import apply_issues
        tmp = tempfile.mkdtemp()
        mm.STATE_DIR, mm.STATE_FILE = tmp, os.path.join(tmp, "state.json")
        mm.INBOX_FILE, mm.LOCK_FILE = os.path.join(tmp, "inbox.jsonl"), os.path.join(tmp, ".lock")
        apply_issues.OUT = os.path.join(tmp, "out.json")
        self.mm, self.ai = mm, apply_issues

    def run_with(self, issues):
        self.ai.command_issues = lambda since: issues
        self.ai.cmd_apply()
        with open(self.ai.OUT) as f:
            return {r["number"]: r for r in json.load(f)}

    def test_stale_setting_is_superseded_additive_is_applied(self):
        s = self.mm.default_state()
        s["budget"]["usd_per_cycle"] = 5.0
        self.mm.save(s)
        out = self.run_with([
            issue(6, "budget", {"usd_per_cycle": 0.5}, 11),
            issue(9, "budget", {"usd_per_cycle": 5}, 4, state="closed"),
            issue(20, "directive_add", {"text": "solo B2B"}, 1),
            issue(21, "agent", {"name": "risk-manager", "status": "paused"}, 0.5),
            issue(22, "agent", {"name": "risk-manager", "status": "active"}, 0.4),
            issue(23, "agent", {"name": "quant-dev", "status": "paused"}, 30),
            issue(24, "system", {"state": "paused"}, 0.1, assoc="NONE"),
            issue(25, "directive_remove", {"id": "x"}, 0.1, assoc="NONE"),
            issue(26, "agent", {"name": "market-scanner", "status": "paused"}, 0.3),
            issue(27, "agent", {"name": "market-scanner", "status": "active"}, 0.2, assoc="NONE"),
        ])
        s = self.mm.load()
        self.assertFalse(out[6]["applied"])
        self.assertEqual(s["budget"]["usd_per_cycle"], 5.0)
        self.assertTrue(out[20]["applied"])
        self.assertEqual([d["text"] for d in s["directives"]], ["solo B2B"])
        self.assertFalse(out[21]["applied"])
        self.assertTrue(out[22]["applied"])
        self.assertFalse(out[23]["applied"])
        self.assertEqual(s["agents"]["quant-dev"]["status"], "active")
        self.assertNotIn(24, out)  # not the owner: ignored entirely
        self.assertEqual(s["status"], "running")
        # a stranger's newer issue must not supersede the owner's command
        self.assertTrue(out[26]["applied"])
        self.assertEqual(s["agents"]["market-scanner"]["status"], "paused")
        self.assertNotIn(27, out)


if __name__ == "__main__":
    unittest.main()
