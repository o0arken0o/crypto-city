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


class FakeTG:
    def __init__(self, updates=None):
        self.sent, self.updates = [], updates or []

    def call(self, method, params=None):
        if method == "getUpdates":
            return {"ok": True, "result": self.updates}
        self.sent.append(params)
        return {"ok": True}

    find_chat = __import__("telegram").Telegram.find_chat


class TelegramTest(unittest.TestCase):
    def setUp(self):
        import mm
        import telegram
        tmp = tempfile.mkdtemp()
        mm.STATE_DIR, mm.STATE_FILE = tmp, os.path.join(tmp, "state.json")
        mm.INBOX_FILE, mm.LOCK_FILE, mm.LIVE_FILE = (os.path.join(tmp, n) for n in ("inbox.jsonl", ".lock", "live.json"))
        self.mm, self.tg = mm, telegram
        self.cli("init")
        os.environ.pop("TELEGRAM_CHAT_ID", None)

    def cli(self, *args):
        with redirect_stdout(StringIO()) as out:
            self.mm.main(list(args))
        return out.getvalue().strip()

    def run_(self, fake):
        with redirect_stdout(StringIO()) as out:
            self.tg.main([], tg=fake)
        return out.getvalue()

    def state(self):
        with open(self.mm.STATE_FILE) as f:
            return json.load(f)

    def test_first_message_is_a_welcome_then_only_news(self):
        self.cli("approval", json.dumps({"title": "Pubblica la guida", "kind": "publish"}))
        fake = FakeTG(updates=[{"message": {"chat": {"id": 4242, "type": "private"}, "text": "/start"}}])
        self.run_(fake)
        self.assertEqual(len(fake.sent), 1)
        self.assertEqual(fake.sent[0]["chat_id"], "4242")  # found from the /start message
        self.assertIn("Avvisi di Crypto Machine attivi", fake.sent[0]["text"])
        self.assertIn("Pubblica la guida", fake.sent[0]["text"])
        self.assertEqual(self.state()["notify"]["telegram"]["chat_id"], "4242")  # remembered for later runs

        fake2 = FakeTG()
        self.run_(fake2)
        self.assertEqual(fake2.sent, [])  # nothing new: no message

        self.cli("ledger", json.dumps({"type": "revenue", "amount_eur": 8, "source": "polar"}))
        self.cli("blocker", json.dumps({"title": "Pubblica il post LinkedIn", "owner": "human"}))
        fake3 = FakeTG()
        self.run_(fake3)
        text = fake3.sent[0]["text"]
        self.assertIn("💰 Risultato registrato: 8,00 € (polar)", text)
        self.assertIn("Pubblica il post LinkedIn", text)
        self.assertNotIn("Pubblica la guida", text)  # already announced

        fake4 = FakeTG()
        self.run_(fake4)
        self.assertEqual(fake4.sent, [])  # the sale and the block are not repeated

    def test_buy_clicks_and_social_visits_are_announced_once(self):
        import datetime
        fake = FakeTG(updates=[{"message": {"chat": {"id": 7, "type": "private"}, "text": "/start"}}])
        day = datetime.date.today().isoformat()
        snap = lambda v, c, li: json.dumps({"boot": "b1", "started": "x", "counts": {f"{day}|opp_abc": {"v": v, "c": c, "r": {"www.linkedin.com": li, "google.com": 3}, "p": {}}}})
        self.cli("traffic", snap(3, 0, 1))
        self.run_(fake)  # welcome: past traffic is not announced
        self.assertNotIn("visita", fake.sent[-1]["text"])
        self.cli("traffic", snap(6, 1, 3))
        self.run_(fake)
        msg = fake.sent[-1]["text"]
        self.assertIn("🛒 1 clic su Compra", msg)
        self.assertIn("👀 2 visite da LinkedIn", msg)
        self.assertNotIn("google", msg.lower())
        n = len(fake.sent)
        self.run_(fake)
        self.assertEqual(len(fake.sent), n)  # nothing new, no message
        self.cli("traffic", snap(7, 1, 4))
        self.run_(fake)
        self.assertIn("👀 1 visita da LinkedIn", fake.sent[-1]["text"])
        self.assertNotIn("la prima", fake.sent[-1]["text"])

    def test_signals_are_sent_once(self):
        self.run_(FakeTG(updates=[{"message": {"chat": {"id": 1, "type": "private"}, "text": "/start"}}]))
        self.cli("opp", json.dumps({"id": "opp_t", "title": "Trend", "stage": "live"}))
        self.cli("signal", json.dumps({"opportunity": "opp_t", "text": "COMPRA · Trend (opp_t): porta BTC al 100%"}))
        fake = FakeTG()
        self.run_(fake)
        self.assertIn("📈 SEGNALE COMPRA · Trend (opp_t): porta BTC al 100%", fake.sent[0]["text"])
        fake2 = FakeTG()
        self.run_(fake2)
        self.assertEqual(fake2.sent, [])

    def test_skipped_cycle_is_reported(self):
        self.cli("notified", json.dumps({"ts": "2026-01-01T00:00:00+00:00", "chat_id": "1"}))
        self.cli("end-cycle", "--summary", "saltato: limite di utilizzo")
        fake = FakeTG()
        self.run_(fake)
        self.assertIn("⏸ Ciclo saltato: limite di utilizzo", fake.sent[0]["text"])

    def test_without_token_or_chat_nothing_happens(self):
        with mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": ""}):
            with redirect_stdout(StringIO()) as out:
                self.tg.main([])
        self.assertIn("non impostato", out.getvalue())
        fake = FakeTG(updates=[])
        self.assertIn("scrivigli /start", self.run_(fake))
        self.assertEqual(fake.sent, [])
        self.assertNotIn("notify", self.state())  # the welcome waits until a chat exists

    def test_network_errors_never_break_the_cycle(self):
        class Broken(FakeTG):
            def call(self, method, params=None):
                raise OSError("rete giù")
        self.cli("notified", json.dumps({"ts": "2026-01-01T00:00:00+00:00", "chat_id": "1"}))
        self.cli("ledger", json.dumps({"type": "revenue", "amount_eur": 8}))
        self.assertIn("errore, saltato", self.run_(Broken()))
        fake = FakeTG()
        self.run_(fake)
        self.assertIn("Risultato registrato", fake.sent[0]["text"])  # not marked as sent: retried next time

    def test_weekly_summary_once_per_week(self):
        import datetime as dt
        self.cli("notified", json.dumps({"ts": "2026-01-01T00:00:00+00:00", "chat_id": "1", "week": "2000-W01"}))
        self.cli("ledger", json.dumps({"type": "revenue", "amount_eur": 8, "date": dt.date.today().isoformat()}))
        fake = FakeTG()
        self.run_(fake)
        text = fake.sent[0]["text"]
        self.assertIn("📊 La tua settimana", text)
        self.assertIn("Risultati reali registrati: 8,00 € (1 voci)", text)
        self.cli("ledger", json.dumps({"type": "revenue", "amount_eur": 3}))
        fake2 = FakeTG()
        self.run_(fake2)
        self.assertIn("Risultato registrato: 3,00 €", fake2.sent[0]["text"])
        self.assertNotIn("La tua settimana", fake2.sent[0]["text"])  # same week: not repeated

    def test_weekly_numbers_come_from_real_data(self):
        import datetime as dt
        today = dt.date.today()
        s = self.mm.default_state()
        s["ledger"] = [{"type": "revenue", "amount_eur": 8, "date": today.isoformat()},
                       {"type": "revenue", "amount_eur": 5, "date": (today - dt.timedelta(days=9)).isoformat()},
                       {"type": "cost", "amount_eur": 2, "date": today.isoformat()}]
        s["budget"]["usd_by_day"] = {today.isoformat(): 1.5, (today - dt.timedelta(days=20)).isoformat(): 9}
        s["traffic"] = {"boots": {"b1": {"counts": {f"{today.isoformat()}|guida": {"v": 4, "c": 1, "r": {}, "p": {}},
                                                     f"{(today - dt.timedelta(days=8)).isoformat()}|guida": {"v": 2, "c": 0, "r": {}, "p": {}}}}}}
        s["reports"] = [{"cycle": 3, "team": "rendite", "ts": today.isoformat() + "T10:00:00+00:00", "headline": "Guida online", "next": ["Scrivere la seconda guida"], "usd": 1.5}]
        w = self.mm.weekly(s)
        self.assertEqual((w["revenue_eur"], w["sales"], w["prev_revenue_eur"]), (8, 1, 5))
        self.assertEqual((w["visits"], w["clicks"], w["prev_visits"]), (4, 1, 2))
        self.assertEqual(w["ai_usd"], 1.5)  # only this week's days
        self.assertEqual((w["cycles"], w["next"]), (1, "Scrivere la seconda guida"))


if __name__ == "__main__":
    unittest.main()
