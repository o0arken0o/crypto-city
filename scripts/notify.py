#!/usr/bin/env python3
"""Avvisa il proprietario solo quando serve davvero: UNA issue GitHub "Crypto Machine: serve la tua attenzione".

- ci sono approvazioni in attesa o blocchi "tocca a te" → la issue è aperta e il testo elenca cosa fare;
  un commento con @proprietario (quindi una notifica/email) parte SOLO quando compare qualcosa di nuovo;
- non c'è più niente → la issue viene chiusa.
Nessun'altra issue, nessuna notifica ripetuta a ogni ciclo. Il titolo non inizia con "mm:", quindi
non viene mai scambiato per un comando.

  python3 scripts/notify.py            # nei workflow, dopo il commit dello stato
  python3 scripts/notify.py --dry-run  # stampa il testo senza chiamare GitHub

Env: GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_API_URL (opzionale), MM_SITE_URL (link alla plancia, opzionale).
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import mm  # noqa: E402

TITLE = "Crypto Machine: serve la tua attenzione"
IDS = re.compile(r"<!-- mm-notify: ([\w, ]*) -->")


def pending_items(s: dict) -> list[dict]:
    """Cosa aspetta il proprietario, dal più vecchio."""
    items = [{"id": a["id"], "text": f"Approva o rifiuta: {a['title']}", "since": a.get("created", "")}
             for a in s["approvals"] if a["status"] == "pending"]
    items += [{"id": b["id"], "text": f"Sblocca: {b['title']}" + (f" — {b['how']}" if b.get("how") else ""),
               "since": b.get("created", ""), "link": b.get("link")}
              for b in s.get("blockers", []) if b.get("status") == "open" and b.get("owner") != "agent"]
    return sorted(items, key=lambda i: i["since"])


def body_for(items: list[dict], panel: str) -> str:
    lines = [f"- [ ] {i['text']} _(dal {i['since'][:10]})_" + (f" · [link]({i['link']})" if i.get("link") else "") for i in items]
    where = f"Decidi dalla [plancia]({panel})." if panel else "Decidi dalla plancia."
    return ("Gli agenti sono fermi su queste cose finché non intervieni tu:\n\n" + "\n".join(lines) +
            f"\n\n{where} Questa issue si aggiorna e si chiude da sola quando non resta niente."
            f"\n<!-- mm-notify: {', '.join(i['id'] for i in items)} -->\n\n---\n_Crypto Machine_")


class GitHub:
    def __init__(self, token: str, repo: str, api: str = "https://api.github.com", opener=None):
        self.token, self.repo, self.api = token, repo, api
        self.open = opener or urllib.request.urlopen

    def call(self, method: str, path: str, body=None):
        req = urllib.request.Request(f"{self.api}/repos/{self.repo}{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                                              "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "crypto-machine"})
        with self.open(req, timeout=20) as r:
            data = r.read()
        return json.loads(data) if data else {}


def sync(gh: GitHub, s: dict, owner: str, panel: str = "") -> str:
    items = pending_items(s)
    issue = next((i for i in gh.call("GET", "/issues?state=open&per_page=100")
                  if i.get("title") == TITLE and "pull_request" not in i), None)
    if not items:
        if issue:
            gh.call("POST", f"/issues/{issue['number']}/comments", {"body": "Tutto risolto, chiudo. ✓\n\n---\n_Crypto Machine_"})
            gh.call("PATCH", f"/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"})
            return f"notify: niente in attesa, chiusa #{issue['number']}"
        return "notify: niente in attesa"
    body = body_for(items, panel)
    if not issue:
        new = gh.call("POST", "/issues", {"title": TITLE, "body": body})
        gh.call("POST", f"/issues/{new['number']}/comments", {"body": f"@{owner} ci sono {len(items)} cose che aspettano te.\n\n---\n_Crypto Machine_"})
        return f"notify: aperta #{new['number']} ({len(items)} in attesa)"
    m = IDS.search(issue.get("body") or "")
    known = {x.strip() for x in m.group(1).split(",")} if m else set()
    fresh = [i for i in items if i["id"] not in known]
    if (issue.get("body") or "") != body:
        gh.call("PATCH", f"/issues/{issue['number']}", {"body": body})
    if fresh:  # solo le novità generano una notifica
        text = "\n".join(f"- {i['text']}" for i in fresh)
        gh.call("POST", f"/issues/{issue['number']}/comments", {"body": f"@{owner} novità:\n{text}\n\n---\n_Crypto Machine_"})
    return f"notify: #{issue['number']} aggiornata, {len(items)} in attesa, {len(fresh)} nuove"


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    with mm.locked():
        s = mm.load()
    panel = os.environ.get("MM_SITE_URL", "").rstrip("/")
    panel = panel + "/plancia" if panel else ""
    if "--dry-run" in argv:
        items = pending_items(s)
        print(body_for(items, panel) if items else "notify: niente in attesa")
        return 0
    token, repo = os.environ.get("GITHUB_TOKEN", ""), os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        print("notify: GITHUB_TOKEN/GITHUB_REPOSITORY mancanti, saltato")
        return 0
    owner = os.environ.get("GITHUB_REPOSITORY_OWNER") or repo.split("/")[0]
    try:
        print(sync(GitHub(token, repo, os.environ.get("GITHUB_API_URL", "https://api.github.com")), s, owner, panel))
    except Exception as e:  # una notifica mancata non deve mai far fallire il ciclo
        print(f"notify: errore, saltato ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
