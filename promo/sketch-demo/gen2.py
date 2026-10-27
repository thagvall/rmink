"""Demo data for the variants A/B animation, built on gen.py's drawing."""

import json
import runpy
import sys
from uuid import UUID

import numpy as np
from rmscene.scene_items import PenColor

from rmink.drawing.model import Dimension, Element, LegendEntry, Symbol
from rmink.drawing.render import COMMENT_LAYER
from rmink.ingest.rm import read_page
from rmink.model import Page, Stroke
from rmink.writer.rm_v6 import write_page

out_path = sys.argv[1]
sys.argv = [sys.argv[0], sys.argv[2]]  # gen.py writes its own data file
G = runpy.run_path(sys.argv[0].replace("gen2.py", "gen.py"))
d2, X0, Y0, X1, Y1 = G["d2"], G["X0"], G["Y0"], G["X1"], G["Y1"]
page_for, paths, analyse, hand_text, hand_line, circle = (
    G["page_for"],
    G["paths"],
    G["analyse"],
    G["hand_text"],
    G["hand_line"],
    G["circle"],
)


RM2 = G["RM2"]
mm_per_px = G["check"]["scale_units_per_px"]
base = d2.model_copy(deep=True)

Ym = (Y0 + Y1) / 2
A = base.model_copy(deep=True)
A.revision, A.phase = 3, "Alternativ A"
A.elements.append(Element(id="BL1", kind="line", points=[(X0, Ym), (X1, Ym)], category="change"))
A.symbols.append(Symbol(id="P5", kind="column", at=((X0 + X1) / 2, Ym), size=34, label="P5"))
A.dimensions.append(
    Dimension(
        id="M3",
        start=(X0, Y0),
        end=(X0, Ym),
        text=f"{round((Ym - Y0) * mm_per_px, -1):.0f}",
        offset=62,
    )
)
A.legend.append(LegendEntry(key="category:change", meaning="Ny bärlina"))
A.log.append("r3A: bärlina längs, mittpelare P5")

xs = [X0 + (X1 - X0) / 3, X0 + 2 * (X1 - X0) / 3]
B = base.model_copy(deep=True)
B.revision, B.phase = 3, "Alternativ B"
for i, x in enumerate(xs):
    B.elements.append(
        Element(id=f"BL{i + 1}", kind="line", points=[(x, Y0), (x, Y1)], category="change")
    )
B.dimensions.append(
    Dimension(
        id="M3",
        start=(X0, Y0 + 150),
        end=(xs[0], Y0 + 150),
        text=f"{round((xs[0] - X0) * mm_per_px, -1):.0f}",
        offset=1,
    )
)
B.legend.append(LegendEntry(key="category:change", meaning="Ny bärlina"))
B.log.append("r3B: två bärlinor tvärs, inga nya pelare")

final = B.model_copy(deep=True)
final.phase = "Beslut"
final.log[-1] = "r3: variant B vald, A förkastad"


def both(d):
    return {
        "pro": paths(page_for("pro", d).strokes),
        "rm2": [{**p, "c": p["m"]} for p in paths(page_for("rm2", d).strokes)],
    }


def split(new, old):
    """Strokes identical to the previous page stay put; the rest are drawn in."""
    out = {}
    for dev in ("pro", "rm2"):
        seen = {p["d"] for p in old[dev]}
        out[dev] = {
            "same": [p for p in new[dev] if p["d"] in seen],
            "new": [p for p in new[dev] if p["d"] not in seen],
        }
    return out


pb, pa, pB, pf = both(base), both(A), both(B), both(final)

# The choice, written on the tablet: a cross on A, a tick and "KÖR B" on B.
cross = [
    hand_line((X0 + 120, Y0 + 110), (X1 - 120, Y1 - 110), 30, 1.2),
    hand_line((X1 - 120, Y0 + 110), (X0 + 120, Y1 - 110), 30, 1.2),
]
tick = [np.array([[575, 930], [610, 975], [680, 870]], float) + G["rng"].normal(0, 1.5, (3, 2))]
tick += G["hand_text"]("KÖR B", (650, 1000), 40)


def marked_groups(d, marks):
    clean = page_for("rm2", d)
    written = read_page(write_page(clean, RM2, UUID(int=2)), RM2)
    strokes = [Stroke(m, width=2.6, color=PenColor.MAGENTA, layer=COMMENT_LAYER) for m in marks]
    both_ = read_page(
        write_page(
            Page(clean.width, clean.height, clean.strokes + strokes, clean.layer_names),
            RM2,
            UUID(int=2),
        ),
        RM2,
    )
    gs = analyse(both_, RM2, {s.id for s in written.strokes})
    return (
        paths(strokes, "#7d7d7d"),
        [{"id": g.id, "b": [round(v) for v in g.bbox], "shape": g.shape} for g in gs],
        len(written.strokes),
    )


marksA, newA, knownA = marked_groups(A, cross)
marksB, newB, knownB = marked_groups(B, tick)


def span(px):
    return round(px * mm_per_px, -1)


data = {
    "base": pb,
    "A": split(pa, pb),
    "B": split(pB, pb),
    "final": split(pf, pB),
    "marksA": marksA,
    "marksB": marksB,
    "newA": newA,
    "newB": newB,
    "compare": {
        "A": {"beams": 1, "posts": 1, "span": span(Ym - Y0), "beam_mm": span(X1 - X0)},
        "B": {"beams": 2, "posts": 0, "span": span(xs[0] - X0), "beam_mm": 2 * span(Y1 - Y0)},
    },
    "known": {"A": knownA, "B": knownB},
}
json.dump(data, open(out_path, "w"), separators=(",", ":"))
print(
    json.dumps(data["compare"]),
    "newA",
    [(g["id"], g["shape"]) for g in newA],
    "newB",
    [(g["id"], g["shape"]) for g in newB],
    {k: (len(data[k]["pro"]["same"]), len(data[k]["pro"]["new"])) for k in ("A", "B", "final")},
)
