"""The calculator rounds and Claude use, and angles on drawings."""

import math

import numpy as np
import pytest

from rmink.calc import CalcError, evaluate, format_angle
from rmink.devices import get_device
from rmink.drawing import workflow
from rmink.drawing.model import AngleDimension, Dimension, Drawing, Element
from rmink.drawing.render import render_drawing


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("2 + 3 * 4", 14),
        ("hypot(3600, 1200)", 3794.733192),
        ("leg(5, 3)", 4.0),
        ("sin(30)", 0.5),
        ("atan(1200 / 3600)", 18.434949),
        ("atan2(1, 1)", 45.0),
        ("3600 / cos(45)", 5091.168825),
        ("round(sqrt(2), 3)", 1.414),
        ("area([(0, 0), (4, 0), (4, 3), (0, 3)])", 12.0),
        ("circle(2)", math.pi),
        ("count(4800, 600)", 9),
        ("count(4700, 600)", 8),
        ("pieces(23.5, 4.8)", 5),
        ("waste(42, 10)", 46.2),
        ("weight(1, 'betong')", 2400),
        ("weight(0.045 * 0.195 * 4.8, 'C24')", 17.6904),
        ("{'A1', 'A2'} | {'A2', 'A3'}", ["A1", "A2", "A3"]),
        ("len({1, 2, 3} & {2, 3, 4})", 2),
        ("{1, 2} - {2}", [1]),
        ("'A2' in {'A1', 'A2'}", True),
        ("triangle(3, 4, 5)['C']", 90.0),
    ],
)
def test_evaluate(expression, expected):
    assert evaluate(expression) == pytest.approx(expected)


def test_slope_and_pitch_agree():
    s = evaluate("slope(1200, 3600)")
    assert s["deg"] == pytest.approx(18.434949) and s["ratio"] == "1:3"
    assert s["percent"] == pytest.approx(33.333333)
    assert evaluate("pitch(45)")["ratio"] == "1:1"
    t = evaluate("triangle(3, 4, 5)")
    assert t["A"] + t["B"] + t["C"] == pytest.approx(180) and t["area"] == 6


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os')",
        "(1).real",
        "open('x')",
        "x + 1",
        "9 ** 999",
        "'a' * 10 ** 9",
        "1 / 0",
        "leg(3, 5)",
        "triangle(1, 2, 10)",
        "weight(1, 'okänt-material')",
        "lambda: 1",
        "[x for x in (1, 2)]",
        "1 +",
        "9" * 1001,
    ],
)
def test_evaluate_refuses(expression):
    with pytest.raises(CalcError):
        evaluate(expression)


def test_calculation_texts_have_glyphs():
    from rmink.drawing.font import _PARSED, _letters

    drawn = set(_letters("√(3600² + 1800²) ≈ 4025 mm, 26,6° (1:2)")) - {" "}
    assert drawn <= set(_PARSED), sorted(drawn - set(_PARSED))


def test_format_angle():
    assert format_angle(38.66) == "38,7°"
    assert format_angle(90.0) == "90°"
    assert format_angle(18.4349) == "18,4°"


def _roof():
    # A 3600 wide, 1200 high gable drawn at 0,25 mm/px: rise over half the span.
    return Drawing(
        name="Tak",
        elements=[
            Element(id="L1", kind="line", points=[(100, 900), (820, 660)]),
            Element(id="L2", kind="line", points=[(820, 660), (1540, 900)]),
            Element(id="B", kind="line", points=[(100, 900), (1540, 900)]),
        ],
        dimensions=[Dimension(id="M1", start=(100, 900), end=(1540, 900), text="5760")],
    )


def test_measure_reads_lengths_and_angles_from_the_drawing():
    m = workflow.measure(_roof(), ["L1", "B"])
    assert m["unit"] == "mm" and m["scale_units_per_px"] == 4.0
    assert m["items"][1]["length"] == 5760.0
    assert m["angle"]["shared"] and m["angle"]["deg"] == pytest.approx(18.43, abs=0.01)
    assert m["angle"]["vertex"] == [100.0, 900.0]
    m = workflow.measure(_roof(), ["L1", "L2"])
    assert m["angle"]["deg"] == pytest.approx(180 - 2 * 18.43, abs=0.02)
    rect = Drawing(
        name="Altan",
        elements=[Element(id="A", kind="rect", points=[(0, 0), (1200, 750)])],
        dimensions=[Dimension(id="M", start=(0, 0), end=(1200, 0), text="4800")],
    )
    (item,) = workflow.measure(rect, ["A"])["items"]
    assert item["area"] == pytest.approx(4800 * 3000)  # mm², 14,4 m²
    assert [c["deg"] for c in item["corners"]] == [90, 90, 90, 90]
    assert workflow.measure(rect, ["nope"])["items"][0]["error"]


def test_angles_are_drawn_and_checked():
    d = _roof()
    d.angles = [
        AngleDimension(id="V1", vertex=(100, 900), start=(1540, 900), end=(820, 660)),
        AngleDimension(id="V2", vertex=(1540, 900), start=(100, 900), end=(820, 660), text="27°"),
    ]
    assert d.angles[0].measured() == pytest.approx(18.43, abs=0.01)
    plain = render_drawing(_roof(), get_device("rm2"))
    page = render_drawing(d, get_device("rm2"))
    # each angle adds an arc, two arrowheads and its degrees
    assert len(page.strokes) > len(plain.strokes) + 6
    check = workflow.check_dimensions(d)["angles"]
    assert check[0]["drawn_deg"] == pytest.approx(18.4) and "consistent" not in check[0]
    assert check[1]["value"] == 27 and check[1]["consistent"] is False
    assert d.find("V2") is d.angles[1]


def test_rectify_keeps_angles_on_their_corners():
    d = Drawing(
        name="x",
        elements=[
            Element(id="a", kind="line", points=[(100, 100), (500, 103)]),
            Element(id="b", kind="line", points=[(102, 98), (100, 400)]),
        ],
        angles=[AngleDimension(id="v", vertex=(101, 99), start=(500, 103), end=(100, 400))],
    )
    r = workflow.rectify(d)
    corner = r.elements[0].points[0]
    assert r.angles[0].vertex == corner and r.angles[0].start == r.elements[0].points[1]
    assert r.angles[0].measured() == pytest.approx(90)


def test_angle_degrees_avoid_a_line_along_the_bisector():
    from rmink.drawing.font import text_paths

    # ridge of a gable with a king post straight down the bisector
    d = Drawing(
        name="Takstol",
        elements=[
            Element(id="L1", kind="line", points=[(100, 1000), (700, 700)]),
            Element(id="L2", kind="line", points=[(700, 700), (1300, 1000)]),
            Element(id="P", kind="line", points=[(700, 700), (700, 1000)]),
        ],
        angles=[AngleDimension(id="V", vertex=(700, 700), start=(100, 1000), end=(1300, 1000))],
    )
    page = render_drawing(d, get_device("rm2"))
    n = len(text_paths("126,9°", (0, 0), 22.0))
    # three lines, then the arc and its two arrowheads, then the degrees
    label = np.vstack([s.points for s in page.strokes[6 : 6 + n]])
    xs = label[:, 0]
    assert xs.max() < 696 or xs.min() > 704, (xs.min(), xs.max())


@pytest.mark.parametrize(
    "text, unit, expected",
    [
        ("4800", "mm", "4800 mm"),
        ("≈4025", "mm", "≈4025 mm"),
        ("2,1", "m", "2,1 m"),
        ("2,1 m", "m", "2,1 m"),
        ("45°", "mm", "45°"),
        ("c600", "mm", "c600"),
        ("4800", "", "4800"),
    ],
)
def test_dimensions_say_their_unit(text, unit, expected):
    from rmink.drawing.render import dimension_label

    dim = Dimension(id="d", start=(0, 0), end=(100, 0), text=text, unit=unit)
    assert dimension_label(dim) == expected
    assert dimension_label(dim, show_unit=False) == text


def test_title_block_says_the_unit():
    from rmink.drawing.font import _letters

    plain = render_drawing(Drawing(name="x"), get_device("rm2"))
    page = render_drawing(_roof(), get_device("rm2"))
    without = render_drawing(_roof().model_copy(update={"show_units": False}), get_device("rm2"))
    # "4800 mm" on the dimension and "Mått i mm" in the title block
    assert len(page.strokes) > len(without.strokes) > len(plain.strokes)
    assert _letters("Mått i mm") == "MÅTT I mm"
