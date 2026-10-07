import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))


class SocialTeamTest(unittest.TestCase):
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
        self.mm, self.server = mm, server
        self.cwd = os.getcwd(); os.chdir(root)

    def tearDown(self):
        os.chdir(self.cwd)

    def cli(self, *args):
        out = StringIO()
        with redirect_stdout(out):
            rc = self.mm.main(list(args))
        return rc, out.getvalue()

    def draft(self, opp, days_ago, platform="instagram", images=True):
        rel = f"products/{opp}/social/{(dt.date.today() - dt.timedelta(days=days_ago)).isoformat()}-{platform}"
        d = os.path.join(self.root, rel)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, "POST.md"), "w").close()
        if images:
            open(os.path.join(d, "slide-01.png"), "w").close()
        return rel

    def test_team_is_registered(self):
        self.assertIn("social", self.mm.TEAMS)
        self.assertEqual(self.mm.TEAM_HEAD["social"], "social-lead")
        for a in ("social-lead", "social-writer", "visual-designer"):
            self.assertIn(a, self.mm.AGENTS)
            self.assertTrue(os.path.exists(os.path.join(self.cwd, "agents", a + ".md")), a)
        self.assertTrue(os.path.exists(os.path.join(self.cwd, "commands", "social.md")))
        self.assertTrue(os.path.exists(os.path.join(self.cwd, ".github", "workflows", "crypto-social.yml")))
        self.assertEqual(self.server.TEAM_WORKFLOW["social"], "crypto-social.yml")

    def test_skips_without_products_and_at_weekly_limit(self):
        rc, out = self.cli("can-run", "--team", "social")
        self.assertEqual(rc, 1); self.assertIn("nessuna strategia in paper trading o live", out)
        self.cli("opp", json.dumps({"id": "opp_a", "title": "CRM", "stage": "live"}))
        rc, out = self.cli("can-run", "--team", "social")
        self.assertEqual(rc, 0, out)
        for i in range(3):
            self.draft("opp_a", i)
        self.draft("opp_a", 9)  # older than a week: does not count
        rc, out = self.cli("can-run", "--team", "social")
        self.assertEqual(rc, 1); self.assertIn("già 3 post", out)
        self.assertEqual(self.cli("can-run", "--team", "social", "--force")[0], 0)  # started by hand

    def test_brief_and_room(self):
        os.makedirs(os.path.join(self.root, "products", "opp_a"))
        with open(os.path.join(self.root, "products", "opp_a", "paper.json"), "w") as f:  # real paper trading results
            json.dump({"metrics": {"return": 0.12, "hold_return": 0.05, "days": 30}}, f)
        with open(os.path.join(self.root, "products", "opp_a", "live.json"), "w") as f:  # approved by the owner
            json.dump({"approved": True, "capital_eur": 100}, f)
        self.cli("opp", json.dumps({"id": "opp_a", "title": "CRM freelance", "stage": "live", "price_eur": 9}))
        ig, li = self.draft("opp_a", 1), self.draft("opp_a", 2, "linkedin")
        self.cli("blocker", json.dumps({"title": "Pubblica il post instagram sul CRM", "owner": "human", "blocks": ["opp_a"], "how": f"testo e immagini in {ig}/"}), "--agent", "social-lead")
        self.cli("blocker", json.dumps({"title": "Pubblica il post linkedin sul CRM", "owner": "human", "blocks": ["opp_a"], "how": f"in {li}/"}), "--agent", "social-lead")
        self.cli("blocker", json.dumps({"title": "Pubblica il post su r/freelance", "owner": "human"}), "--agent", "yield-lead")
        s = self.mm.load()
        done = next(b for b in s["blockers"] if "linkedin" in b["title"])
        self.cli("unblock", done["id"], "--agent", "human")
        _, brief = self.cli("social-brief")
        self.assertIn("Post preparati negli ultimi 7 giorni: 2/3", brief)
        self.assertIn("opp_a [live] CRM freelance · paper +12.0% vs hold +5.0% in 30g", brief)
        self.assertIn("Pubblica il post instagram sul CRM", brief)
        self.assertIn("Pubblicati dal proprietario negli ultimi 30 giorni: 1", brief)
        w = self.server.live_snapshot("social")["world"]
        self.assertEqual([q["title"] for q in w["queue"]], ["Pubblica il post instagram sul CRM"])  # only the social team's
        self.assertEqual(w["queue"][0]["platform"], "instagram")
        self.assertEqual((w["published_30d"], w["platforms"]["linkedin"], w["platforms"]["instagram"]),
                         (1, {"ready": 0, "published": 1}, {"ready": 1, "published": 0}))
        self.assertEqual(w["products"], [{"id": "opp_a", "title": "CRM freelance", "ready": 1, "published": 1}])
        self.assertIn("kpi", w)

    def test_a_post_reaches_the_owner_only_with_its_images(self):
        rel = self.draft("opp_a", 0, "linkedin", images=False)
        title = "Pubblica il post linkedin sul CRM"
        _, out = self.cli("blocker", json.dumps({"title": title, "owner": "human", "how": f"componi tu le slide, testo in {rel}/"}), "--agent", "social-lead")
        self.assertIn("RIFIUTATO", out)
        _, out = self.cli("blocker", json.dumps({"title": title, "owner": "human", "how": "nessuna cartella"}), "--agent", "social-lead")
        self.assertIn("RIFIUTATO", out)
        self.assertEqual(self.mm.load()["blockers"], [])
        _, brief = self.cli("social-brief")
        self.assertIn("DA COMPLETARE PRIMA DI TUTTO", brief); self.assertIn(rel, brief)
        open(os.path.join(self.root, rel, "slide-01.png"), "w").close()
        _, out = self.cli("blocker", json.dumps({"title": title, "owner": "human", "how": f"testo in {rel}/POST.md"}), "--agent", "social-lead")
        self.assertIn("aperto", out)
        _, out = self.cli("blocker", json.dumps({"title": title, "owner": "human", "how": f"testo e 5 slide in {rel}/"}), "--agent", "social-lead")
        self.assertIn("aggiornato", out)
        b = self.mm.load()["blockers"]
        self.assertEqual((len(b), b[0]["how"]), (1, f"testo e 5 slide in {rel}/"))
        # a limit reached with an unfinished post still lets the team finish it
        self.cli("opp", json.dumps({"id": "opp_a", "title": "CRM", "stage": "live"}))
        for i in range(3):
            self.draft("opp_a", i + 1)
        self.assertEqual(self.cli("can-run", "--team", "social")[0], 1)
        self.draft("opp_a", 1, "tiktok", images=False)
        self.assertEqual(self.cli("can-run", "--team", "social")[0], 0)

    def test_report_for_the_social_team(self):
        self.assertEqual(self.cli("report", json.dumps({"headline": "post pronto", "team": "social"}))[0], 0)
        self.assertEqual(self.server.live_snapshot("social")["report"]["headline"], "post pronto")
        self.assertIsNone(self.server.live_snapshot("rendite")["report"])


class SocialCardTest(unittest.TestCase):
    def test_renders_slides_only_with_real_previews(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            self.skipTest("Pillow non installato")
        import social_card
        from PIL import Image
        root = tempfile.mkdtemp()
        media = os.path.join(root, "products", "opp_a", "media"); os.makedirs(media)
        Image.new("RGB", (600, 400), (255, 255, 255)).save(os.path.join(media, "01.png"))
        out = os.path.join(root, "products", "opp_a", "social", "2026-01-01-instagram"); os.makedirs(out)
        spec = {"format": "story", "slides": [{"title": "Ciao", "text": "Testo", "image": "products/opp_a/media/01.png"},
                                              {"title": "Fuori", "image": "../../../etc/passwd"}, {"title": "Punti", "bullets": ["a", "b"]}]}
        files = social_card.render(spec, out, root)
        self.assertEqual([os.path.basename(f) for f in files], ["slide-01.png", "slide-02.png", "slide-03.png", "carosello.pdf"])
        with Image.open(files[0]) as im:
            self.assertEqual(im.size, (1080, 1920))
        self.assertEqual(social_card._safe_image("../../../etc/passwd", root), None)
        self.assertEqual(social_card._safe_image("products/opp_a/deliverable/x.png", root), None)
        self.assertTrue(social_card._safe_image("products/opp_a/media/01.png", root))
        with self.assertRaises(ValueError):
            social_card.render({"slides": []}, out, root)


if __name__ == "__main__":
    unittest.main()
