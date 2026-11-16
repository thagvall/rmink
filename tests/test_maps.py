"""Maps in workbooks: the data, the layout and what stays hidden until the facit."""

import numpy as np
import pymupdf
import pytest

from rmink.devices import get_device
from rmink.workbook import maps
from rmink.workbook.agent import check_workbook
from rmink.workbook.build import FACIT_LAYER, build_pdf, solution_strokes
from rmink.workbook.model import MapFigure

DEVICE = get_device("rm2")


def book(**extra) -> dict:
    field = {"id": "q1", "prompt": "Vad heter landskapet?", "solution": "Dalarna.", "lines": 2}
    return {
        "name": "Karta",
        "layout": 2,
        "sections": [{"id": "s1", "title": "Del ett", "text": "Text.", "fields": [field]}],
        **extra,
    }


def with_figure(figure: dict, **extra) -> dict:
    data = book(**extra)
    data["sections"][0]["fields"][0]["figure"] = figure
    return data


def test_all_25_landskap_in_three_landsdelar():
    m = maps.sverige()
    assert len(m.landskap) == 25
    assert (len(maps.landsdel("Götaland")), len(maps.landsdel("Svealand"))) == (10, 6)
    assert len(maps.landsdel("Norrland")) == 9
    assert maps.expand(["Sverige"]) == maps.names()


def test_every_landskap_is_closed_with_its_anchor_inside():
    for ls in maps.sverige().landskap.values():
        for ring in ls.rings:
            assert np.hypot(*(ring[0] - ring[-1])) < 0.3, ls.name
        assert maps.contains(ls.rings, ls.anchor), ls.name


def test_a_border_is_one_arc_with_two_sides():
    m = maps.sverige()
    assert all(a != b for a, b in m.sides)
    assert sum(1 for a, b in m.sides if a and b) > 40


@pytest.mark.parametrize(
    ("city", "landskap"),
    [
        ("Malmö", "Skåne"), ("Kalmar", "Småland"), ("Visby", "Gotland"), ("Örebro", "Närke"),
        ("Linköping", "Östergötland"), ("Växjö", "Småland"), ("Halmstad", "Halland"),
        ("Västerås", "Västmanland"), ("Karlstad", "Värmland"), ("Falun", "Dalarna"),
        ("Gävle", "Gästrikland"), ("Sundsvall", "Medelpad"), ("Umeå", "Västerbotten"),
        ("Luleå", "Norrbotten"), ("Kiruna", "Lappland"), ("Östersund", "Jämtland"),
        ("Uppsala", "Uppland"), ("Åmål", "Dalsland"), ("Jönköping", "Småland"),
    ],
)  # fmt: skip
def test_cities_lie_in_their_landskap(city, landskap):
    m = maps.sverige()
    x, y = m.city(city)
    near = [(x + dx, y + dy) for dx in (-3, 0, 3) for dy in (-3, 0, 3)]  # towns on a shore
    assert any(maps.contains(m.landskap[landskap].rings, p) for p in near)


def test_neighbours_are_where_the_workbook_says():
    m = maps.sverige()
    centre = {n: np.array(x.anchor) for n, x in m.landskap.items()}
    assert centre["Skåne"][1] < centre["Småland"][1] < centre["Dalarna"][1] < centre["Lappland"][1]
    assert centre["Dalsland"][0] < centre["Närke"][0] < centre["Uppland"][0]


def test_unknown_names_are_refused():
    for figure in ({"highlight": ["Atlantis"]}, {"pins": ["Gotham"]}, {"lakes": ["Loch Ness"]}):
        with pytest.raises(ValueError, match="Okän[dt]"):
            check_workbook(with_figure(figure))


def test_a_workbook_without_maps_keeps_its_layout():
    plain = check_workbook(book())
    assert plain.map_summary is False
    build_pdf(plain, DEVICE)
    assert plain.fields()[0].figure is None
    assert plain.fields()[0].rect[3] > plain.fields()[0].rect[1]


def test_the_map_is_vector_art_on_the_fields_page():
    wb = check_workbook(with_figure({"highlight": ["Dalarna"]}))
    pdf = pymupdf.open(stream=build_pdf(wb, DEVICE))
    f = wb.fields()[0]
    assert f.figure.page == f.page
    assert f.figure.rect[3] <= f.rect[1]  # above the box to write in
    assert len(pdf[f.page].get_drawings()) > 100
    assert not pdf[f.page].get_images()


def test_a_big_map_shrinks_rather_than_leave_a_page_almost_empty():
    wb = check_workbook(with_figure({"height": 470}))
    build_pdf(wb, DEVICE)
    assert wb.fields()[0].page == wb.sections[0].page
    assert wb.fields()[0].figure.rect[3] - wb.fields()[0].figure.rect[1] < 470


def test_a_map_beside_choices_leaves_the_boxes_clear_of_it():
    data = with_figure({"highlight": ["Svealand"], "height": 200})
    field = data["sections"][0]["fields"][0]
    field.update(kind="single", choices=[{"text": "A", "correct": True}, {"text": "B"}])
    wb = check_workbook(data)
    build_pdf(wb, DEVICE)
    f = wb.fields()[0]
    assert all(c.row[2] <= f.figure.rect[0] for c in f.choices)


def test_solution_names_are_hidden_ink():
    wb = check_workbook(with_figure({"view": ["Dalarna"], "solution_labels": ["Dalarna"]}))
    build_pdf(wb, DEVICE)
    strokes = solution_strokes(wb, DEVICE)[wb.fields()[0].page]
    assert strokes and all(s.layer == FACIT_LAYER for s in strokes)
    y0 = wb.fields()[0].figure.rect[1] * DEVICE.dpi / 72
    assert any(s.points[:, 1].max() > y0 for s in strokes)


def test_a_label_in_print_is_not_on_the_facit_layer():
    wb = check_workbook(with_figure({"labels": ["Dalarna"]}))
    pdf = pymupdf.open(stream=build_pdf(wb, DEVICE))
    assert "Dalarna" in pdf[wb.fields()[0].page].get_text()


def test_summary_page_prints_the_outline_and_inks_every_landskap():
    wb = check_workbook(book(map_summary=True))
    pdf = pymupdf.open(stream=build_pdf(wb, DEVICE))
    page = pdf[wb.map_page]
    assert "Sverigekartan" in page.get_text()
    assert not any(name in page.get_text() for name in ("Dalarna", "Skåne"))
    ink = solution_strokes(wb, DEVICE)[wb.map_page]
    assert len(ink) > 25 * 3
    assert all(s.layer == FACIT_LAYER for s in ink)
    assert "Sverigekartan" in [t[1] for t in pdf.get_toc()]


def test_summary_facit_waits_for_the_marking_in_a_test():
    wb = check_workbook(book(map_summary=True, mode="test"))
    pdf = pymupdf.open(stream=build_pdf(wb, DEVICE))
    assert wb.map_page not in solution_strokes(wb, DEVICE)
    assert "efter rättningen" in pdf[wb.map_page].get_text()
    wb.fields()[0].verdict = "correct"
    build_pdf(wb, DEVICE)
    assert wb.map_page in solution_strokes(wb, DEVICE)


def test_labels_stay_on_the_page_and_columns_do_not_overlap():
    fig = MapFigure()
    box = (22.0, 80.0, 425.0, 570.0)
    labels = maps.place_labels(
        maps.names(), maps.view_of(fig, box), box, lambda t: 6.0 * len(t), 11
    )
    assert len(labels) == 25
    for lab in labels:
        assert box[0] - 1 <= lab.at[0] <= box[2] and box[1] - 1 <= lab.at[1] <= box[3] + 4
    west = sorted(lab.at[1] for lab in labels if lab.leader and lab.at[0] <= box[0] + 1)
    assert all(b - a >= 10.9 for a, b in zip(west, west[1:], strict=False))


def test_filled_areas_stop_at_the_frame_of_a_zoomed_map():
    box = (20.0, 100.0, 380.0, 300.0)
    fig = MapFigure(view=["Skåne", "Halland", "Bohuslän"], highlight=["Västergötland"])
    view = maps.view_of(fig, box)
    lakes = maps.lake_paths(fig, view, box)
    assert lakes, "Vänern reaches into this frame"
    for p in lakes:
        assert p[:, 1].min() >= 100 - 1e-6 and p[:, 1].max() <= 300 + 1e-6
    square = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], float)
    corners = maps.clipped_area(square, (5, 5, 20, 20)).tolist()
    assert sorted(corners) == [[5, 5], [5, 10], [10, 5], [10, 10]]
    assert len(maps.clipped_area(square, (50, 50, 60, 60))) == 0


def test_a_tall_map_leaves_the_choices_room_for_their_words():
    data = book()
    data["sections"][0]["fields"] = [{
        "id": "q1", "prompt": "Vilket?", "kind": "single", "solution": "Dalarna.",
        "choices": [{"text": "Dalarna", "correct": True}, {"text": "Västmanland"}],
        "figure": {"height": 340},
    }]  # fmt: skip
    wb = check_workbook(data)
    build_pdf(wb, DEVICE)
    field = wb.fields()[0]
    assert field.figure.rect[0] - field.choices[0].rect[0] >= 175
