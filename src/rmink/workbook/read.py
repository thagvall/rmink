"""Read the ink on a workbook the tablet synced and sort it into answer boxes.

A PDF document's ``.content`` maps each page to a PDF page ("redir"); a page
the user added on the tablet has none and its ink is left out. Ink on rmink's
own "Handskrift" layer is handwriting an earlier round already read, kept
hidden, and the "Facit" layer is rmink's solutions, rewritten each revision;
everything else is new. New ink whose middle lies in a field's box
(a little enlarged) belongs to that field; the rest stays on the page as it is,
except dots from tapping links. Ink on a choice question that is done (right,
or graded in a test) stays too, as notes.

:func:`read_choices` reads the crosses in a choice question: ink in a box is
a cross, a box filled in or a line through a row takes it back. Anything else
(a ring round the text, ink between the rows) is left to Claude.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field

import numpy as np
import pymupdf

from rmink.devices import DeviceProfile
from rmink.ingest.rm import read_page
from rmink.model import Stroke
from rmink.workbook.build import FACIT_LAYER
from rmink.workbook.model import AnswerField, Workbook

HANDWRITING_LAYER = "Handskrift"
SLACK = 8.0  # pt a stroke's middle may lie outside its box
DOT = 4.0  # pt: smaller ink outside the boxes is a tap on a link
BOX_SLACK = 3.0  # pt a cross's middle may lie outside its choice box
FILLED = 0.5  # share of a choice box inked when it is filled in (taken back)
UNCLEAR = 0.3  # from here to FILLED, a cross or a filling is Claude's call


@dataclass
class Ink:
    pdf: bytes
    pages: dict[int, list[Stroke]]  # PDF page index -> strokes, device px
    name: str = ""
    added_pages: int = 0  # pages with ink the user added on the tablet


@dataclass
class Sorted:
    by_field: dict[str, list[Stroke]] = field(default_factory=dict)
    kept: dict[int, list[Stroke]] = field(default_factory=dict)  # earlier handwriting
    loose: dict[int, list[Stroke]] = field(default_factory=dict)  # new ink outside the boxes


def read_ink(data: bytes, device: DeviceProfile) -> Ink:
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        content_name = next(n for n in names if n.endswith(".content"))
        doc_id = content_name.removesuffix(".content")
        content = json.loads(zf.read(content_name))
        if content.get("fileType") != "pdf" or f"{doc_id}.pdf" not in names:
            raise ValueError("Not a workbook: the document has no PDF")
        meta_name = f"{doc_id}.metadata"
        meta = json.loads(zf.read(meta_name)) if meta_name in names else {}
        ink = Ink(zf.read(f"{doc_id}.pdf"), {}, meta.get("visibleName", ""))
        for entry in content.get("cPages", {}).get("pages", []):
            rm_name = f"{doc_id}/{entry['id']}.rm"
            if "deleted" in entry or rm_name not in names:
                continue
            strokes = read_page(zf.read(rm_name), device).strokes
            redir = (entry.get("redir") or {}).get("value")
            if redir is None:
                ink.added_pages += bool(strokes)
                continue
            ink.pages.setdefault(int(redir), []).extend(strokes)
    return ink


def _bounds_pt(stroke: Stroke, device: DeviceProfile) -> tuple[float, float, float, float]:
    k = 72 / device.dpi
    (x0, y0), (x1, y1) = stroke.points.min(axis=0) * k, stroke.points.max(axis=0) * k
    return float(x0), float(y0), float(x1), float(y1)


def sort_ink(ink: Ink, workbook: Workbook, device: DeviceProfile) -> Sorted:
    out = Sorted()
    boxes: dict[int, list[AnswerField]] = {}
    for f in workbook.fields():
        if f.rect is not None and workbook.open_for_answers(f):
            boxes.setdefault(f.page, []).append(f)
    for page, strokes in ink.pages.items():
        for s in strokes:
            if s.layer == FACIT_LAYER:
                continue
            if s.layer == HANDWRITING_LAYER:
                out.kept.setdefault(page, []).append(s)
                continue
            x0, y0, x1, y1 = _bounds_pt(s, device)
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            hit = next(
                (
                    f
                    for f in boxes.get(page, [])
                    if f.rect[0] - SLACK <= cx <= f.rect[2] + SLACK
                    and f.rect[1] - SLACK <= cy <= f.rect[3] + SLACK
                ),
                None,
            )
            if hit is not None:
                out.by_field.setdefault(hit.id, []).append(s)
            elif max(x1 - x0, y1 - y0) >= DOT:
                out.loose.setdefault(page, []).append(s)
    return out


def _inside(x: float, y: float, rect, slack: float) -> bool:
    return rect[0] - slack <= x <= rect[2] + slack and rect[1] - slack <= y <= rect[3] + slack


def coverage(strokes: list[Stroke], rect, device: DeviceProfile) -> float:
    """Share of ``rect`` (PDF points) the strokes cover, on a half-point grid."""
    step = 0.5
    x0, y0, x1, y1 = rect
    grid = np.zeros((int((y1 - y0) / step) + 1, int((x1 - x0) / step) + 1), dtype=bool)
    k = 72 / device.dpi
    for s in strokes:
        pts = s.points.astype(np.float64) * k
        if len(pts) > 1:
            # Samples every quarter point along the stroke.
            seg = np.diff(pts, axis=0)
            n = np.maximum(1, (np.hypot(seg[:, 0], seg[:, 1]) / 0.25).astype(int))
            pts = np.concatenate(
                [
                    pts[i] + seg[i] * np.linspace(0, 1, n[i], endpoint=False)[:, None]
                    for i in range(len(seg))
                ]
                + [pts[-1:]]
            )
        r = max(s.width * k / 2, 0.6) / step
        reach = int(np.ceil(r))
        cells = np.round((pts - (x0, y0)) / step).astype(int)
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                if dx * dx + dy * dy > r * r:
                    continue
                cx, cy = cells[:, 0] + dx, cells[:, 1] + dy
                ok = (cx >= 0) & (cy >= 0) & (cx < grid.shape[1]) & (cy < grid.shape[0])
                grid[cy[ok], cx[ok]] = True
    return float(grid.mean())


def read_choices(f: AnswerField, strokes: list[Stroke], device: DeviceProfile) -> list[int] | None:
    """The choices crossed in ``f``, or ``None`` when the ink is not clear
    enough to read without Claude."""
    in_box: dict[int, list[Stroke]] = {}
    struck: set[int] = set()
    for s in strokes:
        x0, y0, x1, y1 = _bounds_pt(s, device)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        box = next(
            (i for i, c in enumerate(f.choices) if c.rect and _inside(cx, cy, c.rect, BOX_SLACK)),
            None,
        )
        if box is not None:
            in_box.setdefault(box, []).append(s)
            continue
        row = next(
            (i for i, c in enumerate(f.choices) if c.row and c.row[1] <= cy <= c.row[3]), None
        )
        if row is not None:
            r = f.choices[row].row
            if x1 - x0 >= 0.5 * (r[2] - r[0]) and y1 - y0 <= r[3] - r[1]:
                struck.add(row)  # a line through the row
                continue
        if max(x1 - x0, y1 - y0) < DOT:
            continue
        return None
    chosen = []
    for i, box_strokes in sorted(in_box.items()):
        share = coverage(box_strokes, f.choices[i].rect, device)
        if UNCLEAR <= share < FILLED:
            return None
        if share < FILLED and i not in struck:
            chosen.append(i)
    return chosen


def field_png(pdf: bytes, f: AnswerField, strokes: list[Stroke], device: DeviceProfile) -> bytes:
    """The field's box with its new ink drawn on, as the user sees it."""
    doc = pymupdf.open(stream=pdf)
    page = doc[f.page]
    k = 72 / device.dpi
    for s in strokes:
        pts = [(float(x) * k, float(y) * k) for x, y in s.points]
        if len(pts) == 1:
            pts.append((pts[0][0] + 0.3, pts[0][1]))
        page.draw_polyline(pts, color=(0, 0, 0), width=max(s.width * k, 0.8))
    clip = pymupdf.Rect(f.rect) + (-SLACK, -SLACK, SLACK, SLACK)
    for s in strokes:  # ink that runs out of the box
        x0, y0, x1, y1 = _bounds_pt(s, device)
        clip |= pymupdf.Rect(x0 - 2, y0 - 2, x1 + 2, y1 + 2)
    return page.get_pixmap(clip=clip & page.rect, dpi=150).tobytes("png")
