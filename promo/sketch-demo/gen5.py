"""Demo data for the export animation: the real SVG export of Altan r5, and
the same drawing model as millimetre geometry for a PDF sheet and a DXF file."""

import json
import math
import runpy
import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

from rmink.drawing.render import page_svg, render_drawing

here = Path(sys.argv[0]).parent
out_path = sys.argv[1]
sys.argv = [str(here / "gen3.py"), str(here / "data3.json")]
G3 = runpy.run_path(str(here / "gen3.py"))
ov5, both, RM2 = G3["ov5"], G3["both"], G3["G2"]["RM2"]
X0, Y0, X1, Y1 = G3["G2"]["X0"], G3["G2"]["Y0"], G3["X1"], G3["Y1"]
k = G3["G2"]["mm_per_px"]

svg_text = page_svg(render_drawing(ov5, replace(RM2, color=True)), RM2)


def mm(p):
    """Page px to millimetres, origin at P4 (bottom left), y up, locked to a
    50 mm grid so the walls land exactly on the written measurements."""
    return [round((p[0] - X0) * k / 50) * 50, round((Y1 - p[1]) * k / 50) * 50]


LAYER_OF = {
    "structure": "VAGG",
    "change": "BARLINA",
    "electrical": "EL",
    "dimension": "MATT",
    "default": "TEXT",
    "text": "TEXT",
    "comment": "KOMMENTAR",
}
ents = []
for e in ov5.elements:
    layer = "DETALJ" if e.id in ("DA", "DAT") else LAYER_OF.get(e.category, "0")
    if e.kind == "line":
        ents.append({"t": "line", "l": layer, "p": [mm(e.points[0]), mm(e.points[1])]})
    elif e.kind == "circle":
        ents.append(
            {"t": "circle", "l": layer, "c": mm(e.center), "r": round(e.radius * k / 10) * 10}
        )
    elif e.kind == "text":
        ents.append(
            {
                "t": "text",
                "l": layer,
                "p": mm(e.points[0]),
                "s": "A" if e.id == "DAT" else e.text,
                "h": 200,
            }
        )
for s in ov5.symbols:
    ents.append(
        {
            "t": "insert",
            "l": "PELARE" if s.kind == "column" else "EL",
            "b": "PELARE" if s.kind == "column" else "ELUTTAG",
            "p": mm(s.at),
            "label": s.label,
        }
    )
for d in ov5.dimensions:
    a, b = mm(d.start), mm(d.end)
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy) or 1
    # The renderer's offset is "left of a->b" on screen; y is flipped here.
    nx, ny = -dy / n, dx / n
    off = d.offset * k
    a2 = [a[0] + nx * off, a[1] + ny * off]
    b2 = [b[0] + nx * off, b[1] + ny * off]
    ents.append({"t": "dim", "l": "MATT", "p": [a, b], "q": [a2, b2], "s": d.text})
for an in ov5.annotations:
    if an.status == "open":
        tgt = next((s for s in ov5.symbols if s.id in an.targets), None)
        if tgt:
            ents.append({"t": "circle", "l": "KOMMENTAR", "c": mm(tgt.at), "r": 250})
            ents.append(
                {
                    "t": "text",
                    "l": "KOMMENTAR",
                    "p": [mm(tgt.at)[0] - 1900, mm(tgt.at)[1] - 450],
                    "s": "1: " + an.text,
                    "h": 110,
                }
            )

# DXF R12, written from the same entities.
ACI = {
    "VAGG": 7,
    "BARLINA": 3,
    "EL": 1,
    "MATT": 8,
    "PELARE": 7,
    "DETALJ": 8,
    "TEXT": 7,
    "KOMMENTAR": 6,
}
lines = []


def g(code, val):
    lines.extend([str(code), str(val)])


g(0, "SECTION")
g(2, "TABLES")
g(0, "TABLE")
g(2, "LAYER")
g(70, len(ACI))
for name, col in ACI.items():
    g(0, "LAYER")
    g(2, name)
    g(70, 0)
    g(62, col)
    g(6, "DASHED" if name == "DETALJ" else "CONTINUOUS")
g(0, "ENDTAB")
g(0, "ENDSEC")
g(0, "SECTION")
g(2, "BLOCKS")
g(0, "BLOCK")
g(8, "0")
g(2, "PELARE")
g(70, 0)
g(10, 0)
g(20, 0)
for (x1, y1), (x2, y2) in [
    ((-45, -45), (45, -45)),
    ((45, -45), (45, 45)),
    ((45, 45), (-45, 45)),
    ((-45, 45), (-45, -45)),
    ((-45, -45), (45, 45)),
    ((-45, 45), (45, -45)),
]:
    g(0, "LINE")
    g(8, "0")
    g(10, x1)
    g(20, y1)
    g(11, x2)
    g(21, y2)
g(0, "ENDBLK")
g(8, "0")
g(0, "BLOCK")
g(8, "0")
g(2, "ELUTTAG")
g(70, 0)
g(10, 0)
g(20, 0)
g(0, "CIRCLE")
g(8, "0")
g(10, 0)
g(20, 0)
g(40, 60)
g(0, "ENDBLK")
g(8, "0")
g(0, "ENDSEC")
g(0, "SECTION")
g(2, "ENTITIES")
entity_start = len(lines)
for e in ents:
    if e["t"] == "line":
        (x1, y1), (x2, y2) = e["p"]
        g(0, "LINE")
        g(8, e["l"])
        g(10, x1)
        g(20, y1)
        g(11, x2)
        g(21, y2)
    elif e["t"] == "circle":
        g(0, "CIRCLE")
        g(8, e["l"])
        g(10, e["c"][0])
        g(20, e["c"][1])
        g(40, e["r"])
    elif e["t"] == "text":
        g(0, "TEXT")
        g(8, e["l"])
        g(10, e["p"][0])
        g(20, e["p"][1])
        g(40, e["h"])
        g(1, e["s"])
    elif e["t"] == "insert":
        g(0, "INSERT")
        g(8, e["l"])
        g(2, e["b"])
        g(10, e["p"][0])
        g(20, e["p"][1])
    elif e["t"] == "dim":
        (x1, y1), (x2, y2) = e["q"]
        g(0, "LINE")
        g(8, "MATT")
        g(10, round(x1))
        g(20, round(y1))
        g(11, round(x2))
        g(21, round(y2))
        g(0, "TEXT")
        g(8, "MATT")
        g(10, round((x1 + x2) / 2))
        g(20, round((y1 + y2) / 2) + 60)
        g(40, 120)
        g(1, e["s"])
g(0, "ENDSEC")
g(0, "EOF")
dxf = "\n".join(lines) + "\n"
(here / "altan-r5.dxf").write_text(dxf)
(here / "altan-r5.svg").write_text(svg_text)


data = {
    "ov": both(ov5),
    "svgBytes": len(svg_text.encode()),
    "dxfBytes": len(dxf.encode()),
    "ents": ents,
    "layers": [{"n": n, "c": ACI[n], "count": c} for n, c in Counter(e["l"] for e in ents).items()],
    "dxfSnippet": "\n".join(
        f"{a:>3}  {b}"
        for a, b in zip(lines[entity_start::2][:14], lines[entity_start + 1 :: 2][:14], strict=True)
    ),
    "size_mm": [4800, 3600],
    "pageWidth": RM2.width,
    "grid": 50,
}
json.dump(data, open(out_path, "w"), separators=(",", ":"))
print(data["svgBytes"], data["dxfBytes"], data["layers"])
print([e for e in ents if e["t"] != "text"][:6])
