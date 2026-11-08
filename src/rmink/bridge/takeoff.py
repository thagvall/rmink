"""Quantities with the pen: lengths and counts from ink on a sheet at a known scale.

On a sheet with a scale, a straight stroke along a wall is a length, and a small
cross or ring is one of something. :func:`find_quantities` reads them from a
notebook from ``rmink sheet send``, deterministically and without a model.
Everything else, such as writing, is left alone. A line with writing right
beside it is taken for an underline and left alone too.

The scale is the sheet's own, as a PDF viewport with a /Measure dictionary, the
way ``rmink sheet drawing`` and CAD programs write it. On a sheet from ``rmink
sheet drawing`` a length along a wall takes the wall's category, and a mark on a
symbol counts as that symbol; elsewhere marks count by their shape.

:func:`write_quantities` adds them as measurements and count markers that a PDF
editor lists and totals, in a layer of their own; the ink stays as it is. A
length is what the hand drew, not the wall: the result says so.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from collections import Counter

import numpy as np
import pymupdf
from pydantic import BaseModel

from rmink import knowledge
from rmink.bridge.ink_pdf import ERASERS, notebook_manifest, off_sheet, stroke_key
from rmink.bridge.sheet import Manifest, unrotate
from rmink.devices import DeviceProfile, get_device
from rmink.drawing.fit import classify
from rmink.model import Stroke
from rmink.workbook.read import read_ink

FORMAT = "rmink/sheet-takeoff"
PLACEMENT = "rmink.placement.json"
DRAWING = "rmink.drawing.json"
MIN_LINE = 15.0  # mm on the tablet: a shorter straight stroke is no length
MARK_MIN, MARK_MAX = 2.0, 15.0  # mm, the size of a cross or ring
CROSS_ANGLE = 40.0  # degrees two strokes of a cross must at least differ
STRAIGHT = 0.25  # of a stroke's length it may bend and still be a straight stroke
ENDS = 0.15  # of a stroke's length at each end where it may hook
CLEAR = 3.0  # mm of space around a mark: an x in a word is no cross
UNDERLINE = 2.5  # mm: writing this close to a line makes it an underline
ALONG = 4.0  # mm on the sheet a length may lie from a wall and follow it
ALONG_ANGLE = 8.0  # degrees
PT_TO_MM = 25.4 / 72
COLORS = [(0.88, 0.11, 0.28), (0.15, 0.39, 0.92), (0.09, 0.64, 0.29), (0.85, 0.47, 0.02)]
RADIUS = 9.0  # pt, the count marker as Open PDF Studio draws it


class Quantity(BaseModel):
    id: str  # "L1" for a length, "A1" for a count
    kind: str  # "length" or "count"
    group: str  # what it is: "Bärande", "Linje", "Kryss", "Uttag", ...
    sheet_page: int  # 0-based
    tablet_page: int  # 0-based
    points: list[tuple[float, float]]  # displayed sheet pt: two for a length, one for a count
    value: float  # mm for a length, 1 for a count
    unit: str  # "mm" or "st"
    strokes: list[str]
    symbol: str = ""  # the rmink symbol a count is on, as in knowledge/symbols.toml


class Takeoff(BaseModel):
    format: str = FORMAT
    version: int = 1
    session: str
    name: str
    scales: dict[int, str] = {}  # sheet page -> "1:25"
    quantities: list[Quantity] = []
    ignored: int = 0  # strokes that were neither, such as writing
    underlines: int = 0  # straight strokes taken for underlines
    unscaled: int = 0  # marks on sheet pages without a scale

    def totals(self) -> list[tuple[str, str, int, float]]:
        """(kind, group, how many, sum) per group, lengths first."""
        sums: dict[tuple[str, str], list[float]] = {}
        for q in self.quantities:
            sums.setdefault((q.kind, q.group), []).append(q.value)
        order = sorted(sums, key=lambda k: (k[0] != "length", k[1]))
        return [(k, g, len(sums[(k, g)]), float(sum(sums[(k, g)]))) for k, g in order]


class Scale(BaseModel):
    per_unit: float  # real units per unit of user space
    unit: str
    ratio: str  # "1:25"


def _resolve(doc: pymupdf.Document, text: str, depth: int = 4) -> str:
    for _ in range(depth):
        refs = re.findall(r"(\d+) 0 R", text)
        if not refs:
            break
        text = re.sub(
            r"(\d+) 0 R", lambda m: doc.xref_object(int(m.group(1)), compressed=True), text
        )
    return text


def page_scale(doc: pymupdf.Document, page: pymupdf.Page) -> Scale | None:
    """The scale of the page's first viewport with a /Measure, if it has one."""
    kind, value = doc.xref_get_key(page.xref, "VP")
    if kind == "null":
        return None
    text = _resolve(doc, value)
    x = re.search(r"/X\s*\[\s*<<(.*?)>>", text, re.S)
    if not x:
        return None
    c = re.search(r"/C\s+([0-9.eE+-]+)", x.group(1))
    u = re.search(r"/U\s*\(([^)]*)\)", x.group(1))
    r = re.search(r"/R\s*\(([^)]*)\)", text)
    if not c:
        return None
    return Scale(
        per_unit=float(c.group(1)), unit=u.group(1) if u else "", ratio=r.group(1) if r else ""
    )


def fixed_scale(n: int) -> Scale:
    """1:N on a sheet that does not say its scale, in mm."""
    return Scale(per_unit=n * PT_TO_MM, unit="mm", ratio=f"1:{n}")


# --- what the strokes are ----------------------------------------------------


def _size(s: Stroke) -> float:
    (x0, y0), (x1, y1) = s.points.min(axis=0), s.points.max(axis=0)
    return float(max(x1 - x0, y1 - y0))


def _box(s: Stroke, pad: float = 0.0) -> tuple[float, float, float, float]:
    (x0, y0), (x1, y1) = s.points.min(axis=0), s.points.max(axis=0)
    return float(x0 - pad), float(y0 - pad), float(x1 + pad), float(y1 + pad)


def _meet(a, b) -> bool:
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def _straight(s: Stroke) -> tuple[np.ndarray, np.ndarray] | None:
    """The chord of a stroke that does not bend away from it. The ends are left
    out: a pen often hooks as it lands or lifts."""
    p = s.points.astype(float)
    run = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    if run[-1] > 0:
        keep = (run >= ENDS * run[-1]) & (run <= (1 - ENDS) * run[-1])
        p = p[keep] if keep.sum() >= 2 else p
    a, b = p[0], p[-1]
    length = float(np.linalg.norm(b - a))
    if length == 0:
        return None
    d = (b - a) / length
    off = np.abs((p[:, 0] - a[0]) * d[1] - (p[:, 1] - a[1]) * d[0])
    return (a, b) if off.max() <= STRAIGHT * length else None


def _crosses(a: tuple, b: tuple) -> float | None:
    """The angle between two chords that cross each other, in degrees."""
    (p, p2), (q, q2) = a, b
    r, s = p2 - p, q2 - q
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((q - p)[0] * s[1] - (q - p)[1] * s[0]) / den
    u = ((q - p)[0] * r[1] - (q - p)[1] * r[0]) / den
    if not (0 <= t <= 1 and 0 <= u <= 1):
        return None
    cos = abs(float(np.dot(r, s))) / (np.linalg.norm(r) * np.linalg.norm(s))
    return math.degrees(math.acos(min(cos, 1.0)))


def _distance(points: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    d = b - a
    t = np.clip(((points - a) @ d) / max(float(d @ d), 1e-9), 0, 1)
    return np.linalg.norm(points - (a + t[:, None] * d), axis=1)


def read_marks(strokes: list[Stroke], device: DeviceProfile) -> tuple[list, int, int]:
    """("line", [i], (a, b)), ("cross", [i, j], centre) and ("ring", [i], centre) in
    tablet px, plus how many strokes were left and how many lines were underlines."""
    mm = device.px_per_mm
    small = [i for i, s in enumerate(strokes) if MARK_MIN * mm <= _size(s) <= MARK_MAX * mm]
    short = [i for i, s in enumerate(strokes) if _size(s) < MIN_LINE * mm]
    marks: list = []
    used: set[int] = set()

    def clear(members: list[int]) -> bool:
        area = [_box(strokes[i], CLEAR * mm) for i in members]
        return not any(
            j not in members and any(_meet(a, _box(strokes[j])) for a in area) for j in short
        )

    chords = {i: _straight(strokes[i]) for i in small}
    for n, i in enumerate(small):
        if i in used or chords[i] is None:
            continue
        for j in small[n + 1 :]:
            if j in used or chords[j] is None:
                continue
            angle = _crosses(chords[i], chords[j])
            if angle is not None and angle >= CROSS_ANGLE and clear([i, j]):
                pts = np.vstack([strokes[i].points, strokes[j].points])
                centre = (pts.min(axis=0) + pts.max(axis=0)) / 2
                marks.append(("cross", [i, j], centre))
                used |= {i, j}
                break

    for i in small:
        if i in used:
            continue
        shape, _ = classify(strokes[i].points)
        if shape in ("circle", "closed") and clear([i]):
            s = strokes[i].points
            marks.append(("ring", [i], (s.min(axis=0) + s.max(axis=0)) / 2))
            used.add(i)

    underlines = 0
    for i, s in enumerate(strokes):
        if i in used or _size(s) < MIN_LINE * mm:
            continue
        shape, fit = classify(s.points)
        if shape != "line":
            continue
        a, b = (np.array(p, dtype=float) for p in fit["points"])
        near = [
            j
            for j in short
            if j not in used and _distance(strokes[j].points, a, b).min() <= UNDERLINE * mm
        ]
        if len(near) > 2:
            underlines += 1
            continue
        marks.append(("line", [i], (a, b)))
        used.add(i)
    return marks, len(strokes) - len(used) - underlines, underlines


# --- what they are on --------------------------------------------------------


class _Plan:
    """Walls and symbols of a drawing from ``rmink sheet drawing``, on its sheet."""

    def __init__(self, segments: list, symbols: list) -> None:
        self.segments = segments  # (a, b, group) in sheet pt
        self.symbols = symbols  # (centre, radius, name, kind) in sheet pt

    def length_group(self, a: np.ndarray, b: np.ndarray) -> str:
        d = b - a
        reach = ALONG / PT_TO_MM
        for p, q, group in self.segments:
            e = q - p
            if np.linalg.norm(e) == 0:
                continue
            cos = abs(float(d @ e)) / (np.linalg.norm(d) * np.linalg.norm(e))
            if math.degrees(math.acos(min(cos, 1.0))) > ALONG_ANGLE:
                continue
            if _distance(np.array([a, b]), p, q).max() <= reach:
                return group
        return "Linje"

    def count_group(self, at: np.ndarray, shape: str) -> tuple[str, str]:
        """The group a mark counts in, and the symbol it is on ("" for none)."""
        for centre, radius, name, kind in self.symbols:
            if np.linalg.norm(at - centre) <= max(radius, ALONG / PT_TO_MM):
                return name, kind
        return _shape_group(shape), ""


def _plan(doc: pymupdf.Document, sheet_page: int) -> _Plan | None:
    names = doc.embfile_names()
    if PLACEMENT not in names or DRAWING not in names:
        return None
    place = json.loads(doc.embfile_get(PLACEMENT))
    if place.get("page") != sheet_page:
        return None
    from rmink.drawing import workflow
    from rmink.drawing.render import _element_paths
    from rmink.drawing.symbols import SYMBOLS

    d = workflow.drawing_from_json(doc.embfile_get(DRAWING).decode())
    k = place["pt_per_px"]
    origin = np.array(place["origin"], dtype=float)
    labels = {c.name: c.label or c.name for c in d.categories}
    segments = []
    for e in d.elements:
        if e.kind == "text":
            continue
        for path in _element_paths(e):
            p = np.asarray(path, dtype=float) * k + origin
            segments += [
                (p[i], p[i + 1], labels.get(e.category, e.category)) for i in range(len(p) - 1)
            ]
    symbols = [
        (
            np.array(s.at, dtype=float) * k + origin,
            s.size * k * 0.75,
            s.label or SYMBOLS.get(s.kind, (s.kind, []))[0],
            s.kind,
        )
        for s in d.symbols
    ]
    return _Plan(segments, symbols)


def _shape_group(shape: str) -> str:
    return "Kryss" if shape == "cross" else "Ring"


def find_quantities(notebook: bytes, sheet: bytes, scale: int | None = None) -> Takeoff:
    """Lengths and counts on a notebook from ``rmink sheet send``. ``sheet`` gives
    the scale; ``scale`` (N in 1:N) is for a sheet that does not say."""
    manifest: Manifest = notebook_manifest(notebook)
    device = get_device(manifest.device)
    ink = read_ink(notebook, device)
    doc = pymupdf.open(stream=sheet, filetype="pdf")
    px = 72 / device.dpi
    result = Takeoff(session=manifest.session, name=manifest.name)
    plans: dict[int, _Plan | None] = {}
    numbers: Counter = Counter()

    for tile in manifest.tiles:
        strokes = [
            s
            for s in ink.pages.get(tile.tablet_page, [])
            if s.pen not in ERASERS and s.id is not None and not off_sheet(s, tile, px)
        ]
        if not strokes:
            continue
        page = doc[tile.sheet_page]
        found = page_scale(doc, page) or (fixed_scale(scale) if scale else None)
        marks, ignored, underlines = read_marks(strokes, device)
        result.ignored += ignored
        result.underlines += underlines
        if found is None:
            result.unscaled += len(marks)
            continue
        result.scales[tile.sheet_page] = found.ratio
        if tile.sheet_page not in plans:
            plans[tile.sheet_page] = _plan(doc, tile.sheet_page)
        plan = plans[tile.sheet_page]

        def sheet_point(p, tile=tile) -> np.ndarray:
            return np.array(tile.to_sheet(float(p[0]) * px, float(p[1]) * px), dtype=float)

        derotate = unrotate(page)
        marks.sort(key=lambda m: float(np.min(strokes[m[1][0]].points[:, 1])))
        for shape, members, where in marks:
            keys = [stroke_key(manifest, tile.tablet_page, strokes[i]) for i in members]
            if shape == "line":
                a, b = sheet_point(where[0]), sheet_point(where[1])
                ra, rb = pymupdf.Point(*a) * derotate, pymupdf.Point(*b) * derotate
                value = abs(rb - ra) * found.per_unit
                group = plan.length_group(a, b) if plan else "Linje"
                numbers["L"] += 1
                result.quantities.append(
                    Quantity(
                        id=f"L{numbers['L']}", kind="length", group=group,
                        sheet_page=tile.sheet_page, tablet_page=tile.tablet_page,
                        points=[tuple(a), tuple(b)], value=round(value, 1),
                        unit=found.unit, strokes=keys,
                    )
                )  # fmt: skip
            else:
                at = sheet_point(where)
                group, kind = plan.count_group(at, shape) if plan else (_shape_group(shape), "")
                numbers["A"] += 1
                result.quantities.append(
                    Quantity(
                        id=f"A{numbers['A']}", kind="count", group=group,
                        sheet_page=tile.sheet_page, tablet_page=tile.tablet_page,
                        points=[tuple(at)], value=1, unit="st", strokes=keys, symbol=kind,
                    )
                )  # fmt: skip
    return result


# --- on the sheet ------------------------------------------------------------


def _str(doc: pymupdf.Document, xref: int, key: str, text: str) -> None:
    doc.xref_set_key(xref, key, pymupdf.get_pdf_str(text))


def _layer(doc: pymupdf.Document, name: str) -> int:
    known = {o["name"]: xref for xref, o in doc.get_ocgs().items()}
    return known.get(name) or doc.add_ocg(name)


def _measure(scale: Scale) -> str:
    return (
        f"<</Type/Measure/Subtype/RL/R({scale.ratio})"
        f"/X[<</Type/NumberFormat/U({scale.unit})/C {scale.per_unit:.6f}/D 1>>]"
        f"/D[<</Type/NumberFormat/U({scale.unit})/C 1/D 1>>]>>"
    )


def _group_id(group: str) -> str:
    import unicodedata

    plain = unicodedata.normalize("NFKD", group).encode("ascii", "ignore").decode().lower()
    return "rmink-" + re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def write_quantities(
    sheet: bytes, takeoff: Takeoff, scale: int | None = None
) -> tuple[bytes, int, int]:
    """Add the lengths as measurements and the counts as count markers, which
    Open PDF Studio lists and totals. Returns the PDF, how many were added and
    how many were there already."""
    doc = pymupdf.open(stream=sheet, filetype="pdf")
    layer = _layer(doc, f"Mängder {takeoff.name}")
    names = {a.info.get("id", "") for p in doc for a in p.annots()}
    groups = sorted({q.group for q in takeoff.quantities if q.kind == "count"})
    colors = {g: COLORS[i % len(COLORS)] for i, g in enumerate(groups)}
    numbers = Counter(
        doc.xref_get_key(a.xref, "OPS_CountCategory")[1]
        for p in doc
        for a in p.annots(types=[pymupdf.PDF_ANNOT_CIRCLE])
    )
    added = skipped = 0
    for q in takeoff.quantities:
        name = f"rmink-qty-{q.strokes[0]}"
        if name in names:
            skipped += 1
            continue
        page = doc[q.sheet_page]
        found = page_scale(doc, page) or (fixed_scale(scale) if scale else None)
        derotate = unrotate(page)
        if q.kind == "length":
            a, b = (pymupdf.Point(p) * derotate for p in q.points)
            annot = page.add_line_annot(a, b)
            annot.set_colors(stroke=(0.15, 0.39, 0.92))
            annot.set_border(width=1.5)
            annot.set_line_ends(pymupdf.PDF_ANNOT_LE_CIRCLE, pymupdf.PDF_ANNOT_LE_CIRCLE)
            text = f"{q.value:.0f} {q.unit}"
            annot.set_info(title="rmink", subject=f"Längd {q.id.removeprefix('L')}", content=text)
            annot.set_oc(layer)
            annot.update()
            x = annot.xref
            doc.xref_set_key(x, "IT", "/LineDimension")
            doc.xref_set_key(x, "Cap", "true")
            if found:
                doc.xref_set_key(x, "Measure", _measure(found))
                # Open PDF Studio then follows the page's scale when the line is edited.
                doc.xref_set_key(x, "OPS_ScaleInherited", "true")
            _str(doc, x, "OPS_Subtype", "measureDistance")
        else:
            at = pymupdf.Point(q.points[0]) * derotate
            r = pymupdf.Rect(at.x - RADIUS, at.y - RADIUS, at.x + RADIUS, at.y + RADIUS)
            annot = page.add_circle_annot(r)
            annot.set_colors(stroke=colors[q.group], fill=colors[q.group])
            annot.set_border(width=1.5)
            annot.set_info(title="rmink", subject=q.group, content="")
            annot.set_oc(layer)
            annot.update(opacity=0.85)
            x = annot.xref
            group = _group_id(q.group)
            numbers[group] += 1
            _str(doc, x, "OPS_Subtype", "count")
            doc.xref_set_key(x, "OPS_CountNumber", str(numbers[group]))
            _str(doc, x, "OPS_CountCategory", group)
            _str(doc, x, "OPS_CountCategoryName", q.group)
            _str(doc, x, "OPS_MarkerStyle", "dot")
            mapped = knowledge.symbol(q.symbol) if q.symbol else None
            if mapped and mapped["ops"]:
                _str(doc, x, "OPS_SymbolId", mapped["ops"])
        _str(doc, x, "NM", name)
        _str(doc, x, "RMINK_Strokes", json.dumps(q.strokes))
        names.add(name)
        added += 1
    return doc.tobytes(garbage=1, deflate=True), added, skipped


def _number(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}".replace(".", ",")


def _ifc(kind: str) -> str:
    """IfcOutlet.POWEROUTLET for a count on a symbol with an IFC class."""
    mapped = knowledge.symbol(kind) if kind else None
    if not mapped or not mapped["ifc"]:
        return ""
    return ".".join(x for x in (mapped["ifc"], mapped["ifc_type"]) if x)


def quantities_csv(takeoff: Takeoff) -> str:
    """Every length and count, then the sums per group; Swedish Excel opens it as is."""
    out = io.StringIO()
    out.write("﻿")
    w = csv.writer(out, delimiter=";")
    w.writerow(["Nr", "Typ", "Grupp", "Blad", "Värde", "Enhet", "IFC"])
    for q in takeoff.quantities:
        kind = "Längd" if q.kind == "length" else "Antal"
        value = _number(q.value, 0)
        w.writerow([q.id, kind, q.group, q.sheet_page + 1, value, q.unit, _ifc(q.symbol)])
    w.writerow([])
    w.writerow(["Summa", "Typ", "Grupp", "Antal", "Summa", "Enhet"])
    for kind, group, n, total in takeoff.totals():
        if kind == "length":
            unit = next(q.unit for q in takeoff.quantities if q.group == group)
            value, unit = (
                (_number(total / 1000, 2), "m") if unit == "mm" else (_number(total, 0), unit)
            )
            w.writerow(["", "Längd", group, n, value, unit])
        else:
            w.writerow(["", "Antal", group, n, n, "st"])
    return out.getvalue()
