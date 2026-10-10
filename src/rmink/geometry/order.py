"""Stroke ordering, endpoint chaining and point budgets."""

from __future__ import annotations

import numpy as np
from scipy.spatial import cKDTree

from rmink.geometry.simplify import rdp_mask
from rmink.model import Stroke


def reading_order(strokes: list[Stroke], band: float = 60.0) -> list[Stroke]:
    """Sort strokes top-to-bottom in horizontal bands, left-to-right within a
    band, so lasso selection and undo history feel natural."""

    def key(s: Stroke):
        mn = s.points.min(axis=0)
        return (int(mn[1] // band), float(mn[0]))

    return sorted(strokes, key=key)


def chain_polylines(
    paths: list[np.ndarray], gap: float, max_turn_deg: float = 50.0
) -> list[np.ndarray]:
    """Join polylines whose endpoints are within ``gap`` and whose directions
    continue smoothly (turn below ``max_turn_deg``).

    Candidate endpoint pairs come from a KD-tree and are accepted greedily,
    best (closest, straightest) first, so this stays O(n log n).
    """
    paths = [np.asarray(p, dtype=np.float64) for p in paths if len(p) >= 1]
    n = len(paths)
    if n < 2:
        return paths
    cos_lim = np.cos(np.radians(max_turn_deg))

    # Endpoint e = 2*i (start of path i) or 2*i+1 (end of path i).
    pts = np.empty((2 * n, 2))
    dirs = np.zeros((2 * n, 2))  # outward tangent at each endpoint
    for i, p in enumerate(paths):
        pts[2 * i], pts[2 * i + 1] = p[0], p[-1]
        k = min(len(p) - 1, 4)
        if k:
            for e, v in ((2 * i, p[0] - p[k]), (2 * i + 1, p[-1] - p[-1 - k])):
                norm = np.hypot(*v)
                if norm > 0:
                    dirs[e] = v / norm

    candidates = []
    for a, b in cKDTree(pts).query_pairs(gap):
        if a // 2 == b // 2:
            continue
        # Outward tangents of two joinable ends point towards each other.
        cos = -float(np.dot(dirs[a], dirs[b]))
        if cos < cos_lim:
            continue
        dist = float(np.hypot(*(pts[a] - pts[b])))
        candidates.append((dist / gap + (1 - cos), a, b))
    candidates.sort()

    link = np.full(2 * n, -1)
    # Union-find over paths prevents closing a chain into a loop.
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, a, b in candidates:
        if link[a] >= 0 or link[b] >= 0:
            continue
        ra, rb = find(a // 2), find(b // 2)
        if ra == rb:
            continue
        link[a], link[b] = b, a
        parent[ra] = rb

    out = []
    visited = np.zeros(n, dtype=bool)
    for i in range(n):
        if visited[i]:
            continue
        # Walk to one end of the chain containing path i.
        e = 2 * i
        seen = {i}
        while link[e] >= 0 and (link[e] // 2) not in seen:
            j = link[e] // 2
            seen.add(j)
            e = link[e] ^ 1  # leave path j through its other end
        # e is a free endpoint; traverse from there.
        chain = []
        cur = e
        while True:
            j = cur // 2
            visited[j] = True
            p = paths[j] if cur % 2 == 0 else paths[j][::-1]
            if chain and np.allclose(chain[-1][-1], p[0]):
                p = p[1:]
            chain.append(p)
            nxt = link[cur ^ 1]
            if nxt < 0 or visited[nxt // 2]:
                break
            cur = nxt
        out.append(np.vstack(chain))
    return out


def enforce_budget(strokes: list[Stroke], max_points: int, start_tol: float) -> list[Stroke]:
    """Re-simplify with growing tolerance until the page fits ``max_points``."""
    tol = max(start_tol, 0.25)
    total = sum(len(s) for s in strokes)
    while total > max_points and tol < 50:
        tol *= 1.6
        for s in strokes:
            if len(s) > 2:
                keep = rdp_mask(s.points.astype(np.float64), tol)
                s.points = s.points[keep]
                if s.widths is not None:
                    s.widths = s.widths[keep]
        total = sum(len(s) for s in strokes)
    return strokes
