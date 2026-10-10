"""PDF pages as vector or raster sources."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pymupdf

from rmink.ingest import RasterSource, Source, parse_page_ranges
from rmink.ingest.svg import parse_svg_text

# Pages whose embedded images cover more than this share are traced as raster.
_RASTER_AREA_SHARE = 0.3
_RASTER_DPI = 300


def _image_area_share(page: pymupdf.Page) -> float:
    page_area = abs(page.rect)
    if page_area == 0:
        return 0.0
    covered = sum(abs(pymupdf.Rect(info["bbox"]) & page.rect) for info in page.get_image_info())
    return min(covered / page_area, 1.0)


def _has_vectors(page: pymupdf.Page) -> bool:
    return bool(page.get_text("text").strip()) or bool(page.get_drawings())


def render_page(page: pymupdf.Page, dpi: int = _RASTER_DPI) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).copy()


def load_pdf(path: Path, mode: str, pages: str | None = None) -> list[Source]:
    sources: list[Source] = []
    with pymupdf.open(path) as doc:
        for i in parse_page_ranges(pages, doc.page_count):
            page = doc[i]
            label = f"{path.name} p{i + 1}"
            share = _image_area_share(page)
            if mode == "vector":
                use_raster = False
            elif mode in ("centerline", "outline"):
                use_raster = True
            else:
                use_raster = share > _RASTER_AREA_SHARE or not _has_vectors(page)

            if use_raster:
                sources.append(RasterSource(label, render_page(page), dpi=_RASTER_DPI))
                continue

            svg = page.get_svg_image(text_as_path=True)
            src = parse_svg_text(svg, label, px_per_unit_at_dpi=1 / 72)
            if share > 0.02:
                src.warnings.append(
                    f"{label}: embedded images ({share:.0%} of page) are skipped in vector "
                    "mode; use --mode centerline to trace them."
                )
            sources.append(src)
    return sources
