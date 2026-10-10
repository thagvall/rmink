"""Shareable video pages on the hosted site: /video (English) and /video/sv.

Writes the link-preview images (1200 × 627, for LinkedIn and others), the
posters and the pages into deploy/vercel/public/, and copies the rendered MP4s.

Usage: python promo/make_share.py   (after render.py LANG and render.py LANG --cover)
"""

import html
import shutil

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
OUT = HERE / "out"
PUBLIC = HERE.parent / "deploy" / "vercel" / "public"
DEST = PUBLIC / "promo"
SITE = "https://rmink.vercel.app"
SUPPORT = "https://buy.stripe.com/7sY4gy4b1aQo0iI0SB1sQ00"
SOURCE = "https://github.com/thagvall/rmink"
SANS = "/System/Library/Fonts/HelveticaNeue.ttc"
TEXT = {
    "en": ("Photos and handwriting\nbecome real, editable\nreMarkable ink", "Free · open source · no install",
           "Watch the demo"),
    "sv": ("Foton och handstil blir\nriktigt, redigerbart\nreMarkable-bläck", "Gratis · öppen källkod · ingen installation",
           "Se demon"),
}  # fmt: skip
PAPER, INK, MUTED, BLUE = "#f4f2ec", "#1d1d1b", "#6b6a65", "#2b5fd9"


def font(path: str, size: int, index: int = 0, weight: int | None = None):
    f = ImageFont.truetype(path, size, index=index)
    if weight:
        f.set_variation_by_axes([weight])
    return f


def make(lang: str) -> Path:
    img = Image.new("RGB", (1200, 627), PAPER)
    d = ImageDraw.Draw(img)
    # Video frame on the right with a shadow and a play button.
    cover = Image.open(OUT / f"cover-{lang}.png").convert("RGB").resize((448, 560))
    x0, y0 = 700, 34
    shadow = Image.new("L", (1200, 627), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x0 + 6, y0 + 16, x0 + 454, y0 + 576), 22, fill=110)
    img.paste(Image.new("RGB", img.size, "#000"), mask=shadow.filter(ImageFilter.GaussianBlur(18)))
    mask = Image.new("L", cover.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *cover.size), 20, fill=255)
    img.paste(cover, (x0, y0), mask)
    cx, cy, r = x0 + 224, y0 + 300, 58
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(29, 29, 27))
    d.polygon([(cx - 18, cy - 28), (cx - 18, cy + 28), (cx + 30, cy)], fill="white")

    head, sub, cta = TEXT[lang]
    d.text((68, 34), "rmink", font=font(str(OUT / "assets" / "Caveat.ttf"), 110, weight=700), fill=INK)
    d.multiline_text((72, 182), head, font=font(SANS, 42, index=1), fill=INK, spacing=8)
    d.text((72, 352), sub, font=font(SANS, 25), fill=MUTED)
    bold = font(SANS, 30, index=1)
    d.rounded_rectangle((72, 420, 72 + d.textlength(cta, font=bold) + 98, 486), 33, fill=BLUE)
    d.polygon([(104, 439), (104, 467), (127, 453)], fill="white")
    d.text((142, 436), cta, font=bold, fill="white")
    d.text((72, 540), "rmink.vercel.app/video" + ("/sv" if lang == "sv" else ""), font=font(SANS, 26, index=1), fill=MUTED)
    DEST.mkdir(parents=True, exist_ok=True)
    path = DEST / f"og-{lang}.jpg"
    img.save(path, quality=90)
    return path


PAGE = {
    "en": {
        "path": "/video", "file": "video.html", "other": ("/video/sv", "På svenska"),
        "title": "rmink: photos and handwriting as real reMarkable ink",
        "desc": "A 90-second demo: drop a photo, download the notebook, copy it to your "
                "reMarkable, then erase, move and draw on it like your own pen strokes. Free and open source.",
        "h1": "Your handwritten notes, as real reMarkable ink",
        "lead": "Drop a photo of notes, a sketch, a portrait or a PDF. rmink traces it into native pen "
                "strokes that you can erase, lasso, move and draw on, on your tablet.",
        "try": "Try it free", "code": "Source code", "support": "Support it with 100 kr ♥",
        "note": "rmink is an independent hobby project, not affiliated with reMarkable AS.",
    },
    "sv": {
        "path": "/video/sv", "file": "video-sv.html", "other": ("/video", "In English"),
        "title": "rmink: foton och handstil som riktigt reMarkable-bläck",
        "desc": "En 90 sekunder lång demo: släpp in ett foto, ladda ner anteckningsboken, lägg över den till "
                "din reMarkable och sudda, flytta och rita som med din egen penna. Gratis och öppen källkod.",
        "h1": "Dina handskrivna anteckningar, som riktigt reMarkable-bläck",
        "lead": "Släpp in ett foto av anteckningar, en skiss, ett porträtt eller en PDF. rmink spårar om det "
                "till riktiga pennstreck som du kan sudda, lassa, flytta och rita vidare på i plattan.",
        "try": "Prova gratis", "code": "Källkod", "support": "Stöd med 100 kr ♥",
        "note": "rmink är ett fristående hobbyprojekt utan koppling till reMarkable AS.",
    },
}  # fmt: skip

TEMPLATE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{site}{path}">
<meta property="og:type" content="video.other">
<meta property="og:site_name" content="rmink">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{site}{path}">
<meta property="og:image" content="{site}/promo/og-{lang}.jpg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="627">
<meta property="og:video" content="{site}/promo/rmink-promo-{lang}.mp4">
<meta property="og:video:type" content="video/mp4">
<meta property="og:video:width" content="1080">
<meta property="og:video:height" content="1350">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{site}/promo/og-{lang}.jpg">
<style>
:root {{ --paper: #f4f2ec; --ink: #1d1d1b; --muted: #6b6a65; --accent: #2b5fd9; --line: #dcd8cd; --heart: #d0406a; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; background: var(--paper); color: var(--ink);
  font: 17px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
main {{ max-width: 980px; margin: 0 auto; padding: 32px 16px 48px; display: grid; gap: 36px;
  grid-template-columns: minmax(0, 1fr) minmax(0, 420px); align-items: center; }}
.brand {{ font-weight: 800; font-size: 22px; letter-spacing: -.02em; color: var(--ink); text-decoration: none; }}
h1 {{ font-size: clamp(30px, 4.4vw, 46px); line-height: 1.1; letter-spacing: -.02em; margin: 14px 0 16px; }}
p.lead {{ color: var(--muted); font-size: 19px; margin: 0 0 26px; }}
.btns {{ display: flex; flex-wrap: wrap; gap: 12px; }}
.btn {{ display: inline-block; padding: 13px 22px; border-radius: 999px; font-weight: 700; text-decoration: none; }}
.primary {{ background: var(--accent); color: #fff; }}
.ghost {{ border: 1.5px solid var(--line); color: var(--ink); background: #fff; }}
.heart {{ color: var(--heart); }}
video {{ width: 100%; aspect-ratio: 4 / 5; border-radius: 18px; background: #000; display: block;
  box-shadow: 0 24px 60px rgb(0 0 0 / .2); }}
.meta {{ margin-top: 26px; font-size: 14px; color: var(--muted); }}
.meta a {{ color: var(--muted); }}
@media (max-width: 760px) {{ main {{ grid-template-columns: 1fr; gap: 24px; padding-top: 20px; }} .video {{ order: -1; }} }}
</style>
</head>
<body>
<main>
  <div>
    <a class="brand" href="/">rmink</a>
    <h1>{h1}</h1>
    <p class="lead">{lead}</p>
    <div class="btns">
      <a class="btn primary" href="/">{try_}</a>
      <a class="btn ghost" href="{source}">{code}</a>
      <a class="btn ghost" href="{support_url}">{support}</a>
    </div>
    <p class="meta"><a href="{other_path}">{other_label}</a> · {note}</p>
  </div>
  <div class="video">
    <video controls playsinline preload="metadata" poster="/promo/poster-{lang}.jpg">
      <source src="/promo/rmink-promo-{lang}.mp4" type="video/mp4">
    </video>
  </div>
</main>
</body>
</html>
"""


def page(lang: str) -> Path:
    t = {k: html.escape(v) if isinstance(v, str) else v for k, v in PAGE[lang].items()}
    out = TEMPLATE.format(
        lang=lang, site=SITE, path=t["path"], title=t["title"], desc=t["desc"], h1=t["h1"],
        lead=t["lead"], try_=t["try"], code=t["code"], support=t["support"].replace("♥", '<span class="heart">♥</span>'),
        source=SOURCE, support_url=SUPPORT, other_path=t["other"][0], other_label=t["other"][1], note=t["note"],
    )  # fmt: skip
    path = PUBLIC / t["file"]
    path.write_text(out)
    return path


if __name__ == "__main__":
    for lang in TEXT:
        shutil.copy(OUT / f"rmink-promo-{lang}.mp4", DEST / f"rmink-promo-{lang}.mp4")
        Image.open(OUT / f"cover-{lang}.png").convert("RGB").save(DEST / f"poster-{lang}.jpg", quality=88)
        print(make(lang), page(lang))
