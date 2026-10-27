"""The sketch-to-drawing entry on the hosted site, next to the image-to-ink app.

Pages (static files in deploy/vercel/public, routed in vercel.json):
  /sketch, /sketch/sv (also /skiss)   the interactive demo, with "Watch the video"
  /sketch?demo, /sketch/sv?demo=sv    the same with the 4:5 video open in a dialog
  /sketch/video, /sketch/video/sv     share links: link-preview tags for LinkedIn
                                      and other sites, then on to the page with
                                      the video open

The app's own start page is not touched.

Usage (from the repo root, after building promo/sketch-demo and rendering the
videos with render.py):
  python promo/sketch-video/make_site.py           # pages, videos, posters
  python promo/sketch-video/make_site.py --shots   # share images from the built
                                                   # pages, then the pages again
"""

import functools
import hashlib
import html
import http.server
import io
import shutil
import sys
import threading
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
PROMO = HERE.parent
DEMO = PROMO / "sketch-demo"
OUT = PROMO / "out"
PUBLIC = PROMO.parent / "deploy" / "vercel" / "public"
MEDIA = PUBLIC / "promo" / "sketch"
SITE = "https://rmink.vercel.app"

PAGES = {
    "en": {
        "file": "sketch.html", "path": "/sketch", "template": "template-en.html",
        "title": "rmink: from hand sketch to clean drawing",
        "desc": "Sketch a 2D drawing on your reMarkable, get a clean drawing back and mark it up in rounds. "
                "An interactive demo and a 2.5-minute video. Free and open source.",
        "share_file": "sketch-video.html", "share_path": "/sketch/video",
        "share_title": "rmink: from hand sketch to clean drawing (video)",
        "share_desc": "A 2.5-minute video: a hand sketch on a reMarkable becomes a clean drawing, gets marked "
                      "up in rounds, split into variants and detail views, and exported. Free and open source.",
        "app": "Image to ink", "watch": "Watch the video", "other": "Svenska", "other_href": "/sketch/sv",
        "videos": "Videos", "tall": "4:5 for phones and feeds", "wide": "16:9 for screens and meetings",
        "close": "Close", "lang_label": "Language",
    },
    "sv": {
        "file": "sketch-sv.html", "path": "/sketch/sv", "template": "template.html",
        "title": "rmink: från handskiss till ren ritning",
        "desc": "Skissa en 2D-ritning på din reMarkable, få tillbaka en ren ritning och markera den i omgångar. "
                "En interaktiv demo och en video på 2,5 minuter. Gratis och öppen källkod.",
        "share_file": "sketch-video-sv.html", "share_path": "/sketch/video/sv",
        "share_title": "rmink: från handskiss till ren ritning (video)",
        "share_desc": "En video på 2,5 minuter: en handskiss på en reMarkable blir en ren ritning, markeras i "
                      "omgångar, delas upp i varianter och detaljer och exporteras. Gratis och öppen källkod.",
        "app": "Bild till bläck", "watch": "Se videon", "other": "English", "other_href": "/sketch",
        "videos": "Videor", "tall": "4:5 för mobil och flöden", "wide": "16:9 för skärm och möten",
        "close": "Stäng", "lang_label": "Språk",
    },
}  # fmt: skip

HEAD = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="{site}{path}">
<link rel="alternate" hreflang="en" href="{site}/sketch">
<link rel="alternate" hreflang="sv" href="{site}/sketch/sv">
<meta property="og:type" content="website">
<meta property="og:site_name" content="rmink">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{site}{path}">
<meta property="og:image" content="{site}/promo/sketch/{image}">
<meta property="og:image:secure_url" content="{site}/promo/sketch/{image}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="627">
<meta property="og:image:alt" content="{title}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{site}/promo/sketch/{image}">
{fonts}
"""

SITE_CSS = """
<style>
[hidden] { display: none !important; }
img { max-width: 100%; }
.sitebar { display: flex; flex-wrap: wrap; gap: 10px 18px; align-items: center; justify-content: space-between; }
.sitebar .home { font-weight: 700; color: var(--ink); text-decoration: none; font-family: var(--display); font-size: 1.15rem; }
.sitebar .home span { color: var(--muted); font-weight: 500; font-size: .92rem; margin-left: 8px; }
.sitebar nav { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.sitebar nav a { color: var(--accent); font-size: .92rem; }
.videos { display: grid; gap: 10px; }
.videos .links { display: flex; flex-wrap: wrap; gap: 8px 22px; }
.videos a { color: var(--accent); }
.videos span { color: var(--muted); }
#demo { border: 0; padding: 12px; background: #111; border-radius: 16px; width: min(94vw, calc((92vh - 52px) * .8)); }
#demo::backdrop { background: rgb(0 0 0 / .72); }
#demo .vbar2 { display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 8px; }
#demo .seg { background: rgb(255 255 255 / .14); border: 0; }
#demo .seg button { color: #fff; }
#demo .seg button[aria-pressed="true"] { background: #fff; color: #111; }
#demo .close { background: rgb(255 255 255 / .14); color: #fff; border: 0; border-radius: 999px; width: 40px; height: 40px; font-size: 22px; cursor: pointer; }
#demo video { display: block; width: 100%; aspect-ratio: 4 / 5; background: #000; border-radius: 12px; }
</style>
"""

NAV = """
    <div class="sitebar">
      <a class="home" href="/">rmink<span>{app} →</span></a>
      <nav>
        <a href="{other_href}" lang="{other_lang}">{other}</a>
        <button class="btn primary" type="button" id="watch">▶ {watch}</button>
      </nav>
    </div>
"""

VIDEOS = """
  <section class="videos" id="videor">
    <h3>{videos}</h3>
    <div class="links">
      <span>{tall}:</span>
      <a href="/promo/sketch/rmink-sketch-sv-4x5.mp4">Svenska</a>
      <a href="/promo/sketch/rmink-sketch-en-4x5.mp4">English</a>
    </div>
    <div class="links">
      <span>{wide}:</span>
      <a href="/promo/sketch/rmink-sketch-sv-16x9.mp4">Svenska</a>
      <a href="/promo/sketch/rmink-sketch-en-16x9.mp4">English</a>
    </div>
  </section>
"""

DIALOG = """
<dialog id="demo" aria-label="{watch}">
  <div class="vbar2">
    <div class="seg" role="group" aria-label="{lang_label}">
      <button type="button" data-vlang="en">English</button><button type="button" data-vlang="sv">Svenska</button>
    </div>
    <button type="button" class="close" aria-label="{close}" autofocus>×</button>
  </div>
  <video controls playsinline preload="none"></video>
</dialog>
<script>
(() => {{
  // The 4:5 video in a dialog, as on the app's start page. ?demo (or ?demo=sv)
  // opens it on load, so a link can go straight to the video.
  const dlg = document.getElementById("demo"), video = dlg.querySelector("video");
  const params = new URLSearchParams(location.search);
  const pageLang = document.documentElement.lang;
  const preferred = () => (["sv", "en"].includes(params.get("demo")) ? params.get("demo") : pageLang);
  const show = (lang, autoplay) => {{
    for (const b of dlg.querySelectorAll("[data-vlang]")) b.setAttribute("aria-pressed", String(b.dataset.vlang === lang));
    const src = `/promo/sketch/rmink-sketch-${{lang}}-4x5.mp4`;
    if (video.getAttribute("src") !== src) {{ video.src = src; video.poster = `/promo/sketch/poster-${{lang}}.jpg`; }}
    if (autoplay) video.play().catch(() => {{ video.muted = true; video.play().catch(() => {{}}); }});
  }};
  const open = lang => {{ if (!dlg.open) dlg.showModal(); show(lang, true); }};
  document.getElementById("watch").addEventListener("click", () => open(preferred()));
  for (const b of dlg.querySelectorAll("[data-vlang]")) b.addEventListener("click", () => show(b.dataset.vlang, true));
  dlg.querySelector(".close").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", e => {{ if (e.target === dlg) dlg.close(); }});
  dlg.addEventListener("close", () => {{
    video.pause();
    if (params.has("demo")) history.replaceState(null, "", location.pathname + location.hash);
  }});
  if (params.has("demo")) open(preferred());
}})();
</script>
"""

SHARE = """<!doctype html>
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
<meta property="og:image" content="{site}/promo/sketch/{image}">
<meta property="og:image:secure_url" content="{site}/promo/sketch/{image}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="627">
<meta property="og:image:alt" content="{title}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{site}/promo/sketch/{image}">
<script>location.replace("{target}");</script>
<style>body {{ margin: 0; background: #f4f2ec; color: #1d1d1b; font: 17px/1.5 system-ui, sans-serif; padding: 32px 16px; }}</style>
</head>
<body>
<!-- Link previews read the tags above; people go on to the page with the video open. -->
<p><a href="{target}">{title}</a></p>
</body>
</html>
"""


def share_image(lang: str) -> str:
    """The newest share image; its name carries a content hash so LinkedIn
    fetches it instead of a cached one."""
    shots = sorted(MEDIA.glob(f"og-{lang}-*.jpg"), key=lambda f: f.stat().st_mtime)
    return shots[-1].name if shots else f"poster-{lang}.jpg"


def data_filled(template: str) -> str:
    s = (DEMO / template).read_text()
    for n, name in ((5, "data5.json"), (4, "data4.json"), (3, "data3.json"), (2, "data2.json")):
        s = s.replace(f"__DATA{n}__", (DEMO / name).read_text())
    return s.replace("__DATA__", (DEMO / "data.json").read_text())


def page(lang: str) -> Path:
    c = PAGES[lang]
    e = {k: html.escape(v) for k, v in c.items()}
    s = data_filled(c["template"])
    head_part, rest = s[: s.index("<style>")], s[s.index("<style>") :]
    # The template's own <title> and artifact meta give way to the site head.
    fonts = "\n".join(ln for ln in head_part.splitlines() if ln.startswith("<link"))
    out = HEAD.format(lang=lang, site=SITE, path=c["path"], title=e["title"], desc=e["desc"],
                      image=share_image(lang), fonts=fonts)  # fmt: skip
    style_end = rest.index("</style>") + len("</style>")
    out += rest[:style_end] + SITE_CSS + "</head>\n<body>\n"
    body = rest[style_end:]
    nav = NAV.format(app=e["app"], other_href=c["other_href"], other_lang="sv" if lang == "en" else "en",
                     other=e["other"], watch=e["watch"])  # fmt: skip
    marker = "<header>\n"
    assert marker in body
    body = body.replace(marker, marker + nav, 1)
    footer = "  <footer>"
    assert footer in body
    body = body.replace(
        footer, VIDEOS.format(videos=e["videos"], tall=e["tall"], wide=e["wide"]) + "\n" + footer, 1
    )
    out += (
        body
        + DIALOG.format(watch=e["watch"], close=e["close"], lang_label=e["lang_label"])
        + "</body>\n</html>\n"
    )
    path = PUBLIC / c["file"]
    path.write_text(out)
    return path


def share_page(lang: str) -> Path:
    c = PAGES[lang]
    target = f"{c['path']}?demo={lang}"
    out = SHARE.format(lang=lang, site=SITE, path=c["share_path"], title=html.escape(c["share_title"]),
                       desc=html.escape(c["share_desc"]), image=share_image(lang), target=target)  # fmt: skip
    path = PUBLIC / c["share_file"]
    path.write_text(out)
    return path


def media() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    for lang in PAGES:
        for tag in ("4x5", "16x9"):
            shutil.copy(
                OUT / f"rmink-sketch-{lang}-{tag}.mp4", MEDIA / f"rmink-sketch-{lang}-{tag}.mp4"
            )
        poster = Image.open(OUT / f"sketch-cover-{lang}-4x5.png").convert("RGB")
        poster.save(MEDIA / f"poster-{lang}.jpg", quality=86)


def serve_public() -> int:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(PUBLIC))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


# The poster is a frame from 51 s in; showing it avoids seeking, which the
# local test server cannot serve (no byte ranges).
PLAY = """
  const v = document.querySelector('#demo video');
  v.pause(); v.removeAttribute('controls'); v.removeAttribute('src'); v.load();
  const img = new Image(); img.src = v.poster; await img.decode();
  document.activeElement.blur();
  const play = document.createElement('div');
  play.innerHTML = `<svg viewBox="0 0 100 100" width="104" height="104"><circle cx="50" cy="50" r="48" fill="rgba(29,29,27,.82)"/><path d="M40 30 L72 50 L40 70 Z" fill="#fff"/></svg>`;
  const r = v.getBoundingClientRect();
  Object.assign(play.style, { position: 'fixed', left: (r.left + r.width / 2 - 52) + 'px', top: (r.top + r.height * 0.62 - 52) + 'px', zIndex: 99 });
  v.closest('dialog').appendChild(play);
"""


def shots() -> None:
    """Share images (1200 × 627): the built page with the video open, as on the
    live site. Served locally, so this works before deploying."""
    from playwright.sync_api import sync_playwright

    port = serve_public()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for lang, c in PAGES.items():
            pg = browser.new_page(viewport={"width": 1600, "height": 836}, device_scale_factor=0.75)
            pg.goto(f"http://127.0.0.1:{port}/{c['file']}?demo={lang}")
            pg.wait_for_selector("#demo[open]")
            pg.evaluate("async () => {" + PLAY + "}")
            pg.wait_for_timeout(600)
            img = Image.open(io.BytesIO(pg.screenshot())).convert("RGB")
            for old in MEDIA.glob(f"og-{lang}-*.jpg"):
                old.unlink()
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=88)
            name = f"og-{lang}-{hashlib.sha1(buf.getvalue()).hexdigest()[:8]}.jpg"
            (MEDIA / name).write_bytes(buf.getvalue())
            print(MEDIA / name)
        browser.close()


if __name__ == "__main__":
    if "--shots" in sys.argv:
        shots()
    else:
        media()
    for lang in PAGES:
        print(page(lang), share_page(lang))
