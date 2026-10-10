import numpy as np
from skimage.draw import disk, line

from rmink.extract.centerline import centerline_strokes


def _thick_line(mask, r0, c0, r1, c1, radius=2):
    rr, cc = line(r0, c0, r1, c1)
    for r, c in zip(rr, cc, strict=True):
        dr, dc = disk((r, c), radius, shape=mask.shape)
        mask[dr, dc] = True


def test_straight_line_is_one_stroke_with_width():
    mask = np.zeros((100, 200), bool)
    _thick_line(mask, 50, 20, 50, 180, radius=3)
    strokes = centerline_strokes(mask, simplify_px=0.5)
    assert len(strokes) == 1
    pts, widths = strokes[0]
    assert abs(pts[:, 1].mean() - 50) < 1.0
    assert pts[:, 0].max() - pts[:, 0].min() > 150
    assert 4 <= np.median(widths) <= 9


def test_t_junction_gives_at_most_three_strokes():
    mask = np.zeros((200, 200), bool)
    _thick_line(mask, 40, 20, 40, 180)
    _thick_line(mask, 40, 100, 180, 100)
    strokes = centerline_strokes(mask, simplify_px=0.5)
    assert 1 <= len(strokes) <= 3


def test_ring_is_one_closed_stroke():
    mask = np.zeros((200, 200), bool)
    yy, xx = np.mgrid[0:200, 0:200]
    r = np.hypot(yy - 100, xx - 100)
    mask[(r > 60) & (r < 66)] = True
    strokes = centerline_strokes(mask, simplify_px=0.5)
    assert len(strokes) == 1
    pts, _ = strokes[0]
    assert np.hypot(*(pts[0] - pts[-1])) < 3


def test_empty_mask():
    assert centerline_strokes(np.zeros((10, 10), bool), 0.5) == []
