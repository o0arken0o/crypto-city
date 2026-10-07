#!/usr/bin/env python3
"""Immagine di anteprima (1200×630) per quando un link del sito viene condiviso su Facebook, LinkedIn, WhatsApp.

  python3 scripts/share_card.py            # tutte le guide in site/<slug>/public/ + quella generale del sito
  python3 scripts/share_card.py <slug>     # solo una pagina

Scrive site/<slug>/public/share.png (titolo della pagina, marchio del negozio) e site/_brand/share.png (per la home).
Le pagine prodotto non ne hanno bisogno: usano la copertina vera del prodotto. Richiede Pillow.
"""
from __future__ import annotations

import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand_mark  # noqa: E402
from cover import font, wrap  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE = os.path.join(ROOT, "site")
W, H = 1200, 630


def render(title: str, kicker: str, out: str) -> str:
    from PIL import Image, ImageDraw
    b = brand_mark.load()
    accent = b["light"] if b else (94, 234, 212)
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):  # same navy as the covers
        k = y / H
        d.line([(0, y), (W, y)], fill=(int(14 + 10 * k), int(22 + 8 * k), int(48 + 14 * k)))
    d.rectangle([0, 0, W, 12], fill=accent)
    pad = 72
    brand_mark.draw(img, pad, 52, 70, b)
    d = ImageDraw.Draw(img)
    d.text((pad, 168), kicker.upper(), font=font("bold", 30), fill=accent)
    size = 68
    while size > 44:  # the biggest font that fits in 4 lines
        ft = font("bold", size)
        lines = wrap(d, title, ft, W - 2 * pad)
        if len(lines) <= 4:
            break
        size -= 6
    y = 220
    for ln in lines[:4]:
        d.text((pad, y), ln, font=ft, fill=(255, 255, 255)); y += int(size * 1.18)
    d.text((pad, H - 62), "Creato con l'aiuto dell'AI", font=font("regular", 24), fill=(150, 160, 185))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    img.save(out, optimize=True)
    return out


def page_title(slug: str) -> str:
    try:
        with open(os.path.join(SITE, slug, "public", "index.html"), encoding="utf-8") as f:
            m = re.search(r"<title>(.*?)</title>", f.read(), re.S | re.I)
    except OSError:
        return ""
    return html.unescape(m.group(1)).strip() if m else ""


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    slugs = argv or sorted(s for s in os.listdir(SITE) if not s.startswith(("_", "opp_")) and s != "contatti" and os.path.isdir(os.path.join(SITE, s, "public")))
    for s in slugs:
        t = page_title(s)
        if t:
            print(render(t, "Guida gratuita · non è un consiglio finanziario", os.path.join(SITE, s, "public", "share.png")))
    if not argv:
        print(render("Strategie crypto testate in pubblico, con numeri veri.", "Backtest e paper trading · niente promesse",
                     os.path.join(SITE, "_brand", "share.png")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
