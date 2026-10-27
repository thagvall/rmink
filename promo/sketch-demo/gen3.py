"""Demo data for the detail view ("nedslag") animation, built on gen2.py."""

import json
import runpy
import sys
from pathlib import Path

import numpy as np

from rmink.drawing.model import Annotation, Dimension, Drawing, Element, SketchRef

here = Path(sys.argv[0]).parent
out_path = sys.argv[1]
sys.argv = [str(here / "gen2.py"), str(here / "data2.json"), str(here / "data.json")]
G2 = runpy.run_path(str(here / "gen2.py"))
final, X1, Y1 = G2["final"], G2["X1"], G2["Y1"]
both, split, marked_groups = G2["both"], G2["split"], G2["marked_groups"]
hand_text, hand_line, circle = G2["hand_text"], G2["hand_line"], G2["circle"]

# Overview: r3 with the user's ring around the corner at P3.
marks1 = [circle((X1, Y1), 82, 52, 1.6)] + hand_text("DETALJ", (X1 - 300, Y1 - 52), 34)
_, new1, known1 = marked_groups(final, marks1)
marks1_paths, _, _ = marked_groups(final, marks1)

ov4 = final.model_copy(deep=True)
ov4.revision, ov4.phase = 4, "Detaljering"
ov4.elements.append(
    Element(
        id="DA",
        kind="circle",
        center=(X1 - 38, Y1 - 38),
        radius=72,
        category="dimension",
        line_type="dashed",
    )
)
ov4.elements.append(
    Element(
        id="DAT", kind="text", points=[(X1 - 160, Y1 - 92)], text="A", size=34, category="dimension"
    )
)
ov4.log.append("r4: detalj A vid P3")
ov5 = ov4.model_copy(deep=True)
ov5.revision = 5
ov5.log.append("r5: vinkelbeslag i detalj A")

# Detail page: the corner at P3 at 1:5, in real millimetres.
k = (226 / 25.4) / 5  # device px per mm at 1:5
C = (700.0, 740.0)


def P(x, y):
    return (C[0] + x * k, C[1] + y * k)


R = 300
els = [
    Element(id="F", kind="rect", points=[P(-R, -R), P(R, R)], category="dimension"),
    Element(id="P3", kind="rect", points=[P(-45, -45), P(45, 45)], category="structure"),
    Element(id="V3a", kind="line", points=[P(-45, -22.5), P(-R, -22.5)], category="structure"),
    Element(id="V3b", kind="line", points=[P(-45, 22.5), P(-R, 22.5)], category="structure"),
    Element(id="V2a", kind="line", points=[P(-22.5, -45), P(-22.5, -R)], category="structure"),
    Element(id="V2b", kind="line", points=[P(22.5, -45), P(22.5, -R)], category="structure"),
    Element(
        id="T",
        kind="text",
        points=[(P(-R, -R)[0], P(-R, -R)[1] - 22)],
        text="DETALJ A  SKALA 1:5",
        size=26,
    ),
]
dims = [
    Dimension(id="D1", start=P(-45, 45), end=P(45, 45), text="90", offset=-50),
    Dimension(id="D2", start=P(-200, 22.5), end=P(-200, -22.5), text="45", offset=60),
]
d4 = Drawing(
    name="Altan detalj A",
    revision=4,
    phase="Detaljering",
    date="2026-10-27",
    elements=els,
    dimensions=dims,
    log=["r4: hörn vid P3 ur Altan r3"],
    sketch=SketchRef(device="rm2"),
)

# The user sketches a bracket in the inner corner and asks about it.
L = np.vstack(
    [
        hand_line(P(-30, -150), P(-30, -30), 16, 0.6),
        hand_line(P(-30, -30), P(-150, -30), 16, 0.6)[1:],
    ]
)
marks2 = [L] + hand_text("VINKELBESLAG?", (P(-285, -205)[0], P(-285, -205)[1]), 30)
tip = np.array(P(-95, -95))
marks2 += [
    hand_line(P(-150, -190), tuple(tip), 14, 0.6),
    np.array([tip + [-26, -6], tip, tip + [-8, -26]]),
]
_, new2, known2 = marked_groups(d4, marks2)
marks2_paths, _, _ = marked_groups(d4, marks2)

d5 = d4.model_copy(deep=True)
d5.revision = 5
d5.elements.append(
    Element(
        id="VB1",
        kind="polyline",
        points=[P(-30, -150), P(-30, -30), P(-150, -30)],
        category="change",
    )
)
d5.elements.append(
    Element(
        id="VBT",
        kind="text",
        points=[P(-285, -170)],
        text="VINKELBESLAG",
        size=24,
        category="change",
    )
)
d5.annotations.append(
    Annotation(
        id="A2",
        kind="circle",
        targets=["VB1"],
        text="Vilket beslag? Dimension och skruv",
        revision=4,
    )
)
d5.log.append("r5: vinkelbeslag VB1, typ öppen")

bov3 = both(final)
bov4, bov5 = both(ov4), both(ov5)
bd4, bd5 = both(d4), both(d5)
data = {
    "ov3": bov3,
    "ov4": split(bov4, bov3),
    "ov5": split(bov5, bov4),
    "det4": bd4,
    "det5": split(bd5, bd4),
    "marks1": marks1_paths,
    "new1": new1,
    "marks2": marks2_paths,
    "new2": new2,
    "known": {"ov": known1, "det": known2},
    "scale": "1:5",
    "cut_mm": 2 * R,
}
json.dump(data, open(out_path, "w"), separators=(",", ":"))
print(
    "new1",
    [(g["id"], g["shape"]) for g in new1],
    "new2",
    [(g["id"], g["shape"]) for g in new2],
    {k: (len(data[k]["pro"]["same"]), len(data[k]["pro"]["new"])) for k in ("ov4", "ov5", "det5")},
)
