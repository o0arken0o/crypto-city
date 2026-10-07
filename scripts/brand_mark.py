"""Il marchio del negozio (site/_brand/brand.json) disegnato con Pillow su copertine e immagini social.

Il logo è lo stesso di site/_brand/logo.svg (grafico in salita), ridisegnato qui perché Pillow non legge
gli SVG. Senza brand.json non disegna nulla: le immagini restano come prima.
"""
from __future__ import annotations

import json
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BRAND = os.path.join(ROOT, "site", "_brand", "brand.json")


def _hex(c, default):
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(c or ""))
    return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if m else default


def load(path: str = BRAND) -> dict | None:
    try:
        with open(path, encoding="utf-8") as f:
            b = json.load(f)
    except (OSError, ValueError):
        return None
    name = b.get("name")
    parts = [str(p)[:20] for p in name] if isinstance(name, list) else [str(name or "")[:40]]
    if not "".join(parts).strip():
        return None
    return {"name": parts[:2], "color": _hex(b.get("color"), (15, 118, 110)), "light": _hex(b.get("color_light"), (94, 234, 212))}


def logo(size: int, brand: dict):
    """Il logo come immagine RGBA size×size (disegnato 4 volte più grande e ridotto, per bordi morbidi)."""
    from PIL import Image, ImageDraw
    from cover import font  # same font lookup as the covers
    k = 4
    S = size * k
    u = S / 72  # the SVG is drawn on a 72×72 grid
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([2 * u, 2 * u, 70 * u, 70 * u], fill=brand["color"])
    w = round(6 * u)
    gold = brand.get("light") or (247, 183, 49)
    pts = [(16, 48), (28, 36), (36, 43), (54, 24)]
    d.line([(x * u, y * u) for x, y in pts], fill=gold, width=w, joint="curve")
    d.line([(46 * u, 24 * u), (55 * u, 24 * u), (55 * u, 33 * u)], fill=gold, width=w, joint="curve")
    for x, y in pts + [(46, 24), (55, 33)]:
        d.ellipse([x * u - w / 2, y * u - w / 2, x * u + w / 2, y * u + w / 2], fill=gold)
    d.line([(16 * u, 56 * u), (56 * u, 56 * u)], fill=(200, 210, 225), width=round(4 * u))
    return im.resize((size, size), Image.LANCZOS)


def draw(img, x: int, y: int, size: int, brand: dict | None = None) -> int:
    """Logo + nome su sfondo scuro, con l'angolo in alto a sinistra in (x, y). Ritorna la larghezza usata (0 se niente)."""
    from PIL import ImageDraw
    from cover import font
    brand = brand if brand is not None else load()
    if not brand:
        return 0
    lg = logo(size, brand)
    img.paste(lg, (x, y), lg)
    d = ImageDraw.Draw(img)
    f = font("bold", round(size * .5))
    tx = x + size + round(size * .28)
    ty = y + size // 2
    colors = [(255, 255, 255), brand["light"]]
    for i, part in enumerate(brand["name"]):
        d.text((tx, ty), part, font=f, fill=colors[i % 2], anchor="lm")
        tx += round(d.textlength(part, font=f))
    return tx - x
