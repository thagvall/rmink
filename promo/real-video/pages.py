"""Render the pages of real workbook revisions (.rmdoc from the tablet) as the
tablet shows them: the PDF page with the ink drawn on, with or without the
hidden Facit layer.

Usage: python promo/real-video/pages.py OUT_DIR NAME=FILE.rmdoc [NAME=FILE.rmdoc ...]
Writes OUT_DIR/<name>-p<page>.png and OUT_DIR/<name>-p<page>-facit.png. A page
with handwriting also gets <name>-p<page>-blank.png (no ink) and
<name>-p<page>-ink.json (the strokes as SVG paths in image pixels), so the video
can write it again.
"""

import json

import sys
from pathlib import Path

import pymupdf

from rmink.devices import get_device
from rmink.workbook.build import FACIT_LAYER
from rmink.workbook.read import read_ink

DEVICE = get_device("rm2")
DPI = 200


def render(pdf: bytes, strokes, index: int, facit: bool, ink: bool = True) -> pymupdf.Pixmap:
    doc = pymupdf.open(stream=pdf)
    page = doc[index]
    k = 72 / DEVICE.dpi
    for s in strokes:
        if (s.layer == FACIT_LAYER and not facit) or (s.layer != FACIT_LAYER and not ink):
            continue
        pts = [(float(x) * k, float(y) * k) for x, y in s.points]
        if len(pts) == 1:
            pts.append((pts[0][0] + 0.3, pts[0][1]))
        rgb = (0.17, 0.37, 0.85) if s.layer == FACIT_LAYER else (0.1, 0.1, 0.1)
        page.draw_polyline(pts, color=rgb, width=max(s.width * k, 0.9), closePath=False)
    return page.get_pixmap(dpi=DPI)


def main(out: Path, docs: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for arg in docs:
        name, path = arg.split("=", 1)
        ink = read_ink(Path(path).read_bytes(), DEVICE)
        n = len(pymupdf.open(stream=ink.pdf))
        for i in range(n):
            strokes = ink.pages.get(i, [])
            render(ink.pdf, strokes, i, False).save(out / f"{name}-p{i + 1:02d}.png")
            if any(s.layer == FACIT_LAYER for s in strokes):
                render(ink.pdf, strokes, i, True).save(out / f"{name}-p{i + 1:02d}-facit.png")
            hand = [s for s in strokes if s.layer != FACIT_LAYER]
            if hand:
                render(ink.pdf, strokes, i, False, ink=False).save(out / f"{name}-p{i + 1:02d}-blank.png")
                k = DPI / DEVICE.dpi
                paths = [{"d": "M" + " L".join(f"{x * k:.1f} {y * k:.1f}" for x, y in s.points),
                          "w": round(max(s.width * k, 2.5), 1)} for s in hand]  # fmt: skip
                (out / f"{name}-p{i + 1:02d}-ink.json").write_text(json.dumps(paths))
        print(name, n, "pages")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
