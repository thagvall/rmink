"""Field rounds: from strokes on a sheet to a numbered list."""

from __future__ import annotations

import csv
import io

import numpy as np
import pymupdf
import pytest
from rmscene.scene_items import Pen
from test_bridge import RM2, notebook, sheet_bytes

from rmink.bridge.ink_pdf import pull
from rmink.bridge.points import (
    Point,
    Points,
    find_points,
    group_notes,
    point_image,
    points_csv,
    write_points,
)
from rmink.bridge.sheet import build_pack
from rmink.model import Stroke

PX = RM2.px_per_mm  # px per mm on the tablet


def word(x: float, y: float, letters: int = 3) -> list[Stroke]:
    """Letters 4 mm wide and 5 mm high, at mm from the page's corner."""
    return [
        Stroke(
            [((x + i * 5) * PX, y * PX), ((x + i * 5 + 3) * PX, (y + 5) * PX)],
            width=2,
            pressures=[100, 100],
        )
        for i in range(letters)
    ]


def line(x0: float, y0: float, x1: float, y1: float, pen=Pen.FINELINER_2) -> Stroke:
    n = 12
    pts = np.c_[np.linspace(x0, x1, n), np.linspace(y0, y1, n)] * PX
    return Stroke(pts, width=2, pen=pen, pressures=[100] * n)


def ring(cx: float, cy: float, r: float) -> Stroke:
    t = np.linspace(0, 2 * np.pi, 40)
    return Stroke(np.c_[cx + r * np.cos(t), cy + r * np.sin(t)] * PX, width=2, pressures=[100] * 40)


def test_words_on_two_lines_are_one_note():
    strokes = word(10, 10) + word(32, 10) + word(10, 18)
    assert len(group_notes(strokes, RM2)) == 1


def test_notes_with_space_between_are_two():
    assert len(group_notes(word(10, 10) + word(10, 30), RM2)) == 2


def test_a_line_along_a_wall_beside_a_note_stays_its_own_point():
    strokes = [line(5, 5, 5, 120), *word(15, 40)]
    assert sorted(len(g) for g in group_notes(strokes, RM2)) == [1, 3]


def test_a_ring_around_a_note_belongs_to_it():
    assert len(group_notes([ring(30, 30, 25), *word(25, 28, 2)], RM2)) == 1


def test_a_highlight_over_a_word_belongs_to_it():
    strokes = [*word(20, 20), line(18, 22, 40, 22, Pen.HIGHLIGHTER_2)]
    assert len(group_notes(strokes, RM2)) == 1


def test_parts_of_a_note_whose_areas_meet_are_joined():
    note = word(10, 10, 2) + word(27, 19, 2)  # spans x 10-35, y 10-24
    inside = [line(12, 20, 14, 24)]  # within that area, too far from each stroke
    assert len(group_notes(note + inside, RM2)) == 1


def test_find_points_numbers_and_types_them():
    source = sheet_bytes(size=(400, 500))
    pack = build_pack(source, RM2, "Plan", "s")
    data = notebook(pack, {0: [*word(20, 20), line(20, 100, 110, 100), ring(60, 150, 20)]})
    points = find_points(data).points
    assert [p.id for p in points] == ["P1", "P2", "P3"]
    assert [p.kind for p in points] == ["note", "line", "ring"]
    assert [len(p.strokes) for p in points] == [3, 1, 1]


def test_a_tap_on_a_button_is_no_point():
    source = sheet_bytes(size=(2384, 1684))
    pack = build_pack(source, RM2, "A1", "s")
    r = pack.manifest.tiles[0].links[0]
    px = 72 / 226
    tap = Stroke([((r[0] + 8) / px, (r[1] + 8) / px)], width=2, pressures=[100])
    assert find_points(notebook(pack, {0: [tap]})).points == []


def filled(data: bytes) -> tuple[bytes, Points]:
    source = sheet_bytes(size=(400, 500))
    pack = build_pack(source, RM2, "Plan", "abc")
    book = notebook(pack, {0: data})
    points = find_points(book)
    return pull(book, source).pdf, points


def test_points_become_numbered_comments_beside_the_ink():
    sheet, points = filled(word(20, 20))
    points.points[0].text = "Fukt vid fönster"
    pdf, added, skipped = write_points(sheet, points)
    assert (added, skipped) == (1, 0)
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    page = doc[0]
    annots = list(page.annots())
    comment = next(a for a in annots if a.type[1] == "Text")
    assert comment.info["content"] == "1. Fukt vid fönster"
    assert comment.info["subject"] == "Punkt 1"
    assert comment.info["id"] == "rmink-point-abc-P1"
    assert doc.xref_get_key(comment.xref, "RMINK_Status")[1] == "Ny kommentar"
    assert "abc:0:" in doc.xref_get_key(comment.xref, "RMINK_Strokes")[1]
    assert sum(a.type[1] == "Ink" for a in annots) == 3  # the ink stays
    assert "Punkter Plan" in {o["name"] for o in doc.get_ocgs().values()}
    label = next(a for a in annots if a.type[1] == "FreeText")
    assert label.info["content"] == "1"


def test_writing_points_twice_keeps_what_is_there():
    sheet, points = filled(word(20, 20))
    pdf, *_ = write_points(sheet, points)
    points.points[0].text = "Annat"
    again, added, skipped = write_points(pdf, points)
    assert (added, skipped) == (0, 1)
    page = pymupdf.open(stream=again, filetype="pdf")[0]
    assert sum(a.type[1] == "Text" for a in page.annots()) == 1


def test_a_status_with_a_state_gets_a_review_reply():
    sheet, points = filled(word(20, 20))
    points.points[0].status = "Har åtgärdats"
    doc = pymupdf.open(stream=write_points(sheet, points)[0], filetype="pdf")
    page = doc[0]
    reply = next(a for a in page.annots() if doc.xref_get_key(a.xref, "State")[0] != "null")
    assert doc.xref_get_key(reply.xref, "State")[1] == "Completed"
    assert doc.xref_get_key(reply.xref, "StateModel")[1] == "Review"
    assert doc.xref_get_key(reply.xref, "IRT")[0] == "xref"


def test_a_status_without_a_state_is_kept_privately():
    sheet, points = filled(word(20, 20))
    points.points[0].status = "Annat forum"
    doc = pymupdf.open(stream=write_points(sheet, points)[0], filetype="pdf")
    page = doc[0]
    assert all(doc.xref_get_key(a.xref, "State")[0] == "null" for a in page.annots())
    comment = next(a for a in page.annots() if a.type[1] == "Text")
    assert doc.xref_get_key(comment.xref, "RMINK_Status")[1] == "Annat forum"


def test_an_unknown_status_is_refused():
    sheet, points = filled(word(20, 20))
    points.points[0].status = "Klar"
    with pytest.raises(ValueError, match="unknown status"):
        write_points(sheet, points)


def test_an_unsure_point_says_so_on_the_sheet_and_in_the_list():
    sheet, points = filled(word(20, 20))
    points.points[0].unsure = True
    page = pymupdf.open(stream=write_points(sheet, points)[0], filetype="pdf")[0]
    comment = next(a for a in page.annots() if a.type[1] == "Text")
    assert comment.info["content"].startswith("[osäker] 1.")
    assert "ja" in points_csv(points)


@pytest.mark.parametrize("rotation", [0, 90, 180, 270])
def test_the_comment_sits_at_the_point_on_a_rotated_sheet(rotation):
    source = sheet_bytes(rotation=rotation)
    point = Point(
        id="P1",
        sheet_page=0,
        tablet_page=0,
        rect=(200, 120, 260, 150),
        kind="note",
        strokes=[],
        text="x",
    )
    pdf, *_ = write_points(source, Points(session="s", name="Plan", points=[point]))
    page = pymupdf.open(stream=pdf, filetype="pdf")[0]
    pm = page.get_pixmap(alpha=False, annots=True)
    base = pymupdf.open(stream=source, filetype="pdf")[0].get_pixmap(alpha=False)
    a = np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w, 3).astype(int)
    b = np.frombuffer(base.samples, np.uint8).reshape(pm.h, pm.w, 3).astype(int)
    ys, xs = np.where(np.abs(a - b).sum(axis=2) > 60)
    assert 180 <= xs.min() <= 300
    assert 90 <= ys.min() <= 180


def test_the_list_opens_in_a_swedish_spreadsheet():
    sheet, points = filled(word(20, 20))
    points.points[0].text = "Fukt; vid fönster"
    text = points_csv(points)
    assert text.startswith("\ufeff")
    rows = list(csv.reader(io.StringIO(text.lstrip("\ufeff")), delimiter=";"))
    assert rows[0][:2] == ["Nr", "Blad"]
    assert rows[1][0] == "1"
    assert rows[1][4] == "Fukt; vid fönster"


def test_point_image_shows_the_ink():
    sheet, points = filled(word(20, 20))
    assert point_image(sheet, points.points[0]).startswith(b"\x89PNG")
