"""Raster image loading."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

from rmink.ingest import RasterSource


def _open(path: Path) -> Image.Image:
    if path.suffix.lower() == ".heic":
        try:
            from pillow_heif import register_heif_opener
        except ImportError as e:
            raise RuntimeError("HEIC input needs the extra: pip install 'rmink[heic]'") from e
        register_heif_opener()
    return Image.open(path)


def to_rgb_array(img: Image.Image) -> np.ndarray:
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img)
    return np.asarray(img.convert("RGB"), dtype=np.uint8).copy()


def load_image(path: Path) -> RasterSource:
    with _open(path) as img:
        dpi = img.info.get("dpi", (None,))[0]
        arr = to_rgb_array(img)
    return RasterSource(path.name, arr, dpi=float(dpi) if dpi else None)
