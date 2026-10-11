"""Public entry point: inputs -> ``.rmdoc``. The CLI, MCP server and web UI are
thin wrappers around :func:`convert`."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

from PIL import Image

from rmink.devices import MONO_PALETTE, DeviceProfile, get_device
from rmink.extract.raster import extract_raster
from rmink.extract.shade import shade
from rmink.extract.tone import device_tone
from rmink.extract.vector import extract_vector
from rmink.geometry.order import enforce_budget, reading_order
from rmink.geometry.transform import Fit, Placement, place
from rmink.ingest import RasterSource, Source, VectorSource, load
from rmink.model import Document, Page, Stroke
from rmink.options import ConvertOptions, ConvertResult, FillMode, Mode, PageStats, Shading
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.render.preview import contact_sheet, render_rm, thumbnail_png
from rmink.writer.rm_v6 import write_page

log = logging.getLogger(__name__)


@dataclass
class Rendered:
    """A converted document before packaging."""

    document: Document
    labels: list[str]
    rm_pages: list[bytes]
    images: list[Image.Image]
    warnings: list[str]
    device: DeviceProfile
    uuids: UuidFactory
    author: UUID  # must match .content cPages.uuids[0].first


def _palette(device: DeviceProfile, colors: str):
    if colors == "mono":
        return MONO_PALETTE[:1], None
    clusters = int(colors) if colors.isdigit() else None
    return device.palette, clusters


def shade_strokes(
    src: RasterSource,
    placement: Placement,
    opts: ConvertOptions,
    budget: int,
    tone=None,
) -> list[Stroke]:
    """Strokes for the grey tones of ``src`` in ``opts.shading`` style.

    ``tone`` is the ``(tone, factor)`` pair from :func:`device_tone`, for
    callers that shade the same source in several styles.
    """
    if opts.shading == Shading.none:
        return []
    tone_px, factor = tone or device_tone(src, placement, opts.shade_contrast)
    to_dev = placement.scale / factor
    result = shade(tone_px, opts.shading, to_dev, opts.width, opts.shade_density, budget)
    pen = result.pen or opts.pen.pen
    return [
        Stroke(
            placement.apply(p.points / factor),
            width=p.width,
            widths=p.widths,
            pressures=p.pressures,
            pen=pen,
        )
        for p in result.paths
    ]


def _raster_placement(src: RasterSource, device: DeviceProfile, opts: ConvertOptions) -> Placement:
    h, w = src.image.shape[:2]
    true_size = device.dpi / src.dpi if src.dpi else 1.0
    return place(w, h, device, opts.fit, opts.margin_mm, physical_px_per_unit=true_size)


def _raster_lines(
    src: RasterSource, placement: Placement, device: DeviceProfile, opts: ConvertOptions
) -> list[Stroke]:
    palette, clusters = _palette(device, opts.colors)
    # Photographed black ink reads as grey; gray is only offered when it is
    # an exact source colour (vectors).
    raster_palette = tuple(e for e in palette if e.name != "gray") or palette
    if opts.shading != Shading.none and opts.fill == FillMode.hatch:
        # Shading draws the dark areas; even hatching would hide it.
        opts = opts.model_copy(update={"fill": FillMode.outline})
    return extract_raster(src, placement, device, raster_palette, clusters, opts)


def source_to_page(src: Source, device: DeviceProfile, opts: ConvertOptions) -> Page:
    palette, clusters = _palette(device, opts.colors)
    if isinstance(src, VectorSource):
        placement = place(
            src.width,
            src.height,
            device,
            opts.fit,
            opts.margin_mm,
            physical_px_per_unit=src.px_per_unit_at_dpi * device.dpi,
        )
        strokes = extract_vector(src, placement, device, palette, opts)
    else:
        placement = _raster_placement(src, device, opts)
        strokes = _raster_lines(src, placement, device, opts)
        budget = opts.max_points - sum(len(s) for s in strokes)
        strokes += shade_strokes(src, placement, opts, max(budget, 0))

    strokes = enforce_budget(reading_order(strokes), opts.max_points, opts.simplify)
    return Page(device.width, placement.page_height, strokes)


@dataclass
class StylePreview:
    style: Shading
    image: Image.Image
    strokes: int
    points: int


def style_previews(
    path: Path, opts: ConvertOptions, styles: list[Shading] | None = None
) -> list[StylePreview]:
    """The first page of ``path`` rendered once per shading style.

    Line extraction and the tone map run once; only the shading differs. Vector
    sources have no shading, so they give an empty list.
    """
    device = get_device(opts.device)
    src = next(iter(load(Path(path), opts.mode.value, opts.pages)), None)
    if not isinstance(src, RasterSource):
        return []
    styles = styles or list(Shading)
    placement = _raster_placement(src, device, opts)
    plain = _raster_lines(src, placement, device, opts.model_copy(update={"shading": Shading.none}))
    if opts.fill == FillMode.hatch:
        shaded = opts.model_copy(update={"shading": Shading.stipple})
        lines = _raster_lines(src, placement, device, shaded)
    else:
        lines = plain
    tone = device_tone(src, placement, opts.shade_contrast)
    author = UuidFactory(0)()
    out = []
    for style in styles:
        style_opts = opts.model_copy(update={"shading": style})
        base = plain if style == Shading.none else lines
        budget = opts.max_points - sum(len(s) for s in base)
        strokes = [replace(s, points=s.points.copy()) for s in base] + shade_strokes(
            src, placement, style_opts, max(budget, 0), tone
        )
        strokes = enforce_budget(reading_order(strokes), opts.max_points, opts.simplify)
        page = Page(device.width, placement.page_height, strokes)
        image = render_rm(write_page(page, device, author), device, page.height)
        out.append(StylePreview(style, image, len(page.strokes), page.point_count))
    return out


def render(inputs: list[Path], opts: ConvertOptions) -> Rendered:
    device = get_device(opts.device)
    if opts.mode == Mode.vector and any(p.suffix.lower() not in (".pdf", ".svg") for p in inputs):
        raise ValueError("--mode vector only works for PDF and SVG inputs")

    sources: list[Source] = []
    for path in inputs:
        if not path.is_file():
            raise FileNotFoundError(path)
        sources.extend(load(path, opts.mode.value, opts.pages))
    if not sources:
        raise ValueError("No pages to convert")

    warnings = [w for s in sources for w in s.warnings]
    if not device.verified:
        warnings.append(
            f"{device.name}: coordinate scale is not yet verified on hardware; "
            "print `rmink calibrate` and check the ruler."
        )

    uuids = UuidFactory(opts.seed)
    author = uuids()
    doc = Document(name=opts.name or inputs[0].stem)
    rm_pages, images, labels = [], [], []
    for src in sources:
        log.info("Converting %s", src.label)
        page = source_to_page(src, device, opts)
        if not page.strokes:
            warnings.append(f"{src.label}: no ink found")
        data = write_page(page, device, author)
        doc.pages.append(page)
        rm_pages.append(data)
        images.append(render_rm(data, device, page.height))
        labels.append(src.label)
        if isinstance(src, RasterSource) and opts.fit == Fit.none and not src.dpi:
            warnings.append(f"{src.label}: image has no DPI; assumed 1 px = 1 device px")
    return Rendered(doc, labels, rm_pages, images, warnings, device, uuids, author)


def convert(
    inputs: list[Path],
    output: Path | None = None,
    opts: ConvertOptions | None = None,
    preview: Path | None = None,
) -> ConvertResult:
    opts = opts or ConvertOptions()
    inputs = [Path(p) for p in inputs]
    rendered = render(inputs, opts)
    name = rendered.document.name
    output = Path(output) if output else inputs[0].with_name(f"{inputs[0].stem}.rmdoc")
    if output.suffix.lower() != ".rmdoc":
        output = output.with_suffix(".rmdoc")

    doc_id = str(rendered.uuids())
    page_ids = [str(rendered.uuids()) for _ in rendered.rm_pages]
    pages = [
        RmdocPage(data, thumbnail_png(img))
        for data, img in zip(rendered.rm_pages, rendered.images, strict=True)
    ]
    result = write_rmdoc(
        output,
        name,
        pages,
        page_ids,
        rendered.author,
        rendered.device,
        doc_id,
        compress=opts.compress,
        now_ms=0 if opts.seed is not None else None,
    )

    if preview is not None:
        save_preview(rendered.images, Path(preview))

    return ConvertResult(
        path=result.path,
        name=name,
        device=rendered.device.key,
        size_bytes=result.size_bytes,
        pages=[
            PageStats(label=lbl, strokes=len(p.strokes), points=p.point_count, height_px=p.height)
            for lbl, p in zip(rendered.labels, rendered.document.pages, strict=True)
        ],
        warnings=rendered.warnings + result.warnings,
        preview_path=Path(preview) if preview else None,
    )


def save_preview(images: list[Image.Image], path: Path) -> Path:
    img = images[0] if len(images) == 1 else contact_sheet(images)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


def calibration_page(device: DeviceProfile) -> Page:
    """A page with millimetre rulers along two edges and a 50 mm square, for
    checking the coordinate scale on real hardware."""
    from rmink.model import Stroke

    mm = device.px_per_mm
    x0, y0 = 10 * mm, 10 * mm
    strokes = []
    length_x = int((device.width - 2 * x0) / mm)
    length_y = int((device.height - 2 * y0) / mm)
    strokes.append(Stroke([[x0, y0], [x0 + length_x * mm, y0]], width=2))
    strokes.append(Stroke([[x0, y0], [x0, y0 + length_y * mm]], width=2))
    for i in range(length_x + 1):
        tick = 6 if i % 10 == 0 else (4 if i % 5 == 0 else 2)
        strokes.append(Stroke([[x0 + i * mm, y0], [x0 + i * mm, y0 + tick * mm]], width=1.5))
    for i in range(length_y + 1):
        tick = 6 if i % 10 == 0 else (4 if i % 5 == 0 else 2)
        strokes.append(Stroke([[x0, y0 + i * mm], [x0 + tick * mm, y0 + i * mm]], width=1.5))
    cx, cy, s = device.width / 2, device.height / 2, 25 * mm
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1)]
    strokes.append(Stroke([[cx + dx * s, cy + dy * s] for dx, dy in corners], width=3))
    return Page(device.width, device.height, strokes)


def calibration_sheet(device_key: str, output: Path, seed: int | None = None) -> Path:
    device = get_device(device_key)
    uuids = UuidFactory(seed)
    author = uuids()
    page = calibration_page(device)
    data = write_page(page, device, author)
    image = render_rm(data, device)
    write_rmdoc(
        Path(output),
        f"rmink calibration ({device.key})",
        [RmdocPage(data, thumbnail_png(image))],
        [str(uuids())],
        author,
        device,
        str(uuids()),
    )
    return Path(output)


def inspect(path: Path) -> dict:
    """Summarise a ``.rmdoc`` archive or a single ``.rm`` page."""
    import json
    import zipfile
    from collections import Counter

    from rmink.render.preview import read_lines

    def page_summary(name: str, data: bytes) -> dict:
        header = data[:43].decode("ascii", "replace").strip()
        lines = read_lines(data) if "version=6" in header else []
        return {
            "page": name,
            "header": header,
            "strokes": len(lines),
            "points": sum(len(ln.points) for ln in lines),
            "pens": dict(Counter(ln.tool.name for ln in lines)),
            "colors": dict(Counter(ln.color.name for ln in lines)),
            "bytes": len(data),
        }

    path = Path(path)
    if path.suffix.lower() == ".rm":
        return {"file": str(path), "pages": [page_summary(path.name, path.read_bytes())]}

    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        content_name = next(n for n in names if n.endswith(".content"))
        meta_name = next((n for n in names if n.endswith(".metadata")), None)
        content = json.loads(zf.read(content_name))
        doc_id = content_name.removesuffix(".content")
        pages = content.get("cPages", {}).get("pages") or [
            {"id": pid} for pid in content.get("pages", [])
        ]
        summaries = []
        for p in pages:
            rm_name = f"{doc_id}/{p['id']}.rm"
            if rm_name in names:
                summaries.append(page_summary(p["id"], zf.read(rm_name)))
        meta = json.loads(zf.read(meta_name)) if meta_name else {}
    return {
        "file": str(path),
        "name": meta.get("visibleName"),
        "size_bytes": path.stat().st_size,
        "page_count": len(pages),
        "pages": summaries,
    }
