"""Build src/rmink/workbook/data/sverige.json, the map behind workbook figures.

Sources, both free to reuse:
- Landskap: github.com/perliedman/svenska-landskap, svenska-landskap-klippt.geo.json
  (CC0, from Lantmäteriet's Distriktskarta).
- Lakes: Natural Earth ne_10m_lakes.geojson (public domain).

The landskap files do not share vertices, so simplifying them one by one leaves
double lines along every border. Instead they are rasterised and the borders
traced again: each border then exists once, as an arc between two landskap.

Usage: python tools/sverige_karta.py LANDSKAP.geo.json LAKES.geojson OUT.json
"""

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

CELL = 0.75  # km per raster cell
TOLERANCE = 1.0  # km, Douglas-Peucker on the traced borders
MIN_LOOP = 25.0  # km², smaller islands are dropped
LAT0 = 62.0
LON0 = 15.0
LAKES = ["Vänern", "Vättern", "Mälaren", "Hjälmaren", "Storsjön", "Siljan", "Torneträsk"]


def project(lon: float, lat: float) -> tuple[float, float]:
    """Sinusoidal around 15°E, close to SWEREF 99 TM: km east and km north."""
    return (lon - LON0) * 111.32 * math.cos(math.radians(lat)), (lat - LAT0) * 110.9


def polygons(feature: dict) -> list[list]:
    g = feature["geometry"]
    return g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]


def douglas_peucker(p: np.ndarray, tol: float) -> np.ndarray:
    keep = np.zeros(len(p), bool)
    keep[[0, -1]] = True
    stack = [(0, len(p) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        d = p[b] - p[a]
        n = np.hypot(*d)
        rel = p[a + 1 : b] - p[a]
        dist = np.hypot(*rel.T) if n < 1e-9 else np.abs(d[0] * rel[:, 1] - d[1] * rel[:, 0]) / n
        i = int(dist.argmax())
        if dist[i] > tol:
            keep[a + 1 + i] = True
            stack += [(a, a + 1 + i), (a + 1 + i, b)]
    return p[keep]


def area(p: np.ndarray) -> float:
    x, y = p[:, 0], p[:, 1]
    return abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))) / 2


def trace(grid: np.ndarray) -> list[tuple[list[tuple[int, int]], tuple[int, int]]]:
    """The borders of a label raster as arcs of grid corners, with the two
    labels on either side. An arc ends where three labels meet."""
    edges: dict[tuple[int, int], list[tuple[tuple[int, int], tuple[int, int]]]] = defaultdict(list)
    h, w = grid.shape
    ys, xs = np.nonzero(grid[:, 1:] != grid[:, :-1])
    for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
        a, b = (x + 1, y), (x + 1, y + 1)
        side = tuple(sorted((int(grid[y, x]), int(grid[y, x + 1]))))
        edges[a].append((b, side))
        edges[b].append((a, side))
    ys, xs = np.nonzero(grid[1:, :] != grid[:-1, :])
    for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
        a, b = (x, y + 1), (x + 1, y + 1)
        side = tuple(sorted((int(grid[y, x]), int(grid[y + 1, x]))))
        edges[a].append((b, side))
        edges[b].append((a, side))

    def is_node(v) -> bool:
        return len(edges[v]) != 2 or edges[v][0][1] != edges[v][1][1]

    seen, arcs = set(), []

    def walk(start, nxt, side):
        path, prev, cur = [start, nxt], start, nxt
        seen.add(frozenset((start, nxt)))
        while not is_node(cur) and cur != start:
            n = next(v for v, _ in edges[cur] if v != prev)
            seen.add(frozenset((cur, n)))
            path.append(n)
            prev, cur = cur, n
        return path, side

    for v in [v for v in edges if is_node(v)]:
        for n, side in edges[v]:
            if frozenset((v, n)) not in seen:
                arcs.append(walk(v, n, side))
    for v in edges:  # closed loops: islands and enclaves
        for n, side in edges[v]:
            if frozenset((v, n)) not in seen:
                arcs.append(walk(v, n, side))
    return arcs


def main(landskap: Path, lakes: Path, out: Path) -> None:
    features = json.loads(landskap.read_text())["features"]
    rings = {}
    for i, f in enumerate(features, 1):
        rings[i] = [
            np.array([project(*q[:2]) for q in r]) for poly in polygons(f) for r in poly[:1]
        ]
    pts = np.vstack([r for rs in rings.values() for r in rs])
    x0, y0 = pts.min(0) - 5
    x1, y1 = pts.max(0) + 5
    w, h = int((x1 - x0) / CELL), int((y1 - y0) / CELL)
    image = Image.new("I", (w, h), 0)
    draw = ImageDraw.Draw(image)
    for i, rs in rings.items():
        for r in rs:
            draw.polygon([((x - x0) / CELL, (y1 - y) / CELL) for x, y in r], fill=i)
    grid = np.array(image, dtype=np.int32)

    # The source is clipped at the shore, so the big lakes read as sea: give
    # their water to the nearest landskap. (The lake is then drawn on top.)
    lake_features = json.loads(lakes.read_text())["features"]
    water = Image.new("1", (w, h), 0)
    pen = ImageDraw.Draw(water)
    for name in LAKES:
        for f in lake_features:
            if f["properties"].get("name") == name:
                for poly in polygons(f):
                    q = [project(*c[:2]) for c in poly[0]]
                    pen.polygon(
                        [((x - x0) / CELL, (y1 - y) / CELL) for x, y in q], fill=1, outline=1
                    )
    mask = np.array(water, bool)
    for _ in range(4):  # reach the shore's small gaps too
        mask[1:] |= mask[:-1]
        mask[:-1] |= mask[1:]
        mask[:, 1:] |= mask[:, :-1]
        mask[:, :-1] |= mask[:, 1:]
    while True:
        todo = mask & (grid == 0)
        near = np.zeros_like(grid)
        near[1:] = np.maximum(near[1:], grid[:-1])
        near[:-1] = np.maximum(near[:-1], grid[1:])
        near[:, 1:] = np.maximum(near[:, 1:], grid[:, :-1])
        near[:, :-1] = np.maximum(near[:, :-1], grid[:, 1:])
        fill = todo & (near > 0)
        if not fill.any():
            break
        grid[fill] = near[fill]

    arcs, sides = [], []
    for path, side in trace(grid):
        p = np.array(path, float) * CELL
        p = np.column_stack([p[:, 0] + x0, y1 - p[:, 1]])
        closed = path[0] == path[-1]
        if closed and side[0] == 0 and area(p) < MIN_LOOP:
            continue
        if len(p) > 4:  # take the steps out of the raster, ends fixed
            k = np.ones(5) / 5
            q = p.copy()
            for c in range(2):
                pad = (
                    np.r_[p[:, c][-3:-1], p[:, c], p[:, c][1:3]]
                    if closed
                    else np.r_[[p[0, c]] * 2, p[:, c], [p[-1, c]] * 2]
                )
                q[1:-1, c] = np.convolve(pad, k, "valid")[1:-1]
            p = q
        if closed:
            mid = len(p) // 2  # two anchors, or a loop has no extent to measure from
            p = np.vstack(
                [douglas_peucker(p[: mid + 1], TOLERANCE), douglas_peucker(p[mid:], TOLERANCE)[1:]]
            )
        else:
            p = douglas_peucker(p, TOLERANCE)
        arcs.append(np.round(p, 1))
        sides.append(side)

    data = {
        "source": "Lantmäteriet via svenska-landskap (CC0); Natural Earth (public domain)",
        "unit": "km",
        "lon0": LON0,
        "lat0": LAT0,
    }
    data["arcs"] = [p.flatten().tolist() for p in arcs]
    data["sides"] = [[int(a), int(b)] for a, b in sides]
    data["landskap"] = [
        {"id": i, "name": f["properties"]["landskap"], "landsdel": f["properties"]["landsdel"]}
        for i, f in enumerate(features, 1)
    ]
    data["lakes"] = []
    for name in LAKES:
        found = [f for f in lake_features if f["properties"].get("name") == name]
        ring = max((r[0] for f in found for r in polygons(f)), key=len)
        p = douglas_peucker(np.array([project(*q[:2]) for q in ring]), 0.7)
        data["lakes"].append({"name": name, "ring": np.round(p, 1).flatten().tolist()})
    out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(
        len(arcs), "arcs,", sum(len(p) for p in arcs), "points,", out.stat().st_size // 1024, "KB"
    )


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
