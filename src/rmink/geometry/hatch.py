"""Scanline hatching of filled regions."""

from __future__ import annotations

import numpy as np


def hatch_polygons(rings: list[np.ndarray], spacing: float) -> list[np.ndarray]:
    """Horizontal hatch segments filling ``rings`` with the even-odd rule.

    Consecutive segments on adjacent scanlines that overlap are joined into a
    zig-zag so a filled shape becomes a handful of strokes instead of hundreds.
    """
    edges = []
    for ring in rings:
        if len(ring) < 3:
            continue
        r = np.asarray(ring, dtype=np.float64)
        if not np.allclose(r[0], r[-1]):
            r = np.vstack([r, r[:1]])
        edges.append(np.stack([r[:-1], r[1:]], axis=1))
    if not edges:
        return []
    e = np.concatenate(edges)  # (M, 2, 2)
    e = e[e[:, 0, 1] != e[:, 1, 1]]
    if len(e) == 0:
        return []
    y0, y1 = e[:, 0, 1], e[:, 1, 1]
    ymin, ymax = min(y0.min(), y1.min()), max(y0.max(), y1.max())

    rows: list[list[tuple[float, float]]] = []
    for y in np.arange(ymin + spacing / 2, ymax, spacing):
        hit = (np.minimum(y0, y1) <= y) & (np.maximum(y0, y1) > y)
        if not hit.any():
            rows.append([])
            continue
        he = e[hit]
        t = (y - he[:, 0, 1]) / (he[:, 1, 1] - he[:, 0, 1])
        xs = np.sort(he[:, 0, 0] + t * (he[:, 1, 0] - he[:, 0, 0]))
        rows.append([(xs[i], xs[i + 1]) for i in range(0, len(xs) - 1, 2)])
    return _join_scanlines(rows, ymin + spacing / 2, spacing)


def hatch_mask(mask: np.ndarray, spacing: float) -> list[np.ndarray]:
    """Horizontal hatch segments for a boolean raster mask (pixel coordinates)."""
    h = mask.shape[0]
    step = max(1, int(round(spacing)))
    start = step // 2
    rows: list[list[tuple[float, float]]] = []
    for y in range(start, h, step):
        row = mask[y].astype(np.int8)
        d = np.diff(np.concatenate([[0], row, [0]]))
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1) - 1
        rows.append([(float(a), float(b)) for a, b in zip(starts, ends, strict=True)])
    return _join_scanlines(rows, float(start), float(step))


def _join_scanlines(
    rows: list[list[tuple[float, float]]],
    y_start: float,
    spacing: float,
    max_jump: float | None = None,
) -> list[np.ndarray]:
    """Join spans on consecutive rows into zig-zags.

    ``max_jump`` limits how far the connecting segment may run sideways, so
    spans of very different length are not joined by a long diagonal.
    """
    done: list[list[tuple[float, float]]] = []
    # (points, last span, whether the path currently ends on the span's right side)
    open_paths: list[tuple[list[tuple[float, float]], tuple[float, float], bool]] = []
    for i, row in enumerate(rows):
        y = y_start + i * spacing
        new_open = []
        used = set()
        for path, (a0, a1), on_right in open_paths:
            match = None
            for j, (b0, b1) in enumerate(row):
                if j not in used and b0 <= a1 and b1 >= a0:
                    jump = abs(b1 - a1) if on_right else abs(b0 - a0)
                    if max_jump is None or jump <= max_jump:
                        match = j
                    break
            if match is None:
                done.append(path)
                continue
            used.add(match)
            b0, b1 = row[match]
            # Continue the zig-zag from where the previous segment ended.
            if on_right:
                path += [(b1, y), (b0, y)]
            else:
                path += [(b0, y), (b1, y)]
            new_open.append((path, (b0, b1), not on_right))
        for j, (b0, b1) in enumerate(row):
            if j not in used:
                new_open.append(([(b0, y), (b1, y)], (b0, b1), True))
        open_paths = new_open
    done.extend(p for p, _, _ in open_paths)
    return [np.array(p) for p in done if len(p) >= 2]
