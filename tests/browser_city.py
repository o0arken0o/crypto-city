"""Optional real-browser Crypto City regressions.

Run with ``python3 tests/browser_city.py`` after installing Playwright and Chromium.
The server uses a temporary state copy and a local test token. No live workflows,
external market requests, commands, orders, or repository state writes are made.
"""
import copy
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


ROOT = pathlib.Path(__file__).resolve().parents[1]
CHROMIUM = os.environ.get("CITY_TEST_CHROMIUM") or shutil.which("chromium") or shutil.which("chromium-browser")
TEST_TOKEN = "crypto-city-local-browser-test"
ROOMS = {"btc": "BTC Trader", "eth": "ETH Trader", "sol": "SOL Trader", "xrp": "XRP Trader",
         "ada": "ADA Trader", "cro": "CRO Trader", "scanner": "Market Scanner", "quant": "Quant Analyst",
         "risk": "Risk Manager", "portfolio": "Portfolio Manager", "yield": "Yield Agent",
         "chief": "Chief Trading Agent"}


@unittest.skipUnless(sync_playwright and CHROMIUM, "Install Playwright and Chromium to run browser regressions")
class CryptoCityBrowserTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="crypto-city-browser-")
        cls.state_dir = pathlib.Path(cls.temporary.name) / "state"
        cls.state_dir.mkdir()
        shutil.copy2(ROOT / "state" / "state.json", cls.state_dir / "state.json")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        cls.base = "http://127.0.0.1:" + str(port)
        # These requests are loopback only; an inherited external HTTP proxy
        # must not receive local test traffic or the disposable test token.
        cls.local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        env = os.environ.copy()
        for name in ("PORT", "MM_GITHUB_REPO", "MM_GITHUB_TOKEN", "MM_SITE_URL", "MM_LINKEDIN_REDIRECT", "RAILWAY_PUBLIC_DOMAIN"):
            env.pop(name, None)
        env.update(MM_HOST="127.0.0.1", MM_PORT=str(port), MM_STATE_DIR=str(cls.state_dir),
                   MM_AUTOSTART="false", MM_TOKEN=TEST_TOKEN)
        cls.server_log = open(pathlib.Path(cls.temporary.name) / "server.log", "w+", encoding="utf-8")
        cls.server = subprocess.Popen([sys.executable, str(ROOT / "dashboard" / "server.py")],
                                      cwd=ROOT, env=env, stdout=cls.server_log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with cls.local_http.open(cls.base + "/healthz", timeout=1) as response:
                    if response.status == 200:
                        break
            except (urllib.error.URLError, OSError):
                if cls.server.poll() is not None:
                    cls.server_log.seek(0)
                    raise RuntimeError("Test server failed: " + cls.server_log.read())
                time.sleep(.05)
        else:
            cls.server.terminate()
            raise RuntimeError("Test server did not become ready")
        req = urllib.request.Request(cls.base + "/api/state", headers={"X-MM-Token": TEST_TOKEN})
        with cls.local_http.open(req, timeout=3) as response:
            cls.snapshot = json.load(response)
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            executable_path=CHROMIUM, headless=True,
            args=["--no-sandbox", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--disable-dev-shm-usage"])

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "browser"):
            cls.browser.close()
            cls.playwright.stop()
        if hasattr(cls, "server"):
            cls.server.terminate()
            try:
                cls.server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                cls.server.kill()
                cls.server.wait(timeout=5)
        if hasattr(cls, "server_log"):
            cls.server_log.close()
        if hasattr(cls, "temporary"):
            cls.temporary.cleanup()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 1440, "height": 1100},
                                                device_scale_factor=1, service_workers="block")
        self.context.add_init_script("localStorage.setItem('mm-token'," + json.dumps(TEST_TOKEN) + ");")
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)
        self.errors = []
        self.writes = []
        self.page.on("pageerror", lambda error: self.errors.append(str(error)))
        self.page.on("request", lambda request: self.writes.append(request.url)
                     if request.method not in ("GET", "HEAD", "OPTIONS") else None)
        self.page.on("dialog", lambda dialog: dialog.dismiss())
        self.context.route("**/api/**", self.fixture_api)

    def tearDown(self):
        self.context.close()
        self.assertEqual(self.errors, [], "Uncaught JavaScript errors can leave a white screen")
        self.assertEqual(self.writes, [], "City navigation must never issue commands or orders")

    def fixture_api(self, route):
        url = urllib.parse.urlsplit(route.request.url)
        query = urllib.parse.parse_qs(url.query)
        path = url.path
        if path == "/api/state":
            return route.continue_()  # exercise the real authenticated local state endpoint
        if route.request.headers.get("x-mm-token") != TEST_TOKEN:
            return route.fulfill(status=401, json={"error": "token"})
        if path == "/api/live":
            team = query.get("team", ["trading"])[0]
            agents = {name: {"desc": item.get("desc", ""), "paused": item.get("status") != "active",
                             "status": "working", "task": "Live task for " + name,
                             "last_run": item.get("last_run"), "runs": item.get("runs", 0)}
                      for name, item in self.snapshot["state"].get("agents", {}).items()}
            result = {"team": team, "phase": "working", "system": "running", "cycle": 10,
                      "run": {"status": "in_progress", "started": "2026-10-07T00:17:00Z"},
                      "live": {"updated": "2026-10-07T00:17:00Z"}, "agents": agents,
                      "world": {"opps": [], "markets": [], "signals": [], "kpi": {}},
                      "events": [], "report": None, "mode": "live"}
        elif path == "/api/candles":
            result = {"pair": query.get("pair", ["BTC-EUR"])[0], "tf": query.get("tf", ["1h"])[0],
                      "source": "Deterministic browser fixture", "ts": 1791331200,
                      "candles": [[1791324000 + i * 3600, 100 + i, 104 + i, 98 + i, 102 + i, 2 + i]
                                  for i in range(24)]}
        elif path == "/api/orderbook":
            result = {"pair": "BTC-EUR", "mid": 101, "bids": [[100, 1]], "asks": [[102, 1]]}
        elif path == "/api/trades":
            result = {"trades": [{"t": "00:17:00", "p": 101, "q": .1, "buy": True}]}
        elif path == "/api/prices":
            result = {"prices": [{"asset": room.upper(), "eur": 100, "move": 0} for room in list(ROOMS)[:6]]}
        elif path == "/api/feargreed":
            result = {"value": 50, "label": "neutrale", "source": "Browser fixture"}
        elif path == "/api/weather":
            result = {"city": "Roma", "kind": "clear", "temp": 20}
        elif path == "/api/secrets":
            result = {"secrets": {}}
        elif path == "/api/ai":
            result = {"providers": {}}
        else:
            return route.fulfill(status=404, json={"error": "Unknown test API"})
        return route.fulfill(json=result)

    def load_city(self, path="/plancia"):
        self.page.goto(self.base + path, wait_until="domcontentloaded")
        self.page.locator('[data-pane="city"]').wait_for(state="visible")
        self.page.wait_for_function("document.querySelectorAll('#cityBuildings [data-city-room]').length===12")
        self.assertTrue(self.page.locator("#cityStatus").inner_text().strip())

    def open_room(self, room_id):
        self.page.locator('#cityBuildings [data-city-room="' + room_id + '"]').click()
        self.page.locator("#cityRoom").wait_for(state="visible")
        self.assertEqual(self.page.locator("#cityRoomTitle").text_content().strip(), ROOMS[room_id])
        self.assertIn("#city/" + room_id, self.page.url)

    def close_room(self):
        self.page.keyboard.press("Escape")
        self.page.locator("#cityRoom").wait_for(state="hidden")

    def test_home_renders_3d_and_all_twelve_rooms_are_read_only(self):
        self.load_city()
        self.page.wait_for_function("document.querySelector('#cityViewport').dataset.renderer==='webgl'", timeout=20000)
        self.page.locator("#cityViewport canvas").first.wait_for(state="visible", timeout=20000)
        box = self.page.locator("#cityViewport canvas").first.bounding_box()
        self.assertGreater(box["width"], 400)
        self.assertGreater(box["height"], 250)
        self.open_room("scanner")
        self.page.wait_for_function("document.querySelector('#cityRoom').textContent.includes('Live task for market-scanner')", timeout=10000)
        self.close_room()
        for room_id in ROOMS:
            with self.subTest(room=room_id):
                self.open_room(room_id)
                body = self.page.locator("#cityRoom").inner_text().lower()
                task_label = "prossimo passo" if room_id in list(ROOMS)[:6] else "compito"
                for label in ("stato", "ultimo", task_label, "strateg", "paper", "p&l", "rischio", "ciclo"):
                    self.assertIn(label, body)
                self.close_room()

    def test_actual_scene_building_can_be_selected_with_pointer(self):
        self.load_city()
        self.page.wait_for_function("document.querySelector('#cityViewport').dataset.renderer==='webgl'", timeout=20000)
        canvas = self.page.locator("#cityViewport canvas").first
        canvas.wait_for(state="visible", timeout=20000)
        canvas.scroll_into_view_if_needed()
        box = canvas.bounding_box()
        # A regular screen grid hits building geometry through the renderer's
        # real pointer handlers and raycaster, without a test-only application API.
        selected = False
        for row in (5, 4, 6, 3, 7, 2):
            for col in range(1, 12):
                x = box["x"] + box["width"] * col / 12
                y = box["y"] + box["height"] * row / 9
                if not self.page.evaluate("([x,y])=>document.elementFromPoint(x,y)?.matches('#cityViewport canvas')", [x, y]):
                    continue  # exercise geometry, rather than a projected HTML label
                self.page.mouse.click(x, y)
                if self.page.evaluate("location.hash.startsWith('#city/')"):
                    self.page.locator("#cityRoom").wait_for(state="visible")
                    selected = True
                    break
            if selected:
                break
        self.assertTrue(selected, "Clicking visible 3D building geometry must open a room")
        self.assertIn(self.page.locator("#cityRoomTitle").text_content().strip(), ROOMS.values())

    def test_mobile_rooms_remain_usable_without_horizontal_overflow(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.load_city()
        self.assertLessEqual(self.page.evaluate("document.documentElement.scrollWidth"), 392)
        self.open_room("risk")
        box = self.page.locator("#cityRoom").bounding_box()
        self.assertGreaterEqual(box["x"], -1)
        self.assertLessEqual(box["x"] + box["width"], 391)
        self.assertLessEqual(box["height"], 844)
        self.close_room()
        self.open_room("cro")

    def test_mobile_building_labels_keep_readable_touch_targets(self):
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.load_city()
        self.page.wait_for_function("document.querySelector('#cityViewport').dataset.renderer==='webgl'", timeout=20000)
        labels = self.page.locator(".city-scene-label").evaluate_all("""elements=>elements.map(element=>{
            const r=element.getBoundingClientRect();
            const points=[[.5,.5],[.2,.2],[.8,.2],[.2,.8],[.8,.8]];
            return {id:element.dataset.cityBuilding,label:element.getAttribute('aria-label'),
                visible:getComputedStyle(element).visibility==='visible',
                x:r.x,y:r.y,w:r.width,h:r.height,
                exposed:points.some(([x,y])=>document.elementFromPoint(r.x+r.width*x,r.y+r.height*y)?.closest('.city-scene-label')===element)};
        })""")
        visible = [label for label in labels if label["visible"]]
        self.assertEqual(len(visible), 12)
        for label in visible:
            with self.subTest(label=label["id"]):
                self.assertGreaterEqual(label["h"], 43.9)  # tolerate transformed DOM subpixel rounding
                self.assertIn(ROOMS[label["id"]], label["label"])
                self.assertTrue(label["exposed"], "Every building label needs an unobstructed touch area")
        for index, first in enumerate(visible):
            for second in visible[index + 1:]:
                width = max(0, min(first["x"] + first["w"], second["x"] + second["w"]) - max(first["x"], second["x"]))
                height = max(0, min(first["y"] + first["h"], second["y"] + second["h"]) - max(first["y"], second["y"]))
                overlap = width * height / min(first["w"] * first["h"], second["w"] * second["h"])
                self.assertLessEqual(overlap, .45, f"Mobile labels {first['id']} and {second['id']} overlap too much")

    def test_existing_hashes_and_server_routes_remain_compatible(self):
        self.load_city()
        for pane in ("oggi", "prodotti", "dafare", "team", "soldi", "mercati", "impostazioni", "city"):
            with self.subTest(pane=pane):
                self.page.evaluate("value => { location.hash=value; }", pane)
                self.page.locator('[data-pane="' + pane + '"]').wait_for(state="visible")
        for route in ("/plancia", "/plancia/", "/index.html", "/office.html", "/sales.html", "/ai.html", "/sims.html"):
            with self.subTest(route=route):
                response = self.context.request.get(self.base + route)
                self.assertEqual(response.status, 200)
                self.assertIn("text/html", response.headers.get("content-type", ""))

    def test_room_and_terminal_charts_work_without_external_charts_module(self):
        # Older Windows checkouts have neither charts.js nor its server route.
        # A valid market response must still produce both charts without a
        # module load failure leaving the terminal or the City room blank.
        chart_requests = []
        self.page.on("request", lambda request: chart_requests.append(request.url)
                     if urllib.parse.urlsplit(request.url).path == "/charts.js" else None)
        self.context.route("**/charts.js*", lambda route: route.fulfill(status=404, body="missing"))
        self.load_city()
        self.open_room("btc")
        self.page.wait_for_function("document.querySelector('#cityChartNote').textContent.includes('Prezzi pubblici Coinbase')")
        self.page.locator("#cityRoomChart").wait_for(state="visible")
        self.assertEqual(self.page.locator("#cityRoomChart").evaluate(
            "canvas=>canvas.getContext('2d').getImageData(0,0,1,1).data[3]"), 255)
        self.close_room()
        self.page.evaluate("location.hash='oggi'")
        self.page.locator('[data-pane="oggi"]').wait_for(state="visible")
        self.page.wait_for_function("document.querySelector('#chead .last').textContent!=='—'")
        self.assertEqual(self.page.locator("#mktChart").evaluate(
            "canvas=>canvas.getContext('2d').getImageData(0,0,1,1).data[3]"), 255)
        self.assertEqual(chart_requests, [], "The home must work without a charts.js route")

    def test_deep_link_unknown_hash_and_browser_back(self):
        self.load_city("/plancia#city/eth")
        self.page.locator("#cityRoom").wait_for(state="visible")
        self.assertEqual(self.page.locator("#cityRoomTitle").text_content().strip(), ROOMS["eth"])
        self.close_room()
        self.open_room("btc")
        self.page.go_back()
        self.page.locator("#cityRoom").wait_for(state="hidden")
        self.assertTrue(self.page.url.endswith("#city"))
        self.open_room("btc")
        self.close_room()
        self.page.evaluate("location.hash='unrecognized-view'")
        self.page.locator('[data-pane="city"]').wait_for(state="visible")
        self.assertFalse(self.page.locator("#cityRoom").is_visible())

    def test_hostile_hash_quotes_do_not_become_javascript_or_selectors(self):
        self.load_city()
        for value in ('city/\"<img src=x onerror=alert(1)>', '\"]:not(*)', "city/not-an-agent"):
            with self.subTest(hash=value):
                self.page.evaluate("value=>{location.hash=value}", value)
                self.page.locator('[data-pane="city"]').wait_for(state="visible")
                self.assertFalse(self.page.locator("#cityRoom").is_visible())
        self.open_room("chief")

    def test_webgl_context_loss_falls_back_to_usable_directory(self):
        self.load_city()
        self.page.wait_for_function("document.querySelector('#cityViewport').dataset.renderer==='webgl'", timeout=20000)
        lost = self.page.evaluate("""() => {
            const context=document.querySelector('#cityViewport canvas').getContext('webgl2');
            const extension=context?.getExtension('WEBGL_lose_context');
            if(!extension) return false;
            extension.loseContext(); return true;
        }""")
        self.assertTrue(lost, "Chromium should support a real WebGL context-loss test")
        self.page.wait_for_function("document.querySelector('#cityViewport').dataset.renderer==='fallback'")
        self.open_room("risk")

    def test_offline_api_failures_keep_city_and_directory_visible(self):
        self.context.unroute("**/api/**")
        self.context.route("**/api/**", lambda route: route.abort("failed"))
        self.context.route("**/state.json", lambda route: route.abort("failed"))
        self.context.route("**/config.json", lambda route: route.abort("failed"))
        self.load_city()
        self.open_room("btc")
        self.assertIn("disponibil", self.page.locator("#cityRoom").inner_text().lower())

    def test_failed_three_module_keeps_accessible_building_directory(self):
        self.context.route("**/vendor/three/**", lambda route: route.abort("failed"))
        self.load_city()
        self.page.wait_for_function("!document.querySelector('#cityStatus').textContent.includes('Caricamento')")
        self.open_room("chief")

    def test_webgl_unavailable_keeps_rooms_accessible(self):
        self.context.add_init_script("""
            const original=HTMLCanvasElement.prototype.getContext;
            HTMLCanvasElement.prototype.getContext=function(kind,...args){
                if(String(kind).includes('webgl')) return null;
                return original.call(this,kind,...args);
            };
        """)
        self.load_city()
        self.open_room("yield")

    def test_missing_authentication_does_not_expose_private_state(self):
        self.context.add_init_script("localStorage.removeItem('mm-token');")
        self.load_city()
        response = self.context.request.get(self.base + "/api/state")
        self.assertEqual(response.status, 401)
        self.open_room("scanner")
        self.assertNotIn("Live task for market-scanner", self.page.locator("#cityRoom").inner_text())

    def test_untrusted_room_data_is_text_and_cannot_execute_script(self):
        payload = "BTC <img src=x onerror=\"globalThis.cityXss='executed'\">"
        snapshot = copy.deepcopy(self.snapshot)
        opportunity = copy.deepcopy(snapshot["state"]["opportunities"][0])
        opportunity.update(id="browser-xss", title=payload, work_title=payload,
                           rules=payload, next_action=payload, stage="building", strategy="trend-following")
        snapshot["state"]["opportunities"] = [opportunity]
        self.context.route("**/api/state", lambda route: route.fulfill(json=snapshot))
        self.load_city()
        self.open_room("btc")
        self.assertIn(payload, self.page.locator("#cityRoom").inner_text())
        self.assertEqual(self.page.locator("#cityRoom img[onerror]").count(), 0)
        self.assertIsNone(self.page.evaluate("globalThis.cityXss || null"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
