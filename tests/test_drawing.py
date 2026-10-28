import json
import zipfile
from uuid import UUID

import anyio
import numpy as np
import pytest
from rmscene.scene_items import PenColor

from rmink.devices import get_device
from rmink.drawing import workflow
from rmink.drawing.fit import analyse, classify
from rmink.drawing.font import _letters, text_paths
from rmink.drawing.model import Annotation, Dimension, Drawing, Element, SketchRef, Symbol
from rmink.drawing.render import COMMENT_LAYER, render_drawing
from rmink.ingest.rm import read_page, read_rmdoc
from rmink.model import Page, Stroke
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.writer.rm_v6 import write_page

RM2 = get_device("rm2")


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("RMINK_CLOUD_TOKEN", raising=False)


def _wobbly(a, b, n=40, seed=0):
    rng = np.random.default_rng(seed)
    return np.linspace(a, b, n) + rng.normal(0, 1.2, (n, 2))


@pytest.fixture
def sketch(tmp_path):
    """A hand-drawn rectangle with a written measurement above it and a circle."""
    strokes = [
        Stroke(_wobbly((200, 300), (1200, 300), seed=1)),
        Stroke(_wobbly((1200, 300), (1200, 1000), seed=2)),
        Stroke(_wobbly((1200, 1000), (200, 1000), seed=3)),
        Stroke(_wobbly((200, 1000), (200, 300), seed=4)),
    ]
    t = np.linspace(0, 2 * np.pi, 60)
    strokes.append(Stroke(np.column_stack([450 + 60 * np.cos(t), 450 + 60 * np.sin(t)])))
    strokes += [Stroke(p) for p in text_paths("4800", (640, 260), 34)]
    page = Page(RM2.width, RM2.height, strokes)
    uu = UuidFactory(1)
    author = uu()
    path = tmp_path / "Altan.rmdoc"
    write_rmdoc(
        path, "Altan", [RmdocPage(write_page(page, RM2, author))], [str(uu())], author, RM2,
        str(uu()),
    )  # fmt: skip
    return path


def test_layers_round_trip():
    page = Page(
        RM2.width,
        RM2.height,
        [
            Stroke([[10, 10], [100, 20]], layer="Ritning r1"),
            Stroke([[50, 50], [60, 500]], color=PenColor.RED, layer="Ritning r1"),
        ],
        layer_names=["Ritning r1", COMMENT_LAYER],
    )
    back = read_page(write_page(page, RM2, UUID(int=1)), RM2)
    assert back.layer_names == ["Ritning r1", COMMENT_LAYER]
    assert [s.id for s in back.strokes] == [(1, 16), (1, 17)]
    assert back.strokes[1].color == PenColor.RED
    np.testing.assert_allclose(back.strokes[0].points, page.strokes[0].points, atol=0.01)


def test_single_layer_output_unchanged():
    page = Page(RM2.width, RM2.height, [Stroke([[10, 10], [100, 20]])])
    back = read_page(write_page(page, RM2, UUID(int=1)), RM2)
    assert back.layer_names == ["Layer 1"]


def test_read_rmdoc(sketch):
    doc = read_rmdoc(sketch, RM2)
    assert doc.name == "Altan"
    assert len(doc.pages) == 1 and len(doc.pages[0].strokes) > 5


def test_classify_shapes():
    shape, fit = classify(_wobbly((0, 0), (500, 4)))
    assert shape == "line" and abs(fit["angle_deg"]) < 2
    t = np.linspace(0, 2 * np.pi, 50)
    shape, fit = classify(np.column_stack([100 + 80 * np.cos(t), 200 + 80 * np.sin(t)]))
    assert shape == "circle" and abs(fit["radius"] - 80) < 2
    t = np.linspace(0, 2 * np.pi * 1.08, 50)  # overshoots its start, as by hand
    shape, _ = classify(np.column_stack([100 + 50 * np.cos(t), 200 + 50 * np.sin(t)]))
    assert shape == "circle"
    shape, fit = classify(np.array([[0, 0], [300, 0], [300, 300], [0, 300.0]]))
    assert shape == "polyline" and len(fit["points"]) == 4


def test_analyse_groups(sketch):
    page = read_rmdoc(sketch, RM2).pages[0]
    groups = analyse(page, RM2)
    shapes = sorted(g.shape for g in groups)
    # Four walls, a circle and the digits of "4800" as one handwriting group.
    assert shapes == ["circle", "line", "line", "line", "line", "mark"]


def test_unit_letters():
    assert _letters("Trädäck 28x120 mm") == "TRÄDÄCK 28X120 mm"
    assert _letters("mot väster, 3 m2") == "MOT VÄSTER, 3 m2"


def _drawing(sketch_path) -> Drawing:
    return Drawing(
        name="Altan",
        elements=[
            Element(id="e1", kind="rect", points=[(201, 302), (1199, 998)], category="structure"),
            Element(id="e2", kind="circle", center=(450, 450), radius=60, category="plumbing"),
        ],
        dimensions=[Dimension(id="d1", start=(200, 300), end=(1200, 300), text="4800")],
        symbols=[Symbol(id="s1", kind="column", at=(1200, 1000))],
        sketch=SketchRef(document=str(sketch_path), page=1, device="rm2"),
    )


def test_render_colour_and_mono(sketch):
    d = _drawing(sketch)
    pro = render_drawing(
        d.model_copy(update={"sketch": SketchRef(device="pro")}), get_device("pro")
    )
    mono = render_drawing(d, RM2)
    assert pro.layers == mono.layers == ["Ritning r1", COMMENT_LAYER]
    assert PenColor.BLUE in {s.color for s in pro.strokes}
    assert {s.color for s in mono.strokes} <= {PenColor.BLACK, PenColor.GRAY}
    # Mono tells plumbing apart by dashes: the circle becomes many pieces.
    assert len(mono.strokes) > len(pro.strokes)


def test_rectify_and_dimensions():
    d = Drawing(
        name="x",
        elements=[
            Element(id="a", kind="line", points=[(100, 100), (500, 108)]),
            Element(id="b", kind="line", points=[(505, 104), (497, 400)]),
        ],
        dimensions=[
            Dimension(id="d1", start=(100, 100), end=(500, 100), text="4000"),
            Dimension(id="d2", start=(500, 100), end=(500, 400), text="2000"),
        ],
    )
    r = workflow.rectify(d)
    (a0, a1), (b0, b1) = r.elements[0].points, r.elements[1].points
    assert a0[1] == a1[1] and b0[0] == b1[0]  # square
    assert a1 == b0  # joined corner
    check = workflow.check_dimensions(d)
    flags = {row["id"]: row["consistent"] for row in check["dimensions"]}
    # 400 px for 4000 and 300 px for 2000 cannot share one scale.
    assert flags == {"d1": False, "d2": False}


def test_revision_round_trip(sketch, tmp_path):
    """r1 is written with the sketch after it; markings drawn on r1 come back
    as the only groups in the next round."""
    d = _drawing(sketch)
    doc = read_rmdoc(sketch, RM2)
    rev = workflow.build_revision(d, tmp_path / "Altan r1.rmdoc", doc.pages[0], seed=2)
    saved = workflow.load_drawing("Altan")
    assert saved.sketch.written_ids and saved.legend  # legend made from what is used

    back = read_rmdoc(rev.path, RM2)
    assert back.name == "Altan r01" and len(back.pages) == 2
    clean = back.pages[0]
    assert clean.layer_names == ["Ritning r1", COMMENT_LAYER]
    with zipfile.ZipFile(rev.path) as zf:
        meta = [json.loads(zf.read(n)) for n in zf.namelist() if n.endswith("-metadata.json")]
    assert {"name": COMMENT_LAYER} in meta[0]["layers"]

    # The user rings the column on the comment layer and writes "?" next to it.
    t = np.linspace(0, 2 * np.pi, 40)
    ring = np.column_stack([1200 + 50 * np.cos(t), 1000 + 50 * np.sin(t)])
    marks = [Stroke(ring, layer=COMMENT_LAYER)]
    marks += [Stroke(p, layer=COMMENT_LAYER) for p in text_paths("?", (1270, 960), 40)]
    marked = Page(clean.width, clean.height, clean.strokes + marks, clean.layer_names)
    uu = UuidFactory(9)
    author = uu()
    # Firmware keeps existing ids when it saves; emulate by writing the marks
    # after the original strokes, which keeps rmink's (1, n) counters in place.
    data = write_page(marked, RM2, author)
    marked_back = read_page(data, RM2)
    known = {tuple(i) for i in saved.sketch.written_ids}
    assert sum(s.id not in known for s in marked_back.strokes) == len(marks)

    path = tmp_path / "marked.rmdoc"
    write_rmdoc(path, "Altan r1", [RmdocPage(data)], [str(uu())], author, RM2, str(uu()))
    sk = workflow.read_sketch(str(path), 1, RM2, since=saved)
    assert len(sk.groups) == 2
    assert {g.layer for g in sk.groups} == {COMMENT_LAYER}
    assert sk.overlay_png(RM2)[:4] == b"\x89PNG"

    # Turned into an open remark, it shows up on r2.
    r2 = saved.model_copy(deep=True)
    r2.revision = 2
    r2.annotations.append(Annotation(id="a1", kind="circle", targets=["s1"], text="Flytta?"))
    r2.log.append("r2: anmärkning på pelare")
    page2 = render_drawing(r2, RM2)
    assert page2.layers[0] == "Ritning r2"
    assert len(page2.strokes) > len(render_drawing(saved, RM2).strokes)


def test_mcp_drawing_tools(sketch, tmp_path):
    from mcp import Client

    from rmink.mcp_server import server

    async def run():
        async with Client(server, raise_exceptions=True) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            assert {
                "read_sketch", "drawing_reference", "render_drawing_preview", "save_revision",
                "get_drawing", "cloud_connect", "cloud_list",
            } <= tools  # fmt: skip

            res = await client.call_tool("read_sketch", {"document": str(sketch)})
            assert not res.is_error, res
            assert any(c.type == "image" for c in res.content)
            info = json.loads(next(c.text for c in res.content if c.type == "text"))
            assert len(info["groups"]) == 6

            drawing = _drawing(sketch).model_dump(mode="json")
            res = await client.call_tool("render_drawing_preview", {"drawing": drawing})
            assert not res.is_error, res
            assert any(c.type == "image" for c in res.content)

            out = tmp_path / "r1.rmdoc"
            res = await client.call_tool(
                "save_revision",
                {"drawing": drawing, "output_path": str(out), "svg_path": str(tmp_path / "r1.svg")},
            )
            assert not res.is_error, res
            assert out.exists() and (tmp_path / "r1.svg").read_text().startswith("<svg")
            assert len(read_rmdoc(out, RM2).pages) == 2

            res = await client.call_tool("get_drawing", {"name": "Altan"})
            assert not res.is_error, res

    anyio.run(run)


def test_remarks_on_large_targets_mark_the_corners():
    """A remark on a long text gets corner marks hugging it, not a ring that
    runs through the texts around it; a small target keeps its ring."""
    long_text = Element(id="t", kind="text", points=[(200, 600)], text="BETONG 150 C25/30 XC2")
    d = Drawing(
        name="x",
        elements=[long_text, Element(id="s", kind="text", points=[(200, 300)], text="A")],
        annotations=[
            Annotation(id="a1", kind="circle", targets=["t"], text="XC2?"),
            Annotation(id="a2", kind="circle", targets=["s"], text="?"),
        ],
    )
    page = render_drawing(d, get_device("rm2"))
    comment = [
        s.points for s in page.strokes if 450 < s.points[:, 1].mean() < 660
    ]  # not the title block
    marks = np.vstack(comment)
    # everything drawn for the remark stays within a band around the text line
    assert marks[:, 1].min() > 600 - 22 - 60 and marks[:, 1].max() < 600 + 60
    plain = render_drawing(d.model_copy(update={"annotations": []}), get_device("rm2"))
    assert len(page.strokes) > len(plain.strokes)
