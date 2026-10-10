"""Polyline simplification and smoothing."""

from __future__ import annotations

import numpy as np


def rdp_mask(points: np.ndarray, tolerance: float) -> np.ndarray:
    """Ramer-Douglas-Peucker: boolean mask of the points to keep."""
    n = len(points)
    keep = np.zeros(n, dtype=bool)
    if n <= 2 or tolerance <= 0:
        keep[:] = True
        return keep
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end - start < 2:
            continue
        a, b = points[start], points[end]
        seg = points[start + 1 : end]
        ab = b - a
        norm = float(np.hypot(*ab))
        if norm < 1e-9:
            dists = np.hypot(*(seg - a).T)
        else:
            dists = np.abs(ab[0] * (seg[:, 1] - a[1]) - ab[1] * (seg[:, 0] - a[0])) / norm
        i = int(np.argmax(dists))
        if dists[i] > tolerance:
            mid = start + 1 + i
            keep[mid] = True
            stack.append((start, mid))
            stack.append((mid, end))
    return keep


def rdp(points: np.ndarray, tolerance: float) -> np.ndarray:
    return points[rdp_mask(points, tolerance)]


def chaikin(points: np.ndarray, iterations: int = 1, closed: bool = False) -> np.ndarray:
    """Corner-cutting smoothing that keeps the endpoints of open polylines."""
    pts = np.asarray(points, dtype=np.float64)
    for _ in range(iterations):
        if len(pts) < 3:
            break
        p0 = pts if closed else pts[:-1]
        p1 = np.roll(pts, -1, axis=0) if closed else pts[1:]
        q = 0.75 * p0 + 0.25 * p1
        r = 0.25 * p0 + 0.75 * p1
        out = np.empty((len(q) * 2, 2))
        out[0::2] = q
        out[1::2] = r
        if not closed:
            out = np.vstack([pts[:1], out, pts[-1:]])
        else:
            out = np.vstack([out, out[:1]])
        pts = out
    return pts


def resample_values(src_points: np.ndarray, values: np.ndarray, dst_points: np.ndarray):
    """Carry per-point values (e.g. widths) over to a modified polyline by
    nearest-arclength lookup."""
    if len(src_points) < 2:
        return np.full(len(dst_points), values[0] if len(values) else 0.0)
    s_src = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(src_points, axis=0).T))])
    s_dst = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(dst_points, axis=0).T))])
    if s_dst[-1] > 0 and s_src[-1] > 0:
        s_dst = s_dst * (s_src[-1] / s_dst[-1])
    return np.interp(s_dst, s_src, values)
