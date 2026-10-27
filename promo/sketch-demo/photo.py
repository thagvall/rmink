"""A synthetic phone photo of a pencil sketch on paper: a small shed plan."""

import json
import math
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from rmink.drawing.font import text_paths

rng = np.random.default_rng(11)
W, H = 1200, 1600
S = 5.0  # photo px per paper mm
OFF = np.array([75.0, 57.0])
ROT = math.radians(1.6)
CEN = np.array([W / 2, H / 2])


def to_photo(pts_mm):
    p = np.asarray(pts_mm, float) * S + OFF
    c, s = math.cos(ROT), math.sin(ROT)
    return (p - CEN) @ np.array([[c, s], [-s, c]]) + CEN


def wob(a, b, n=30, amp=0.35):
    a, b = np.array(a, float), np.array(b, float)
    t = np.linspace(0, 1, n)[:, None]
    p = a + (b - a) * t
    d = b - a
    nrm = np.array([-d[1], d[0]]) / (np.linalg.norm(d) or 1)
    p += (
        nrm
        * (
            np.sin(np.pi * t[:, 0]) * rng.normal(0, 0.8)
            + np.convolve(rng.normal(0, amp, n), np.ones(5) / 5, "same")
        )[:, None]
    )
    # Pencil strokes overshoot their ends a little.
    p[0] -= (b - a) / np.linalg.norm(b - a) * rng.uniform(0.5, 2.5)
    p[-1] += (b - a) / np.linalg.norm(b - a) * rng.uniform(0.5, 2.5)
    return p


def arc(c, r, a0, a1, n=30):
    t = np.radians(np.linspace(a0, a1, n))
    return np.column_stack([c[0] + r * np.cos(t), c[1] + r * np.sin(t)]) + rng.normal(
        0, 0.25, (n, 2)
    )


def write(text, at, size):
    return [p + rng.normal(0, size * 0.03, p.shape) for p in text_paths(text, at, size)]


# The sketch in paper millimetres (A4 portrait, 210 x 297).
X0, Y0, X1, Y1 = 30, 70, 180, 190  # 150 x 120 mm  ->  3000 x 2400 at 1:20
D0, D1 = 62, 102  # door opening in the bottom wall
WI0, WI1 = 112, 160  # window in the top wall
strokes = [
    wob((X0, Y0), (WI0, Y0)),
    wob((WI1, Y0), (X1, Y0)),
    wob((X1, Y0), (X1, Y1)),
    wob((X1, Y1), (D1, Y1)),
    wob((D0, Y1), (X0, Y1)),
    wob((X0, Y1), (X0, Y0)),
    wob((WI0, Y0 - 3), (WI1, Y0 - 3), 16),
    wob((WI0, Y0 + 3), (WI1, Y0 + 3), 16),
    wob((WI0, Y0 - 3), (WI0, Y0 + 3), 6, 0.1),
    wob((WI1, Y0 - 3), (WI1, Y0 + 3), 6, 0.1),
    wob((D0, Y1), (D0, Y1 - 40), 16),
    arc((D0, Y1), 40, -90, 0),
    wob((X0, Y0 - 14), (X1, Y0 - 14), 30, 0.2),
    wob((X1 + 14, Y0), (X1 + 14, Y1), 30, 0.2),
]
strokes += write("3000", (93, Y0 - 18), 8)
strokes += [p for p in text_paths("2400", (X1 + 26, 142), 8, -90)]
strokes += write("FÖRRÅD", (X0, 34), 12)
strokes += write("TAKLUTNING 15°", (X0, 214), 7)
strokes += write("DÖRR 9X21", (D1 + 4, Y1 - 6), 5)

# Paper on a light table, with a soft shadow and uneven light.
img = Image.new("RGB", (W, H))
yy, xx = np.mgrid[0:H, 0:W]
table = np.stack([196 + 12 * (xx / W), 191 + 10 * (xx / W), 182 + 6 * (yy / H)], -1)
img = Image.fromarray(np.clip(table + rng.normal(0, 3, table.shape), 0, 255).astype(np.uint8))
corners = to_photo([(0, 0), (210, 0), (210, 297), (0, 297)])
shadow = Image.new("L", (W, H), 0)
ImageDraw.Draw(shadow).polygon([tuple(p + [10, 14]) for p in corners], fill=90)
img.paste((120, 116, 108), mask=shadow.filter(ImageFilter.GaussianBlur(16)))
paper = Image.new("L", (W, H), 0)
ImageDraw.Draw(paper).polygon([tuple(p) for p in corners], fill=255)
light = 244 - 10 * ((xx - W * 0.3) ** 2 + (yy - H * 0.25) ** 2) / (W**2 + H**2) * 4
tone = np.stack([light, light - 2, light - 7], -1) + rng.normal(0, 2.2, (H, W, 3))
img.paste(Image.fromarray(np.clip(tone, 0, 255).astype(np.uint8)), mask=paper)

ink = Image.new("L", (W, H), 0)
dr = ImageDraw.Draw(ink)
for s in strokes:
    pts = [tuple(p) for p in to_photo(s)]
    dr.line(
        pts, fill=int(rng.uniform(150, 200)), width=int(rng.choice([3, 4, 4, 5])), joint="curve"
    )
ink = ink.filter(ImageFilter.GaussianBlur(0.8))
img.paste((62, 62, 70), mask=ink)
img = img.filter(ImageFilter.GaussianBlur(0.5))
img.save(sys.argv[1], quality=88)

json.dump(
    {
        "S": S,
        "OFF": OFF.tolist(),
        "ROT": ROT,
        "W": W,
        "H": H,
        "box": [X0, Y0, X1, Y1],
        "door": [D0, D1],
        "window": [WI0, WI1],
    },
    open(sys.argv[2], "w"),
)
