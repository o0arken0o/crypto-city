#!/usr/bin/env python3
"""Porta nello stato i conteggi di traffico della plancia online (visite, clic /go/, siti di provenienza).

  python3 scripts/traffic_sync.py

Env: MM_TRAFFIC_URL (o MM_SITE_URL) e MM_TRAFFIC_KEY. La plancia salva da sola entrambi come secret GitHub
all'avvio (serve il permesso Secrets sul suo token). Senza, non fa nulla. Non deve mai fermare il ciclo.
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import mm  # noqa: E402


def main() -> int:
    base = (os.environ.get("MM_TRAFFIC_URL") or os.environ.get("MM_SITE_URL") or "").strip().rstrip("/")
    key = os.environ.get("MM_TRAFFIC_KEY", "").strip()
    if not base or not key:
        print("traffico: MM_TRAFFIC_URL/MM_TRAFFIC_KEY non impostati, saltato")
        return 0
    req = urllib.request.Request(base + "/api/traffic", headers={"X-MM-Traffic-Key": key, "User-Agent": "crypto-machine-sync"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            snap = json.loads(r.read() or b"{}")
    except Exception as e:  # noqa: BLE001
        print(f"traffico: plancia non raggiungibile, saltato ({type(e).__name__})")
        return 0
    mm.main(["traffic", json.dumps(snap)])
    return 0


if __name__ == "__main__":
    sys.exit(main())
