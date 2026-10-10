"""Mapping arbitrary colours to the device pen palette."""

from __future__ import annotations

import numpy as np
from skimage.color import rgb2lab

from rmink.devices import PaletteEntry

# Colours lighter than this (CIE L*) with little chroma count as background.
_WHITE_L = 92.0
_WHITE_CHROMA = 12.0


def to_lab(rgb: np.ndarray) -> np.ndarray:
    arr = np.asarray(rgb, dtype=np.float64).reshape(-1, 1, 3) / 255.0
    return rgb2lab(arr).reshape(-1, 3)


def is_background(rgb: tuple[int, int, int]) -> bool:
    L, a, b = to_lab(np.array(rgb))[0]
    return L > _WHITE_L and np.hypot(a, b) < _WHITE_CHROMA


def nearest(rgb: tuple[int, int, int], palette: tuple[PaletteEntry, ...]) -> PaletteEntry:
    return palette[int(nearest_indices(np.array([rgb]), palette)[0])]


def nearest_indices(rgbs: np.ndarray, palette: tuple[PaletteEntry, ...]) -> np.ndarray:
    lab = to_lab(rgbs)
    pal = to_lab(np.array([e.rgb for e in palette]))
    # Weight lightness less so dark saturated ink maps to its hue, not black.
    w = np.array([0.6, 1.0, 1.0])
    d = (((lab[:, None, :] - pal[None, :, :]) * w) ** 2).sum(axis=2)
    return np.argmin(d, axis=1)
