"""Sheets to the tablet and back: ink must land where it was written."""

from __future__ import annotations

import dataclasses
import io
import json
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pymupdf
import pytest
from rmscene.scene_items import Pen, PenColor

from rmink.bridge.ink_pdf import notebook_manifest, pull
from rmink.bridge.sheet import MANIFEST, build_pack, read_manifest, tablet_size, write_pack
from rmink.devices import get_device
from rmink.model import Page, Stroke
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.workbook.read import read_ink
from rmink.writer.rm_v6 import write_page

RM2 = get_device("rm2")
MARK = pymupdf.Rect(100, 50, 130, 80)  # in the unrotated page


def sheet_bytes(rotation=0, crop=None, unit=None, size=(800, 500), frame=False) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=size[0], height=size[1])
    page.draw_rect(MARK, color=None, fill=(0, 0, 0))
    if frame:
        page.draw_rect(page.rect + (5, 5, -5, -5), color=(0, 0, 0), width=1)
    if crop:
        page.set_cropbox(pymupdf.Rect(crop))
    if unit:
        doc.xref_set_key(page.xref, "UserUnit", str(unit))
    if rotation:
        page.set_rotation(rotation)
    return doc.tobytes()


def dark(pdf: bytes, number: int = 0, annots: bool = True) -> np.ndarray:
    page = pymupdf.open(stream=pdf, filetype="pdf")[number]
    pm = page.get_pixmap(alpha=False, annots=annots)
    return np.frombuffer(pm.samples, np.uint8).reshape(pm.h, pm.w, 3)[:, :, 0] < 128


def box(mask: np.ndarray) -> tuple[float, float, float, float]:
    ys, xs = np.where(mask)
    return float(xs.min()), float(ys.min()), float(xs.max() + 1), float(ys.max() + 1)


def notebook(pack, strokes: dict[int, list[Stroke]], device=RM2) -> bytes:
    """A notebook as the tablet would sync it, with ``strokes`` per tablet page."""
    uuids = UuidFactory(1)
    author = uuids()
    pages = []
    # The tablet keeps x from the middle of the page as shown (see read._landscape_shifts).
    shift = (device.height - device.width) / 2 if pack.manifest.orientation == "landscape" else 0
    for n in range(len(pack.manifest.tiles)):
        on_page = [dataclasses.replace(s, points=s.points - (shift, 0)) for s in strokes.get(n, [])]
        page = Page(device.width, device.height, on_page, ["Layer 1"])
        pages.append(
            RmdocPage(write_page(page, device, author) if on_page else b"", None, page.layers)
        )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "n.rmdoc"
        write_rmdoc(
            path, "Plan", pages, [str(uuids()) for _ in pages], author, device, str(uuids()),
            now_ms=0, pdf=pack.pdf,
        )  # fmt: skip
        return path.read_bytes()


def stroke_at(tile, x, y, length=30.0, pen=Pen.FINELINER_2, device=RM2) -> Stroke:
    """A vertical line at displayed sheet point (x, y), 8 px wide so it shows."""
    px = 72 / device.dpi
    tx, ty = tile.to_tablet(x, y)
    tx2, ty2 = tile.to_tablet(x, y + length)
    points = [(tx / px, ty / px), (tx2 / px, ty2 / px)]
    return Stroke(points, width=8, pen=pen, pressures=[60, 200])


CASES = [
    {},
    {"rotation": 90},
    {"rotation": 180},
    {"rotation": 270},
    {"crop": (50, 20, 700, 450)},
    {"unit": 2},
    {"rotation": 90, "crop": (50, 20, 700, 450)},
    {"rotation": 270, "unit": 2},
    {"rotation": 180, "crop": (50, 20, 700, 450), "unit": 2},
]


@pytest.mark.parametrize("case", CASES, ids=str)
@pytest.mark.parametrize("zoom", [1.0, 1.7])
def test_tiles_show_the_sheet_where_the_matrix_says(case, zoom):
    source = sheet_bytes(**case)
    x0, y0, x1, y1 = box(dark(source))
    pack = build_pack(source, RM2, "Plan", "s", zoom=zoom)
    width, height = tablet_size(RM2, pack.manifest.orientation).br
    tiles = [t for t in pack.manifest.tiles if t.kind == "tile"] or pack.manifest.tiles
    whole = [
        t
        for t in tiles
        if 0 <= t.to_tablet(x0, y0)[0] and t.to_tablet(x1, y1)[0] <= width
        if 0 <= t.to_tablet(x0, y0)[1] and t.to_tablet(x1, y1)[1] <= height
        if not any(
            t.to_tablet(x0, y0)[0] < r[2]
            and r[0] < t.to_tablet(x1, y1)[0]
            and t.to_tablet(x0, y0)[1] < r[3]
            and r[1] < t.to_tablet(x1, y1)[1]
            for r in t.links
        )
    ]
    assert whole
    for tile in whole:
        mask = dark(pack.pdf, tile.tablet_page)
        for r in tile.links:
            mask[int(r[1]) - 1 : int(r[3]) + 2, int(r[0]) - 1 : int(r[2]) + 2] = False
        got = box(mask)
        want = (*tile.to_tablet(x0, y0), *tile.to_tablet(x1, y1))
        assert np.allclose(got, want, atol=1.5), (got, want)


@pytest.mark.parametrize("case", CASES, ids=str)
def test_ink_lands_on_the_displayed_sheet(case):
    source = sheet_bytes(**case)
    pack = build_pack(source, RM2, "Plan", "s", zoom=1.0)
    tile = pack.manifest.tiles[0]
    page = pymupdf.open(stream=source, filetype="pdf")[0]
    x, y = page.rect.width * 0.6, page.rect.height * 0.3
    pulled = pull(notebook(pack, {0: [stroke_at(tile, x, y)]}), source)
    assert pulled.added == 1
    drawn = dark(pulled.pdf) & ~dark(source)
    x0, y0, x1, y1 = box(drawn)
    assert x0 - 8 <= x <= x1 + 8
    assert y0 - 8 <= y and y + 30 <= y1 + 8
    assert y1 - y0 < 50


def test_transform_error_is_below_half_a_point():
    source = sheet_bytes(rotation=90, crop=(50, 20, 700, 450))
    pack = build_pack(source, RM2, "Plan", "s")
    for tile in pack.manifest.tiles:
        x, y = 37.25, 91.5
        tx, ty = tile.to_tablet(x, y)
        assert np.hypot(*np.subtract(tile.to_sheet(tx, ty), (x, y))) < 0.5


def test_a_big_sheet_is_cut_with_overlap_and_covers_everything():
    pack = build_pack(sheet_bytes(size=(2384, 1684), frame=True), RM2, "A1", "s", zoom=1.0)
    tiles = [t for t in pack.manifest.tiles if t.kind == "tile"]
    assert pack.manifest.tiles[0].kind == "overview"
    assert pack.manifest.orientation == "landscape"
    # 4 x 4 at the largest zoom a little below 1 that saves pages; 1 would take 5 x 4.
    assert len(tiles) == 16
    assert 1 / tiles[0].matrix[0] == pytest.approx(0.95)
    tablet = tablet_size(RM2, "landscape").br
    seen = np.zeros((1684, 2384), dtype=bool)
    for t in tiles:
        x0, y0 = t.to_sheet(0, 0)
        x1, y1 = t.to_sheet(*tablet)
        seen[int(y0) : int(np.ceil(y1)), int(x0) : int(np.ceil(x1))] = True
    assert seen.all()


def test_a_landscape_a3_takes_four_landscape_tiles_where_it_took_six():
    a3 = (420 * 72 / 25.4, 297 * 72 / 25.4)
    source = sheet_bytes(size=a3, frame=True)
    turned = build_pack(source, RM2, "A3", "s", legend="none")
    upright = build_pack(source, RM2, "A3", "s", orientation="portrait", legend="none")
    assert [t.kind for t in turned.manifest.tiles].count("tile") == 4
    assert [t.kind for t in upright.manifest.tiles].count("tile") == 6
    # The overview is a third larger.
    assert turned.manifest.tiles[0].matrix[0] < upright.manifest.tiles[0].matrix[0] * 0.76


def test_blank_margins_get_no_tiles():
    source = sheet_bytes(size=(2384, 1684))  # only a mark near the top left
    tiles = [t for t in build_pack(source, RM2, "A1", "s").manifest.tiles if t.kind == "tile"]
    assert len(tiles) == 1
    x, y = tiles[0].to_sheet(0, 0)
    assert x == 0 and y == 0


def test_a_sheet_that_fits_is_one_page():
    pack = build_pack(sheet_bytes(size=(400, 500)), RM2, "Liten", "s", zoom=1.0)
    assert [t.kind for t in pack.manifest.tiles] == ["overview"]


def test_stroke_keeps_pressure_id_and_layer():
    source = sheet_bytes()
    pack = build_pack(source, RM2, "Plan", "abc")
    tile = pack.manifest.tiles[0]
    s = stroke_at(tile, 300, 200, pen=Pen.BALLPOINT_1)
    s.layer = "El"
    pulled = pull(notebook(pack, {0: [s, stroke_at(tile, 400, 200)]}), source)
    doc = pymupdf.open(stream=pulled.pdf, filetype="pdf")
    page = doc[0]
    annots = list(page.annots())
    assert len(annots) == 2
    for a in annots:
        assert a.type[1] == "Ink"
        assert doc.xref_get_key(a.xref, "AP")[0] == "dict"
        kind, value = doc.xref_get_key(a.xref, "OPS_InkPressure")
        assert kind == "array"
        assert len(value.strip("[]").split()) == len(a.vertices[0])
        assert a.info["id"].startswith("rmink-abc:0:")
        assert doc.xref_get_key(a.xref, "RMINK_Id")[1].startswith("abc:0:")
    assert {o["name"] for o in doc.get_ocgs().values()} == {"Bläck Plan", "Bläck Plan · El"}
    offs = [doc.xref_get_key(a.xref, "OPS_InkPressureOff")[0] for a in annots]
    assert sorted(offs) == ["bool", "null"]  # the fineliner is even on the tablet


def test_pulling_twice_adds_nothing():
    source = sheet_bytes()
    pack = build_pack(source, RM2, "Plan", "s")
    data = notebook(pack, {0: [stroke_at(pack.manifest.tiles[0], 300, 200)]})
    first = pull(data, source)
    second = pull(data, first.pdf)
    assert (second.added, second.skipped) == (0, 1)
    page = pymupdf.open(stream=second.pdf, filetype="pdf")[0]
    assert len(list(page.annots())) == 1
    assert read_manifest(second.pdf)["rounds"][0]["strokes"] == 1


def test_pulling_twice_keeps_the_files_attached_to_the_sheet():
    doc = pymupdf.open(stream=sheet_bytes(), filetype="pdf")
    doc.embfile_add("ritning.dwg", b"dwg", desc="the user's")
    doc.embfile_add("rmink.placement.json", b"{}")
    source = doc.tobytes()
    pack = build_pack(source, RM2, "Plan", "s")
    data = notebook(pack, {0: [stroke_at(pack.manifest.tiles[0], 300, 200)]})
    second = pull(data, pull(data, source).pdf).pdf
    kept = pymupdf.open(stream=second, filetype="pdf")
    names = ["rmink.manifest.json", "rmink.placement.json", "ritning.dwg"]
    assert sorted(kept.embfile_names()) == sorted(names)
    assert kept.embfile_get("ritning.dwg") == b"dwg"
    assert kept.embfile_info("ritning.dwg")["description"] == "the user's"
    assert read_manifest(second)["rounds"][0]["strokes"] == 1


def test_erasers_and_blank_pages_leave_nothing():
    source = sheet_bytes()
    pack = build_pack(source, RM2, "Plan", "s")
    data = notebook(pack, {0: [stroke_at(pack.manifest.tiles[0], 300, 200, pen=Pen.ERASER)]})
    assert pull(data, source).added == 0


def test_a_dot_survives():
    source = sheet_bytes()
    pack = build_pack(source, RM2, "Plan", "s")
    px = 72 / 226
    tx, ty = pack.manifest.tiles[0].to_tablet(300, 200)
    dot = Stroke([(tx / px, ty / px)], width=8, pressures=[100])
    assert pull(notebook(pack, {0: [dot]}), source).added == 1


def test_the_overview_opens_each_tile_and_each_tile_leads_back():
    source = sheet_bytes(size=(2384, 1684))
    pack = build_pack(source, RM2, "A1", "s", zoom=1.0)
    doc = pymupdf.open(stream=pack.pdf, filetype="pdf")
    tiles = pack.manifest.tiles
    assert sorted(link["page"] for link in doc[0].get_links()) == list(range(1, len(tiles)))
    for link, tile in zip(doc[0].get_links(), tiles[1:], strict=True):
        assert tuple(link["from"]) in [pytest.approx(r) for r in tiles[0].links]
        assert tile.kind == "tile"
    for n in range(1, len(tiles)):
        assert [link["page"] for link in doc[n].get_links()] == [0]


@pytest.mark.parametrize("size", [(894, 1192), (2384, 1684), (1684, 2384), (3370, 2384)])
def test_the_buttons_on_the_overview_do_not_collide(size):
    rects = build_pack(sheet_bytes(size=size), RM2, "Ark", "s").manifest.tiles[0].links
    for n, a in enumerate(rects):
        for b in rects[n + 1 :]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1]


def test_a_tap_on_a_button_is_not_ink_but_a_dot_elsewhere_is():
    source = sheet_bytes(size=(2384, 1684))
    pack = build_pack(source, RM2, "A1", "s", zoom=1.0)
    overview = pack.manifest.tiles[0]
    px = 72 / 226
    r = overview.links[0]
    tap = Stroke([((r[0] + 8) / px, (r[1] + 8) / px)], width=2, pressures=[100])
    dot = Stroke([(300 / px, 400 / px)], width=2, pressures=[100])
    across = Stroke(
        [((r[0] + 2) / px, (r[1] + 8) / px), ((r[2] + 30) / px, (r[1] + 8) / px)],
        width=2,
        pressures=[100, 100],
    )
    assert pull(notebook(pack, {0: [tap, dot, across]}), source).added == 2


def test_a_highlighter_in_a_colour_rmscene_does_not_know_survives():
    source = sheet_bytes()
    pack = build_pack(source, RM2, "Plan", "s")
    s = stroke_at(pack.manifest.tiles[0], 300, 200, pen=Pen.HIGHLIGHTER_2)
    s.color = PenColor.HIGHLIGHT
    data = notebook(pack, {0: [s]})
    # The tablet writes colour 14 as tag 2 of the line; rewrite it in the page.
    known, newer = bytes([0x24, 9, 0, 0, 0]), bytes([0x24, 14, 0, 0, 0])
    buffer = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as zin, zipfile.ZipFile(buffer, "w") as zout:
        for n in zin.namelist():
            raw = zin.read(n)
            if n.endswith(".rm"):
                assert known in raw
                raw = raw.replace(known, newer)
            zout.writestr(n, raw)
    pulled = pull(buffer.getvalue(), source)
    assert (pulled.added, pulled.unread) == (1, 0)
    doc = pymupdf.open(stream=pulled.pdf, filetype="pdf")
    page = doc[0]
    annot = next(iter(page.annots()))
    assert annot.opacity == pytest.approx(0.4)
    assert annot.colors["stroke"][2] < 0.5  # yellow, not black
    assert annot.colors["stroke"][0] > 0.9


def test_the_wrong_sheet_is_refused():
    source = sheet_bytes()
    pack = build_pack(source, RM2, "Plan", "s")
    with pytest.raises(ValueError, match="not the sheet"):
        pull(notebook(pack, {}), sheet_bytes(size=(600, 600)))


def test_a_sheet_changed_in_an_editor_is_recognised_by_its_record():
    source = sheet_bytes()
    pack = build_pack(source, RM2, "Plan", "s")
    tile = pack.manifest.tiles[0]
    first = pull(notebook(pack, {0: [stroke_at(tile, 300, 200)]}), source)
    doc = pymupdf.open(stream=first.pdf, filetype="pdf")
    doc[0].add_text_annot((20, 20), "granskad")
    again = pull(notebook(pack, {0: [stroke_at(tile, 300, 200)]}), doc.tobytes())
    assert (again.added, again.skipped) == (0, 1)


def test_write_pack_makes_a_notebook_read_ink_accepts(tmp_path):
    src = tmp_path / "Plan.pdf"
    src.write_bytes(sheet_bytes())
    out = tmp_path / "Plan.rmdoc"
    manifest = write_pack(src, out, RM2, seed=1)
    data = out.read_bytes()
    assert notebook_manifest(data).session == manifest.session
    assert read_ink(data, RM2).pages == {}
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        pdf = next(n for n in zf.namelist() if n.endswith(".pdf"))
        pages = pymupdf.open(stream=zf.read(pdf), filetype="pdf")
    assert pages.page_count == len(manifest.tiles)
    assert pages[0].rect.width == pytest.approx(1872 * 72 / 226)  # the sheet lies
    assert json.loads(pages.embfile_get(MANIFEST))["format"] == "rmink/sheet"
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        content = json.loads(zf.read(next(n for n in zf.namelist() if n.endswith(".content"))))
    assert content["orientation"] == "landscape"


def test_only_a_notebook_from_send_is_accepted():
    with pytest.raises(ValueError, match="not made by"):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("x.content", "{}")
        notebook_manifest(buffer.getvalue())


def test_cli_sends_and_pulls_with_the_same_files(tmp_path):
    from typer.testing import CliRunner

    from rmink.cli import app

    src = tmp_path / "Plan.pdf"
    src.write_bytes(sheet_bytes())
    out = tmp_path / "Plan.rmdoc"
    runner = CliRunner()
    sent = runner.invoke(app, ["sheet", "send", str(src), "-o", str(out)])
    assert sent.exit_code == 0, sent.output
    pulled = tmp_path / "ut.pdf"
    done = runner.invoke(app, ["sheet", "pull", str(out), str(src), "-o", str(pulled)])
    assert done.exit_code == 0, done.output
    assert "0 strokes added" in done.output
    assert pulled.exists()
    wrong = tmp_path / "Annan.pdf"
    wrong.write_bytes(sheet_bytes(size=(600, 600)))
    refused = runner.invoke(app, ["sheet", "pull", str(out), str(wrong)])
    assert refused.exit_code == 1


def test_mcp_tools_are_listed():
    anyio = pytest.importorskip("anyio")
    mcp = pytest.importorskip("mcp")

    from rmink.mcp_server import server

    async def names():
        async with mcp.Client(server) as client:
            return [t.name for t in (await client.list_tools()).tools]

    assert {"send_sheet", "pull_sheet"} <= set(anyio.run(names))
