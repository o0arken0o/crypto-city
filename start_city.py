#!/usr/bin/env python3
"""Start the adjacent Crypto City checkout with Python's standard library.

The launcher does not install, copy, search for or update another project. Each
invocation starts its own local server on a free port; existing listeners are
never contacted or reused during port selection.
"""
import argparse
import errno
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser


ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
DEFAULT_PORT = 8977
PORT_ATTEMPTS = 20
ROOMS = {"btc", "eth", "sol", "xrp", "ada", "cro", "scanner", "quant", "risk", "portfolio", "yield", "chief"}


class CityError(Exception):
    """An actionable local startup failure."""


class CityHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.model = False
        self.rooms = []
        self.invalid_room = False

    def handle_starttag(self, tag, attrs):
        if tag == "a" and any(name == "data-city-room" for name, _ in attrs):
            names = [name for name, _ in attrs]
            if names.count("data-city-room") != 1 or names.count("href") != 1:
                self.invalid_room = True
        attrs = dict(attrs)
        if tag == "script" and attrs.get("id") == "city-model":
            self.model = True
        if tag == "a" and attrs.get("data-city-room"):
            room = attrs["data-city-room"]
            if attrs.get("href") == "#city/" + room:
                self.rooms.append(room)


def valid_city(html):
    parser = CityHTML()
    parser.feed(html.decode("utf-8"))
    return parser.model and not parser.invalid_room and len(parser.rooms) == 12 and set(parser.rooms) == ROOMS


def validate_repo(root):
    root = Path(root).resolve()
    required = (
        "dashboard/server.py", "dashboard/index.html", "engine/mm.py",
        "dashboard/vendor/three/three.module.min.js",
        "dashboard/vendor/three/addons/controls/OrbitControls.js",
    )
    missing = [name for name in required if not (root / name).is_file()]
    if missing or not (root / "state").is_dir():
        if not (root / "state").is_dir():
            missing.append("state/")
        raise CityError("Il pacchetto e' incompleto: manca " + ", ".join(missing)
                        + ".\nEstrai tutto lo ZIP, poi avvia APRI_CRYPTO_CITY.cmd nella cartella estratta.")
    for name in (*required, "state"):
        entry = root / name
        if entry.is_symlink() or any(parent.is_symlink() for parent in entry.parents if root in parent.parents):
            raise CityError("Un file del pacchetto e' un collegamento: " + name
                            + ". Estrai una copia completa nella sua cartella.")
    html = (root / "dashboard/index.html").read_bytes()
    if not valid_city(html):
        raise CityError("La pagina del pacchetto non contiene Crypto City e tutte le 12 sale."
                        "\nScarica ed estrai il pacchetto completo.")
    server = (root / "dashboard/server.py").read_text(encoding="utf-8")
    for route in ("/healthz", "/plancia", "/api/state", "/vendor/three/"):
        if route not in server:
            raise CityError("Il server del pacchetto non supporta " + route + ".")
    three = (root / "dashboard/vendor/three/three.module.min.js").read_text(encoding="utf-8")
    if not re.search(r'\bconst\s+\w+\s*=\s*[\"\']170[\"\']', three):
        raise CityError("La libreria 3D del pacchetto non e' la versione r170 verificata.")
    return root


def port_occupied(port):
    """Probe a local bind, avoiding Windows timeouts on a TCP connect."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            elif os.name != "nt":
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((HOST, port))
        return False
    except OSError as error:
        if error.errno == errno.EADDRINUSE or getattr(error, "winerror", None) == 10048:
            return True
        raise CityError("Impossibile verificare la porta locale " + str(port) + ": " + str(error)) from None


def choose_port(explicit=None):
    if explicit is not None:
        if isinstance(explicit, bool) or not isinstance(explicit, int) or not 1 <= explicit <= 65535:
            raise CityError("La porta deve essere un numero da 1 a 65535.")
        if port_occupied(explicit):
            raise CityError("La porta " + str(explicit) + " e' gia' occupata."
                            "\nAvvia senza --port per scegliere automaticamente una porta libera."
                            " Nessun processo esistente e' stato contattato o chiuso.")
        return explicit
    for port in range(DEFAULT_PORT, DEFAULT_PORT + PORT_ATTEMPTS):
        if not port_occupied(port):
            return port
    raise CityError("Le porte da " + str(DEFAULT_PORT) + " a " + str(DEFAULT_PORT + PORT_ATTEMPTS - 1)
                    + " sono occupate. Usa --port con una porta libera."
                    "\nNessun processo esistente e' stato contattato o chiuso.")


def server_environment(root, port):
    env = os.environ.copy()
    # This complete local checkout owns its state. An inherited hosted/GitHub
    # configuration must not redirect reads or send commands to another repo.
    for key in list(env):
        if key.startswith("MM_GITHUB_") or key in {"PORT", "MM_SITE_URL", "RAILWAY_PUBLIC_DOMAIN"}:
            env.pop(key, None)
    env.update(MM_HOST=HOST, MM_PORT=str(port), MM_STATE_DIR=str(Path(root).resolve() / "state"),
               MM_AUTOSTART="false", MM_LINKEDIN="false")
    return env


def http_get(base, path, limit=2_000_000):
    # Local requests must bypass inherited HTTP proxies. Reject redirects to
    # keep verification on this server, even with a malformed configuration.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    request = urllib.request.Request(base + path, headers={"Cache-Control": "no-cache"})
    try:
        with opener.open(request, timeout=1) as response:
            data = response.read(limit + 1)
            if len(data) > limit:
                raise CityError("Risposta locale troppo grande: " + path)
            return response.status, response.headers.get("Content-Type", ""), data
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("Content-Type", ""), b""


def verify_running_server(base, expected_html):
    status, _, data = http_get(base, "/healthz", limit=4096)
    try:
        healthy = json.loads(data).get("ok") is True
    except (ValueError, AttributeError):
        healthy = False
    if status != 200 or not healthy:
        raise CityError("Il server non risponde correttamente a /healthz.")
    status, content_type, data = http_get(base, "/plancia")
    if status != 200 or "text/html" not in content_type or not valid_city(data):
        raise CityError("Il server non fornisce Crypto City e tutte le 12 sale su /plancia.")
    if data != expected_html:
        raise CityError("La pagina ricevuta non corrisponde a quella di questa cartella.")
    status, _, data = http_get(base, "/api/state")
    if status == 401:
        return True
    try:
        state_ok = isinstance(json.loads(data).get("state"), dict)
    except (ValueError, AttributeError):
        state_ok = False
    if status != 200 or not state_ok:
        raise CityError("La pagina e' pronta, ma /api/state non fornisce i dati (HTTP " + str(status)
                        + "). Leggi l'errore nella finestra del server.")
    return False


def launch(root=None, port=None, open_browser=True, startup_timeout=25):
    root = validate_repo(ROOT if root is None else root)
    expected_html = (root / "dashboard/index.html").read_bytes()
    chosen = choose_port(port)
    base = "http://" + HOST + ":" + str(chosen)
    env = server_environment(root, chosen)
    flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
    process = subprocess.Popen([sys.executable, str(root / "dashboard/server.py")],
                               cwd=root, env=env, creationflags=flags)
    print("Avvio di questa copia di Crypto City sulla porta " + str(chosen) + ".", flush=True)
    deadline = time.monotonic() + startup_timeout
    last_error = "server non ancora pronto"
    auth_required = False
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise CityError("Il server si e' fermato (codice " + str(process.returncode)
                            + "). Leggi l'errore nella sua finestra.")
        try:
            auth_required = verify_running_server(base, expected_html)
            if process.poll() is not None:
                raise CityError("Il server di questa cartella si e' fermato. Leggi la sua finestra.")
            break
        except (CityError, urllib.error.URLError, UnicodeError, OSError) as error:
            last_error = str(error)
            time.sleep(.2)
    else:
        raise CityError("Il server non e' pronto: " + last_error
                        + "\nLa finestra del server resta aperta per leggere l'errore.")
    print("Pagina, 12 sale e API verificate. Lascia aperta la finestra del server.", flush=True)
    if auth_required:
        print("La plancia richiede il token gia' configurato. Inseriscilo solo nel browser, se richiesto.", flush=True)
    url = base + "/plancia#city"
    print("Apri nel browser: " + url, flush=True)
    if open_browser and not webbrowser.open(url, new=2):
        print("Il browser non si e' aperto automaticamente: copia l'indirizzo qui sopra.", flush=True)
    return process, base


def main(argv=None):
    if sys.version_info < (3, 10):
        print("Serve Python 3.10 o successivo; consigliato Python 3.12.", file=sys.stderr)
        return 1
    parser = argparse.ArgumentParser(description="Apri la Crypto City contenuta in questa cartella.")
    parser.add_argument("--port", type=int, help="Porta locale esplicita; deve essere libera")
    parser.add_argument("--no-browser", action="store_true", help="Verifica il server senza aprire il browser")
    args = parser.parse_args(argv)
    print("Crypto City: verifico questa cartella e avvio il suo server locale.", flush=True)
    try:
        launch(port=args.port, open_browser=not args.no_browser)
    except (CityError, OSError, UnicodeError) as error:
        print("ERRORE: " + str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Operazione interrotta. Le altre applicazioni restano aperte.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
