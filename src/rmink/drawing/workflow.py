"""Sketch → clean drawing → markings → next revision.

The steps the MCP server and CLI share:

1. :func:`read_sketch` fetches a notebook (local file or reMarkable Cloud),
   numbers the stroke groups on one page and fits shapes to them. With the
   saved drawing of an earlier revision, only strokes the user added since are
   returned: the markings to act on.
2. The interpreter turns the groups into a :class:`Drawing`;
   :func:`rectify` straightens it and :func:`check_dimensions` compares the
   written measurements with the drawn lengths.
3. :func:`build_revision` writes ``<name> r<N>.rmdoc`` with the clean page
   first and the sketch after it, and saves the drawing for the next round.
"""

from __future__ import annotations

import io
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rmink import cloud
from rmink.devices import DeviceProfile, config_dir, get_device
from rmink.drawing.fit import Group, analyse, overlay
from rmink.drawing.model import Drawing, LegendEntry
from rmink.drawing.render import default_legend, render_drawing
from rmink.ingest.rm import read_page, read_rmdoc
from rmink.model import Document, Page
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.render.preview import render_rm, thumbnail_png
from rmink.writer.rm_v6 import write_page


def drawings_dir() -> Path:
    return config_dir() / "drawings"


def _slug(name: str) -> str:
    return re.sub(r"[^\w\-]+", "-", name.strip().lower()).strip("-") or "drawing"


def save_drawing(drawing: Drawing) -> Path:
    path = drawings_dir() / f"{_slug(drawing.name)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(drawing.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_drawing(name: str) -> Drawing:
    path = drawings_dir() / f"{_slug(name)}.json"
    if not path.is_file():
        raise FileNotFoundError(f'No saved drawing named "{name}"')
    return Drawing.model_validate_json(path.read_text(encoding="utf-8"))


def open_document(source: str, device: DeviceProfile) -> Document:
    """A notebook from a local ``.rmdoc``/``.rm`` file or, failing that, the
    document at that path in the user's reMarkable Cloud."""
    path = Path(source).expanduser()
    if path.is_file():
        return read_rmdoc(path, device)
    token = cloud.load_token()
    if not token:
        raise cloud.CloudAuthError(
            f'"{source}" is not a local file and rmink is not connected to reMarkable '
            "Cloud; run `rmink cloud connect`"
        )
    remote = source if source.startswith("/") else "/" + source
    return read_rmdoc(cloud.get(token, remote), device)


@dataclass
class Sketch:
    document: Document
    page_number: int  # 1-based
    page: Page
    groups: list[Group]

    def overlay_png(self, device: DeviceProfile, scale: float = 0.6) -> bytes:
        buf = io.BytesIO()
        overlay(self.page, device, self.groups, scale).save(buf, "PNG", optimize=True)
        return buf.getvalue()

    def summary(self) -> dict:
        return {
            "document": self.document.name,
            "page": self.page_number,
            "pages": len(self.document.pages),
            "page_size_px": [self.page.width, self.page.height],
            "layers": self.page.layers,
            "groups": [g.summary() for g in self.groups],
        }


def read_sketch(
    source: str, page: int, device: DeviceProfile, since: Drawing | None = None
) -> Sketch:
    doc = open_document(source, device)
    if not 1 <= page <= len(doc.pages):
        raise ValueError(f"{doc.name} has {len(doc.pages)} pages; page {page} does not exist")
    known = {tuple(i) for i in since.sketch.written_ids} if since else None
    p = doc.pages[page - 1]
    return Sketch(doc, page, p, analyse(p, device, known))


def rectify(drawing: Drawing, angle_tol: float = 4.0, join_tol: float = 12.0) -> Drawing:
    """Pull endpoints that almost meet onto one corner, then make nearly
    horizontal/vertical segments exact by giving their ends one shared y or x.
    Shared corners stay shared. Returns a new drawing."""
    d = drawing.model_copy(deep=True)
    shapes = [e for e in d.elements if e.kind in ("line", "polyline") and len(e.points) >= 2]
    refs = [(e, i) for e in shapes for i in range(len(e.points))]
    if not refs:
        return d
    pts = np.array([e.points[i] for e, i in refs], dtype=float)

    def union_find(n: int):
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a: int, b: int) -> None:
            parent[find(a)] = find(b)

        return find, union

    def average(axis: int, find) -> None:
        groups: dict[int, list[int]] = {}
        for k in range(len(refs)):
            groups.setdefault(find(k), []).append(k)
        for members in groups.values():
            pts[members, axis] = pts[members, axis].mean()

    # Corners: endpoints of different elements closer than join_tol.
    find, union = union_find(len(refs))
    for a in range(len(refs)):
        for b in range(a + 1, len(refs)):
            if refs[a][0] is not refs[b][0] and np.linalg.norm(pts[a] - pts[b]) < join_tol:
                union(a, b)
    average(0, find)
    average(1, find)

    # Straight segments: their ends share y (horizontal) or x (vertical), and
    # so does every point already joined to those ends.
    fx, ux = union_find(len(refs))
    fy, uy = union_find(len(refs))
    for a in range(len(refs)):
        for b in range(a + 1, len(refs)):
            if np.allclose(pts[a], pts[b]):
                ux(a, b)
                uy(a, b)
    k = 0
    for e in shapes:
        for i in range(1, len(e.points)):
            a, b = k + i - 1, k + i
            dx, dy = pts[b] - pts[a]
            ang = math.degrees(math.atan2(dy, dx)) % 180
            if min(ang, 180 - ang) < angle_tol:
                uy(a, b)
            elif abs(ang - 90) < angle_tol:
                ux(a, b)
        k += len(e.points)
    average(0, fx)
    average(1, fy)

    for k, (e, i) in enumerate(refs):
        e.points[i] = (round(float(pts[k][0]), 1), round(float(pts[k][1]), 1))
    return d


_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def check_dimensions(drawing: Drawing) -> dict:
    """Written measurements against drawn lengths: the common scale and the
    dimensions that disagree with it, which are worth asking about."""
    rows = []
    for dim in drawing.dimensions:
        value = dim.value
        if value is None and (m := _NUMBER.search(dim.text)):
            value = float(m.group().replace(",", "."))
        px = float(np.linalg.norm(np.subtract(dim.end, dim.start)))
        if value and px > 0:
            rows.append({"id": dim.id, "text": dim.text, "value": value, "drawn_px": round(px, 1)})
    if not rows:
        return {"scale": None, "dimensions": []}
    scale = float(np.median([r["value"] / r["drawn_px"] for r in rows]))
    for r in rows:
        expected = r["value"] / scale
        r["deviation_pct"] = round((r["drawn_px"] - expected) / expected * 100, 1)
        r["consistent"] = abs(r["deviation_pct"]) <= 10
    return {"scale_units_per_px": round(scale, 4), "dimensions": rows}


@dataclass
class Revision:
    path: Path
    drawing: Drawing
    saved_to: Path
    preview_png: bytes


def build_revision(
    drawing: Drawing,
    output: Path,
    sketch: Page | None = None,
    seed: int | None = None,
) -> Revision:
    """Write the clean revision (and the sketch after it) as a notebook, and
    save the drawing with the ids of the strokes rmink wrote."""
    device = get_device(drawing.sketch.device)
    drawing = drawing.model_copy(deep=True)
    if not drawing.legend:
        drawing.legend = [LegendEntry(key=k, meaning=m) for k, m in default_legend(drawing)]
    clean = render_drawing(drawing, device)
    pages = [clean] + ([sketch] if sketch is not None and sketch.strokes else [])

    uuids = UuidFactory(seed)
    author = uuids()
    rm_pages, thumbs = [], []
    for p in pages:
        data = write_page(p, device, author)
        rm_pages.append(data)
        thumbs.append(render_rm(data, device, p.height))
    drawing.sketch.written_ids = [s.id for s in read_page(rm_pages[0], device).strokes if s.id]

    output = Path(output)
    if output.suffix.lower() != ".rmdoc":
        output = output.with_suffix(".rmdoc")
    write_rmdoc(
        output,
        f"{drawing.name} r{drawing.revision}",
        [
            RmdocPage(data, thumbnail_png(img), p.layers)
            for data, img, p in zip(rm_pages, thumbs, pages, strict=True)
        ],
        [str(uuids()) for _ in pages],
        author,
        device,
        str(uuids()),
        now_ms=0 if seed is not None else None,
    )
    buf = io.BytesIO()
    thumbs[0].save(buf, "PNG", optimize=True)
    return Revision(output, drawing, save_drawing(drawing), buf.getvalue())


def drawing_from_json(data: str | dict) -> Drawing:
    if isinstance(data, str):
        data = json.loads(data)
    return Drawing.model_validate(data)
