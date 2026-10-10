"""Turn input files into per-page sources (vector shapes or raster images)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

RGB = tuple[int, int, int]


@dataclass
class VectorShape:
    subpaths: list[np.ndarray]  # each (N, 2), source units
    closed: list[bool]
    fill: RGB | None
    stroke: RGB | None
    stroke_width: float  # source units


@dataclass
class VectorSource:
    label: str
    width: float
    height: float
    shapes: list[VectorShape]
    px_per_unit_at_dpi: float = 1 / 72  # multiply by device DPI for true size
    warnings: list[str] = field(default_factory=list)


@dataclass
class RasterSource:
    label: str
    image: np.ndarray  # (H, W, 3) uint8 RGB
    dpi: float | None = None
    warnings: list[str] = field(default_factory=list)


Source = VectorSource | RasterSource

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif", ".heic"}


def parse_page_ranges(spec: str | None, count: int) -> list[int]:
    """'1-3,7' -> [0, 1, 2, 6] (clipped to the document)."""
    if not spec:
        return list(range(count))
    pages: list[int] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo = int(a) if a else 1
            hi = int(b) if b else count
            pages.extend(range(lo - 1, min(hi, count)))
        else:
            pages.append(int(part) - 1)
    return [p for p in pages if 0 <= p < count]


def load(path: Path, mode: str, pages: str | None = None) -> list[Source]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        from rmink.ingest.pdf import load_pdf

        return load_pdf(path, mode, pages)
    if suffix == ".svg":
        from rmink.ingest.svg import load_svg

        return [load_svg(path)]
    if suffix in IMAGE_SUFFIXES:
        from rmink.ingest.image import load_image

        return [load_image(path)]
    raise ValueError(f"Unsupported input type: {path.name}")
