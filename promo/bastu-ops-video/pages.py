"""Put the Bastu drawing r10 on a true-scale sheet, as `rmink sheet drawing` does,
and save it as a PDF and as a picture.

The drawing is the user's real sauna (rmink/Bygg/Bastu on the tablet, r00-r10).
Its JSON lives in the browser's /rounds storage, not on disk, so r10 is written
out again here from the r10 page: same geometry (px of that page), texts and log.

Usage: python promo/bastu-ops-video/pages.py OUT_DIR [SKETCH.rmdoc]
Writes OUT_DIR/Bastu r10.pdf, sheet.png (150 dpi) and sheet.json (scale, layers).
With the hand sketch (Bastu r00 skiss, downloaded from the tablet) it also
writes OUT_DIR/sketch-ink.json: every stroke as an SVG path in page px, in the
order written, so the video can draw the sketch again.
"""

import importlib.util

import json
import sys
from pathlib import Path

import pymupdf

from rmink.bridge.drawing_pdf import drawing_pdf
from rmink.drawing.model import Dimension, Drawing, Element, Symbol

X0, Y0, X1, Y1 = 267, 188, 1072, 725  # 3000 x 2000 mm
PX = (X1 - X0) / 3000  # px per mm


def text(i: int, at: tuple[float, float], s: str, size: float = 22) -> Element:
    return Element(id=f"t{i}", kind="text", points=[at], text=s, size=size, category="text")


def r10() -> Drawing:
    labels = [
        ((1092, 215), "ÖVRE LAVE"), ((1092, 333), "UNDRE LAVE"), ((1092, 502), "LAMPA"),
        ((293, 485), "F 15X10", 20), ((495, 615), "A"), ((953, 648), "G 7X20", 20),
        ((948, 790), "GLASDÖRR 7X20,"), ((948, 825), "HÄRDAT GLAS"), ((425, 920), "AGGREGAT (EL-BASTU)"),
        ((230, 1105), "TRÄHUS - TRÄLASUR"), ((230, 1145), "TAKHÖJD 2,5 m"),
        ((230, 1185), "A = EL-BASTU (AGGREGAT)"), ((230, 1225), "FÖNSTER F 1,5 X 1,0 m, MITT PÅ GAVELN"),
    ]  # fmt: skip
    door = 700 * PX
    return Drawing(
        name="Bastu", area="Bygg", revision=10, date="2026-11-07",
        elements=[
            Element(id="v1", kind="polyline", points=[(X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1)], closed=True, category="structure"),
            Element(id="l1", kind="line", points=[(X0, 312), (X1, 312)]),
            Element(id="l2", kind="line", points=[(X0, 423), (X1, 423)]),
            Element(id="agg", kind="rect", points=[(451, 588), (572, 693)]),
            Element(id="led", kind="line", points=[(512, 693), (512, 885)]),
            # The side window, 1500 mm in the middle of the gable: two lines, as on the page
            *[Element(id=f"f{i}", kind="line", points=[(x, 255), (x, 657)]) for i, x in enumerate((258, 276))],
            *[text(i, *label) for i, label in enumerate(labels)],
        ],
        dimensions=[
            Dimension(id="m1", start=(X0, Y0), end=(X1, Y0), text="3000", value=3000),
            Dimension(id="m2", start=(X0, Y1), end=(X0, Y0), text="2000", value=2000, offset=90),
        ],
        symbols=[
            Symbol(id="g", kind="door", at=(727 + door / 2, Y1), size=door, rotation=0),
            Symbol(id="lampa", kind="light", at=(1029, 527), size=34),
            Symbol(id="fl", kind="exhaust_air", at=(308, 632), size=38, label="FL"),
            Symbol(id="tl", kind="supply_air", at=(512, 663), size=28, label="TL"),
        ],
        log=[
            "R7: GLASDÖRR RITAD 7X19 (700 X 1900 mm) (SVAR 2).",
            "R9: GLASDÖRR ÄNDRAD TILL 7X20 (700 X 2000 mm) I TEXT, SYMBOL OCH FÖRKLARING (SVAR 1).",
            "R10: OMRITAD, INGEN ÄNDRING I INNEHÅLLET",
        ],
    )


def sketch(out: Path, notebook: Path) -> None:
    import zipfile

    spec = importlib.util.spec_from_file_location("bygg_pages", Path(__file__).resolve().parent.parent / "bygg-video" / "pages.py")
    bygg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bygg)
    z = zipfile.ZipFile(notebook)
    rm = next(n for n in z.namelist() if n.endswith(".rm"))
    s, half = bygg.DEVICE.ink_scale, bygg.DEVICE.width / 2
    strokes = sorted(bygg.lines(z.read(rm)), key=lambda la: la[0].points and 0)  # file order is the order written
    paths = [{"d": "M" + " L".join(f"{pt.x / s + half:.1f} {pt.y / s:.1f}" for pt in ln.points),
              "w": round(max(ln.points[0].width / 4 / s, 2.5), 1)} for ln, _ in strokes if len(ln.points) > 1]  # fmt: skip
    (out / "sketch-ink.json").write_text(json.dumps(paths))
    print(len(paths), "sketch strokes")


def main(out: Path, notebook: Path | None = None) -> None:
    out.mkdir(parents=True, exist_ok=True)
    if notebook:
        sketch(out, notebook)
    sheet = drawing_pdf(r10(), paper="a3")
    (out / "Bastu r10.pdf").write_bytes(sheet.pdf)
    doc = pymupdf.open(stream=sheet.pdf, filetype="pdf")
    doc[0].get_pixmap(dpi=150).save(out / "sheet.png")
    facts = {"scale": sheet.scale, "paper": sheet.paper, "layers": [v["name"] for v in doc.get_ocgs().values()],
             "warnings": sheet.warnings}  # fmt: skip
    (out / "sheet.json").write_text(json.dumps(facts, indent=1, ensure_ascii=False))
    print(facts)


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
