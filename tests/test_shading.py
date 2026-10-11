import uuid

import numpy as np
import pytest
from PIL import Image
from rmscene.scene_items import Pen

from rmink import api
from rmink.devices import get_device
from rmink.extract.shade import MAX_SHADE_STROKES, shade
from rmink.extract.tone import tone_map
from rmink.model import Page, Stroke
from rmink.options import ConvertOptions, Shading
from rmink.render.preview import read_lines
from rmink.writer.rm_v6 import write_page


def _ramp(w=600, h=200) -> np.ndarray:
    """Left half a white margin, right half a ramp from light grey to black."""
    img = np.full((h, w), 255.0)
    img[:, w // 2 :] = np.linspace(230, 0, w - w // 2)[None, :]
    return np.repeat(img[..., None], 3, axis=2).astype(np.uint8)


def _ink_per_column_band(paths, width, bands=3):
    """Points (dots) or line length per vertical band of the ramp."""
    edges = np.linspace(width / 2, width, bands + 1)
    amount = np.zeros(bands)
    for p in paths:
        pts = p.points
        seg = np.hypot(*np.diff(pts, axis=0).T) if len(pts) > 1 else np.zeros(1)
        mids = (pts[:-1] + pts[1:]) / 2 if len(pts) > 1 else pts
        for m, length in zip(mids, seg, strict=True):
            b = np.searchsorted(edges, m[0]) - 1
            if 0 <= b < bands:
                amount[b] += max(length, 1.0)
    return amount


def test_tone_map_follows_darkness():
    tone = tone_map(_ramp())
    row = tone[100]
    assert row[:290].max() == 0  # paper stays empty
    ramp = row[310:]
    assert np.all(np.diff(ramp) >= -1e-9) and ramp[-1] > 0.95


# Halftone keeps the dot count and grows the dots instead; see below.
@pytest.mark.parametrize("style", [Shading.stipple, Shading.hatch, Shading.crosshatch])
def test_shading_gets_denser_with_tone(style):
    tone = tone_map(_ramp())
    result = shade(tone, style, to_dev=1.0, pen_width=2.0)
    assert result.paths
    light, mid, dark = _ink_per_column_band(result.paths, tone.shape[1])
    assert light < mid < dark
    # Nothing on the white margin.
    assert all(p.points[:, 0].min() > tone.shape[1] / 2 - 10 for p in result.paths)


def test_halftone_dots_grow_with_tone():
    tone = tone_map(_ramp())
    paths = shade(tone, Shading.halftone, 1.0, 2.0).paths
    xs = np.array([p.points[:, 0].mean() for p in paths])
    ws = np.array([p.width for p in paths])
    assert ws[xs > 520].mean() > 1.5 * ws[(xs > 320) & (xs < 400)].mean()


def test_pencil_pressure_follows_tone():
    tone = tone_map(_ramp())
    result = shade(tone, Shading.pencil, 1.0, 2.0)
    assert result.pen == Pen.PENCIL_2
    pts = np.vstack([p.points for p in result.paths])
    pressure = np.concatenate([p.pressures for p in result.paths])
    assert pressure[pts[:, 0] > 540].mean() > pressure[pts[:, 0] < 380].mean() + 60


def test_shading_respects_budget():
    tone = np.ones((800, 800))
    for style in (Shading.stipple, Shading.halftone, Shading.hatch, Shading.pencil):
        paths = shade(tone, style, 1.0, 2.0, density=3.0, budget=5000).paths
        assert len(paths) <= MAX_SHADE_STROKES
        assert sum(len(p.points) for p in paths) <= 5000 * 1.1, style


def test_pressure_survives_round_trip():
    device = get_device("rm2")
    stroke = Stroke([[10, 10], [20, 20], [30, 30]], pen=Pen.PENCIL_2, pressures=[40, 120, 250])
    lines = read_lines(
        write_page(Page(device.width, device.height, [stroke]), device, uuid.uuid4())
    )
    assert [p.pressure for p in lines[0].points] == [40, 120, 250]


def test_convert_with_shading(tmp_path):
    src = tmp_path / "ramp.png"
    Image.fromarray(_ramp()).save(src)
    plain = api.render([src], ConvertOptions())
    shaded = api.render([src], ConvertOptions(shading="stipple"))
    assert len(shaded.document.pages[0].strokes) > len(plain.document.pages[0].strokes) + 100


def test_style_previews(tmp_path, examples):
    src = tmp_path / "ramp.png"
    Image.fromarray(_ramp()).save(src)
    previews = api.style_previews(src, ConvertOptions())
    assert [p.style for p in previews] == list(Shading)
    assert all(p.image.size[0] == get_device("rm2").width for p in previews)
    assert api.style_previews(examples["svg"], ConvertOptions()) == []
