#!/usr/bin/env python3
"""Apply every open "mm: …" command issue opened by the repo OWNER (oldest first).

Sweeping all open issues (instead of only the one that triggered the run) means a
workflow run cancelled by the concurrency group never loses a command: the next
run picks it up. Commands older than MM_COMMAND_TTL_HOURS (default 24) are closed
without being applied, and so is a settings command (budget, pause, weight, stage…)
superseded by a newer command on the same target, so a stale click can't overwrite
newer settings. Additive commands (directives, ledger entries) are never superseded.

  apply_issues.py apply   -> applies to state, writes the outcome to $MM_ISSUES_OUT
  apply_issues.py close   -> comments + closes the issues listed in $MM_ISSUES_OUT
                             (run it only after the state commit was pushed)
Env: GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_API_URL (optional), MM_STATE_DIR.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import mm  # noqa: E402

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT = os.environ.get("MM_ISSUES_OUT", "/tmp/mm_issues.json")
TTL_H = float(os.environ.get("MM_COMMAND_TTL_HOURS", "24"))
# last-write-wins ops -> which arg identifies the target
SETTINGS = {"system": None, "budget": None, "agent": "name", "strategy": "name",
            "opportunity": "id", "approval": "id"}
FOOTER = "\n\n---\n_Crypto Machine_"


def gh(method, path, body=None):
    req = urllib.request.Request(f"{API}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "crypto-machine"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    return json.loads(data) if data else {}


def command_issues(since):
    issues, page = [], 1
    while True:
        batch = gh("GET", f"/repos/{REPO}/issues?state=all&since={since}&per_page=100&page={page}&sort=created&direction=asc")
        issues += batch
        if len(batch) < 100:
            break
        page += 1
    return issues


def is_owner_command(i):
    """Only the repo OWNER's command issues count, for applying AND for superseding:
    otherwise anyone could open 'mm: budget' to cancel the owner's real commands."""
    return ("pull_request" not in i
            and (i.get("title") or "").startswith("mm:")
            and i.get("author_association") == "OWNER")


def parse(body):
    m = re.search(r"```json\s*(\{.*?\})\s*```", body or "", re.S)
    if not m:
        return None
    c = json.loads(m.group(1))
    return {"op": c.get("op"), "args": c.get("args", {}) or {}, "via": "github-issue"}


def target(c):
    if not c or c.get("op") not in SETTINGS:
        return None
    k = SETTINGS[c["op"]]
    return (c["op"], str(c["args"].get(k, "")) if k else "")


def safe_parse(i):
    try:
        return parse(i.get("body"))
    except (ValueError, TypeError):
        return None


def cmd_apply():
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = [i for i in command_issues(since) if is_owner_command(i)]
    # newest command issue (open or closed) per settings target
    newest = {}
    for i in issues:
        t = target(safe_parse(i))
        if t:
            newest[t] = max(newest.get(t, 0), i["number"])
    results = []
    with mm.locked():
        s = mm.load()
        for i in (x for x in issues if x["state"] == "open"):
            created = dt.datetime.fromisoformat(i["created_at"].replace("Z", "+00:00"))
            age_h = (now - created).total_seconds() / 3600
            t = target(safe_parse(i))
            if t and newest[t] > i["number"]:
                results.append({"number": i["number"], "applied": False,
                                "msg": f"superato dal comando più recente #{newest[t]} sullo stesso elemento."})
                continue
            if age_h > TTL_H:
                results.append({"number": i["number"], "applied": False,
                                "msg": f"scaduto dopo {age_h:.0f} h, per non sovrascrivere impostazioni più recenti. Se serve ancora, ripeti il comando dalla plancia."})
                continue
            try:
                c = parse(i.get("body"))
                msg = mm.apply_command(s, c) if c else "nessun blocco ```json``` trovato"
                applied = c is not None
            except (ValueError, TypeError) as e:
                msg, applied = f"comando non valido: {e}", False
            if applied:
                mm.log(s, "human", f"{msg} (issue #{i['number']})")
            results.append({"number": i["number"], "applied": applied, "msg": msg})
        if any(r["applied"] for r in results):
            mm.save(s)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False)
    for r in results:
        print(f"#{r['number']}: {'OK' if r['applied'] else 'scartato'} — {r['msg']}")
    if not results:
        print("nessun comando in attesa")


def cmd_close():
    if not os.path.exists(OUT):
        return
    for r in json.load(open(OUT, encoding="utf-8")):
        prefix = "Applicato" if r["applied"] else "Non applicato"
        gh("POST", f"/repos/{REPO}/issues/{r['number']}/comments", {"body": f"{prefix}: {r['msg']}{FOOTER}"})
        gh("PATCH", f"/repos/{REPO}/issues/{r['number']}",
           {"state": "closed", "state_reason": "completed" if r["applied"] else "not_planned"})


if __name__ == "__main__":
    {"apply": cmd_apply, "close": cmd_close}[sys.argv[1] if len(sys.argv) > 1 else "apply"]()
