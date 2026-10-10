"""Generate a photo-like handwritten note (EN or SV) for the promo video.

Usage: python promo/make_note.py en|sv OUT.jpg
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
FONT = HERE / "out" / "assets" / "Caveat.ttf"

TEXT = {
    "en": {
        "title": "Weekend plan",
        "items": ["call mum", "buy sourdough", "fix the bike", "sketch the cabin"],
    },
    "sv": {
        "title": "Helgens plan",
        "items": ["ringa mamma", "köpa surdeg", "laga cykeln", "skissa stugan"],
    },
}

W, H = 2400, 3000
INK = (28, 36, 60)
BLUE = (34, 78, 196)
RED = (196, 44, 44)


def font(size: int, weight: int = 500) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(FONT), size)
    f.set_variation_by_axes([weight])
    return f


def wobbly(draw, pts, fill, width, rng, jitter=2.0, steps=24):
    """Hand-drawn polyline through pts."""
    pts = np.asarray(pts, dtype=float)
    out = []
    for a, b in zip(pts[:-1], pts[1:], strict=True):
        for t in np.linspace(0, 1, steps, endpoint=False):
            out.append(a + (b - a) * t)
    out.append(pts[-1])
    out = np.array(out)
    noise = np.cumsum(rng.normal(0, jitter, out.shape), axis=0) * 0.25
    noise -= np.linspace(0, 1, len(out))[:, None] * noise[-1]  # end where we aim
    out = out + noise
    draw.line([tuple(p) for p in out], fill=fill, width=width, joint="curve")


def make(lang: str, out: Path, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    t = TEXT[lang]
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # Title + red wavy underline.
    title_font = font(250, 600)
    d.text((260, 250), t["title"], font=title_font, fill=INK)
    tw = d.textlength(t["title"], font=title_font)
    xs = np.linspace(270, 270 + tw, 40)
    ys = 610 + 14 * np.sin(np.linspace(0, 5 * np.pi, 40))
    wobbly(d, np.c_[xs, ys], RED, 13, rng, jitter=1.2, steps=4)

    # Checklist.
    item_font = font(165, 500)
    y = 860
    for i, item in enumerate(t["items"]):
        box = [(300, y + 55), (390, y + 52), (393, y + 142), (302, y + 145), (300, y + 55)]
        wobbly(d, box, INK, 9, rng, jitter=1.0, steps=8)
        if i < 2:  # done items get a blue tick
            wobbly(d, [(312, y + 95), (345, y + 132), (420, y + 20)], BLUE, 12, rng, steps=10)
        d.text((460, y - 10), item, font=item_font, fill=INK)
        y += 300

    # Arrow from the last item down to the sketch.
    last_w = d.textlength(t["items"][-1], font=item_font)
    ax = 460 + last_w + 40
    wobbly(d, [(ax, y - 200), (ax + 160, y - 140), (ax + 250, y + 40)], INK, 10, rng)
    wobbly(d, [(ax + 190, y + 10), (ax + 250, y + 40), (ax + 270, y - 30)], INK, 10, rng, steps=6)

    # Blue cabin sketch with sun.
    cx, cy = 1150, 2480
    house = [
        (cx - 330, cy),
        (cx - 330, cy + 380),
        (cx + 330, cy + 380),
        (cx + 330, cy),
        (cx - 330, cy),
    ]
    roof = [(cx - 400, cy + 20), (cx, cy - 300), (cx + 400, cy + 20)]
    door = [(cx - 70, cy + 380), (cx - 70, cy + 170), (cx + 70, cy + 170), (cx + 70, cy + 380)]
    window = [
        (cx + 150, cy + 90),
        (cx + 270, cy + 90),
        (cx + 270, cy + 200),
        (cx + 150, cy + 200),
        (cx + 150, cy + 90),
    ]
    chimney = [
        (cx + 180, cy - 150),
        (cx + 180, cy - 280),
        (cx + 260, cy - 280),
        (cx + 260, cy - 80),
    ]
    for shape in (house, roof, door, window, chimney):
        wobbly(d, shape, BLUE, 11, rng, jitter=1.4, steps=14)
    smoke = [
        (cx + 220 + 35 * np.sin(a), cy - 300 - a * 35) for a in np.linspace(0, 1.5 * np.pi, 20)
    ]
    wobbly(d, smoke, BLUE, 9, rng, jitter=0.8, steps=3)
    sx, sy, r = cx - 640, cy - 200, 95
    sun = [(sx + r * np.cos(a), sy + r * np.sin(a)) for a in np.linspace(0, 2 * np.pi, 40)]
    wobbly(d, sun, BLUE, 10, rng, jitter=0.8, steps=3)
    for a in np.linspace(0, 2 * np.pi, 9)[:-1]:
        wobbly(
            d,
            [
                (sx + 140 * np.cos(a), sy + 140 * np.sin(a)),
                (sx + 200 * np.cos(a), sy + 200 * np.sin(a)),
            ],
            BLUE,
            9,
            rng,
            steps=4,
        )
    wobbly(d, [(cx - 700, cy + 385), (cx + 700, cy + 380)], INK, 9, rng, jitter=1.5, steps=30)

    # Photo look: ink softness, paper colour, uneven light, grain, slight blur.
    arr = np.asarray(img.filter(ImageFilter.GaussianBlur(1.6)), dtype=float) / 255
    yy, xx = np.mgrid[0:H, 0:W]
    light = 0.86 + 0.12 * (1 - xx / W) * (1 - 0.5 * yy / H) - 0.08 * ((yy / H) ** 2)
    paper = np.array([0.97, 0.95, 0.90])
    rgb = arr * paper * light[..., None]
    rgb += rng.normal(0, 0.012, rgb.shape)
    Image.fromarray(np.clip(rgb * 255, 0, 255).astype(np.uint8)).save(out, quality=92)


if __name__ == "__main__":
    make(sys.argv[1], Path(sys.argv[2]))
