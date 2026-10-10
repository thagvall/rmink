"""SVG parsing into flattened vector shapes."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from svgelements import SVG, Close, Color, Line, Move, Shape
from svgelements import Path as SvgPath

from rmink.ingest import VectorShape, VectorSource

# Curves are sampled at roughly this fraction of the document's larger side;
# RDP simplification removes the excess later.
_SAMPLE_FRACTION = 1 / 1500


def _rgb(c: Color | None) -> tuple[int, int, int] | None:
    if c is None or c.value is None or c.alpha == 0:
        return None
    return (c.red, c.green, c.blue)


def _flatten(path: SvgPath, step: float) -> tuple[list[np.ndarray], list[bool]]:
    subpaths: list[np.ndarray] = []
    closed: list[bool] = []
    current: list[complex] = []
    is_closed = False

    def flush():
        nonlocal current, is_closed
        if len(current) >= 1:
            arr = np.array([[p.real, p.imag] for p in current])
            subpaths.append(arr)
            closed.append(is_closed)
        current, is_closed = [], False

    for seg in path:
        if isinstance(seg, Move):
            flush()
            current = [complex(*seg.end)]
        elif isinstance(seg, Close):
            if current:
                current.append(current[0])
            is_closed = True
            flush()
        elif isinstance(seg, Line):
            if not current:
                current = [complex(*seg.start)]
            current.append(complex(*seg.end))
        else:
            if not current and seg.start is not None:
                current = [complex(*seg.start)]
            # Estimate length from a coarse polyline, then sample densely.
            coarse = seg.npoint(np.linspace(0, 1, 9))
            approx_len = float(np.sum(np.hypot(*np.diff(coarse, axis=0).T)))
            n = int(np.clip(np.ceil(approx_len / step), 2, 400))
            for x, y in seg.npoint(np.linspace(0, 1, n + 1))[1:]:
                current.append(complex(x, y))
    flush()
    return subpaths, closed


def parse_svg_text(text: str, label: str, px_per_unit_at_dpi: float = 1 / 96) -> VectorSource:
    svg = SVG.parse(io.StringIO(text), reify=True)
    vb = svg.viewbox
    if vb is not None and vb.width and vb.height:
        width, height = float(vb.width), float(vb.height)
    else:
        width, height = float(svg.width or 1000), float(svg.height or 1000)
    step = max(width, height) * _SAMPLE_FRACTION

    shapes: list[VectorShape] = []
    for el in svg.elements():
        if not isinstance(el, Shape):
            continue
        if el.values.get("visibility") == "hidden" or el.values.get("display") == "none":
            continue
        fill, stroke = _rgb(el.fill), _rgb(el.stroke)
        if fill is None and stroke is None:
            continue
        subpaths, closed = _flatten(SvgPath(el), step)
        if not subpaths:
            continue
        sw = el.implicit_stroke_width if stroke is not None else 0.0
        shapes.append(VectorShape(subpaths, closed, fill, stroke, float(sw or 0.0)))

    return VectorSource(label, width, height, shapes, px_per_unit_at_dpi)


def load_svg(path: Path) -> VectorSource:
    return parse_svg_text(path.read_text(encoding="utf-8"), path.name)
