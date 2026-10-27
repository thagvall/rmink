"""Turn sketch strokes into numbered groups with fitted shapes.

The interpreter (Claude) decides what a group *means*: a wall, a dimension, a
symbol, a word. It refers to groups by number and reuses the fitted geometry
here instead of guessing coordinates from the picture, so clean drawings stay
true to the sketch.

Grouping is deliberately simple: small strokes close together (handwriting,
arrowheads, symbols) merge into one group; long strokes stand alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from rmink.devices import COLOR_PALETTE, DeviceProfile
from rmink.geometry.simplify import rdp
from rmink.model import Page, Stroke
from rmink.render.preview import render_lines
from rmink.writer.rm_v6 import page_lines

_SMALL = 70.0  # px: strokes whose bounding box is smaller than this are "small"
_GAP = 28.0  # px: small strokes closer than this join a group


@dataclass
class Group:
    id: int
    strokes: list[int]  # indices into the page's strokes
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1
    shape: str  # line | polyline | closed | circle | arc | mark
    fit: dict = field(default_factory=dict)
    layer: str = ""
    color: str = "black"

    def summary(self) -> dict:
        return {
            "group": self.id,
            "shape": self.shape,
            "bbox": [round(v) for v in self.bbox],
            "strokes": len(self.strokes),
            "layer": self.layer,
            "color": self.color,
            **self.fit,
        }


def _bbox(points: np.ndarray) -> tuple[float, float, float, float]:
    lo, hi = points.min(axis=0), points.max(axis=0)
    return float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])


def _bbox_gap(a, b) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return math.hypot(dx, dy)


def _is_small(b) -> bool:
    return max(b[2] - b[0], b[3] - b[1]) < _SMALL


def group_strokes(strokes: list[Stroke]) -> list[list[int]]:
    boxes = [_bbox(s.points) for s in strokes]
    parent = list(range(len(strokes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    small = [i for i, b in enumerate(boxes) if _is_small(b)]
    for k, i in enumerate(small):
        for j in small[k + 1 :]:
            if strokes[i].layer == strokes[j].layer and _bbox_gap(boxes[i], boxes[j]) < _GAP:
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(strokes)):
        groups.setdefault(find(i), []).append(i)
    # Reading order: top to bottom in bands, then left to right.
    return sorted(
        groups.values(),
        key=lambda g: (round(min(boxes[i][1] for i in g) / 80), min(boxes[i][0] for i in g)),
    )


def fit_line(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Endpoints of the best straight line and the RMS distance to it."""
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c)
    d = vt[0]
    t = (points - c) @ d
    normal = np.array([-d[1], d[0]])
    rms = float(np.sqrt(np.mean(((points - c) @ normal) ** 2)))
    return np.array([c + d * t.min(), c + d * t.max()]), rms


def fit_circle(points: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Centre, radius and RMS radial error of the least-squares circle (Kåsa)."""
    x, y = points[:, 0], points[:, 1]
    a = np.column_stack([x, y, np.ones_like(x)])
    b = x**2 + y**2
    (p, q, r), *_ = np.linalg.lstsq(a, b, rcond=None)
    center = np.array([p / 2, q / 2])
    radius = math.sqrt(max(r + center @ center, 0.0))
    rms = float(np.sqrt(np.mean((np.hypot(x - center[0], y - center[1]) - radius) ** 2)))
    return center, radius, rms


def _round_pts(pts) -> list[list[float]]:
    return [[round(float(x), 1), round(float(y), 1)] for x, y in pts]


def resample(points: np.ndarray, step: float = 5.0) -> np.ndarray:
    """Points evenly spaced along the polyline, so fits weigh every part of a
    stroke by its length rather than by how many points the pen recorded there."""
    seg = np.hypot(*np.diff(points, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if cum[-1] == 0:
        return points[:1]
    d = np.linspace(0, cum[-1], max(int(cum[-1] / step), 2) + 1)
    return np.column_stack([np.interp(d, cum, points[:, 0]), np.interp(d, cum, points[:, 1])])


def classify(points: np.ndarray) -> tuple[str, dict]:
    """Best simple shape for one long stroke."""
    raw = np.asarray(points, dtype=float)
    points = resample(raw)
    b = _bbox(points)
    size = max(b[2] - b[0], b[3] - b[1], 1.0)
    (p0, p1), rms = fit_line(points)
    if rms < max(2.5, size * 0.02):
        angle = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        return "line", {
            "points": _round_pts([p0, p1]),
            "length_px": round(float(np.linalg.norm(p1 - p0)), 1),
            "angle_deg": round(angle, 1),
        }
    closed = np.linalg.norm(points[0] - points[-1]) < max(size * 0.12, 12)
    center, radius, crms = fit_circle(points)
    if crms < max(2.5, radius * 0.06) and radius < size:
        ang = np.degrees(np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0]))
        fit = {"center": _round_pts([center])[0], "radius": round(radius, 1)}
        # Hand-drawn circles often overshoot their start; a sweep of nearly a
        # full turn is a circle even when the ends do not meet.
        sweep = abs(float(np.unwrap(np.radians(ang))[-1] - np.radians(ang[0])))
        if closed or sweep > np.radians(330):
            return "circle", fit
        return "arc", {
            **fit,
            "start_angle": round(float(ang[0]), 1),
            "end_angle": round(float(ang[-1]), 1),
        }
    simple = rdp(raw, max(4.0, size * 0.025))
    return ("closed" if closed else "polyline"), {
        "points": _round_pts(simple),
        "closed": bool(closed),
    }


def analyse(
    page: Page, device: DeviceProfile, known_ids: set[tuple[int, int]] | None = None
) -> list[Group]:
    """Numbered groups for the strokes of ``page``. Strokes whose ids are in
    ``known_ids`` (rmink's own from the previous revision) are left out."""
    known_ids = known_ids or set()
    palette = {e.color: e.name for e in COLOR_PALETTE}
    keep = [i for i, s in enumerate(page.strokes) if s.id is None or tuple(s.id) not in known_ids]
    strokes = [page.strokes[i] for i in keep]
    out = []
    for n, idx in enumerate(group_strokes(strokes), start=1):
        pts = np.vstack([strokes[i].points for i in idx])
        bbox = _bbox(pts)
        if len(idx) == 1 and not _is_small(bbox):
            shape, fit = classify(strokes[idx[0]].points)
        else:
            shape, fit = "mark", {}
        first = strokes[idx[0]]
        color = palette.get(first.color, first.color.name.lower())
        out.append(Group(n, [keep[i] for i in idx], bbox, shape, fit, first.layer, color))
    return out


def _font(size: int):
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow without FreeType
        return ImageFont.load_default()


def overlay(
    page: Page, device: DeviceProfile, groups: list[Group], scale: float = 0.6
) -> Image.Image:
    """The sketch faded, with every group boxed and numbered in red."""
    img = render_lines(page_lines(page, device), device, page.height).convert("RGB")
    faded = Image.blend(Image.new("RGB", img.size, "white"), img, 0.55)
    draw = ImageDraw.Draw(faded)
    font = _font(26)
    for g in groups:
        x0, y0, x1, y1 = g.bbox
        draw.rectangle((x0 - 4, y0 - 4, x1 + 4, y1 + 4), outline=(220, 30, 30), width=2)
        label = str(g.id)
        # Long thin groups (walls, lines) get their number at the middle so
        # numbers of lines meeting at a corner do not pile up.
        if x1 - x0 > 4 * max(y1 - y0, 1):
            tx, ty = (x0 + x1) / 2, max(y0 - 32, 0)
        elif y1 - y0 > 4 * max(x1 - x0, 1):
            tx, ty = x1 + 8, (y0 + y1) / 2
        else:
            tx, ty = x0 - 4, max(y0 - 32, 0)
        box = draw.textbbox((tx, ty), label, font=font)
        draw.rectangle(box, fill=(220, 30, 30))
        draw.text((tx, ty), label, fill="white", font=font)
    if scale != 1:
        faded = faded.resize(
            (round(faded.width * scale), round(faded.height * scale)), Image.Resampling.LANCZOS
        )
    return faded
