"""Render a sheet notebook from the tablet (`rmink sheet send`, then downloaded)
as the tablet shows it, and save the user's ink so the video can write it again.

Usage: python promo/ops-video/pages.py OUT_DIR NOTEBOOK.rmdoc SHEET.pdf
Writes OUT_DIR/tab-p<page>.png (the tablet page without ink, device px),
OUT_DIR/tab-p<page>-ink.json (strokes as SVG paths in the same px) and
OUT_DIR/sheet.png (page 1 of the sheet as drawn, before the tablet).
"""

import io
import json
import sys
import zipfile
from pathlib import Path

import pymupdf

from rmink.bridge.ink_pdf import notebook_manifest
from rmink.devices import get_device
from rmink.workbook.read import read_ink


def main(out: Path, notebook: Path, sheet: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    data = notebook.read_bytes()
    device = get_device(notebook_manifest(data).device)
    ink = read_ink(data, device)
    zoom = device.dpi / 72
    doc = pymupdf.open(stream=ink.pdf, filetype="pdf")
    for i, page in enumerate(doc):
        page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=False).save(out / f"tab-p{i + 1:02d}.png")
        strokes = ink.pages.get(i, [])
        if strokes:
            paths = [{"d": "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in s.points),
                      "w": round(max(float(s.width), 2.5), 1)} for s in strokes]  # fmt: skip
            (out / f"tab-p{i + 1:02d}-ink.json").write_text(json.dumps(paths))
        print(f"page {i + 1}: {page.rect.width:.0f}x{page.rect.height:.0f} pt, {len(strokes)} strokes")
    src = pymupdf.open(sheet)
    src[0].get_pixmap(dpi=150).save(out / "sheet.png")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
