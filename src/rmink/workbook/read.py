"""Read the ink on a workbook the tablet synced and sort it into answer boxes.

A PDF document's ``.content`` maps each page to a PDF page ("redir"); a page
the user added on the tablet has none and its ink is left out. Ink on rmink's
own "Handskrift" layer is handwriting an earlier round already read, kept
hidden; everything else is new. New ink whose middle lies in a field's box
(a little enlarged) belongs to that field; the rest stays on the page as it is,
except dots from tapping links.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field

import pymupdf

from rmink.devices import DeviceProfile
from rmink.ingest.rm import read_page
from rmink.model import Stroke
from rmink.workbook.model import AnswerField, Workbook

HANDWRITING_LAYER = "Handskrift"
SLACK = 8.0  # pt a stroke's middle may lie outside its box
DOT = 4.0  # pt: smaller ink outside the boxes is a tap on a link


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
        if f.rect is not None:
            boxes.setdefault(f.page, []).append(f)
    for page, strokes in ink.pages.items():
        for s in strokes:
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
