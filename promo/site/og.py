"""Share images for the home page, /skola and /bygg: the page with its video
open, 1200 × 627. Serve the site first and pass its address:

    python promo/site/og.py http://localhost:8772

/video and /sketch keep their own hashed images (promo/make_share.py), so the
cards on posts already out do not change.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

PUBLIC = Path(__file__).resolve().parents[2] / "deploy" / "vercel" / "public"
# Page, seconds into its video, output file.
SHOTS = [
    ("/?demo=en", 62.5, "og.jpg"),
    ("/skola?demo", 20, "promo/skola/og.jpg"),
    ("/bygg?demo", 14, "promo/bygg/og.jpg"),
]
SEEK = """async (t) => {
  const v = document.querySelector('#video-dialog video');
  v.pause();
  if (v.readyState < 1) await new Promise((r) => v.addEventListener('loadedmetadata', r, { once: true }));
  v.currentTime = t;
  await new Promise((r) => v.addEventListener('seeked', r, { once: true }));
  v.controls = false;
  document.activeElement.blur();
  const play = document.createElement('div');
  play.innerHTML = `<svg viewBox="0 0 100 100" width="120" height="120"><circle cx="50" cy="50" r="48" fill="rgba(29,29,27,.82)"/><path d="M40 30 L72 50 L40 70 Z" fill="#fff"/></svg>`;
  const r = v.getBoundingClientRect();
  Object.assign(play.style, { position: 'fixed', left: (r.left + r.width / 2 - 60) + 'px', top: (r.top + r.height / 2 - 60) + 'px' });
  v.closest('dialog').appendChild(play);
}"""


def main(base: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(viewport={"width": 1600, "height": 836}, device_scale_factor=0.75,
                                  color_scheme="light", locale="en-US")  # fmt: skip
        page = ctx.new_page()
        for path, at, name in SHOTS:
            page.goto(base + path)
            page.wait_for_selector("#video-dialog[open]")
            page.evaluate(SEEK, at)
            page.wait_for_timeout(600)
            png = page.screenshot()
            Image.open(io.BytesIO(png)).convert("RGB").save(PUBLIC / name, quality=88, optimize=True)
            print(PUBLIC / name)
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1])
