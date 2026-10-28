"""Sketch → clean drawing → markings → next revision.

The steps the MCP server and CLI share:

1. :func:`read_sketch` fetches a notebook (local file or reMarkable Cloud),
   numbers the stroke groups on one page and fits shapes to them. With the
   saved drawing of an earlier revision, only strokes the user added since are
   returned: the markings to act on.
2. The interpreter turns the groups into a :class:`Drawing`;
   :func:`rectify` straightens it and :func:`check_dimensions` compares the
   written measurements and angles with the drawing. :func:`measure` gives
   lengths, areas and angles from its geometry.
3. :func:`build_revision` writes the revision notebook with the clean page
   first and the sketch after it, and saves the drawing for the next round.
4. :func:`send_revision` puts it in the drawing's folder in the cloud:

   rmink/
     Garage                  a new sketch, waiting for its first round
     Altan/
       Altan r03 · 2 frågor  the revision to mark up
       Tidigare/             earlier revisions (and the sketch), oldest first
"""

from __future__ import annotations

import io
import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rmink import cloud
from rmink.devices import DeviceProfile, config_dir, get_device
from rmink.drawing.fit import Group, analyse, overlay
from rmink.drawing.model import Dimension, Drawing, Element, LegendEntry
from rmink.drawing.render import default_legend, render_drawing
from rmink.drawing.store import FileStore, Store
from rmink.ingest.rm import read_page, read_rmdoc
from rmink.model import Document, Page
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.render.preview import render_rm, thumbnail_png
from rmink.writer.rm_v6 import write_page

log = logging.getLogger(__name__)

RMINK_FOLDER = "/rmink"
ARCHIVE = "Tidigare"
# rmapi matches paths as glob patterns: rmink keeps these characters out of the
# names it makes and never moves a notebook whose path has them.
_GLOB = re.compile(r"[*?\[\]\\]")


def safe_name(name: str) -> str:
    return re.sub(r"[/*?\[\]\\]+", "-", name).strip() or "Ritning"


def revision_title(drawing: Drawing) -> str:
    """'Altan r03 · 2 frågor': the notebook name of a revision. Two digits keep
    name order and time order the same; the count says it waits for answers."""
    title = f"{safe_name(drawing.name)} r{drawing.revision:02d}"
    n = sum(a.status == "open" for a in drawing.annotations)
    if n:
        title += f" · {n} {'fråga' if n == 1 else 'frågor'}"
    return title


def drawing_folder(name: str) -> str:
    return f"{RMINK_FOLDER}/{safe_name(name)}"


def drawings_dir() -> Path:
    return config_dir() / "drawings"


def save_drawing(drawing: Drawing, store: Store | None = None) -> str:
    return (store or FileStore()).save(drawing)


def load_drawing(name: str, store: Store | None = None) -> Drawing:
    drawing = (store or FileStore()).load(name)
    if drawing is None:
        raise FileNotFoundError(f'No saved drawing named "{name}"')
    return drawing


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
    before = pts.copy()

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

    # An angle drawn on a corner or line end moves with it.
    def follow(p):
        dist = np.linalg.norm(before - np.asarray(p, float), axis=1)
        k = int(dist.argmin())
        return tuple(round(float(c), 1) for c in pts[k]) if dist[k] < join_tol else p

    for ang in d.angles:
        ang.vertex, ang.start, ang.end = follow(ang.vertex), follow(ang.start), follow(ang.end)
    return d


_NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")
ANGLE_TOLERANCE = 2.0  # degrees between a written angle and the drawn one


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
    angles = []
    for ang in drawing.angles:
        value = ang.value
        if value is None and (m := _NUMBER.search(ang.text)):
            value = float(m.group().replace(",", "."))
        drawn = ang.measured()
        if drawn is None:
            continue
        row = {"id": ang.id, "text": ang.text, "value": value, "drawn_deg": round(drawn, 1)}
        if value is not None:
            row["deviation_deg"] = round(drawn - value, 1)
            row["consistent"] = abs(drawn - value) <= ANGLE_TOLERANCE
        angles.append(row)
    if not rows:
        return {"scale": None, "dimensions": [], "angles": angles}
    scale = float(np.median([r["value"] / r["drawn_px"] for r in rows]))
    for r in rows:
        expected = r["value"] / scale
        r["deviation_pct"] = round((r["drawn_px"] - expected) / expected * 100, 1)
        r["consistent"] = abs(r["deviation_pct"]) <= 10
    return {"scale_units_per_px": round(scale, 4), "dimensions": rows, "angles": angles}


def _segments(e: Element) -> list[tuple[np.ndarray, np.ndarray]]:
    pts = [np.asarray(p, float) for p in e.points]
    if e.kind == "rect" and len(pts) == 2:
        (x0, y0), (x1, y1) = pts
        pts = [np.array(p, float) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    closed = e.kind == "rect" or e.closed
    pairs = list(zip(pts, pts[1:], strict=False))
    if closed and len(pts) > 2:
        pairs.append((pts[-1], pts[0]))
    return pairs


def _corner_angle(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    u, v = a - p, b - p
    return abs(math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u @ v)))


def measure(drawing: Drawing, ids: list[str]) -> dict:
    """Lengths, areas and angles from the drawing's geometry, so they are
    read off the drawing rather than estimated. One element gives its length
    (and area and corner angles when closed); two lines give the angle
    between them. Real units use the scale of the written dimensions."""
    check = check_dimensions(drawing)
    scale = check.get("scale_units_per_px")
    unit = drawing.dimensions[0].unit if drawing.dimensions else "mm"
    out: dict = {"scale_units_per_px": scale, "unit": unit if scale else "px", "items": []}

    def real(px: float, power: int = 1) -> float:
        return round(px * scale**power, 1) if scale else round(px, 1)

    elements = []
    for item_id in ids:
        item = drawing.find(item_id)
        if item is None:
            out["items"].append({"id": item_id, "error": "no such id"})
            continue
        row: dict = {"id": item_id}
        if isinstance(item, Dimension):
            row["length"] = real(float(np.linalg.norm(np.subtract(item.end, item.start))))
        elif isinstance(item, Element) and item.kind in ("circle", "arc") and item.radius:
            sweep = 360.0 if item.kind == "circle" else abs(item.end_angle - item.start_angle)
            row["length"] = real(math.radians(sweep) * item.radius)
            row["radius"] = real(item.radius)
            if item.kind == "circle":
                row["area"] = real(math.pi * item.radius**2, 2)
        elif isinstance(item, Element) and item.kind in ("line", "polyline", "rect"):
            segs = _segments(item)
            row["length"] = real(sum(float(np.linalg.norm(b - a)) for a, b in segs))
            closed = item.kind == "rect" or (item.closed and len(item.points) > 2)
            corners = [a for a, _ in segs] if closed else [b for _, b in segs[:-1]]
            if closed:
                xy = np.array(corners)
                x, y = xy[:, 0], xy[:, 1]
                row["area"] = real(abs(x @ np.roll(y, -1) - y @ np.roll(x, -1)) / 2, 2)
            n = len(corners)
            row["corners"] = [
                {
                    "at": [round(float(c[0]), 1), round(float(c[1]), 1)],
                    "deg": round(
                        _corner_angle(
                            c,
                            corners[i - 1] if closed else segs[i][0],
                            corners[(i + 1) % n] if closed else segs[i + 1][1],
                        ),
                        2,
                    ),
                }
                for i, c in enumerate(corners)
            ]
            elements.append(item)
        else:
            row["error"] = "not measurable"
        out["items"].append(row)

    if len(elements) == 2:
        out["angle"] = _angle_between(*elements, join_tol=12.0)
    return out


def _angle_between(e1: Element, e2: Element, join_tol: float) -> dict:
    """The angle at the corner two lines share, or between their directions."""
    best = None
    for a1, b1 in _segments(e1):
        for a2, b2 in _segments(e2):
            for p, q in ((a1, b1), (b1, a1)):
                for r, s in ((a2, b2), (b2, a2)):
                    dist = float(np.linalg.norm(p - r))
                    if best is None or dist < best[0]:
                        best = (dist, p, q, s, (a1, b1), (a2, b2))
    if best is None:
        return {"error": "no straight segments"}
    dist, p, q, s, seg1, seg2 = best
    if dist < join_tol:
        deg = _corner_angle(p, q, s)
        return {"deg": round(deg, 2), "vertex": [round(float(c), 1) for c in p], "shared": True}
    u, v = seg1[1] - seg1[0], seg2[1] - seg2[0]
    deg = abs(math.degrees(math.atan2(u[0] * v[1] - u[1] * v[0], u @ v))) % 180
    acute = min(deg, 180 - deg)
    return {"deg": round(acute, 2), "obtuse": round(180 - acute, 2), "shared": False}


@dataclass
class Revision:
    path: Path
    drawing: Drawing
    saved_to: str
    preview_png: bytes


def build_revision(
    drawing: Drawing,
    output: Path,
    sketch: Page | None = None,
    seed: int | None = None,
    store: Store | None = None,
) -> Revision:
    """Write the clean revision (and the sketch after it) as a notebook, and
    save the drawing with the ids of the strokes rmink wrote, in ``store``
    (the local drawings folder by default)."""
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
        revision_title(drawing),
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
    return Revision(output, drawing, save_drawing(drawing, store), buf.getvalue())


def send_revision(rev: Revision, token: str, store: Store | None = None) -> str:
    """Upload a revision to its drawing's folder in the reMarkable Cloud and
    return the cloud path.

    The folder is made on the first round. The drawing is saved again with the
    path, which the next round reads. The notebook this round read moves to the
    folder's ``Tidigare``: the previous revision as it is, a new sketch from
    ``/rmink`` as "<name> r00 skiss" so it sorts first. Notebooks anywhere
    else are the user's and stay put.
    """
    d, store = rev.drawing, store or FileStore()
    folder = drawing_folder(d.name)
    read = d.sketch.document
    parent, _, base = read.rpartition("/")
    movable = parent in (RMINK_FOLDER, folder) and not _GLOB.search(read)
    archived_name = f"{safe_name(d.name)} r00 skiss" if parent == RMINK_FOLDER else base
    if movable and read == folder:
        # The sketch has the drawing's name; rmapi finds entries by name, so
        # free it before making the folder.
        renamed = f"{RMINK_FOLDER}/{archived_name}"
        cloud.mv(token, read, renamed)
        read = renamed
    try:
        entries = cloud.ls(token, folder)
    except cloud.CloudNotFoundError:
        cloud.mkdir(token, RMINK_FOLDER)
        cloud.mkdir(token, folder)
        entries = []
    sent_as = f"{folder}/{cloud.put(rev.path, token, folder=folder, name=revision_title(d))}"
    d.sketch.sent_as = sent_as
    store.save(d)
    store.link(sent_as, d.name)

    if movable:
        archive = f"{folder}/{ARCHIVE}"
        try:
            if not any(e.folder and e.name == ARCHIVE for e in entries):
                cloud.mkdir(token, archive)
            store.link(_move_into(token, read, archive, archived_name), d.name)
        except cloud.CloudError as e:
            log.warning("Could not move %s to %s: %s", read, archive, e)
    return sent_as


def _move_into(token: str, src: str, folder: str, name: str, attempts: int = 9) -> str:
    for n in range(1, attempts + 1):
        dst = f"{folder}/{name}" + (f"_{n}" if n > 1 else "")
        try:
            cloud.mv(token, src, dst)
            return dst
        except cloud.CloudExistsError:
            continue
    raise cloud.CloudExistsError(f'Too many notebooks named "{name}" in {folder}')


def drawing_from_json(data: str | dict) -> Drawing:
    if isinstance(data, str):
        data = json.loads(data)
    return Drawing.model_validate(data)
