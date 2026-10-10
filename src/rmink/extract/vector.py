"""Vector shapes (from SVG or PDF) to strokes."""

from __future__ import annotations

import numpy as np

from rmink.color.palette import is_background, nearest
from rmink.devices import DeviceProfile, PaletteEntry
from rmink.geometry.hatch import hatch_polygons
from rmink.geometry.simplify import rdp
from rmink.geometry.transform import Placement
from rmink.ingest import VectorSource
from rmink.model import Stroke
from rmink.options import ConvertOptions, FillMode

_MIN_WIDTH = 1.0
_MAX_WIDTH = 40.0


def _signed_area(ring: np.ndarray) -> float:
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _perimeter(ring: np.ndarray) -> float:
    return float(np.sum(np.hypot(*np.diff(ring, axis=0).T)))


def extract_vector(
    src: VectorSource,
    placement: Placement,
    device: DeviceProfile,
    palette: tuple[PaletteEntry, ...],
    opts: ConvertOptions,
) -> list[Stroke]:
    strokes: list[Stroke] = []
    pen = opts.pen.pen

    def make(points: np.ndarray, width: float, entry: PaletteEntry) -> None:
        pts = rdp(points, opts.simplify)
        if len(pts) >= 2 or (len(pts) == 1 and width >= 2):
            strokes.append(Stroke(pts, width=width, pen=pen, color=entry.color))

    for shape in src.shapes:
        rings = [placement.apply(p) for p in shape.subpaths]

        if shape.fill is not None and opts.fill != FillMode.none and not is_background(shape.fill):
            entry = nearest(shape.fill, palette)
            closed = [np.vstack([r, r[:1]]) if not np.allclose(r[0], r[-1]) else r for r in rings]
            closed = [r for r in closed if len(r) >= 3]
            for r in closed:
                make(r, opts.width, entry)
            if opts.fill == FillMode.hatch and closed:
                area = abs(sum(_signed_area(r) for r in closed))
                perimeter = sum(_perimeter(r) for r in closed)
                # area / (perimeter / 2) approximates the shape's thickness.
                thickness = 2 * area / perimeter if perimeter else 0.0
                if thickness > 1.2 * opts.width:
                    spacing = opts.width * 0.9
                    for seg in hatch_polygons(closed, spacing):
                        make(seg, opts.width, entry)

        if shape.stroke is not None and not is_background(shape.stroke):
            entry = nearest(shape.stroke, palette)
            width = float(np.clip(shape.stroke_width * placement.scale, _MIN_WIDTH, _MAX_WIDTH))
            for r in rings:
                make(r, width, entry)

    return strokes
