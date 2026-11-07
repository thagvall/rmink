"""Status lists: set status and who is responsible with crosses on the tablet.

A field round leaves numbered points on a sheet. This makes tablet pages with a
row per point: its number, an image of it, its text and boxes to cross. The boxes
are read by the workbooks' cross reading, so no model is needed. A row that is
unclear changes nothing and is reported, because a wrong status is worse than
asking. The layout travels in the notebook's PDF, as the sheet manifest does.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from importlib.metadata import version
from pathlib import Path

import pymupdf
from pydantic import BaseModel

from rmink.bridge.points import STATUSES, Points, point_image
from rmink.devices import DeviceProfile, get_device
from rmink.model import Stroke
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.workbook.model import AnswerField, Choice
from rmink.workbook.read import _bounds_pt, read_choices, read_ink

FORMAT = "rmink/sheet-status"
LAYOUT = "rmink.status.json"
MARGIN = 18.0
HEADER = 42.0
ROW = 128.0
PEOPLE_ROW = 26.0
IMAGE = (118.0, 96.0)
BOX = 16.0
PITCH = 23.0
SLACK = 6.0  # pt a stroke may lie outside the boxes of its row


class Row(BaseModel):
    point: str
    status: AnswerField
    responsible: AnswerField | None = None


class Layout(BaseModel):
    format: str = FORMAT
    version: int = 1
    rmink: str
    device: str
    name: str
    session: str  # of the points
    rows: list[Row]


def _boxes(
    page: pymupdf.Page,
    labels: list[str],
    x: float,
    y: float,
    columns: int,
    width: float,
    number: int,
    field_id: str,
) -> AnswerField:
    choices = []
    for i, label in enumerate(labels):
        bx = x + (i % columns) * width
        by = y + (i // columns) * PITCH
        box = pymupdf.Rect(bx, by, bx + BOX, by + BOX)
        page.draw_rect(box, color=(0, 0, 0), width=0.8)
        page.insert_text((box.x1 + 5, box.y1 - 4), label, fontsize=10)
        choices.append(Choice(text=label, rect=tuple(box)))
    rows = (len(labels) + columns - 1) // columns
    rect = (x, y, x + columns * width, y + (rows - 1) * PITCH + BOX)
    return AnswerField(id=field_id, prompt="", choices=choices, page=number, rect=rect)


def build_status_pdf(
    points: Points, sheet: bytes, device: DeviceProfile, people: list[str] | None = None
) -> tuple[bytes, Layout]:
    """Tablet pages with a row per point, and their layout embedded."""
    if not points.points:
        raise ValueError("There are no points to list")
    people = people or []
    width, height = device.width * 72 / device.dpi, device.height * 72 / device.dpi
    row_h = ROW + (PEOPLE_ROW if people else 0)
    per_page = int((height - HEADER - MARGIN) // row_h)
    labels = list(STATUSES)
    out = pymupdf.open()
    rows: list[Row] = []
    for n, p in enumerate(points.points):
        at = n % per_page
        if at == 0:
            page = out.new_page(width=width, height=height)
            page.insert_text((MARGIN, 28), f"Status · {points.name}", fontsize=15)
            page.insert_text((MARGIN, 40), "Kryssa en ruta per rad", fontsize=9)
        top = HEADER + at * row_h
        page.draw_line((MARGIN, top), (width - MARGIN, top), color=(0.6, 0.6, 0.6), width=0.5)
        number = p.id.removeprefix("P")
        page.insert_text((MARGIN, top + 18), number, fontsize=15)
        x = MARGIN + 24
        image = pymupdf.Rect(x, top + 6, x + IMAGE[0], top + 6 + IMAGE[1])
        page.insert_image(image, stream=point_image(sheet, p, dpi=90))
        page.draw_rect(image, color=(0.6, 0.6, 0.6), width=0.4)
        right = image.x1 + 10
        text = p.text or "(ingen text)"
        if p.unsure:
            text = f"[osäker] {text}"
        page.insert_textbox(
            pymupdf.Rect(right, top + 5, width - MARGIN, top + 38), text, fontsize=10
        )
        status = _boxes(
            page,
            labels,
            right,
            top + 40,
            2,
            (width - MARGIN - right) / 2,
            out.page_count - 1,
            f"{p.id}:status",
        )
        responsible = None
        if people:
            responsible = _boxes(
                page,
                people,
                MARGIN + 24,
                top + ROW - 4,
                len(people),
                (width - 2 * MARGIN - 24) / len(people),
                out.page_count - 1,
                f"{p.id}:responsible",
            )
        rows.append(Row(point=p.id, status=status, responsible=responsible))
    layout = Layout(
        rmink=version("rmink"),
        device=device.key,
        name=points.name,
        session=points.session,
        rows=rows,
    )
    out.embfile_add(LAYOUT, layout.model_dump_json().encode())
    return out.tobytes(garbage=3, deflate=True), layout


def write_status_notebook(
    points: Points,
    sheet: bytes,
    output: Path,
    device: DeviceProfile,
    people: list[str] | None = None,
    seed: int | None = None,
) -> int:
    """Write the notebook and return its number of pages."""
    pdf, _ = build_status_pdf(points, sheet, device, people)
    count = pymupdf.open(stream=pdf, filetype="pdf").page_count
    uuids = UuidFactory(seed)
    author = uuids()
    write_rmdoc(
        output,
        f"{points.name} status",
        [RmdocPage(b"") for _ in range(count)],
        [str(uuids()) for _ in range(count)],
        author,
        device,
        str(uuids()),
        now_ms=0 if seed is not None else None,
        pdf=pdf,
    )
    return count


@dataclass
class Read:
    points: Points
    changed: dict[str, str] = field(default_factory=dict)  # point -> what changed
    unclear: list[str] = field(default_factory=list)  # rows to look at


def _layout(notebook: bytes) -> Layout:
    with zipfile.ZipFile(io.BytesIO(notebook)) as zf:
        name = next((n for n in zf.namelist() if n.endswith(".pdf")), None)
        doc = pymupdf.open(stream=zf.read(name), filetype="pdf") if name else None
    if doc is None or LAYOUT not in doc.embfile_names():
        raise ValueError("This notebook is no status list from rmink")
    return Layout.model_validate_json(doc.embfile_get(LAYOUT))


def _in_field(strokes: list[Stroke], f: AnswerField, device: DeviceProfile) -> list[Stroke]:
    x0, y0, x1, y1 = f.rect
    out = []
    for s in strokes:
        a, b, c, d = _bounds_pt(s, device)
        cx, cy = (a + c) / 2, (b + d) / 2
        if x0 - SLACK <= cx <= x1 + SLACK and y0 - SLACK <= cy <= y1 + SLACK:
            out.append(s)
    return out


def _one(f: AnswerField, strokes: list[Stroke], device: DeviceProfile) -> tuple[str | None, bool]:
    """The crossed label and whether the field was clear."""
    ink = _in_field(strokes, f, device)
    if not ink:
        return None, True
    chosen = read_choices(f, ink, device)
    if chosen is None or len(chosen) > 1:
        return None, False
    return (f.choices[chosen[0]].text if chosen else None), True


def read_status(notebook: bytes, points: Points) -> Read:
    """The points with what was crossed on the status list."""
    layout = _layout(notebook)
    if layout.session != points.session:
        raise ValueError(f'This status list belongs to "{layout.name}", not these points')
    device = get_device(layout.device)
    ink = read_ink(notebook, device)
    result = Read(points.model_copy(deep=True))
    by_id = {p.id: p for p in result.points.points}
    for row in layout.rows:
        p = by_id.get(row.point)
        if p is None:
            continue
        strokes = ink.pages.get(row.status.page, [])
        status, clear = _one(row.status, strokes, device)
        changes = []
        if not clear:
            result.unclear.append(p.id)
        elif status and status != p.status:
            p.status = status
            changes.append(status)
        if row.responsible:
            who, clear = _one(row.responsible, strokes, device)
            if not clear:
                if p.id not in result.unclear:
                    result.unclear.append(p.id)
            elif who and who != p.responsible:
                p.responsible = who
                changes.append(who)
        if changes:
            result.changed[p.id] = ", ".join(changes)
    return result
