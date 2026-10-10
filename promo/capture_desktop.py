"""Capture the live web app in a desktop window (one screen, no scrolling), plus
the positions of the elements the video clicks on.

Usage: python promo/capture_desktop.py en|sv   (with `rmink web --port 8771` running)
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = HERE / "out"
URL = "http://localhost:8771/"
VIEW = {"width": 960, "height": 800}


def main(lang: str) -> None:
    out = OUT / f"desk-{lang}"
    out.mkdir(parents=True, exist_ok=True)
    meta = {"view": VIEW, "dpr": 2, "states": {}}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport=VIEW, device_scale_factor=2, accept_downloads=True,
                                locale="en-US")  # fmt: skip

        def box(selector):
            b = page.locator(selector).first.bounding_box()
            return {k: round(v, 1) for k, v in b.items()}

        def shot(name, **boxes):
            page.wait_for_timeout(300)
            page.screenshot(path=out / f"{name}.png")
            meta["states"][name] = {"boxes": {k: box(sel) for k, sel in boxes.items()}}

        page.goto(URL)
        page.wait_for_selector("#devices button")
        # The beta notice for Paper Pro is real but distracts in a short video.
        page.add_style_tag(content="#notices { display: none !important; }")
        idle = "!document.getElementById('status').classList.contains('busy')"
        shot("empty", drop="#drop", pro="#devices button:has-text('Pro')", download="#download")

        page.set_input_files("#picker", str(OUT / f"note-{lang}.jpg"))
        page.wait_for_function("document.querySelectorAll('#gallery figure').length === 1",
                               timeout=90000)  # fmt: skip
        page.wait_for_function(idle)
        shot("preview", gallery="#gallery figure", pro="#devices button:has-text('Pro')",
             download="#download")  # fmt: skip

        page.click("#devices button:has-text('Pro')")
        page.wait_for_timeout(1500)
        page.wait_for_function(idle)
        shot("pro", gallery="#gallery figure", download="#download")

        with page.expect_download() as dl:
            page.click("#download")
        meta["filename"] = dl.value.suggested_filename
        meta["size"] = Path(dl.value.path()).stat().st_size
        page.wait_for_selector("#nudge:not([hidden])")
        shot("downloaded", download="#download", status="#status")
        browser.close()
    (out / "meta.json").write_text(json.dumps(meta, indent=1))
    print(meta["filename"], meta["size"], list(meta["states"]))


if __name__ == "__main__":
    main(sys.argv[1])
