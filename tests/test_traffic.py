import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

UA = {"User-Agent": "Mozilla/5.0 (iPhone) Safari"}


class TrafficTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.root = tempfile.mkdtemp()
        os.makedirs(os.path.join(cls.root, "site", "guida", "public"))
        with open(os.path.join(cls.root, "site", "guida", "public", "index.html"), "w") as f:
            f.write("<title>Guida</title>")
        open(os.path.join(cls.root, "site", "guida", ".approved"), "w").close()
        with open(os.path.join(cls.root, "site", "guida", "links.json"), "w") as f:
            json.dump({"xero": "https://www.xero.com/?ref=1", "bad": "javascript:alert(1)"}, f)
        os.makedirs(os.path.join(cls.root, "products", "opp_abc"))
        with open(os.path.join(cls.root, "products", "opp_abc", "polar.json"), "w") as f:
            json.dump({"checkout_url": "https://buy.polar.sh/polar_cl_x"}, f)
        os.makedirs(os.path.join(cls.root, "products", "opp_evil"))
        with open(os.path.join(cls.root, "products", "opp_evil", "polar.json"), "w") as f:
            json.dump({"checkout_url": "https://evil.example/"}, f)
        server.ROOT, server.GH_MODE, server.TOKEN = cls.root, False, "segreto-lungo-123"
        server._site_cache.clear()
        server.TRAFFIC["counts"].clear()
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path, headers=None):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a):
                return None
        req = urllib.request.Request(self.base + path, headers=headers or {})
        try:
            r = urllib.request.build_opener(NoRedirect).open(req)
            return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_views_clicks_referrers_and_safe_redirects(self):
        self.get("/s/guida/", {**UA, "Referer": "https://www.google.com/search?q=crm"})
        self.get("/s/guida/", UA)
        self.get("/s/guida/", {"User-Agent": "Googlebot/2.1"})  # bot: not counted
        self.get("/s/guida/")                                    # no browser: not counted
        code, _, h = self.get("/go/opp_abc", {**UA, "Referer": self.base + "/s/guida/"})
        self.assertEqual((code, h["Location"]), (302, "https://buy.polar.sh/polar_cl_x"))
        self.assertEqual(self.get("/go/guida/xero", UA)[2]["Location"], "https://www.xero.com/?ref=1")
        for bad in ("/go/opp_evil", "/go/guida/bad", "/go/opp_nope", "/go/../x", "/go/bozza/xero"):
            self.assertEqual(self.get(bad, UA)[0], 404, bad)
        # counts are private: panel token or the derived read-only key
        self.assertEqual(self.get("/api/traffic")[0], 401)
        self.assertEqual(self.get("/api/traffic", {"X-MM-Traffic-Key": "sbagliata"})[0], 401)
        code, body, _ = self.get("/api/traffic", {"X-MM-Traffic-Key": self.server.traffic_key()})
        self.assertEqual(code, 200)
        snap = json.loads(body)
        self.assertNotEqual(self.server.traffic_key(), self.server.TOKEN)
        page = next(v for k, v in snap["counts"].items() if k.endswith("|guida"))
        self.assertEqual((page["v"], page["c"], page["r"], page["p"]), (2, 1, {"www.google.com": 1}, {"opp_abc": 1}))

        # engine: snapshots of the same process replace each other, different processes add up
        import mm
        tmp = tempfile.mkdtemp()
        mm.STATE_DIR, mm.STATE_FILE = tmp, os.path.join(tmp, "state.json")
        mm.INBOX_FILE, mm.LOCK_FILE, mm.LIVE_FILE = (os.path.join(tmp, n) for n in ("inbox.jsonl", ".lock", "live.json"))
        with redirect_stdout(StringIO()):
            mm.main(["traffic", json.dumps(snap)])
            mm.main(["traffic", json.dumps(snap)])
            mm.main(["traffic", json.dumps({**snap, "boot": "altro-avvio"})])
        with open(mm.STATE_FILE) as f:
            s = json.load(f)
        row = next(r for r in mm.traffic_summary(s) if r["page"] == "guida")
        self.assertEqual((row["views"], row["clicks"], row["ctr"]), (4, 2, 0.5))
        self.assertIn("guida: 4 visite, 2 clic (50%)", "\n".join(mm._traffic_lines(s)))


    def test_home_visits_are_counted(self):
        before = sum(v["v"] for k, v in self.server.TRAFFIC["counts"].items() if k.endswith("|home"))
        self.get("/", UA); self.get("/s/", UA); self.get("/", {"User-Agent": "Googlebot/2.1"})
        after = sum(v["v"] for k, v in self.server.TRAFFIC["counts"].items() if k.endswith("|home"))
        self.assertEqual(after - before, 2)


class TrafficFlushTest(unittest.TestCase):
    """Before a restart the panel sends its counts as a command: nothing is lost between two syncs."""

    def test_snapshot_flush_and_engine_op(self):
        import server
        import mm
        old = dict(server.TRAFFIC["counts"])
        try:
            server.TRAFFIC["counts"].clear()
            server.TRAFFIC["counts"]["2026-10-01|vuota"] = {"v": 0, "c": 0, "r": {}, "p": {}}
            for d in range(1, 29):
                server.TRAFFIC["counts"][f"2026-09-{d:02d}|guida"] = {"v": 3, "c": 1, "r": {"x" * 50: 1}, "p": {}}
            snap = server.traffic_snapshot(limit=2000)
            self.assertNotIn("2026-10-01|vuota", snap["counts"])            # empty rows are not sent
            self.assertLessEqual(len(json.dumps(snap)), 2000)               # fits in an issue
            self.assertIn("2026-09-28|guida", snap["counts"])               # the newest days are kept
            self.assertNotIn("2026-09-01|guida", snap["counts"])
            sent = []
            gm, gc = server.GH_MODE, server.gh_command
            server.gh_command = lambda op, args: sent.append((op, args)) or "inviato"
            try:
                server.GH_MODE = False
                self.assertEqual(server.flush_traffic(), "")                # local panel: nothing to send
                server.GH_MODE = True
                self.assertEqual(server.flush_traffic(), "inviato")
            finally:
                server.GH_MODE, server.gh_command = gm, gc
            self.assertEqual(sent[0][0], "traffic")
            s = {"traffic": {"boots": {}}}
            out = mm.apply_command(s, {"op": "traffic", "args": json.loads(json.dumps(sent[0][1]))})
            self.assertIn("visite", out)
            self.assertIn(server.TRAFFIC["boot"], s["traffic"]["boots"])
        finally:
            server.TRAFFIC["counts"].clear(); server.TRAFFIC["counts"].update(old)


if __name__ == "__main__":
    unittest.main()
