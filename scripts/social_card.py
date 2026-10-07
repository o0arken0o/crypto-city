#!/usr/bin/env python3
"""Immagini pronte per i social (post singolo o carosello) dai dati veri del prodotto. Niente mockup inventati.

  python3 scripts/social_card.py products/<opp_id>/social/<YYYY-MM-DD>-<piattaforma>/cards.json

cards.json (scritto dal visual-designer accanto a POST.md):
  {"format": "portrait",            # portrait 1080×1350 (Instagram/Facebook/LinkedIn), square 1080×1080, story 1080×1920 (TikTok/Reel/Storie)
   "accent": "#f5b83d",             # colore del marchio (facoltativo)
   "slides": [
     {"kicker": "FREELANCE", "title": "Chi ti deve ancora pagare?", "text": "Una frase breve.",
      "image": "products/<opp_id>/media/01-….png"},   # facoltativa: SOLO anteprime vere in products/<id>/media/
     {"title": "…", "bullets": ["…", "…"]}
   ],
   "footer": "Creato con l'aiuto dell'AI"}
Scrive slide-01.png, slide-02.png, … nella stessa cartella e, se le slide sono più di una, anche carosello.pdf
(LinkedIn carica i caroselli come documento PDF).
In basso a sinistra di ogni slide c'è il marchio del negozio (site/_brand/), se c'è. Stampa i file creati. Richiede Pillow.
"""
from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand_mark  # noqa: E402

SIZES = {"portrait": (1080, 1350), "square": (1080, 1080), "story": (1080, 1920)}
MAX_SLIDES = 10
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation", "/Library/Fonts", "C:/Windows/Fonts")
FONTS = {"bold": ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"),
         "regular": ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf", "Arial.ttf")}


def _font(kind: str, size: int):
    from PIL import ImageFont
    for d in FONT_DIRS:
        for name in FONTS[kind]:
            p = os.path.join(d, name)
            if os.path.exists(p):
                return ImageFont.truetype(p, size)
    return ImageFont.load_default(size)


def _hex(c: str, default=(245, 184, 61)) -> tuple:
    m = re.fullmatch(r"#?([0-9a-fA-F]{6})", str(c or ""))
    return tuple(int(m.group(1)[i:i + 2], 16) for i in (0, 2, 4)) if m else default


def _wrap(draw, text: str, font, width: int) -> list[str]:
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for w in para.split():
            nxt = (cur + " " + w).strip()
            if draw.textlength(nxt, font=font) <= width or not cur:
                cur = nxt
            else:
                lines.append(cur); cur = w
        lines.append(cur)
    return lines


def _safe_image(path: str, root: str) -> str | None:
    """Only real product previews: files under products/<id>/media/ of this repo."""
    if not path:
        return None
    full = os.path.realpath(os.path.join(root, path))
    if not re.search(r"[/\\]products[/\\][^/\\]+[/\\]media[/\\][^/\\]+\.(png|jpe?g)$", full, re.I):
        return None
    if not full.startswith(os.path.realpath(os.path.join(root, "products")) + os.sep) or not os.path.isfile(full):
        return None
    return full


def render(spec: dict, out_dir: str, root: str = ROOT) -> list[str]:
    from PIL import Image, ImageDraw
    W, H = SIZES.get(spec.get("format"), SIZES["portrait"])
    accent = _hex(spec.get("accent"))
    footer = str(spec.get("footer") or "Creato con l'aiuto dell'AI")[:60]
    slides = [s for s in spec.get("slides") or [] if isinstance(s, dict)][:MAX_SLIDES]
    if not slides:
        raise ValueError("nessuna slide")
    pad, files = 84, []
    for i, sl in enumerate(slides, 1):
        img = Image.new("RGB", (W, H), (12, 16, 28))
        d = ImageDraw.Draw(img)
        for y in range(H):  # soft vertical gradient
            k = y / H
            d.line([(0, y), (W, y)], fill=(int(12 + 14 * k), int(16 + 10 * k), int(28 + 22 * k)))
        d.rectangle([0, 0, W, 14], fill=accent)
        brand_mark.draw(img, pad, H - pad - 140, 56)  # shop logo + name, above the footer
        pic = _safe_image(sl.get("image"), root)
        ops, y = [], 0  # layout first (relative y), then draw: text-only slides are centred vertically
        if sl.get("kicker"):
            f = _font("bold", 34); ops.append(("t", y, pad, str(sl["kicker"]).upper()[:40], f, accent)); y += 60
        if sl.get("title"):
            f = _font("bold", 76 if len(str(sl["title"])) < 40 else 62)
            for ln in _wrap(d, str(sl["title"])[:120], f, W - 2 * pad)[:4]:
                ops.append(("t", y, pad, ln, f, (255, 255, 255))); y += int(f.size * 1.18)
            y += 24
        if sl.get("text"):
            f = _font("regular", 40)
            for ln in _wrap(d, str(sl["text"])[:300], f, W - 2 * pad)[:6]:
                ops.append(("t", y, pad, ln, f, (210, 218, 232))); y += int(f.size * 1.35)
            y += 20
        for b in [str(x)[:90] for x in sl.get("bullets") or []][:6]:
            f = _font("regular", 40); ops.append(("dot", y, pad))
            for ln in _wrap(d, b, f, W - 2 * pad - 40)[:2]:
                ops.append(("t", y, pad + 40, ln, f, (230, 235, 245))); y += int(f.size * 1.3)
            y += 14
        top, bottom = pad + 20, H - pad - 160
        if not pic:
            top = max(top, (top + bottom - y) // 2)
        for op in ops:
            if op[0] == "t":
                d.text((op[2], top + op[1]), op[3], font=op[4], fill=op[5])
            else:
                d.ellipse([op[2], top + op[1] + 16, op[2] + 16, top + op[1] + 32], fill=accent)
        y = top + y
        if pic and bottom - y > 200:
            with Image.open(pic) as p:
                p = p.convert("RGB"); p.thumbnail((W - 2 * pad, bottom - y - 20))
                x0, y0 = (W - p.width) // 2, y + (bottom - y - p.height) // 2
                d.rounded_rectangle([x0 - 10, y0 - 10, x0 + p.width + 10, y0 + p.height + 10], radius=18, fill=(255, 255, 255))
                img.paste(p, (x0, y0))
        f = _font("regular", 28)
        d.text((pad, H - pad), footer, font=f, fill=(150, 160, 180))
        if len(slides) > 1:
            n = f"{i}/{len(slides)}"
            d.text((W - pad - d.textlength(n, font=f), H - pad), n, font=f, fill=(150, 160, 180))
        path = os.path.join(out_dir, f"slide-{i:02d}.png")
        img.save(path, optimize=True)
        files.append(path)
    if len(files) > 1:  # carousel as one PDF document (LinkedIn)
        pages = [Image.open(f).convert("RGB") for f in files]
        pdf = os.path.join(out_dir, "carosello.pdf")
        pages[0].save(pdf, save_all=True, append_images=pages[1:], resolution=144)
        for pg in pages:
            pg.close()
        files.append(pdf)
    return files


def main(argv=None) -> int:
    argv = argv or sys.argv[1:]
    if len(argv) != 1 or not argv[0].endswith("cards.json"):
        print(__doc__); return 2
    spec_path = os.path.realpath(argv[0])
    if not re.search(r"[/\\]products[/\\][^/\\]+[/\\]social[/\\][^/\\]+[/\\]cards\.json$", spec_path):
        print("cards.json deve stare in products/<id>/social/<data>-<piattaforma>/"); return 2
    try:
        with open(spec_path, encoding="utf-8") as f:
            spec = json.load(f)
        files = render(spec, os.path.dirname(spec_path))
    except (OSError, ValueError) as e:
        print(f"errore: {e}"); return 1
    except ImportError:
        print("serve Pillow: python3 -m pip install pillow"); return 1
    print("\n".join(os.path.relpath(p, ROOT) for p in files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
