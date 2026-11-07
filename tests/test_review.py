"""Status lists: crosses on the tablet become status on the sheet."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pymupdf
import pytest
from test_bridge import RM2, notebook, sheet_bytes
from test_points import word

from rmink.bridge.ink_pdf import pull
from rmink.bridge.points import Points, find_points, update_points, write_points
from rmink.bridge.review import build_status_pdf, read_status, write_status_notebook
from rmink.bridge.sheet import build_pack
from rmink.model import Page, Stroke
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.writer.rm_v6 import write_page

PX = 72 / 226


def filled(count: int = 1) -> tuple[bytes, Points]:
    source = sheet_bytes(size=(400, 500))
    pack = build_pack(source, RM2, "Plan", "abc")
    strokes = [s for i in range(count) for s in word(20, 20 + i * 25)]
    book = notebook(pack, {0: strokes})
    points = find_points(book)
    for n, p in enumerate(points.points):
        p.text = f"Punkt nummer {n + 1}"
    return write_points(pull(book, source).pdf, points)[0], points


def cross(rect) -> list[Stroke]:
    x0, y0, x1, y1 = [v / PX for v in rect]
    a = [(x0 + 4, y0 + 4), (x1 - 4, y1 - 4)]
    b = [(x1 - 4, y0 + 4), (x0 + 4, y1 - 4)]
    return [Stroke(a, width=2, pressures=[99, 99]), Stroke(b, width=2, pressures=[99, 99])]


def fill(rect) -> list[Stroke]:
    x0, y0, x1, y1 = [v / PX for v in rect]
    return [
        Stroke([(x0, y), (x1, y)], width=6, pressures=[99, 99])
        for y in [y0 + i * 3 for i in range(int((y1 - y0) / 3) + 1)]
    ]


def tablet(pdf: bytes, strokes: dict[int, list[Stroke]]) -> bytes:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    uuids = UuidFactory(1)
    author = uuids()
    pages = []
    for n in range(doc.page_count):
        ink = strokes.get(n, [])
        page = Page(RM2.width, RM2.height, ink, ["Layer 1"])
        pages.append(RmdocPage(write_page(page, RM2, author) if ink else b"", None, page.layers))
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "s.rmdoc"
        ids = [str(uuids()) for _ in pages]
        write_rmdoc(path, "Status", pages, ids, author, RM2, str(uuids()), now_ms=0, pdf=pdf)
        return path.read_bytes()


def box(layout, row: int, label: str, kind: str = "status"):
    f = getattr(layout.rows[row], kind)
    return next(c.rect for c in f.choices if c.text == label)


def test_a_cross_sets_the_status():
    sheet, points = filled()
    pdf, layout = build_status_pdf(points, sheet, RM2)
    read = read_status(tablet(pdf, {0: cross(box(layout, 0, "Ska åtgärdas"))}), points)
    assert read.points.points[0].status == "Ska åtgärdas"
    assert read.changed == {"P1": "Ska åtgärdas"}
    assert read.unclear == []


def test_a_cross_on_each_of_two_rows():
    sheet, points = filled(2)
    pdf, layout = build_status_pdf(points, sheet, RM2)
    ink = cross(box(layout, 0, "Avvisad")) + cross(box(layout, 1, "Har åtgärdats"))
    read = read_status(tablet(pdf, {0: ink}), points)
    assert [p.status for p in read.points.points] == ["Avvisad", "Har åtgärdats"]


def test_two_crosses_on_a_row_change_nothing_and_are_reported():
    sheet, points = filled()
    pdf, layout = build_status_pdf(points, sheet, RM2)
    ink = cross(box(layout, 0, "Avvisad")) + cross(box(layout, 0, "Annat forum"))
    read = read_status(tablet(pdf, {0: ink}), points)
    assert read.points.points[0].status == "Ny kommentar"
    assert read.unclear == ["P1"]


def test_a_filled_box_is_taken_back():
    sheet, points = filled()
    pdf, layout = build_status_pdf(points, sheet, RM2)
    ink = fill(box(layout, 0, "Avvisad")) + cross(box(layout, 0, "Annat forum"))
    assert read_status(tablet(pdf, {0: ink}), points).points.points[0].status == "Annat forum"


def test_a_scribble_in_the_boxes_is_unclear():
    sheet, points = filled()
    pdf, layout = build_status_pdf(points, sheet, RM2)
    f = layout.rows[0].status
    x0, y0, x1, _ = [v / PX for v in f.rect]
    scribble = Stroke([(x0 + 20, y0 + 30), (x1 - 300, y0 + 34)], width=2, pressures=[99, 99])
    read = read_status(tablet(pdf, {0: [scribble]}), points)
    assert read.unclear == ["P1"]
    assert read.changed == {}


def test_no_ink_leaves_everything_as_it_was():
    sheet, points = filled()
    pdf, _ = build_status_pdf(points, sheet, RM2)
    read = read_status(tablet(pdf, {}), points)
    assert (read.changed, read.unclear) == ({}, [])


def test_people_are_crossed_too():
    sheet, points = filled()
    pdf, layout = build_status_pdf(points, sheet, RM2, ["El", "VVS", "Bygg"])
    ink = cross(box(layout, 0, "VVS", "responsible")) + cross(box(layout, 0, "Ska åtgärdas"))
    read = read_status(tablet(pdf, {0: ink}), points)
    assert read.points.points[0].responsible == "VVS"
    assert read.changed == {"P1": "Ska åtgärdas, VVS"}


def test_many_points_go_over_pages_and_boxes_stay_on_them():
    sheet, points = filled(9)
    points.points = [points.points[0].model_copy(update={"id": f"P{i}"}) for i in range(1, 10)]
    pdf, layout = build_status_pdf(points, sheet, RM2)
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    assert doc.page_count == 3
    last = layout.rows[-1].status
    assert last.page == 2
    read = read_status(tablet(pdf, {2: cross(box(layout, 8, "Avvisad"))}), points)
    assert read.points.points[8].status == "Avvisad"
    assert read.points.points[0].status == "Ny kommentar"


def test_status_list_of_other_points_is_refused():
    sheet, points = filled()
    pdf, _ = build_status_pdf(points, sheet, RM2)
    other = points.model_copy(update={"session": "annan"})
    with pytest.raises(ValueError, match="belongs to"):
        read_status(tablet(pdf, {}), other)


def test_a_notebook_without_a_list_is_refused():
    sheet, points = filled()
    with pytest.raises(ValueError, match="no status list"):
        read_status(tablet(pymupdf.open(stream=sheet, filetype="pdf").tobytes(), {}), points)


def status_of(pdf: bytes) -> tuple[str, list[str], str]:
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    page = doc[0]
    comment = next(a for a in page.annots() if a.type[1] == "Text" and a.info.get("id"))
    states = [
        doc.xref_get_key(a.xref, "State")[1]
        for a in page.annots()
        if doc.xref_get_key(a.xref, "State")[0] != "null"
    ]
    private = doc.xref_get_key(comment.xref, "RMINK_Status")[1]
    return private, states, comment.info["title"]


def test_update_sets_status_and_replaces_the_old_one():
    sheet, points = filled()
    points.points[0].status = "Ska åtgärdas"
    points.points[0].responsible = "VVS"
    pdf, missing = update_points(sheet, points)
    assert missing == []
    assert status_of(pdf) == ("Ska åtgärdas", ["Accepted"], "VVS")
    points.points[0].status = "Har åtgärdats"
    assert status_of(update_points(pdf, points)[0]) == ("Har åtgärdats", ["Completed"], "VVS")


def test_update_to_a_status_without_a_state_removes_the_old_state():
    sheet, points = filled()
    points.points[0].status = "Avvisad"
    pdf = update_points(sheet, points)[0]
    points.points[0].status = "Annat forum"
    assert status_of(update_points(pdf, points)[0])[:2] == ("Annat forum", [])


def test_update_reports_a_point_that_is_gone():
    sheet, points = filled()
    points.points[0].id = "P99"
    assert update_points(sheet, points)[1] == ["P99"]


def test_write_status_notebook(tmp_path):
    sheet, points = filled()
    out = tmp_path / "s.rmdoc"
    assert write_status_notebook(points, sheet, out, RM2, seed=1) == 1
    assert read_status(out.read_bytes(), points).changed == {}
