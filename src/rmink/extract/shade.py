"""Grey tones as pen strokes: stippling, halftone, hatching and pencil.

Every style works on a tone map (0 = paper, 1 = black) in tone pixels and
returns polylines in the same coordinates. Sizes are given in device pixels
and converted with ``to_dev`` (device px per tone px).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image
from rmscene.scene_items import Pen
from scipy import ndimage

from rmink.geometry.hatch import _join_scanlines
from rmink.options import Shading

# More dots or lines than this make a page slow to open and page through.
MAX_SHADE_STROKES = 20_000

# Tone thresholds where hatching adds its next, denser layer of lines.
_LEVELS = (0.12, 0.3, 0.5, 0.72)
_CROSS_ANGLES = (45.0, 135.0, 0.0, 90.0)


@dataclass
class ShadePath:
    points: np.ndarray  # (N, 2) tone px
    width: float  # device px
    widths: np.ndarray | None = None  # per point, device px
    pressures: np.ndarray | None = None  # per point, 0-255


@dataclass
class ShadeResult:
    paths: list[ShadePath]
    pen: Pen | None  # None: use the pen chosen for the lines


def shade(
    tone: np.ndarray,
    style: Shading,
    to_dev: float,
    pen_width: float,
    density: float = 1.0,
    budget: int = 100_000,
) -> ShadeResult:
    """Strokes that reproduce ``tone`` in ``style`` within ``budget`` points."""
    if style == Shading.none or not (tone > 0.05).any():
        return ShadeResult([], None)
    if style == Shading.stipple:
        return ShadeResult(stipple(tone, to_dev, pen_width, density, budget), None)
    if style == Shading.halftone:
        return ShadeResult(halftone(tone, to_dev, density, budget), None)
    if style == Shading.hatch:
        return ShadeResult(hatch(tone, to_dev, pen_width, density, budget, cross=False), None)
    if style == Shading.crosshatch:
        return ShadeResult(hatch(tone, to_dev, pen_width, density, budget, cross=True), None)
    if style == Shading.pencil:
        return ShadeResult(pencil(tone, to_dev, pen_width, density, budget), Pen.PENCIL_2)
    raise ValueError(f"Unknown shading: {style}")


def _dot(x: float, y: float, w: float, to_dev: float) -> ShadePath:
    # Two points a hair apart: a single-point line may not render on the tablet.
    d = 0.25 / to_dev
    return ShadePath(np.array([[x - d, y], [x + d, y]]), w)


def _cells(tone: np.ndarray, cell: float) -> np.ndarray:
    """Mean tone per ``cell`` x ``cell`` block."""
    h, w = tone.shape
    gh, gw = max(1, round(h / cell)), max(1, round(w / cell))
    img = Image.fromarray(tone.astype(np.float32))
    return np.asarray(img.resize((gw, gh), Image.Resampling.BOX), dtype=np.float64)


def stipple(
    tone: np.ndarray, to_dev: float, pen_width: float, density: float, budget: int
) -> list[ShadePath]:
    """Dots whose number per area follows the tone (error diffusion on a grid,
    jittered so no grid pattern shows)."""
    cell = max(pen_width, 1.5) * 1.8 / np.sqrt(density) / to_dev  # tone px
    max_dots = min(MAX_SHADE_STROKES, budget // 2)
    # Each cell gets at most one dot, so the expected count is the tone sum.
    expected = tone.sum() / cell**2
    if expected > max_dots:
        cell *= np.sqrt(expected / max_dots)
    # Dots grow with the cells, so a dark area still reads as dark.
    dot = max(max(pen_width, 1.5) * 1.2, cell * to_dev * 0.75)  # device px
    grid = _cells(tone, cell)
    gh, gw = grid.shape
    sy, sx = tone.shape[0] / gh, tone.shape[1] / gw
    err = grid.copy()
    on = np.zeros_like(grid, dtype=bool)
    # Floyd-Steinberg, serpentine so errors do not drift to one side.
    for y in range(gh):
        xs = range(gw) if y % 2 == 0 else range(gw - 1, -1, -1)
        step = 1 if y % 2 == 0 else -1
        row, nxt = err[y], err[y + 1] if y + 1 < gh else None
        for x in xs:
            v = row[x]
            if v < 0.04:
                q = 0.0
            else:
                q = 1.0 if v >= 0.5 else 0.0
            on[y, x] = q > 0
            e = v - q
            if 0 <= x + step < gw:
                row[x + step] += e * 7 / 16
            if nxt is not None:
                if 0 <= x - step < gw:
                    nxt[x - step] += e * 3 / 16
                nxt[x] += e * 5 / 16
                if 0 <= x + step < gw:
                    nxt[x + step] += e * 1 / 16
    rng = np.random.default_rng(0)
    ys, xs = np.nonzero(on)
    jitter = rng.uniform(-0.3, 0.3, size=(len(ys), 2))
    px = (xs + 0.5 + jitter[:, 0]) * sx
    py = (ys + 0.5 + jitter[:, 1]) * sy
    return [_dot(x, y, dot, to_dev) for x, y in zip(px, py, strict=True)]


def halftone(tone: np.ndarray, to_dev: float, density: float, budget: int) -> list[ShadePath]:
    """A 45-degree dot screen; dot area follows the tone, like newsprint."""
    cell = 7.0 / np.sqrt(density) / to_dev  # tone px between dot centres
    max_dots = min(MAX_SHADE_STROKES, budget // 2)
    lit = (tone > 0.06).sum() / cell**2
    if lit > max_dots:
        cell *= np.sqrt(lit / max_dots)
    h, w = tone.shape
    smooth = ndimage.gaussian_filter(tone, cell / 3)
    c, s = np.cos(np.pi / 4), np.sin(np.pi / 4)
    r = np.hypot(h, w) / 2 + cell
    u = np.arange(-r, r, cell)
    uu, vv = np.meshgrid(u, u)
    x = uu * c - vv * s + w / 2
    y = uu * s + vv * c + h / 2
    inside = (x >= 0) & (x < w - 0.5) & (y >= 0) & (y < h - 0.5)
    x, y = x[inside], y[inside]
    t = smooth[np.round(y).astype(int), np.round(x).astype(int)]
    # Dot area proportional to tone; full tone just touches the neighbours.
    d = cell * to_dev * 1.13 * np.sqrt(np.clip(t, 0, 1))
    keep = (t > 0.06) & (d >= 0.8)
    return [
        _dot(px, py, float(dw), to_dev)
        for px, py, dw in zip(x[keep], y[keep], d[keep], strict=True)
    ]


def _scanlines(mask: np.ndarray, spacing: float, angle_deg: float, phase: float):
    """Hatch lines at ``angle_deg`` across ``mask``, joined into zig-zags.

    Lines run at ``v = phase + k * spacing`` in a frame rotated by the angle.
    """
    h, w = mask.shape
    th = np.radians(angle_deg)
    c, s = np.cos(th), np.sin(th)
    corners = np.array([[0, 0], [w, 0], [0, h], [w, h]], dtype=np.float64)
    us = corners[:, 0] * c + corners[:, 1] * s
    vs = -corners[:, 0] * s + corners[:, 1] * c
    u = np.arange(np.floor(us.min()), np.ceil(us.max()) + 1, 1.0)
    v0 = np.floor((vs.min() - phase) / spacing) * spacing + phase
    v = np.arange(v0, vs.max() + spacing, spacing)
    if len(v) == 0 or len(u) == 0:
        return []
    uu, vv = np.meshgrid(u, v)
    x = uu * c - vv * s
    y = uu * s + vv * c
    hit = ndimage.map_coordinates(mask.astype(np.uint8), [y, x], order=0, cval=0) > 0
    rows = []
    for row in hit:
        d = np.diff(np.concatenate([[0], row.astype(np.int8), [0]]))
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1) - 1
        rows.append([(u[a], u[b]) for a, b in zip(starts, ends, strict=True) if b > a])
    out = []
    for path in _join_scanlines(rows, float(v[0]), spacing, max_jump=2 * spacing):
        pu, pv = path[:, 0], path[:, 1]
        out.append(np.stack([pu * c - pv * s, pu * s + pv * c], axis=1))
    return out


def _hatch_layers(cross: bool, base: float) -> list[tuple[float, float, float, float]]:
    """(threshold, spacing, angle, phase) per tone level.

    Plain hatching adds lines between the existing ones as it gets darker;
    crosshatching adds a new direction instead.
    """
    if cross:
        return [(t, base, a, 0.0) for t, a in zip(_LEVELS, _CROSS_ANGLES, strict=True)]
    layers = [(_LEVELS[0], base, 45.0, 0.0)]
    for k, t in enumerate(_LEVELS[1:]):
        layers.append((t, base / 2**k, 45.0, base / 2 ** (k + 1)))
    return layers


def hatch(
    tone: np.ndarray,
    to_dev: float,
    pen_width: float,
    density: float,
    budget: int,
    cross: bool,
) -> list[ShadePath]:
    base = max(pen_width, 1.0) * (6.0 if cross else 8.0) / density / to_dev
    smooth = ndimage.gaussian_filter(tone, max(1.0, base / 4))
    for _ in range(6):
        paths = []
        for t, spacing, angle, phase in _hatch_layers(cross, base):
            mask = ndimage.binary_opening(smooth > t, iterations=1)
            paths.extend(_scanlines(mask, spacing, angle, phase))
        points = sum(len(p) for p in paths)
        if points <= budget and len(paths) <= MAX_SHADE_STROKES:
            break
        base *= 1.4
    return [ShadePath(p, pen_width) for p in paths]


def _resample(path: np.ndarray, step: float) -> tuple[np.ndarray, np.ndarray]:
    """Points every ``step`` along each segment, and a mask of the corners."""
    out, corner = [path[:1]], [True]
    for a, b in zip(path[:-1], path[1:], strict=True):
        n = max(1, int(np.ceil(np.hypot(*(b - a)) / step)))
        t = np.arange(1, n + 1)[:, None] / n
        out.append(a + (b - a) * t)
        corner.extend([False] * (n - 1) + [True])
    return np.vstack(out), np.array(corner)


def pencil(
    tone: np.ndarray, to_dev: float, pen_width: float, density: float, budget: int
) -> list[ShadePath]:
    """Close diagonal pencil lines; pressure and width follow the tone, so the
    tablet's pencil texture does the grey."""
    spacing = max(pen_width, 1.0) * 2.0 / density / to_dev
    step = 4.0 / to_dev
    smooth = ndimage.gaussian_filter(tone, max(1.0, spacing / 2))
    mask = ndimage.binary_opening(smooth > 0.08, iterations=1)
    h, w = tone.shape
    for _ in range(8):
        lines = _scanlines(mask, spacing, 45.0, 0.0)
        out = []
        total = 0
        for line in lines:
            pts, corners = _resample(line, step)
            t = smooth[
                np.clip(np.round(pts[:, 1]).astype(int), 0, h - 1),
                np.clip(np.round(pts[:, 0]).astype(int), 0, w - 1),
            ]
            # Keep the corners, and inner points only where the pressure changes.
            p = 40 + 215 * np.clip(t, 0, 1)
            keep = corners.copy()
            last = p[0]
            for i in range(1, len(pts) - 1):
                if abs(p[i] - last) > 12:
                    keep[i] = True
                    last = p[i]
            pts, p, t = pts[keep], p[keep], t[keep]
            widths = pen_width * (0.7 + 0.8 * np.clip(t, 0, 1))
            out.append(ShadePath(pts, pen_width, widths=widths, pressures=p))
            total += len(pts)
        if total <= budget and len(out) <= MAX_SHADE_STROKES:
            return out
        spacing *= 1.4
    return out
