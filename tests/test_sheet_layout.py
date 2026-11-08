"""Sheets lie on the tablet as they do on paper, with their legend beside every tile."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from test_bridge import RM2, notebook, sheet_bytes
from test_drawing_pdf import plan
from test_points import line

from rmink.bridge.drawing_pdf import drawing_pdf
from rmink.bridge.ink_pdf import pull
from rmink.bridge.sheet import (
    Manifest,
    build_pack,
    find_legend,
    layout,
    parse_legend,
    tablet_size,
)
from rmink.drawing.model import Symbol
from rmink.drawing.symbols import SYMBOLS
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.workbook.read import read_ink

MM = 72 / 25.4
DATA = Path(__file__).parent / "data"
A3 = (420 * MM, 297 * MM)


def titled(size=A3, block=(130, 34), words: int = 12, text: float = 9) -> bytes:
    """A framed sheet with a title block of ``block`` mm in its bottom right corner."""
    doc = pymupdf.open()
    page = doc.new_page(width=size[0], height=size[1])
    frame = page.rect + (10 * MM, 10 * MM, -10 * MM, -10 * MM)
    page.draw_rect(frame, color=(0, 0, 0), width=1)
    page.draw_rect(pymupdf.Rect(60, 60, 300, 200), color=(0, 0, 0), width=2)  # a room
    w, h = block[0] * MM, block[1] * MM
    box = pymupdf.Rect(frame.x1 - w, frame.y1 - h, frame.x1, frame.y1)
    page.draw_rect(box, color=(0, 0, 0), width=0.7)
    for n in range(words):
        y = box.y0 + 8 + (n // 3) * (text + 3)
        page.insert_text((box.x0 + 6 + (n % 3) * w / 3, y + text), f"Rad{n}", fontsize=text)
    return doc.tobytes()


def test_the_tablet_keeps_x_from_the_middle_of_a_landscape_page():
    """A cross drawn on an rm2 in a ring at (60, 387) of a landscape page."""
    doc = pymupdf.open()
    doc.new_page(width=1872 * 72 / 226, height=1404 * 72 / 226)
    uuids = UuidFactory(3)
    author = uuids()
    rm = (DATA / "rm2-landscape-page.rm").read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "c.rmdoc"
        write_rmdoc(path, "c", [RmdocPage(rm)], [str(uuids())], author, RM2, str(uuids()),
                    pdf=doc.tobytes(), orientation="landscape")  # fmt: skip
        strokes = read_ink(path.read_bytes(), RM2).pages[0]
    k = 72 / RM2.dpi
    cross = np.vstack([s.points for s in strokes[:2]]) * k
    centre = (cross.min(axis=0) + cross.max(axis=0)) / 2
    assert np.allclose(centre, (60, 387), atol=3)
    seam = strokes[2].points * k  # drawn from ring 1 to ring 2, 16 pt round
    assert np.allclose([seam[:, 0].min(), seam[:, 0].max()], (76, 520), atol=4)


def test_landscape_sheets_make_a_landscape_notebook_and_portrait_ones_a_portrait():
    assert build_pack(titled(), RM2, "A3", "s").manifest.orientation == "landscape"
    tall = titled(size=(A3[1], A3[0]))
    assert build_pack(tall, RM2, "A3", "s").manifest.orientation == "portrait"
    forced = build_pack(titled(), RM2, "A3", "s", orientation="portrait").manifest
    assert forced.orientation == "portrait"
    with pytest.raises(ValueError, match="Orientation"):
        build_pack(titled(), RM2, "A3", "s", orientation="sideways")


def test_an_old_manifest_is_portrait():
    pack = build_pack(sheet_bytes(), RM2, "Plan", "s")
    data = json.loads(pack.manifest.model_dump_json())
    del data["orientation"], data["legends"]
    for t in data["tiles"]:
        del t["blocked"]
    old = Manifest.model_validate(data)
    assert old.orientation == "portrait" and old.legends == {}


def test_the_title_block_is_found_in_the_corner():
    page = pymupdf.open(stream=titled(), filetype="pdf")[0]
    found = find_legend(page)
    assert found is not None
    assert [round(v / MM) for v in found] == [280, 253, 410, 287]
    plain = pymupdf.open(stream=sheet_bytes(), filetype="pdf")[0]
    assert find_legend(plain) is None


def test_the_title_block_is_found_on_a_turned_sheet():
    doc = pymupdf.open(stream=titled(size=(A3[1], A3[0])), filetype="pdf")
    page = doc[0]
    # Draw it lying on a tall page, then turn the page to show it as a lying sheet.
    turned = pymupdf.open()
    lying = turned.new_page(width=A3[1], height=A3[0])
    lying.show_pdf_page(lying.rect, pymupdf.open(stream=titled(), filetype="pdf"), 0, rotate=90)
    lying.set_rotation(90)
    found = find_legend(turned[0])
    assert page.rect.width < turned[0].rect.width  # shown lying
    assert found is not None
    assert [round(v / MM) for v in found] == [280, 253, 410, 287]


def test_the_legend_is_pasted_beside_every_tile_and_ink_on_it_stays_off_the_sheet():
    source = titled()
    pack = build_pack(source, RM2, "A3", "s")
    tiles = [t for t in pack.manifest.tiles if t.kind == "tile"]
    assert len(tiles) == 4 and all(t.blocked for t in tiles)
    assert layout(pack.manifest)[0]["legend"] == "beside each tile"
    # The legend's text is on every tile.
    doc = pymupdf.open(stream=pack.pdf, filetype="pdf")
    assert all("Rad0" in doc[t.tablet_page].get_text() for t in tiles)

    tile = tiles[0]
    x0, y0, x1, y1 = tile.blocked[0]
    cx, cy = ((x0 + x1) / 2 / MM, (y0 + y1) / 2 / MM)  # tablet mm
    on_legend = line(cx - 10, cy, cx + 10, cy)
    on_sheet = line(30, 30, 60, 30)
    pulled = pull(notebook(pack, {tile.tablet_page: [on_legend, on_sheet]}), source)
    assert (pulled.added, pulled.on_legend) == (1, 1)


def test_a_legend_too_small_to_read_beside_the_tiles_gets_a_page_of_its_own():
    source = titled(block=(200, 140), words=30, text=7)
    pack = build_pack(source, RM2, "A3", "s")
    kinds = [t.kind for t in pack.manifest.tiles]
    assert kinds[:2] == ["overview", "legend"]
    assert layout(pack.manifest)[0]["legend"] == "own page"
    tiles = [t for t in pack.manifest.tiles if t.kind == "tile"]
    assert not any(t.blocked for t in tiles)
    doc = pymupdf.open(stream=pack.pdf, filetype="pdf")
    # Every tile has a button to the legend page, which shows the legend where it is.
    for t in tiles:
        targets = {link["page"] for link in doc[t.tablet_page].get_links()}
        assert targets == {0, 1}
    legend = pack.manifest.tiles[1]
    found = pack.manifest.legends[0]
    x, y = legend.to_tablet(found[0], found[1])
    assert 0 <= x < 10 and 20 < y < 40


def test_no_legend_and_a_legend_given_by_hand():
    source = titled()
    none = build_pack(source, RM2, "A3", "s", legend="none").manifest
    assert none.legends == {} and not any(t.blocked for t in none.tiles)
    box = parse_legend("280,253,410,287")
    given = build_pack(source, RM2, "A3", "s", legend=box).manifest
    assert [round(v / MM) for v in given.legends[0]] == [280, 253, 410, 287]
    assert parse_legend("none") == "none"
    with pytest.raises(ValueError, match="legend"):
        parse_legend("10,10,5,5")


def test_a_drawing_says_where_its_title_block_is():
    source = drawing_pdf(plan(), "a3").pdf
    doc = pymupdf.open(stream=source, filetype="pdf")
    place = json.loads(doc.embfile_get("rmink.placement.json"))
    pack = build_pack(source, RM2, "Garage", "g")
    assert pack.manifest.legends[0] == pytest.approx(tuple(place["legend"]))


def test_buttons_keep_their_letters_on_a_sheet_with_its_own_helvetica():
    """A sheet with a font named "helv" made PyMuPDF add none for the buttons, and
    the tablet drew "Översikt" without its Ö."""

    def button(source: bytes) -> np.ndarray:
        pack = build_pack(source, RM2, "x", "s", legend="none")
        page = pymupdf.open(stream=pack.pdf, filetype="pdf")[1]
        r = pymupdf.Rect(pack.manifest.tiles[1].links[-1])
        pm = page.get_pixmap(dpi=144, clip=r, alpha=False)
        return np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w, 3)[:, :, 0] < 128

    drawing = drawing_pdf(plan(), "a3").pdf
    assert "helv" in {f[4] for f in pymupdf.open(stream=drawing, filetype="pdf")[0].get_fonts()}
    blank = titled(block=(130, 34), words=0)
    assert np.array_equal(button(drawing), button(blank))


def test_the_notebook_says_it_lies(tmp_path):
    from rmink.bridge.sheet import write_pack

    src = tmp_path / "A3.pdf"
    src.write_bytes(titled())
    write_pack(src, tmp_path / "A3.rmdoc", RM2, seed=1)
    with zipfile.ZipFile(io.BytesIO((tmp_path / "A3.rmdoc").read_bytes())) as zf:
        content = json.loads(zf.read(next(n for n in zf.namelist() if n.endswith(".content"))))
    assert content["orientation"] == content["customZoomOrientation"] == "landscape"
    assert tablet_size(RM2, "landscape").width == pytest.approx(1872 * 72 / 226)


def test_a_drawing_explains_its_symbols_beside_the_title_block():
    symbols = [
        Symbol(id=f"s{i}", kind=kind, at=(300 + 150 * i, 400), size=40)
        for i, kind in enumerate(["outlet", "switch", "light", "outlet"])
    ]
    source = drawing_pdf(plan(symbols=symbols), "a3").pdf
    page = pymupdf.open(stream=source, filetype="pdf")[0]
    place = json.loads(page.parent.embfile_get("rmink.placement.json"))
    legend = pymupdf.Rect(place["legend"])
    text = page.get_text(clip=legend)
    assert "Förklaring" in text
    assert all(name in text for name in ("Eluttag", "Strömbrytare", "Armatur", "Bärande"))
    assert text.count("Eluttag") == 1  # one row per kind
    title = page.get_text(clip=pymupdf.Rect(legend.x1 + 1, legend.y0, page.rect.x1, legend.y1))
    assert "Garage" in title and "Förklaring" not in title
    # On the tablet it is the legend that goes beside every tile.
    pack = build_pack(source, RM2, "Garage", "g")
    assert pack.manifest.legends[0] == pytest.approx(tuple(legend))
    doc = pymupdf.open(stream=pack.pdf, filetype="pdf")
    tiles = [t for t in pack.manifest.tiles if t.kind == "tile"]
    assert all(t.blocked and "Strömbrytare" in doc[t.tablet_page].get_text() for t in tiles)


def test_a_long_legend_says_how_many_more_there_are():
    kinds = list(SYMBOLS)[:30]
    symbols = [
        Symbol(id=f"s{i}", kind=k, at=(150 + 30 * i, 400), size=20) for i, k in enumerate(kinds)
    ]
    source = drawing_pdf(plan(symbols=symbols), "a4").pdf
    page = pymupdf.open(stream=source, filetype="pdf")[0]
    legend = pymupdf.Rect(json.loads(page.parent.embfile_get("rmink.placement.json"))["legend"])
    assert "till" in page.get_text(clip=legend)


def test_a_drawing_with_nothing_to_explain_gives_its_title_block():
    d = plan()
    for e in d.elements:
        e.category = "default"
    source = drawing_pdf(d, "a3").pdf
    page = pymupdf.open(stream=source, filetype="pdf")[0]
    legend = pymupdf.Rect(json.loads(page.parent.embfile_get("rmink.placement.json"))["legend"])
    assert "Garage" in page.get_text(clip=legend)
    assert "Förklaring" not in page.get_text()
