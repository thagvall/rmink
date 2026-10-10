"""Centerline tracing: binary ink mask -> single-line strokes.

The mask is skeletonised, the skeleton is split into a graph at junctions and
endpoints, short spurs are pruned, and edges that continue smoothly through a
junction are chained back together. Stroke width comes from the distance
transform of the original mask.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import convolve, distance_transform_edt
from skimage.morphology import skeletonize

from rmink.geometry.order import chain_polylines
from rmink.geometry.simplify import chaikin, rdp_mask, resample_values

_NEIGHBOUR_KERNEL = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8)


def trace_skeleton(skel: np.ndarray) -> list[np.ndarray]:
    """Split a one-pixel-wide skeleton into pixel paths of (row, col).

    Nodes are pixels whose neighbour count is not 2. Every path runs from a node
    to a node through degree-2 pixels; pure cycles are returned as closed paths.
    Isolated pixels become single-point paths.
    """
    pad = np.pad(skel.astype(bool), 1)
    h, w = pad.shape
    deg = convolve(pad.astype(np.uint8), _NEIGHBOUR_KERNEL, mode="constant") * pad
    flat = pad.ravel()
    flat_deg = deg.ravel()
    offsets = np.array([-w - 1, -w, -w + 1, -1, 1, w - 1, w, w + 1])

    def neighbours(i: int) -> list[int]:
        return [j for j in (i + offsets).tolist() if flat[j]]

    visited = np.zeros(flat.size, dtype=bool)
    node = flat & (flat_deg != 2)
    paths: list[list[int]] = []

    for start in np.flatnonzero(node).tolist():
        if flat_deg[start] == 0:
            paths.append([start])
            continue
        for nb in neighbours(start):
            if node[nb]:
                # Adjacent node pixels (junction clusters) are linked directly,
                # once per pair.
                if nb > start:
                    paths.append([start, nb])
                continue
            if visited[nb]:
                continue
            path = [start, nb]
            visited[nb] = True
            prev, cur = start, nb
            while True:
                nxt = [j for j in neighbours(cur) if j != prev and (node[j] or not visited[j])]
                if not nxt:
                    break
                # Prefer stepping onto a node if one is adjacent.
                nodes_next = [j for j in nxt if node[j]]
                j = nodes_next[0] if nodes_next else nxt[0]
                path.append(j)
                if node[j]:
                    break
                visited[j] = True
                prev, cur = cur, j
            paths.append(path)

    # Remaining unvisited degree-2 pixels form isolated cycles.
    for start in np.flatnonzero(flat & ~node & ~visited).tolist():
        if visited[start]:
            continue
        path = [start]
        visited[start] = True
        prev, cur = -1, start
        while True:
            nxt = [j for j in neighbours(cur) if j != prev and not visited[j]]
            if not nxt:
                break
            prev, cur = cur, nxt[0]
            visited[cur] = True
            path.append(cur)
        path.append(start)
        paths.append(path)

    out = []
    for p in paths:
        idx = np.array(p)
        rows, cols = np.divmod(idx, w)
        out.append(np.stack([rows - 1, cols - 1], axis=1))
    return out


def _prune_spurs(paths: list[np.ndarray], degree: dict, min_len: float) -> list[np.ndarray]:
    """Drop short branches that end in a free endpoint next to a junction."""
    kept = []
    for p in paths:
        if len(p) < 2:
            kept.append(p)
            continue
        a, b = tuple(p[0]), tuple(p[-1])
        da, db = degree.get(a, 2), degree.get(b, 2)
        is_spur = (da == 1 and db >= 3) or (db == 1 and da >= 3)
        length = float(np.sum(np.hypot(*np.diff(p, axis=0).T)))
        if is_spur and length < min_len:
            continue
        kept.append(p)
    return kept


def centerline_strokes(
    mask: np.ndarray,
    simplify_px: float,
    min_length_px: float = 2.0,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Return (points (N,2) as x,y in mask px, widths (N,) in mask px) per stroke."""
    if not mask.any():
        return []
    dist = distance_transform_edt(mask)
    skel = skeletonize(mask)
    paths = trace_skeleton(skel)

    pad = np.pad(skel, 1)
    deg_img = convolve(pad.astype(np.uint8), _NEIGHBOUR_KERNEL, mode="constant")[1:-1, 1:-1]
    degree = {}
    for p in paths:
        for q in (p[0], p[-1]):
            degree[tuple(q)] = int(deg_img[q[0], q[1]])

    median_half_width = float(np.median(dist[skel])) if skel.any() else 1.0
    paths = _prune_spurs(paths, degree, min_len=max(3.0, 2.5 * median_half_width))

    # Chain in (x, y) space.
    xy_paths = [p[:, ::-1].astype(np.float64) for p in paths]
    chained = chain_polylines(xy_paths, gap=2.0, max_turn_deg=55)

    results = []
    for p in chained:
        if len(p) == 1:
            r = dist[int(p[0, 1]), int(p[0, 0])]
            if r >= 1.5:  # a dot (e.g. on an "i"), not noise
                results.append((p, np.array([2 * r])))
            continue
        length = float(np.sum(np.hypot(*np.diff(p, axis=0).T)))
        if length < min_length_px:
            continue
        rows = np.clip(p[:, 1].astype(int), 0, mask.shape[0] - 1)
        cols = np.clip(p[:, 0].astype(int), 0, mask.shape[1] - 1)
        widths = 2 * np.maximum(dist[rows, cols], 0.5)
        closed = np.allclose(p[0], p[-1]) and len(p) > 3
        smooth = chaikin(p, iterations=2, closed=closed)
        widths = resample_values(p, widths, smooth)
        keep = rdp_mask(smooth, simplify_px)
        results.append((smooth[keep], widths[keep]))
    return results
