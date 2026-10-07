#!/usr/bin/env python3
"""Copertina del prodotto per Polar e per il sito, da dati veri (titolo, contenuto, prezzo) e dalle anteprime vere.

  python3 scripts/cover.py products/<opp_id>/cover.json

cover.json: {"kicker": "...", "title": "...", "subtitle": "...", "badges": ["6 email", "IT + EN"],
             "price": "8 €", "previews": ["01-IT-1.png", "02-IT-2.png"], "accent": "#f5b83d"}
In alto il marchio del negozio (site/_brand/), se c'è.
Scrive products/<opp_id>/media/00-cover.png (1200×1500): il nome con 00 la mette prima delle altre anteprime.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brand_mark  # noqa: E402

FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation", "/Library/Fonts", "C:/Windows/Fonts")
FONTS = {"bold": ("DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "arialbd.ttf"), "regular": ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "arial.ttf")}


def font(kind, size):
    from PIL import ImageFont
    for d in FONT_DIRS:
        for n in FONTS[kind]:
            if os.path.exists(os.path.join(d, n)):
                return ImageFont.truetype(os.path.join(d, n), size)
    return ImageFont.load_default(size)


def hexrgb(c):
    c = c.lstrip("#"); return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def wrap(d, text, f, width):
    out, cur = [], ""
    for w in text.split():
        n = (cur + " " + w).strip()
        if d.textlength(n, font=f) <= width or not cur:
            cur = n
        else:
            out.append(cur); cur = w
    return out + [cur]


def render(spec, media_dir):
    from PIL import Image, ImageDraw, ImageFilter
    W, H = 1200, 1500
    accent = hexrgb(spec.get("accent", "#f5b83d"))
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):  # deep navy gradient
        k = y / H
        d.line([(0, y), (W, y)], fill=(int(14 + 10 * k), int(22 + 8 * k), int(48 + 14 * k)))
    d.rectangle([0, 0, W, 16], fill=accent)
    pad = 90
    y = 110
    if brand_mark.draw(img, pad, 52, 76):  # shop logo + name on top
        y = 176
    d.text((pad, y), spec["kicker"].upper(), font=font("bold", 34), fill=accent); y += 70
    ft = font("bold", 92)
    for line in wrap(d, spec["title"], ft, W - 2 * pad)[:3]:
        d.text((pad, y), line, font=ft, fill=(255, 255, 255)); y += 104
    y += 10
    fs = font("regular", 42)
    for line in wrap(d, spec["subtitle"], fs, W - 2 * pad)[:3]:
        d.text((pad, y), line, font=fs, fill=(200, 210, 230)); y += 56
    y += 28
    fb, x = font("bold", 36), pad
    for b in spec.get("badges", []):
        w = d.textlength(b, font=fb) + 48
        d.rounded_rectangle([x, y, x + w, y + 66], radius=33, outline=accent, width=4)
        d.text((x + 24, y + 13), b, font=fb, fill=(255, 255, 255)); x += w + 18
    y += 110
    # real previews, fanned like sheets of paper, with a soft shadow
    pics = [p for p in (os.path.join(media_dir, n) for n in spec.get("previews", [])) if os.path.exists(p)][:2]
    area_top, area_h = y, H - y - 150
    for i, p in enumerate(pics):
        with Image.open(p) as im:
            im = im.convert("RGB")
            h = int(area_h * .98); w = int(im.width * h / im.height)
            im = im.resize((w, h))
            sh = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
            ImageDraw.Draw(sh).rectangle([30, 30, w + 30, h + 30], fill=(0, 0, 0, 150))
            sh = sh.filter(ImageFilter.GaussianBlur(14))
            sheet = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0)); sheet.alpha_composite(sh); sheet.paste(im, (30, 30))
            angle = (-7, 5)[i] if len(pics) > 1 else -4
            sheet = sheet.rotate(angle, expand=True, resample=Image.BICUBIC)
            cx = W // 2 + ((-150, 150)[i] if len(pics) > 1 else 0)
            img.paste(sheet, (cx - sheet.width // 2, area_top + (area_h - sheet.height) // 2 + 20), sheet)
    d = ImageDraw.Draw(img)
    # price tag
    fp = font("bold", 64); price = spec.get("price", "")
    if price:
        w = d.textlength(price, font=fp) + 70
        d.rounded_rectangle([W - pad - w, H - 230, W - pad, H - 130], radius=24, fill=accent)
        d.text((W - pad - w + 35, H - 220), price, font=fp, fill=(20, 16, 6))
    d.text((pad, H - 70), "Creato con l'aiuto dell'AI", font=font("regular", 26), fill=(150, 160, 185))
    out = os.path.join(media_dir, "00-cover.png")
    img.save(out, optimize=True)
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) != 1:
        print(__doc__); return 2
    with open(argv[0], encoding="utf-8") as f:
        spec = json.load(f)
    print(render(spec, os.path.join(os.path.dirname(os.path.abspath(argv[0])), "media")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
