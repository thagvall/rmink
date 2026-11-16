"""Maps for workbooks: Sweden and its 25 landskap, as line art.

:class:`rmink.workbook.model.MapFigure` says what a figure shows. The map is
drawn into the PDF as vectors, so it stays sharp and is not ink: the reader can
write on it and a round does not read it. What must stay hidden until the facit
is on (the names, and the borders on a blank map) is ink on the "Facit" layer.

The data is ``data/sverige.json``, built by ``tools/sverige_karta.py``: each
border is one arc in km on a plane, with the landskap on either side of it.

Names go inside a landskap when they fit, otherwise out to the side with a
leader line, in columns west and east of the map, sorted so leaders do not cross.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

import numpy as np

from rmink.workbook.model import MapFigure

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 on the page, y down

# Cities the maps can pin, as (longitude, latitude).
CITIES = {
    "Stockholm": (18.07, 59.33), "Göteborg": (11.97, 57.71), "Malmö": (13.00, 55.60),
    "Uppsala": (17.64, 59.86), "Linköping": (15.62, 58.41), "Örebro": (15.21, 59.27),
    "Västerås": (16.55, 59.61), "Karlstad": (13.50, 59.38), "Falun": (15.63, 60.61),
    "Gävle": (17.14, 60.67), "Sundsvall": (17.31, 62.39), "Östersund": (14.64, 63.18),
    "Umeå": (20.26, 63.83), "Luleå": (22.15, 65.58), "Kiruna": (20.22, 67.86),
    "Visby": (18.30, 57.64), "Kalmar": (16.36, 56.66), "Växjö": (14.81, 56.88),
    "Halmstad": (12.86, 56.67), "Jönköping": (14.16, 57.78), "Åmål": (12.70, 59.05),
}  # fmt: skip


@dataclass(frozen=True)
class Landskap:
    name: str
    landsdel: str
    rings: tuple[np.ndarray, ...]
    anchor: tuple[float, float]  # the point deepest inside, in km


@dataclass(frozen=True)
class Sverige:
    arcs: tuple[np.ndarray, ...]
    sides: tuple[tuple[int, int], ...]
    landskap: dict[str, Landskap]
    lakes: dict[str, np.ndarray]
    lon0: float
    lat0: float

    def city(self, name: str) -> tuple[float, float]:
        lon, lat = CITIES[name]
        return (lon - self.lon0) * 111.32 * np.cos(np.radians(lat)), (lat - self.lat0) * 110.9


def _rings(arcs: list[np.ndarray]) -> list[np.ndarray]:
    """Chain the arcs around one landskap into closed rings."""
    left = list(arcs)
    rings = []
    while left:
        ring = [left.pop()]
        while not np.allclose(ring[-1][-1], ring[0][0], atol=0.051) and left:
            end = ring[-1][-1]
            d = [min(np.hypot(*(a[0] - end)), np.hypot(*(a[-1] - end))) for a in left]
            i = int(np.argmin(d))
            if d[i] > 0.2:
                break
            a = left.pop(i)
            ring.append(a if np.hypot(*(a[0] - end)) <= np.hypot(*(a[-1] - end)) else a[::-1])
        rings.append(np.vstack(ring))
    return rings


def _inside(p: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """For points ``p`` (n, 2): whether they are in ``ring``, by crossing count."""
    a, b = ring, np.roll(ring, -1, axis=0)
    x, y = p[:, 0][:, None], p[:, 1][:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        cross = ((a[:, 1] > y) != (b[:, 1] > y)) & (
            x < (b[:, 0] - a[:, 0]) * (y - a[:, 1]) / (b[:, 1] - a[:, 1]) + a[:, 0]
        )
    return cross.sum(axis=1) % 2 == 1


def contains(rings: tuple[np.ndarray, ...], point: tuple[float, float]) -> bool:
    p = np.array([point], float)
    return any(bool(_inside(p, r)[0]) for r in rings)


def _anchor(rings: list[np.ndarray]) -> tuple[float, float]:
    """The point of the biggest ring farthest from its edge, on a coarse grid."""

    def size(r: np.ndarray) -> float:
        x, y = r[:, 0], r[:, 1]
        return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))

    ring = max(rings, key=size)
    lo, hi = ring.min(0), ring.max(0)
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 36), np.linspace(lo[1], hi[1], 36))
    pts = np.column_stack([gx.ravel(), gy.ravel()])
    pts = pts[_inside(pts, ring)]
    seg = np.diff(np.vstack([ring, ring[:1]]), axis=0)
    t = ((pts[:, None] - ring) * seg).sum(2) / np.maximum((seg * seg).sum(1), 1e-9)
    near = ring + np.clip(t, 0, 1)[..., None] * seg
    return tuple(
        float(v) for v in pts[np.hypot(*np.moveaxis(pts[:, None] - near, 2, 0)).min(1).argmax()]
    )


@lru_cache(maxsize=1)
def sverige() -> Sverige:
    data = json.loads(resources.files("rmink.workbook.data").joinpath("sverige.json").read_text())
    arcs = [np.array(a).reshape(-1, 2) for a in data["arcs"]]
    sides = [tuple(s) for s in data["sides"]]
    landskap = {}
    for item in data["landskap"]:
        rings = _rings([a for a, s in zip(arcs, sides, strict=True) if item["id"] in s])
        landskap[item["name"]] = Landskap(
            item["name"], item["landsdel"], tuple(rings), _anchor(rings)
        )
    lakes = {x["name"]: np.array(x["ring"]).reshape(-1, 2) for x in data["lakes"]}
    return Sverige(tuple(arcs), tuple(sides), landskap, lakes, data["lon0"], data["lat0"])


def names() -> list[str]:
    return list(sverige().landskap)


def landsdel(name: str) -> list[str]:
    return [n for n, x in sverige().landskap.items() if x.landsdel == name]


def expand(items: list[str]) -> list[str]:
    """Landskap, with a landsdel (or "Sverige") standing for all of its own."""
    out: list[str] = []
    for item in items:
        out += names() if item == "Sverige" else landsdel(item) or [item]
    return list(dict.fromkeys(out))


def check(figure: MapFigure) -> None:
    """``ValueError`` for a name the map does not have."""
    for item in expand([*figure.view, *figure.highlight, *figure.labels, *figure.solution_labels]):
        if item not in sverige().landskap:
            raise ValueError(f"Okänt landskap på kartan: {item}. Finns: {', '.join(names())}.")
    for city in [*figure.pins, *figure.solution_pins]:
        if city not in CITIES:
            raise ValueError(f"Okänd stad på kartan: {city}. Finns: {', '.join(CITIES)}.")
    for lake in figure.lakes:
        if lake not in sverige().lakes:
            raise ValueError(f"Okänd sjö på kartan: {lake}. Finns: {', '.join(sverige().lakes)}.")


@dataclass(frozen=True)
class View:
    """From map km to page points, so that the map fits ``box``."""

    scale: float
    ox: float
    oy: float

    def page(self, p) -> np.ndarray:
        p = np.asarray(p, float)
        return (
            np.column_stack([self.ox + p[..., 0] * self.scale, self.oy - p[..., 1] * self.scale])
            if p.ndim == 2
            else np.array([self.ox + p[0] * self.scale, self.oy - p[1] * self.scale])
        )


def view_of(figure: MapFigure, box: Box) -> View:
    m = sverige()
    chosen = expand(figure.view) or names()
    pts = np.vstack([r for n in chosen for r in m.landskap[n].rings])
    lo, hi = pts.min(0), pts.max(0)
    x0, y0, x1, y1 = box
    # Room on the sides for the names that go out with a leader.
    side = min(70.0, (x1 - x0) * 0.24) if figure.labels or figure.solution_labels else 0.0
    scale = min((x1 - x0 - 2 * side) / max(hi[0] - lo[0], 1), (y1 - y0) / max(hi[1] - lo[1], 1))
    cx, cy = (lo + hi) / 2
    return View(float(scale), (x0 + x1) / 2 - cx * scale, (y0 + y1) / 2 + cy * scale)


def clipped(p: np.ndarray, box: Box) -> list[np.ndarray]:
    """The parts of a polyline inside ``box``: a zoomed map stops at its frame."""
    x0, y0, x1, y1 = box
    ok = (p[:, 0] >= x0) & (p[:, 0] <= x1) & (p[:, 1] >= y0) & (p[:, 1] <= y1)
    runs, i = [], 0
    while i < len(p):
        if ok[i]:
            j = i
            while j + 1 < len(p) and ok[j + 1]:
                j += 1
            if j > i:
                runs.append(p[i : j + 1])
            i = j + 1
        else:
            i += 1
    return runs


def clipped_area(p: np.ndarray, box: Box) -> np.ndarray:
    """The part of a closed ring inside ``box`` (Sutherland-Hodgman): a filled lake or
    landskap at the edge of a zoomed map must not paint over the text around it.
    Empty when nothing is inside."""
    x0, y0, x1, y1 = box
    for axis, edge, keep in ((0, x0, 1), (0, x1, -1), (1, y0, 1), (1, y1, -1)):
        if not len(p):
            break
        inside = (p[:, axis] - edge) * keep >= 0
        out = []
        for i in range(len(p)):
            a, b = p[i - 1], p[i]
            if inside[i - 1] != inside[i]:
                out.append(a + (b - a) * (edge - a[axis]) / (b[axis] - a[axis]))
            if inside[i]:
                out.append(b)
        p = np.array(out).reshape(-1, 2)
    return p


def outline(view: View, box: Box) -> list[np.ndarray]:
    """The coast and the borders with Norway and Finland."""
    m = sverige()
    return [
        q
        for a, s in zip(m.arcs, m.sides, strict=True)
        if s[0] == 0
        for q in clipped(view.page(a), box)
    ]


def borders(view: View, box: Box) -> list[np.ndarray]:
    """The borders between landskap."""
    m = sverige()
    return [
        q
        for a, s in zip(m.arcs, m.sides, strict=True)
        if s[0] != 0
        for q in clipped(view.page(a), box)
    ]


def lake_paths(figure: MapFigure, view: View, box: Box) -> list[np.ndarray]:
    m = sverige()
    out = []
    for name in figure.lakes:
        p = clipped_area(view.page(m.lakes[name]), box)
        if len(p) > 2:
            out.append(p)
    return out


@dataclass(frozen=True)
class Label:
    text: str
    at: tuple[float, float]  # baseline start
    leader: tuple[tuple[float, float], tuple[float, float]] | None = None


def _width_at(rings, x: float, y: float) -> float:
    """How wide the landskap is along the row through (x, y), in km."""
    xs = np.linspace(x - 260, x + 260, 261)
    pts = np.column_stack([xs, np.full_like(xs, y)])
    inside = np.any([_inside(pts, r) for r in rings], axis=0)
    i = int(np.abs(xs - x).argmin())
    if not inside[i]:
        return 0.0
    a = i
    while a > 0 and inside[a - 1]:
        a -= 1
    b = i
    while b < len(xs) - 1 and inside[b + 1]:
        b += 1
    return float(xs[b] - xs[a])


def place_labels(items: list[str], view: View, box: Box, width, line: float) -> list[Label]:
    """Labels for landskap names: inside when ``width(text)`` fits, otherwise in
    a column on the side nearest the map's edge. ``line`` is the row height."""
    m = sverige()
    x0, y0, x1, y1 = box
    out: list[Label] = []
    outside: list[tuple[str, np.ndarray]] = []
    for name in items:
        ls = m.landskap[name]
        at = view.page(np.array(ls.anchor))
        w = width(name)
        if w + 3 <= _width_at(ls.rings, *ls.anchor) * view.scale * 0.92:
            out.append(Label(name, (float(at[0] - w / 2), float(at[1] + line * 0.3))))
        else:
            outside.append((name, at))
    if outside:
        # East of the map's spine goes east; the spine follows Sweden's lean.
        def spine(y: float) -> float:
            km = (view.oy - y) / view.scale
            return view.ox + (40 + 0.1 * km) * view.scale

        for east in (False, True):
            col = sorted(
                [o for o in outside if (o[1][0] > spine(o[1][1])) == east], key=lambda o: o[1][1]
            )
            if not col:
                continue
            ys = [float(o[1][1]) for o in col]
            for i in range(1, len(ys)):
                ys[i] = max(ys[i], ys[i - 1] + line)
            over = ys[-1] - (y1 - 2)
            if over > 0:
                ys = [y - over for y in ys]
                for i in range(len(ys) - 2, -1, -1):
                    ys[i] = min(ys[i], ys[i + 1] - line)
            shift = (y0 + line) - ys[0]
            if shift > 0:
                ys = [y + shift for y in ys]
            for (name, at), y in zip(col, ys, strict=True):
                w = width(name)
                x = x1 - w if east else x0
                end = x - 2 if east else x + w + 2
                out.append(
                    Label(name, (x, y + line * 0.3), ((end, y), (float(at[0]), float(at[1]))))
                )
    return out
