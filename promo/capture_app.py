"""Capture full-page screenshots of the live web app in a phone viewport, plus
the positions of the elements the video taps on.

Usage: python promo/capture_app.py en|sv
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "out"
URL = "http://localhost:8771/"  # local `rmink web` running the current UI
VIEW = {"width": 390, "height": 844}


def box(page, selector):
    b = page.locator(selector).first.bounding_box()
    sy = page.evaluate("scrollY")
    return {k: round(v, 1) for k, v in {**b, "y": b["y"] + sy}.items()}


def main(lang: str) -> None:
    out = OUT / f"app-{lang}"
    out.mkdir(parents=True, exist_ok=True)
    meta = {"view": VIEW, "dpr": 3, "states": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        ctx = browser.new_context(
            viewport=VIEW, device_scale_factor=3, is_mobile=True, has_touch=True,
            accept_downloads=True, locale="en-US",
        )  # fmt: skip
        page = ctx.new_page()

        def shot(name, **boxes):
            page.evaluate("scrollTo(0, 0)")
            page.wait_for_timeout(300)
            page.screenshot(path=out / f"{name}.png", full_page=True)
            meta["states"][name] = {
                "height": page.evaluate("document.documentElement.scrollHeight"),
                "boxes": {k: box(page, sel) for k, sel in boxes.items()},
            }

        page.goto(URL)
        page.wait_for_selector("#devices button")
        # The beta notice for Paper Pro is real but distracts in a 60-second video.
        page.add_style_tag(content="#notices { display: none !important; }")
        shot("empty", drop="#drop", pro="#devices button:has-text('Pro')")

        page.set_input_files("#picker", str(OUT / f"note-{lang}.jpg"))
        page.wait_for_function(
            "document.querySelectorAll('#gallery figure').length === 1", timeout=90000
        )
        page.wait_for_function("!document.getElementById('status').classList.contains('busy')")
        shot("preview", gallery="#gallery figure", pro="#devices button:has-text('Pro')",
             download="#download")  # fmt: skip

        page.click("#devices button:has-text('Pro')")
        page.wait_for_function("!document.getElementById('status').classList.contains('busy')")
        page.wait_for_timeout(1500)
        page.wait_for_function("!document.getElementById('status').classList.contains('busy')")
        shot("pro", gallery="#gallery figure", pro="#devices button:has-text('Pro')",
             download="#download")  # fmt: skip

        with page.expect_download():
            page.click("#download")
        page.wait_for_selector("#nudge:not([hidden])")
        shot("downloaded", status="#status", nudge="#nudge", download="#download")
        browser.close()
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps({k: v["height"] for k, v in meta["states"].items()}))


if __name__ == "__main__":
    main(sys.argv[1])
