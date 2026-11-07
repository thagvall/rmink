"""Quantities with the pen: lengths and counts from ink on a sheet with a scale."""

from __future__ import annotations

import csv
import io
import json

import numpy as np
import pymupdf
import pytest
from test_bridge import RM2, notebook, sheet_bytes
from test_drawing_pdf import plan
from test_points import line, ring, word

from rmink.bridge.drawing_pdf import _viewport, drawing_pdf
from rmink.bridge.sheet import build_pack
from rmink.bridge.takeoff import (
    find_quantities,
    page_scale,
    quantities_csv,
    read_marks,
    write_quantities,
)
from rmink.drawing.model import Symbol
from rmink.model import Stroke

PX = RM2.px_per_mm
TABLET_PX = 72 / RM2.dpi  # pt per tablet px


def cross(cx: float, cy: float, half: float = 4.0) -> list[Stroke]:
    """Two strokes crossing at (cx, cy), in mm on the tablet."""
    return [
        line(cx - half, cy - half, cx + half, cy + half),
        line(cx - half, cy + half, cx + half, cy - half),
    ]


def scaled(n: int = 50, size=(400, 500), rotation: int = 0) -> bytes:
    doc = pymupdf.open(stream=sheet_bytes(size=size), filetype="pdf")
    _viewport(doc, doc[0], n)
    if rotation:
        doc[0].set_rotation(rotation)
    return doc.tobytes()


def on_sheet(pack, tablet_mm: float) -> float:
    """Sheet mm for a horizontal stroke this long on the first tablet page."""
    tile = pack.manifest.tiles[0]
    x0, y0 = tile.to_sheet(0, 0)
    x1, y1 = tile.to_sheet(tablet_mm * PX * TABLET_PX, 0)
    return float(np.hypot(x1 - x0, y1 - y0)) * 25.4 / 72


def kinds(strokes: list[Stroke]) -> list[str]:
    marks, _, _ = read_marks(strokes, RM2)
    return sorted(m[0] for m in marks)


def test_a_straight_stroke_a_cross_and_a_ring_are_read():
    strokes = [line(10, 10, 110, 10), *cross(40, 60), ring(80, 60, 3)]
    assert kinds(strokes) == ["cross", "line", "ring"]


def test_a_cross_with_a_hook_where_the_pen_lifted_is_a_cross():
    n = 20
    t = np.linspace(-4, 4, n)
    hooked = np.c_[40 + t, 60 + t]
    hooked[-3:] = [[44.5, 63.0], [45.2, 61.0], [45.5, 59.0]]  # the tail curls up 5 mm
    strokes = [Stroke(hooked * PX, width=2), line(36, 64, 44, 56)]
    assert kinds(strokes) == ["cross"]


def test_writing_is_left_alone():
    # An x inside a word and an o after it are letters, not marks.
    strokes = [*word(10, 10), *cross(27, 12.5, 2.5), *word(31, 10), ring(48, 12.5, 2.5)]
    marks, ignored, _ = read_marks(strokes, RM2)
    assert marks == []
    assert ignored == len(strokes)


def test_a_line_under_writing_is_an_underline():
    strokes = [*word(10, 10, 4), line(9, 16.5, 30, 16.5)]
    marks, _, underlines = read_marks(strokes, RM2)
    assert marks == [] and underlines == 1


def test_a_long_bent_stroke_is_no_length():
    t = np.linspace(0, np.pi, 30)
    arc = Stroke(np.c_[60 + 40 * np.cos(t), 60 + 40 * np.sin(t)] * PX, width=2)
    assert kinds([arc]) == []


def test_the_scale_comes_from_the_viewport():
    doc = pymupdf.open(stream=scaled(25), filetype="pdf")
    s = page_scale(doc, doc[0])
    assert s.ratio == "1:25" and s.unit == "mm"
    assert s.per_unit == pytest.approx(25 * 25.4 / 72, rel=1e-5)
    plain = pymupdf.open(stream=sheet_bytes(), filetype="pdf")
    assert page_scale(plain, plain[0]) is None


@pytest.mark.parametrize("rotation", [0, 90])
def test_a_length_is_its_real_size_at_the_scale(rotation):
    source = scaled(50, rotation=rotation)
    pack = build_pack(source, RM2, "Plan", "s")
    book = notebook(pack, {0: [line(20, 30, 120, 30)]})
    takeoff = find_quantities(book, source)
    (q,) = takeoff.quantities
    assert (q.kind, q.group, q.unit) == ("length", "Linje", "mm")
    assert q.value == pytest.approx(on_sheet(pack, 100) * 50, rel=0.01)
    assert takeoff.scales == {0: "1:50"}


def test_a_sheet_without_a_scale_needs_one():
    source = sheet_bytes(size=(400, 500))
    book = notebook(build_pack(source, RM2, "Plan", "s"), {0: [line(20, 30, 120, 30)]})
    assert find_quantities(book, source).unscaled == 1
    (q,) = find_quantities(book, source, scale=20).quantities
    assert q.value == pytest.approx(
        on_sheet(build_pack(source, RM2, "Plan", "s"), 100) * 20, rel=0.01
    )


def written(strokes: list[Stroke], n: int = 50):
    source = scaled(n)
    book = notebook(build_pack(source, RM2, "Plan", "abc"), {0: strokes})
    takeoff = find_quantities(book, source)
    return source, takeoff, write_quantities(source, takeoff)


def test_quantities_become_measurements_and_counts():
    _, takeoff, (pdf, added, skipped) = written(
        [line(20, 20, 120, 20), *cross(40, 80), *cross(70, 80), ring(100, 80, 3)]
    )
    assert (added, skipped) == (4, 0)
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    page = doc[0]
    annots = list(page.annots())
    (length,) = [a for a in annots if a.type[1] == "Line"]
    assert doc.xref_get_key(length.xref, "IT")[1] == "/LineDimension"
    assert doc.xref_get_key(length.xref, "OPS_Subtype")[1] == "measureDistance"
    assert "/Subtype/RL" in doc.xref_get_key(length.xref, "Measure")[1].replace(" ", "")
    assert length.info["content"].endswith(" mm")
    assert length.info["id"].startswith("rmink-qty-abc:0:")
    counts = [a for a in annots if a.type[1] == "Circle"]
    groups = [doc.xref_get_key(a.xref, "OPS_CountCategoryName")[1] for a in counts]
    numbers = [doc.xref_get_key(a.xref, "OPS_CountNumber")[1] for a in counts]
    assert sorted(groups) == ["Kryss", "Kryss", "Ring"]
    assert sorted(numbers) == ["1", "1", "2"]
    assert all(doc.xref_get_key(a.xref, "OPS_Subtype")[1] == "count" for a in counts)
    assert "Mängder Plan" in {o["name"] for o in doc.get_ocgs().values()}


def test_writing_quantities_twice_adds_nothing():
    _, takeoff, (pdf, *_) = written([line(20, 20, 120, 20), *cross(40, 80)])
    again, added, skipped = write_quantities(pdf, takeoff)
    assert (added, skipped) == (0, 2)


def test_the_list_has_every_quantity_and_the_sums():
    _, takeoff, _ = written([line(20, 20, 120, 20), line(20, 40, 70, 40), *cross(40, 80)])
    rows = list(csv.reader(io.StringIO(quantities_csv(takeoff).lstrip("﻿")), delimiter=";"))
    assert rows[0] == ["Nr", "Typ", "Grupp", "Blad", "Värde", "Enhet"]
    sums = rows[rows.index(["Summa", "Typ", "Grupp", "Antal", "Summa", "Enhet"]) + 1 :]
    assert sums[0][:4] == ["", "Längd", "Linje", "2"]
    total = sum(q.value for q in takeoff.quantities if q.kind == "length")
    assert sums[0][4] == f"{total / 1000:.2f}".replace(".", ",") and sums[0][5] == "m"
    assert rows[1][4] == f"{takeoff.quantities[0].value:.0f}"
    assert sums[1] == ["", "Antal", "Kryss", "1", "1", "st"]


def test_on_a_drawing_a_wall_and_a_symbol_are_named():
    d = plan(symbols=[Symbol(id="s1", kind="column", at=(700, 300), size=40)])
    source = drawing_pdf(d, "a3").pdf
    doc = pymupdf.open(stream=source, filetype="pdf")
    place = json.loads(doc.embfile_get("rmink.placement.json"))
    k, (ox, oy) = place["pt_per_px"], place["origin"]
    pack = build_pack(source, RM2, "Garage", "g")
    strokes: dict[int, list[Stroke]] = {}

    def draw(points: list[tuple[float, float]], make) -> None:
        """``make`` given tablet mm for ``points``, drawing px, on a tile holding them all."""
        sheet = [(x * k + ox, y * k + oy) for x, y in points]
        for tile in pack.manifest.tiles:
            if tile.tablet_page == 0:
                continue
            mm = [np.array(tile.to_tablet(*p)) / TABLET_PX / PX for p in sheet]
            if all(5 < x < 150 and 5 < y < 200 for x, y in mm):
                strokes.setdefault(tile.tablet_page, []).extend(make(*mm))
                return
        raise AssertionError("no tile holds the points")

    # 6 px (30 mm) beside the top wall: 1.2 mm on the sheet at 1:25.
    draw([(600, 106), (900, 106)], lambda a, b: [line(*a, *b)])  # along the top wall
    draw([(700, 300)], lambda c: cross(*c))  # on the column
    draw([(600, 600), (900, 600)], lambda a, b: [line(*a, *b)])  # across the floor
    takeoff = find_quantities(notebook(pack, strokes), source)
    found = sorted((q.kind, q.group) for q in takeoff.quantities)
    assert found == [("count", "Pelare"), ("length", "Bärande"), ("length", "Linje")]
    wall = next(q for q in takeoff.quantities if q.group == "Bärande")
    assert wall.value == pytest.approx(1500, rel=0.01)  # 300 px at 5 mm per px
