#!/usr/bin/env python3
"""Publish state/live.json to the `mm-live` branch while a cycle runs.

The branch always holds a single commit (force-updated), so it never grows, and
pushes there trigger nothing: Railway and the workflows only watch `main`.
The dashboard reads it through the contents API (?ref=mm-live).

  live_push.py once            push if changed
  live_push.py loop [secs]     push every N seconds (default 8) until killed
Env: GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_API_URL (optional), MM_STATE_DIR.
"""
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
BRANCH = os.environ.get("MM_LIVE_BRANCH", "mm-live")
LIVE = os.path.join(os.environ.get("MM_STATE_DIR", os.path.join(os.getcwd(), "state")), "live.json")


def gh(method, path, body=None):
    req = urllib.request.Request(f"{API}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
                                          "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "crypto-machine"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = r.read()
    return json.loads(data) if data else {}


def push(text: str) -> None:
    tree = gh("POST", f"/repos/{REPO}/git/trees",
              {"tree": [{"path": "live.json", "mode": "100644", "type": "blob", "content": text}]})
    commit = gh("POST", f"/repos/{REPO}/git/commits", {"message": "live", "tree": tree["sha"], "parents": []})
    try:
        gh("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}", {"sha": commit["sha"], "force": True})
    except urllib.error.HTTPError as e:
        if e.code not in (404, 422):
            raise
        gh("POST", f"/repos/{REPO}/git/refs", {"ref": f"refs/heads/{BRANCH}", "sha": commit["sha"]})


_last = None


def once() -> None:
    global _last
    try:
        with open(LIVE, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return
    if text == _last:
        return
    try:
        push(text)
        _last = text
    except (urllib.error.URLError, KeyError, ValueError) as e:  # live view is best effort
        print(f"live_push: {e}", file=sys.stderr)


def loop(every: float) -> None:
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(1))
    while not stop:
        once()
        for _ in range(int(every * 10)):
            if stop:
                break
            time.sleep(0.1)


if __name__ == "__main__":
    if not (REPO and TOKEN):
        sys.exit(0)  # not on GitHub: nothing to publish
    if len(sys.argv) > 1 and sys.argv[1] == "loop":
        loop(float(sys.argv[2]) if len(sys.argv) > 2 else 8)
    else:
        once()
