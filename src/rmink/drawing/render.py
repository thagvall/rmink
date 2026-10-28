"""Render a :class:`~rmink.drawing.model.Drawing` as clean ink.

Everything becomes fineliner strokes on two layers: ``Ritning r<N>`` with the
drawing, and an empty ``Kommentarer`` layer for the next round of markings.
Colour tablets get each category's colour; greyscale tablets tell categories
apart by line type and width instead. A title block goes below the drawing:
the legend, the open remarks (each with a line to write the answer on) and the
change log.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np
from rmscene.scene_items import Pen, PenColor

from rmink.calc import format_angle
from rmink.devices import COLOR_PALETTE, DeviceProfile
from rmink.drawing.font import text_paths, text_width
from rmink.drawing.model import (
    AngleDimension,
    Annotation,
    Category,
    Dimension,
    Drawing,
    Element,
    LineType,
)
from rmink.drawing.symbols import SYMBOLS, symbol_paths
from rmink.model import Page, Stroke

COMMENT_LAYER = "Kommentarer"
_PALETTE = {e.name: e for e in COLOR_PALETTE}
# Dash patterns as (on, off, on, off, ...) multiples of the line width plus a base length.
_DASHES: dict[str, tuple[float, ...]] = {
    "dashed": (18, 10),
    "dotted": (2, 8),
    "dashdot": (26, 8, 3, 8),
}
_ARROW = 16.0  # arrowhead length, px
_MARGIN = 60.0


def drawing_layer(revision: int) -> str:
    return f"Ritning r{revision}"


@dataclass
class _Style:
    color: PenColor
    rgb: tuple[int, int, int]
    line_type: LineType
    width: float


def _style(cat: Category, device: DeviceProfile, line_type: LineType | None = None) -> _Style:
    if device.color:
        entry = _PALETTE.get(cat.color, _PALETTE["black"])
        lt = cat.line_type
    else:
        entry = _PALETTE[cat.mono_color]
        lt = cat.mono_line_type or cat.line_type
    return _Style(entry.color, entry.rgb, line_type or lt, cat.width)


def _dash(path: np.ndarray, line_type: LineType, width: float) -> list[np.ndarray]:
    if line_type == "solid" or len(path) < 2:
        return [path]
    pattern = [v * max(width, 1.5) / 2 for v in _DASHES[line_type]]
    seg = np.diff(path, axis=0)
    lengths = np.hypot(seg[:, 0], seg[:, 1])
    cum = np.concatenate([[0.0], np.cumsum(lengths)])
    total = cum[-1]
    if total == 0:
        return [path]

    def at(d: float) -> np.ndarray:
        return np.column_stack([np.interp(d, cum, path[:, 0]), np.interp(d, cum, path[:, 1])])[0]

    out, d, i = [], 0.0, 0
    while d < total:
        on, off = pattern[i % len(pattern)], pattern[(i + 1) % len(pattern)]
        end = min(d + on, total)
        inner = [path[k] for k in range(len(path)) if d < cum[k] < end]
        out.append(np.array([at(d), *inner, at(end)]))
        d = end + off
        i += 2
    return out


class _Pen:
    """Collects strokes for one page."""

    def __init__(self, drawing: Drawing, device: DeviceProfile, layer: str) -> None:
        self.drawing, self.device, self.layer = drawing, device, layer
        self.strokes: list[Stroke] = []

    def style(self, category: str, line_type: LineType | None = None) -> _Style:
        return _style(self.drawing.category(category), self.device, line_type)

    def paths(self, paths: list[np.ndarray], st: _Style, width: float | None = None) -> None:
        w = width or st.width
        for p in paths:
            for piece in _dash(np.asarray(p, dtype=float), st.line_type, w):
                if len(piece) >= 2:
                    self.strokes.append(
                        Stroke(piece, width=w, pen=Pen.FINELINER_2, color=st.color,
                               rgba=None, layer=self.layer)
                    )  # fmt: skip

    def text(self, text: str, at, size: float, st: _Style, angle: float = 0.0) -> None:
        solid = _Style(st.color, st.rgb, "solid", max(1.5, size / 16))
        self.paths(text_paths(text, at, size, angle), solid)


def _circle(center, r: float, a0: float = 0.0, a1: float = 360.0) -> np.ndarray:
    n = max(int(abs(a1 - a0) / 6), 8)
    t = np.radians(np.linspace(a0, a1, n + 1))
    return np.column_stack([center[0] + r * np.cos(t), center[1] + r * np.sin(t)])


def _element_paths(e: Element) -> list[np.ndarray]:
    pts = np.array(e.points, dtype=float).reshape(-1, 2)
    if e.kind == "line" or e.kind == "polyline":
        if e.closed and len(pts) > 2:
            pts = np.vstack([pts, pts[:1]])
        return [pts] if len(pts) >= 2 else []
    if e.kind == "rect" and len(pts) >= 2:
        (x0, y0), (x1, y1) = pts[0], pts[1]
        return [np.array([[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]])]
    if e.kind in ("circle", "arc") and e.center and e.radius:
        a0, a1 = (0.0, 360.0) if e.kind == "circle" else (e.start_angle, e.end_angle)
        return [_circle(e.center, e.radius, a0, a1)]
    return []


def _arrowhead(tip: np.ndarray, direction: np.ndarray, size: float = _ARROW) -> np.ndarray:
    d = direction / (np.linalg.norm(direction) or 1)
    n = np.array([-d[1], d[0]])
    back = tip - d * size
    return np.array([back + n * size * 0.35, tip, back - n * size * 0.35])


def _readable(angle: float) -> float:
    """Text angle in [-90, 90) so labels never read upside down; vertical
    labels read from the bottom up, as on drawings."""
    while angle >= 90:
        angle -= 180
    while angle < -90:
        angle += 180
    return angle


_HAS_UNIT = re.compile(r"[A-Za-zÅÄÖåäö°%²³]")


def dimension_label(dim: Dimension, show_unit: bool = True) -> str:
    """The dimension's text with its unit, "4800" -> "4800 mm", unless it
    already says what it is ("2,1 m", "45°", "c600")."""
    if not show_unit or not dim.unit or not dim.text or _HAS_UNIT.search(dim.text):
        return dim.text
    return f"{dim.text} {dim.unit}"


def _dimension(pen: _Pen, dim: Dimension, size: float) -> None:
    st = pen.style(dim.category)
    a, b = np.array(dim.start, float), np.array(dim.end, float)
    d = b - a
    length = float(np.linalg.norm(d))
    if length < 1:
        return
    u = d / length
    n = np.array([u[1], -u[0]])  # left of the direction a -> b, i.e. "above" a horizontal line
    off = n * dim.offset
    a2, b2 = a + off, b + off
    ext = n * 8 * np.sign(dim.offset or 1)
    pen.paths([np.array([a + n * 6 * np.sign(dim.offset or 1), a2 + ext])], st)
    pen.paths([np.array([b + n * 6 * np.sign(dim.offset or 1), b2 + ext])], st)
    pen.paths([np.array([a2, b2]), _arrowhead(a2, -u), _arrowhead(b2, u)], st)
    angle = _readable(math.degrees(math.atan2(u[1], u[0])))
    label = dimension_label(dim, pen.drawing.show_units)
    w = text_width(label, size)
    r = math.radians(angle)
    along = np.array([math.cos(r), math.sin(r)])
    up = np.array([math.sin(r), -math.cos(r)])
    mid = (a2 + b2) / 2
    # The label goes on the side of the dimension line away from the object.
    if np.dot(up, off) >= 0:
        origin = mid - along * w / 2 + up * 8
    else:
        origin = mid - along * w / 2 - up * (8 + size)
    text_st = pen.style("text")
    text_st.color, text_st.rgb = st.color, st.rgb
    pen.text(label, origin, size, text_st, angle)


def _angle(pen: _Pen, ang: AngleDimension, size: float) -> None:
    """An arc from one leg to the other with arrows at both ends and the
    degrees outside the middle of the arc."""
    deg = ang.measured()
    if deg is None:
        return
    st = pen.style(ang.category)
    v = np.array(ang.vertex, float)
    a, b = np.subtract(ang.start, v), np.subtract(ang.end, v)
    t0 = math.atan2(a[1], a[0])
    sweep = math.atan2(a[0] * b[1] - a[1] * b[0], a @ b)  # signed, the smaller way round
    t = t0 + np.linspace(0, sweep, max(8, int(abs(math.degrees(sweep)) / 4)))
    r = ang.radius
    arc = v + r * np.column_stack([np.cos(t), np.sin(t)])
    paths = [arc]
    if abs(sweep) * r > 2.5 * _ARROW:
        s = math.copysign(1.0, sweep)
        paths.append(_arrowhead(arc[-1], s * np.array([-math.sin(t[-1]), math.cos(t[-1])])))
        paths.append(_arrowhead(arc[0], -s * np.array([-math.sin(t[0]), math.cos(t[0])])))
    text = ang.text or format_angle(deg)
    w = text_width(text, size)
    # Beside the middle of the arc, unless a line runs there (a king post along
    # the bisector): then further along the arc, or outside it.
    origin = None
    for frac, extra in _LABEL_SPOTS:
        tm = t0 + sweep * frac
        at = v + (r + 10 + extra + 0.6 * max(w, size)) * np.array([math.cos(tm), math.sin(tm)])
        box = (at[0] - w / 2 - 4, at[1] - size / 2 - 4, at[0] + w / 2 + 4, at[1] + size / 2 + 4)
        if origin is None:
            origin = at
        if not _hits(box, pen.strokes):
            origin = at
            break
    pen.paths(paths, st)
    text_st = pen.style("text")
    text_st.color, text_st.rgb = st.color, st.rgb
    pen.text(text, (origin[0] - w / 2, origin[1] + size / 2), size, text_st)


# Where an angle's degrees may go: (fraction along the arc, extra distance out).
_LABEL_SPOTS = [
    (0.5, 0), (0.3, 0), (0.7, 0), (0.2, 0), (0.8, 0), (0.5, 40), (0.3, 40), (0.7, 40),
]  # fmt: skip


def _hits(box: tuple[float, float, float, float], strokes: list[Stroke]) -> bool:
    """Whether any stroke passes through the box (x0, y0, x1, y1)."""
    x0, y0, x1, y1 = box
    for stroke in strokes:
        p = stroke.points
        if len(p) == 0:
            continue
        lo, hi = p.min(axis=0), p.max(axis=0)
        if hi[0] < x0 or lo[0] > x1 or hi[1] < y0 or lo[1] > y1:
            continue
        # sample each segment every few px so long straight lines are caught
        seg = np.diff(p, axis=0) if len(p) > 1 else np.zeros((0, 2))
        pts = [p]
        for a, d in zip(p[:-1], seg, strict=True):
            n = int(np.hypot(*d) // 3)
            if n > 1:
                pts.append(a + np.outer(np.linspace(0, 1, n), d))
        q = np.vstack(pts)
        if ((q[:, 0] >= x0) & (q[:, 0] <= x1) & (q[:, 1] >= y0) & (q[:, 1] <= y1)).any():
            return True
    return False


def _bbox_of(drawing: Drawing, ids: list[str]) -> tuple[np.ndarray, np.ndarray] | None:
    pts = []
    for item_id in ids:
        item = drawing.find(item_id)
        if item is None:
            continue
        if isinstance(item, Element):
            for p in _element_paths(item):
                pts.append(p)
            if item.kind == "text" and item.points:
                x, y = item.points[0]
                w = text_width(item.text or "", item.size)
                pts.append(np.array([[x, y - item.size], [x + w, y]]))
        elif isinstance(item, Dimension):
            pts.append(np.array([item.start, item.end]))
        elif isinstance(item, AngleDimension):
            r = item.radius
            pts.append(np.array([item.vertex]) + [[-r, -r], [r, r]])
        else:
            r = item.size / 2
            pts.append(
                np.array([[item.at[0] - r, item.at[1] - r], [item.at[0] + r, item.at[1] + r]])
            )
    if not pts:
        return None
    allp = np.vstack(pts)
    return allp.min(axis=0), allp.max(axis=0)


_RING_MAX = 60.0  # px; larger targets get corner marks instead of a ring


def _annotation(pen: _Pen, ann: Annotation, number: int) -> None:
    """A numbered marker for an open remark: a small ring around a small
    target, or corner marks around a large one, so it never runs through the
    drawing's texts."""
    st = pen.style("comment")
    box = _bbox_of(pen.drawing, ann.targets)
    if box is not None:
        lo, hi = box
        center = (lo + hi) / 2
        radius = max(float(np.linalg.norm(hi - lo)) / 2 + 14, 24)
    elif ann.at is not None:
        center, radius = np.array(ann.at, float), 24.0
    else:
        return
    if ann.at is not None and box is not None and radius <= _RING_MAX:
        center = np.array(ann.at, float)
    if radius > _RING_MAX and box is not None:
        lo, hi = lo - 10, hi + 10
        arm = min(24.0, float(min(hi - lo)) / 3)
        corners = []
        for (x, y), (dx, dy) in (
            ((lo[0], lo[1]), (1, 1)), ((hi[0], lo[1]), (-1, 1)),
            ((hi[0], hi[1]), (-1, -1)), ((lo[0], hi[1]), (1, -1)),
        ):  # fmt: skip
            corners.append(np.array([[x + dx * arm, y], [x, y], [x, y + dy * arm]]))
        pen.paths(corners, st)
        # The number goes at the first corner, or side, where nothing is drawn.
        mid = (lo[1] + hi[1]) / 2
        spots = [(lo[0] - 18, lo[1] - 18), (hi[0] + 18, lo[1] - 18), (hi[0] + 18, hi[1] + 18),
                 (lo[0] - 18, hi[1] + 18), (lo[0] - 24, mid), (hi[0] + 24, mid)]  # fmt: skip
        badge = np.array(spots[0])
        for x, y in spots:
            if not _hits((x - 18, y - 18, x + 18, y + 18), pen.strokes):
                badge = np.array([x, y])
                break
    else:
        if ann.kind == "cross":
            r = radius * 0.7
            pen.paths([np.array([center - r, center + r]),
                       np.array([center + [r, -r], center + [-r, r]])], st)  # fmt: skip
        else:
            pen.paths([_circle(center, radius)], st)
        # Number badge at the top-left of the ring (labels sit top-right), matching the list.
        badge = center + np.array([-radius * 0.75, -radius * 0.75])
    pen.paths([_circle(badge, 16)], st, width=1.8)
    label = str(number)
    pen.text(label, badge + [-text_width(label, 16) / 2, 8], 16, st)


def _content_bottom(strokes: list[Stroke]) -> float:
    return max((float(s.points[:, 1].max()) for s in strokes), default=0.0)


def _wrap(text: str, size: float, width: float, max_lines: int) -> list[str]:
    """Break ``text`` at spaces into lines no wider than ``width``; the last
    allowed line ends in "…" if text is left over."""
    lines: list[str] = []
    for word in text.split():
        if lines and text_width(f"{lines[-1]} {word}", size) <= width:
            lines[-1] += f" {word}"
        else:
            lines.append(word)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] += " …"
    return lines


def _title_block(pen: _Pen, top: float, open_remarks: list[tuple[int, Annotation]]) -> None:
    d, dev = pen.drawing, pen.device
    st_text = pen.style("text")
    x0, x1 = _MARGIN, dev.width - _MARGIN
    frame = _Style(st_text.color, st_text.rgb, "solid", 2.0)
    y = top
    pen.paths([np.array([[x0, y], [x1, y]])], frame)
    y += 44
    title = d.name.upper()
    pen.text(title, (x0, y), 30, st_text)
    rev = (
        f"REV {d.revision}"
        + (f"  {d.phase}" if d.phase else "")
        + (f"  {d.date}" if d.date else "")
    )
    pen.text(rev, (x1 - text_width(rev, 20), y), 20, st_text)
    units = [dim.unit for dim in d.dimensions if dim.unit]
    if units:
        note = f"Mått i {max(set(units), key=units.count)}"
        pen.text(note, (x1 - text_width(note, 16), y + 28), 16, st_text)
        y += 20
    y += 30

    if d.legend:
        y += 24
        pen.text("FÖRKLARINGAR", (x0, y), 18, st_text)
        col_w = (x1 - x0) / 2
        for i, entry in enumerate(d.legend):
            col, row = i % 2, i // 2
            cx = x0 + col * col_w
            cy = y + 40 + row * 44
            sample_mid = np.array([cx + 30, cy - 9])
            if entry.key.startswith("category:"):
                cat = entry.key.split(":", 1)[1]
                pen.paths([np.array([sample_mid - [28, 0], sample_mid + [28, 0]])], pen.style(cat))
            else:
                pen.paths(symbol_paths(entry.key, tuple(sample_mid), 30), pen.style("default"))
            pen.text(entry.meaning, (cx + 72, cy), 18, st_text)
        y += 40 + ((len(d.legend) + 1) // 2) * 44

    if open_remarks:
        y += 24
        st_c = pen.style("comment")
        pen.text("ANMÄRKNINGAR", (x0, y), 18, st_c)
        answer_line = _Style(st_c.color, st_c.rgb, "solid", 1.2)
        for n, ann in open_remarks:
            for i, line in enumerate(_wrap(f"{n}. {ann.text}", 18, x1 - x0, 3)):
                y += 32 if i == 0 else 26
                pen.text(line, (x0, y), 18, st_c)
            # A line to write the answer on, so it is clear which remark it answers.
            y += 84
            pen.text("SVAR:", (x0 + 28, y), 16, st_c)
            start = x0 + 28 + text_width("SVAR:", 16) + 12
            pen.paths([np.array([[start, y], [x1, y]])], answer_line)
            y += 12
    if d.log:
        y += 36
        pen.text("ÄNDRINGAR", (x0, y), 18, st_text)
        for entry in d.log[-6:]:
            for i, line in enumerate(_wrap(entry, 16, x1 - x0, 2)):
                y += 30 if i == 0 else 22
                pen.text(line, (x0 + (0 if i == 0 else 24), y), 16, st_text)


def render_drawing(drawing: Drawing, device: DeviceProfile, size: float = 22.0) -> Page:
    """The clean revision as a page with the drawing and an empty comment layer."""
    layer = drawing_layer(drawing.revision)
    pen = _Pen(drawing, device, layer)
    for e in drawing.elements:
        if e.kind == "text":
            if e.points and e.text:
                pen.text(e.text, e.points[0], e.size, pen.style(e.category))
            continue
        pen.paths(_element_paths(e), pen.style(e.category, e.line_type))
    for s in drawing.symbols:
        st = pen.style(s.category)
        pen.paths(symbol_paths(s.kind, s.at, s.size, s.rotation), st)
        if s.label:
            pen.text(s.label, (s.at[0] + s.size * 0.7, s.at[1] - s.size * 0.4), size * 0.8, st)
    for dim in drawing.dimensions:
        _dimension(pen, dim, size)
    for ang in drawing.angles:
        _angle(pen, ang, size)
    open_remarks = [
        (i + 1, a) for i, a in enumerate(a for a in drawing.annotations if a.status == "open")
    ]
    for n, ann in open_remarks:
        _annotation(pen, ann, n)

    top = _content_bottom(pen.strokes) + _MARGIN
    _title_block(pen, top, open_remarks)
    height = max(device.height, int(_content_bottom(pen.strokes) + _MARGIN))
    return Page(device.width, height, pen.strokes, layer_names=[layer, COMMENT_LAYER])


def _clip(p0: np.ndarray, p1: np.ndarray, box) -> np.ndarray | None:
    """The part of segment p0-p1 inside box (x0, y0, x1, y1) (Liang–Barsky)."""
    x0, y0, x1, y1 = box
    d = p1 - p0
    t0, t1 = 0.0, 1.0
    for p, q in ((-d[0], p0[0] - x0), (d[0], x1 - p0[0]), (-d[1], p0[1] - y0), (d[1], y1 - p0[1])):
        if p == 0:
            if q < 0:
                return None
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return None
    return np.array([p0 + t0 * d, p0 + t1 * d])


def _hatch(box, pattern: str, angle: float = 45.0, spacing: float = 10.0) -> list[np.ndarray]:
    """Hatch lines for a rectangle, after the patterns in hatches.toml."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if w <= 2 or h <= 2:
        return []

    def lines(deg: float, step: float) -> list[np.ndarray]:
        a = math.radians(deg)
        u = np.array([math.cos(a), -math.sin(a)])  # along the line, y down
        n = np.array([-u[1], u[0]])
        c = np.array([(x0 + x1) / 2, (y0 + y1) / 2])
        reach = math.hypot(w, h)
        out = []
        for k in np.arange(-reach / 2, reach / 2 + step, step):
            seg = _clip(c + n * k - u * reach, c + n * k + u * reach, box)
            if seg is not None and np.linalg.norm(seg[1] - seg[0]) > 1:
                out.append(seg)
        return out

    def dots(step: float) -> list[np.ndarray]:
        out = []
        for i, y in enumerate(np.arange(y0 + step / 2, y1, step)):
            for x in np.arange(x0 + step / 2 + (step / 2 if i % 2 else 0), x1, step):
                out.append(np.array([[x - 1.2, y], [x + 1.2, y]]))
        return out

    def waves(step: float, amp: float) -> list[np.ndarray]:
        xs = np.linspace(x0, x1, max(8, int(w / 4)))
        out = []
        for y in np.arange(y0 + step / 2, y1, step):
            ys = y + amp * np.sin((xs - x0) / step * math.pi)
            out.append(np.column_stack([xs, np.clip(ys, y0, y1)]))
        return out

    if pattern == "lines":
        return lines(angle, spacing)
    if pattern == "cross":
        return lines(angle, spacing) + lines(angle + 90, spacing)
    if pattern == "lines_dots":
        return lines(angle, spacing * 1.6) + dots(spacing * 0.9)
    if pattern == "dots":
        return dots(spacing)
    if pattern == "wave":
        return waves(min(spacing, h), min(spacing, h) / 3)
    if pattern == "grain":
        return waves(spacing * 0.7, 1.5)
    if pattern == "earth":
        return [np.array([[x, y1], [x + 6, y1 - 6]]) for x in np.arange(x0 + 2, x1 - 6, spacing)]
    if pattern == "solid":
        return lines(0, 2.5)
    return []


def _material_hatch(material: str) -> tuple[str, float]:
    from rmink import knowledge

    kb = knowledge.load()
    hatch_id = next((m["hatch"] for m in kb["materials"]["material"] if m["id"] == material), "")
    h = next((h for h in kb["hatches"]["hatch"] if h["id"] == hatch_id), None)
    return (h["pattern"], float(h["angle"])) if h else ("blank", 0.0)


def _option(pen: _Pen, opt, x0: float, x1: float, y: float) -> float:
    """One alternative: key, title, a small section with hatched layers and
    their texts, then facts, pros and cons. Returns the y below it."""
    st_text, st_line = pen.style("text"), pen.style("default")
    thin = _Style(st_line.color, st_line.rgb, "solid", 1.2)
    pen.paths([_circle((x0 + 22, y - 10), 22)], st_text)
    pen.text(opt.key, (x0 + 22 - text_width(opt.key, 24) / 2, y + 2), 24, st_text)
    tx = x0 + 64
    for i, line in enumerate(_wrap(opt.title, 24, x1 - tx, 2)):
        pen.text(line, (tx, y + i * 32), 24, st_text)
    y += 32 * min(2, len(_wrap(opt.title, 24, x1 - tx, 2))) + 16

    layers = opt.layers
    if layers:
        total = sum(max(layer.thickness_mm, 0) for layer in layers) or 1
        scale = min(0.6, 280 / total)
        sx0, sx1 = tx, tx + 170
        top, rows, last_text = y, [], y - 24
        for layer in layers:
            h = max(layer.thickness_mm * scale, 6 if layer.thickness_mm > 0 else 0)
            box = (sx0, top, sx1, top + h)
            if h > 0:
                pattern, angle = _material_hatch(layer.material)
                pen.paths([np.array([[sx0, top], [sx1, top], [sx1, top + h], [sx0, top + h],
                                     [sx0, top]])], st_line)  # fmt: skip
                pen.paths(_hatch(box, pattern, angle, 9.0), thin)
            else:
                pen.paths([np.array([[sx0 - 6, top], [sx1 + 6, top]])], thin)
            mid = top + h / 2
            ty = max(mid + 6, last_text + 24)
            rows.append((mid, ty, layer.text))
            last_text = ty
            top += h
        for mid, ty, text in rows:
            pen.paths([np.array([[sx1, mid], [sx1 + 14, ty - 6]])], thin)
            (line,) = _wrap(text, 16, x1 - sx1 - 24, 1) or [""]
            pen.text(line, (sx1 + 18, ty), 16, st_text)
        y = max(top, last_text) + 34
    if opt.facts:
        for line in _wrap("  ·  ".join(opt.facts), 17, x1 - tx, 3):
            pen.text(line, (tx, y), 17, st_text)
            y += 26
        y += 6
    for sign, items in (("+", opt.pros), ("-", opt.cons)):
        for item in items:
            for i, line in enumerate(_wrap(item, 16, x1 - tx - 24, 2)):
                if i == 0:
                    pen.text(sign, (tx, y), 16, st_text)
                pen.text(line, (tx + 24, y), 16, st_text)
                y += 24
    return y


def render_alternatives(drawing: Drawing, device: DeviceProfile) -> Page | None:
    """The open choices as a page to put after the drawing: each alternative
    with a small hatched section, facts, pros and cons. None when there are
    no open choices."""
    open_sets = [a for a in drawing.alternatives if not a.chosen and a.options]
    if not open_sets:
        return None
    layer = drawing_layer(drawing.revision)
    pen = _Pen(drawing, device, layer)
    st_text = pen.style("text")
    frame = _Style(st_text.color, st_text.rgb, "solid", 2.0)
    x0, x1 = _MARGIN, device.width - _MARGIN
    y = _MARGIN + 30
    pen.text(f"ALTERNATIV · {drawing.name}", (x0, y), 30, st_text)
    y += 20
    for alt in open_sets:
        y += 40
        for line in _wrap(alt.question, 22, x1 - x0, 2):
            pen.text(line, (x0, y), 22, st_text)
            y += 30
        pen.paths([np.array([[x0, y - 14], [x1, y - 14]])], frame)
        for opt in alt.options:
            y = _option(pen, opt, x0, x1, y + 36)
            y += 12
        keys = "/".join(o.key for o in alt.options)
        tail = f"Välj {keys}: skriv bokstaven på SVAR-raden på ritningen."
        for line in [*_wrap(alt.note, 16, x1 - x0, 3), *_wrap(tail, 16, x1 - x0, 2)]:
            y += 24
            pen.text(line, (x0, y), 16, st_text)
        y += 12
    height = max(device.height, int(y + _MARGIN))
    return Page(device.width, height, pen.strokes, layer_names=[layer, COMMENT_LAYER])


def default_legend(drawing: Drawing) -> list[tuple[str, str]]:
    """Legend rows for every symbol kind and non-default category in use."""
    rows: dict[str, str] = {}
    for s in drawing.symbols:
        rows.setdefault(s.kind, SYMBOLS.get(s.kind, (s.kind, []))[0] or s.kind)
    for e in drawing.elements:
        if e.category not in ("default", "text"):
            cat = drawing.category(e.category)
            rows.setdefault(f"category:{cat.name}", cat.label or cat.name)
    return list(rows.items())


def page_svg(page: Page, device: DeviceProfile) -> str:
    """The rendered page as SVG, for sharing outside the tablet."""
    rgb = {e.color: e.rgb for e in COLOR_PALETTE}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{page.width}" height="{page.height}" '
        f'viewBox="0 0 {page.width} {page.height}">',
        f'<rect width="{page.width}" height="{page.height}" fill="white"/>',
        '<g fill="none" stroke-linecap="round" stroke-linejoin="round">',
    ]
    for s in page.strokes:
        r, g, b = s.rgba[:3] if s.rgba else rgb.get(s.color, (0, 0, 0))
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in s.points)
        parts.append(
            f'<polyline points="{pts}" stroke="rgb({r},{g},{b})" stroke-width="{s.width:.2f}"/>'
        )
    parts.append("</g></svg>")
    return "\n".join(parts)
