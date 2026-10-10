import numpy as np

from rmink.geometry.hatch import hatch_mask, hatch_polygons
from rmink.geometry.order import chain_polylines
from rmink.geometry.simplify import chaikin, rdp
from rmink.package.rmdoc import page_indices


def test_rdp_removes_collinear_points():
    pts = np.array([[0, 0], [1, 0.01], [2, 0], [3, 0], [3, 3]], dtype=float)
    out = rdp(pts, 0.1)
    assert out.tolist() == [[0, 0], [3, 0], [3, 3]]


def test_chaikin_keeps_open_endpoints():
    pts = np.array([[0, 0], [10, 0], [10, 10]], dtype=float)
    out = chaikin(pts, iterations=2)
    assert np.allclose(out[0], pts[0]) and np.allclose(out[-1], pts[-1])
    assert len(out) > len(pts)


def test_page_indices_are_sorted_and_unique():
    for n in (1, 26, 27, 650, 651, 2000):
        idx = page_indices(n)
        assert len(idx) == n
        assert idx == sorted(idx)
        assert len(set(idx)) == n
    assert page_indices(3) == ["ba", "bb", "bc"]


def test_hatch_square_covers_area():
    square = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], dtype=float)
    paths = hatch_polygons([square], spacing=1.0)
    assert len(paths) == 1  # zig-zag joined into a single stroke
    ys = np.unique(paths[0][:, 1])
    assert len(ys) == 10


def test_hatch_polygon_with_hole_has_two_spans_per_row():
    outer = np.array([[0, 0], [30, 0], [30, 30], [0, 30]], dtype=float)
    hole = np.array([[10, 10], [20, 10], [20, 20], [10, 20]], dtype=float)
    paths = hatch_polygons([outer, hole], spacing=2.0)
    for p in paths:
        for (x0, y0), (x1, y1) in zip(p[:-1], p[1:], strict=True):
            if y0 == y1 and 10 < y0 < 20:
                lo, hi = sorted((x0, x1))
                assert hi <= 10 + 1e-9 or lo >= 20 - 1e-9


def test_hatch_mask_matches_rows():
    mask = np.zeros((20, 20), bool)
    mask[5:15, 5:15] = True
    paths = hatch_mask(mask, 2)
    assert paths and all(p[:, 0].min() >= 5 and p[:, 0].max() <= 14 for p in paths)


def test_chain_joins_collinear_but_not_perpendicular():
    a = np.array([[0, 0], [10, 0]], float)
    b = np.array([[11, 0], [20, 0]], float)
    c = np.array([[10.5, 1], [10.5, 30]], float)
    out = chain_polylines([a, b, c], gap=2)
    lengths = sorted(len(p) for p in out)
    assert len(out) == 2 and lengths == [2, 4]
