"""Render the pages of real drawing revisions (.rmdoc notebooks from the tablet)
as the tablet shows them, and save the user's own marks separately so the
video can write them again.

Usage: python promo/bygg-video/pages.py OUT_DIR NAME=FILE.rmdoc [NAME=FILE.rmdoc ...]
Writes OUT_DIR/<name>-p<page>.png (everything), and for a page with marks by
the user (strokes with another author than rmink's) <name>-p<page>-blank.png
(rmink's strokes only) and <name>-p<page>-ink.json (the marks as SVG paths).
"""

import io
import json
import sys
import zipfile
from pathlib import Path

from rmscene import scene_items as si
from rmscene.scene_stream import SceneLineItemBlock, read_blocks

from rmink.devices import get_device
from rmink.render.preview import render_lines

DEVICE = get_device("rm2")
RMINK = 1  # the author id in the CrdtIds of the strokes rmink writes


def lines(rm: bytes) -> list[tuple[si.Line, int]]:
    return [
        (b.item.value, b.item.item_id.part1)
        for b in read_blocks(io.BytesIO(rm))
        if isinstance(b, SceneLineItemBlock) and b.item.value is not None
    ]


def main(out: Path, docs: list[str]) -> None:
    out.mkdir(parents=True, exist_ok=True)
    s, half = DEVICE.ink_scale, DEVICE.width / 2
    for arg in docs:
        name, path = arg.split("=", 1)
        z = zipfile.ZipFile(path)
        content = next(n for n in z.namelist() if n.endswith(".content"))
        doc = content.removesuffix(".content")
        pages = json.loads(z.read(content))["cPages"]["pages"]
        for i, p in enumerate(pages):
            rm = f"{doc}/{p['id']}.rm"
            ls = lines(z.read(rm)) if rm in z.namelist() else []
            stem = out / f"{name}-p{i + 1:02d}"
            render_lines([ln for ln, _ in ls], DEVICE).save(f"{stem}.png")
            mine = [ln for ln, author in ls if author != RMINK]
            if mine:
                render_lines([ln for ln, a in ls if a == RMINK], DEVICE).save(f"{stem}-blank.png")
                paths = [{"d": "M" + " L".join(f"{pt.x / s + half:.1f} {pt.y / s:.1f}" for pt in ln.points),
                          "w": round(max(ln.points[0].width / 4 / s, 2.5), 1)} for ln in mine]  # fmt: skip
                Path(f"{stem}-ink.json").write_text(json.dumps(paths))
        print(name, len(pages), "pages")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
