"""Demo data for the sketch → drawing page, made with rmink itself."""

import json
import sys
from dataclasses import replace
from uuid import UUID

import numpy as np
from rmscene.scene_items import PenColor

from rmink.devices import COLOR_PALETTE, get_device
from rmink.drawing.fit import analyse
from rmink.drawing.font import text_paths
from rmink.drawing.model import (
    Annotation,
    Dimension,
    Drawing,
    Element,
    LegendEntry,
    SketchRef,
    Symbol,
)
from rmink.drawing.render import COMMENT_LAYER, render_drawing
from rmink.drawing.workflow import check_dimensions, rectify
from rmink.ingest.rm import read_page
from rmink.model import Page, Stroke
from rmink.writer.rm_v6 import write_page

rng = np.random.default_rng(7)
RM2 = get_device("rm2")


def hand_line(a, b, n=36, amp=2.2):
    a, b = np.array(a, float), np.array(b, float)
    t = np.linspace(0, 1, n)[:, None]
    p = a + (b - a) * t
    d = b - a
    nrm = np.array([-d[1], d[0]]) / (np.linalg.norm(d) or 1)
    bow = np.sin(np.pi * t[:, 0]) * rng.normal(0, 5)
    wig = np.convolve(rng.normal(0, amp, n), np.ones(5) / 5, "same")
    p = p + nrm * (bow + wig)[:, None]
    p[0] += rng.normal(0, 4, 2)
    p[-1] += rng.normal(0, 4, 2)
    return p


def hand_text(text, origin, size, angle=0.0):
    out = []
    for p in text_paths(text, origin, size, angle):
        q = p.copy()
        q[:, 0] += (origin[1] - q[:, 1]) * 0.12 * (angle == 0)  # slant
        q += rng.normal(0, size * 0.025, q.shape)
        out.append(q)
    return out


def circle(c, r, n=48, wob=2.0):
    t = np.linspace(0, 2 * np.pi * 1.06, n)
    rr = r + np.convolve(rng.normal(0, wob, n), np.ones(5) / 5, "same")
    return np.column_stack([c[0] + rr * np.cos(t), c[1] + rr * np.sin(t)])


def col_mark(c, s=17):
    x, y = c
    sq = np.array(
        [[x - s, y - s], [x + s, y - s], [x + s, y + s], [x - s, y + s], [x - s, y - s]]
    ) + rng.normal(0, 1.5, (5, 2))
    return [
        sq,
        hand_line((x - s, y - s), (x + s, y + s), 8, 0.6),
        hand_line((x + s, y - s), (x - s, y + s), 8, 0.6),
    ]


X0, Y0, X1, Y1 = 230, 360, 1180, 1072  # 950 x 712 px  ->  4800 x 3600
S = []


def add(paths, color=PenColor.BLACK, w=2.4, layer="Layer 1"):
    for p in paths if isinstance(paths, list) else [paths]:
        S.append(Stroke(p, width=w, color=color, layer=layer))


add(
    [
        hand_line((X0, Y0), (X1, Y0)),
        hand_line((X1, Y0), (X1, Y1)),
        hand_line((X1, Y1), (X0, Y1)),
        hand_line((X0, Y1), (X0, Y0)),
    ],
    w=3,
)
add(hand_line((X0, Y0 - 62), (X1, Y0 - 62), amp=1.2), w=1.8)  # dimension line
add(hand_text("4800", (650, Y0 - 78), 34))
add(hand_line((X1 + 62, Y1), (X1 + 62, Y0), amp=1.2), w=1.8)
add(hand_text("3600", (X1 + 112, 760), 34, -90))
add(circle((470, 560), 52), color=PenColor.BLUE)  # brunn
for c in [(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)]:
    add(col_mark(c), w=2.2)
add(hand_line((X1, 760), (X1 - 150, 760), amp=1.0), color=PenColor.RED)  # el
add(circle((X1 - 172, 760), 18, 30, 0.8), color=PenColor.RED)
add(hand_text("ALTAN", (X0, 230), 46))
# The legend the user wrote in the corner of the sketch.
add(col_mark((X0 + 18, 1210), 15), w=2)
add(hand_text("= PELARE 90X90", (X0 + 60, 1226), 28))
add(circle((X0 + 18, 1290), 15, 30, 0.6), color=PenColor.BLUE)
add(hand_text("= BRUNN", (X0 + 60, 1306), 28))
add(hand_line((X0, 1370), (X0 + 40, 1370), 8, 0.4), color=PenColor.RED)
add(hand_text("= EL", (X0 + 60, 1386), 28))

sketch = Page(RM2.width, RM2.height, S)
sketch_rt = read_page(write_page(sketch, RM2, UUID(int=1)), RM2)
groups = analyse(sketch_rt, RM2)


def fit_of(gid):
    return next(g for g in groups if g.id == gid)


# The drawing an interpreter would build: walls from the fitted lines,
# everything else read from the marks.
walls = [
    g
    for g in groups
    if g.shape == "line"
    and min(g.bbox[2] - g.bbox[0], g.bbox[3] - g.bbox[1]) < 30
    and max(g.bbox[2] - g.bbox[0], g.bbox[3] - g.bbox[1]) > 600
]
walls = [
    w
    for w in walls
    if X0 - 40 < (w.bbox[0] + w.bbox[2]) / 2 < X1 + 40
    and Y0 - 40 < (w.bbox[1] + w.bbox[3]) / 2 < Y1 + 40
]
elements = [
    Element(
        id=f"V{i + 1}",
        kind="line",
        points=[tuple(p) for p in w.fit["points"]],
        category="structure",
        source_groups=[w.id],
    )
    for i, w in enumerate(walls)
]
brunn = next(g for g in groups if g.shape == "circle" and g.color == "blue" and g.bbox[1] < 1100)
elements.append(
    Element(
        id="B1",
        kind="circle",
        center=tuple(brunn.fit["center"]),
        radius=brunn.fit["radius"],
        category="plumbing",
        source_groups=[brunn.id],
    )
)
elements.append(
    Element(id="E1", kind="line", points=[(X1, 760), (X1 - 150, 760)], category="electrical")
)
d1 = Drawing(
    name="Altan",
    phase="Förslag",
    date="2026-10-27",
    elements=elements,
    dimensions=[
        Dimension(id="M1", start=(X0, Y0), end=(X1, Y0), text="4800", value=4800, offset=62),
        Dimension(id="M2", start=(X1, Y1), end=(X1, Y0), text="3600", value=3600, offset=-62),
    ],
    symbols=[
        Symbol(id=f"P{i + 1}", kind="column", at=c, size=34, label=f"P{i + 1}")
        for i, c in enumerate([(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)])
    ]
    + [Symbol(id="U1", kind="outlet", at=(X1 - 172, 760), size=36, category="electrical")],
    legend=[
        LegendEntry(key="column", meaning="Pelare 90x90"),
        LegendEntry(key="category:plumbing", meaning="Brunn / avlopp"),
        LegendEntry(key="outlet", meaning="Eluttag"),
        LegendEntry(key="category:structure", meaning="Bärande"),
    ],
    log=["r1: renritad från skiss"],
    sketch=SketchRef(document="/Altan", device="rm2"),
)
d1 = rectify(d1)
check = check_dimensions(d1)

# Round 2: the user rings P3 and writes a question, and crosses out the drain.
P3 = (X1, Y1)
marks = [circle(P3, 58, 50, 1.5)] + hand_text("FLYTTA 200?", (X1 - 330, Y1 - 92), 30)
marks += [hand_line((410, 500), (530, 620), 10, 0.8), hand_line((530, 500), (410, 620), 10, 0.8)]
mark_strokes = [Stroke(m, width=2.6, color=PenColor.MAGENTA, layer=COMMENT_LAYER) for m in marks]

d2 = d1.model_copy(deep=True)
d2.revision, d2.phase = 2, "Granskning"
d2.elements = [e for e in d2.elements if e.id != "B1"]
d2.legend = [entry for entry in d2.legend if entry.key != "category:plumbing"]
d2.annotations.append(
    Annotation(id="A1", kind="circle", targets=["P3"], text="Flytta P3 200 mot väster?", revision=1)
)
d2.log.append("r2: brunn B1 struken")


def page_for(dev_key, drawing):
    # Same page geometry as the sketch; only colour differs.
    return render_drawing(drawing, replace(RM2, color=(dev_key == "pro")))


# Clean page ids, for the "only new strokes" step.
clean1 = page_for("rm2", d1)
written = read_page(write_page(clean1, RM2, UUID(int=2)), RM2)
marked = Page(clean1.width, clean1.height, clean1.strokes + mark_strokes, clean1.layer_names)
marked_rt = read_page(write_page(marked, RM2, UUID(int=2)), RM2)
known = {s.id for s in written.strokes}
new_groups = analyse(marked_rt, RM2, known)

HEX = {e.color: "#{:02x}{:02x}{:02x}".format(*e.rgb) for e in COLOR_PALETTE}
MONO = {PenColor.BLACK: "#1b1d1f", PenColor.GRAY: "#7d7d7d"}


def mono(c):
    return (
        MONO.get(c, "#1b1d1f")
        if c in MONO
        else (
            "#7d7d7d"
            if c in (PenColor.MAGENTA, PenColor.PINK, PenColor.YELLOW, PenColor.CYAN)
            else "#1b1d1f"
        )
    )


def paths(strokes, colour_mono=None):
    out = []
    for s in strokes:
        pts = s.points
        d = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
        out.append(
            {
                "d": d,
                "c": HEX.get(s.color, "#000"),
                "m": colour_mono or mono(s.color),
                "w": round(float(s.width), 2),
            }
        )
    return out


def clean_paths(drawing):
    pro, rm2 = page_for("pro", drawing).strokes, page_for("rm2", drawing).strokes
    return {"pro": paths(pro), "rm2": [{**p, "c": p["m"]} for p in paths(rm2)]}


data = {
    "sketch": paths(S),
    "groups": [{"id": g.id, "b": [round(v) for v in g.bbox], "shape": g.shape} for g in groups],
    "clean1": clean_paths(d1),
    "clean2": clean_paths(d2),
    "marks": paths(mark_strokes, "#7d7d7d"),
    "newGroups": [
        {"id": g.id, "b": [round(v) for v in g.bbox], "shape": g.shape} for g in new_groups
    ],
    "check": check,
    "counts": {
        "sketch": len(S),
        "groups": len(groups),
        "clean1": len(clean1.strokes),
        "known": len(known),
        "new": len(new_groups),
    },
}
json.dump(data, open(sys.argv[1], "w"), separators=(",", ":"))
print(json.dumps(data["counts"]), json.dumps(check))
for g in groups:
    print(g.id, g.shape, [round(v) for v in g.bbox], g.color)
print("new:", [(g.id, g.shape, [round(v) for v in g.bbox]) for g in new_groups])
