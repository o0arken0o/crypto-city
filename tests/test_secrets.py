import base64
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))

try:
    from nacl import encoding, public
except ImportError:  # the panel needs PyNaCl (requirements.txt); skip if absent locally
    public = None


@unittest.skipIf(public is None, "PyNaCl non installato")
class SecretsTest(unittest.TestCase):
    def setUp(self):
        import server
        self.server = server
        self.priv = public.PrivateKey.generate()
        self.calls = []
        pub_b64 = self.priv.public_key.encode(encoding.Base64Encoder()).decode()

        def fake_gh(method, path, body=None, raw=False):
            self.calls.append((method, path, body))
            if path.endswith("/public-key"):
                return {"key_id": "k1", "key": pub_b64}
            if path.endswith("/actions/secrets?per_page=100"):
                return {"secrets": [{"name": "POLAR_ACCESS_TOKEN", "updated_at": "2026-09-27T10:00:00Z"}]}
            return {}
        self.patches = [mock.patch.object(server, "gh_request", fake_gh), mock.patch.object(server, "GH_MODE", True),
                        mock.patch.object(server, "GH_REPO", "o/r")]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_valid_token_is_encrypted_for_github_and_never_stored_in_clear(self):
        with mock.patch.object(self.server, "check_polar_token", return_value=(True, "")):
            ok, msg = self.server.set_secret("POLAR_ACCESS_TOKEN", "  polar_oat_SEGRETO  ")
        self.assertTrue(ok, msg)
        put = [c for c in self.calls if c[0] == "PUT"][0]
        self.assertEqual(put[1], "/repos/o/r/actions/secrets/POLAR_ACCESS_TOKEN")
        self.assertEqual(put[2]["key_id"], "k1")
        self.assertNotIn("SEGRETO", json.dumps(put[2]))
        clear = public.SealedBox(self.priv).decrypt(base64.b64decode(put[2]["encrypted_value"]))
        self.assertEqual(clear, b"polar_oat_SEGRETO")
        self.assertNotIn("SEGRETO", msg)

    def test_rejections(self):
        with mock.patch.object(self.server, "check_polar_token", return_value=(False, "Polar ha rifiutato il token")):
            self.assertEqual(self.server.set_secret("POLAR_ACCESS_TOKEN", "sbagliato"), (False, "Polar ha rifiutato il token"))
        with mock.patch.object(self.server, "check_ai_key", return_value=(True, "connessione OK")):  # no network in tests
            self.assertTrue(self.server.set_secret("ANTHROPIC_API_KEY", "x")[0])
            self.assertTrue(self.server.set_secret("GROQ_API_KEY_1", "x")[0])
        self.assertFalse(self.server.set_secret("POLAR_ACCESS_TOKEN", "con spazio dentro")[0])
        with mock.patch.object(self.server, "GH_MODE", False):
            self.assertIn("solo con la plancia collegata a GitHub", self.server.set_secret("POLAR_ACCESS_TOKEN", "x")[1])
        self.assertTrue(any(c[0] == "PUT" and c[1].endswith("/ANTHROPIC_API_KEY") for c in self.calls))
        self.assertTrue(any(c[0] == "PUT" and c[1].endswith("/GROQ_API_KEY_1") for c in self.calls))

    def test_status_and_auth(self):
        st = self.server.secrets_status()
        self.assertEqual(st["secrets"]["POLAR_ACCESS_TOKEN"], "2026-09-27T10:00:00Z")
        with mock.patch.object(self.server, "TOKEN", "segreto-lungo-123"):
            httpd = self.server.ThreadingHTTPServer(("127.0.0.1", 0), self.server.H)
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            try:
                for method, path, data in (("GET", "/api/secrets", None), ("POST", "/api/secret", b'{"name":"POLAR_ACCESS_TOKEN","value":"x"}')):
                    with self.assertRaises(urllib.error.HTTPError) as e:
                        urllib.request.urlopen(urllib.request.Request(base + path, data=data, method=method))
                    self.assertEqual(e.exception.code, 401)
            finally:
                httpd.shutdown()

    def test_ai_key_connectivity_check(self):
        class Resp:
            def read(self):
                return b'{"data":[{"id":"model-a"},{"id":"model-b"}]}'
            def __enter__(self): return self
            def __exit__(self, *args): pass
        with mock.patch.object(self.server.urllib.request, "urlopen", return_value=Resp()) as call:
            ok, msg = self.server.check_ai_key("GROQ_API_KEY", "secret-value")
        self.assertTrue(ok)
        self.assertIn("2 modelli", msg)
        req = call.call_args.args[0]
        self.assertEqual(req.headers.get("Authorization"), "Bearer secret-value")

    def test_ai_key_rejected_before_save(self):
        with mock.patch.object(self.server, "check_ai_key", return_value=(False, "key rifiutata")):
            ok, msg = self.server.set_secret("GROQ_API_KEY", "bad")
        self.assertFalse(ok)
        self.assertEqual(msg, "key rifiutata")
        self.assertFalse(any(c[0] == "PUT" and c[1].endswith("/GROQ_API_KEY") for c in self.calls))


if __name__ == "__main__":
    unittest.main()


class TelegramSecretTest(unittest.TestCase):
    """The panel saves the bot token, finds the owner's chat from /start, saves it and sends a test message."""

    def setUp(self):
        import server
        self.server, self.saved, self.tg = server, {}, []
        self.updates = [{"message": {"chat": {"id": 777, "type": "private"}, "text": "/start"}}]

        def fake_tg(token, method, params=None):
            self.tg.append((method, params))
            if token != "123:ok":
                raise urllib.error.HTTPError("u", 401, "no", {}, None)
            return {"getMe": {"result": {"username": "mm_avvisi_bot"}}, "getUpdates": {"result": self.updates}}.get(method, {"ok": True})
        self.patches = [mock.patch.object(server, "telegram_api", fake_tg), mock.patch.object(server, "GH_MODE", True),
                        mock.patch.object(server, "put_secret", lambda n, v: self.saved.__setitem__(n, v))]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_saves_token_and_chat_then_sends_a_test_message(self):
        ok, msg = self.server.set_secret("TELEGRAM_BOT_TOKEN", "123:ok")
        self.assertTrue(ok, msg)
        self.assertEqual(self.saved, {"TELEGRAM_BOT_TOKEN": "123:ok", "TELEGRAM_CHAT_ID": "777"})
        self.assertIn("@mm_avvisi_bot", msg)
        self.assertIn("messaggio di prova", msg)
        self.assertEqual(self.tg[-1][0], "sendMessage")
        self.assertEqual(self.tg[-1][1]["chat_id"], "777")

    def test_without_start_the_token_is_saved_and_the_owner_is_told(self):
        self.updates = []
        ok, msg = self.server.set_secret("TELEGRAM_BOT_TOKEN", "123:ok")
        self.assertTrue(ok)
        self.assertEqual(list(self.saved), ["TELEGRAM_BOT_TOKEN"])
        self.assertIn("premi Avvia", msg)

    def test_wrong_token_is_not_saved(self):
        ok, msg = self.server.set_secret("TELEGRAM_BOT_TOKEN", "999:bad")
        self.assertFalse(ok)
        self.assertEqual(self.saved, {})
        self.assertIn("BotFather", msg)

    def test_telegram_is_not_counted_as_an_ai_provider(self):
        self.assertFalse(self.server.AI_SECRET_RE.fullmatch("TELEGRAM_BOT_TOKEN_1"))
        self.assertNotIn("TELEGRAM_BOT_TOKEN", self.server.AI_SECRET_BASES)
