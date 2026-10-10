"""Render ``.rm`` v6 bytes back to an image.

Rendering from the *parsed* file rather than the in-memory model means every
preview also exercises the writer.
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw
from rmscene import scene_items as si
from rmscene.scene_stream import SceneLineItemBlock, read_blocks

from rmink.devices import COLOR_PALETTE, DeviceProfile

_HIGHLIGHT_ALPHA = 90
_PALETTE_RGB = {e.color: e.rgb for e in COLOR_PALETTE}


def read_lines(rm_bytes: bytes) -> list[si.Line]:
    return [
        b.item.value
        for b in read_blocks(io.BytesIO(rm_bytes))
        if isinstance(b, SceneLineItemBlock) and b.item.value is not None
    ]


def _rgb(line: si.Line) -> tuple[int, int, int]:
    if line.color_rgba is not None:
        return line.color_rgba[:3]
    return _PALETTE_RGB.get(line.color, (0, 0, 0))


def render_rm(rm_bytes: bytes, device: DeviceProfile, height: int | None = None) -> Image.Image:
    lines = read_lines(rm_bytes)
    s = device.ink_scale
    max_y = max((p.y for ln in lines for p in ln.points), default=0) / s
    h = max(height or device.height, int(max_y) + 1)
    img = Image.new("RGB", (device.width, h), "white")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    odraw = ImageDraw.Draw(overlay)

    for ln in lines:
        rgb = _rgb(ln)
        highlight = si.Pen.is_highlighter(ln.tool) or ln.tool == si.Pen.SHADER
        target = odraw if highlight else draw
        fill = (*rgb, _HIGHLIGHT_ALPHA) if highlight else rgb
        pts = [(p.x / s + device.width / 2, p.y / s) for p in ln.points]
        if len(pts) == 1:
            r = max(ln.points[0].width / 8 / s, 0.5)
            x, y = pts[0]
            target.ellipse((x - r, y - r, x + r, y + r), fill=fill)
            continue
        for (p0, p1), pt in zip(zip(pts, pts[1:], strict=False), ln.points, strict=False):
            w = max(round(pt.width / 4 / s), 1)
            target.line((p0, p1), fill=fill, width=w)
            if w > 2:
                r = w / 2
                target.ellipse((p1[0] - r, p1[1] - r, p1[0] + r, p1[1] + r), fill=fill)

    img.paste(overlay, (0, 0), overlay)
    return img


def thumbnail_png(image: Image.Image, width: int = 280) -> bytes:
    h = round(image.height * width / image.width)
    buf = io.BytesIO()
    image.resize((width, h), Image.Resampling.LANCZOS).save(buf, "PNG", optimize=True)
    return buf.getvalue()


def contact_sheet(images: list[Image.Image], columns: int = 4, width: int = 400) -> Image.Image:
    thumbs = [im.resize((width, round(im.height * width / im.width))) for im in images]
    cols = min(columns, len(thumbs)) or 1
    rows = (len(thumbs) + cols - 1) // cols
    cell_h = max((t.height for t in thumbs), default=1)
    gap = 12
    sheet = Image.new(
        "RGB", (cols * width + (cols + 1) * gap, rows * cell_h + (rows + 1) * gap), (210, 210, 210)
    )
    for i, t in enumerate(thumbs):
        r, c = divmod(i, cols)
        sheet.paste(t, (gap + c * (width + gap), gap + r * (cell_h + gap)))
    return sheet
