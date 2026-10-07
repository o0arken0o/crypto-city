import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))


class PublicSiteTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import server
        cls.root = tempfile.mkdtemp()
        for slug, approved in (("guida-crm", True), ("bozza", False)):
            os.makedirs(os.path.join(cls.root, "site", slug, "public"))
            with open(os.path.join(cls.root, "site", slug, "public", "index.html"), "w") as f:
                f.write(f"<title>Titolo {slug}</title><p>ok</p>")
            if approved:
                open(os.path.join(cls.root, "site", slug, ".approved"), "w").close()
        with open(os.path.join(cls.root, "site", "guida-crm", "public", "style.css"), "w") as f:
            f.write("p{}")
        with open(os.path.join(cls.root, "site", "guida-crm", "NOTE.md"), "w") as f:
            f.write("interno")
        server.ROOT, server.GH_MODE, server.TOKEN = cls.root, False, "segreto-lungo-123"
        server._site_cache.clear()
        cls.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.H)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a):
                return None
        try:
            r = urllib.request.build_opener(NoRedirect).open(self.base + path)
            return r.status, r.read().decode(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode(), dict(e.headers)

    def test_only_approved_public_files_are_served_without_token(self):
        code, body, h = self.get("/s/guida-crm/")
        self.assertEqual((code, "Titolo guida-crm" in body), (200, True))
        self.assertIn("script-src 'none'", h["Content-Security-Policy"])
        self.assertEqual(self.get("/s/guida-crm/style.css")[0], 200)
        self.assertEqual(self.get("/s/guida-crm")[0], 301)
        for bad in ("/s/bozza/", "/s/guida-crm/../NOTE.md", "/s/guida-crm/%2e%2e/NOTE.md", "/s/guida-crm/NOTE.md",
                    "/s/guida-crm/.approved", "/s/../dashboard/index.html"):
            self.assertEqual(self.get(bad)[0], 404, bad)

    def test_index_sitemap_robots_and_private_api_still_protected(self):
        _, idx, _ = self.get("/s/")
        self.assertIn('href="/s/guida-crm/"', idx)
        self.assertNotIn("bozza", idx)
        _, sm, _ = self.get("/s/sitemap.xml")
        self.assertIn("/s/guida-crm/</loc>", sm)
        _, rb, _ = self.get("/robots.txt")
        self.assertIn("Disallow: /", rb)
        self.assertEqual(self.get("/api/state")[0], 401)

    def test_shared_3d_module_is_served_to_the_rooms(self):
        code, js, h = self.get("/scene3d.js")
        self.assertEqual(code, 200)
        self.assertTrue(h["Content-Type"].startswith("text/javascript"))
        self.assertIn("export function workstation", js)
        code, js, h = self.get("/exchange.js")  # the exchange-look room shell, built on scene3d.js
        self.assertEqual(code, 200)
        self.assertTrue(h["Content-Type"].startswith("text/javascript"))
        self.assertIn('from "./scene3d.js"', js)
        for page in ("office.html", "sales.html"):
            self.assertIn('from "./exchange.js"', self.get("/" + page)[1])

    def test_room_kpi_numbers_for_the_wall_screen(self):
        import datetime as _dt
        import server
        today = _dt.date.today().isoformat()
        s = {"budget": {"usd_today": 1.234, "usd_per_day": 3, "usd_per_cycle": .5, "usd_total": 10, "day": server.mm.today()},
             "ledger": [{"type": "revenue", "amount_eur": 8, "date": today}, {"type": "revenue", "amount_eur": 5, "date": "2020-01-01"},
                        {"type": "cost", "amount_eur": 1, "date": today}],
             "opportunities": [{"stage": "live"}, {"stage": "idea"}, {"stage": "scaling"}]}
        k = server.room_kpi(s)
        self.assertEqual((k["revenue_eur"], k["revenue_30d"], k["sales_30d"], k["live_products"]), (13, 8, 1, 2))
        self.assertEqual((k["ai_today_usd"], k["ai_day_usd"], k["net_eur"]), (1.23, 3, 2.8))
        s["budget"]["day"] = "2000-01-01"  # yesterday's spending does not count today
        self.assertEqual(server.room_kpi(s)["ai_today_usd"], 0.0)


    def test_first_sale_for_the_party_in_the_rooms(self):
        import server
        self.assertIsNone(server.first_sale({"ledger": [{"type": "cost", "amount_eur": 3, "date": "2026-01-01"}]}))
        s = {"ledger": [{"id": "tx_b", "type": "revenue", "amount_eur": 6.5, "date": "2026-03-02", "note": "Pacchetto · netto commissioni Polar"},
                        {"id": "tx_a", "type": "revenue", "amount_eur": 7.12, "date": "2026-03-01", "note": "Email di sollecito · netto commissioni Polar"},
                        {"id": "tx_z", "type": "revenue", "amount_eur": 0, "date": "2025-01-01"}]}
        self.assertEqual(server.first_sale(s), {"id": "tx_a", "date": "2026-03-01", "amount_eur": 7.12, "name": "Email di sollecito"})
        js = self.get("/scene3d.js")[1]
        self.assertIn("export function firstSaleParty", js)
        self.assertIn("party.check(d.world, DEMO)", self.get("/exchange.js")[1])  # shared by the rooms
        for page in ("office.html", "sales.html"):
            self.assertIn('from "./exchange.js"', self.get("/" + page)[1])

    def test_weather_kinds_and_city_lookup_cached(self):
        import io, json as _j
        import server
        self.assertEqual([server.wmo_kind(c) for c in (0, 3, 45, 61, 81, 73, 95)], ["clear", "clouds", "fog", "rain", "rain", "snow", "storm"])
        calls = []
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        def op(req, timeout=0):
            calls.append(req.full_url)
            if "geocoding" in req.full_url:
                return R(_j.dumps({"results": [{"latitude": 41.9, "longitude": 12.5, "name": "Roma"}]}).encode())
            return R(_j.dumps({"current": {"temperature_2m": 14.2, "weather_code": 63}}).encode())
        server._weather.update(ts=0, data=None, geo=None)
        w = server.city_weather(op)
        self.assertEqual((w["city"], w["kind"], w["temp"]), ("Roma", "rain", 14.2))
        server.city_weather(op)
        self.assertEqual(len(calls), 2)  # second call served from the cache

    def test_milestones_only_from_real_facts(self):
        import server
        s = {"ledger": [], "traffic": {"boots": {"b": {"counts": {"2026-10-02|opp_abc": {"v": 3, "c": 1, "r": {"www.linkedin.com": 2}, "p": {}}}}}}}
        g = server.growth_numbers(s, [])
        self.assertEqual((g["visits_total"], g["clicks_total"], g["linkedin_visits"]), (3, 1, 2))
        done = dict(g["milestones"])
        self.assertFalse(done["Prima strategia in paper trading"] or done["Primo guadagno reale"])
        g = server.growth_numbers({"ledger": [], "opportunities": [{"stage": "building"}], "signals": [{"id": "sig_1"}]}, [{"amount_eur": 5}])
        done = dict(g["milestones"])
        self.assertTrue(done["Prima strategia in paper trading"] and done["Primo segnale"] and done["Primo guadagno reale"])
        self.assertFalse(done["Prima strategia live"])


class OldHostRedirectTest(unittest.TestCase):
    def test_redirect_only_from_railway_address(self):
        import server
        old = server.SITE_URL
        try:
            server.SITE_URL = ""
            self.assertEqual(server.old_host_redirect("x-production.up.railway.app", "/s/"), "")  # no own domain yet
            server.SITE_URL = "https://pagapuntuale.com"
            self.assertEqual(server.old_host_redirect("x-production.up.railway.app", "/s/guida/?a=1"), "https://pagapuntuale.com/s/guida/?a=1")
            self.assertEqual(server.old_host_redirect("pagapuntuale.com", "/s/"), "")
            self.assertEqual(server.old_host_redirect("healthcheck.railway.app", "/healthz"), "")
            self.assertEqual(server.old_host_redirect("127.0.0.1:8787", "/"), "")
        finally:
            server.SITE_URL = old


if __name__ == "__main__":
    unittest.main()


class RoomsOfflineTest(unittest.TestCase):
    """The 3D rooms load three.js from the panel itself, not from a CDN (blocked by some antivirus/networks)."""

    def test_rooms_use_vendored_three(self):
        import json as _json
        import re as _re
        dash = os.path.join(os.path.dirname(__file__), "..", "dashboard")
        read = lambda n: open(os.path.join(dash, n), encoding="utf-8").read()
        modules = read("exchange.js") + read("scene3d.js")  # the rooms' shared code
        self.assertNotIn("cdn.jsdelivr", modules)
        for page in ("office.html", "sales.html"):
            html = read(page)
            self.assertNotIn("cdn.jsdelivr", html, page)
            imports = _json.loads(_re.search(r'<script type="importmap">(.*?)</script>', html, _re.S).group(1))["imports"]
            self.assertTrue(os.path.isfile(os.path.join(dash, imports["three"])), page)
            for mod in set(_re.findall(r'from "three/addons/([^"]+)"', html + modules)):
                self.assertTrue(os.path.isfile(os.path.join(dash, imports["three/addons/"], mod)), (page, mod))


class CandlesTest(unittest.TestCase):
    """Real candles for the room screens: whitelisted pairs only, Coinbase order fixed, cached, honest when down."""

    def test_candles_whitelist_order_and_failure(self):
        import io
        import json as _j
        import urllib.error
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
        import server
        server._candles.clear()
        self.assertEqual(server.crypto_candles("DOGE-EUR", "1h")["candles"], [])
        self.assertEqual(server.crypto_candles("BTC-EUR", "2m")["candles"], [])
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        calls = []
        def op(req, timeout=0):
            calls.append(req.full_url)
            return R(_j.dumps([[200, 9, 12, 10, 11, 5], [100, 8, 11, 9, 10, 4]]).encode())
        d = server.crypto_candles("btc-eur", "1h", opener=op)
        self.assertEqual(d["candles"], [[100, 9.0, 11.0, 8.0, 10.0, 4.0], [200, 10.0, 12.0, 9.0, 11.0, 5.0]])  # t, o, h, l, c, v
        self.assertIn("products/BTC-EUR/candles?granularity=3600", calls[0])
        server.crypto_candles("BTC-EUR", "1h", opener=op)
        self.assertEqual(len(calls), 1)  # cached for 60 s
        def down(req, timeout=0):
            raise urllib.error.URLError("offline")
        self.assertEqual(server.crypto_candles("ETH-EUR", "15m", opener=down)["candles"], [])


class WallDataTest(unittest.TestCase):
    """Data for the new wall screens: order book bands, fear & greed, monthly results. Honest when sources are down."""

    def setUp(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
        import server
        self.server = server

    def _op(self, payload):
        import io, json as _j
        class R(io.BytesIO):
            def __enter__(self): return self
            def __exit__(self, *a): return False
        return lambda req, timeout=0: R(_j.dumps(payload).encode())

    def test_orderbook_bands_and_failure(self):
        import urllib.error
        srv = self.server; srv._books.clear()
        book = {"bids": [["100.00", "2", 1], ["99.97", "1", 1], ["99.00", "9", 1]], "asks": [["100.02", "3", 1], ["100.06", "1", 1]]}
        d = srv.crypto_orderbook("BTC-EUR", opener=self._op(book))
        self.assertEqual(d["mid"], 100.01)
        self.assertEqual(len(d["bids"]), 14); self.assertEqual(len(d["asks"]), 14)
        self.assertAlmostEqual(sum(q for _, q in d["bids"]), 3)  # 99.00 is outside the 14 bands of 0.05%
        self.assertAlmostEqual(sum(q for _, q in d["asks"]), 4)
        self.assertEqual(srv.crypto_orderbook("DOGE-EUR")["bids"], [])
        def down(req, timeout=0): raise urllib.error.URLError("x")
        self.assertEqual(srv.crypto_orderbook("ETH-EUR", opener=down)["bids"], [])

    def test_fear_greed(self):
        srv = self.server; srv._fng.update(ts=0, data=None)
        d = srv.fear_greed(opener=self._op({"data": [{"value": "62", "value_classification": "Greed"}]}))
        self.assertEqual((d["value"], d["label"]), (62, "avidità"))

    def test_ledger_months(self):
        import datetime as dt
        led = [{"type": "revenue", "amount_eur": 5, "date": "2026-10-02"}, {"type": "revenue", "amount_eur": 2.5, "date": "2026-10-20"},
               {"type": "cost", "amount_eur": 9, "date": "2026-10-03"}, {"type": "revenue", "amount_eur": 1, "date": "2025-10-01"}]
        m = self.server.ledger_months(led, dt.date(2026, 10, 25))
        self.assertEqual(len(m), 12); self.assertEqual(m[0][0], "2025-11"); self.assertEqual(m[-1], ["2026-10", 7.5])

    def test_trades_taker_side(self):
        srv = self.server; srv._trades.clear()
        d = srv.crypto_trades("BTC-EUR", opener=self._op([{"time": "2026-10-05T01:13:02.1Z", "price": "76855.1", "size": "0.01", "side": "sell"},
                                                         {"time": "2026-10-05T01:13:01.0Z", "price": "76850", "size": "0.2", "side": "buy"}]))
        self.assertEqual(d["trades"][0], {"t": "01:13:02", "p": 76855.1, "q": 0.01, "buy": True})
        self.assertFalse(d["trades"][1]["buy"])
        self.assertEqual(srv.crypto_trades("XRP-EUR")["trades"], [])


class AutostartTest(unittest.TestCase):
    """The hosted panel starts the workflows at their scheduled minute (GitHub cron is often late or skipped)."""

    def test_slots_window_and_once(self):
        import datetime as dt
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
        import server
        T = lambda h, m: dt.datetime(2026, 10, 5, h, m)
        wfs = lambda now, done={}: sorted(w for w, _, _ in server.autostart_due(now, done))
        self.assertEqual(wfs(T(0, 17)), ["crypto-cycle.yml"])                   # 02:17 in Italy
        self.assertEqual(wfs(T(0, 40)), ["crypto-cycle.yml", "crypto-pulse.yml"])  # still inside the 25' window; pulse at :23
        self.assertEqual(wfs(T(0, 42)), ["crypto-pulse.yml"])                  # cycle window over (25'), pulse still open (20')
        self.assertEqual(wfs(T(0, 43)), [])
        self.assertEqual(wfs(T(1, 17)), [])                                     # no trading slot at 01:17 UTC
        self.assertEqual(wfs(T(23, 50)), ["crypto-rendite.yml"])                # pulse window (23:23-23:43) already over
        self.assertIn("crypto-rendite.yml", wfs(dt.datetime(2026, 10, 6, 0, 5)))  # 23:47 slot still open after midnight
        done = {k: True for _, k, _ in server.autostart_due(T(0, 20), {})}
        self.assertEqual(wfs(T(0, 21), done), [])                               # dispatched once per slot


class ManualCooldownTest(unittest.TestCase):
    def test_avvia_ciclo_twice_does_not_start_twice(self):
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dashboard"))
        import server
        calls = []
        saved = (server.GH_MODE, server._recent_run, server.gh_request)
        try:
            server.GH_MODE = True
            server.gh_request = lambda *a, **k: calls.append(a) or {}
            server._recent_run = lambda wf, since: True
            self.assertIn("già partito", server.run_cycle("trading"))
            self.assertEqual(calls, [])
            server._recent_run = lambda wf, since: False
            self.assertIn("avviato", server.run_cycle("trading"))
            self.assertEqual(len(calls), 1)
        finally:
            server.GH_MODE, server._recent_run, server.gh_request = saved
