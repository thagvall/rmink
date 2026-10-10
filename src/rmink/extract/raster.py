"""Raster sources -> strokes: binarise, separate colours, classify, trace."""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.cluster.vq import kmeans2
from skimage.filters import threshold_otsu, threshold_sauvola
from skimage.measure import find_contours
from skimage.morphology import remove_small_holes, remove_small_objects, skeletonize

from rmink.color.palette import nearest_indices, to_lab
from rmink.devices import DeviceProfile, PaletteEntry
from rmink.extract.centerline import centerline_strokes
from rmink.geometry.hatch import hatch_mask
from rmink.geometry.simplify import rdp
from rmink.geometry.transform import Placement
from rmink.ingest import RasterSource
from rmink.model import Stroke
from rmink.options import ConvertOptions, FillMode, Mode

# Work at this many mask pixels per device pixel: enough to keep thin pen lines
# connected, without wasting time on 12 MP photos.
_OVERSAMPLE = 2.0
_MAX_UPSAMPLE = 4.0
_MIN_DOMINANT_SHARE = 0.7


def _gray(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def _paper_background(gray: np.ndarray) -> np.ndarray:
    """Estimate the paper brightness everywhere by removing ink with a large
    grey-level closing on a downscaled copy (photos have shadows/vignetting)."""
    h, w = gray.shape
    f = min(1.0, 400 / max(h, w))
    small = np.asarray(
        Image.fromarray(gray.astype(np.float32)).resize(
            (max(1, round(w * f)), max(1, round(h * f))), Image.Resampling.BILINEAR
        )
    )
    size = max(5, int(max(small.shape) / 25)) | 1
    bg = ndimage.grey_closing(small, size=(size, size))
    bg = ndimage.uniform_filter(bg, size=size)
    return np.asarray(Image.fromarray(bg).resize((w, h), Image.Resampling.BILINEAR))


def binarize(rgb: np.ndarray, threshold: str = "auto") -> np.ndarray:
    gray = _gray(rgb.astype(np.float64))
    if threshold != "auto":
        return gray < float(threshold)
    if gray.std() < 1:
        return np.zeros(gray.shape, dtype=bool)
    # Digital renders and clean scans have a pure-white plateau; photos don't.
    clean = np.mean(gray >= 245) > 0.4
    bg = None if clean else _paper_background(gray)
    if clean or bg.std() < 4:
        # Evenly lit: a global threshold keeps large solid fills that
        # background estimation would swallow.
        mask = gray < threshold_otsu(gray)
    else:
        norm = np.clip(gray / np.maximum(bg, 1), 0, 1.2)
        t = threshold_otsu(norm)
        local = threshold_sauvola(norm, window_size=max(15, (min(gray.shape) // 40) | 1), k=0.2)
        # Otsu on the normalised image separates ink from paper; Sauvola trims
        # the halo around strokes. Keep only clearly darker-than-paper pixels.
        mask = (norm < min(t, 0.85)) & (norm < local)
    min_obj = max(4, int(gray.size * 2e-6))
    mask = remove_small_objects(mask, max_size=min_obj)
    mask = remove_small_holes(mask, max_size=min_obj)
    return mask


def color_layers(
    rgb: np.ndarray, mask: np.ndarray, palette: tuple[PaletteEntry, ...], clusters: int | None
) -> list[tuple[PaletteEntry, np.ndarray]]:
    """Split ``mask`` into one mask per palette colour."""
    if len(palette) == 1 or not mask.any():
        return [(palette[0], mask)]
    ink = rgb[mask].astype(np.float64)
    k = clusters or 6
    sample = ink[:: max(1, len(ink) // 20000)]
    lab_sample = to_lab(sample)
    k = max(1, min(k, len(np.unique(sample, axis=0))))
    centers, _ = kmeans2(lab_sample, k, seed=0, minit="++")
    # Each pixel -> nearest cluster -> nearest palette colour.
    lab_ink = to_lab(ink)
    pixel_cluster = np.argmin(((lab_ink[:, None, :] - centers[None]) ** 2).sum(axis=2), axis=1)
    centers_rgb = np.array(
        [
            ink[pixel_cluster == c].mean(axis=0) if (pixel_cluster == c).any() else [0, 0, 0]
            for c in range(k)
        ]
    )
    cluster_palette = nearest_indices(centers_rgb, palette)
    labels = np.full(mask.shape, -1, dtype=int)
    labels[mask] = cluster_palette[pixel_cluster]

    # Anti-aliased edges pick up stray colours; give each connected component
    # its dominant colour when one clearly dominates.
    comp, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n:
        flat_comp = comp[mask]
        flat_lab = labels[mask]
        counts = np.zeros((n + 1, len(palette)), dtype=np.int64)
        np.add.at(counts, (flat_comp, flat_lab), 1)
        dominant = counts.argmax(axis=1)
        share = counts.max(axis=1) / np.maximum(counts.sum(axis=1), 1)
        override = share >= _MIN_DOMINANT_SHARE
        new = np.where(override[flat_comp], dominant[flat_comp], flat_lab)
        labels[mask] = new

    layers = []
    for idx in np.unique(labels[mask]):
        layers.append((palette[int(idx)], labels == idx))
    return layers


def _outline_strokes(mask: np.ndarray, pen_w: float, fill: FillMode, tol: float):
    """Outlines (+ hatching) for thick ink, in mask pixel coordinates."""
    paths = []
    for c in find_contours(np.pad(mask, 1).astype(np.uint8), 0.5):
        pts = c[:, ::-1] - 1  # (row, col) -> (x, y)
        pts = rdp(pts, tol)
        if len(pts) >= 2:
            paths.append(pts)
    if fill == FillMode.hatch:
        inner = ndimage.binary_erosion(mask, iterations=max(1, int(pen_w / 2)))
        paths.extend(rdp(p, tol) for p in hatch_mask(inner, max(1.0, pen_w * 0.9)))
    return paths


def extract_raster(
    src: RasterSource,
    placement: Placement,
    device: DeviceProfile,
    palette: tuple[PaletteEntry, ...],
    clusters: int | None,
    opts: ConvertOptions,
) -> list[Stroke]:
    rgb = src.image
    # Resample so one mask pixel is 1/_OVERSAMPLE device pixel.
    factor = min(placement.scale * _OVERSAMPLE, _MAX_UPSAMPLE)
    if abs(factor - 1) > 0.05:
        h, w = rgb.shape[:2]
        size = (max(1, round(w * factor)), max(1, round(h * factor)))
        rgb = np.asarray(Image.fromarray(rgb).resize(size, Image.Resampling.LANCZOS))
    to_device = placement.scale / factor  # device px per mask px

    mask = binarize(rgb, opts.threshold)
    pen = opts.pen.pen
    tol_mask = opts.simplify / to_device
    pen_w_mask = opts.width / to_device
    strokes: list[Stroke] = []

    def emit(points: np.ndarray, widths: np.ndarray | None, width: float, entry: PaletteEntry):
        dev = placement.apply(points / factor)
        w_dev = None if widths is None else np.clip(widths * to_device, 1.0, 40.0)
        strokes.append(Stroke(dev, width=width, widths=w_dev, pen=pen, color=entry.color))

    for entry, layer in color_layers(rgb, mask, palette, clusters):
        if opts.mode == Mode.outline:
            thick, thin = layer, np.zeros_like(layer)
        elif opts.mode == Mode.centerline:
            thick, thin = np.zeros_like(layer), layer
        else:
            # Per connected component: wide blobs are outlined, lines are traced.
            # The median half-width along the skeleton ignores junction blobs.
            dist = ndimage.distance_transform_edt(layer)
            comp, n = ndimage.label(layer, structure=np.ones((3, 3)))
            if n:
                skel = skeletonize(layer)
                half = ndimage.median(dist, np.where(skel, comp, 0), index=np.arange(1, n + 1))
                limit = opts.thick_px / to_device / 2
                thick_ids = np.flatnonzero(np.nan_to_num(np.asarray(half)) > limit) + 1
                thick = np.isin(comp, thick_ids)
            else:
                thick = np.zeros_like(layer)
            thin = layer & ~thick

        for pts, widths in centerline_strokes(thin, tol_mask):
            emit(pts, widths, float(np.median(widths) * to_device), entry)
        if thick.any():
            for pts in _outline_strokes(thick, pen_w_mask, opts.fill, tol_mask):
                emit(pts, None, opts.width, entry)
    return strokes
