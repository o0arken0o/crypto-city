#!/usr/bin/env python3
"""Crypto Machine control panel — server (stdlib only).

Local:   python3 dashboard/server.py            -> http://127.0.0.1:8787
Hosted (Railway, Render…): binds 0.0.0.0:$PORT and REQUIRES MM_TOKEN.

Env:
  MM_PORT / PORT, MM_HOST        listen address (PORT set => 0.0.0.0)
  MM_TOKEN                       shared secret for the panel (mandatory when public)
  MM_STATE_DIR                   local state dir (default ./state)
  MM_CLAUDE                      claude CLI for the "run cycle" button (local only)
  MM_GITHUB_REPO, MM_GITHUB_TOKEN, MM_GITHUB_BRANCH (default main)
      GitHub mode: state is read live from the repo and every command becomes an
      issue "mm: …" applied by the `Crypto commands` workflow. Use a fine-grained
      token of the repo OWNER limited to this repo: Contents read, Issues read/write.

Traffic (no cookies, no JavaScript, no personal data): the server counts page views of /s/…, clicks on
/go/… links and the referring site, in memory. The workflows read the counts from /api/traffic with a
read-only key derived from MM_TOKEN, that the panel saves by itself as the GitHub secret MM_TRAFFIC_KEY.
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import shutil
import signal
import subprocess
import sys
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import mm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TOKEN = os.environ.get("MM_TOKEN", "")
CLAUDE = os.environ.get("MM_CLAUDE", "claude")
GH_REPO = os.environ.get("MM_GITHUB_REPO", "").strip()
GH_TOKEN = os.environ.get("MM_GITHUB_TOKEN", "").strip()
GH_BRANCH = os.environ.get("MM_GITHUB_BRANCH", "main")
GH_API = os.environ.get("MM_GITHUB_API", "https://api.github.com")
GH_MODE = bool(GH_REPO and GH_TOKEN)
GH_TTL = 15  # seconds between GitHub reads

_cycle_proc = None
_gh_cache = {"at": 0.0, "state": None, "error": None}
_gh_lock = threading.Lock()
_gh_sent = []  # commands sent this process, shown until the workflow applies them


# ---------------------------------------------------------------- GitHub mode

def gh_request(method, path, body=None, raw=False):
    req = urllib.request.Request(
        f"{GH_API}{path}", method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {GH_TOKEN}",
                 "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "crypto-machine-panel"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = r.read()
    return data if raw else json.loads(data or b"{}")


def gh_state():
    with _gh_lock:
        if time.time() - _gh_cache["at"] > GH_TTL or _gh_cache["state"] is None:
            try:
                data = gh_request("GET", f"/repos/{GH_REPO}/contents/state/state.json?ref={GH_BRANCH}", raw=True)
                _gh_cache.update(state=json.loads(data), error=None)
            except (urllib.error.URLError, ValueError) as e:
                _gh_cache["error"] = f"lettura GitHub fallita: {e}"
            _gh_cache["at"] = time.time()
        return _gh_cache["state"], _gh_cache["error"]


def gh_command(op, args):
    body = "```json\n" + json.dumps({"op": op, "args": args}, ensure_ascii=False) + "\n```\n\nInviato dalla plancia Crypto Machine."
    label = op + (" " + str(args.get("name") or args.get("id") or args.get("state") or "")).rstrip()
    issue = gh_request("POST", f"/repos/{GH_REPO}/issues", {"title": f"mm: {label}"[:120], "body": body})
    _gh_sent.append({"ts": mm.now(), "op": op, "issue": issue.get("number")})
    del _gh_sent[:-20]
    return f"inviato come issue #{issue.get('number')}: verrà applicato dal workflow entro ~1 minuto"


# ---------------------------------------------------------------- secrets (write-only)
# The owner pastes a token in the panel; it is verified, encrypted with the repository's public key
# (libsodium sealed box, as GitHub requires) and stored as a GitHub Actions secret. It is never written
# to the repo, to the state or to the logs, and never returned. The GitHub token of the panel needs the
# repository permission "Secrets: read and write".

SECRETS = {
    "POLAR_ACCESS_TOKEN": {"label": "Token Polar (non usato dalla versione crypto)", "check": "polar"},
    "OPENAI_API_KEY": {"label": "OpenAI", "check": None},
    "ANTHROPIC_API_KEY": {"label": "Anthropic", "check": None},
    "GROQ_API_KEY": {"label": "Groq", "check": None},
    "CEREBRAS_API_KEY": {"label": "Cerebras", "check": None},
    "GEMINI_API_KEY": {"label": "Google Gemini", "check": None},
    "OPENROUTER_API_KEY": {"label": "OpenRouter", "check": None},
    "TOGETHER_API_KEY": {"label": "Together AI", "check": None},
    "MISTRAL_API_KEY": {"label": "Mistral", "check": None},
    "DEEPSEEK_API_KEY": {"label": "DeepSeek", "check": None},
    "XAI_API_KEY": {"label": "xAI / Grok", "check": None},
    "TELEGRAM_BOT_TOKEN": {"label": "Bot Telegram", "check": "telegram"},
}
NOT_AI = ("POLAR_ACCESS_TOKEN", "TELEGRAM_BOT_TOKEN")
AI_SECRET_BASES = tuple(n for n in SECRETS if n not in NOT_AI)
AI_SECRET_RE = re.compile(r"^(?:" + "|".join(re.escape(n) for n in AI_SECRET_BASES) + r")_[1-9][0-9]?$")


def check_polar_token(value):
    """True if Polar accepts the token (read-only call)."""
    req = urllib.request.Request("https://api.polar.sh/v1/orders/?limit=1", headers={
        "Authorization": f"Bearer {value}", "Accept": "application/json", "User-Agent": "crypto-machine-panel"})
    try:
        with urllib.request.urlopen(req, timeout=15):
            return True, ""
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return False, "Polar ha rifiutato il token (scaduto, revocato o senza il permesso orders:read)"
        return False, f"Polar ha risposto {e.code}: riprova tra poco"
    except urllib.error.URLError as e:
        return False, f"Polar non raggiungibile: {e.reason}"



def telegram_api(token, method, params=None):
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}", data=urllib.parse.urlencode(params or {}).encode(),
                                 headers={"User-Agent": "crypto-machine-panel"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or b"{}")


def check_telegram_token(value):
    """True if Telegram knows the bot (getMe, read-only)."""
    try:
        me = telegram_api(value, "getMe").get("result") or {}
        return True, f"@{me.get('username', 'bot')}"
    except urllib.error.HTTPError as e:
        if e.code in (401, 404):
            return False, "Telegram non riconosce il token: ricopialo dal messaggio di BotFather"
        return False, f"Telegram ha risposto {e.code}: riprova tra poco"
    except urllib.error.URLError as e:
        return False, f"Telegram non raggiungibile: {e.reason}"


def connect_telegram_chat(token):
    """Find the private chat that sent /start to the bot, save it as TELEGRAM_CHAT_ID and send a test message."""
    try:
        ups = telegram_api(token, "getUpdates").get("result") or []
        chat = next((str(u["message"]["chat"]["id"]) for u in reversed(ups)
                     if (u.get("message") or {}).get("chat", {}).get("type") == "private"), "")
        if not chat:
            return "ma non trovo ancora la tua chat: apri il bot su Telegram, premi Avvia (/start) e poi salva di nuovo il token"
        put_secret("TELEGRAM_CHAT_ID", chat)
        telegram_api(token, "sendMessage", {"chat_id": chat, "text": "✅ Crypto Machine è collegata a questo bot. Da ora ti scrivo qui quando arriva una vendita, quando serve una tua decisione e quando un ciclo viene saltato o fallisce."})
        return "chat trovata: ti ho mandato un messaggio di prova su Telegram"
    except (urllib.error.URLError, ValueError, KeyError) as e:
        return f"token salvato, ma non sono riuscito a collegare la chat ({getattr(e, 'reason', e)}): ci riprova da solo al prossimo ciclo"


def check_ai_key(name, value):
    """Read-only connectivity check for an AI provider key. Never logs or returns the key."""
    base = name.rsplit("_", 1)[0] if re.search(r"_[1-9][0-9]? $".replace(" ", ""), name) else name
    urls = {
        "OPENAI_API_KEY": ("https://api.openai.com/v1/models", {"Authorization": "Bearer " + value}),
        "GROQ_API_KEY": ("https://api.groq.com/openai/v1/models", {"Authorization": "Bearer " + value}),
        "CEREBRAS_API_KEY": ("https://api.cerebras.ai/v1/models", {"Authorization": "Bearer " + value}),
        "OPENROUTER_API_KEY": ("https://openrouter.ai/api/v1/models", {"Authorization": "Bearer " + value}),
        "GEMINI_API_KEY": ("https://generativelanguage.googleapis.com/v1beta/openai/models", {"Authorization": "Bearer " + value}),
        "TOGETHER_API_KEY": ("https://api.together.xyz/v1/models", {"Authorization": "Bearer " + value}),
        "MISTRAL_API_KEY": ("https://api.mistral.ai/v1/models", {"Authorization": "Bearer " + value}),
        "DEEPSEEK_API_KEY": ("https://api.deepseek.com/v1/models", {"Authorization": "Bearer " + value}),
        "XAI_API_KEY": ("https://api.x.ai/v1/models", {"Authorization": "Bearer " + value}),
        "ANTHROPIC_API_KEY": ("https://api.anthropic.com/v1/models?limit=1", {"x-api-key": value, "anthropic-version": "2023-06-01"}),
    }
    target = urls.get(base)
    if not target: return False, "provider non supportato"
    url, headers = target
    req = urllib.request.Request(url, headers={**headers, "Accept": "application/json", "User-Agent": "crypto-machine-panel"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read() or b"{}")
        models = data.get("data") or data.get("models") or []
        return True, f"connessione OK · {len(models)} modelli visibili"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403): return False, "key rifiutata dal provider (controlla validità, permessi o progetto)"
        if e.code == 429: return False, "provider raggiungibile ma quota/rate limit esaurito"
        return False, f"provider ha risposto HTTP {e.code}"
    except urllib.error.URLError: return False, "provider non raggiungibile dal server"
    except (ValueError, TypeError): return False, "risposta del provider non valida"

def set_secret(name, value):
    if name not in SECRETS and not AI_SECRET_RE.fullmatch(name):
        return False, "segreto non previsto"
    value = (value or "").strip()
    if not value or len(value) > 500 or any(c.isspace() for c in value):
        return False, "valore vuoto o non valido"
    if not GH_MODE:
        return False, "disponibile solo con la plancia collegata a GitHub (MM_GITHUB_REPO e MM_GITHUB_TOKEN)"
    bot = ""
    if name == "POLAR_ACCESS_TOKEN" and SECRETS[name]["check"] == "polar":
        ok, why = check_polar_token(value)
        if not ok:
            return False, why
    elif name == "TELEGRAM_BOT_TOKEN":
        ok, bot = check_telegram_token(value)
        if not ok:
            return False, bot
    elif name != "POLAR_ACCESS_TOKEN":
        ok, why = check_ai_key(name, value)
        if not ok:
            return False, why
    try:
        put_secret(name, value)
    except ImportError:
        return False, "manca la libreria PyNaCl sul server (requirements.txt)"
    if name == "TELEGRAM_BOT_TOKEN":
        return True, f"bot {bot} verificato e salvato su GitHub, {connect_telegram_chat(value)}"
    label = (SECRETS.get(name) or SECRETS.get(re.sub(r"_[1-9][0-9]?$", "", name)) or {"label": name})["label"]  # GROQ_API_KEY_1 -> Groq
    return True, f"{label} verificato e salvato come secret {name} su GitHub"


def put_secret(name, value):
    """Encrypt (libsodium sealed box, as GitHub requires) and store an Actions secret. Never logged."""
    from nacl import encoding, public
    key = gh_request("GET", f"/repos/{GH_REPO}/actions/secrets/public-key")
    box = public.SealedBox(public.PublicKey(key["key"].encode(), encoding.Base64Encoder()))
    enc = base64.b64encode(box.encrypt(value.encode())).decode()
    gh_request("PUT", f"/repos/{GH_REPO}/actions/secrets/{name}", {"encrypted_value": enc, "key_id": key["key_id"]})


def secrets_status():
    """{name: updated_at|None} for the known secrets; None values if they cannot be read."""
    out = {n: None for n in (*SECRETS, "TELEGRAM_CHAT_ID", "LINKEDIN_ACCESS_TOKEN")}
    if not GH_MODE:
        return {"available": False, "secrets": out}
    try:
        items = gh_request("GET", f"/repos/{GH_REPO}/actions/secrets?per_page=100").get("secrets", [])
        for it in items:
            name = it.get("name")
            if name in out or AI_SECRET_RE.fullmatch(str(name or "")):
                out[name] = it.get("updated_at")
        return {"available": True, "secrets": out}
    except urllib.error.HTTPError as e:
        return {"available": True, "secrets": out, "error": f"GitHub {e.code}: al token della plancia manca il permesso Secrets"}
    except urllib.error.URLError as e:
        return {"available": True, "secrets": out, "error": f"GitHub non raggiungibile: {e.reason}"}


# ---------------------------------------------------------------- LinkedIn: the owner connects their own profile
# The owner pastes Client ID and Client Secret of their LinkedIn app in the panel; they are kept only in memory for the
# few minutes of the login. LinkedIn sends the owner back to /linkedin/callback with a one-time code: the server swaps it
# for an access token (60 days) and saves token and profile id as GitHub secrets, used only by scripts/linkedin.py
# when the owner approves a post. Nothing is published here.
LI_SCOPES = "openid profile w_member_social"
_li_pending = {}


def linkedin_redirect(host=""):
    return public_base(host) + "/linkedin/callback"


def linkedin_start(client_id, client_secret, host=""):
    client_id, client_secret = (client_id or "").strip(), (client_secret or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{8,40}", client_id) or not re.fullmatch(r"[\x21-\x7e]{8,200}", client_secret):
        return False, "Client ID o Client Secret non validi: copiali dalla scheda Auth dell'app LinkedIn"
    if not GH_MODE:
        return False, "disponibile solo con la plancia online collegata a GitHub"
    now = time.time()
    for k in [k for k, v in _li_pending.items() if now - v["ts"] > 900]:
        del _li_pending[k]
    state = base64.urlsafe_b64encode(os.urandom(24)).decode().rstrip("=")
    redirect = linkedin_redirect(host)
    _li_pending[state] = {"id": client_id, "secret": client_secret, "redirect": redirect, "ts": now}
    return True, "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode(
        {"response_type": "code", "client_id": client_id, "redirect_uri": redirect, "state": state, "scope": LI_SCOPES})


def linkedin_finish(state, code, opener=None):
    """Swap the one-time code for the access token and save it. Returns (ok, message)."""
    op = opener or urllib.request.urlopen
    p = _li_pending.pop(state or "", None)
    if not p or time.time() - p["ts"] > 900:
        return False, "Il collegamento è scaduto o è già stato usato: riprova da Collega LinkedIn in plancia."
    data = urllib.parse.urlencode({"grant_type": "authorization_code", "code": code, "client_id": p["id"],
                                   "client_secret": p["secret"], "redirect_uri": p["redirect"]}).encode()
    try:
        with op(urllib.request.Request("https://www.linkedin.com/oauth/v2/accessToken", data=data,
                                       headers={"Content-Type": "application/x-www-form-urlencoded"}), timeout=20) as r:
            tok = json.loads(r.read() or b"{}")
        access = str(tok.get("access_token") or "")
        with op(urllib.request.Request("https://api.linkedin.com/v2/userinfo", headers={"Authorization": f"Bearer {access}"}), timeout=20) as r:
            me = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return False, f"LinkedIn ha rifiutato il collegamento (HTTP {e.code}): controlla Client Secret e l'indirizzo di ritorno dell'app."
    except (urllib.error.URLError, ValueError) as e:
        return False, f"LinkedIn non raggiungibile: {e}"
    if not access or not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", str(me.get("sub") or "")):
        return False, "LinkedIn non ha dato l'accesso: hai aggiunto all'app i prodotti Share on LinkedIn e Sign In with LinkedIn?"
    try:
        put_secret("LINKEDIN_ACCESS_TOKEN", access)
        put_secret("LINKEDIN_PERSON_URN", "urn:li:person:" + me["sub"])
    except ImportError:
        return False, "manca la libreria PyNaCl sul server"
    except urllib.error.HTTPError as e:
        return False, f"GitHub ha risposto {e.code}: al token della plancia manca il permesso Secrets"
    days = int(tok.get("expires_in") or 0) // 86400
    if days and GH_MODE:  # the engine reminds the owner a week before it expires
        try:
            gh_command("linkedin", {"expires": (datetime.date.today() + datetime.timedelta(days=days)).isoformat()})
        except Exception:  # noqa: BLE001 - the connection itself worked
            pass
    return True, f"LinkedIn collegato come {me.get('name') or 'te'}" + (f": vale {days} giorni, poi va ricollegato." if days else ".")


# ---------------------------------------------------------------- public site (/s/)
# Pagine pubbliche (track record, guide) approvate dal proprietario. Si serve SOLO site/<slug>/public/ e SOLO se
# esiste site/<slug>/.approved, scritto da scripts/actions.py dopo l'approvazione del proprietario.
# Niente token: sono pagine pubbliche. Niente JavaScript (CSP script-src 'none').

SITE_TTL = 120
SITE_URL = os.environ.get("MM_SITE_URL", "").rstrip("/")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,60}$")
SAFE_PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
OPP_ID = re.compile(r"^opp_[a-z0-9]{3,20}$")
CTYPES = {".html": "text/html", ".css": "text/css", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
          ".webp": "image/webp", ".svg": "image/svg+xml", ".ico": "image/x-icon", ".txt": "text/plain",
          ".xml": "application/xml", ".pdf": "application/pdf"}
_site_cache = {}


def _site_read(rel):
    """Bytes of repo file site/<rel> or None; cached, from disk or GitHub."""
    now_t = time.time()
    hit = _site_cache.get(rel)
    if hit and now_t - hit[0] < SITE_TTL:
        return hit[1]
    data = None
    if GH_MODE:
        try:
            data = gh_request("GET", f"/repos/{GH_REPO}/contents/site/{urllib.parse.quote(rel)}?ref={GH_BRANCH}", raw=True)
        except urllib.error.HTTPError as e:
            if e.code != 404 and hit:
                return hit[1]
        except urllib.error.URLError:
            if hit:
                return hit[1]
    else:
        p = os.path.join(ROOT, "site", *rel.split("/"))
        if os.path.isfile(p):
            with open(p, "rb") as f:
                data = f.read()
    _site_cache[rel] = (now_t, data)
    if len(_site_cache) > 500:
        _site_cache.clear()
    return data


def site_slugs():
    """Approved page slugs."""
    hit = _site_cache.get("__slugs__")
    if hit and time.time() - hit[0] < SITE_TTL:
        return hit[1]
    if GH_MODE:
        try:
            items = gh_request("GET", f"/repos/{GH_REPO}/contents/site?ref={GH_BRANCH}")
            names = [i["name"] for i in items if i.get("type") == "dir"]
        except (urllib.error.URLError, ValueError, TypeError):
            names = hit[1] if hit else []
    else:
        d = os.path.join(ROOT, "site")
        names = sorted(os.listdir(d)) if os.path.isdir(d) else []
    slugs = [n for n in names if SLUG_RE.match(n) and _site_read(f"{n}/.approved") is not None]
    _site_cache["__slugs__"] = (time.time(), slugs)
    return slugs


def site_file(path):
    """(bytes, ctype) for a public URL path below /s/, or None."""
    parts = [p for p in path.split("/") if p]
    if not parts or not SLUG_RE.match(parts[0]) or not all(SAFE_PART.match(p) for p in parts[1:]):
        return None
    if _site_read(f"{parts[0]}/.approved") is None:
        return None
    rest = parts[1:] or ["index.html"]
    ext = os.path.splitext(rest[-1])[1].lower() or ".html"
    if not os.path.splitext(rest[-1])[1]:
        rest = rest + ["index.html"]
    data = _site_read("/".join([parts[0], "public", *rest]))
    return (data, CTYPES.get(ext, "application/octet-stream")) if data is not None and ext in CTYPES else None


def _title(slug):
    html = (_site_read(f"{slug}/public/index.html") or b"").decode("utf-8", "replace")
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    return (m.group(1).strip() if m else slug)[:120]


SITE_CSS = ("*{box-sizing:border-box}body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;"
            "line-height:1.6;color:#1f2933;background:#f7f8fa}.wrap{max-width:760px;margin:0 auto;padding:24px 18px 48px}"
            "h1{font-size:1.9rem;line-height:1.25;margin:6px 0 8px}h2{font-size:1.25rem;margin:30px 0 10px;color:#1a4d8f}"
            ".lead{font-size:1.08rem;color:#3e4c59;margin:0 0 8px}.card{display:flex;gap:14px;align-items:center;background:#fff;"
            "border:1px solid #d9dee5;border-radius:14px;padding:14px;margin:10px 0;text-decoration:none;color:inherit}"
            ".card:hover{border-color:#1a73e8}.card img{width:74px;height:100px;object-fit:cover;border-radius:6px;border:1px solid #e3e6ee;flex:none}"
            ".card b{display:block;font-size:1.05rem;color:#111827}.card span{display:block;font-size:.93rem;color:#52606d}"
            ".price{display:inline-block;margin-top:6px;font-weight:700;color:#1a73e8}.free{color:#16a34a}"
            "footer{margin-top:36px;font-size:.85rem;color:#7b8794}")


def _desc(slug):
    return _meta((_site_read(f"{slug}/public/index.html") or b"").decode("utf-8", "replace"), "description")


def _short(text, n=160):
    """Cut at a word boundary, with an ellipsis."""
    text = str(text or "").strip()
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0].rstrip(",.;:") + "…"


OWNER_JS = 'try{if(localStorage.getItem("mm-token"))location.replace("/plancia")}catch(e){}'
OWNER_JS_HASH = "sha256-" + base64.b64encode(hashlib.sha256(OWNER_JS.encode()).digest()).decode()  # the only script allowed on the site


def brand():
    """Shop brand from site/_brand/brand.json (+ logo.svg): {"name": ["Solleciti", "Facili"], "color": "#1a73e8", "tagline": "..."}."""
    try:
        b = json.loads(_site_read("_brand/brand.json") or b"{}")
    except ValueError:
        b = {}
    if not b.get("name"):
        return None
    name = b["name"] if isinstance(b["name"], list) else [str(b["name"]), ""]
    color = b.get("color") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(b.get("color") or "")) else "#1a73e8"
    return {"a": str(name[0])[:30], "b": str(name[1] if len(name) > 1 else "")[:30], "color": color,
            "light": b.get("color_light") if re.fullmatch(r"#[0-9a-fA-F]{6}", str(b.get("color_light") or "")) else color,
            "tagline": str(b.get("tagline") or "")[:200], "logo": _site_read("_brand/logo.svg") is not None,
            "featured": str(b.get("featured") or "")[:30]}


def brand_bar(br):
    """Small header with logo and shop name, linking to the home of the site."""
    if not br:
        return ""
    logo = '<img src="/brand/logo.svg" alt="" width="34" height="34" style="display:block">' if br["logo"] else ""
    return ('<header data-mm-brand style="background:#fff;border-bottom:1px solid #e3e6ee"><a href="/" style="max-width:760px;margin:0 auto;'
            'padding:10px 18px;display:flex;align-items:center;gap:10px;text-decoration:none;font:800 20px/1 system-ui,sans-serif;'
            f'letter-spacing:-.01em;color:#0f172a">{logo}<span>{_attr(br["a"])}<span style="color:{br["color"]}">{_attr(br["b"])}</span></span></a></header>')


HOME_CSS = (".aud{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 4px}.aud a{background:#fff;border:1px solid #d9dee5;border-radius:99px;"
            "padding:8px 14px;font-weight:700;text-decoration:none;color:var(--c)}.aud~.prods{margin-top:0}.aud~h2{margin-top:28px}"
            ".hero{background:linear-gradient(160deg,#0f172a,#1e293b);color:#fff;padding:34px 18px 40px}"
            ".hero .in{max-width:760px;margin:0 auto}.hero h1{font-size:2.1rem;line-height:1.15;margin:14px 0 10px;color:#fff}"
            ".hero p{color:#cbd5e1;font-size:1.08rem;margin:0 0 18px}.hero .go{display:inline-block;background:var(--c);color:#fff;"
            "font-weight:800;text-decoration:none;padding:13px 20px;border-radius:12px}"
            ".brand{display:flex;align-items:center;gap:12px;font:800 26px/1 system-ui,sans-serif;letter-spacing:-.01em}"
            ".prods{display:grid;grid-template-columns:1fr;gap:14px;margin-top:-22px}@media(min-width:640px){.prods{grid-template-columns:1fr 1fr}}"
            ".prod{display:block;background:#fff;border:1px solid #d9dee5;border-radius:16px;overflow:hidden;text-decoration:none;color:inherit;"
            "box-shadow:0 8px 24px rgba(15,23,42,.10)}.prod img{display:block;width:100%;aspect-ratio:4/5;object-fit:cover;background:#0f172a}"
            ".prod div{padding:12px 14px}.prod b{display:block;font-size:1.02rem;color:#111827;line-height:1.3}"
            ".prod .price{font-style:normal;display:inline-block;margin-top:6px;font-weight:800;color:var(--c)}.prod .free{color:#16a34a}")


def site_index(base="", home=False):
    """/ and /s/: hero with the brand, the products on sale as big cards (real covers and prices), then the guides."""
    e = lambda t: _attr(str(t or ""))
    br = brand()
    guides, prods = [], []
    for sl in site_slugs():
        if sl in INFO_PAGES:
            continue
        info = product_info(sl) if re.match(r"^opp_[a-z0-9]{3,20}$", sl) else None
        (prods if info else guides).append((sl, info))
    featured = (br or {}).get("featured") or ""
    prods.sort(key=lambda p: (p[0] != featured, -float((p[1] or {}).get("price") or 0)))  # the featured product, then by price
    def price(info):
        amount = float(info.get("price") or 0)
        label = ("%.2f €" % amount).replace(".", ",") if amount else "Gratis"
        if amount and info.get("min"):  # pay what you want
            label = "Paga quanto vuoi, da " + ("%.0f €" % float(info["min"]))
        return '<em class="price' + ("" if amount else " free") + '">' + label + "</em>"
    def guide(sl):
        return (f'<a class="card" href="/s/{e(sl)}/"><div><b>{e(_title(sl))}</b>'
                f'<span>{e(_short(_desc(sl)))}</span></div></a>')
    def prod(sl, info):
        img = '<img src="/' + e(info.get("image")) + '" alt="" loading="lazy">' if info.get("image") else ""
        return f'<a class="prod" href="/s/{e(sl)}/">{img}<div><b>{e(info.get("name") or _title(sl))}</b>{price(info)}</div></a>'
    color = br["color"] if br else "#1a73e8"
    logo_img = '<img src="/brand/logo.svg" alt="" width="44" height="44">' if br and br["logo"] else ""
    name = (f'<div class="brand">{logo_img}'
            f'<span>{e(br["a"])}<span style="color:{br["light"]}">{e(br["b"])}</span></span></div>') if br else ""
    hero = (f'<section class="hero"><div class="in">{name}'
            '<h1>Strategie crypto testate in pubblico, con numeri veri.</h1>'
            f'<p>{e(br["tagline"]) if br and br["tagline"] else "Backtest e paper trading con prezzi reali, senza promesse di guadagno. Non è un consiglio finanziario."}</p>'
            + ('<a class="go" href="#modelli">Vedi i risultati</a>' if prods else "") + "</div></section>")
    body = ""
    groups = [(k, [p for p in prods if p[1].get("audience") == k]) for k in AUDIENCES]
    groups = [g for g in groups if g[1]]
    if len(groups) > 1:  # one section per kind of customer, so each finds their own models at once
        body += '<nav class="aud" id="modelli">' + "".join(f'<a href="#per-{k}">{e(AUDIENCES[k])}</a>' for k, _ in groups) + "</nav>"
        for k, ps in groups:
            body += f'<h2 id="per-{k}">{e(AUDIENCES[k])}</h2><div class="prods">' + "".join(prod(*p) for p in ps) + "</div>"
    elif prods:
        body += '<div class="prods" id="modelli">' + "".join(prod(*p) for p in prods) + "</div>"
    if guides:
        body += "<h2>Guide gratuite</h2>" + "".join(guide(g[0]) for g in guides)
    body = body or "<p>In arrivo.</p>"
    title = (f"{br['a']}{br['b']}: " if br else "") + "strategie crypto con numeri veri"
    canon = f'<link rel="canonical" href="{e(base)}/s/">' if base else ""
    if home:
        _, gmeta = google_verify()
        if gmeta:  # Google Search Console, "HTML tag" method
            canon += f'<meta name="google-site-verification" content="{e(gmeta)}">'
        # the owner (panel password saved in this browser) goes straight to the panel; visitors and search engines see the site
        canon += f"<script>{OWNER_JS}</script>"
    icon = '<link rel="icon" href="/brand/logo.svg" type="image/svg+xml">' if br and br["logo"] else ""
    share = share_image("_none_", base)
    if share:  # preview when the home is shared on Facebook, LinkedIn, WhatsApp
        canon += (f'<meta property="og:type" content="website"><meta property="og:title" content="{e(title)}">'
                  f'<meta property="og:url" content="{e(base)}/"><meta property="og:image" content="{e(share)}">'
                  '<meta name="twitter:card" content="summary_large_image">')
    return ('<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{e(title)}</title>{icon}'
            '<meta name="description" content="Strategie crypto testate in pubblico: backtest e paper trading con prezzi reali, senza promesse di guadagno. Non è un consiglio finanziario.">'
            f'{canon}<style>:root{{--c:{color}}}{SITE_CSS}{HOME_CSS}</style></head><body>' + hero + '<div class="wrap">'
            + body + "<footer>Contenuti creati con l'aiuto dell'AI e controllati prima della pubblicazione. Risultati passati o simulati non garantiscono quelli futuri. Non è un consiglio finanziario."
            + (' · <a href="/s/contatti/">Contatti e privacy</a>' if "contatti" in site_slugs() else "") + "</footer>"
            "</div></body></html>").encode()


def site_sitemap(base):
    urls = [(f"{base}/s/", "")] + [(f"{base}/s/{s}/", _published(s)[:10]) for s in site_slugs()]
    body = "".join(f"<url><loc>{u}</loc>" + (f"<lastmod>{d}</lastmod>" if d else "") + "</url>" for u, d in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + body + "</urlset>").encode()


# ---------------------------------------------------------------- traffic (/go/ + page views)

BOT_UA = re.compile(r"bot|crawl|spider|slurp|preview|monitor|curl|wget|python|headless|facebookexternalhit|lighthouse", re.I)
GO_ALLOWED = ("https://buy.polar.sh/", "https://polar.sh/")
_traffic_lock = threading.Lock()
TRAFFIC = {"boot": datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d%H%M%S") + "-" + os.urandom(3).hex(),
           "started": mm.now(), "counts": {}}


def traffic_key():
    """Read-only key for /api/traffic, derived from the panel password (never the password itself)."""
    return hmac.new(TOKEN.encode(), b"mm-traffic-v1", "sha256").hexdigest()[:40] if TOKEN else ""


def count(page, kind, referer="", host="", ua="", product=None):
    """kind: "v" page view or "c" click. Bots and requests without a browser user agent are ignored."""
    if not ua or BOT_UA.search(ua):
        return
    ref = (urllib.parse.urlparse(referer).hostname or "") if referer else ""
    day = datetime.date.today().isoformat()
    with _traffic_lock:
        c = TRAFFIC["counts"].setdefault(f"{day}|{page}", {"v": 0, "c": 0, "r": {}, "p": {}})
        c[kind] += 1
        if ref and ref != (host or "").split(":")[0]:
            c["r"][ref] = c["r"].get(ref, 0) + 1
            if len(c["r"]) > 30:
                c["r"].pop(min(c["r"], key=c["r"].get))
        if product:
            c["p"][product] = c["p"].get(product, 0) + 1
        if len(TRAFFIC["counts"]) > 3000:  # ~60 days × 50 pages; the oldest go first
            for k in sorted(TRAFFIC["counts"])[:500]:
                del TRAFFIC["counts"][k]


def go_target(parts):
    """Checkout or affiliate URL for /go/<opp_id> or /go/<slug>/<name>; None if not allowed."""
    if len(parts) == 1 and re.match(r"^opp_[a-z0-9]{3,20}$", parts[0]):
        try:
            url = json.loads(_repo_read(f"products/{parts[0]}/polar.json") or b"{}").get("checkout_url") or ""
        except ValueError:
            return None
        return url if url.startswith(GO_ALLOWED) else None
    if len(parts) == 2 and SLUG_RE.match(parts[0]) and SAFE_PART.match(parts[1]) and _site_read(f"{parts[0]}/.approved") is not None:
        try:  # affiliate links of an APPROVED page only: site/<slug>/links.json {"name": "https://..."}
            url = json.loads(_site_read(f"{parts[0]}/links.json") or b"{}").get(parts[1]) or ""
        except ValueError:
            return None
        return url if url.startswith("https://") else None
    return None


def traffic_snapshot(limit=60000):
    """Copy of the counts with something in them, small enough for a GitHub issue (the oldest days go first)."""
    with _traffic_lock:
        snap = {"boot": TRAFFIC["boot"], "started": TRAFFIC["started"],
                "counts": {k: v for k, v in TRAFFIC["counts"].items() if v.get("v") or v.get("c")}}
    keys = sorted(snap["counts"])
    while keys and len(json.dumps(snap, ensure_ascii=False)) > limit:
        for k in keys[:max(1, len(keys) // 10)]:
            del snap["counts"][k]
        keys = sorted(snap["counts"])
    return snap


def flush_traffic():
    """Railway stops the panel (SIGTERM) at every deploy, and the counts live in memory: what the workflows
    have not read yet is sent as a command issue ("mm: traffic"), applied like the other commands."""
    snap = traffic_snapshot()
    if not (GH_MODE and snap["counts"]):
        return ""
    try:
        return gh_command("traffic", snap)
    except Exception as e:  # noqa: BLE001 - never block the shutdown
        return f"non salvati ({type(e).__name__})"


def publish_traffic_key():
    """Save MM_TRAFFIC_KEY (and where to read it) as GitHub secrets, so the workflows can sync the counts.
    Runs once at start; silently does nothing without GitHub mode, PyNaCl or the Secrets permission."""
    base = SITE_URL or (f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}" if os.environ.get("RAILWAY_PUBLIC_DOMAIN") else "")
    if not (GH_MODE and TOKEN and base):
        return
    try:
        put_secret("MM_TRAFFIC_KEY", traffic_key())
        put_secret("MM_TRAFFIC_URL", base)
        print("traffico: chiave di lettura salvata nei secret GitHub", flush=True)
    except Exception as e:  # noqa: BLE001 - optional feature
        print(f"traffico: secret non salvati ({type(e).__name__})", flush=True)


# ---------------------------------------------------------------- findability (all automatic)
# 1. IndexNow: every new or changed approved page is sent to Bing, Yandex, Seznam, Naver, Yep, Internet Archive
#    and Amazon (Bing also feeds ChatGPT search, Copilot and DuckDuckGo). Key file served at /<key>.txt.
# 2. Each approved page gets, at serve time, what search engines and link previews read: canonical, Open Graph,
#    schema.org JSON-LD (Product with its real price, or Article) and links to the other pages. Plus an Atom feed
#    and /llms.txt for AI assistants. Nothing is invented: data come from store.json / polar.json / the page.

INDEXNOW_API = "https://api.indexnow.org/indexnow"
_indexnow = {"sent": {}, "last": None, "error": None}


def indexnow_key():
    return hmac.new(TOKEN.encode(), b"mm-indexnow-v1", "sha256").hexdigest()[:32] if TOKEN else ""


def old_host_redirect(host, path):
    """With MM_SITE_URL set to the shop's own domain, a GET on the old *.up.railway.app address → same path there."""
    h = (host or "").split(":")[0].lower()
    if not SITE_URL or not h.endswith(".up.railway.app") or urllib.parse.urlparse(SITE_URL).hostname == h:
        return ""
    return SITE_URL + (path if path.startswith("/") else "/" + path)


def public_base(host=""):
    if SITE_URL:
        return SITE_URL
    if os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
        return f"https://{os.environ['RAILWAY_PUBLIC_DOMAIN']}"
    return f"https://{host}" if host else ""


def indexnow_submit(base, opener=None):
    """Send new/changed approved pages to IndexNow. Returns the URLs sent."""
    key = indexnow_key()
    host = urllib.parse.urlparse(base).hostname or ""
    if not key or not host or host in ("localhost", "127.0.0.1"):
        return []
    todo = {}
    for slug in site_slugs():
        body = _site_read(f"{slug}/public/index.html") or b""
        todo[f"{base}/s/{slug}/"] = hashlib.sha256(body).hexdigest()
    if todo:
        todo[f"{base}/s/"] = hashlib.sha256("".join(sorted(todo)).encode()).hexdigest()
    urls = [u for u, h in todo.items() if _indexnow["sent"].get(u) != h]
    if not urls:
        return []
    req = urllib.request.Request(INDEXNOW_API, method="POST", data=json.dumps(
        {"host": host, "key": key, "keyLocation": f"{base}/{key}.txt", "urlList": urls}).encode(),
        headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": "crypto-machine-panel"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=20) as r:
            ok = r.status in (200, 202)
    except urllib.error.HTTPError as e:
        ok, _indexnow["error"] = False, f"IndexNow {e.code}"
    except urllib.error.URLError as e:
        ok, _indexnow["error"] = False, f"IndexNow non raggiungibile: {e.reason}"
    if ok:
        _indexnow["sent"].update({u: todo[u] for u in urls})
        _indexnow["last"], _indexnow["error"] = mm.now(), None
        print(f"IndexNow: {len(urls)} pagine inviate ai motori di ricerca", flush=True)
        return urls
    return []


def indexnow_loop():
    time.sleep(60)  # let the first deploy settle (the key file must be reachable)
    while True:
        base = public_base()
        if base:
            try:
                indexnow_submit(base)
            except Exception as e:  # noqa: BLE001 - never kill the panel
                _indexnow["error"] = f"{type(e).__name__}"
        time.sleep(1800)


def _meta(html, name):
    m = re.search(r'<meta[^>]+(?:name|property)=["\']%s["\'][^>]*content=["\']([^"\']*)' % re.escape(name), html, re.I) or \
        re.search(r'<meta[^>]+content=["\']([^"\']*)["\'][^>]*(?:name|property)=["\']%s["\']' % re.escape(name), html, re.I)
    return m.group(1) if m else ""


def _attr(v):
    return str(v).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def product_info(slug):
    """Public data of a product that is on sale on Polar (else None): name, price, first preview image."""
    try:
        pol = json.loads(_repo_read(f"products/{slug}/polar.json") or b"{}")
        store = json.loads(_repo_read(f"products/{slug}/store.json") or b"{}")
    except ValueError:
        return None
    if not str(pol.get("checkout_url") or "").startswith(GO_ALLOWED):
        return None
    media = sorted(n for n in _repo_list(f"products/{slug}/media") if os.path.splitext(n)[1].lower() in MEDIA_CT)
    mn = store.get("min_eur") if isinstance(store.get("min_eur"), (int, float)) and store.get("min_eur") > 0 else None
    aud = store.get("audience") if store.get("audience") in AUDIENCES else (
        "ecommerce" if re.search(r"e-?commerce|shopify|negozi", str(store.get("name") or ""), re.I) else "freelance")
    return {"name": store.get("name") or "", "price": store.get("price_eur") or pol.get("price_eur"), "min": mn,
            "image": f"m/{slug}/{media[0]}" if media else "", "audience": aud}


# who a product is for (store.json "audience"; without it, guessed from the name): the home shows one section each
AUDIENCES = {"freelance": "Per freelance e partite IVA", "ecommerce": "Per negozi online"}


INFO_PAGES = ("contatti",)  # site pages that are not guides: kept out of the lists of guides and related links


def share_image(slug, base):
    """Preview image for shared links: the page's own share.png (scripts/share_card.py), else the site's one."""
    if _site_read(f"{slug}/public/share.png") is not None:
        return f"{base}/s/{slug}/share.png"
    return f"{base}/brand/share.png" if _site_read("_brand/share.png") is not None else ""


def enrich(slug, data, base):
    """Add canonical, Open Graph, JSON-LD and related links to an approved page (only what is missing)."""
    html = data.decode("utf-8", "replace")
    url = f"{base}/s/{slug}/"
    title = (re.search(r"<title>(.*?)</title>", html, re.S | re.I) or [None, ""])[1].strip()
    desc = _meta(html, "description")
    prod = product_info(slug)
    head = []
    if 'rel="canonical"' not in html:
        head.append(f'<link rel="canonical" href="{_attr(url)}">')
    if 'property="og:' not in html:
        head += [f'<meta property="og:{k}" content="{_attr(v)}">' for k, v in
                 (("type", "product" if prod else "article"), ("title", title), ("description", desc), ("url", url),
                  ("image", f"{base}/{prod['image']}" if prod and prod["image"] else share_image(slug, base))) if v]
        head.append('<meta name="twitter:card" content="summary_large_image">')
    if "application/ld+json" not in html:
        if prod and prod["price"]:
            ld = {"@context": "https://schema.org", "@type": "Product", "name": prod["name"] or title, "description": desc,
                  "url": url, "offers": {"@type": "Offer", "price": f"{float(prod.get('min') or prod['price']):.2f}", "priceCurrency": "EUR",
                                         "availability": "https://schema.org/InStock", "url": f"{base}/go/{slug}"}}
            if prod["image"]:
                ld["image"] = f"{base}/{prod['image']}"
        else:
            ld = {"@context": "https://schema.org", "@type": "Article", "headline": title, "description": desc,
                  "url": url, "inLanguage": "it"}
        head.append('<script type="application/ld+json">' + json.dumps(ld, ensure_ascii=False).replace("</", "<\\/") + "</script>")
    rest = [s for s in site_slugs() if s != slug and s not in INFO_PAGES]
    is_prod = lambda s: bool(re.match(r"^opp_[a-z0-9]{3,20}$", s) and product_info(s))
    others = ([s for s in rest if not is_prod(s)] + [s for s in rest if is_prod(s)])[:5]  # guides first, then the products
    body = ""
    if others and "data-mm-related" not in html:
        items = "".join(f'<li style="margin:6px 0"><a href="/s/{s}/" style="color:#1a4d8f">{_attr(_title(s))}</a>'
                        + (" · modello pronto" if is_prod(s) else "") + "</li>" for s in others)
        body = (f'<nav data-mm-related style="max-width:720px;margin:2rem auto;padding:16px 18px;font:15px/1.6 system-ui,sans-serif;'
                f'background:#fff;border:1px solid #d9dee5;border-radius:12px">'
                f'<h2 style="font-size:1.05rem;margin:0 0 6px">Leggi anche</h2><ul style="margin:0;padding-left:18px">{items}</ul>'
                f'<p style="margin:10px 0 0"><a href="/s/" style="color:#1a73e8;font-weight:700">Tutte le guide e i modelli →</a></p></nav>')
    if head:
        i = html.lower().find("</head>")
        html = html[:i] + "\n".join(head) + html[i:] if i >= 0 else "\n".join(head) + html
    bar = brand_bar(brand()) if "data-mm-brand" not in html else ""
    if bar:
        m = re.search(r"<body[^>]*>", html, re.I)
        html = html[:m.end()] + bar + html[m.end():] if m else bar + html
    if body:
        i = html.lower().rfind("</body>")
        html = html[:i] + body + html[i:] if i >= 0 else html + body
    return html.encode("utf-8")


def _published(slug):
    try:
        return json.loads(_site_read(f"{slug}/.approved") or b"{}").get("published") or ""
    except ValueError:
        return ""


def site_feed(base):
    esc = _attr
    entries = "".join(
        f"<entry><title>{esc(_title(s))}</title><link href=\"{base}/s/{s}/\"/><id>{base}/s/{s}/</id>"
        f"<updated>{esc(_published(s) or mm.now())}</updated><summary>{esc(_meta((_site_read(f'{s}/public/index.html') or b'').decode('utf-8', 'replace'), 'description'))}</summary></entry>"
        for s in site_slugs())
    return ('<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom">'
            f'<title>Guide e strumenti</title><link href="{base}/s/"/><id>{base}/s/</id><updated>{mm.now()}</updated>'
            + entries + "</feed>").encode()


def site_llms(base):
    lines = ["# Guide e strumenti", "", "> Guide pratiche e strumenti digitali (file Excel, PDF) in italiano.", ""]
    for s in site_slugs():
        d = _meta((_site_read(f"{s}/public/index.html") or b"").decode("utf-8", "replace"), "description")
        lines.append(f"- [{_title(s)}]({base}/s/{s}/)" + (f": {d}" if d else ""))
    return ("\n".join(lines) + "\n").encode()


MEDIA_CT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


GOOGLE_FILE = re.compile(r"^google[0-9a-f]{6,40}\.html$")
GOOGLE_META = re.compile(r"^[A-Za-z0-9_-]{20,100}$")


def google_verify():
    """MM_GOOGLE_VERIFY (Railway variable) proves to Google Search Console that the site is yours:
    the name of the file Google gives you ("google1a2b3c….html", served at /<name>) or the content of its
    meta tag (added to the home page). Returns (file name or "", meta content or "")."""
    v = os.environ.get("MM_GOOGLE_VERIFY", "").strip()
    m = re.search(r'content="([^"]+)"', v)  # the whole <meta …> tag pasted: keep only the code
    v = m.group(1) if m else v
    if GOOGLE_FILE.match(v) or GOOGLE_FILE.match(v + ".html"):
        return (v if v.endswith(".html") else v + ".html"), ""
    return "", (v if GOOGLE_META.match(v) else "")


def strategy_visible(oid: str) -> bool:
    """A strategy whose charts may be shown: it is in paper trading or live (paper.json / live.json exist)."""
    return bool(re.match(r"^opp_[a-z0-9]{3,20}$", oid or "")) and (
        _repo_read(f"products/{oid}/paper.json") is not None or _repo_read(f"products/{oid}/live.json") is not None)


def strategy_perf(oid) -> str:
    """One line of real numbers for a strategy: backtest verdict and paper trading vs buy & hold."""
    if not re.match(r"^opp_[a-z0-9]{3,20}$", str(oid or "")):
        return ""
    def js(name):
        try:
            return json.loads(_repo_read(f"products/{oid}/{name}") or b"{}")
        except ValueError:
            return {}
    return mm.perf_line({"backtest": js("backtest.json"), "paper": js("paper.json")})


def media_file(parts):
    """/m/<opp_id>/<image>: charts of strategies in paper trading or live (real results only)."""
    if len(parts) != 2 or not re.match(r"^opp_[a-z0-9]{3,20}$", parts[0]) or not SAFE_PART.match(parts[1]):
        return None
    ct = MEDIA_CT.get(os.path.splitext(parts[1])[1].lower())
    if not ct or not (product_info(parts[0]) or strategy_visible(parts[0])):
        return None
    data = _repo_read(f"products/{parts[0]}/media/{parts[1]}")
    return (data, ct) if data else None


# ---------------------------------------------------------------- snapshot

_live_cache = {"at": 0.0, "live": None}
_run_cache = {}  # team -> {"at", "run"}
TEAM_WORKFLOW = {"trading": "crypto-cycle.yml", "rendite": "crypto-rendite.yml", "social": "crypto-social.yml"}
TEAM_COMMAND = {"trading": "/crypto-machine:cycle", "rendite": "/crypto-machine:growth", "social": "/crypto-machine:social"}
TEAM_LABEL = {"trading": "ciclo del team trading", "rendite": "ciclo del team rendite", "social": "ciclo del team social"}
LIVE_TTL, RUN_TTL, LIVE_STALE_S = 4, 10, 180


def _age_s(ts):
    try:
        return time.time() - datetime.datetime.fromisoformat(ts).timestamp()
    except (TypeError, ValueError):
        return 1e9


def gh_live(team="trading"):
    """live.json from the mm-live branch + latest run of the team's workflow (both cached)."""
    with _gh_lock:
        if time.time() - _live_cache["at"] > LIVE_TTL:
            try:
                _live_cache["live"] = json.loads(gh_request("GET", f"/repos/{GH_REPO}/contents/live.json?ref=mm-live", raw=True))
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    _live_cache["live"] = None  # no cycle has published yet
            except (urllib.error.URLError, ValueError):
                pass  # keep the last good value
            _live_cache["at"] = time.time()
        rc = _run_cache.setdefault(team, {"at": 0.0, "run": None})
        if time.time() - rc["at"] > RUN_TTL:
            try:
                wf = TEAM_WORKFLOW.get(team, "crypto-cycle.yml")
                runs = gh_request("GET", f"/repos/{GH_REPO}/actions/workflows/{wf}/runs?per_page=1").get("workflow_runs") or []
                rc["run"] = ({"status": runs[0]["status"], "conclusion": runs[0].get("conclusion"),
                              "url": runs[0]["html_url"], "started": runs[0].get("run_started_at")} if runs else None)
            except (urllib.error.URLError, ValueError, KeyError):
                pass  # token without Actions:read -> rely on live.json only
            rc["at"] = time.time()
        return _live_cache["live"], rc["run"]


def _repo_read(rel):
    now_t = time.time()
    hit = _site_cache.get("repo:" + rel)
    if hit and now_t - hit[0] < SITE_TTL:
        return hit[1]
    data = None
    if GH_MODE:
        try:
            data = gh_request("GET", f"/repos/{GH_REPO}/contents/{urllib.parse.quote(rel)}?ref={GH_BRANCH}", raw=True)
        except urllib.error.HTTPError as e:
            if e.code != 404 and hit:
                return hit[1]
        except urllib.error.URLError:
            if hit:
                return hit[1]
    else:
        p = os.path.join(ROOT, *rel.split("/"))
        if os.path.isfile(p):
            with open(p, "rb") as f:
                data = f.read()
    _site_cache["repo:" + rel] = (now_t, data)
    return data


def _repo_list(rel):
    """File names in a repo folder (cached), from disk or GitHub."""
    now_t = time.time()
    hit = _site_cache.get("ls:" + rel)
    if hit and now_t - hit[0] < SITE_TTL:
        return hit[1]
    names = []
    if GH_MODE:
        try:
            items = gh_request("GET", f"/repos/{GH_REPO}/contents/{urllib.parse.quote(rel)}?ref={GH_BRANCH}")
            names = [i["name"] for i in items if isinstance(i, dict) and i.get("type") == "file"]
        except (urllib.error.URLError, ValueError, TypeError):
            names = hit[1] if hit else []
    else:
        d = os.path.join(ROOT, *rel.split("/"))
        names = sorted(n for n in os.listdir(d) if os.path.isfile(os.path.join(d, n))) if os.path.isdir(d) else []
    _site_cache["ls:" + rel] = (now_t, names)
    return names


RESEARCH_PREFIX = ("yield", "staking", "airdrop", "portfolio")


def _research_title(name: str) -> str:
    txt = (_repo_read(f"state/research/{name}") or b"").decode("utf-8", "replace")
    m = re.search(r"^#\s+(.+)$", txt, re.M)
    return (m.group(1) if m else name)[:90]


def sales_world(s):
    """Compact view for the 3D yield room ("sala rendite"): the yield vending machine (real public APIs from
    DefiLlama, via scripts/yields.py), the research notes wall, the owner's to-do board and the safe (real results)."""
    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    led = s.get("ledger") or []
    try:
        yj = json.loads(_repo_read("state/market/yields.json") or b"{}")
    except ValueError:
        yj = {}
    products = []
    for kind in ("stable", "majors"):
        for i, r in enumerate((yj.get(kind) or [])[:4]):
            products.append({"id": f"{kind}{i}", "title": f"{r.get('project')} · {r.get('symbol')}", "name": f"{r.get('project')} · {r.get('symbol')}",
                             "apy": r.get("apy_30d"), "chain": r.get("chain"), "tvl_musd": r.get("tvl_musd"),
                             "reward": r.get("apy_reward") or 0, "kind": "stablecoin" if kind == "stable" else "crypto principali",
                             "date": yj.get("date"), "price_eur": None, "revenue_eur": 0, "sales_30d": 0, "page": None, "image": ""})
    notes = sorted((n for n in _repo_list("state/research") if n.startswith(RESEARCH_PREFIX) and n.endswith(".md")), reverse=True)
    pages = [{"slug": n[:-3], "title": _research_title(n), "online": True, "views": 0, "clicks": 0} for n in notes[:10]]
    team_agents = {"yield-lead", "yield-scout", "airdrop-scout", "portfolio-analyst"}
    posts = [{"title": b.get("title", ""), "how": b.get("how", ""), "link": b.get("link", "")}
             for b in s.get("blockers") or [] if b.get("status") == "open" and b.get("owner") == "human" and b.get("by") in team_agents]
    posts += [{"title": a.get("title", ""), "how": "approvazione in plancia", "link": ""}
              for a in s.get("approvals") or [] if a.get("status") == "pending" and a.get("by") in team_agents]
    rev = [e for e in led if e.get("type") == "revenue"]
    airdrops = [{"title": _research_title(n), "slug": n[:-3]} for n in notes if n.startswith("airdrop")][:5]
    return {"products": products, "pages": pages, "posts": posts[:8], "months": ledger_months(led), "airdrops": airdrops,
            "revenue_eur": round(sum(e.get("amount_eur", 0) for e in rev), 2), "orders": len(rev),
            "revenue_30d": round(sum(e.get("amount_eur", 0) for e in rev if str(e.get("date", "")) >= since), 2),
            "pending_approvals": sum(1 for a in s.get("approvals") or [] if a.get("status") == "pending" and a.get("by") in team_agents),
            "site_url": (SITE_URL or "") + "/s/"}


def first_sale(s: dict) -> dict | None:
    """The first real sale in the ledger (for the party in the 3D rooms), or None."""
    rev = [e for e in s.get("ledger") or [] if e.get("type") == "revenue" and float(e.get("amount_eur") or 0) > 0]
    if not rev:
        return None
    e = sorted(rev, key=lambda e: str(e.get("date", "")))[0]
    return {"id": str(e.get("id") or e.get("ref") or e.get("date")), "date": str(e.get("date", ""))[:10],
            "amount_eur": round(float(e.get("amount_eur") or 0), 2), "name": str(e.get("note", "")).split(" · ")[0][:60]}


SOCIAL_AGENTS = {"social-lead", "social-writer", "visual-designer"}


def shop_name(o):
    """The name the product has in the shop (products/<id>/store.json), else the working title of the idea."""
    oid = str(o.get("id") or "")
    if re.match(r"^opp_[a-z0-9]{3,20}$", oid):
        try:
            name = json.loads(_repo_read(f"products/{oid}/store.json") or b"{}").get("name")
        except ValueError:
            name = ""
        if name:
            return str(name)
    return o.get("title", "")


SOCIAL_PLATFORM_RE = re.compile(r"\b(instagram|tiktok|linkedin|facebook)\b", re.I)


SOCIAL_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}-(instagram|tiktok|linkedin|facebook)$")
SLIDE = re.compile(r"^slide-\d{2}\.png$")


def _repo_dirs(rel):
    """Sub-folder names of a repo folder (cached), from disk or GitHub."""
    hit = _site_cache.get("dirs:" + rel)
    if hit and time.time() - hit[0] < SITE_TTL:
        return hit[1]
    names = []
    if GH_MODE:
        try:
            items = gh_request("GET", f"/repos/{GH_REPO}/contents/{urllib.parse.quote(rel)}?ref={GH_BRANCH}")
            names = sorted(i["name"] for i in items if isinstance(i, dict) and i.get("type") == "dir")
        except (urllib.error.URLError, ValueError, TypeError):
            names = hit[1] if hit else []
    else:
        d = os.path.join(ROOT, *rel.split("/"))
        names = sorted(n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n))) if os.path.isdir(d) else []
    _site_cache["dirs:" + rel] = (time.time(), names)
    return names


def social_gallery(s, limit=6):
    """Posts prepared by the social team for products on sale: first slide, platform and whether it is out."""
    out, blockers = [], s.get("blockers") or []
    for o in s.get("opportunities") or []:
        oid = str(o.get("id") or "")
        if o.get("stage") not in ("building", "live", "scaling") or not OPP_ID.match(oid):
            continue
        for folder in _repo_dirs(f"products/{oid}/social"):
            if not SOCIAL_DIR.match(folder) or "slide-01.png" not in _repo_list(f"products/{oid}/social/{folder}"):
                continue
            about = [b for b in blockers if folder in f"{b.get('how', '')} {b.get('link', '')}"]
            status = ("da pubblicare" if any(b.get("status") == "open" for b in about) else
                      "pubblicato" if any(b.get("status") == "done" for b in about) else "pronto")
            out.append({"img": f"/p/{oid}/{folder}/slide-01.png", "platform": folder[11:], "date": folder[:10], "status": status})
    return sorted(out, key=lambda x: x["date"], reverse=True)[:limit]


def social_file(parts):
    """/p/<opp>/<date-platform>/slide-NN.png: slides of posts about products already on sale."""
    if len(parts) != 3 or not OPP_ID.match(parts[0]) or not SOCIAL_DIR.match(parts[1]) or not SLIDE.match(parts[2]):
        return None
    if not (product_info(parts[0]) or strategy_visible(parts[0])):
        return None
    data = _repo_read(f"products/{parts[0]}/social/{parts[1]}/{parts[2]}")
    return (data, "image/png") if data else None


def social_world(s):
    """Compact view for the 3D social room: posts ready for the owner, posts published, products on sale."""
    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    mine = [b for b in s.get("blockers") or [] if b.get("owner") == "human"
            and (b.get("by") in SOCIAL_AGENTS or SOCIAL_PLATFORM_RE.search(str(b.get("title", ""))))]
    plat = lambda title: next((p for p in mm.SOCIAL_PLATFORMS if p in str(title).lower()), "altro")
    queue = [{"title": b.get("title", ""), "how": b.get("how", ""), "link": b.get("link", ""), "platform": plat(b.get("title")),
              "created": b.get("created"), "for": (b.get("blocks") or [None])[0]} for b in mine if b.get("status") == "open"]
    done = [b for b in mine if b.get("status") == "done" and str(b.get("resolved") or "") >= since]
    li = [a for a in s.get("approvals") or [] if a.get("channel") == "linkedin"]  # posts the machine publishes itself
    queue += [{"title": a.get("title", ""), "how": "Approva in plancia: la macchina lo pubblica su LinkedIn", "link": "",
               "platform": "linkedin", "created": a.get("created"), "for": a.get("opportunity")}
              for a in li if a.get("status") == "pending" or (a.get("status") == "approved" and not a.get("consumed"))]
    done += [{"title": a.get("title", "") + " (linkedin)", "blocks": [a.get("opportunity")], "resolved": a.get("resolved")}
             for a in li if a.get("consumed") and a.get("status") == "approved" and str(a.get("resolved") or "") >= since]
    products = []
    for o in s.get("opportunities") or []:
        if o.get("stage") in ("live", "scaling"):
            oid = o.get("id")
            products.append({"id": oid, "title": shop_name(o),
                             "ready": sum(1 for q in queue if q["for"] == oid),
                             "published": sum(1 for b in done if oid in (b.get("blocks") or []))})
    by_platform = {p: {"ready": sum(1 for q in queue if q["platform"] == p), "published": sum(1 for b in done if plat(b.get("title")) == p)}
                   for p in mm.SOCIAL_PLATFORMS}
    return {"products": products[:10], "queue": queue[:8], "published_30d": len(done),
            "published": [b.get("title", "") for b in done][-6:], "platforms": by_platform,
            "per_week": mm.SOCIAL_PER_WEEK, "pending_approvals": len(queue), "gallery": social_gallery(s)}


def room_kpi(s: dict) -> dict:
    """Numbers for the wall screen and the budget tank of the 3D rooms (read-only, no state change)."""
    b = s.get("budget") or {}
    ledger = s.get("ledger") or []
    rev = [e for e in ledger if e.get("type") == "revenue"]
    since = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
    live = [o for o in s.get("opportunities") or [] if o.get("stage") in ("live", "scaling")]
    ai_eur = (b.get("usd_total") or 0) * 0.92
    cost = sum(e.get("amount_eur", 0) for e in ledger if e.get("type") == "cost")
    return {"revenue_eur": round(sum(e.get("amount_eur", 0) for e in rev), 2),
            "revenue_30d": round(sum(e.get("amount_eur", 0) for e in rev if str(e.get("date", "")) >= since), 2),
            "sales_30d": sum(1 for e in rev if str(e.get("date", "")) >= since),
            "net_eur": round(sum(e.get("amount_eur", 0) for e in rev) - cost - ai_eur, 2),
            "ai_today_usd": round(b.get("usd_today") or 0, 2) if b.get("day") == mm.today() else 0.0,
            "ai_day_usd": mm.effective_day(s) if "ledger" in s and "usd_per_day" in b else b.get("usd_per_day"),
            "ai_cycle_usd": b.get("usd_per_cycle"), "saver": bool("ledger" in s and "usd_per_day" in b and mm.saver_active(s)),
            "live_products": len(live), **growth_numbers(s, rev)}


SOCIAL_HOSTS = ("linkedin.com", "lnkd.in", "facebook.com", "instagram.com", "tiktok.com", "reddit.com", "t.co", "x.com", "twitter.com")


def growth_numbers(s: dict, rev: list) -> dict:
    """Real numbers for the things that grow in the rooms: all-time site visits, buy clicks, visits from socials,
    and the milestones reached (never invented: each one is a fact in the state)."""
    rows = mm.traffic_summary(s, days=3650)
    visits = sum(r["views"] for r in rows); clicks = sum(r["clicks"] for r in rows)
    hosts = {}
    for b in ((s.get("traffic") or {}).get("boots") or {}).values():
        for v in (b.get("counts") or {}).values():
            for h, n in (v.get("r") or {}).items():
                hosts[h] = hosts.get(h, 0) + n
    social = lambda d: sum(n for h, n in hosts.items() if h == d or h.endswith("." + d))
    li = social("linkedin.com") + social("lnkd.in")
    orders, total = len(rev), sum(e.get("amount_eur", 0) for e in rev)
    return {"visits_total": visits, "clicks_total": clicks, "linkedin_visits": li,
            "milestones": [["Prima strategia in paper trading", any(o.get("stage") in ("building", "live", "scaling") for o in s.get("opportunities") or [])],
                           ["Prima strategia live", any(o.get("stage") in ("live", "scaling") for o in s.get("opportunities") or [])],
                           ["Primo segnale", bool(s.get("signals"))], ["Primo guadagno reale", orders > 0],
                           ["10 risultati registrati", orders >= 10], ["100 € di guadagni", total >= 100]]}


# ---------------------------------------------------------------- weather of the owner's city (Open-Meteo, free, no key)
# MM_CITY (default Bari). Cached 30 minutes; any error → no weather, the rooms stay as they are.
_weather = {"ts": 0, "data": None, "geo": None}


def wmo_kind(code: int) -> str:
    if code in (95, 96, 99): return "storm"
    if code in (71, 73, 75, 77, 85, 86): return "snow"
    if 51 <= code <= 67 or 80 <= code <= 82: return "rain"
    if code in (45, 48): return "fog"
    if code in (2, 3): return "clouds"
    return "clear"


def city_weather(opener=None):
    op = opener or urllib.request.urlopen
    if _weather["data"] and time.time() - _weather["ts"] < 1800:
        return _weather["data"]
    city = os.environ.get("MM_CITY", "Bari").strip() or "Bari"
    try:
        if not _weather["geo"] or _weather["geo"][0] != city:
            with op(urllib.request.Request("https://geocoding-api.open-meteo.com/v1/search?" + urllib.parse.urlencode({"name": city, "count": 1, "language": "it"}),
                                           headers={"User-Agent": "crypto-machine"}), timeout=10) as r:
                res = (json.loads(r.read() or b"{}").get("results") or [{}])[0]
            _weather["geo"] = (city, res.get("latitude"), res.get("longitude"), res.get("name") or city)
        _, lat, lon, name = _weather["geo"]
        if lat is None:
            return None
        with op(urllib.request.Request("https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(
                {"latitude": lat, "longitude": lon, "current": "temperature_2m,weather_code"}), headers={"User-Agent": "crypto-machine"}), timeout=10) as r:
            cur = json.loads(r.read() or b"{}").get("current") or {}
        data = {"city": name, "temp": cur.get("temperature_2m"), "code": cur.get("weather_code"), "kind": wmo_kind(int(cur.get("weather_code") or 0))}
        _weather.update(ts=time.time(), data=data)
        return data
    except (urllib.error.URLError, ValueError, TypeError, OSError):
        return None


# ---------------------------------------------------------------- live crypto prices for the ticker in the 3D rooms
# Coinbase public spot prices (no key), in euro. Cached 60 s; MM_TICKER = comma list of assets (default BTC,ETH,SOL,XRP,ADA,CRO).
_prices = {"ts": 0, "data": None}


def crypto_prices(opener=None):
    op = opener or urllib.request.urlopen
    if _prices["data"] is not None and time.time() - _prices["ts"] < 60:
        return _prices["data"]
    assets = [a.strip().upper() for a in os.environ.get("MM_TICKER", "BTC,ETH,SOL,XRP,ADA,CRO").split(",") if re.match(r"^[A-Za-z0-9]{2,10}$", a.strip())][:8]
    out = []
    for a in assets:
        try:
            with op(urllib.request.Request(f"https://api.coinbase.com/v2/prices/{a}-EUR/spot", headers={"User-Agent": "crypto-machine"}), timeout=8) as r:
                amt = float((json.loads(r.read() or b"{}").get("data") or {}).get("amount"))
            prev = next((x for x in (_prices["data"] or []) if x["asset"] == a), None)
            out.append({"asset": a, "eur": amt, "move": (0 if not prev else (1 if amt > prev["eur"] else -1 if amt < prev["eur"] else prev.get("move", 0)))})
        except (urllib.error.URLError, ValueError, TypeError, OSError):
            continue
    if out:
        _prices.update(ts=time.time(), data=out)
    return out or (_prices["data"] or [])


# Real candles for the chart screens of the 3D rooms: Coinbase Exchange public API (no key), cached 60 s per chart.
# Only a few pairs/timeframes are allowed, so the panel cannot be used as an open proxy.
CANDLE_PAIRS = {f"{a}-{q}" for a in ("BTC", "ETH", "SOL", "XRP", "ADA", "CRO") for q in ("EUR", "USD")}  # = market_data.MARKETS
CANDLE_TF = {"5m": 300, "15m": 900, "1h": 3600, "6h": 21600, "1d": 86400}
_candles = {}


def crypto_candles(pair: str, tf: str, opener=None) -> dict:
    pair, tf = str(pair).upper(), str(tf)
    if pair not in CANDLE_PAIRS or tf not in CANDLE_TF:
        return {"error": "coppia o timeframe non ammessi", "candles": []}
    key = pair + tf
    hit = _candles.get(key)
    if hit and time.time() - hit["ts"] < 60:
        return hit["data"]
    op = opener or urllib.request.urlopen
    try:
        url = f"https://api.exchange.coinbase.com/products/{pair}/candles?granularity={CANDLE_TF[tf]}"
        with op(urllib.request.Request(url, headers={"User-Agent": "crypto-machine"}), timeout=8) as r:
            rows = json.loads(r.read() or b"[]")
        # Coinbase: [time, low, high, open, close, volume], newest first (the last one is the candle still forming)
        out = sorted(([int(x[0]), float(x[3]), float(x[2]), float(x[1]), float(x[4]), float(x[5])] for x in rows if len(x) >= 6), key=lambda x: x[0])[-120:]
        data = {"pair": pair, "tf": tf, "candles": out, "source": "Coinbase", "ts": int(time.time())}
        if out:
            _candles[key] = {"ts": time.time(), "data": data}
            return data
    except (urllib.error.URLError, ValueError, TypeError, OSError, IndexError):
        pass
    return hit["data"] if hit else {"pair": pair, "tf": tf, "candles": [], "error": "dati non disponibili"}


# Order book (Coinbase Exchange level 2, public) grouped into 14 price bands per side, cached 30 s.
_books = {}


def crypto_orderbook(pair: str = "BTC-EUR", opener=None) -> dict:
    pair = str(pair).upper()
    if pair not in CANDLE_PAIRS:
        return {"error": "coppia non ammessa", "bids": [], "asks": []}
    hit = _books.get(pair)
    if hit and time.time() - hit["ts"] < 30:
        return hit["data"]
    op = opener or urllib.request.urlopen
    try:
        with op(urllib.request.Request(f"https://api.exchange.coinbase.com/products/{pair}/book?level=2",
                                       headers={"User-Agent": "crypto-machine"}), timeout=8) as r:
            j = json.loads(r.read() or b"{}")
        bids = [(float(p), float(q)) for p, q, *_ in j.get("bids", [])[:400]]
        asks = [(float(p), float(q)) for p, q, *_ in j.get("asks", [])[:400]]
        if not bids or not asks:
            raise ValueError("book vuoto")
        mid = (bids[0][0] + asks[0][0]) / 2
        step = mid * 0.0005  # bands of 0.05% of the price

        def bands(side, sign):
            out = []
            for k in range(14):
                lo, hi = (mid + sign * step * k, mid + sign * step * (k + 1))
                lo, hi = min(lo, hi), max(lo, hi)
                out.append([round((lo + hi) / 2, 2), round(sum(q for p, q in side if lo <= p < hi), 4)])
            return out
        data = {"pair": pair, "mid": round(mid, 2), "bids": bands(bids, -1), "asks": bands(asks, 1), "source": "Coinbase", "ts": int(time.time())}
        _books[pair] = {"ts": time.time(), "data": data}
        return data
    except (urllib.error.URLError, ValueError, TypeError, OSError, IndexError, KeyError):
        return hit["data"] if hit else {"pair": pair, "bids": [], "asks": [], "error": "dati non disponibili"}


# Last trades (Coinbase Exchange, public), newest first, cached 10 s.
_trades = {}


def crypto_trades(pair: str = "BTC-EUR", opener=None) -> dict:
    pair = str(pair).upper()
    if pair not in CANDLE_PAIRS:
        return {"error": "coppia non ammessa", "trades": []}
    hit = _trades.get(pair)
    if hit and time.time() - hit["ts"] < 10:
        return hit["data"]
    op = opener or urllib.request.urlopen
    try:
        with op(urllib.request.Request(f"https://api.exchange.coinbase.com/products/{pair}/trades?limit=40",
                                       headers={"User-Agent": "crypto-machine"}), timeout=8) as r:
            rows = json.loads(r.read() or b"[]")
        # Coinbase "side" is the maker side: "sell" = the taker bought (price went up), "buy" = the taker sold
        out = [{"t": str(x["time"])[11:19], "p": float(x["price"]), "q": float(x["size"]), "buy": x.get("side") == "sell"} for x in rows[:40]]
        data = {"pair": pair, "trades": out, "source": "Coinbase"}
        if out:
            _trades[pair] = {"ts": time.time(), "data": data}
            return data
    except (urllib.error.URLError, ValueError, TypeError, OSError, KeyError):
        pass
    return hit["data"] if hit else {"pair": pair, "trades": [], "error": "dati non disponibili"}


# Crypto Fear & Greed index (alternative.me, public, updated once a day), cached 1 hour.
_fng = {"ts": 0, "data": None}


def fear_greed(opener=None) -> dict:
    if _fng["data"] and time.time() - _fng["ts"] < 3600:
        return _fng["data"]
    op = opener or urllib.request.urlopen
    try:
        with op(urllib.request.Request("https://api.alternative.me/fng/?limit=1", headers={"User-Agent": "crypto-machine"}), timeout=8) as r:
            d = (json.loads(r.read() or b"{}").get("data") or [{}])[0]
        it = {"Extreme Fear": "paura estrema", "Fear": "paura", "Neutral": "neutrale", "Greed": "avidità", "Extreme Greed": "avidità estrema"}
        data = {"value": int(d["value"]), "label": it.get(d.get("value_classification"), d.get("value_classification", "")), "source": "alternative.me"}
        _fng.update(ts=time.time(), data=data)
        return data
    except (urllib.error.URLError, ValueError, TypeError, OSError, KeyError, IndexError):
        return _fng["data"] or {"value": None, "error": "dati non disponibili"}


def ledger_months(ledger: list, today: datetime.date | None = None) -> list:
    """Real results of the last 12 months, oldest first: [["2026-10", euro], ...] (revenue minus losses booked as trading)."""
    today = today or datetime.date.today()
    keys = []
    y, m = today.year, today.month
    for _ in range(12):
        keys.append(f"{y:04d}-{m:02d}"); m -= 1
        if not m:
            y, m = y - 1, 12
    keys.reverse()
    tot = dict.fromkeys(keys, 0.0)
    for e in ledger:
        k = str(e.get("date", ""))[:7]
        if k in tot and e.get("type") == "revenue":
            tot[k] += float(e.get("amount_eur") or 0)
    return [[k, round(v, 2)] for k, v in tot.items()]


def live_snapshot(team="trading") -> dict:
    team = team if team in TEAM_WORKFLOW else "trading"
    if GH_MODE:
        live, run = gh_live(team)
        s, _ = gh_state()
        s = s or mm.default_state()
    else:
        live = mm.live_load()
        running = bool(_cycle_proc and _cycle_proc.poll() is None)
        run = {"status": "in_progress" if running else "completed", "url": None, "started": None}
        with mm.locked():
            s = mm.load()
    live = live or {"running": False, "agents": {}, "events": []}
    if live.get("team", "trading") != team:  # the other team is working: this room stays asleep
        live = {"running": False, "agents": {}, "events": [], "other_team": live.get("team") if live.get("running") else None}
    run_active = bool(run and run.get("status") in ("queued", "in_progress"))
    # a crashed run can leave running=true behind: trust it only while fresh or while the action is active
    live_running = bool(live.get("running")) and (run_active or _age_s(live.get("updated")) < LIVE_STALE_S)
    phase = "working" if live_running else ("starting" if run_active else "idle")
    agents = {}
    for name, cfg in s.get("agents", {}).items():
        la = (live.get("agents") or {}).get(name, {}) if live_running else {}
        agents[name] = {"desc": cfg.get("desc", ""), "paused": cfg.get("status") != "active",
                        "status": la.get("status", "idle"), "task": la.get("task"),
                        "last": ((live.get("agents") or {}).get(name) or {}).get("last"), "runs": cfg.get("runs", 0),
                        "usd": round(cfg.get("usd", 0) or 0, 2), "last_run": cfg.get("last_run")}
    reps = [x for x in s.get("reports") or [] if x.get("team", "trading") == team]
    opps = s.get("opportunities") or []
    world = {  # compact view for the 3D control room (one light call instead of /api/state)
        "markets": [{"name": m.get("name", ""), "strategy": m.get("strategy", ""), "score": m.get("score", 0),
                     "evidence": str(m.get("evidence", ""))[:160]}
                    for m in sorted(s.get("markets") or [], key=lambda m: -m.get("score", 0))[:14]],
        "opps": [{"id": o.get("id"), "title": shop_name(o), "stage": o.get("stage"), "score": o.get("score", 0),
                  "expected_eur": o.get("expected_eur"), "price_eur": o.get("price_eur"), "strategy": o.get("strategy"),
                  "perf": strategy_perf(o.get("id")) if team == "trading" and o.get("stage") != "idea" else "",
                  "next": str(o.get("next_action", ""))[:140]} for o in opps if o.get("stage") != "killed"],
        "killed": [o.get("title", "") for o in opps if o.get("stage") == "killed"][-6:],
        "pending_approvals": sum(1 for a in s.get("approvals") or [] if a.get("status") == "pending"),
        "revenue_eur": round(sum(e.get("amount_eur", 0) for e in s.get("ledger") or [] if e.get("type") == "revenue"), 2),
        "signals": [{"ts": g.get("ts"), "text": str(g.get("text", ""))[:160]} for g in (s.get("signals") or [])[-6:]][::-1],
    }
    if team == "rendite":
        world = sales_world(s)
    elif team == "social":
        world = social_world(s)
    world["kpi"] = room_kpi(s)
    world["first_sale"] = first_sale(s)
    br = brand()
    world["shop"] = (br["a"] + br["b"]) if br else ""
    # what waits for the owner, for the "tocca a te" panel of every room
    world["todo"] = ([{"kind": "approval", "title": a.get("title", "")} for a in s.get("approvals") or [] if a.get("status") == "pending"]
                     + [{"kind": "blocker", "title": b.get("title", ""), "how": b.get("how", ""), "link": b.get("link", "")}
                        for b in s.get("blockers") or [] if b.get("status") == "open" and b.get("owner") == "human"])[:8]
    return {"world": world, "team": team, "other_team": live.get("other_team"), "phase": phase, "run": run, "live": {k: live.get(k) for k in ("started", "ended", "result", "updated", "run_url")},
            "events": (live.get("events") or [])[-20:], "agents": agents, "system": s.get("status"),
            "cycle": s.get("cycle"), "report": reps[-1] if reps else None, "mode": "github" if GH_MODE else "live"}


def snapshot() -> dict:
    extra = {}
    if GH_MODE:
        s, err = gh_state()
        if s is None:
            s = mm.default_state()
        s = json.loads(json.dumps(s))  # private copy
        extra = {"mode": "github", "repo": GH_REPO, "error": err, "sent": _gh_sent[-5:]}
        pending = 0
    else:
        with mm.locked():
            s = mm.load()
        pending = 0
        if os.path.exists(mm.INBOX_FILE):
            with open(mm.INBOX_FILE, encoding="utf-8") as f:
                pending = sum(1 for ln in f if ln.strip())
        extra = {"mode": "live"}
    for k, v in mm.default_state().items():
        s.setdefault(k, v)
    mm.roll_day(s)
    s = json.loads(json.dumps(s))  # display copy: products show their shop name, the idea title stays in work_title
    for o in s.get("opportunities") or []:
        name = shop_name(o)
        if name != o.get("title"):
            o["work_title"], o["title"] = o.get("title", ""), name
    return {"state": s, "kpis": mm.kpis(s), "allocation": mm.allocate(s, 0), "stages": mm.STAGES,
            "inbox_pending": pending, "cycle_running": bool(_cycle_proc and _cycle_proc.poll() is None),
            "can_run_cycle": not GH_MODE and shutil.which(CLAUDE) is not None, **extra}


def run_cycle(team: str = "trading") -> str:
    global _cycle_proc
    team = team if team in TEAM_WORKFLOW else "trading"
    if GH_MODE:
        # pressing the button again a few minutes later only spends AI quota twice: refuse while a run is recent
        if _recent_run(TEAM_WORKFLOW[team], datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None) - datetime.timedelta(minutes=MANUAL_COOLDOWN_MIN)):
            return f"{TEAM_LABEL[team]} già partito negli ultimi {MANUAL_COOLDOWN_MIN} minuti: aspetta che finisca (lo vedi nelle sale e su GitHub → Azioni)"
        gh_request("POST", f"/repos/{GH_REPO}/actions/workflows/{TEAM_WORKFLOW[team]}/dispatches", {"ref": GH_BRANCH})
        return TEAM_LABEL[team] + " avviato su GitHub Actions"
    if _cycle_proc and _cycle_proc.poll() is None:
        return "ciclo già in corso"
    if not shutil.which(CLAUDE):
        return "CLI claude non trovata"
    script = os.path.join(ROOT, "scripts", "cycle.sh")
    env = dict(os.environ, MM_COMMAND=TEAM_COMMAND[team], MM_FORCE="1")
    _cycle_proc = subprocess.Popen(["bash", script], cwd=os.getcwd(), env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return TEAM_LABEL[team] + " avviato"


# ---------------------------------------------------------------- automatic start at the scheduled times
# GitHub's own cron is best-effort and on young repos it is often hours late or skipped. The hosted panel is
# always on, so it starts each workflow itself at the scheduled minute (UTC, same times as the workflows' cron).
# The workflows keep their cron as a backup; their "gate" job skips a cron run if one already started recently.
MANUAL_COOLDOWN_MIN = 30  # "Avvia ciclo" refused if the same team started less than this ago
AUTOSTART = [  # (workflow, minute, hours UTC or None = every hour, window minutes)
    ("crypto-cycle.yml", 17, (22, 0, 2, 4), 25),   # team trading (see .github/workflows/crypto-cycle.yml)
    ("crypto-rendite.yml", 47, (23,), 25),         # team rendite
    ("crypto-pulse.yml", 23, None, 20),            # paper trading + signals, every hour, no AI
]
_auto_done = {}


def autostart_due(now: datetime.datetime, done: dict) -> list:
    """Workflows whose slot started in the last `window` minutes and were not dispatched yet for that slot."""
    due = []
    for wf, minute, hours, window in AUTOSTART:
        for back in (0, 1):  # this hour and the previous one (a slot at :47 may still be open after midnight)
            t = (now - datetime.timedelta(hours=back)).replace(minute=minute, second=0, microsecond=0)
            if (hours is None or t.hour in hours) and t <= now < t + datetime.timedelta(minutes=window):
                key = f"{wf}@{t.isoformat()}"
                if key not in done:
                    due.append((wf, key, t))
    return due


def _recent_run(wf: str, since: datetime.datetime) -> bool:
    """A run of the workflow was created at or after `since` (any trigger): don't start another one."""
    try:
        runs = gh_request("GET", f"/repos/{GH_REPO}/actions/workflows/{wf}/runs?per_page=5").get("workflow_runs") or []
    except (urllib.error.URLError, ValueError):
        return False
    return any(str(r.get("created_at", "")) >= since.strftime("%Y-%m-%dT%H:%M:%SZ") for r in runs)


def autostart_loop():
    if os.environ.get("MM_AUTOSTART", "true").lower() == "false" or not GH_MODE:
        return
    while True:
        try:
            now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            for wf, key, t in autostart_due(now, _auto_done):
                if not _recent_run(wf, t):
                    gh_request("POST", f"/repos/{GH_REPO}/actions/workflows/{wf}/dispatches", {"ref": GH_BRANCH, "inputs": {"auto": "1"}})
                    print(f"autostart: {wf} per le {t:%H:%M} UTC", flush=True)
                _auto_done[key] = True
            for k in [k for k in _auto_done if k.split("@")[1] < (now - datetime.timedelta(days=1)).isoformat()]:
                del _auto_done[k]
        except Exception as e:  # never stop the loop (network, permissions): retry next minute
            print(f"autostart: {e}", flush=True)
        time.sleep(60)


def apply_local(op, args):
    cmd = mm.enqueue({"op": op, "args": args, "via": "dashboard"})
    with mm.locked():
        s = mm.load()
        msgs = mm.drain_inbox(s)
        mm.save(s)
    return cmd["id"], msgs


# ---------------------------------------------------------------- HTTP

class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype if ctype.startswith("image/") else ctype + "; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_public(self, code, data, ctype, script_hash=""):
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text/", "application/xml")) else ""))
        self.send_header("Cache-Control", "public, max-age=300")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' https: data:; "
                         "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
                         f"script-src {script_hash and repr(script_hash) or repr('none')}; frame-ancestors 'none'; form-action 'none'")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _public(self, path):
        """Public site: /s/…, /robots.txt. Returns True if handled."""
        base = SITE_URL or f"https://{self.headers.get('Host', 'localhost')}"
        key = indexnow_key()
        gfile, _ = google_verify()
        if gfile and path == "/" + gfile:  # Google Search Console, "HTML file" method
            self._send_public(200, f"google-site-verification: {gfile}".encode(), "text/html")
        elif path == "/robots.txt":
            allow_g = f"Allow: /{gfile}\n" if gfile else ""
            self._send_public(200, f"User-agent: *\nAllow: /$\nAllow: /s/\nAllow: /m/\nAllow: /llms.txt\n{allow_g}Disallow: /\nSitemap: {base}/s/sitemap.xml\n".encode(), "text/plain")
        elif key and path == f"/{key}.txt":
            self._send_public(200, key.encode(), "text/plain")
        elif path == "/llms.txt":
            self._send_public(200, site_llms(base), "text/plain")
        elif path == "/s/feed.xml":
            self._send_public(200, site_feed(base), "application/xml")
        elif path.startswith("/p/"):
            hit = social_file([p for p in path[3:].split("/") if p])
            if hit:
                self._send_public(200, hit[0], hit[1])
            else:
                self._send_public(404, b"not found", "text/plain")
        elif path.startswith("/m/"):
            hit = media_file([p for p in path[3:].split("/") if p])
            if hit:
                self._send_public(200, hit[0], hit[1])
            else:
                self._send_public(404, b"not found", "text/plain")
        elif path == "/linkedin/callback":  # LinkedIn sends the owner back here after the login
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            if q.get("error"):
                ok, msg = False, "Collegamento annullato su LinkedIn: " + q.get("error_description", q["error"])[0][:200]
            else:
                ok, msg = linkedin_finish(q.get("state", [""])[0], q.get("code", [""])[0])
            page = ('<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>LinkedIn</title></head><body style="font:17px/1.5 system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 18px">'
                    f'<h1 style="font-size:1.4rem">{"✅" if ok else "⚠️"} {_attr(msg)}</h1>'
                    '<p><a href="/plancia" style="font-weight:700">Torna alla plancia</a></p></body></html>')
            self._send_public(200 if ok else 400, page.encode(), "text/html")
        elif path == "/brand/share.png":
            png = _site_read("_brand/share.png")
            if png and png.startswith(b"\x89PNG"):
                self._send_public(200, png, "image/png")
            else:
                self._send_public(404, b"not found", "text/plain")
        elif path == "/brand/logo.svg":
            svg = _site_read("_brand/logo.svg")
            if svg and b"<script" not in svg.lower():
                self._send_public(200, svg, "image/svg+xml")
            else:
                self._send_public(404, b"not found", "text/plain")
        elif path in ("/s", "/s/"):
            count("home", "v", self.headers.get("Referer", ""), self.headers.get("Host", ""), self.headers.get("User-Agent", ""))
            self._send_public(200, site_index(base), "text/html")
        elif path == "/":  # home of the public site (same content as /s/, canonical /s/); the owner is sent on to the panel
            count("home", "v", self.headers.get("Referer", ""), self.headers.get("Host", ""), self.headers.get("User-Agent", ""))
            self._send_public(200, site_index(base, home=True), "text/html", script_hash=OWNER_JS_HASH)
        elif path == "/s/sitemap.xml":
            self._send_public(200, site_sitemap(base), "application/xml")
        elif path.startswith("/go/"):
            parts = [p for p in path[4:].split("/") if p]
            url = go_target(parts)
            if not url:
                self._send_public(404, b"<!doctype html><meta charset=utf-8><p>Link non disponibile. <a href=\"/s/\">Tutte le guide</a></p>", "text/html")
                return True
            ref = self.headers.get("Referer", "")
            rp = urllib.parse.urlparse(ref).path if ref else ""
            page = rp.split("/")[2] if rp.startswith("/s/") and len(rp.split("/")) > 2 and rp.split("/")[2] else "-"
            count(page, "c", ref, self.headers.get("Host", ""), self.headers.get("User-Agent", ""), "/".join(parts))
            self.send_response(302)
            self.send_header("Location", url)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
            self.end_headers()
        elif path.startswith("/s/"):
            parts = [p for p in path[3:].split("/") if p]
            if len(parts) == 1 and not path.endswith("/") and not os.path.splitext(parts[0])[1]:
                self.send_response(301)
                self.send_header("Location", path + "/")
                self.end_headers()
                return True
            hit = site_file(path[3:])
            if hit:
                data = hit[0]
                if hit[1] == "text/html":
                    count(parts[0], "v", self.headers.get("Referer", ""), self.headers.get("Host", ""), self.headers.get("User-Agent", ""))
                    if len(parts) == 1 or parts[-1] == "index.html":
                        data = enrich(parts[0], data, base)
                self._send_public(200, data, hit[1])
            else:
                self._send_public(404, b"<!doctype html><meta charset=utf-8><p>Pagina non trovata. <a href=\"/s/\">Tutte le guide</a></p>", "text/html")
        else:
            return False
        return True

    def _authed(self):
        return not TOKEN or hmac.compare_digest(self.headers.get("X-MM-Token", ""), TOKEN)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            return self._send(200, {"ok": True})
        to = old_host_redirect(self.headers.get("Host", ""), self.path)
        if to:  # the shop has its own domain: the old Railway address sends everyone there (links already shared keep working)
            self.send_response(301); self.send_header("Location", to); self.send_header("Content-Length", "0"); self.end_headers()
            return
        if self._public(path):
            return
        if path in ("/plancia/", "/index.html"):  # the panel lives at /plancia; "/" is the public site
            self.send_response(301); self.send_header("Location", "/plancia"); self.end_headers(); return
        if path in ("/plancia", "/office.html", "/sales.html", "/ai.html", "/sims.html"):
            name = {"/office.html": "office.html", "/sales.html": "sales.html", "/ai.html": "ai.html", "/sims.html": "sims.html"}.get(path, "index.html")
            with open(os.path.join(HERE, name), "rb") as f:
                data = f.read()
            return self._send(200, data, "text/html")
        app = {"/manifest.webmanifest": "application/manifest+json", "/sw.js": "text/javascript", "/icon-192.png": "image/png",
               "/icon-512.png": "image/png", "/icon-maskable-512.png": "image/png", "/apple-touch-icon.png": "image/png"}
        if path in app:  # installable app (PWA): manifest, service worker and icons, no data
            with open(os.path.join(HERE, path[1:]), "rb") as f:
                return self._send(200, f.read(), app[path])
        if path in ("/scene3d.js", "/exchange.js", "/charts.js"):  # shared 3D look of the rooms (no data, public like the pages)
            with open(os.path.join(HERE, path[1:]), "rb") as f:
                return self._send(200, f.read(), "text/javascript")
        if path.startswith("/vendor/three/") and path.endswith(".js"):  # three.js shipped with the panel: rooms work without a CDN
            base = os.path.realpath(os.path.join(HERE, "vendor", "three"))
            f = os.path.realpath(os.path.join(HERE, path.lstrip("/")))
            if not f.startswith(base + os.sep) or not os.path.isfile(f):
                return self._send(404, {"error": "not found"})
            with open(f, "rb") as fh:
                return self._send(200, fh.read(), "text/javascript")
        if path == "/api/live":
            if not self._authed():
                return self._send(401, {"error": "token"})
            q = urllib.parse.parse_qs(self.path.partition("?")[2])
            return self._send(200, live_snapshot((q.get("team") or ["trading"])[0]))
        if path == "/api/state":
            if not self._authed():
                return self._send(401, {"error": "token"})
            return self._send(200, snapshot())
        if path == "/api/traffic":
            key = traffic_key()
            if not (self._authed() and TOKEN) and not (key and hmac.compare_digest(self.headers.get("X-MM-Traffic-Key", ""), key)):
                return self._send(401, {"error": "token"})
            with _traffic_lock:
                return self._send(200, json.loads(json.dumps(TRAFFIC)))
        if path == "/api/ai":
            if not self._authed():
                return self._send(401, {"error": "token"})
            return self._send(200, {"providers": secrets_status()})
        if path == "/api/prices":
            if not self._authed():
                return self._send(401, {"error": "token"})
            return self._send(200, {"prices": crypto_prices()})
        if path == "/api/orderbook":
            if not self._authed():
                return self._send(401, {"error": "token"})
            q = urllib.parse.parse_qs(self.path.partition("?")[2])
            return self._send(200, crypto_orderbook((q.get("pair") or ["BTC-EUR"])[0]))
        if path == "/api/trades":
            if not self._authed():
                return self._send(401, {"error": "token"})
            q = urllib.parse.parse_qs(self.path.partition("?")[2])
            return self._send(200, crypto_trades((q.get("pair") or ["BTC-EUR"])[0]))
        if path == "/api/feargreed":
            if not self._authed():
                return self._send(401, {"error": "token"})
            return self._send(200, fear_greed())
        if path == "/api/candles":
            if not self._authed():
                return self._send(401, {"error": "token"})
            q = urllib.parse.parse_qs(self.path.partition("?")[2])
            return self._send(200, crypto_candles((q.get("pair") or ["BTC-EUR"])[0], (q.get("tf") or ["1h"])[0]))
        if path == "/api/weather":
            if not self._authed():
                return self._send(401, {"error": "token"})
            return self._send(200, city_weather() or {})
        if path == "/api/secrets":
            if not self._authed():
                return self._send(401, {"error": "token"})
            return self._send(200, {**secrets_status(), "linkedin_redirect": linkedin_redirect(self.headers.get("Host", ""))})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if not self._authed():
            return self._send(401, {"error": "token"})
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "json"})
        try:
            if self.path == "/api/command":
                op, args = body.get("op"), body.get("args", {}) or {}
                if GH_MODE:
                    return self._send(200, {"ok": True, "result": [gh_command(op, args)]})
                cid, msgs = apply_local(op, args)
                return self._send(200, {"ok": True, "id": cid, "result": msgs})
            if self.path == "/api/ai/test":
                name, value = str(body.get("name", "")), str(body.get("value", ""))
                if name not in SECRETS and not AI_SECRET_RE.fullmatch(name):
                    return self._send(400, {"ok": False, "result": ["provider non previsto"]})
                ok, msg = (check_polar_token(value) if name == "POLAR_ACCESS_TOKEN" else
                           check_telegram_token(value) if name == "TELEGRAM_BOT_TOKEN" else check_ai_key(name, value))
                return self._send(200 if ok else 400, {"ok": ok, "result": [msg]})
            if self.path == "/api/secret":
                ok, msg = set_secret(str(body.get("name", "")), str(body.get("value", "")))
                return self._send(200 if ok else 400, {"ok": ok, "result": [msg]})
            if self.path == "/api/linkedin/start":
                ok, res = linkedin_start(str(body.get("client_id", "")), str(body.get("client_secret", "")), self.headers.get("Host", ""))
                return self._send(200 if ok else 400, {"ok": ok, "url": res if ok else "", "result": [] if ok else [res]})
            if self.path == "/api/cycle":
                return self._send(200, {"ok": True, "result": [run_cycle(str(body.get("team") or "trading"))]})
        except urllib.error.HTTPError as e:
            why = {401: "il token GitHub della plancia (MM_GITHUB_TOKEN) non è valido o è scaduto: creane uno nuovo",
                   403: "al token GitHub della plancia manca un permesso (Actions, Issues, Contents)",
                   404: "repository o ramo non trovati: controlla MM_GITHUB_REPO e MM_GITHUB_BRANCH"}.get(e.code, "controlla i permessi del token")
            return self._send(502, {"ok": False, "result": [f"GitHub ha risposto {e.code}: {why}"]})
        except urllib.error.URLError as e:
            return self._send(502, {"ok": False, "result": [f"GitHub non raggiungibile: {e.reason}"]})
        self._send(404, {"error": "not found"})


def main():
    public = "PORT" in os.environ
    host = os.environ.get("MM_HOST", "0.0.0.0" if public else "127.0.0.1")
    port = int(os.environ.get("MM_PORT") or os.environ.get("PORT") or "8787")
    if host not in ("127.0.0.1", "localhost", "::1") and len(TOKEN) < 12:
        sys.exit("ERRORE: plancia esposta in rete senza MM_TOKEN (min 12 caratteri). "
                 "Imposta la variabile MM_TOKEN e riavvia.")
    if not GH_MODE:
        with mm.locked():
            mm.save(mm.load())
    threading.Thread(target=publish_traffic_key, daemon=True).start()
    threading.Thread(target=indexnow_loop, daemon=True).start()
    threading.Thread(target=autostart_loop, daemon=True).start()
    where = f"GitHub {GH_REPO}@{GH_BRANCH}" if GH_MODE else mm.STATE_FILE
    print(f"Crypto Machine plancia → http://{host}:{port}  (stato: {where})", flush=True)
    def stop(signum, _frame):  # deploy or restart: keep the visits counted since the last sync
        r = flush_traffic()
        print(f"plancia: arresto, traffico {r or 'niente da salvare'}", flush=True)
        sys.exit(0)
    signal.signal(signal.SIGTERM, stop)
    ThreadingHTTPServer((host, port), H).serve_forever()


if __name__ == "__main__":
    main()
