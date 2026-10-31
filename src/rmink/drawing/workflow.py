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

import datetime
import io
import json
import logging
import math
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from rmink import cloud
from rmink.devices import DeviceProfile, config_dir, get_device
from rmink.drawing.fit import Group, analyse, overlay
from rmink.drawing.font import text_width
from rmink.drawing.model import Dimension, Drawing, Element, LegendEntry
from rmink.drawing.render import default_legend, render_alternatives, render_drawing
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


BYGG = "Bygg"  # the area new drawings are filed under
AREAS = (BYGG, "Skola")  # folders under rmink that hold areas, not a drawing


def new_area(sketch: str) -> str:
    """The area a new drawing from the notebook ``sketch`` goes in: Bygg for a
    sketch in rmink or under rmink/Bygg, none for one in a folder of its own
    (rmink/Garage/skiss stays in rmink/Garage), so its revisions go beside it."""
    parts = [p for p in sketch.split("/") if p]
    if parts[:1] != ["rmink"] or len(parts) <= 2:
        return BYGG
    return parts[1] if parts[1] in AREAS else ""


def drawing_folder(name: str, area: str = "") -> str:
    """'/rmink/Bygg/Altan', or '/rmink/Altan' without an area."""
    return "/".join([RMINK_FOLDER, *(safe_name(p) for p in (area, name) if p)])


def make_folders(token: str, folder: str) -> list[cloud.Entry]:
    """The entries of ``folder``, made with the folders above it if missing."""
    try:
        return cloud.ls(token, folder)
    except cloud.CloudNotFoundError:
        pass
    path = ""
    for part in folder.strip("/").split("/"):
        path += "/" + part
        cloud.mkdir(token, path)  # a folder that is there counts as made
    return []


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


def rectify(
    drawing: Drawing, angle_tol: float = 12.0, join_tol: float = 12.0, kept_tol: float = 4.0
) -> Drawing:
    """Pull endpoints that almost meet onto one corner, then make nearly
    horizontal/vertical segments exact by giving their ends one shared y or x.
    Shared corners stay shared. Returns a new drawing.

    A hand sketch means its walls to meet at right angles, so a segment within
    ``angle_tol`` of an axis is squared. One with an angle dimension at either
    end is drawn at that angle on purpose (a roof pitch, a ramp): it is only
    squared within ``kept_tol``."""
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
    vertices = np.array([a.vertex for a in d.angles], dtype=float).reshape(-1, 2)

    def angled(k: int) -> bool:
        return bool(len(vertices)) and bool(
            (np.linalg.norm(vertices - before[k], axis=1) < join_tol).any()
        )

    # Each end of an open line, with the way its segment runs once squared.
    ends: dict[int, str] = {}
    k = 0
    for e in shapes:
        n = len(e.points)
        closing = [(n - 1, 0)] if e.closed and n > 2 else []
        for i, j in [(i - 1, i) for i in range(1, n)] + closing:
            a, b = k + i, k + j
            tol = kept_tol if angled(a) or angled(b) else angle_tol
            dx, dy = pts[b] - pts[a]
            ang = math.degrees(math.atan2(dy, dx)) % 180
            way = ""
            if min(ang, 180 - ang) < tol:
                uy(a, b)
                way = "h"
            elif abs(ang - 90) < tol:
                ux(a, b)
                way = "v"
            if way and not e.closed and i == 0:
                ends[a] = way
            if way and not e.closed and j == n - 1:
                ends[b] = way
        k += n
    average(0, fx)
    average(1, fy)

    # A hand-drawn corner often overshoots or stops short: a horizontal and a
    # vertical line whose ends are close meet where they cross.
    reach = 2.5 * join_tol
    for a, wa in ends.items():
        for b, wb in ends.items():
            if wa == "h" and wb == "v" and refs[a][0] is not refs[b][0]:
                if np.linalg.norm(pts[a] - pts[b]) < reach:
                    corner = np.array([pts[b][0], pts[a][1]])
                    for m in (a, b):
                        same = np.flatnonzero((np.abs(pts - pts[m]) < 1e-9).all(axis=1))
                        pts[same] = corner

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


FIT_TOP = 110.0  # px, where a fitted drawing starts (under the tablet's toolbar)
FIT_MARGIN = 50.0  # px left and right, room for dimensions and labels
FIT_HEIGHT = 0.6  # of the page height at most, so the title block fits below
FIT_FLOOR = 0.3  # of the page height: never smaller to make room for remarks
FIT_MIN = 1.1  # enlarge only when it gains at least this much


def _extent(drawing: Drawing) -> tuple[np.ndarray, np.ndarray] | None:
    """Bounding box of the drawing's geometry (not its texts' sizes)."""
    pts: list[tuple[float, float]] = []
    for e in drawing.elements:
        pts += e.points
        if e.center is not None and e.radius:
            cx, cy = e.center
            pts += [(cx - e.radius, cy - e.radius), (cx + e.radius, cy + e.radius)]
    for d in drawing.dimensions:
        pts += [d.start, d.end]
    for a in drawing.angles:
        pts += [a.vertex, a.start, a.end]
    for sym in drawing.symbols:
        x, y = sym.at
        pts += [(x - sym.size / 2, y - sym.size / 2), (x + sym.size / 2, y + sym.size / 2)]
    if not pts:
        return None
    arr = np.array(pts, dtype=float)
    return arr.min(axis=0), arr.max(axis=0)


def fit_to_page(
    drawing: Drawing, device: DeviceProfile, max_height: float | None = None
) -> Drawing:
    """Fit the drawing to the page width (and at most ``max_height`` px,
    :data:`FIT_HEIGHT` of the page by default) from the top, keeping its
    shape: a drawing sketched small is enlarged, one that runs off the page
    or is taller than allowed is shrunk. Sizes of texts, dimension offsets
    and angle arcs stay, and texts stay on the page; dimensions keep their
    values, so scale and measurements are unchanged. A drawing that already
    fits is returned as it is, so fitting twice changes nothing."""
    box = _extent(drawing)
    if box is None:
        return drawing
    lo, hi = box
    w, h = max(hi[0] - lo[0], 1.0), max(hi[1] - lo[1], 1.0)
    width = device.width - 2 * FIT_MARGIN
    tallest = max_height or device.height * FIT_HEIGHT
    k = min(width / w, tallest / h, 4.0)
    off_page = lo[0] < 0 or lo[1] < 0 or hi[0] > device.width or hi[1] > device.height
    # Must it change? Too big, off the page or too tall: yes. Too small: only
    # when it gains enough to be worth it.
    must = k < 0.98 or off_page
    texts = [e for e in drawing.elements if e.kind == "text" and e.points and e.text]

    def at(p):
        q = (np.asarray(p, dtype=float) - lo) * k + origin
        return (round(float(q[0]), 1), round(float(q[1]), 1))

    # Texts keep their size: shrink until the widest one stays on the page.
    while True:
        if not must and k < FIT_MIN:
            return drawing
        origin = np.array([FIT_MARGIN + (width - w * k) / 2, FIT_TOP])
        right = max((at(e.points[0])[0] + text_width(e.text, e.size) for e in texts), default=0.0)
        if right <= device.width - FIT_MARGIN / 2 or k < 0.2:
            break
        k *= 0.95

    d = drawing.model_copy(deep=True)
    for e in d.elements:
        e.points = [at(p) for p in e.points]
        if e.center is not None:
            e.center = at(e.center)
        if e.radius:
            e.radius = round(e.radius * k, 1)
    for dim in d.dimensions:
        dim.start, dim.end = at(dim.start), at(dim.end)
    for a in d.angles:
        a.vertex, a.start, a.end = at(a.vertex), at(a.start), at(a.end)
    for sym in d.symbols:
        sym.at, sym.size = at(sym.at), round(sym.size * k, 1)
    for ann in d.annotations:
        if ann.at is not None:
            ann.at = at(ann.at)
    return d


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
    """Write the clean revision (then a page of open alternatives, if any, and
    the sketch) as a notebook, and
    save the drawing with the ids of the strokes rmink wrote, in ``store``
    (the local drawings folder by default)."""
    device = get_device(drawing.sketch.device)
    drawing = drawing.model_copy(deep=True)
    if not drawing.legend:
        drawing.legend = [LegendEntry(key=k, meaning=m) for k, m in default_legend(drawing)]
    fitted = fit_to_page(drawing, device)
    floor = device.height * FIT_FLOOR
    for _ in range(4):
        # The remarks and their answer lines run past the page: make the
        # drawing smaller so the page stays one screen, which the tablet and
        # the desktop app show at full width. Labels and dimension offsets
        # keep their size, so it can take a few tries.
        over = render_drawing(fitted, device).height - device.height
        box = _extent(fitted)
        if over <= 0 or box is None:
            break
        tall = float(box[1][1] - box[0][1])
        if tall <= floor + 1:
            break
        fitted = fit_to_page(drawing, device, max_height=max(tall - over - 8, floor))
    drawing = fitted
    if not drawing.area:
        # Claude's JSON has no area: keep the saved drawing's, Bygg when new.
        saved = (store or FileStore()).load(drawing.name)
        drawing.area = saved.area if saved else new_area(drawing.sketch.document)
    clean = render_drawing(drawing, device)
    alternatives = render_alternatives(drawing, device)
    pages = [clean] + ([alternatives] if alternatives else [])
    pages += [sketch] if sketch is not None and sketch.strokes else []

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
    folder's ``Tidigare``: the previous revision as it is, the sketch of a first
    round (in ``/rmink`` or already in the drawing's folder) as
    "<name> r00 skiss" so it sorts first. Notebooks anywhere else are the
    user's and stay put.
    """
    d, store = rev.drawing, store or FileStore()
    folder = drawing_folder(d.name, d.area)
    inboxes = {RMINK_FOLDER, folder.rpartition("/")[0]}  # rmink and rmink/<area>
    read = d.sketch.document
    parent, _, base = read.rpartition("/")
    movable = (parent in inboxes or parent == folder) and not _GLOB.search(read)
    first = parent in inboxes or d.revision == 1
    archived_name = f"{safe_name(d.name)} r00 skiss" if first else base
    if movable and read == folder:
        # The sketch has the drawing's name; rmapi finds entries by name, so
        # free it before making the folder.
        renamed = f"{parent}/{archived_name}"
        cloud.mv(token, read, renamed)
        read = renamed
    entries = make_folders(token, folder)
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


def move_to_area(drawing: Drawing, area: str, token: str, store: Store | None = None) -> str:
    """Move a drawing's folder, with its revisions and Tidigare, into
    rmink/<area>/ and save it with its new paths. Returns the new folder."""
    store = store or FileStore()
    old = drawing_folder(drawing.name, drawing.area)
    moved = drawing.model_copy(deep=True)
    moved.area = area
    new = drawing_folder(moved.name, area)
    if old == new:
        return new
    make_folders(token, new.rpartition("/")[0])
    cloud.mv(token, old, new)
    for attr in ("sent_as", "document"):
        path = getattr(moved.sketch, attr)
        if path.startswith(old + "/"):
            setattr(moved.sketch, attr, new + path[len(old) :])
    store.save(moved)
    for e in cloud.ls(token, new):
        if e.folder and e.name == ARCHIVE:
            for old_rev in cloud.ls(token, f"{new}/{ARCHIVE}"):
                store.link(f"{new}/{ARCHIVE}/{old_rev.name}", moved.name)
        elif not e.folder:
            store.link(f"{new}/{e.name}", moved.name)
    return new


class NewMarksError(cloud.CloudError):
    """The current revision has marks a round has not read yet."""


def upgrade(drawing: Drawing, token: str, store: Store | None = None) -> str:
    """Send a drawing again drawn the current way (:func:`resend`), first
    filing it under rmink/Bygg/ if it was made before areas. Refuses, before changing
    anything, when the current revision has marks a round has not read.
    Returns the cloud path of the new revision."""
    device = get_device(drawing.sketch.device)
    page = read_rmdoc(cloud.get(token, drawing.sketch.sent_as), device).pages[0]
    written = set(drawing.sketch.written_ids)
    if any(s.id not in written for s in page.strokes):
        raise NewMarksError(f"{drawing.name} har nya markeringar på plattan. Kör nästa varv först.")
    if not drawing.area:
        move_to_area(drawing, BYGG, token, store)
        drawing = (store or FileStore()).load(drawing.name) or drawing
    return resend(drawing, token, store)


def resend(drawing: Drawing, token: str, store: Store | None = None) -> str:
    """Send the drawing again as its next revision, drawn the way rmink draws
    now (enlarged to the page, room to answer), with the sketch page of the
    current revision; the current one moves to Tidigare. Run it when the
    current revision has no new marks. Returns the cloud path."""
    device = get_device(drawing.sketch.device)
    current = read_rmdoc(cloud.get(token, drawing.sketch.sent_as), device)
    n = drawing.sketch.page
    sketch = current.pages[n] if len(current.pages) > n else None
    d = drawing.model_copy(deep=True)
    d.revision += 1
    d.date = datetime.date.today().isoformat()
    d.sketch.document = d.sketch.sent_as
    d.log.append(f"r{d.revision}: ny layout, större ritning och fler SVAR-rader")
    with tempfile.TemporaryDirectory() as tmp:
        rev = build_revision(d, Path(tmp) / f"{revision_title(d)}.rmdoc", sketch, store=store)
        return send_revision(rev, token, store)
