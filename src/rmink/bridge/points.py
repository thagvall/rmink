"""Field rounds: turn the ink on a sheet into a numbered list of points.

Strokes are the wrong unit for a list: two written sentences are eighty strokes.
:func:`find_points` groups them into notes, deterministically and without a
model. Words lie further apart than lines, so the gaps differ per direction.
Parts of a note that stayed apart, because no two strokes came close enough,
join when their areas meet. Long strokes are shapes, such as rings, lines along
a wall and highlights: they join a note they touch and are a point of their own
otherwise.

Reading the handwriting is left to whoever calls this, through the images from
:func:`point_image`. :func:`write_points` then adds each point to the sheet as a
numbered comment beside the ink, which stays as it is, and :func:`points_csv`
gives the list for a spreadsheet.
"""

from __future__ import annotations

import csv
import io
import json

import numpy as np
import pymupdf
from pydantic import BaseModel

from rmink.bridge.ink_pdf import ERASERS, HIGHLIGHTERS, is_tap, notebook_manifest, stroke_key
from rmink.bridge.sheet import Manifest, unrotate
from rmink.devices import DeviceProfile, get_device
from rmink.drawing.fit import classify
from rmink.model import Stroke
from rmink.workbook.read import read_ink

FORMAT = "rmink/sheet-points"
WORD_GAP = 10.0  # mm on the tablet between strokes of one note, sideways
LINE_GAP = 4.0  # mm, up and down
SHAPE_GAP = 4.5  # mm a shape may lie from what it belongs to
LONG = 28.0  # mm: a stroke longer than this is a shape, not writing
SPECKS = 2  # stray strokes a shape may have and still count as that shape
UNSURE = "[osäker] "
PT_TO_MM = 25.4 / 72

# BEAst Effektivare granskning 3.0, as PDF review states. The last two have no
# state of their own and are kept only in /RMINK_Status.
STATUSES = {
    "Ny kommentar": None,
    "Avvisad": "Rejected",
    "Ska åtgärdas": "Accepted",
    "Har åtgärdats": "Completed",
    "Ny granskning": None,
    "Annat forum": None,
}


class Point(BaseModel):
    id: str  # "P1"
    sheet_page: int  # 0-based
    tablet_page: int  # 0-based
    rect: tuple[float, float, float, float]  # displayed sheet pt
    kind: str  # "note", "ring", "line" or "highlight"
    strokes: list[str]  # stroke ids on the sheet
    text: str = ""
    status: str = "Ny kommentar"
    responsible: str = ""
    unsure: bool = False


class Points(BaseModel):
    format: str = FORMAT
    version: int = 1
    session: str
    name: str
    points: list[Point]


def _bounds(s: Stroke) -> tuple[float, float, float, float]:
    (x0, y0), (x1, y1) = s.points.min(axis=0), s.points.max(axis=0)
    return float(x0), float(y0), float(x1), float(y1)


def _gaps(a, b) -> tuple[float, float]:
    return max(a[0] - b[2], b[0] - a[2]), max(a[1] - b[3], b[1] - a[3])


def group_notes(strokes: list[Stroke], device: DeviceProfile) -> list[list[int]]:
    """Indices of the strokes in each note, top to bottom."""
    mm = device.px_per_mm
    boxes = [_bounds(s) for s in strokes]
    parent = list(range(len(strokes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def shape(i: int) -> bool:
        x0, y0, x1, y1 = boxes[i]
        return max(x1 - x0, y1 - y0) > LONG * mm or strokes[i].pen in HIGHLIGHTERS

    for i in range(len(strokes)):
        for j in range(i + 1, len(strokes)):
            dx, dy = _gaps(boxes[i], boxes[j])
            if shape(i) or shape(j):
                near = dx <= SHAPE_GAP * mm and dy <= SHAPE_GAP * mm
            else:
                near = dx <= WORD_GAP * mm and dy <= LINE_GAP * mm
            if near:
                parent[find(i)] = find(j)

    groups: dict[int, list[int]] = {}
    for i in range(len(strokes)):
        groups.setdefault(find(i), []).append(i)
    notes = [g for g in groups.values() if not all(shape(i) for i in g)]
    shapes = [g for g in groups.values() if all(shape(i) for i in g)]

    def area(group: list[int]) -> tuple[float, float, float, float]:
        b = [boxes[i] for i in group]
        return (
            min(x[0] for x in b),
            min(x[1] for x in b),
            max(x[2] for x in b),
            max(x[3] for x in b),
        )

    merged = True
    while merged:
        merged = False
        for i, a in enumerate(notes):
            for b in notes[i + 1 :]:
                dx, dy = _gaps(area(a), area(b))
                if dx <= 0 and dy <= LINE_GAP * mm:
                    a.extend(b)
                    notes.remove(b)
                    merged = True
                    break
            if merged:
                break
    return sorted(notes + shapes, key=lambda g: area(g)[1])


def _kind(strokes: list[Stroke], device: DeviceProfile) -> str:
    if all(s.pen in HIGHLIGHTERS for s in strokes):
        return "highlight"

    def size(s: Stroke) -> float:
        x0, y0, x1, y1 = _bounds(s)
        return max(x1 - x0, y1 - y0)

    longest = max(strokes, key=size)
    if size(longest) > LONG * device.px_per_mm and len(strokes) - 1 <= SPECKS:
        return "line" if classify(longest.points)[0] == "line" else "ring"
    return "note"


def find_points(notebook: bytes) -> Points:
    """The notes on a notebook from ``rmink sheet send``, numbered sheet by sheet."""
    manifest: Manifest = notebook_manifest(notebook)
    device = get_device(manifest.device)
    ink = read_ink(notebook, device)
    px = 72 / device.dpi
    points: list[Point] = []
    for tile in manifest.tiles:
        strokes = [
            s
            for s in ink.pages.get(tile.tablet_page, [])
            if s.pen not in ERASERS and s.id is not None and not is_tap(s, tile, px)
        ]
        for group in group_notes(strokes, device):
            members = [strokes[i] for i in group]
            pts = np.vstack([s.points for s in members])
            x0, y0 = tile.to_sheet(*(pts.min(axis=0) * px))
            x1, y1 = tile.to_sheet(*(pts.max(axis=0) * px))
            points.append(
                Point(
                    id=f"P{len(points) + 1}",
                    sheet_page=tile.sheet_page,
                    tablet_page=tile.tablet_page,
                    rect=(float(x0), float(y0), float(x1), float(y1)),
                    kind=_kind(members, device),
                    strokes=[stroke_key(manifest, tile.tablet_page, s) for s in members],
                )
            )
    return Points(session=manifest.session, name=manifest.name, points=points)


def point_image(sheet: bytes, point: Point, margin: float = 20.0, dpi: int = 150) -> bytes:
    """A PNG of the point on the sheet with its ink; ``sheet`` is a result of ``pull``."""
    doc = pymupdf.open(stream=sheet, filetype="pdf")
    page = doc[point.sheet_page]
    x0, y0, x1, y1 = point.rect
    clip = pymupdf.Rect(x0 - margin, y0 - margin, x1 + margin, y1 + margin) & page.rect
    return page.get_pixmap(dpi=dpi, clip=clip).tobytes("png")


def _key(doc: pymupdf.Document, xref: int, key: str, text: str) -> None:
    doc.xref_set_key(xref, key, pymupdf.get_pdf_str(text))


def _comment(page: pymupdf.Page, at: pymupdf.Point, text: str) -> pymupdf.Annot:
    annot = page.add_text_annot(at * unrotate(page), text, icon="Comment")
    annot.set_info(title="rmink", content=text)
    return annot


def write_points(sheet: bytes, points: Points) -> tuple[bytes, int, int]:
    """Add the points as comments in a layer of their own, each with a number
    beside its ink. Returns the PDF, how many were added and how many were
    there already. A point already there keeps what was done to it since."""
    doc = pymupdf.open(stream=sheet, filetype="pdf")
    layer_name = f"Punkter {points.name}"
    known = {o["name"]: xref for xref, o in doc.get_ocgs().items()}
    layer = known.get(layer_name) or doc.add_ocg(layer_name)
    added = skipped = 0
    for p in points.points:
        if p.status not in STATUSES:
            raise ValueError(f"{p.id}: unknown status {p.status!r}")
        page = doc[p.sheet_page]
        name = f"rmink-point-{points.session}-{p.id}"
        if any(a.info.get("id") == name for a in page.annots()):
            skipped += 1
            continue
        number = p.id.removeprefix("P")
        text = f"{UNSURE if p.unsure else ''}{number}. {p.text}".strip()
        x0, y0, x1, y1 = p.rect
        # Beside the ink and its number: the icon would hide what it marks.
        icon_x = x1 + 12 + 8 * len(number)
        comment = _comment(page, pymupdf.Point(icon_x, y0), text)
        comment.set_info(title=p.responsible or "rmink", subject=f"Punkt {number}", content=text)
        comment.set_oc(layer)
        comment.update()
        _key(doc, comment.xref, "NM", name)
        _key(doc, comment.xref, "RMINK_Status", p.status)
        _key(doc, comment.xref, "RMINK_Strokes", json.dumps(p.strokes))
        if STATUSES[p.status]:
            _add_state(doc, page, comment.xref, p.status)
        side = pymupdf.Rect(x1 + 3, y0, x1 + 5 + 8 * len(number) + 6, y0 + 15) * unrotate(page)
        label = page.add_freetext_annot(
            side, number, fontsize=11, text_color=(0.76, 0.23, 0.13), rotate=page.rotation,
            fill_color=(1, 1, 1), align=pymupdf.TEXT_ALIGN_CENTER,
        )  # fmt: skip
        label.set_info(title="rmink", subject=f"Punkt {number}")
        label.set_oc(layer)
        label.update()
        _key(doc, label.xref, "NM", f"{name}-nr")
        added += 1
    return doc.tobytes(garbage=1, deflate=True), added, skipped


def _state_replies(doc: pymupdf.Document, page: pymupdf.Page, xref: int) -> list[pymupdf.Annot]:
    target = f"{xref} 0 R"
    return [
        a
        for a in page.annots()
        if doc.xref_get_key(a.xref, "IRT")[1] == target
        and doc.xref_get_key(a.xref, "State")[0] != "null"
    ]


def _add_state(doc: pymupdf.Document, page: pymupdf.Page, xref: int, status: str) -> None:
    reply = page.add_text_annot(pymupdf.Point(0, 0), status)
    reply.set_flags(pymupdf.PDF_ANNOT_IS_HIDDEN)
    reply.update()
    doc.xref_set_key(reply.xref, "IRT", f"{xref} 0 R")
    doc.xref_set_key(reply.xref, "State", pymupdf.get_pdf_str(STATUSES[status]))
    doc.xref_set_key(reply.xref, "StateModel", pymupdf.get_pdf_str("Review"))


def update_points(sheet: bytes, points: Points) -> tuple[bytes, list[str]]:
    """Set status and responsible on points already on the sheet. Returns the PDF
    and the ids that are not on it, which are left out."""
    doc = pymupdf.open(stream=sheet, filetype="pdf")
    missing = []
    for p in points.points:
        if p.status not in STATUSES:
            raise ValueError(f"{p.id}: unknown status {p.status!r}")
        page = doc[p.sheet_page]
        name = f"rmink-point-{points.session}-{p.id}"
        comment = next((a for a in page.annots() if a.info.get("id") == name), None)
        if comment is None:
            missing.append(p.id)
            continue
        xref = comment.xref
        if p.responsible:
            doc.xref_set_key(xref, "T", pymupdf.get_pdf_str(p.responsible))
        _key(doc, xref, "RMINK_Status", p.status)
        for reply in _state_replies(doc, page, xref):
            page.delete_annot(reply)
        if STATUSES[p.status]:
            _add_state(doc, page, xref, p.status)
    return doc.tobytes(garbage=1, deflate=True), missing


def points_csv(points: Points) -> str:
    """The list for a spreadsheet; a Swedish Excel opens this without an import step."""
    out = io.StringIO()
    out.write("\ufeff")
    w = csv.writer(out, delimiter=";")
    w.writerow(["Nr", "Blad", "X mm", "Y mm", "Text", "Typ", "Status", "Ansvarig", "Osäker"])
    for p in points.points:
        x, y = p.rect[0] * PT_TO_MM, p.rect[1] * PT_TO_MM
        w.writerow(
            [
                p.id.removeprefix("P"),
                p.sheet_page + 1,
                f"{x:.0f}",
                f"{y:.0f}",
                p.text,
                p.kind,
                p.status,
                p.responsible,
                "ja" if p.unsure else "",
            ]
        )
    return out.getvalue()
