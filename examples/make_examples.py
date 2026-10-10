"""Generate the example inputs used in the README and tests."""

from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).parent

LOGO_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <circle cx="200" cy="200" r="150" fill="none" stroke="#1f4fd1" stroke-width="10"/>
  <path d="M120 260 L200 110 L280 260 Z" fill="#d12a2a"/>
  <path d="M110 300 C160 340 240 340 290 300" fill="none" stroke="#1c9a3c" stroke-width="8"
        stroke-linecap="round"/>
  <rect x="185" y="300" width="30" height="30" fill="#111"/>
</svg>
"""


def make_svg(path: Path) -> None:
    path.write_text(LOGO_SVG)


def make_pdf(path: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 90), "rmink: native ink for reMarkable", fontsize=22)
    page.insert_textbox(
        pymupdf.Rect(60, 120, 535, 300),
        "Vector PDFs become editable strokes: text glyphs are outlined, lines stay "
        "lines and filled shapes are hatched. Erase, lasso and recolour them on the "
        "tablet like your own handwriting.",
        fontsize=12,
    )
    page.draw_rect(pymupdf.Rect(60, 330, 260, 480), color=(0, 0, 0), width=2)
    page.draw_circle((400, 405), 70, color=(0.1, 0.3, 0.8), width=3)
    page.draw_line((60, 520), (535, 620), color=(0.8, 0.1, 0.1), width=4)
    shape = page.new_shape()
    shape.draw_rect(pymupdf.Rect(60, 650, 200, 760))
    shape.finish(fill=(0.2, 0.2, 0.2), color=None)
    shape.commit()
    page2 = doc.new_page(width=595, height=842)
    page2.insert_text((60, 90), "Page two", fontsize=28)
    page2.draw_bezier((60, 300), (200, 100), (400, 500), (535, 300), color=(0, 0, 0), width=2)
    doc.save(path)


def make_handwriting_photo(path: Path, seed: int = 1) -> None:
    """A fake phone photo: hand-drawn-ish strokes, uneven lighting, noise."""
    rng = np.random.default_rng(seed)
    w, h = 1600, 1200
    img = Image.new("L", (w, h), 255)
    d = ImageDraw.Draw(img)

    def wobbly(points, width):
        pts = np.array(points, dtype=float)
        t = np.linspace(0, 1, 200)
        # Catmull-Rom-ish through the control points with jitter.
        xs = np.interp(t, np.linspace(0, 1, len(pts)), pts[:, 0])
        ys = np.interp(t, np.linspace(0, 1, len(pts)), pts[:, 1])
        xs += np.cumsum(rng.normal(0, 0.4, len(t)))
        ys += np.cumsum(rng.normal(0, 0.4, len(t)))
        d.line(list(zip(xs, ys, strict=False)), fill=30, width=width, joint="curve")

    # A loopy cursive-ish word and some shapes.
    t = np.linspace(0, 6 * np.pi, 400)
    x = 200 + t * 45
    y = 300 + 60 * np.sin(t) - 30 * np.cos(2 * t)
    d.line(list(zip(x, y, strict=False)), fill=25, width=7, joint="curve")
    wobbly([(200, 550), (600, 520), (1000, 560), (1400, 540)], 6)  # underline
    wobbly([(300, 700), (500, 1000), (700, 700)], 8)  # V
    d.ellipse((900, 700, 1250, 1000), outline=35, width=7)
    wobbly([(1000, 760), (1150, 940)], 6)
    d.ellipse((1330, 690, 1352, 712), fill=30)  # a dot

    arr = np.asarray(img, dtype=float)
    yy, xx = np.mgrid[0:h, 0:w]
    lighting = 0.75 + 0.25 * (xx / w) - 0.12 * ((yy - h / 2) / h) ** 2
    paper = 235 * lighting
    arr = np.minimum(arr, 255) / 255 * paper + rng.normal(0, 4, arr.shape)
    rgb = np.stack([arr * 1.0, arr * 0.97, arr * 0.92], axis=-1)
    out = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)).filter(
        ImageFilter.GaussianBlur(1.2)
    )
    out.save(path, quality=88)


if __name__ == "__main__":
    make_svg(HERE / "logo.svg")
    make_pdf(HERE / "document.pdf")
    make_handwriting_photo(HERE / "handwriting.jpg")
    print("examples written to", HERE)
