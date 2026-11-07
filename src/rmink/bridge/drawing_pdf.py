"""Turn a clean drawing into a PDF sheet at a true scale.

A :class:`~rmink.drawing.model.Drawing` lives in tablet pixels, and its real size
comes from the written dimensions. Here it goes on a paper sheet at a standard
scale, with one PDF layer per category and the scale stored the standard way,
as a page viewport with a /Measure dictionary. A PDF editor can then measure it
and take it on to CAD, without anything of rmink in the file being needed.

The scale is only as good as the dimensions it is derived from: a sheet without
any is refused, and one that disagrees with them says so in its title block.
The geometry is a sketch cleaned up, not a survey, and the sheet says that too.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pymupdf

from rmink.devices import get_device
from rmink.drawing import workflow
from rmink.drawing.font import _letters, text_width
from rmink.drawing.model import Drawing
from rmink.drawing.render import (
    _angle,
    _bbox_of,
    _dimension,
    _element_paths,
    _Pen,
    _Style,
    symbol_paths,
)
from rmink.workbook.build import plain

PT_PER_MM = 72 / 25.4
PAPERS = {"a4": (210, 297), "a3": (297, 420), "a2": (420, 594), "a1": (594, 841)}
SCALES = (1, 2, 5, 10, 20, 25, 50, 75, 100, 200, 500)  # 1:N
MARGIN = 10.0  # mm around the frame
TITLE_H = 34.0  # mm, the title block
TITLE_W = 130.0
PEN_MM = 0.125  # mm of line per px of category width
MIN_LINE = 0.18  # mm
CAP_HEIGHT = 0.72  # of the font size in Helvetica
MIN_FONT = 5.0  # pt
FIT = 0.2  # share a text may grow or shrink to keep its width
STATES = {"accepted": "Accepted", "rejected": "Rejected"}


@dataclass
class _Part:
    layer: str
    paths: list[tuple[np.ndarray, _Style, float]] = field(default_factory=list)
    labels: list[tuple[str, tuple[float, float], float, float, _Style]] = field(
        default_factory=list
    )


class _Recorder(_Pen):
    """Keeps paths and real text apart, per layer, instead of making strokes."""

    def __init__(self, drawing: Drawing, device) -> None:
        super().__init__(drawing, device, "")
        self.parts: dict[str, _Part] = {}
        self.part: _Part | None = None

    def on(self, layer: str) -> None:
        self.part = self.parts.setdefault(layer, _Part(layer))

    def paths(self, paths, st, width=None) -> None:
        w = width or st.width
        for p in paths:
            self.part.paths.append((np.asarray(p, dtype=float), st, w))

    def text(self, text, at, size, st, angle=0.0) -> None:
        self.part.labels.append((text, (float(at[0]), float(at[1])), size, angle, st))


def _record(d: Drawing) -> _Recorder:
    # A colour device keeps the categories' colours; the page is not for a tablet.
    pen = _Recorder(d, get_device("pro"))
    labels = {c.name: c.label or c.name for c in d.categories}

    def name(category: str) -> str:
        return labels.get(category, category)

    for e in d.elements:
        pen.on(name(e.category))
        if e.kind == "text":
            if e.points and e.text:
                pen.text(e.text, e.points[0], e.size, pen.style(e.category))
            continue
        pen.paths(_element_paths(e), pen.style(e.category, e.line_type))
    for s in d.symbols:
        pen.on("Symboler")
        st = pen.style(s.category)
        pen.paths(symbol_paths(s.kind, s.at, s.size, s.rotation), st)
        if s.label:
            pen.text(s.label, (s.at[0] + s.size * 0.7, s.at[1] - s.size * 0.4), 18.0, st)
    for dim in d.dimensions:
        pen.on(name(dim.category))
        _dimension(pen, dim, 22.0)
    for ang in d.angles:
        pen.on(name(ang.category))
        _angle(pen, ang, 22.0)
    return pen


def _layer_name(name: str) -> str:
    """Plain letters: Open PDF Studio's DXF export drops a name in UTF-16 and strips
    å, ä and ö from others, and a wall on a layer called Brande helps nobody."""
    return unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()


def _font_size(label: str, text: str, size: float, k: float) -> float:
    """Helvetica at the height of the tablet lettering, within reason as wide as
    it, so text placed by its lettering stays centred or lined up."""
    high = size * k / CAP_HEIGHT
    wide = text_width(text, size) * k / max(pymupdf.get_text_length(label, fontsize=1), 1e-6)
    return max(min(max(wide, high * (1 - FIT)), high * (1 + FIT)), MIN_FONT)


def _bounds(pen: _Recorder) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for part in pen.parts.values():
        for p, _, _ in part.paths:
            xs += [p[:, 0].min(), p[:, 0].max()]
            ys += [p[:, 1].min(), p[:, 1].max()]
        for text, (x, y), size, _, _ in part.labels:
            xs += [x, x + len(text) * size * 0.7]
            ys += [y - size, y]
    return min(xs), min(ys), max(xs), max(ys)


def choose_sheet(
    width_mm: float, height_mm: float, paper: str = "a3", scale: int | None = None
) -> tuple[float, float, int]:
    """Paper (width, height, mm) and N for content of this real size: the largest
    standard scale that fits, on the paper turned the way that fits best."""
    if paper not in PAPERS:
        raise ValueError(f"Unknown paper {paper!r}; use {', '.join(PAPERS)}")
    short, long = PAPERS[paper]
    usable = []
    for w, h in ((long, short), (short, long)):
        usable.append((w, h, w - 2 * MARGIN - 4, h - 2 * MARGIN - TITLE_H - 4))
    scales = [scale] if scale else SCALES
    for n in scales:
        for w, h, uw, uh in usable:
            if width_mm / n <= uw and height_mm / n <= uh:
                return float(w), float(h), n
    if scale:
        raise ValueError(f"The drawing does not fit on {paper} at 1:{scale}")
    raise ValueError(f"The drawing does not fit on {paper} at any standard scale")


@dataclass
class SheetPdf:
    pdf: bytes
    scale: int
    paper: str
    mm_per_px: float
    warnings: list[str]


def _viewport(doc: pymupdf.Document, page: pymupdf.Page, n: int) -> None:
    """The scale as ISO 32000 stores it: real units per point, over the whole page."""
    per_point = n / PT_PER_MM
    measure = (
        f"<</Type/Measure/Subtype/RL/R(1:{n})"
        f"/X[<</Type/NumberFormat/U(mm)/C {per_point:.6f}/D 1>>]"
        f"/D[<</Type/NumberFormat/U(mm)/C 1/D 1>>]"
        f"/A[<</Type/NumberFormat/U(mm2)/C {per_point * per_point:.6f}/D 1>>]>>"
    )
    r = page.rect
    box = f"[0 0 {r.width:.3f} {r.height:.3f}]"
    doc.xref_set_key(
        page.xref, "VP", f"[<</Type/Viewport/Name(Ritning)/BBox{box}/Measure{measure}>>]"
    )


def _title_block(
    page: pymupdf.Page, d: Drawing, n: int, paper: str, warnings: list[str], layer: int
) -> None:
    r = page.rect
    m = MARGIN * PT_PER_MM
    frame = pymupdf.Rect(m, m, r.width - m, r.height - m)
    box = pymupdf.Rect(frame.x1 - TITLE_W * PT_PER_MM, frame.y1 - TITLE_H * PT_PER_MM, *frame.br)
    page.draw_rect(frame, color=(0, 0, 0), width=1.0, oc=layer)
    page.draw_rect(box, color=(0, 0, 0), width=0.7, oc=layer)
    x = box.x0 + 8
    y = box.y0 + 19

    def line(text: str, size: float, color=(0, 0, 0)) -> None:
        nonlocal y
        page.insert_text((x, y), text, fontsize=size, color=color, oc=layer)
        y += size + 3.5

    line(plain(d.name), 15)
    facts = [f"Rev {d.revision}", d.phase, d.date, f"Skala 1:{n}", paper.upper(), "Mått i mm"]
    line(plain("  ·  ".join(f for f in facts if f)), 9)
    line("Skiss renritad av rmink. Skalan är härledd ur skrivna mått.", 8)
    for w in warnings[:2]:
        line(plain(f"OBS: {w}"), 8, (0.76, 0.23, 0.13))


def drawing_pdf(d: Drawing, paper: str = "a3", scale: int | None = None) -> SheetPdf:
    """The drawing on a sheet at a true scale, with the drawing itself embedded."""
    check = workflow.check_dimensions(d)
    mm_per_px = check.get("scale_units_per_px")
    if not mm_per_px:
        raise ValueError("The drawing has no written measurements to take a scale from")
    warnings = [
        f"{r['text']} avviker {r['deviation_pct']:+.0f} % från skalan"
        for r in check["dimensions"]
        if not r["consistent"]
    ]
    pen = _record(d)
    x0, y0, x1, y1 = _bounds(pen)
    w_mm, h_mm, n = choose_sheet((x1 - x0) * mm_per_px, (y1 - y0) * mm_per_px, paper, scale)

    doc = pymupdf.open()
    page = doc.new_page(width=w_mm * PT_PER_MM, height=h_mm * PT_PER_MM)
    k = mm_per_px / n * PT_PER_MM  # pt on the sheet per px of the drawing
    room_w = page.rect.width - 2 * MARGIN * PT_PER_MM
    room_h = page.rect.height - (2 * MARGIN + TITLE_H) * PT_PER_MM
    ox = MARGIN * PT_PER_MM + (room_w - (x1 - x0) * k) / 2 - x0 * k
    oy = MARGIN * PT_PER_MM + (room_h - (y1 - y0) * k) / 2 - y0 * k

    def to_sheet(p) -> pymupdf.Point:
        return pymupdf.Point(float(p[0]) * k + ox, float(p[1]) * k + oy)

    for part in pen.parts.values():
        layer = doc.add_ocg(_layer_name(part.layer))
        shape = page.new_shape()
        for path, st, width in part.paths:
            shape.draw_polyline([to_sheet(p) for p in path])
            dashes = {"dashed": "[6 4] 0", "dotted": "[1 3] 0", "dashdot": "[8 3 1 3] 0"}
            shape.finish(
                color=tuple(c / 255 for c in st.rgb),
                width=max(width * PEN_MM, MIN_LINE) * PT_PER_MM,
                dashes=dashes.get(st.line_type),
                lineCap=1,
                lineJoin=1,
                closePath=False,
                oc=layer,
            )
        if part.paths:
            shape.commit()
        for text, at, size, angle, st in part.labels:
            label = plain(_letters(text))
            font = _font_size(label, text, size, k)
            page.insert_text(
                to_sheet(at),
                label,
                fontsize=font,
                color=tuple(c / 255 for c in st.rgb),
                morph=(to_sheet(at), pymupdf.Matrix(angle)) if angle else None,
                oc=layer,
            )

    frame = doc.add_ocg("Ritningshuvud")
    _title_block(page, d, n, paper, warnings, frame)
    _viewport(doc, page, n)

    taken: dict[tuple[int, int], int] = {}
    for number, ann in enumerate(d.annotations, start=1):
        place = _bbox_of(d, ann.targets) if ann.targets else None
        # Right of what it is about: the icon would hide what it marks.
        at = (place[1][0], place[0][1]) if place else ann.at
        if at is None or not ann.text:
            continue
        spot = to_sheet(at)
        key = (round(spot.x), round(spot.y))
        taken[key] = taken.get(key, -1) + 1
        icon = pymupdf.Point(min(spot.x + 14, page.rect.width - 30), spot.y + taken[key] * 22)
        comment = page.add_text_annot(icon, plain(f"{number}. {ann.text}"), icon="Comment")
        comment.set_info(title="rmink", subject=f"Anmärkning {number}")
        comment.update()
        doc.xref_set_key(comment.xref, "NM", pymupdf.get_pdf_str(f"rmink-remark-{ann.id}"))
        doc.xref_set_key(comment.xref, "RMINK_Targets", pymupdf.get_pdf_str(",".join(ann.targets)))
        if ann.status in STATES:
            reply = page.add_text_annot(pymupdf.Point(0, 0), ann.status)
            reply.set_flags(pymupdf.PDF_ANNOT_IS_HIDDEN)
            reply.update()
            doc.xref_set_key(reply.xref, "IRT", f"{comment.xref} 0 R")
            doc.xref_set_key(reply.xref, "State", pymupdf.get_pdf_str(STATES[ann.status]))
            doc.xref_set_key(reply.xref, "StateModel", pymupdf.get_pdf_str("Review"))

    doc.set_metadata({"title": f"{d.name} r{d.revision:02d}", "creator": "rmink"})
    doc.embfile_add("rmink.drawing.json", d.model_dump_json().encode())
    return SheetPdf(doc.tobytes(garbage=3, deflate=True), n, paper, mm_per_px, warnings)
