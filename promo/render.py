"""Render the promo timeline to MP4 (or to still frames for review).

Usage:
  python promo/render.py en                      # out/rmink-promo-en.mp4
  python promo/render.py sv --stills 3,9,20,35   # out/stills-sv.png contact sheet
  python promo/render.py en --cover 3.2          # out/cover-en.png
"""

import argparse
import functools
import http.server
import io
import subprocess
import threading
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "out"
W, H, FPS = 1080, 1350, 30


def serve() -> int:
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(HERE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


def open_page(p, port: int, lang: str):
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"http://127.0.0.1:{port}/timeline.html?lang={lang}")
    page.wait_for_function("window.ready === true", timeout=60000)
    if errors:
        raise RuntimeError("page errors: " + "; ".join(errors))
    return browser, page, errors


def frame(page, t: float) -> bytes:
    page.evaluate("t => window.seek(t)", t)
    return page.screenshot(type="jpeg", quality=93)


def stills(lang: str, times: list[float]) -> Path:
    port = serve()
    with sync_playwright() as p:
        browser, page, errors = open_page(p, port, lang)
        imgs = [Image.open(io.BytesIO(frame(page, t))) for t in times]
        browser.close()
    if errors:
        raise RuntimeError("; ".join(errors))
    cols = min(4, len(imgs))
    rows = (len(imgs) + cols - 1) // cols
    tw, th = W // 3, H // 3
    sheet = Image.new("RGB", (cols * (tw + 10) + 10, rows * (th + 10) + 10), "#777")
    for i, im in enumerate(imgs):
        r, c = divmod(i, cols)
        sheet.paste(im.resize((tw, th)), (10 + c * (tw + 10), 10 + r * (th + 10)))
    path = OUT / f"stills-{lang}.png"
    sheet.save(path)
    return path


def cover(lang: str, t: float) -> Path:
    port = serve()
    with sync_playwright() as p:
        browser, page, errors = open_page(p, port, lang)
        page.evaluate("t => window.seek(t)", t)
        path = OUT / f"cover-{lang}.png"
        page.screenshot(path=path, type="png")
        browser.close()
    return path


def video(lang: str) -> Path:
    path = OUT / f"rmink-promo-{lang}.mp4"
    port = serve()
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "mjpeg", "-i", "-",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-map", "0:v", "-map", "1:a", "-shortest",
        # JPEG frames are full range; convert to standard TV range for players.
        "-vf", "scale=out_range=tv,format=yuv420p", "-color_range", "tv",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "96k",
        str(path),
    ]  # fmt: skip
    ff = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with sync_playwright() as p:
        browser, page, errors = open_page(p, port, lang)
        n = int(page.evaluate("window.DURATION") * FPS)
        for i in range(n):
            ff.stdin.write(frame(page, i / FPS))
            if i % 150 == 0:
                print(f"{lang}: {i / FPS:4.1f}s", flush=True)
        browser.close()
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg failed")
    if errors:
        raise RuntimeError("; ".join(errors))
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("lang", choices=["en", "sv"])
    ap.add_argument("--stills", help="comma-separated times in seconds")
    ap.add_argument("--cover", type=float, help="save one full-size frame as out/cover-LANG.png")
    a = ap.parse_args()
    if a.cover is not None:
        print(cover(a.lang, a.cover))
    elif a.stills:
        print(stills(a.lang, [float(x) for x in a.stills.split(",")]))
    else:
        print(video(a.lang))
