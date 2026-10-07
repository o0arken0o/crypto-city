"""Standalone startup regressions; every running backend uses a disposable copy."""
import errno
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
ROOMS = ("btc", "eth", "sol", "xrp", "ada", "cro", "scanner", "quant",
         "risk", "portfolio", "yield", "chief")
SPEC = importlib.util.spec_from_file_location("standalone_city_test", ROOT / "start_city.py")
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def source_hashes(root):
    """State normalization belongs to the existing backend; source stays untouched."""
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()
            and path.relative_to(root).parts[0] not in ("state", ".git")
            and "__pycache__" not in path.parts}


class StartupSafetyTest(unittest.TestCase):
    def test_free_port_uses_bind_even_when_windows_connect_would_time_out(self):
        port = free_port()
        with mock.patch.object(socket, "create_connection", side_effect=socket.timeout("timed out")) as connect:
            self.assertFalse(launcher.port_occupied(port))
        connect.assert_not_called()

    def test_occupied_listener_is_not_contacted_or_closed(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((launcher.HOST, 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            self.assertTrue(launcher.port_occupied(port))
            listener.setblocking(False)
            with self.assertRaises(BlockingIOError):
                listener.accept()
            self.assertEqual(listener.getsockname()[1], port)
        self.assertFalse(launcher.port_occupied(port))

    def test_default_skips_occupied_port_within_bounded_range(self):
        with mock.patch.object(launcher, "port_occupied", side_effect=(True, False)) as probe:
            self.assertEqual(launcher.choose_port(), launcher.DEFAULT_PORT + 1)
        self.assertEqual([call.args[0] for call in probe.call_args_list],
                         [launcher.DEFAULT_PORT, launcher.DEFAULT_PORT + 1])

    def test_full_default_range_fails_instead_of_scanning_unbounded_ports(self):
        with mock.patch.object(launcher, "port_occupied", return_value=True) as probe:
            with self.assertRaises(launcher.CityError):
                launcher.choose_port()
        self.assertEqual(probe.call_count, launcher.PORT_ATTEMPTS)

    def test_explicit_occupied_port_fails_without_trying_another(self):
        with mock.patch.object(launcher, "port_occupied", return_value=True) as probe:
            with self.assertRaises(launcher.CityError):
                launcher.choose_port(launcher.DEFAULT_PORT)
        probe.assert_called_once_with(launcher.DEFAULT_PORT)

    def test_invalid_explicit_ports_fail_before_any_socket_is_created(self):
        for port in (0, -1, 65536, True, "8977"):
            with self.subTest(port=port), mock.patch.object(socket, "socket") as probe:
                with self.assertRaises(launcher.CityError):
                    launcher.choose_port(port)
                probe.assert_not_called()

    def test_bind_permission_error_is_not_treated_as_a_free_port(self):
        with mock.patch.object(socket, "socket") as factory:
            probe = factory.return_value.__enter__.return_value
            probe.bind.side_effect = PermissionError(errno.EACCES, "reserved port")
            with self.assertRaises(launcher.CityError):
                launcher.choose_port()

    def test_server_environment_forces_adjacent_local_state_and_no_autostart(self):
        inherited = {"MM_HOST": "0.0.0.0", "MM_PORT": "8787", "PORT": "8787",
                     "MM_STATE_DIR": "/some-other-project/state", "MM_AUTOSTART": "true",
                     "MM_GITHUB_REPO": "other/repository", "MM_GITHUB_TOKEN": "test-only-value",
                     "MM_GITHUB_BRANCH": "other-branch", "MM_GITHUB_API": "https://invalid.example",
                     "MM_TOKEN": "owner-auth-test-value"}
        with mock.patch.dict(os.environ, inherited, clear=True):
            environment = launcher.server_environment(ROOT, 8978)
            self.assertEqual(os.environ, inherited, "Do not alter the launcher's own environment")
        self.assertEqual(environment["MM_HOST"], "127.0.0.1")
        self.assertEqual(environment["MM_PORT"], "8978")
        self.assertEqual(Path(environment["MM_STATE_DIR"]), ROOT / "state")
        self.assertEqual(environment["MM_AUTOSTART"], "false")
        self.assertFalse(any(environment.get(key) for key in inherited if key.startswith("MM_GITHUB_")))
        self.assertEqual(environment["MM_TOKEN"], inherited["MM_TOKEN"], "Preserve owner authentication")

    def test_city_requires_each_of_the_twelve_rooms_exactly_once(self):
        html = (ROOT / "dashboard/index.html").read_bytes()
        self.assertTrue(launcher.valid_city(html))
        for room in ROOMS:
            with self.subTest(room=room):
                marker = ('data-city-room="' + room + '"').encode()
                self.assertFalse(launcher.valid_city(html.replace(marker, b"data-missing-room", 1)))
                duplicate = ('<a href="#city/' + room + '" data-city-room="' + room + '"></a>').encode()
                self.assertFalse(launcher.valid_city(html + duplicate))

    def test_command_line_starts_its_adjacent_project_without_install_or_picker(self):
        with mock.patch.object(launcher, "launch", return_value=(None, "http://127.0.0.1:8978")) as start:
            self.assertEqual(launcher.main(["--port", "8978", "--no-browser"]), 0)
        start.assert_called_once_with(port=8978, open_browser=False)


class ReadinessTest(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "dashboard/index.html").read_bytes()
        self.responses = {"/healthz": (200, b'{"ok":true}'),
                          "/plancia": (200, self.html),
                          "/api/state": (200, b'{"state":{"strategies":[],"agents":[],"cycle":0}}')}
        self.requests = []
        case = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                case.requests.append(("GET", self.path))
                status, body = case.responses.get(self.path, (404, b"missing"))
                self.send_response(status)
                self.send_header("Content-Type", "text/html" if self.path == "/plancia" else "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer((launcher.HOST, 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.base = "http://127.0.0.1:" + str(self.server.server_port)

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_exact_city_and_state_are_verified_before_readiness(self):
        self.assertFalse(launcher.verify_running_server(self.base, self.html))
        self.assertEqual({path for _, path in self.requests}, {"/healthz", "/plancia", "/api/state"})
        self.assertTrue(all(method == "GET" for method, _ in self.requests))

    def test_different_city_document_is_rejected_even_with_twelve_rooms(self):
        self.responses["/plancia"] = (200, self.html + b"\n<!-- different checkout -->")
        with self.assertRaises(launcher.CityError):
            launcher.verify_running_server(self.base, self.html)

    def test_unhealthy_service_is_rejected(self):
        self.responses["/healthz"] = (200, b'{"ok":false}')
        with self.assertRaises(launcher.CityError):
            launcher.verify_running_server(self.base, self.html)

    def test_invalid_state_json_is_rejected(self):
        self.responses["/api/state"] = (200, b"<html>not the project API</html>")
        with self.assertRaises(launcher.CityError):
            launcher.verify_running_server(self.base, self.html)

    def test_state_authentication_requirement_is_preserved(self):
        self.responses["/api/state"] = (401, b'{"error":"unauthorized"}')
        self.assertTrue(launcher.verify_running_server(self.base, self.html))


class ActualStartupTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="Crypto City standalone test with spaces ")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name) / "standalone project"
        shutil.copytree(ROOT, self.repo,
                        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".venv", "downloads"))

    def stop_owned_server(self, process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except Exception:
                process.kill()
                process.wait(timeout=5)

    def test_launch_serves_actual_adjacent_city_state_without_changing_source(self):
        original_state = (ROOT / "state/state.json").read_bytes()
        state_file = self.repo / "state/state.json"
        expected_state = json.loads(state_file.read_bytes())
        expected_state["cycle"] = 151515
        state_file.write_text(json.dumps(expected_state), encoding="utf-8")
        before = source_hashes(self.repo)
        port = free_port()
        environment = {"PYTHONDONTWRITEBYTECODE": "1", "MM_AUTOSTART": "true",
                       "MM_STATE_DIR": str(ROOT / "state"), "MM_HOST": "0.0.0.0",
                       "MM_GITHUB_REPO": "wrong/repository", "MM_GITHUB_TOKEN": "test-only-token",
                       "MM_TOKEN": "", "MM_CLAUDE": "nonexistent-test-command"}
        log_path = Path(self.temporary.name) / "owned-backend.log"
        log = log_path.open("wb")
        self.addCleanup(log.close)
        real_popen = launcher.subprocess.Popen

        def spawn_owned(*args, **kwargs):
            process = real_popen(*args, stdout=log, stderr=subprocess.STDOUT, **kwargs)
            self.addCleanup(self.stop_owned_server, process)
            return process

        with mock.patch.dict(os.environ, environment), \
                mock.patch.object(launcher.webbrowser, "open") as browser:
            with mock.patch.object(launcher.subprocess, "Popen", side_effect=spawn_owned):
                try:
                    process, base = launcher.launch(self.repo, port=port, open_browser=False, startup_timeout=15)
                except launcher.CityError as error:
                    self.fail(str(error) + "\n" + log_path.read_text(encoding="utf-8", errors="replace"))
            self.assertIsNone(process.poll())
            self.assertEqual(base, "http://127.0.0.1:" + str(port))
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(base + "/plancia", timeout=3) as response:
                actual_html = response.read()
            self.assertEqual(actual_html, (self.repo / "dashboard/index.html").read_bytes())
            with opener.open(base + "/api/state", timeout=3) as response:
                state = json.loads(response.read())
            self.assertIsInstance(state, dict)
            self.assertEqual(state["state"]["cycle"], 151515, "Read only the adjacent copy's local state")
            self.assertNotEqual(state.get("mode"), "github")
            with mock.patch.object(launcher.subprocess, "Popen") as another_process:
                with self.assertRaises(launcher.CityError):
                    launcher.launch(self.repo, port=port, open_browser=False)
            another_process.assert_not_called()
            self.assertIsNone(process.poll(), "An occupied matching server must not be stopped or reused")
            browser.assert_not_called()
            self.assertEqual(source_hashes(self.repo), before)
            self.assertEqual((ROOT / "state/state.json").read_bytes(), original_state)

    def test_explicit_foreign_listener_is_left_untouched_and_no_process_starts(self):
        before = source_hashes(self.repo)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind((launcher.HOST, 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            with mock.patch.object(launcher.subprocess, "Popen") as spawn:
                with self.assertRaises(launcher.CityError):
                    launcher.launch(self.repo, port=port, open_browser=False)
            spawn.assert_not_called()
            listener.setblocking(False)
            with self.assertRaises(BlockingIOError):
                listener.accept()
        self.assertEqual(source_hashes(self.repo), before)

    def test_invalid_adjacent_project_fails_before_process_or_file_changes(self):
        (self.repo / "dashboard/index.html").write_bytes(b"<html>old dashboard</html>")
        before = source_hashes(self.repo)
        with mock.patch.object(launcher.subprocess, "Popen") as spawn:
            with self.assertRaises(launcher.CityError):
                launcher.launch(self.repo, port=free_port(), open_browser=False)
        spawn.assert_not_called()
        self.assertEqual(source_hashes(self.repo), before)


if __name__ == "__main__":
    unittest.main()
