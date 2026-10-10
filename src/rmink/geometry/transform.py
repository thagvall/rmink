"""Placing source content on a device page."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from rmink.devices import DeviceProfile


class Fit(StrEnum):
    page = "page"  # scale to fit the whole page
    width = "width"  # scale to page width; tall content extends the page downwards
    none = "none"  # physical size (PDF points / image DPI)


@dataclass(frozen=True)
class Placement:
    scale: float  # device px per source unit
    offset_x: float
    offset_y: float
    page_height: int

    def apply(self, pts: np.ndarray) -> np.ndarray:
        out = np.asarray(pts, dtype=np.float64) * self.scale
        out[:, 0] += self.offset_x
        out[:, 1] += self.offset_y
        return out


def place(
    src_w: float,
    src_h: float,
    device: DeviceProfile,
    fit: Fit = Fit.page,
    margin_mm: float = 5.0,
    physical_px_per_unit: float | None = None,
) -> Placement:
    """Compute how a ``src_w`` x ``src_h`` source maps onto the device page.

    ``physical_px_per_unit`` is the true-size scale used by ``Fit.none`` (e.g.
    ``dpi / 72`` for PDF points).
    """
    m = margin_mm * device.px_per_mm
    avail_w = device.width - 2 * m
    avail_h = device.height - 2 * m
    if fit == Fit.page:
        scale = min(avail_w / src_w, avail_h / src_h)
    elif fit == Fit.width:
        scale = avail_w / src_w
    else:
        scale = physical_px_per_unit or 1.0

    w, h = src_w * scale, src_h * scale
    page_h = max(device.height, int(np.ceil(h + 2 * m)))
    off_x = (device.width - w) / 2
    off_y = (page_h - h) / 2 if fit == Fit.page else m
    return Placement(scale, off_x, off_y, page_h)
