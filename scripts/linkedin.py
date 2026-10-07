#!/usr/bin/env python3
"""Pubblica sul profilo LinkedIn del proprietario un post preparato dal team social, dopo la sua approvazione.

  python3 scripts/linkedin.py preview products/<id>/social/<data>-linkedin   # stampa il testo che verrebbe pubblicato
  python3 scripts/linkedin.py check                                         # il token funziona?

La pubblicazione vera la fa scripts/actions.py (approvazione "channel":"linkedin", "target": la cartella del post).
Testo: la sezione "Testo da incollare" di POST.md più gli hashtag. Immagini: carosello.pdf come documento
(il carosello di LinkedIn) oppure, se manca o LinkedIn lo rifiuta, le slide-NN.png (fino a 9).

Env: LINKEDIN_ACCESS_TOKEN (salvato dalla plancia con "Collega LinkedIn", scade dopo 60 giorni),
LINKEDIN_PERSON_URN (urn:li:person:…, salvato insieme al token), LINKEDIN_VERSION (facoltativo, AAAAMM).
API ufficiali: Posts, Images e Documents (permesso w_member_social del prodotto "Share on LinkedIn").
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.linkedin.com"
RESERVED = set("\\|{}@[]()<>#*_~")  # LinkedIn "little text" format: these must be escaped in commentary
MAX_TEXT = 2900


def version() -> str:
    """LinkedIn-Version header: a monthly version from ~2 months ago (versions stay supported for a year)."""
    v = os.environ.get("LINKEDIN_VERSION", "").strip()
    if re.fullmatch(r"20\d{4}", v):
        return v
    d = dt.date.today().replace(day=1) - dt.timedelta(days=45)
    return f"{d.year}{d.month:02d}"


def escape(text: str) -> str:
    """Escape the little-text reserved characters; hashtags become real LinkedIn hashtags."""
    out, i = [], 0
    for m in re.finditer(r"#(\w+)", text):
        out.append("".join("\\" + c if c in RESERVED else c for c in text[i:m.start()]))
        out.append("{hashtag|\\#|" + m.group(1) + "}")
        i = m.end()
    out.append("".join("\\" + c if c in RESERVED else c for c in text[i:]))
    return "".join(out)


def section(md: str, title: str) -> str:
    m = re.search(r"^##\s*" + re.escape(title) + r"[^\n]*\n(.*?)(?=^##\s|\Z)", md, re.S | re.M | re.I)
    return m.group(1).strip() if m else ""


def post_text(folder: str) -> str:
    """The text to publish: 'Testo da incollare' (without notes in parentheses for the owner) + hashtags."""
    with open(os.path.join(folder, "POST.md"), encoding="utf-8") as f:
        md = f.read()
    body = section(md, "Testo da incollare") or section(md, "Testo")
    paras = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    paras = [p for p in paras if not (p.startswith("(") and p.endswith(")"))]  # e.g. "(Circa 1.400 caratteri: …)"
    tags = section(md, "Hashtag")
    tags = " ".join(t for t in re.findall(r"#\w+", tags))
    text = "\n\n".join(paras) + (("\n\n" + tags) if tags and tags not in body else "")
    if "aiuto dell'AI" not in text and "aiuto dell’AI" not in text:  # POLICY: AI use stated
        text += "\n\nCreato con l'aiuto dell'AI"
    return text[:MAX_TEXT]


class LinkedIn:
    def __init__(self, token: str, person: str, opener=None):
        self.token, self.person = token, person
        self.open = opener or urllib.request.urlopen

    def call(self, method: str, path: str, body=None, raw: bytes | None = None, headers: dict | None = None):
        h = {"Authorization": f"Bearer {self.token}", "LinkedIn-Version": version(), "X-Restli-Protocol-Version": "2.0.0"}
        data = raw
        if body is not None:
            data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
        h.update(headers or {})
        url = path if path.startswith("http") else API + path
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with self.open(req, timeout=120) as r:
                txt = r.read().decode("utf-8", "replace")
                return (json.loads(txt) if txt.strip().startswith("{") else {}), dict(r.headers)
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"LinkedIn {method} {path.split('?')[0]}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")

    def upload(self, kind: str, path: str) -> str:
        """kind: "images" or "documents". Returns the urn of the uploaded file."""
        res, _ = self.call("POST", f"/rest/{kind}?action=initializeUpload", {"initializeUploadRequest": {"owner": self.person}})
        v = res.get("value") or {}
        with open(path, "rb") as f:
            self.call("PUT", v["uploadUrl"], raw=f.read(), headers={"Content-Type": "application/octet-stream"})
        return v.get("image") or v.get("document")

    def wait_ready(self, urn: str, kind: str, tries: int = 10):
        for _ in range(tries):
            try:
                res, _ = self.call("GET", f"/rest/{kind}/{urllib.parse.quote(urn, safe='')}")
                if str(res.get("status", "")).upper() in ("AVAILABLE", ""):
                    return
            except RuntimeError:
                pass
            time.sleep(3)

    def post(self, text: str, content: dict | None = None) -> str:
        body = {"author": self.person, "commentary": escape(text), "visibility": "PUBLIC",
                "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
                "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
        if content:
            body["content"] = content
        _, h = self.call("POST", "/rest/posts", body)
        return h.get("x-restli-id") or h.get("X-RestLi-Id") or ""



def publish(folder: str, api: LinkedIn) -> dict:
    """Publish the post in `folder`; returns {urn, url, kind}."""
    text = post_text(folder)
    title = re.sub(r"\s+", " ", text.split("\n")[0])[:100] or "Carosello"
    pdf = os.path.join(folder, "carosello.pdf")
    slides = sorted(glob.glob(os.path.join(folder, "slide-*.png")))[:9]
    urn, kind = "", "text"
    if os.path.exists(pdf):
        try:
            doc = api.upload("documents", pdf); api.wait_ready(doc, "documents")
            urn, kind = api.post(text, {"media": {"title": title, "id": doc}}), "carosello"
        except RuntimeError as e:
            print(f"linkedin: carosello PDF non accettato, uso le immagini ({e})")
    if not urn and slides:
        ids = [api.upload("images", p) for p in slides]
        content = {"media": {"id": ids[0]}} if len(ids) == 1 else {"multiImage": {"images": [{"id": i} for i in ids]}}
        urn, kind = api.post(text, content), "immagini"
    if not urn:
        urn = api.post(text)
    return {"urn": urn, "url": f"https://www.linkedin.com/feed/update/{urn}/" if urn else "", "kind": kind,
            "published": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


def from_env(opener=None) -> LinkedIn:
    token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()
    person = os.environ.get("LINKEDIN_PERSON_URN", "").strip()
    if not token or not person.startswith("urn:li:person:"):
        raise RuntimeError("LinkedIn non collegato: in plancia, Impostazioni → Collega LinkedIn")
    return LinkedIn(token, person, opener)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if argv[:1] == ["preview"] and len(argv) == 2:
        print(post_text(argv[1])); return 0
    if argv[:1] == ["check"]:
        try:
            api = from_env()
            res, _ = api.call("GET", "https://api.linkedin.com/v2/userinfo")
            print(f"linkedin: collegato come {res.get('name', '?')}")
        except RuntimeError as e:
            print(f"linkedin: {e}")
        return 0
    print(__doc__); return 2


if __name__ == "__main__":
    sys.exit(main())
