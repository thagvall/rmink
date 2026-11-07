"""A clean drawing on a PDF sheet at a true scale."""

from __future__ import annotations

import json

import pymupdf
import pytest

from rmink.bridge.drawing_pdf import PT_PER_MM, choose_sheet, drawing_pdf
from rmink.drawing.model import (
    Alternatives,
    Annotation,
    Dimension,
    Drawing,
    Element,
    Option,
    OptionLayer,
    Symbol,
)


def plan(**kw) -> Drawing:
    """A 6 x 4.5 m room, drawn at 5 mm per px."""
    d = Drawing(
        name="Garage",
        revision=3,
        elements=[
            Element(id="v1", kind="rect", points=[(100, 100), (1300, 1000)], category="structure"),
            Element(id="t", kind="text", points=[(500, 500)], text="GARAGE", category="text"),
        ],
        dimensions=[
            Dimension(id="d1", start=(100, 100), end=(1300, 100), text="6000", value=6000),
            Dimension(id="d2", start=(100, 100), end=(100, 1000), text="4500", value=4500),
        ],
        **kw,
    )
    return d


def key(doc, page, name):
    return doc.xref_get_key(page.xref, name)


def test_it_picks_the_largest_standard_scale_that_fits():
    assert choose_sheet(6000, 4500, "a3")[2] == 20
    assert choose_sheet(6000, 4500, "a4")[2] == 50
    assert choose_sheet(60000, 40000, "a3")[2] == 200


def test_it_turns_the_paper_to_fit():
    w, h, _ = choose_sheet(2000, 11000, "a4", 50)
    assert w < h


def test_a_scale_that_does_not_fit_is_refused():
    with pytest.raises(ValueError, match="does not fit"):
        choose_sheet(60000, 40000, "a4", 20)


def test_an_unknown_paper_is_refused():
    with pytest.raises(ValueError, match="Unknown paper"):
        choose_sheet(1, 1, "b5")


def test_a_wall_measures_its_real_length_with_the_stored_scale():
    sheet = drawing_pdf(plan(), "a3")
    doc = pymupdf.open(stream=sheet.pdf, filetype="pdf")
    page = doc[0]
    vp = key(doc, page, "VP")
    assert vp[0] == "array"
    assert "/Subtype/RL" in vp[1].replace(" ", "") or "/Subtype /RL" in vp[1]
    per_point = float(vp[1].split("/C ")[1].split("/")[0].split()[0])
    wide = max(
        (r for r in (d["rect"] for d in page.get_drawings()) if r.width < page.rect.width * 0.9),
        key=lambda r: r.width,
    )
    assert wide.width * per_point == pytest.approx(6000, rel=0.02)
    assert per_point == pytest.approx(sheet.scale / PT_PER_MM)


def test_categories_become_layers():
    doc = pymupdf.open(stream=drawing_pdf(plan()).pdf, filetype="pdf")
    names = {o["name"] for o in doc.get_ocgs().values()}
    assert {"Barande", "Text", "Matt", "Ritningshuvud"} <= names


def test_text_stays_text():
    page = pymupdf.open(stream=drawing_pdf(plan()).pdf, filetype="pdf")[0]
    words = page.get_text()
    assert "GARAGE" in words
    assert "1:25" in words
    assert "härledd" in words


def test_characters_the_font_lacks_keep_their_meaning():
    d = plan()
    d.elements.append(
        Element(id="m", kind="text", points=[(300, 700)], text="Makadam 16–32", category="text")
    )
    words = pymupdf.open(stream=drawing_pdf(d).pdf, filetype="pdf")[0].get_text()
    assert "MAKADAM 16-32" in words


def test_a_comment_icon_stays_off_what_it_marks():
    ann = [
        Annotation(id="a1", kind="note", targets=["t"], text="Ett"),
        Annotation(id="a2", kind="note", targets=["t"], text="Två"),
    ]
    page = pymupdf.open(stream=drawing_pdf(plan(annotations=ann)).pdf, filetype="pdf")[0]
    text = page.search_for("GARAGE")[0]
    icons = [a.rect for a in page.annots() if a.type[1] == "Text" and a.info.get("id")]
    assert all((r & text).is_empty for r in icons)
    assert (icons[0] & icons[1]).is_empty


def test_rotated_dimension_text_stays_on_the_sheet():
    doc = pymupdf.open(stream=drawing_pdf(plan()).pdf, filetype="pdf")
    page = doc[0]
    rects = page.search_for("4500")
    assert rects and page.rect.contains(rects[0])


def test_no_written_measurements_is_refused():
    d = plan()
    d.dimensions = []
    with pytest.raises(ValueError, match="no written measurements"):
        drawing_pdf(d)


def test_a_dimension_that_disagrees_shows_on_the_sheet():
    d = plan()
    d.dimensions.append(
        Dimension(id="d3", start=(100, 300), end=(700, 300), text="1000", value=1000)
    )
    sheet = drawing_pdf(d)
    assert sheet.warnings and "1000" in sheet.warnings[0]
    assert "OBS" in pymupdf.open(stream=sheet.pdf, filetype="pdf")[0].get_text()


def test_remarks_become_comments_and_keep_their_status():
    ann = [
        Annotation(id="a1", kind="note", targets=["v1"], text="Kolla fall"),
        Annotation(id="a2", kind="note", targets=["v1"], text="Klart", status="accepted"),
    ]
    doc = pymupdf.open(stream=drawing_pdf(plan(annotations=ann)).pdf, filetype="pdf")
    page = doc[0]
    texts = [a.info["content"] for a in page.annots() if a.info.get("id", "").startswith("rmink-")]
    assert "1. Kolla fall" in texts
    states = [
        doc.xref_get_key(a.xref, "State")[1]
        for a in page.annots()
        if doc.xref_get_key(a.xref, "State")[0] != "null"
    ]
    assert states == ["Accepted"]


def choice(chosen: str = "") -> Alternatives:
    def option(key: str, title: str, mm: float) -> Option:
        return Option(
            key=key,
            title=title,
            layers=[OptionLayer(text=f"Betong {mm:.0f}", thickness_mm=mm)],
            facts=["Kostnad: låg"],
            pros=["Enkel"],
            cons=["Kall"],
        )

    return Alternatives(
        id="alt",
        question="Bottenplatta",
        options=[option("A", "Tunn platta", 100), option("B", "Tjock platta", 200)],
        chosen=chosen,
    )


def layers(doc) -> dict[str, bool]:
    return {o["name"]: o["on"] for o in doc.get_ocgs().values()}


def test_alternatives_get_a_page_and_a_layer_each():
    doc = pymupdf.open(stream=drawing_pdf(plan(alternatives=[choice()])).pdf, filetype="pdf")
    assert doc.page_count == 2
    names = layers(doc)
    assert names["Alternativ A Tunn platta"] is True
    assert names["Alternativ B Tjock platta"] is False
    assert names["Barande"] is True


def test_only_one_alternative_can_be_on():
    doc = pymupdf.open(stream=drawing_pdf(plan(alternatives=[choice()])).pdf, filetype="pdf")
    root = doc.xref_get_key(doc.pdf_catalog(), "OCProperties")[1]
    assert "/RBGroups" in root.replace(" ", "") or "RBGroups" in root
    ui = doc.get_layer()
    assert len(ui["rbgroups"]) == 1
    assert len(ui["rbgroups"][0]) == 2


def test_the_chosen_alternative_starts_on():
    doc = pymupdf.open(stream=drawing_pdf(plan(alternatives=[choice("B")])).pdf, filetype="pdf")
    names = layers(doc)
    assert names["Alternativ B Tjock platta"] is True
    assert names["Alternativ A Tunn platta"] is False
    assert "Valt: B" in doc[1].get_text()


def test_switching_layers_changes_what_shows():
    pdf = drawing_pdf(plan(alternatives=[choice()])).pdf
    before = pymupdf.open(stream=pdf, filetype="pdf")
    first = before[1].get_pixmap(dpi=40).samples
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    named = {o["name"]: x for x, o in doc.get_ocgs().items()}
    a, b = named["Alternativ A Tunn platta"], named["Alternativ B Tjock platta"]
    doc.set_layer(-1, on=[b], off=[a])
    switched = pymupdf.open(stream=doc.tobytes(), filetype="pdf")
    assert switched[1].get_pixmap(dpi=40).samples != first


def test_two_choices_get_a_page_and_a_group_each():
    second = choice().model_copy(update={"id": "alt2", "question": "Tak"})
    doc = pymupdf.open(
        stream=drawing_pdf(plan(alternatives=[choice(), second])).pdf, filetype="pdf"
    )
    assert doc.page_count == 3
    assert len(doc.get_layer()["rbgroups"]) == 2
    assert "Alternativ 2A Tunn platta" in layers(doc)


def test_the_scale_is_on_the_drawing_only():
    doc = pymupdf.open(stream=drawing_pdf(plan(alternatives=[choice()])).pdf, filetype="pdf")
    assert key(doc, doc[0], "VP")[0] == "array"
    assert key(doc, doc[1], "VP")[0] == "null"


def test_a_drawing_without_alternatives_has_no_groups():
    doc = pymupdf.open(stream=drawing_pdf(plan()).pdf, filetype="pdf")
    assert doc.page_count == 1
    assert not doc.get_layer().get("rbgroups")


def test_symbols_get_a_layer():
    d = plan(symbols=[Symbol(id="s1", kind="column", at=(400, 400))])
    doc = pymupdf.open(stream=drawing_pdf(d).pdf, filetype="pdf")
    assert "Symboler" in {o["name"] for o in doc.get_ocgs().values()}


def test_the_drawing_travels_in_the_pdf():
    doc = pymupdf.open(stream=drawing_pdf(plan()).pdf, filetype="pdf")
    assert json.loads(doc.embfile_get("rmink.drawing.json"))["name"] == "Garage"
    assert doc.metadata["title"] == "Garage r03"
