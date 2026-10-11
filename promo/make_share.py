"""Shareable video links on the hosted site: /video (English) and /video/sv.

The pages carry the link-preview tags and send visitors on to the app with the
demo video open (/?demo=en, /?demo=sv).

Usage:
  python promo/make_share.py           # copy MP4s + posters, write the pages (deploy/vercel/public)
  python promo/make_share.py --shots   # after deploying: share images (1200 × 627) taken from
                                       # the live site with the video open
"""

import hashlib
import html
import io
import shutil
from pathlib import Path

from PIL import Image

HERE = Path(__file__).parent
OUT = HERE / "out"
PUBLIC = HERE.parent / "deploy" / "vercel" / "public"
DEST = PUBLIC / "promo"
SITE = "https://rmink.vercel.app"
PAGE = {
    "en": {
        "path": "/video", "file": "video.html",
        "title": "rmink: photos and handwriting as real reMarkable ink",
        "desc": "A 100-second demo: drop a photo, download the notebook, copy it to your "
                "reMarkable, then erase, move and draw on it like your own pen strokes. Free and open source.",
        "h1": "Your handwritten notes, as real reMarkable ink",
    },
    "sv": {
        "path": "/video/sv", "file": "video-sv.html",
        "title": "rmink: foton och handstil som riktigt reMarkable-bläck",
        "desc": "En 100 sekunder lång demo: släpp in ett foto, ladda ner anteckningsboken, lägg över den till "
                "din reMarkable och sudda, flytta och rita som med din egen penna. Gratis och öppen källkod.",
        "h1": "Dina handskrivna anteckningar, som riktigt reMarkable-bläck",
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
<meta property="og:type" content="website">
<meta property="og:site_name" content="rmink">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{site}{path}">
<meta property="og:image" content="{site}/promo/{image}">
<meta property="og:image:secure_url" content="{site}/promo/{image}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="627">
<meta property="og:image:alt" content="{h1}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{site}/promo/{image}">
<script>location.replace("/?demo={lang}");</script>
<style>body {{ margin: 0; background: #f4f2ec; color: #1d1d1b; font: 17px/1.5 system-ui, sans-serif; padding: 32px 16px; }}</style>
</head>
<body>
<!-- Link previews read the tags above; people go on to the app with the video open. -->
<p><a href="/?demo={lang}">{h1}</a></p>
</body>
</html>
"""


def page(lang: str) -> Path:
    t = {k: html.escape(v) if isinstance(v, str) else v for k, v in PAGE[lang].items()}
    # The newest share image; its name carries a content hash so that LinkedIn
    # fetches it instead of a cached one.
    shots = sorted(DEST.glob(f"og-{lang}-*.jpg"), key=lambda f: f.stat().st_mtime)
    image = shots[-1].name if shots else f"og-{lang}.jpg"
    out = TEMPLATE.format(lang=lang, site=SITE, path=t["path"], title=t["title"], desc=t["desc"],
                          h1=t["h1"], image=image)  # fmt: skip
    path = PUBLIC / t["file"]
    path.write_text(out)
    return path


# Frame of the video shown in the share image (the portrait in every shading style).
SHOT_AT = 62.5
PLAY_OVERLAY = """
  const v = document.querySelector('#demo video');
  v.pause(); v.muted = true; v.removeAttribute('controls'); v.preload = 'auto';
  await new Promise(r => { if (v.readyState >= 1) r(); else v.addEventListener('loadedmetadata', r, {once: true}); });
  v.currentTime = %s;
  await new Promise(r => v.addEventListener('seeked', r, {once: true}));
  v.pause();
  document.activeElement.blur();
  const play = document.createElement('div');
  play.innerHTML = '<svg viewBox="0 0 100 100" width="120" height="120"><circle cx="50" cy="50" r="48" fill="rgba(29,29,27,.82)"/><path d="M40 30 L72 50 L40 70 Z" fill="#fff"/></svg>';
  const r = v.getBoundingClientRect();
  Object.assign(play.style, { position: 'fixed', left: (r.left + r.width / 2 - 60) + 'px', top: (r.top + r.height / 2 - 60) + 'px', zIndex: 99 });
  v.closest('dialog').appendChild(play);
"""


def site_shot(lang: str, dest: Path) -> Path:
    """The live app with the demo dialog open, as a 1200 × 627 share image."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 836}, device_scale_factor=0.75)
        page.goto(f"{SITE}/?demo={lang}")
        page.wait_for_selector("#demo[open]")
        page.evaluate("async () => {" + PLAY_OVERLAY % SHOT_AT + "}")
        page.wait_for_timeout(800)
        png = page.screenshot()
        browser.close()
    Image.open(io.BytesIO(png)).convert("RGB").save(dest, quality=90)
    return dest


if __name__ == "__main__":
    import sys

    if "--shots" not in sys.argv:
        DEST.mkdir(parents=True, exist_ok=True)
        for lang in PAGE:
            shutil.copy(OUT / f"rmink-promo-{lang}.mp4", DEST / f"rmink-promo-{lang}.mp4")
            Image.open(OUT / f"cover-{lang}.png").convert("RGB").save(DEST / f"poster-{lang}.jpg", quality=88)
            print(page(lang))
    else:
        # Share images: the live site with the video open, so run this after the
        # videos are deployed. public/og.jpg overrides the app's own /og.jpg.
        print(site_shot("en", PUBLIC / "og.jpg"))
        shutil.copy(PUBLIC / "og.jpg", HERE.parent / "src" / "rmink" / "web" / "static" / "og.jpg")
        for lang in PAGE:
            for old in DEST.glob(f"og-{lang}*.jpg"):
                old.unlink()
            tmp = site_shot(lang, DEST / f"og-{lang}.jpg")
            named = DEST / f"og-{lang}-{hashlib.sha1(tmp.read_bytes()).hexdigest()[:8]}.jpg"
            tmp.rename(named)
            print(named, page(lang))
