"""Regression for the Windows package on a checkout without charts.js."""
import hashlib
import errno
import importlib.util
from pathlib import Path
import shutil
import socket
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[1]


class CityPackageTest(unittest.TestCase):
    package_filename = "crypto-city-update.zip"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="city-package-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        with zipfile.ZipFile(ROOT / "downloads" / self.package_filename) as archive:
            self.assertIsNone(archive.testzip())
            for name in archive.namelist():
                self.assertFalse(Path(name).is_absolute())
                self.assertNotIn("..", Path(name).parts)
            archive.extractall(self.root / "package")
        installer = next((self.root / "package").rglob("install_city.py"))
        spec = importlib.util.spec_from_file_location("city_package_test", installer)
        self.installer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.installer)
        self.repo = self.root / "existing project with spaces"
        for name in ("dashboard/server.py", "engine/mm.py", "state/state.json", "POLICY.md",
                     "dashboard/vendor/three/three.module.min.js",
                     "dashboard/vendor/three/addons/controls/OrbitControls.js"):
            target = self.repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        self.previous_html = b"<!doctype html><title>Previous local dashboard</title>"
        (self.repo / "dashboard/index.html").write_bytes(self.previous_html)

    def protected_hashes(self):
        return {str(path.relative_to(self.repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.repo.rglob("*") if path.is_file()
                and path.relative_to(self.repo).parts[0] != "dashboard"}

    def test_missing_charts_module_does_not_block_ui_only_installation(self):
        self.assertFalse((self.repo / "dashboard/charts.js").exists())
        protected = self.protected_hashes()
        server = (self.repo / "dashboard/server.py").read_bytes()
        backup = self.installer.install(self.repo)
        self.assertEqual(backup.read_bytes(), self.previous_html)
        self.assertEqual((self.repo / "dashboard/index.html").read_bytes(),
                         (ROOT / "dashboard/index.html").read_bytes())
        self.assertEqual(self.protected_hashes(), protected)
        self.assertEqual((self.repo / "dashboard/server.py").read_bytes(), server)
        self.assertFalse((self.repo / "dashboard/charts.js").exists())
        self.assertEqual(self.installer.find_repo(), self.repo)
        backups = list((self.repo / "dashboard/.crypto-city-backups").iterdir())
        self.assertIsNone(self.installer.install(self.repo))
        self.assertEqual(list((self.repo / "dashboard/.crypto-city-backups").iterdir()), backups)

    def test_incompatible_checkout_is_left_unchanged(self):
        (self.repo / "dashboard/server.py").unlink()
        previous = {str(path.relative_to(self.repo)): path.read_bytes()
                    for path in self.repo.rglob("*") if path.is_file()}
        with self.assertRaises(self.installer.CityError):
            self.installer.install(self.repo)
        current = {str(path.relative_to(self.repo)): path.read_bytes()
                   for path in self.repo.rglob("*") if path.is_file()}
        self.assertEqual(current, previous)
        self.assertFalse(self.installer.LOCAL_CONFIG.exists())


class CityStartPackageTest(CityPackageTest):
    package_filename = "Crypto-City-START.zip"

    def test_external_folder_resolves_its_single_inner_project(self):
        self.assertEqual(self.installer.resolve_repo(self.root), self.repo)
        self.assertFalse(self.installer.LOCAL_CONFIG.exists())

    def test_external_folder_with_multiple_projects_requires_a_choice(self):
        shutil.copytree(self.repo, self.root / "another project")
        protected = self.protected_hashes()
        with self.assertRaises(self.installer.CityError):
            self.installer.resolve_repo(self.root)
        self.assertEqual(self.protected_hashes(), protected)
        self.assertEqual((self.repo / "dashboard/index.html").read_bytes(), self.previous_html)
        self.assertFalse(self.installer.LOCAL_CONFIG.exists())

    def test_one_desktop_project_is_found_without_path_entry(self):
        home = self.root / "home"
        project = home / "Desktop/crypto-machine-download (3)/inner project"
        shutil.copytree(self.repo, project)
        with mock.patch.object(Path, "home", return_value=home), \
                mock.patch.object(Path, "cwd", return_value=self.installer.PACKAGE), \
                mock.patch.object(self.installer, "choose_repo", side_effect=AssertionError("unexpected chooser")):
            self.assertEqual(self.installer.find_repo(), project)
        self.assertFalse(self.installer.LOCAL_CONFIG.exists())

    def test_multiple_desktop_projects_are_not_selected_arbitrarily(self):
        home = self.root / "home"
        for name in ("crypto-machine-first", "crypto-machine-second"):
            shutil.copytree(self.repo, home / "Desktop" / name / "inner project")
        with mock.patch.object(Path, "home", return_value=home), \
                mock.patch.object(Path, "cwd", return_value=self.installer.PACKAGE), \
                mock.patch.object(self.installer, "choose_repo", side_effect=self.installer.CityError("choice required")) as chooser:
            with self.assertRaises(self.installer.CityError):
                self.installer.find_repo()
        chooser.assert_called_once()
        self.assertFalse(self.installer.LOCAL_CONFIG.exists())

    def test_free_port_probe_does_not_require_a_tcp_connection(self):
        with socket.socket() as free:
            free.bind(("127.0.0.1", 0))
            port = free.getsockname()[1]
        with mock.patch.object(socket, "create_connection", side_effect=socket.timeout("Windows connect timeout")) as connect:
            self.assertFalse(self.installer.port_occupied(port))
        connect.assert_not_called()

    def test_listener_is_detected_without_connecting_or_closing_it(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            self.assertTrue(self.installer.port_occupied(port))
            self.assertEqual(listener.getsockname()[1], port)
        self.assertFalse(self.installer.port_occupied(port))

    def test_bind_permission_error_does_not_start_a_server(self):
        self.installer.install(self.repo)
        with mock.patch.object(socket, "socket") as factory, \
                mock.patch.object(self.installer.subprocess, "Popen") as spawn:
            probe = factory.return_value.__enter__.return_value
            probe.bind.side_effect = PermissionError(errno.EACCES, "port unavailable")
            with self.assertRaises(self.installer.CityError):
                self.installer.launch(self.repo, open_browser=False)
        spawn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
