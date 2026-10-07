import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))


class SaverModeTest(unittest.TestCase):
    def setUp(self):
        import mm
        st = tempfile.mkdtemp()
        mm.STATE_DIR, mm.STATE_FILE = st, os.path.join(st, "state.json")
        mm.INBOX_FILE, mm.LOCK_FILE, mm.LIVE_FILE = (os.path.join(st, n) for n in ("inbox.jsonl", ".lock", "live.json"))
        self.mm = mm

    def state(self, total, per_day=10.0, revenue_days_ago=None, saver=True):
        s = self.mm.default_state()
        s["budget"].update(usd_total=total, usd_per_day=per_day, usd_per_cycle=5.0, saver=saver)
        if revenue_days_ago is not None:
            s["ledger"].append({"type": "revenue", "amount_eur": 8, "date": (dt.date.today() - dt.timedelta(days=revenue_days_ago)).isoformat()})
        return s

    def test_caps_spend_until_the_first_revenue(self):
        mm = self.mm
        self.assertFalse(mm.saver_active(self.state(5)))  # still exploring: under the threshold
        s = self.state(15)
        self.assertTrue(mm.saver_active(s))
        self.assertEqual(mm.effective_day(s), mm.SAVER_DAY_USD)
        self.assertAlmostEqual(mm.cycle_cap(s), round(mm.SAVER_DAY_USD / 3, 4))
        self.assertIn("modalità risparmio", mm.saver_note(s))
        self.assertFalse(mm.saver_active(self.state(15, revenue_days_ago=3)))   # a real sale switches it off
        self.assertTrue(mm.saver_active(self.state(15, revenue_days_ago=40)))   # ...but only a recent one
        self.assertFalse(mm.saver_active(self.state(15, saver=False)))          # the owner switched it off
        self.assertEqual(mm.effective_day(self.state(15, per_day=1.0)), 1.0)    # never raises a lower budget
        self.assertEqual(mm.saver_note(self.state(15, per_day=1.0)), "")

    def test_owner_toggles_it_from_the_panel(self):
        mm = self.mm
        s = self.state(15)
        mm.save(s)
        with open(mm.INBOX_FILE, "w") as f:
            f.write(json.dumps({"op": "budget", "args": {"saver": False}}) + "\n")
        with redirect_stdout(StringIO()):
            mm.main(["apply"])
        s = mm.load()
        self.assertFalse(s["budget"]["saver"])
        self.assertEqual(mm.effective_day(s), 10.0)
        self.assertEqual(mm.kpis(s)["saver"]["active"], False)

    def test_old_states_get_it_switched_on(self):
        s = self.mm.default_state(); del s["budget"]["saver"]; s["budget"]["usd_total"] = 15
        self.assertTrue(self.mm.saver_active(s))


if __name__ == "__main__":
    unittest.main()
