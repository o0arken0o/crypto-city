#!/usr/bin/env python3
"""Avvisi sul telefono via Telegram: un solo messaggio per ciclo, e solo se c'è qualcosa di nuovo.

  📈 SEGNALI delle strategie live approvate (compra/vendi: li esegui tu, se sei d'accordo)
  💰 risultati reali nuovi (dal registro, li registri tu)
  🔔 approvazioni o blocchi "tocca a te" comparsi dopo l'ultimo avviso
  📣 il resoconto del team, ⏸ ciclo saltato, ⚠️ ciclo finito con errore
  🛒 clic nuovi su "Compra" e 👀 visite nuove arrivate da un social (dal conteggio anonimo del sito)

Cosa è già stato avvisato resta nello stato (mm notified), così niente si ripete. Al primo avvio manda
solo un messaggio di benvenuto con il riepilogo di cosa aspetta già, senza riversare tutto lo storico.

  python3 scripts/telegram.py            # nei workflow, prima del commit dello stato
  python3 scripts/telegram.py --dry-run  # stampa il messaggio senza inviarlo

Env: TELEGRAM_BOT_TOKEN (dal BotFather; senza, non fa nulla), TELEGRAM_CHAT_ID (facoltativo: se manca lo
ricava da chi ha scritto /start al bot e lo ricorda), MM_SITE_URL (link alla plancia, facoltativo).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "engine"))
import mm  # noqa: E402

TEAM = {"rendite": "Team rendite", "social": "Team social"}
SOCIAL = {"linkedin.com": "LinkedIn", "lnkd.in": "LinkedIn", "facebook.com": "Facebook", "fb.com": "Facebook",
          "instagram.com": "Instagram", "tiktok.com": "TikTok", "reddit.com": "Reddit", "t.co": "X", "x.com": "X",
          "twitter.com": "X", "youtube.com": "YouTube", "pinterest.com": "Pinterest", "threads.net": "Threads"}
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")


def social_name(host: str) -> str:
    h = str(host or "").lower()
    return next((n for d, n in SOCIAL.items() if h == d or h.endswith("." + d)), "")


def page_name(slug: str) -> str:
    import html
    import re
    try:
        with open(os.path.join(ROOT, "site", slug, "public", "index.html"), encoding="utf-8") as f:
            m = re.search(r"<title>(.*?)</title>", f.read(), re.S | re.I)
        return html.unescape(m.group(1)).strip()[:70] if m else slug
    except OSError:
        return slug


def traffic_counts(s: dict) -> tuple[dict, dict]:
    """Running totals from the site's anonymous counts: buy clicks per page, visits per page and social site.
    Keys include the server's boot id, so a restart of the site never makes a count go down."""
    since = (__import__("datetime").date.today() - __import__("datetime").timedelta(days=14)).isoformat()
    clicks, social = {}, {}
    for boot, b in ((s.get("traffic") or {}).get("boots") or {}).items():
        for k, v in (b.get("counts") or {}).items():
            day, page = k.split("|", 1)
            if day < since:
                continue
            if v.get("c"):
                clicks[f"{boot}|{k}"] = v["c"]
            for host, n in (v.get("r") or {}).items():
                if social_name(host):
                    social[f"{boot}|{k}|{host}"] = n
    return clicks, social


def traffic_lines(s: dict, memo: dict) -> list[str]:
    """What is new since the last message: buy clicks and visits from social networks."""
    clicks, social = traffic_counts(s)
    if memo is None:  # first time: remember, do not announce the past
        return []
    out = []
    new_clicks = {}
    for k, n in clicks.items():
        d = n - (memo.get("clicks") or {}).get(k, 0)
        if d > 0:
            page = k.split("|")[2]; new_clicks[page] = new_clicks.get(page, 0) + d
    for page, d in new_clicks.items():
        out.append(f"🛒 {d} {'clic' if d == 1 else 'clic'} su Compra: {page_name(page)}")
    seen_before = {social_name(k.split("|")[3]) for k in (memo.get("social") or {})}
    new_social = {}
    for k, n in social.items():
        d = n - (memo.get("social") or {}).get(k, 0)
        if d > 0:
            src = social_name(k.split("|")[3]); new_social[src] = new_social.get(src, 0) + d
    for src, d in new_social.items():
        first = "" if src in seen_before else " (la prima!)"
        out.append(f"👀 {d} {'visita' if d == 1 else 'visite'} da {src}{first}")
    return out


def _week_id() -> str:
    y, w, _ = __import__("datetime").date.today().isocalendar()
    return f"{y}-W{w:02d}"


def weekly_text(s: dict) -> str:
    """The week in a few lines (same numbers as the panel's "La settimana")."""
    w = mm.weekly(s)
    lines = [f"📊 La tua settimana ({w['from'][8:10]}/{w['from'][5:7]} – {w['to'][8:10]}/{w['to'][5:7]})",
             f"💰 Risultati reali registrati: {_eur(w['revenue_eur'])} ({w['sales']} voci) · settimana prima {_eur(w['prev_revenue_eur'])}",
             f"⚡ Spesa AI: ${w['ai_usd']:.2f} · {w['cycles']} cicli" + (f", {w['skipped']} saltati" if w["skipped"] else "")]
    if w["published"]:
        lines.append(f"🌐 Online: {len(w['published'])} novità")
    if w["next"]:
        lines.append(f"🎯 Prossima mossa: {w['next']}")
    if w["needs_you"]:
        lines.append(f"🔔 Ti aspettano {w['needs_you']} cose in plancia")
    return "\n".join(lines)


def _eur(v) -> str:
    return f"{float(v or 0):.2f} €".replace(".", ",")


def human_items(s: dict) -> list[tuple[str, str]]:
    """(id, testo) di cosa aspetta il proprietario."""
    out = [(a["id"], f"approva o rifiuta: {a['title']}") for a in s.get("approvals", []) if a.get("status") == "pending"]
    out += [(b["id"], f"tocca a te: {b['title']}") for b in s.get("blockers", [])
            if b.get("status") == "open" and b.get("owner") != "agent"]
    return out


def compose(s: dict, panel: str = "") -> tuple[str, dict]:
    """Il testo da inviare ('' se non c'è niente di nuovo) e il nuovo promemoria di cosa è stato avvisato."""
    t = (s.get("notify") or {}).get("telegram") or {}
    first = not t.get("ts")
    since, sent = t.get("ts") or "", set(t.get("sent") or [])
    sales = [e for e in s.get("ledger", []) if e.get("type") == "revenue"]
    todo = human_items(s)
    lines = []
    trafficmemo = t.get("traffic") if "traffic" in t else None
    if first:
        lines.append("✅ Avvisi di Crypto Machine attivi: ti scrivo i segnali delle strategie che approvi, quando serve "
                     "una tua decisione e quando un ciclo viene saltato o fallisce. Nessun ordine parte da solo.")
        if todo:
            lines.append(f"\n🔔 In questo momento aspettano te {len(todo)} cose:")
            lines += [f"• {txt}" for _, txt in todo[:6]]
    else:
        for g in [x for x in s.get("signals", []) if x.get("id") and x["id"] not in sent][-5:]:
            lines.append(f"📈 SEGNALE {g['text']}")
        new_sales = [e for e in sales if e.get("id") and e["id"] not in sent]
        for e in new_sales[:5]:
            src = f" ({e['source']})" if e.get("source") else ""
            lines.append(f"💰 Risultato registrato: {_eur(e.get('amount_eur'))}{src}")
        if new_sales:
            lines.append(f"Totale guadagni registrati: {_eur(sum(e.get('amount_eur', 0) for e in sales))}")
        fresh = [(i, txt) for i, txt in todo if i not in sent]
        if fresh:
            lines.append(f"\n🔔 Nuove cose per te ({len(fresh)}):")
            lines += [f"• {txt}" for _, txt in fresh[:6]]
        reps = [r for r in s.get("reports", []) if str(r.get("ts", "")) > since]
        if reps:
            r = reps[-1]
            lines.append(f"\n📣 {TEAM.get(r.get('team'), 'Team trading')}, ciclo #{r.get('cycle')}: {r.get('headline', '')}")
        sk = s.get("last_skip") or {}
        if str(sk.get("ts", "")) > since and not reps:
            lines.append(f"\n⏸ Ciclo saltato: {sk.get('reason', '')}")
        tl = traffic_lines(s, trafficmemo)
        if tl:
            lines.append("")
            lines += tl
        errs = [l for l in s.get("log", []) if l.get("agent") == "engine" and "errore" in l.get("msg", "")
                and str(l.get("ts", "")) > since]
        if errs:
            lines.append(f"\n⚠️ {errs[-1]['msg']}")
    week = _week_id()
    if not first and t.get("week") != week:  # first message of a new week: the weekly summary
        lines.append("\n" + weekly_text(s))
    clicks, social = traffic_counts(s)
    sigs = {x["id"] for x in s.get("signals", []) if x.get("id")}
    memo = {"ts": mm.now(), "week": week, "sent": sorted({e["id"] for e in sales if e.get("id")} | {i for i, _ in todo} | sigs | sent)[-300:],
            "traffic": {"clicks": clicks, "social": social}}
    if not lines:
        return "", memo
    if panel and (first or any(l.startswith(("\n🔔", "🔔")) for l in lines)):
        lines.append(f"\nApri la plancia: {panel}")
    return "\n".join(lines)[:3900], memo


class Telegram:
    def __init__(self, token: str, opener=None):
        self.base = f"https://api.telegram.org/bot{token}"
        self.open = opener or urllib.request.urlopen

    def call(self, method: str, params: dict | None = None) -> dict:
        data = urllib.parse.urlencode(params or {}).encode()
        with self.open(urllib.request.Request(f"{self.base}/{method}", data=data), timeout=20) as r:
            return json.loads(r.read() or b"{}")

    def find_chat(self) -> str:
        """La chat privata più recente che ha scritto al bot (basta mandargli /start)."""
        ups = self.call("getUpdates").get("result") or []
        for u in reversed(ups):
            chat = (u.get("message") or {}).get("chat") or {}
            if chat.get("type") == "private" and chat.get("id"):
                return str(chat["id"])
        return ""


def main(argv=None, tg: Telegram | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    with mm.locked():
        s = mm.load()
    panel = os.environ.get("MM_SITE_URL", "").strip().rstrip("/")
    text, memo = compose(s, panel + "/plancia" if panel else "")
    if "--dry-run" in argv:
        print(text or "telegram: niente di nuovo")
        return 0
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token and tg is None:
        print("telegram: TELEGRAM_BOT_TOKEN non impostato, saltato")
        return 0
    try:  # un avviso mancato non deve mai far fallire il ciclo
        tg = tg or Telegram(token)
        chat = os.environ.get("TELEGRAM_CHAT_ID", "").strip() or ((s.get("notify") or {}).get("telegram") or {}).get("chat_id") or tg.find_chat()
        if not chat:
            print("telegram: nessuna chat trovata: apri il tuo bot su Telegram e scrivigli /start")
            return 0
        memo["chat_id"] = chat
        if text:
            tg.call("sendMessage", {"chat_id": chat, "text": text, "disable_web_page_preview": "true"})
        mm.main(["notified", json.dumps(memo)])
        print("telegram: inviato" if text else "telegram: niente di nuovo")
    except Exception as e:
        print(f"telegram: errore, saltato ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
