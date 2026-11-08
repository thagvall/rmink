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

import json
import math
import unicodedata
from dataclasses import dataclass, field

import numpy as np
import pymupdf

from rmink.devices import get_device
from rmink.drawing import workflow
from rmink.drawing.font import _letters, text_width
from rmink.drawing.model import Drawing, LegendEntry
from rmink.drawing.render import (
    _angle,
    _bbox_of,
    _dimension,
    _element_paths,
    _option,
    _Pen,
    _Style,
    default_legend,
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
OPTION_WIDTH = 1100.0  # px an alternative is laid out in
STATES = {"accepted": "Accepted", "rejected": "Rejected"}
LEGEND_HEAD = 8.0  # mm, the heading of the legend
LEGEND_ROW = 5.2  # mm a row
LEGEND_COL = 62.0  # mm a column at most
LEGEND_SAMPLE = 4.2  # mm, a symbol in the legend
DASHES = {"dashed": "[6 4] 0", "dotted": "[1 3] 0", "dashdot": "[8 3 1 3] 0"}


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
) -> pymupdf.Rect:
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
    return box


def _legend(
    page: pymupdf.Page, d: Drawing, pen: _Recorder, title: pymupdf.Rect, layer: int
) -> pymupdf.Rect | None:
    """The symbols and line kinds the drawing uses and what they mean, in the strip
    left of the title block, column by column; None when there is nothing to explain."""
    entries = d.legend or [LegendEntry(key=k, meaning=m) for k, m in default_legend(d)]
    if not entries:
        return None
    mm = PT_PER_MM
    room = title.x0 - MARGIN * mm
    col_w = min(LEGEND_COL * mm, room)
    if col_w < 30 * mm:
        return None
    rows = int((TITLE_H - LEGEND_HEAD) // LEGEND_ROW)
    cols = min(math.ceil(len(entries) / rows), int(room // col_w))
    shown = entries[: rows * cols]
    rest = len(entries) - len(shown)
    if rest:
        shown, rest = shown[:-1], rest + 1
    box = pymupdf.Rect(title.x0 - cols * col_w, title.y0, title.x0, title.y1)
    page.draw_rect(box, color=(0, 0, 0), width=0.7, oc=layer)
    page.insert_text((box.x0 + 8, box.y0 + 15), "Förklaring", fontsize=11, oc=layer)
    text_w = col_w - 16 * mm
    for i, entry in enumerate(shown):
        col, row = divmod(i, rows)
        x = box.x0 + col * col_w + 3 * mm
        y = box.y0 + (LEGEND_HEAD + (row + 0.75) * LEGEND_ROW) * mm
        mid = np.array([x + 5 * mm, y - 1.1 * mm])
        if entry.key.startswith("category:"):
            st = pen.style(entry.key.split(":", 1)[1])
            page.draw_line(
                pymupdf.Point(*(mid - (4.5 * mm, 0))),
                pymupdf.Point(*(mid + (4.5 * mm, 0))),
                color=tuple(c / 255 for c in st.rgb),
                width=max(st.width * PEN_MM, MIN_LINE) * mm,
                dashes=DASHES.get(st.line_type),
                oc=layer,
            )
        else:
            shape = page.new_shape()
            for p in symbol_paths(entry.key, (0.0, 0.0), LEGEND_SAMPLE * mm):
                shape.draw_polyline([pymupdf.Point(*(q + mid)) for q in p])
            shape.finish(
                color=(0, 0, 0), width=0.5, closePath=False, lineCap=1, lineJoin=1, oc=layer
            )
            shape.commit()
        label = plain(entry.meaning)
        while label and pymupdf.get_text_length(label, fontsize=8) > text_w:
            label = label[:-4].rstrip() + "..."
        page.insert_text((x + 12 * mm, y), label, fontsize=8, oc=layer)
    if rest:
        col, row = divmod(len(shown), rows)
        x = box.x0 + col * col_w + 3 * mm
        y = box.y0 + (LEGEND_HEAD + (row + 0.75) * LEGEND_ROW) * mm
        page.insert_text((x + 12 * mm, y), f"+ {rest} till", fontsize=8, oc=layer)
    return box


def _draw_part(doc, page, part: _Part, layer: int, to_sheet, k: float) -> None:
    shape = page.new_shape()
    dashes = DASHES
    for path, st, width in part.paths:
        shape.draw_polyline([to_sheet(p) for p in path])
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
        page.insert_text(
            to_sheet(at),
            label,
            fontsize=_font_size(label, text, size, k),
            color=tuple(c / 255 for c in st.rgb),
            morph=(to_sheet(at), pymupdf.Matrix(angle)) if angle else None,
            oc=layer,
        )


def _alternatives(
    doc, d: Drawing, alt, number: int, paper: tuple[float, float], frame: int, off: list[int]
) -> list[int]:
    """A page for one choice: its options in the same place, in layers of their
    own, so that an editor shows one at a time."""
    page = doc.new_page(width=paper[0] * PT_PER_MM, height=paper[1] * PT_PER_MM)
    m = MARGIN * PT_PER_MM
    r = page.rect
    page.draw_rect(
        pymupdf.Rect(m, m, r.width - m, r.height - m), color=(0, 0, 0), width=1.0, oc=frame
    )
    y = m + 26
    title = plain(f"Alternativ · {d.name}: {alt.question}")
    page.insert_text((m + 12, y), title, fontsize=15, oc=frame)
    if alt.chosen:
        y += 16
        page.insert_text((m + 12, y), plain(f"Valt: {alt.chosen}"), fontsize=10, oc=frame)
    y += 15
    hint = "Visa ett alternativ i taget i PDF-läsarens lagerpanel."
    page.insert_text((m + 12, y), plain(hint), fontsize=9, color=(0.4, 0.4, 0.4), oc=frame)
    if alt.note:
        y += 13
        page.insert_text((m + 12, y), plain(alt.note), fontsize=9, oc=frame)

    pens = []
    for opt in alt.options:
        pen = _Recorder(d, get_device("pro"))
        pen.on(opt.key)
        bottom = _option(pen, opt, 0.0, OPTION_WIDTH, 30.0)
        pens.append((opt, pen, bottom))
    room_w, room_h = r.width - 2 * m - 24, r.height - m - y - 24
    k = min(room_w / OPTION_WIDTH, room_h / max(b for _, _, b in pens))

    def to_sheet(p) -> pymupdf.Point:
        return pymupdf.Point(float(p[0]) * k + m + 12, float(p[1]) * k + y + 12)

    prefix = f"{number}" if number else ""
    first = alt.chosen if alt.chosen in {o.key for o in alt.options} else alt.options[0].key
    group = []
    for opt, pen, _ in pens:
        name = _layer_name(f"Alternativ {prefix}{opt.key} {opt.title}")[:60].strip()
        layer = doc.add_ocg(name)
        group.append(layer)
        if opt.key != first:
            off.append(layer)
        _draw_part(doc, page, pen.parts[opt.key], layer, to_sheet, k)
    return group


def _exclusive_layers(doc, groups: list[list[int]], off: list[int]) -> None:
    if groups:
        on = [x for x in doc.get_ocgs() if x not in off]
        doc.set_layer(-1, on=on, off=off, rbgroups=groups)


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
        _draw_part(doc, page, part, doc.add_ocg(_layer_name(part.layer)), to_sheet, k)

    frame = doc.add_ocg("Ritningshuvud")
    title = _title_block(page, d, n, paper, warnings, frame)
    legend = _legend(page, d, pen, title, doc.add_ocg("Forklaring"))
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

    sets = [a for a in d.alternatives if a.options]
    numbered = len(sets) > 1
    off: list[int] = []
    groups = [
        _alternatives(doc, d, alt, i if numbered else 0, (w_mm, h_mm), frame, off)
        for i, alt in enumerate(sets, start=1)
    ]
    _exclusive_layers(doc, groups, off)

    doc.set_metadata({"title": f"{d.name} r{d.revision:02d}", "creator": "rmink"})
    doc.embfile_add("rmink.drawing.json", d.model_dump_json().encode())
    # Where the drawing lies on the first page, so that marks on it can be tied to it,
    # and its legend, or its title block, which rmink sheet send pastes beside every tile.
    place = {"page": 0, "pt_per_px": k, "origin": [ox, oy], "legend": list(legend or title)}
    doc.embfile_add("rmink.placement.json", json.dumps(place).encode())
    return SheetPdf(doc.tobytes(garbage=3, deflate=True), n, paper, mm_per_px, warnings)
