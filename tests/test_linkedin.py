import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
import linkedin  # noqa: E402


class Resp(io.BytesIO):
    def __init__(self, body=b"", headers=None):
        super().__init__(body); self.headers = headers or {}
    def __enter__(self): return self
    def __exit__(self, *a): return False


class LinkedInTest(unittest.TestCase):
    def folder(self, pdf=True):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "POST.md"), "w") as f:
            f.write("# POST\n\n## Testo da incollare\nIl cliente non paga (succede)?\n\nEcco cosa scrivere.\n\n(Circa 300 caratteri.)\n\n"
                    "## Hashtag\n#freelance #partitaiva\n\n## Testo delle slide\n1. ...\n")
        open(os.path.join(d, "slide-01.png"), "wb").write(b"png")
        if pdf:
            open(os.path.join(d, "carosello.pdf"), "wb").write(b"%PDF")
        return d

    def test_text_drops_owner_notes_adds_hashtags_and_ai_note(self):
        t = linkedin.post_text(self.folder())
        self.assertNotIn("Circa 300", t)
        self.assertIn("#freelance #partitaiva", t)
        self.assertIn("aiuto dell'AI", t)
        self.assertNotIn("Testo delle slide", t)

    def test_escape_little_text(self):
        self.assertEqual(linkedin.escape("a (b) #tag_x"), "a \\(b\\) {hashtag|\\#|tag_x}")

    def test_publish_uploads_the_carousel_then_posts(self):
        calls = []
        def opener(req, timeout=0):
            calls.append((req.get_method(), req.full_url))
            if "initializeUpload" in req.full_url:
                return Resp(json.dumps({"value": {"uploadUrl": "https://up.example/x", "document": "urn:li:document:1"}}).encode())
            if req.full_url.endswith("/rest/posts"):
                body = json.loads(req.data)
                self.assertEqual(body["content"]["media"]["id"], "urn:li:document:1")
                self.assertEqual(body["author"], "urn:li:person:abc")
                return Resp(b"", {"x-restli-id": "urn:li:share:9"})
            return Resp(json.dumps({"status": "AVAILABLE"}).encode())
        api = linkedin.LinkedIn("tok", "urn:li:person:abc", opener)
        res = linkedin.publish(self.folder(), api)
        self.assertEqual((res["urn"], res["kind"]), ("urn:li:share:9", "carosello"))
        self.assertIn(("PUT", "https://up.example/x"), calls)

    def test_not_connected(self):
        with mock.patch.dict(os.environ, {"LINKEDIN_ACCESS_TOKEN": "", "LINKEDIN_PERSON_URN": ""}):
            with self.assertRaises(RuntimeError):
                linkedin.from_env()

    def test_oauth_start_and_finish_save_the_secrets(self):
        import server
        saved = {}
        with mock.patch.object(server, "GH_MODE", True), mock.patch.object(server, "put_secret", lambda n, v: saved.__setitem__(n, v)):
            ok, url = server.linkedin_start("abcd1234efgh", "secretvalue123", "esempio.app")
            self.assertTrue(ok); self.assertIn("w_member_social", urllib_unquote(url))
            state = url.split("state=")[1].split("&")[0]
            def opener(req, timeout=0):
                if "accessToken" in req.full_url:
                    return Resp(json.dumps({"access_token": "AT", "expires_in": 5184000}).encode())
                return Resp(json.dumps({"sub": "abc123", "name": "Dimitri"}).encode())
            ok, msg = server.linkedin_finish(state, "CODE", opener)
            self.assertTrue(ok, msg); self.assertIn("60 giorni", msg)
            self.assertEqual(saved, {"LINKEDIN_ACCESS_TOKEN": "AT", "LINKEDIN_PERSON_URN": "urn:li:person:abc123"})
            self.assertFalse(server.linkedin_finish(state, "CODE", opener)[0])  # one-time only


def urllib_unquote(s):
    import urllib.parse
    return urllib.parse.unquote_plus(s)



class LinkedInExpiryTest(unittest.TestCase):
    """A week before the 60-day token expires the owner gets a "tocca a te" block; reconnecting closes it."""

    def test_reminder_and_reconnect(self):
        import datetime as dt
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
        import mm
        s = {"blockers": [], "log": []}
        self.assertIn("2026-11-30", mm.apply_command(s, {"op": "linkedin", "args": {"expires": "2026-11-30"}}))
        self.assertEqual(mm.linkedin_reminder(s, dt.date(2026, 11, 20)), [])          # still 10 days
        out = mm.linkedin_reminder(s, dt.date(2026, 11, 24))
        self.assertEqual(len(out), 1)
        b = s["blockers"][0]
        self.assertEqual((b["status"], b["owner"]), ("open", "human"))
        self.assertIn("30/11", b["title"])
        self.assertEqual(mm.linkedin_reminder(s, dt.date(2026, 11, 25)), [])          # only once
        mm.apply_command(s, {"op": "linkedin", "args": {"expires": "2027-01-29"}})    # reconnected
        self.assertEqual(s["blockers"][0]["status"], "done")
        self.assertIn("non valida", mm.apply_command(s, {"op": "linkedin", "args": {"expires": "domani"}}))


if __name__ == "__main__":
    unittest.main()
