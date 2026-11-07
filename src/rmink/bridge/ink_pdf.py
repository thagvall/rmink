"""Put ink from the tablet back on the sheet as PDF annotations.

Each stroke becomes one /Ink annotation, because Open PDF Studio reads only the
first stroke of an /Ink. It stays ordinary PDF: other readers draw /InkList with
/BS. The ``OPS_`` keys add the pen pressure in Open PDF Studio and are ignored
elsewhere. /NM and /RMINK_Id come from the stroke's id on the tablet, so pulling
a notebook twice adds nothing. Nothing is ever removed from the sheet: a stroke
erased on the tablet after a pull stays. A dot on a button is a tap, not ink.

The sheet keeps a record of its rounds in an embedded file, which also ties it
to the source when an editor has changed the file since.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field

import numpy as np
import pymupdf
from pydantic import BaseModel
from rmscene.scene_items import Pen
from rmscene.scene_stream import UnreadableBlock, read_blocks

from rmink.bridge.sheet import MANIFEST, Manifest, Tile, read_manifest, unrotate
from rmink.devices import COLOR_PALETTE, get_device
from rmink.model import Stroke
from rmink.workbook.read import DOT, read_ink

FORMAT = "rmink/sheet-ink"
ERASERS = {Pen.ERASER, Pen.ERASER_AREA}
HIGHLIGHTERS = {Pen.HIGHLIGHTER_1, Pen.HIGHLIGHTER_2}
# Pens whose line does not follow the pressure on the tablet.
EVEN_PENS = {Pen.FINELINER_1, Pen.FINELINER_2, Pen.MARKER_1, Pen.MARKER_2} | HIGHLIGHTERS
MIN_WIDTH = 0.1  # pt
COLORS = {e.color: e.rgb for e in COLOR_PALETTE}
HIGHLIGHT_RGB = (255, 225, 60)


class Round(BaseModel):
    session: str
    name: str
    device: str
    rmink: str
    strokes: int


class Record(BaseModel):
    format: str = FORMAT
    version: int = 1
    source_sha256: str
    rounds: list[Round] = []


@dataclass
class Pulled:
    pdf: bytes
    added: int = 0
    skipped: int = 0  # strokes already on the sheet
    layers: list[str] = field(default_factory=list)
    pages: dict[int, int] = field(default_factory=dict)  # sheet page -> strokes added
    added_pages: int = 0  # tablet pages the user added, which have no place on the sheet
    unread: int = 0  # blocks on the tablet pages that could not be read; ink may be missing


def notebook_manifest(notebook: bytes) -> Manifest:
    with zipfile.ZipFile(io.BytesIO(notebook)) as zf:
        pdf = next((n for n in zf.namelist() if n.endswith(".pdf")), None)
        data = read_manifest(zf.read(pdf)) if pdf else None
    if data is None:
        raise ValueError("This notebook was not made by rmink sheet send")
    return Manifest.model_validate(data)


def _unread(notebook: bytes) -> int:
    with zipfile.ZipFile(io.BytesIO(notebook)) as zf:
        pages = [zf.read(n) for n in zf.namelist() if n.endswith(".rm")]
    return sum(isinstance(b, UnreadableBlock) for p in pages for b in read_blocks(io.BytesIO(p)))


def _record(sheet: bytes, doc: pymupdf.Document, manifest: Manifest) -> Record:
    """The sheet's record, after checking that this is the sheet the notebook came from."""
    wanted = manifest.source.sha256
    data = read_manifest(sheet)
    if data is not None and data.get("format") == FORMAT:
        record = Record.model_validate(data)
        if record.source_sha256 == wanted:
            return record
    elif hashlib.sha256(sheet).hexdigest() == wanted:
        return Record(source_sha256=wanted)
    raise ValueError(f'This is not the sheet "{manifest.source.name}" the notebook was made from')


def _rgb(stroke: Stroke) -> tuple[float, float, float]:
    if stroke.rgba:
        rgb = stroke.rgba[:3]
    elif stroke.pen in HIGHLIGHTERS:
        rgb = COLORS.get(stroke.color, HIGHLIGHT_RGB)
    else:
        rgb = COLORS.get(stroke.color, (0, 0, 0))
    return tuple(c / 255 for c in rgb)


def _layer(doc: pymupdf.Document, name: str) -> int:
    known = {o["name"]: xref for xref, o in doc.get_ocgs().items()}
    return known.get(name) or doc.add_ocg(name)


def _layer_name(manifest: Manifest, tablet_layer: str) -> str:
    base = f"Bläck {manifest.name}"
    return base if tablet_layer == "Layer 1" else f"{base} · {tablet_layer}"


def _existing(page: pymupdf.Page) -> set[str]:
    return {a.info.get("id", "") for a in page.annots(types=[pymupdf.PDF_ANNOT_INK])}


def _user_unit(doc: pymupdf.Document, page: pymupdf.Page) -> float:
    kind, value = doc.xref_get_key(page.xref, "UserUnit")
    return float(value) if kind == "real" or kind == "int" else 1.0


def _is_tap(stroke: Stroke, tile: Tile, px: float) -> bool:
    (x0, y0), (x1, y1) = stroke.points.min(axis=0) * px, stroke.points.max(axis=0) * px
    x, y = (x0 + x1) / 2, (y0 + y1) / 2
    return max(x1 - x0, y1 - y0) < DOT and any(
        r[0] <= x <= r[2] and r[1] <= y <= r[3] for r in tile.links
    )


def add_stroke(
    doc: pymupdf.Document,
    page: pymupdf.Page,
    points: list[tuple[float, float]],
    pressures: list[float] | None,
    width: float,
    stroke: Stroke,
    layer: int,
    stroke_id: str,
) -> None:
    """One /Ink annotation; ``points`` and ``width`` in displayed sheet points."""
    if len(points) == 1:  # a dot; an /Ink line needs two points
        x, y = points[0]
        points = [(x, y), (x + 0.01, y)]
        pressures = pressures * 2 if pressures else None
    derotate = unrotate(page)
    raw = [tuple(pymupdf.Point(p) * derotate) for p in points]
    annot = page.add_ink_annot([raw])
    annot.set_border(width=max(width / _user_unit(doc, page), MIN_WIDTH))
    annot.set_colors(stroke=_rgb(stroke))
    annot.set_info(title="rmink", subject="Bläck")
    annot.set_oc(layer)
    annot.update(opacity=0.4 if stroke.pen in HIGHLIGHTERS else 1.0)
    xref = annot.xref
    doc.xref_set_key(xref, "NM", pymupdf.get_pdf_str(f"rmink-{stroke_id}"))
    doc.xref_set_key(xref, "RMINK_Id", pymupdf.get_pdf_str(stroke_id))
    if pressures:
        values = " ".join(f"{p:.3f}" for p in pressures)
        doc.xref_set_key(xref, "OPS_InkPressure", f"[{values}]")
        if stroke.pen in EVEN_PENS:
            doc.xref_set_key(xref, "OPS_InkPressureOff", "true")


def pull(notebook: bytes, sheet: bytes) -> Pulled:
    """The sheet with the notebook's ink added. ``sheet`` is the source PDF, or
    an earlier result of this function, also after editing it elsewhere."""
    manifest = notebook_manifest(notebook)
    device = get_device(manifest.device)
    ink = read_ink(notebook, device)
    doc = pymupdf.open(stream=sheet, filetype="pdf")
    record = _record(sheet, doc, manifest)
    result = Pulled(b"", added_pages=ink.added_pages, unread=_unread(notebook))
    seen: dict[int, set[str]] = {}

    for tablet_page, strokes in sorted(ink.pages.items()):
        tile = manifest.tile(tablet_page)
        if tile is None:
            continue
        page = doc[tile.sheet_page]
        known = seen.setdefault(tile.sheet_page, _existing(page))
        px = 72 / device.dpi
        scale = float(np.hypot(tile.matrix[0], tile.matrix[1])) * px
        for s in strokes:
            if s.pen in ERASERS or s.id is None or _is_tap(s, tile, px):
                continue
            stroke_id = f"{manifest.session}:{tablet_page}:{s.id[0]}:{s.id[1]}"
            if f"rmink-{stroke_id}" in known:
                result.skipped += 1
                continue
            name = _layer_name(manifest, s.layer)
            if name not in result.layers:
                result.layers.append(name)
            points = [tile.to_sheet(float(x) * px, float(y) * px) for x, y in s.points]
            pressures = None if s.pressures is None else (s.pressures / 255).clip(0, 1).tolist()
            add_stroke(
                doc, page, points, pressures, s.width * scale, s, _layer(doc, name), stroke_id
            )
            known.add(f"rmink-{stroke_id}")
            result.added += 1
            result.pages[tile.sheet_page] = result.pages.get(tile.sheet_page, 0) + 1

    done = next((r for r in record.rounds if r.session == manifest.session), None)
    if done:
        done.strokes += result.added
    else:
        record.rounds.append(
            Round(
                session=manifest.session,
                name=manifest.name,
                device=manifest.device,
                rmink=manifest.rmink,
                strokes=result.added,
            )
        )
    payload = json.dumps(record.model_dump(), ensure_ascii=False, indent=1).encode()
    if MANIFEST in doc.embfile_names():
        doc.embfile_del(MANIFEST)
    doc.embfile_add(MANIFEST, payload)
    result.pdf = doc.tobytes(garbage=1, deflate=True)
    return result
