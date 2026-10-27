"""Demo data for the paper sketch animation: a photo through rmink's real
photo conversion, then grouping and a clean drawing."""

import base64
import io
import json
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image

from rmink import api
from rmink.api import _raster_placement
from rmink.devices import COLOR_PALETTE, get_device
from rmink.drawing.fit import analyse
from rmink.drawing.model import Dimension, Drawing, Element, LegendEntry, SketchRef
from rmink.drawing.render import render_drawing
from rmink.drawing.workflow import check_dimensions, rectify
from rmink.ingest import load
from rmink.options import ConvertOptions

here = Path(sys.argv[0]).parent
photo, meta = here / "forrad.jpg", json.loads((here / "forrad.json").read_text())

RM2 = get_device("rm2")
opts = ConvertOptions(device="rm2", mode="centerline")
rendered = api.render([photo], opts)
page = rendered.document.pages[0]
src = next(iter(load(photo, "centerline", None)))
placement = _raster_placement(src, RM2, opts)
f = src.image.shape[1] / meta["W"]

S, OFF = meta["S"], np.array(meta["OFF"])


def mm(x, y):
    """Paper mm to page px, without the photo's slight rotation (the clean
    drawing is square to the page)."""
    p = (np.array([[x, y]], float) * S + OFF) * f
    return tuple(float(v) for v in placement.apply(p)[0])


X0, Y0, X1, Y1 = meta["box"]
D0, D1 = meta["door"]
W0, W1 = meta["window"]
px_per_mm = mm(1, 0)[0] - mm(0, 0)[0]
groups = analyse(page, RM2)


def L(i, a, b, cat="structure"):
    return Element(id=i, kind="line", points=[mm(*a), mm(*b)], category=cat)


els = [
    L("V1", (X0, Y0), (W0, Y0)),
    L("V2", (W1, Y0), (X1, Y0)),
    L("V3", (X1, Y0), (X1, Y1)),
    L("V4", (X1, Y1), (D1, Y1)),
    L("V5", (D0, Y1), (X0, Y1)),
    L("V6", (X0, Y1), (X0, Y0)),
    L("F1", (W0, Y0 - 3), (W1, Y0 - 3), "default"),
    L("F2", (W0, Y0), (W1, Y0), "default"),
    L("F3", (W0, Y0 + 3), (W1, Y0 + 3), "default"),
    L("F4", (W0, Y0 - 3), (W0, Y0 + 3), "default"),
    L("F5", (W1, Y0 - 3), (W1, Y0 + 3), "default"),
    L("D", (D0, Y1), (D0, Y1 - 40), "default"),
    Element(
        id="DB",
        kind="arc",
        center=mm(D0, Y1),
        radius=40 * px_per_mm,
        start_angle=-90,
        end_angle=0,
        category="hidden",
    ),
    Element(id="T1", kind="text", points=[mm(D1 + 4, Y1 - 6)], text="DÖRR 9X21", size=22),
    Element(id="T2", kind="text", points=[mm(X0, 214)], text="TAKLUTNING 15°", size=26),
]
d = Drawing(
    name="Förråd",
    phase="Förslag",
    date="2026-10-27",
    elements=els,
    dimensions=[
        Dimension(id="M1", start=mm(X0, Y0), end=mm(X1, Y0), text="3000", value=3000, offset=70),
        Dimension(id="M2", start=mm(X1, Y1), end=mm(X1, Y0), text="2400", value=2400, offset=-70),
    ],
    legend=[
        LegendEntry(key="category:structure", meaning="Vägg"),
        LegendEntry(key="window", meaning="Fönster"),
        LegendEntry(key="door", meaning="Dörr 9x21"),
    ],
    log=["r1: från foto av pappersskiss"],
    sketch=SketchRef(document="forrad.jpg", device="rm2"),
)
d = rectify(d)
check = check_dimensions(d)

HEX = {e.color: "#{:02x}{:02x}{:02x}".format(*e.rgb) for e in COLOR_PALETTE}
MONO = {"#000000": "#1b1d1f", "#7d7d7d": "#7d7d7d"}


def paths(strokes, mono=False):
    out = []
    for s in strokes:
        c = HEX.get(s.color, "#000000")
        m = (
            "#7d7d7d"
            if c not in ("#000000",) and c != "#000000" and s.color.name in ("GRAY", "MAGENTA")
            else "#1b1d1f"
        )
        out.append(
            {
                "d": "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in s.points),
                "c": c,
                "m": m,
                "w": round(float(s.width), 2),
            }
        )
    return out


def both(dd):
    return {
        "pro": paths(render_drawing(dd, replace(RM2, color=True)).strokes),
        "rm2": [{**p, "c": p["m"]} for p in paths(render_drawing(dd, RM2).strokes)],
    }


img = Image.open(photo).convert("RGB")
img.thumbnail((720, 960))
buf = io.BytesIO()
img.save(buf, "JPEG", quality=80)
ink = [{**p, "c": "#1b1d1f", "m": "#1b1d1f"} for p in paths(page.strokes)]
data = {
    "photo": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
    "photoSize": list(img.size),
    "ink": ink,
    "inkPoints": page.point_count,
    "groups": [{"id": g.id, "b": [round(v) for v in g.bbox], "shape": g.shape} for g in groups],
    "clean": both(d),
    "check": check,
}
json.dump(data, open(sys.argv[1], "w"), separators=(",", ":"))

print(
    len(page.strokes),
    "strokes",
    page.point_count,
    "points;",
    Counter(g.shape for g in groups),
    check["dimensions"],
)
for g in groups:
    print(g.id, g.shape, [round(v) for v in g.bbox])
