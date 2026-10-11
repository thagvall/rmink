"""Grey tones of a raster source, for shading."""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage

from rmink.extract.raster import _gray, _paper_background
from rmink.geometry.transform import Placement
from rmink.ingest import RasterSource

# The tone map is sampled at most this many pixels per device pixel.
_MAX_FACTOR = 4.0
# Tones below this count as paper.
_PAPER = 0.06
# Paper under uneven light stays within this brightness ratio across a photo.
_PAPER_SPREAD = 0.55


def tone_map(rgb: np.ndarray, contrast: float = 1.0) -> np.ndarray:
    """Darkness 0..1 (1 = black) per pixel, relative to the paper colour.

    Photos are divided by an estimate of the paper brightness first, so
    shadows and vignetting across the sheet do not turn into shading.
    """
    gray = _gray(rgb.astype(np.float64))
    if gray.std() < 1:
        return np.zeros(gray.shape)
    clean = np.mean(gray >= 245) > 0.4
    if clean:
        norm = gray / 255.0
    else:
        bg = _paper_background(gray)
        lo, hi = np.percentile(bg, [2, 98])
        if lo / max(hi, 1) > _PAPER_SPREAD:
            # A photographed sheet: the estimate is the paper under uneven light.
            norm = gray / np.maximum(bg, 1)
        else:
            # A scene or portrait: the "background" is the subject itself, so
            # compare against the brightest areas instead.
            norm = gray / max(float(np.percentile(gray, 99)), 1)
    tone = 1.0 - np.clip(norm, 0, 1)
    top = max(float(np.percentile(tone, 99.5)), 0.25)
    tone = np.clip((tone - _PAPER) / (top - _PAPER), 0, 1)
    if contrast != 1.0:
        tone = np.clip(0.5 + (tone - 0.5) * contrast, 0, 1)
    return tone


def device_tone(src: RasterSource, placement: Placement, contrast: float = 1.0):
    """Tone map resampled to about one pixel per device pixel.

    Returns ``(tone, factor)`` where ``factor`` is tone pixels per source pixel,
    so ``placement.apply(points / factor)`` maps tone pixels onto the page.
    """
    rgb = src.image
    factor = min(placement.scale, _MAX_FACTOR)
    h, w = rgb.shape[:2]
    size = (max(1, round(w * factor)), max(1, round(h * factor)))
    if size != (w, h):
        resample = Image.Resampling.BOX if factor < 1 else Image.Resampling.BICUBIC
        rgb = np.asarray(Image.fromarray(rgb).resize(size, resample))
    tone = tone_map(rgb, contrast)
    # Photo grain would otherwise turn into noise in every style.
    tone = ndimage.gaussian_filter(tone, 0.8)
    return tone, factor
