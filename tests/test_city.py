"""Crypto City regressions that need only Python and Node, with no network or server."""
import collections
import json
import pathlib
import shutil
import subprocess
import unittest
from html.parser import HTMLParser


ROOT = pathlib.Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
ROOM_IDS = ("btc", "eth", "sol", "xrp", "ada", "cro", "scanner", "quant",
            "risk", "portfolio", "yield", "chief")


class DashboardHTML(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.elements = []
        self.scripts = []
        self._script = None
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.elements.append((tag, attrs))
        if tag == "script":
            self._script = {"attrs": attrs, "code": ""}

    def handle_data(self, data):
        if self._script is not None:
            self._script["code"] += data

    def handle_endtag(self, tag):
        if tag == "script" and self._script is not None:
            self.scripts.append(self._script)
            self._script = None


class CityMarkupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = DashboardHTML((DASHBOARD / "index.html").read_text(encoding="utf-8"))

    def test_city_home_and_existing_views_have_unique_ids(self):
        ids = [attrs["id"] for _, attrs in self.html.elements if "id" in attrs]
        duplicates = [key for key, count in collections.Counter(ids).items() if count > 1]
        self.assertEqual(duplicates, [], "Duplicate IDs break room controls and legacy dashboard selectors")
        for expected in ("cityViewport", "cityStatus", "cityBuildings", "cityRoom", "cityRoomTitle"):
            self.assertIn(expected, ids)
        panes = [attrs["data-pane"] for _, attrs in self.html.elements if "data-pane" in attrs]
        self.assertEqual(len(panes), len(set(panes)))
        for pane in ("city", "oggi", "prodotti", "dafare", "team", "soldi", "mercati", "impostazioni"):
            self.assertIn(pane, panes)
        city = next(attrs for _, attrs in self.html.elements if attrs.get("data-pane") == "city")
        self.assertNotIn("hidden", city, "Crypto City must be the initial home before JavaScript loads")

    def test_city_navigation_drops_old_rooms_but_keeps_direct_routes(self):
        hrefs = {attrs.get("href") for _, attrs in self.html.elements}
        for route in ("office.html", "sales.html", "sims.html"):
            self.assertFalse(any(value and value.lstrip("./") == route for value in hrefs), route)
            self.assertTrue((DASHBOARD / route).is_file())
        self.assertIn("ai.html", hrefs, "Agent provider configuration remains useful in Settings")
        ids = {attrs.get("id") for _, attrs in self.html.elements}
        for obsolete in ("cityRoomLegacy", "btnSocial", "liBox", "trafTable", "homeComp"):
            self.assertNotIn(obsolete, ids)

    def test_installable_app_uses_city_branding_and_shortcuts(self):
        manifest = json.loads((DASHBOARD / "manifest.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "Crypto City")
        self.assertEqual(manifest["short_name"], "Crypto City")
        self.assertEqual({item["url"] for item in manifest["shortcuts"]},
                         {"/plancia#city", "/plancia#dafare", "/plancia#city/risk"})
        for name in ("index.html", "ai.html", "sw.js"):
            source = (DASHBOARD / name).read_text(encoding="utf-8")
            self.assertIn("Crypto City", source)
            self.assertNotIn("Crypto Machine", source)

    def test_city_scripts_are_read_only(self):
        scripts = [s for s in self.html.scripts if s["attrs"].get("id", "").startswith("city-")]
        self.assertGreaterEqual(len(scripts), 2)
        code = "\n".join(s["code"] for s in scripts)
        self.assertNotRegex(code, r"(?i)method\s*:\s*['\"](?:POST|PUT|PATCH|DELETE)['\"]")
        for protected_api in ("api/command", "api/cycle", "api/secret", "api/linkedin/start"):
            self.assertNotIn(protected_api, code)

    def test_charts_are_inline_for_existing_panel_servers(self):
        source = "\n".join(script["code"] for script in self.html.scripts)
        self.assertNotRegex(source, r"(?:from\s*|import\s*\()\s*['\"][^'\"]*charts\.js['\"]")
        self.assertFalse(any(script["attrs"].get("src", "").endswith("charts.js")
                             for script in self.html.scripts))
        chart_index = next(i for i, script in enumerate(self.html.scripts)
                           if script["attrs"].get("id") == "city-charts")
        terminal_index = next(i for i, script in enumerate(self.html.scripts)
                              if 'const ASSETS = ["BTC"' in script["code"])
        self.assertLess(chart_index, terminal_index,
                        "Chart helpers must exist before the trading terminal starts")


@unittest.skipUnless(shutil.which("node"), "Node is required to exercise inline chart helpers")
class CityInlineChartsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts = DashboardHTML((DASHBOARD / "index.html").read_text(encoding="utf-8")).scripts
        cls.charts = next(script["code"] for script in scripts
                          if script["attrs"].get("id") == "city-charts")

    def evaluate(self, expression):
        script = "const vm=require('node:vm'); const context=vm.createContext({});\n"
        script += "vm.runInContext(" + json.dumps(self.charts) + ",context);\n"
        script += "const result=vm.runInContext(" + json.dumps(expression) + ",context);\n"
        script += "process.stdout.write(JSON.stringify(result));"
        result = subprocess.run([shutil.which("node"), "-"], input=script, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_all_helpers_are_available_without_dom_or_modules(self):
        result = self.evaluate("""(() => {
          const helpers=globalThis.CryptoCityCharts;
          return {names:Object.keys(helpers).sort(), frozen:Object.isFrozen(helpers),
                  callable:Object.values(helpers).every(value=>typeof value==='function'),
                  price:helpers.fmtPrice(123.5,'EUR'), leaked:typeof globalThis.fmtPrice};
        })()""")
        self.assertEqual(result["names"], ["drawRealCandles", "fmtPrice", "sparkline"])
        self.assertTrue(result["frozen"])
        self.assertTrue(result["callable"])
        self.assertIn("123,50", result["price"])
        self.assertIn("€", result["price"])
        self.assertEqual(result["leaked"], "undefined")

    def test_missing_market_data_is_shown_without_invented_candles(self):
        result = self.evaluate("""(() => {
          const messages=[], rectangles=[], cleared=[];
          const canvas={fillRect(...args){rectangles.push(args);},
                        fillText(text){messages.push(text);},
                        clearRect(...args){cleared.push(args);}};
          CryptoCityCharts.drawRealCandles(canvas,640,400,null,'BTC / EUR');
          CryptoCityCharts.drawRealCandles(canvas,640,400,{loading:true,pair:'BTC-EUR'},'BTC / EUR');
          CryptoCityCharts.sparkline(canvas,100,25,[],true);
          return {messages,rectangles,cleared};
        })()""")
        self.assertEqual(result["messages"], ["BTC / EUR", "dati non disponibili",
                                              "BTC / EUR", "carico i dati…"])
        self.assertEqual(result["rectangles"], [[0, 0, 640, 400]] * 2)
        self.assertEqual(result["cleared"], [[0, 0, 100, 25]])

    def test_supplied_candles_render_without_mutating_market_data(self):
        result = self.evaluate("""(() => {
          const messages=[], values=[], candleColors=[];
          const canvas={fillRect(...args){values.push(...args);candleColors.push(this.fillStyle);},
                        fillText(text,...args){messages.push(text);values.push(...args);},
                        clearRect(...args){values.push(...args);},beginPath(){},stroke(){},
                        moveTo(...args){values.push(...args);},lineTo(...args){values.push(...args);},
                        closePath(){},fill(){},createLinearGradient(){return {addColorStop(){}};}};
          const data={pair:'BTC-EUR',candles:[[1700000000,100,110,90,105,20],
                                            [1700003600,105,109,95,102,30]]};
          const before=JSON.stringify(data);
          CryptoCityCharts.drawRealCandles(canvas,640,400,data,'BTC / EUR','#75becb',{volume:true});
          CryptoCityCharts.sparkline(canvas,100,25,data.candles,false);
          return {unchanged:JSON.stringify(data)===before, finite:values.every(Number.isFinite),
                  lastPrice:messages.includes(CryptoCityCharts.fmtPrice(102,'EUR')),
                  hasUp:candleColors.includes('#2fd59b'),hasDown:candleColors.includes('#ff4d6a')};
        })()""")
        self.assertEqual(result, {"unchanged": True, "finite": True, "lastPrice": True,
                                  "hasUp": True, "hasDown": True})


@unittest.skipUnless(shutil.which("node"), "Node is required to parse dashboard JavaScript")
class DashboardJavaScriptSyntaxTest(unittest.TestCase):
    def test_every_inline_classic_script_and_module_parses(self):
        count = 0
        for path in sorted(DASHBOARD.glob("*.html")):
            for index, script in enumerate(DashboardHTML(path.read_text(encoding="utf-8")).scripts):
                attrs, code = script["attrs"], script["code"]
                kind = attrs.get("type", "").lower()
                if "src" in attrs or kind not in ("", "module", "text/javascript", "application/javascript"):
                    continue
                with self.subTest(page=path.name, script=attrs.get("id", index)):
                    result = subprocess.run(
                        [shutil.which("node"), "--input-type=" + ("module" if kind == "module" else "commonjs"), "--check"],
                        input=code, text=True, capture_output=True, timeout=15)
                    self.assertEqual(result.returncode, 0, result.stderr)
                count += 1
        self.assertGreater(count, 0)

    def test_shared_dashboard_modules_parse(self):
        for path in sorted(DASHBOARD.glob("*.js")):
            with self.subTest(module=path.name):
                result = subprocess.run([shutil.which("node"), "--input-type=module", "--check"],
                                        input=path.read_text(encoding="utf-8"), text=True,
                                        capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr)


@unittest.skipUnless(shutil.which("node"), "Node is required for the pure room data adapter")
class CityDataModelTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scripts = DashboardHTML((DASHBOARD / "index.html").read_text(encoding="utf-8")).scripts
        cls.model = next(s["code"] for s in scripts if s["attrs"].get("id") == "city-model")

    def evaluate(self, expression, snapshot=None, live=None):
        script = "const vm=require('node:vm'); const context=vm.createContext({});\n"
        script += "vm.runInContext(" + json.dumps(self.model) + ",context);\n"
        script += "context.snapshot=" + json.dumps(snapshot or {}) + ";\n"
        script += "context.live=" + json.dumps(live or {}) + ";\n"
        script += "const result=vm.runInContext(" + json.dumps(
            "const {ROOMS,buildRoom,nextSchedule}=CryptoCityModel; " + expression) + ",context);\n"
        script += "process.stdout.write(JSON.stringify(result));"
        result = subprocess.run([shutil.which("node"), "-"], input=script, text=True,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_twelve_rooms_and_existing_agent_bindings(self):
        rooms = self.evaluate("ROOMS")
        self.assertEqual([room["id"] for room in rooms], list(ROOM_IDS))
        by_id = {room["id"]: room for room in rooms}
        for room in rooms:
            self.assertTrue(room["title"])
            self.assertIn(room["team"], ("trading", "rendite"))
        for room_id in ROOM_IDS[:6]:
            self.assertEqual(by_id[room_id]["asset"], room_id.upper())
        for room_id, agent in (("scanner", "market-scanner"), ("quant", "quant-analyst"),
                               ("risk", "risk-manager"), ("portfolio", "portfolio-analyst"),
                               ("yield", "yield-lead"), ("chief", "ceo")):
            self.assertIn(agent, by_id[room_id]["agents"])

    def test_missing_data_is_not_fabricated_from_global_kpis(self):
        rooms = self.evaluate("ROOMS.map(r=>buildRoom(r.id,snapshot,live,new Date('2026-10-07T00:00:00Z')))",
                              {"state": {}, "kpis": {"revenue_eur": 12345}})
        for room in rooms:
            self.assertIsNone(room["pnl"])
            self.assertFalse(room["lastRun"])
            self.assertEqual(room["strategies"], [])

    def test_asset_views_use_explicit_asset_tokens_and_linked_market(self):
        state = {"state": {"status": "running", "markets": [{"id": "btc-market", "name": "BTC/USD"}],
                            "opportunities": [
                                {"id": "btc", "title": "BTC trend", "stage": "building"},
                                {"id": "linked", "title": "Trend", "market": "btc-market", "stage": "validating"},
                                {"id": "eth", "title": "ETH trend", "stage": "building"},
                                {"id": "substring", "title": "Canadian crowd rotation", "stage": "idea"}]}}
        result = self.evaluate("['btc','eth','ada','cro'].map(id=>buildRoom(id,snapshot,live).strategies.map(s=>s.id))", state)
        self.assertEqual(set(result[0]), {"btc", "linked"})
        self.assertEqual(result[1], ["eth"])
        self.assertEqual(result[2:], [[], []])

    def test_asset_pnl_is_attributed_only_to_its_ledger_entries(self):
        state = {"state": {"status": "running", "opportunities": [
            {"id": "btc", "title": "BTC trend", "stage": "building"},
            {"id": "eth", "title": "ETH trend", "stage": "building"}], "ledger": [
                {"type": "revenue", "amount_eur": 12.5, "opportunity": "btc"},
                {"type": "revenue", "amount_eur": 900, "opportunity": "unrelated"}]},
                 "kpis": {"revenue_eur": 912.5}}
        result = self.evaluate("['btc','eth'].map(id=>buildRoom(id,snapshot,live).pnl)", state)
        self.assertEqual(result, [12.5, None])

    def test_pnl_counts_attributed_costs_and_preserves_recorded_zero(self):
        state = {"state": {"opportunities": [
            {"id": "btc", "title": "BTC trend", "stage": "live"},
            {"id": "eth", "title": "ETH trend", "stage": "building"}], "ledger": [
                {"type": "revenue", "amount_eur": 10, "opportunity": "btc"},
                {"type": "cost", "amount_eur": 3, "opportunity": "btc"},
                {"type": "revenue", "amount_eur": "500", "opportunity": "btc"},
                {"type": "revenue", "amount_eur": 0, "opportunity": "eth"}]}}
        self.assertEqual(self.evaluate("['btc','eth'].map(id=>buildRoom(id,snapshot,live).pnl)", state), [7, 0])

    def test_backtest_performance_is_not_real_money_pnl(self):
        state = {"state": {"opportunities": [{"id": "btc", "title": "BTC trend", "stage": "building"}]}}
        live = {"trading": {"world": {"opps": [{"id": "btc", "perf": "backtest +27%; paper +4%"}]}}}
        result = self.evaluate("buildRoom('btc',snapshot,live)", state, live)
        self.assertIsNone(result["pnl"])
        self.assertEqual(result["strategies"][0]["perf"], "backtest +27%; paper +4%")

    def test_historical_losses_from_killed_strategies_remain_in_asset_pnl(self):
        snapshot = {"state": {"opportunities": [
            {"id": "old-btc", "title": "BTC old strategy", "stage": "killed"},
            {"id": "active-btc", "title": "BTC current strategy", "stage": "building"}],
            "ledger": [{"type": "cost", "amount_eur": 50, "opportunity": "old-btc"},
                       {"type": "revenue", "amount_eur": 10, "opportunity": "active-btc"}]}}
        result = self.evaluate("buildRoom('btc',snapshot,live)", snapshot)
        self.assertEqual(result["pnl"], -40)
        self.assertEqual([strategy["id"] for strategy in result["strategies"]], ["active-btc"])

    def test_missing_live_activity_is_not_reported_as_verified_idleness(self):
        snapshot = {"state": {"status": "running", "agents": {"market-scanner": {"status": "active"}}}}
        result = self.evaluate("buildRoom('scanner',snapshot,live)", snapshot)
        self.assertEqual(result["status"], "Attività non disponibile")
        self.assertFalse(result["lastRun"])

    def test_yield_room_uses_its_own_team_activity(self):
        snapshot = {"state": {"agents": {"yield-lead": {"status": "active"}}}}
        live = {"trading": {"agents": {"yield-lead": {"task": "Wrong trading team task"}}},
                "rendite": {"agents": {"yield-lead": {"status": "working", "task": "Real yield team task"}}}}
        result = self.evaluate("buildRoom('yield',snapshot,live)", snapshot, live)
        self.assertEqual(result["task"], "Real yield team task")
        self.assertEqual(result["status"], "Al lavoro")

    def test_real_agent_activity_is_not_presented_as_a_dedicated_asset_agent(self):
        state = {"state": {"status": "running", "agents": {"market-scanner": {
            "status": "active", "last_run": "2026-10-06T22:17:00Z"}}}}
        live = {"trading": {"phase": "working", "agents": {"market-scanner": {
            "status": "working", "task": "Scanner task from live data", "last_run": "2026-10-06T22:17:00Z"}}}}
        result = self.evaluate("['scanner','btc'].map(id=>buildRoom(id,snapshot,live))", state, live)
        self.assertEqual(result[0]["lastRun"], "2026-10-06T22:17:00Z")
        self.assertIn("Scanner task from live data", result[0]["task"])
        self.assertFalse(result[1]["lastRun"])

    def test_next_cycles_follow_utc_schedules_and_respect_pause(self):
        expression = "['btc','yield'].map(id=>buildRoom(id,snapshot,live,new Date('2026-10-06T23:59:00Z')).nextCycle)"
        result = self.evaluate(expression, {"state": {"status": "running"}})
        self.assertEqual(result, ["2026-10-07T00:17:00.000Z", "2026-10-07T23:47:00.000Z"])
        self.assertEqual(self.evaluate(expression, {"state": {"status": "paused"}}), [None, None])

    def test_room_adapter_does_not_modify_api_snapshots(self):
        snapshot = {"state": {"status": "running", "agents": {}, "ledger": [], "opportunities": []}}
        result = self.evaluate("(()=>{const before=JSON.stringify([snapshot,live]); ROOMS.forEach(r=>buildRoom(r.id,snapshot,live)); return before===JSON.stringify([snapshot,live]);})()", snapshot)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
