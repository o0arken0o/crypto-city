#!/usr/bin/env python3
"""Guardia della POLICY attorno al turno degli agenti (la lancia scripts/cycle.sh da una copia temporanea).

  guard.py snapshot <file>   prima degli agenti: salva approvazioni, ledger e marcatori di pubblicazione
  guard.py verify <file>     dopo gli agenti: annulla ciò che solo il proprietario può fare

Gli agenti possono solo CHIEDERE un'approvazione. Se durante il loro turno un'approvazione diventa
"approved", compare un marcatore di pubblicazione (site/*/.approved, products/*/live.json) o viene
registrato un incasso, la guardia lo annulla e scrive un allarme nel registro eventi.
Le azioni legittime (sync delle vendite, esecuzione delle approvazioni) girano prima o dopo il turno.
Nota per l'uso in locale: approvazioni o incassi inseriti dalla plancia locale MENTRE gira un ciclo
vengono annullati anche loro; ripetili a ciclo finito.
"""
from __future__ import annotations

import glob
import json
import os
import sys

ROOT = os.environ.get("MM_ROOT") or os.getcwd()
HERE = os.path.dirname(os.path.abspath(__file__))
# cycle.sh runs a temporary copy with its own engine/ next to it, out of the agents' reach
sys.path.insert(0, os.path.join(HERE, "engine") if os.path.isdir(os.path.join(HERE, "engine")) else os.path.join(ROOT, "engine"))
import mm  # noqa: E402

MARKERS = ("site/*/.approved", "products/*/live.json")


def markers(root: str) -> list[str]:
    return sorted(os.path.relpath(p, root) for pat in MARKERS for p in glob.glob(os.path.join(root, pat)))


def snapshot(path: str, root: str = ROOT) -> None:
    with mm.locked():
        s = mm.load()
    snap = {"approvals": {a["id"]: a["status"] for a in s["approvals"]},
            "ledger": [e["id"] for e in s["ledger"]], "markers": markers(root),
            "signals": [x["id"] for x in s.get("signals", [])]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snap, f)


def verify(path: str, root: str = ROOT) -> list[str]:
    with open(path, encoding="utf-8") as f:
        snap = json.load(f)
    alarms = []
    for rel in markers(root):
        if rel not in snap["markers"]:
            os.remove(os.path.join(root, rel))
            alarms.append(f"rimosso {rel}: creato dagli agenti senza approvazione")
    with mm.locked():
        s = mm.load()
        for a in s["approvals"]:
            before = snap["approvals"].get(a["id"])
            if a["status"] != "pending" and before in (None, "pending"):
                alarms.append(f"approvazione {a['id']} riportata in attesa: decisa durante il turno degli agenti")
                a.update(status="pending", resolved=None, consumed=None)
        known = set(snap["ledger"])
        fake = [e for e in s["ledger"] if e["id"] not in known and e["type"] == "revenue"]
        if fake:
            s["ledger"] = [e for e in s["ledger"] if e not in fake]
            alarms.append(f"annullati {len(fake)} incassi registrati dagli agenti (solo il proprietario o le sync reali)")
        sig = [x for x in s.get("signals", []) if x["id"] not in set(snap.get("signals", []))]
        if sig:  # signals come only from scripts/paper.py, never from the agents
            s["signals"] = [x for x in s["signals"] if x not in sig]
            alarms.append(f"annullati {len(sig)} segnali scritti dagli agenti (solo il paper trading li genera)")
        for msg in alarms:
            mm.log(s, "engine", "GUARDIA POLICY: " + msg)
        mm.save(s)
    return alarms


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] not in ("snapshot", "verify"):
        print(__doc__)
        return 2
    if argv[0] == "snapshot":
        snapshot(argv[1])
    else:
        for msg in verify(argv[1]):
            print("GUARDIA POLICY:", msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
