import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))


class Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FindabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.root = tempfile.mkdtemp()
        pages = {"opp_plan": '<html><head><title>Planner 2027</title><meta name="description" content="Planner PDF con link">'
                           '</head><body><a href="/go/opp_plan">Compra</a></body></html>',
                 "guida": "<html><head><title>Guida fatture</title></head><body><p>ok</p></body></html>"}
        for slug, html in pages.items():
            os.makedirs(os.path.join(cls.root, "site", slug, "public"))
            with open(os.path.join(cls.root, "site", slug, "public", "index.html"), "w") as f:
                f.write(html)
            with open(os.path.join(cls.root, "site", slug, ".approved"), "w") as f:
                json.dump({"published": "2026-09-20T10:00:00+00:00"}, f)
        os.makedirs(os.path.join(cls.root, "products", "opp_plan", "media"))
        with open(os.path.join(cls.root, "products", "opp_plan", "polar.json"), "w") as f:
            json.dump({"checkout_url": "https://buy.polar.sh/x", "price_eur": 7}, f)
        with open(os.path.join(cls.root, "products", "opp_plan", "store.json"), "w") as f:
            json.dump({"name": "Planner 2026-27", "price_eur": 7}, f)
        with open(os.path.join(cls.root, "products", "opp_plan", "media", "01-cover.png"), "wb") as f:
            f.write(b"\x89PNG fake")
        os.makedirs(os.path.join(cls.root, "products", "opp_draft", "media"))
        with open(os.path.join(cls.root, "products", "opp_draft", "media", "a.png"), "wb") as f:
            f.write(b"\x89PNG")
        server.ROOT, server.GH_MODE, server.TOKEN, server.SITE_URL = cls.root, False, "segreto-lungo-123", "https://esempio.up.railway.app"
        server._site_cache.clear()
        cls.server = server
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.server.SITE_URL = ""

    def get(self, path):
        try:
            r = urllib.request.urlopen(self.base + path)
            return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, ""

    def test_site_index_shows_products_then_guides_with_real_prices(self):
        code, html = self.get("/s/")
        self.assertEqual(code, 200)
        self.assertIn('<link rel="canonical"', html)
        self.assertLess(html.index('id="modelli"'), html.index("<h2>Guide gratuite</h2>"))
        self.assertIn("7,00 €", html)  # price from polar.json
        self.assertIn('src="/m/opp_plan/01-cover.png"', html)  # real preview only for products on sale
        self.assertNotIn("data-mm-brand", html)  # no brand configured: no logo bar
        _, g = self.get("/s/guida/")
        self.assertIn("Leggi anche", g)
        self.assertIn('href="/s/"', g)  # every page links back to the index

    def test_brand_logo_and_bar(self):
        d = os.path.join(self.root, "site", "_brand"); os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "brand.json"), "w") as f:
            json.dump({"name": ["Solleciti", "Facili"], "color": "#1a73e8", "tagline": "Modelli e guide per farti pagare"}, f)
        with open(os.path.join(d, "logo.svg"), "w") as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10"/></svg>')
        self.server._site_cache.clear()
        try:
            _, home = self.get("/")
            self.assertIn("Solleciti", home); self.assertIn("Modelli e guide per farti pagare", home)
            self.assertNotIn("_brand", [p["slug"] for p in []])
            self.assertEqual(urllib.request.urlopen(self.base + "/brand/logo.svg").headers["Content-Type"].split(";")[0], "image/svg+xml")
            _, g = self.get("/s/guida/")
            self.assertIn("data-mm-brand", g)  # every page gets the logo bar
            self.assertEqual(self.get("/s/_brand/")[0], 404)  # the brand folder is not a page
        finally:
            import shutil; shutil.rmtree(d); self.server._site_cache.clear()

    def test_share_preview_images_for_guides_and_home(self):
        d = os.path.join(self.root, "site", "_brand"); os.makedirs(d, exist_ok=True)
        png = b"\x89PNG\r\n\x1a\nfake"
        with open(os.path.join(d, "share.png"), "wb") as f:
            f.write(png)
        self.server._site_cache.clear()
        try:
            _, g = self.get("/s/guida/")
            self.assertRegex(g, r'property="og:image" content="https?://[^"]+/brand/share\.png"')  # no image of its own: the site's one
            _, home = self.get("/")
            self.assertIn('property="og:image"', home)
            self.assertEqual(urllib.request.urlopen(self.base + "/brand/share.png").read(), png)
            with open(os.path.join(self.root, "site", "guida", "public", "share.png"), "wb") as f:
                f.write(png)
            self.server._site_cache.clear()
            self.assertIn("/s/guida/share.png", self.get("/s/guida/")[1])  # its own image wins
        finally:
            import shutil; shutil.rmtree(d); self.server._site_cache.clear()
            own = os.path.join(self.root, "site", "guida", "public", "share.png")
            if os.path.exists(own):
                os.remove(own)

    def test_installable_app_files(self):
        code, man = self.get("/manifest.webmanifest")
        m = json.loads(man)
        self.assertEqual((code, m["display"], m["start_url"]), (200, "standalone", "/plancia"))
        self.assertTrue({"192x192", "512x512"} <= {i["sizes"] for i in m["icons"]})
        for icon in m["icons"]:
            r = urllib.request.urlopen(self.base + icon["src"])
            self.assertEqual(r.headers["Content-Type"], "image/png")
            self.assertEqual(r.read()[:4], b"\x89PNG")
        code, sw = self.get("/sw.js")
        self.assertEqual(code, 200)
        self.assertIn('startsWith("/api/")', sw)  # live data is never cached
        _, home = self.get("/plancia")
        self.assertIn('rel="manifest"', home)
        self.assertIn('rel="apple-touch-icon"', home)

    def test_root_is_the_public_site_and_the_panel_moved(self):
        code, home = self.get("/")
        self.assertEqual(code, 200)
        self.assertIn("Strategie crypto testate in pubblico", home)  # visitors and Google see the site, not a password prompt
        self.assertIn('location.replace("/plancia")', home)  # the owner (token saved) is sent to the panel
        self.assertNotIn("api/state", home)
        self.assertIn("Allow: /$", self.get("/robots.txt")[1])
        _, panel = self.get("/plancia")
        self.assertIn("api/state", panel)
        r = urllib.request.urlopen(self.base + "/index.html")  # old address still works (redirect)
        self.assertTrue(r.geturl().endswith("/plancia"))

    def test_google_search_console_verification(self):
        from unittest import mock
        self.assertEqual(self.get("/google0123abcd.html")[0], 404)  # nothing configured: nothing served
        with mock.patch.dict(os.environ, {"MM_GOOGLE_VERIFY": "google0123abcd.html"}):
            code, body = self.get("/google0123abcd.html")
            self.assertEqual((code, body), (200, "google-site-verification: google0123abcd.html"))
            self.assertEqual(self.get("/google9999.html")[0], 404)  # only the configured file
            self.assertIn("Allow: /google0123abcd.html", self.get("/robots.txt")[1])
        tag = '<meta name="google-site-verification" content="AbC_dEf-1234567890xyzXYZ" />'
        with mock.patch.dict(os.environ, {"MM_GOOGLE_VERIFY": tag}):  # whole tag pasted: the code is kept
            self.assertIn('<meta name="google-site-verification" content="AbC_dEf-1234567890xyzXYZ">', self.get("/")[1])
        with mock.patch.dict(os.environ, {"MM_GOOGLE_VERIFY": 'x"><script>'}):  # anything else is ignored
            self.assertNotIn("google-site-verification", self.get("/")[1])

    def test_pages_carry_real_structured_data_previews_and_related_links(self):
        _, html = self.get("/s/opp_plan/")
        ld = json.loads(html.split('<script type="application/ld+json">')[1].split("</script>")[0])
        self.assertEqual((ld["@type"], ld["name"], ld["offers"]["price"], ld["offers"]["priceCurrency"]), ("Product", "Planner 2026-27", "7.00", "EUR"))
        self.assertEqual(ld["image"], "https://esempio.up.railway.app/m/opp_plan/01-cover.png")
        self.assertNotIn("aggregateRating", html)  # never invented reviews
        self.assertIn('<link rel="canonical" href="https://esempio.up.railway.app/s/opp_plan/">', html)
        self.assertIn('property="og:image"', html)
        self.assertIn('href="/s/guida/"', html)  # related pages
        _, g = self.get("/s/guida/")
        self.assertIn('"@type": "Article"', g)
        self.assertEqual(self.get("/m/opp_plan/01-cover.png")[0], 200)
        self.assertEqual(self.get("/m/opp_draft/a.png")[0], 404)  # not on sale: images stay private
        self.assertEqual(self.get("/m/opp_plan/../polar.json")[0], 404)

    def test_feed_llms_sitemap_and_indexnow(self):
        _, feed = self.get("/s/feed.xml")
        self.assertIn("<title>Planner 2027</title>", feed)
        _, llms = self.get("/llms.txt")
        self.assertIn("[Guida fatture](https://esempio.up.railway.app/s/guida/)", llms)
        _, sm = self.get("/s/sitemap.xml")
        self.assertIn("<lastmod>2026-09-20</lastmod>", sm)
        key = self.server.indexnow_key()
        self.assertEqual(self.get(f"/{key}.txt"), (200, key))
        self.assertNotIn(self.server.TOKEN, key)
        sent = []

        def opener(req, timeout=None):
            sent.append(json.loads(req.data))
            return Resp()
        self.server._indexnow["sent"].clear()
        urls = self.server.indexnow_submit("https://esempio.up.railway.app", opener)
        self.assertEqual(len(urls), 3)
        self.assertEqual(sent[0]["keyLocation"], f"https://esempio.up.railway.app/{key}.txt")
        self.assertEqual(self.server.indexnow_submit("https://esempio.up.railway.app", opener), [])  # unchanged: not resent
        self.assertEqual(self.server.indexnow_submit("http://localhost:8787", opener), [])


if __name__ == "__main__":
    unittest.main()
