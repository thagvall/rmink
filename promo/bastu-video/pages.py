"""Build the Bastu drawing r01-r03 with rmink's own renderer and save the pages
as the tablet shows them. The drawing is a made-up example, written the way
Claude writes one from a sketch; nothing is sent or saved to the drawings folder.

Usage: python promo/bastu-video/pages.py OUT_DIR
Writes OUT_DIR/r0N-p0P.png and pages.json (what each round says).
"""

import importlib.util
import json
import sys
from pathlib import Path

from rmink.drawing.model import Annotation, Dimension, Drawing, Element, Symbol
from rmink.drawing.store import MemoryStore
from rmink.drawing.workflow import build_revision

HERE = Path(__file__).resolve().parent


X0, Y0, X1, Y1 = 300, 420, 1100, 953  # 3600 x 2400 mm
WALL = 567  # the wall between the changing room and the sauna, 1200 mm in
D0, D1 = 600, 756  # the sauna door, 700 mm
E0, E1 = 620, 798  # the outer door, 800 mm


def base(r: int, date: str, kamin: str) -> Drawing:
    wall = {"category": "structure"}
    return Drawing(
        name="Bastu", area="Bygg", revision=r, date=date,
        elements=[
            Element(id="v1", kind="polyline", points=[(X0, E0), (X0, Y0), (X1, Y0), (X1, Y1), (X0, Y1), (X0, E1)], **wall),
            Element(id="v2", kind="line", points=[(WALL, Y0), (WALL, D0)], **wall),
            Element(id="v3", kind="line", points=[(WALL, D1), (WALL, Y1)], **wall),
            Element(id="kamin", kind="rect", points=[(600, 450), (700, 550)]),
            Element(id="lave", kind="rect", points=[(960, 420), (1100, 953)], category="hidden"),
            Element(id="t1", kind="text", points=[(740, 700)], text="BASTU", size=34, category="text"),
            Element(id="t2", kind="text", points=[(322, 520)], text="OMKL.", size=30, category="text"),
            Element(id="t3", kind="text", points=[(975, 700)], text="LAVE", size=24, category="text"),
            Element(id="t4", kind="text", points=[(600, 590)], text=kamin, size=22, category="text"),
        ],
        dimensions=[
            Dimension(id="m1", start=(X0, Y0), end=(X1, Y0), text="3600", value=3600),
            Dimension(id="m2", start=(X1, Y0), end=(X1, Y1), text="2400", value=2400),
        ],
        symbols=[
            Symbol(id="d1", kind="door", at=(WALL + 78, 678), size=156, rotation=90),
            Symbol(id="d2", kind="door", at=(X0 - 89, (E0 + E1) / 2), size=178, rotation=-90),
            Symbol(id="f1", kind="window", at=(830, Y0), size=180),
        ],
    )


def r01() -> Drawing:
    d = base(1, "2026-11-07", "KAMIN")
    d.annotations = [
        Annotation(id="a1", kind="circle", targets=["kamin"], text="KAMINEN: VED ELLER EL?"),
        Annotation(id="a2", kind="note", targets=["v1"], text="HUR LÅNGT ÄR DET TILL TOMTGRÄNSEN? (MINST 4,5 m, PBL 9 KAP.)"),
    ]
    d.log = ["R1: BASTU 3600 × 2400 mm RITAD FRÅN SKISSEN."]
    return d


def r02() -> Drawing:
    d = base(2, "2026-11-07", "VEDKAMIN")
    d.annotations = [
        Annotation(id="a1", kind="circle", targets=["kamin"], status="accepted", text="VED"),
        Annotation(id="a2", kind="note", targets=["v1"], status="accepted", text="12 m"),
    ]
    d.log = [
        "R1: BASTU 3600 × 2400 mm RITAD FRÅN SKISSEN.",
        "R2: VEDKAMIN VALD. NY ELDSTAD KRÄVER ANMÄLAN (PBF 6 KAP. 1 §).",
        "R2: 12 m TILL TOMTGRÄNSEN (MINST 4,5 m UPPFYLLT).",
    ]
    return d


def r03() -> Drawing:
    d = r02()
    d.revision, d.date = 3, "2026-11-21"
    door = next(s for s in d.symbols if s.id == "d1")
    door.at, door.rotation = (WALL - 78, 678), -90
    d.log.append("R3: BASTUDÖRREN ÖPPNAR UTÅT, MOT OMKLÄDNINGSRUMMET.")
    return d


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location("bygg_pages", HERE.parent / "bygg-video" / "pages.py")
    bygg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bygg)
    docs, facts = [], {}
    for name, d in (("r01", r01()), ("r02", r02()), ("r03", r03())):
        rev = build_revision(d, out / f"{name}.rmdoc", seed=d.revision, store=MemoryStore())
        docs.append(f"{name}={out / (name + '.rmdoc')}")
        facts[name] = {"remarks_page": rev.drawing.sketch.remarks_page, "door": rev.drawing.find("d1").at}
    bygg.main(out, docs)
    (out / "pages.json").write_text(json.dumps(facts, indent=1))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
