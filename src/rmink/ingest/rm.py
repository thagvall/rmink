"""Read notebooks back from the tablet: ``.rmdoc`` archives or single ``.rm`` pages.

The inverse of :mod:`rmink.writer.rm_v6`: scene coordinates become device
pixels again, and every stroke keeps its layer name and CRDT id, so strokes the
user added after rmink wrote a page can be told apart from rmink's own.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
from rmscene import scene_items as si
from rmscene.scene_stream import read_tree

from rmink.devices import DeviceProfile
from rmink.model import Document, Page, Stroke


def _strokes(group: si.Group, layer: str, device: DeviceProfile) -> list[Stroke]:
    out: list[Stroke] = []
    s = device.ink_scale
    for item_id, item in group.children.items():
        if isinstance(item, si.Group):
            out.extend(_strokes(item, layer, device))
        elif isinstance(item, si.Line) and item.points:
            pts = np.array([(p.x / s + device.width / 2, p.y / s) for p in item.points])
            out.append(
                Stroke(
                    pts,
                    width=float(np.median([p.width for p in item.points])) / 4 / s,
                    pen=item.tool,
                    color=item.color,
                    rgba=item.color_rgba,
                    pressures=np.array([p.pressure for p in item.points]),
                    layer=layer,
                    id=(item_id.part1, item_id.part2),
                )
            )
    return out


def read_page(rm_bytes: bytes, device: DeviceProfile) -> Page:
    tree = read_tree(io.BytesIO(rm_bytes))
    page = Page(device.width, device.height)
    for item in tree.root.children.values():
        if isinstance(item, si.Group):
            name = item.label.value or "Layer 1"
            page.layer_names.append(name)
            page.strokes.extend(_strokes(item, name, device))
    # Lines straight under the root (not seen from firmware 3.x) are skipped
    # by the loop above; layers are the only containers the tablet writes.
    if page.strokes:
        bottom = max(float(st.points[:, 1].max()) for st in page.strokes)
        page.height = max(page.height, int(bottom) + 1)
    return page


def read_rmdoc(source: Path | bytes, device: DeviceProfile) -> Document:
    """All pages of a ``.rmdoc`` (or the one page of a ``.rm`` file), in page order."""
    if isinstance(source, Path) and source.suffix.lower() == ".rm":
        return Document(source.stem, [read_page(source.read_bytes(), device)])
    data = source.read_bytes() if isinstance(source, Path) else source
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        content_name = next(n for n in names if n.endswith(".content"))
        doc_id = content_name.removesuffix(".content")
        content = json.loads(zf.read(content_name))
        meta_name = f"{doc_id}.metadata"
        meta = json.loads(zf.read(meta_name)) if meta_name in names else {}
        entries = content.get("cPages", {}).get("pages") or [
            {"id": pid} for pid in content.get("pages", [])
        ]
        # cPages lists pages with an "idx" sort key; deleted pages carry "deleted".
        entries = [e for e in entries if "deleted" not in e]
        entries.sort(key=lambda e: (e.get("idx") or {}).get("value", ""))
        pages = []
        for e in entries:
            rm_name = f"{doc_id}/{e['id']}.rm"
            # A page the user never drew on has no .rm file.
            pages.append(
                read_page(zf.read(rm_name), device)
                if rm_name in names
                else Page(device.width, device.height)
            )
    name = meta.get("visibleName") or (source.stem if isinstance(source, Path) else doc_id)
    return Document(name, pages)
