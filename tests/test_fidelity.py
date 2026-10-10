"""Compare the source ink with a rendering of the *parsed* output."""

import numpy as np
import pytest
from PIL import Image
from scipy.ndimage import binary_dilation

from rmink.api import render
from rmink.extract.raster import binarize
from rmink.geometry.transform import place
from rmink.ingest.pdf import render_page
from rmink.options import ConvertOptions


def _ink(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L")) < 160


def _source_mask(rgb: np.ndarray, device, opts) -> np.ndarray:
    """Binarise the source and place it on the device page like the converter."""
    h, w = rgb.shape[:2]
    pl = place(w, h, device, opts.fit, opts.margin_mm)
    size = (round(w * pl.scale), round(h * pl.scale))
    small = np.asarray(Image.fromarray(rgb).resize(size, Image.Resampling.LANCZOS))
    mask = np.zeros((pl.page_height, device.width), bool)
    x, y = round(pl.offset_x), round(pl.offset_y)
    m = binarize(small)
    mask[y : y + m.shape[0], x : x + m.shape[1]] = m
    return mask


def _scores(src: np.ndarray, out: np.ndarray, tol: int = 3) -> tuple[float, float]:
    """(precision, recall) of ink pixels within ``tol`` px."""
    st = np.ones((3, 3), bool)
    src_d = binary_dilation(src, st, iterations=tol)
    out_d = binary_dilation(out, st, iterations=tol)
    precision = (out & src_d).sum() / max(out.sum(), 1)
    recall = (src & out_d).sum() / max(src.sum(), 1)
    return precision, recall


@pytest.mark.parametrize("device_key", ["rm2", "pro"])
def test_handwriting_photo_fidelity(examples, device_key):
    opts = ConvertOptions(device=device_key)
    rendered = render([examples["photo"]], opts)
    out = _ink(rendered.images[0])
    src = _source_mask(
        np.asarray(Image.open(examples["photo"]).convert("RGB")), rendered.device, opts
    )
    precision, recall = _scores(src, out)
    assert precision > 0.95, precision
    assert recall > 0.85, recall
    assert len(rendered.document.pages[0].strokes) < 30


def test_vector_pdf_fidelity(examples):
    import pymupdf

    opts = ConvertOptions(device="rm2", pages="1")
    rendered = render([examples["pdf"]], opts)
    out = _ink(rendered.images[0])
    with pymupdf.open(examples["pdf"]) as doc:
        rgb = render_page(doc[0], dpi=200)
    src = _source_mask(rgb, rendered.device, opts)
    precision, recall = _scores(src, out)
    assert precision > 0.9, precision
    assert recall > 0.9, recall
