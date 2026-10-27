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
from dataclasses import dataclass

import numpy as np
from rmscene.scene_items import Pen, PenColor

from rmink.devices import COLOR_PALETTE, DeviceProfile
from rmink.drawing.font import text_paths, text_width
from rmink.drawing.model import Annotation, Category, Dimension, Drawing, Element, LineType
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
    w = text_width(dim.text, size)
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
    pen.text(dim.text, origin, size, text_st, angle)


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
        else:
            r = item.size / 2
            pts.append(
                np.array([[item.at[0] - r, item.at[1] - r], [item.at[0] + r, item.at[1] + r]])
            )
    if not pts:
        return None
    allp = np.vstack(pts)
    return allp.min(axis=0), allp.max(axis=0)


def _annotation(pen: _Pen, ann: Annotation, number: int) -> None:
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
    if ann.at is not None and box is not None:
        center = np.array(ann.at, float)
    if ann.kind == "cross":
        r = radius * 0.7
        pen.paths([np.array([center - r, center + r]),
                   np.array([center + [r, -r], center + [-r, r]])], st)  # fmt: skip
    else:
        pen.paths([_circle(center, radius)], st)
    # Number badge at the top-left of the ring (labels sit top-right), matching the remark list.
    badge = center + np.array([-radius * 0.75, -radius * 0.75])
    pen.paths([_circle(badge, 16)], st, width=1.8)
    label = str(number)
    pen.text(label, badge + [-text_width(label, 16) / 2, 8], 16, st)


def _content_bottom(strokes: list[Stroke]) -> float:
    return max((float(s.points[:, 1].max()) for s in strokes), default=0.0)


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
            y += 32
            pen.text(f"{n}. {ann.text}"[:70], (x0, y), 18, st_c)
            # A line to write the answer on, so it is clear which remark it answers.
            y += 84
            pen.text("SVAR:", (x0 + 28, y), 16, st_c)
            start = x0 + 28 + text_width("SVAR:", 16) + 12
            pen.paths([np.array([[start, y], [x1, y]])], answer_line)
            y += 12
    if d.log:
        y += 36
        pen.text("ÄNDRINGAR", (x0, y), 18, st_text)
        for line in d.log[-6:]:
            y += 30
            pen.text(line[:70], (x0, y), 16, st_text)


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
    open_remarks = [
        (i + 1, a) for i, a in enumerate(a for a in drawing.annotations if a.status == "open")
    ]
    for n, ann in open_remarks:
        _annotation(pen, ann, n)

    top = _content_bottom(pen.strokes) + _MARGIN
    _title_block(pen, top, open_remarks)
    height = max(device.height, int(_content_bottom(pen.strokes) + _MARGIN))
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
