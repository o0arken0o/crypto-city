#!/usr/bin/env python3
"""Esegue da solo le azioni che il proprietario ha approvato in plancia (POLICY: prima l'ok umano).

  python3 scripts/actions.py run-approved

Canali gestiti (campo "channel" dell'approvazione):
  site          pubblica la pagina site/<target>/public/ sul sito servito dalla plancia (/s/<target>/):
                scrive site/<target>/.approved, che la plancia controlla prima di servire qualsiasi file.
  golive        strategia approvata per soldi veri: scrive products/<opp>/live.json con il capitale massimo
                (capital_eur). Nessun ordine automatico: scripts/paper.py manda i SEGNALI al proprietario.
  stop          ferma una strategia live (torna solo paper trading).
  linkedin      pubblica sul profilo LinkedIn del proprietario il post in "target" (products/<id>/social/<data>-linkedin):
                testo di POST.md e carosello.pdf o slide-NN.png (serve LinkedIn collegato dalla plancia; senza, resta in coda).
Le approvazioni rifiutate non vengono mai eseguite; ogni approvazione viene eseguita una sola volta.
"""
from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import mm  # noqa: E402

SITE = os.path.join(ROOT, "site")
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{1,60}$")


def publish_page(ap: dict) -> str:
    slug = ap.get("target") or ap.get("opportunity") or ""
    if not SLUG.match(slug):
        raise ValueError(f"slug della pagina non valido: {slug!r}")
    index = os.path.join(SITE, slug, "public", "index.html")
    if not os.path.exists(index):
        raise ValueError(f"manca site/{slug}/public/index.html")
    with open(os.path.join(SITE, slug, ".approved"), "w", encoding="utf-8") as f:
        json.dump({"approval": ap["id"], "title": ap["title"], "approved": ap.get("resolved"), "published": mm.now()}, f,
                  ensure_ascii=False, indent=1)
    base = os.environ.get("MM_SITE_URL", "").rstrip("/")
    return f"pagina online: {base}/s/{slug}/" if base else f"pagina {slug} online su /s/{slug}/"


OPP = re.compile(r"^opp_[a-z0-9]{3,20}$")


def go_live(ap: dict) -> str:
    """The owner approved a strategy for real money: write products/<id>/live.json (protected by the guard).
    Nothing is ever sent to an exchange: from now on scripts/paper.py turns every exposure change into a
    signal for the owner (Telegram + panel), who executes it by hand if he agrees."""
    oid = ap.get("opportunity") or ""
    folder = os.path.join(ROOT, "products", oid)
    if not OPP.match(oid) or not os.path.isfile(os.path.join(folder, "strategy.py")):
        raise ValueError(f"strategia non valida: {oid!r}")
    cap = float(ap.get("capital_eur") or 0)
    if cap <= 0:
        raise ValueError("manca il capitale massimo (capital_eur) nell'approvazione")
    with open(os.path.join(folder, "live.json"), "w", encoding="utf-8") as f:
        json.dump({"approved": True, "approval": ap["id"], "title": ap["title"], "capital_eur": cap,
                   "resolved": ap.get("resolved"), "since": mm.now(), "mode": "segnali (esecuzione manuale)"},
                  f, ensure_ascii=False, indent=1)
    return f"{oid} live: segnali al proprietario, capitale massimo {cap:.0f} €"


def stop_live(ap: dict) -> str:
    """Stop a live strategy (back to paper trading only): live.json → live-stopped.json."""
    oid = ap.get("opportunity") or ""
    path = os.path.join(ROOT, "products", oid, "live.json")
    if not OPP.match(oid) or not os.path.exists(path):
        return f"{oid} non era live"
    os.replace(path, os.path.join(ROOT, "products", oid, "live-stopped.json"))
    mm.main(["stage", oid, "building", "--next", "fermata dal proprietario: solo paper trading", "--agent", "risk-manager"])
    return f"{oid} fermata: niente più segnali, resta in paper trading"


LI_TARGET = re.compile(r"^products/opp_[a-z0-9]{3,20}/social/\d{4}-\d{2}-\d{2}-linkedin$")


def publish_linkedin(ap: dict) -> str:
    import linkedin
    target = str(ap.get("target") or "")
    folder = os.path.join(ROOT, target)
    if not LI_TARGET.match(target) or not os.path.isfile(os.path.join(folder, "POST.md")):
        raise ValueError(f"cartella del post non valida: {target!r}")
    done = os.path.join(folder, "published.json")
    if os.path.exists(done):
        return "già pubblicato su LinkedIn"
    try:
        res = linkedin.publish(folder, linkedin.from_env())
    except RuntimeError as e:
        if "non collegato" in str(e) or "HTTP 401" in str(e):  # wait for the owner to (re)connect LinkedIn
            raise RuntimeError(str(e) if "non collegato" in str(e) else "accesso LinkedIn scaduto: ricollega LinkedIn dalla plancia")
        raise ValueError(str(e))  # anything else: tell the owner instead of retrying forever
    with open(done, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    with mm.locked():
        s = mm.load()
    for b in s["blockers"]:  # the old "publish it yourself" reminder for this post is no longer needed
        if b.get("status") == "open" and target in str(b.get("how", "")):
            mm.main(["unblock", b["id"], "--agent", "social-lead"])
    return f"pubblicato su LinkedIn ({res['kind']}): {res['url']}"


HANDLERS = {"golive": go_live, "stop": stop_live, "site": publish_page, "linkedin": publish_linkedin}


def run_approved() -> list[str]:
    with mm.locked():
        s = mm.load()
    todo = [a for a in s["approvals"] if a["status"] == "approved" and not a.get("consumed") and a.get("channel") in HANDLERS]
    out = []
    for ap in todo:
        try:
            msg = HANDLERS[ap["channel"]](ap)
        except RuntimeError as e:  # temporary (missing token, network): keep it queued
            out.append(f"{ap['id']}: in attesa ({e})")
            continue
        except Exception as e:  # permanent: tell the owner and archive it
            msg = f"non eseguibile: {e}"
        mm.main(["log", ap.get("by") or "ceo", f"{ap['id']} {ap['title'][:60]}: {msg}"])
        mm.main(["consume", ap["id"]])
        out.append(f"{ap['id']}: {msg}")
    return out


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] != ["run-approved"]:
        print(__doc__)
        return 2
    try:
        print("\n".join(run_approved()) or "azioni: nessuna azione approvata in coda")
    except Exception as e:  # never break the workflow
        print(f"azioni: errore ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
