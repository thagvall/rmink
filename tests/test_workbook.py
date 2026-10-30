import io
import json
import zipfile

import numpy as np
import pymupdf
import pytest
import rmscene
from test_rounds import FakeClient, FakeCloud, _block, _tool

from rmink.devices import get_device
from rmink.drawing.agent import RoundError
from rmink.drawing.store import FileStore, MemoryStore
from rmink.model import Stroke
from rmink.workbook import workflow
from rmink.workbook.agent import create_workbook, find_workbook, run_round
from rmink.workbook.build import build_pdf, page_size, plain
from rmink.workbook.model import Workbook
from rmink.workbook.read import HANDWRITING_LAYER, Sorted, read_ink, sort_ink

RM2 = get_device("rm2")

WORKBOOK = {
    "name": "Bråk",
    "title": "Bråk och procent",
    "intro": "Skriv svaren i rutorna.",
    "sections": [
        {
            "id": "s1",
            "title": "Bråk",
            "text": "Ett bråk är en del av en helhet.",
            "fields": [
                {"id": "s1f1", "prompt": "Vad är 3/4 av 12?", "lines": 2},
                {"id": "s1f2", "prompt": "Förklara hur du tänkte.", "lines": 4},
            ],
        },
        {
            "id": "s2",
            "title": "Procent",
            "text": "Procent betyder hundradelar.",
            "fields": [{"id": "s2f1", "prompt": "Vad är 25 % av 80?", "lines": 2}],
        },
    ],
}


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for key in ("RMINK_CLOUD_TOKEN", "UPSTASH_REDIS_REST_URL", "KV_REST_API_URL"):
        monkeypatch.delenv(key, raising=False)


def _wb() -> Workbook:
    wb = Workbook.model_validate(WORKBOOK)
    build_pdf(wb, RM2)
    return wb


def _writing_in(wb: Workbook, field_id: str) -> Stroke:
    """A scribble across the middle of a field's box, in device px."""
    x0, y0, x1, y1 = (v * RM2.dpi / 72 for v in wb.field(field_id).rect)
    ym = (y0 + y1) / 2
    return Stroke(np.linspace((x0 + 30, ym), (x0 + 200, ym + 10), 20))


def _synced(wb: Workbook, tmp_path, strokes: dict[int, list[Stroke]], name="synced"):
    """The revision as the tablet syncs it after the user wrote ``strokes``."""
    path = workflow.build_revision(wb, tmp_path / name, RM2, Sorted(loose=strokes))
    return path


def test_page_is_the_tablet_format():
    w, h = page_size(RM2)
    assert (round(w, 1), round(h, 1)) == (447.3, 596.4)


def test_pdf_has_contents_links_and_boxes():
    wb = Workbook.model_validate(WORKBOOK)
    doc = pymupdf.open(stream=build_pdf(wb, RM2))
    assert doc.get_toc() == [[1, "Innehåll", 1], [1, "Bråk", 2], [1, "Procent", 3]]
    assert [ln["page"] for ln in doc[0].get_links()] == [1, 2]
    # back to the contents from each section, and on to the next one
    assert [ln["page"] for ln in doc[1].get_links()] == [0, 2]
    assert [ln["page"] for ln in doc[2].get_links()] == [0]
    assert [s.page for s in wb.sections] == [1, 2]
    for f in wb.fields():
        assert f.page in (1, 2) and f.rect[2] > f.rect[0] and f.rect[3] > f.rect[1]


def test_answers_are_pdf_text_and_keep_the_layout():
    wb = _wb()
    rects = [f.rect for f in wb.fields()]
    wb.field("s1f1").answer = "9"
    wb.field("s2f1").answer, wb.field("s2f1").confident = "20 kr", False
    doc = pymupdf.open(stream=build_pdf(wb, RM2))
    assert [f.rect for f in wb.fields()] == rects
    assert doc[1].search_for("9") and doc[2].search_for("20 kr")
    assert "?" in doc[2].get_text()


def test_long_sections_continue_on_new_pages():
    wb = Workbook.model_validate(
        {
            "name": "Lång",
            "sections": [
                {
                    "id": "s1",
                    "title": "Många frågor",
                    "fields": [
                        {"id": f"f{i}", "prompt": f"Fråga {i}", "lines": 6} for i in range(8)
                    ],
                }
            ],
        }
    )
    doc = pymupdf.open(stream=build_pdf(wb, RM2))
    assert doc.page_count > 2
    _, h = page_size(RM2)
    assert all(f.rect[3] < h - 40 for f in wb.fields())
    assert "(forts.)" in doc[2].get_text()


def test_plain_keeps_swedish_and_replaces_the_rest():
    assert plain("Åsa är 5½ år → x² ≈ π") == "Åsa är 5½ år -> x² ~ pi"
    assert plain("中") == "?"
    assert plain("Bråk – åk 5 “svar” …") == 'Bråk - åk 5 "svar" ...'


def test_revision_is_a_pdf_document(tmp_path):
    wb = _wb()
    path = workflow.build_revision(wb, tmp_path / "r01", RM2, seed=1)
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        content = json.loads(zf.read(next(n for n in names if n.endswith(".content"))))
        meta = json.loads(zf.read(next(n for n in names if n.endswith(".metadata"))))
    assert content["fileType"] == "pdf"
    assert [p["redir"]["value"] for p in content["cPages"]["pages"]] == [0, 1, 2]
    assert sum(n.endswith(".pdf") for n in names) == 1
    assert not any(n.endswith(".rm") for n in names)  # no ink yet
    assert meta["visibleName"] == "Bråk r01"


def test_ink_is_sorted_into_boxes(tmp_path):
    wb = _wb()
    page = wb.field("s1f2").page
    tap = Stroke(np.array([(1300.0, 100.0), (1301.0, 101.0)]))  # on the contents link
    note = Stroke(np.linspace((100, 1800), (400, 1800), 10))  # below the boxes
    synced = _synced(wb, tmp_path, {page: [_writing_in(wb, "s1f2"), tap, note]})
    ink = read_ink(synced.read_bytes(), RM2)
    marks = sort_ink(ink, wb, RM2)
    assert list(marks.by_field) == ["s1f2"]
    assert [len(s) for s in marks.loose[page]] == [10]
    assert ink.added_pages == 0


def test_read_handwriting_goes_to_a_hidden_layer(tmp_path):
    wb = _wb()
    f = wb.field("s1f1")
    marks = Sorted(by_field={"s1f1": [_writing_in(wb, "s1f1")]})
    f.answer = "9"
    path = workflow.build_revision(wb, tmp_path / "r02", RM2, marks, {"s1f1"}, "keep")
    ink = read_ink(path.read_bytes(), RM2)
    assert [s.layer for s in ink.pages[f.page]] == [HANDWRITING_LAYER]
    with zipfile.ZipFile(path) as zf:
        rm = next(n for n in zf.namelist() if n.endswith(".rm"))
        layers = rmscene.read_tree(io.BytesIO(zf.read(rm))).root.children.values()
    assert {g.label.value: g.visible.value for g in layers} == {
        "Layer 1": True,
        HANDWRITING_LAYER: False,
    }
    # The next round sees it as already read.
    assert not sort_ink(ink, wb, RM2).by_field

    removed = workflow.build_revision(wb, tmp_path / "r02b", RM2, marks, {"s1f1"}, "remove")
    assert not read_ink(removed.read_bytes(), RM2).pages


def test_ink_claude_could_not_read_stays(tmp_path):
    wb = _wb()
    marks = Sorted(by_field={"s1f1": [_writing_in(wb, "s1f1")]})
    path = workflow.build_revision(wb, tmp_path / "r02", RM2, marks, set(), "remove")
    page = read_ink(path.read_bytes(), RM2).pages[wb.field("s1f1").page]
    assert [s.layer for s in page] == ["Layer 1"]


def _answers(*entries):
    return [
        ([_tool("t1", "save_answers", {"answers": list(entries)})], "tool_use"),
    ]


def test_round_sets_the_answers(tmp_path):
    store = FileStore(tmp_path / "d")
    wb = _wb()
    store.save_workbook(wb)
    synced = _synced(
        wb,
        tmp_path,
        {1: [_writing_in(wb, "s1f1"), _writing_in(wb, "s1f2")], 2: [_writing_in(wb, "s2f1")]},
        name="Bråk r01",
    )
    store.link(str(synced), "workbook:Bråk")
    client = FakeClient(
        _answers(
            {"id": "s1f1", "text": "9", "confident": True},
            {"id": "s1f2", "text": "12/4 = 3, 3*3 = 9", "confident": False},
            {"id": "s2f1", "text": "", "confident": False},
        )
    )
    r = run_round(str(synced), None, store, client=client, send=False)
    request = client.requests[0]
    images = [b for b in request["messages"][0]["content"] if b["type"] == "image"]
    assert len(images) == 3
    assert r.revision == 2 and r.sent_as is None
    assert r.open_questions == ["Förklara hur du tänkte. → 12/4 = 3, 3*3 = 9"]
    saved = store.load_workbook("Bråk")
    assert saved.field("s1f1").answer == "9"
    assert saved.field("s2f1").answer == ""
    assert "1 gick inte att läsa" in saved.log[-1]


def test_round_sends_bad_answers_back(tmp_path):
    store = MemoryStore()
    wb = _wb()
    store.save_workbook(wb)
    synced = _synced(wb, tmp_path, {1: [_writing_in(wb, "s1f1")]}, name="Bråk r01")
    client = FakeClient(
        _answers({"id": "nope", "text": "9", "confident": True})
        + _answers({"id": "s1f1", "text": "9", "confident": True})
    )
    r = run_round(str(synced), "rm2", store, client=client, send=False)
    assert r.revision == 2
    error = client.requests[1]["messages"][-1]["content"][0]
    assert error["is_error"] and "nope" in error["content"]
    assert "workbook:bråk" in store.changed


def test_round_without_new_ink(tmp_path):
    store = FileStore(tmp_path / "d")
    wb = _wb()
    store.save_workbook(wb)
    synced = _synced(wb, tmp_path, {}, name="Bråk r01")
    with pytest.raises(RoundError, match="Inget nytt"):
        run_round(str(synced), "rm2", store, client=FakeClient([]), send=False)


def test_find_workbook_tells_drawings_apart(tmp_path):
    store = FileStore(tmp_path / "d")
    store.save_workbook(_wb())
    store.link("/rmink/Altan/Altan r02", "Altan")
    assert find_workbook("/rmink/Bråk/Bråk r03 · 1 att kolla", store).name == "Bråk"
    assert find_workbook("/rmink/Altan/Altan r02", store) is None
    store.link("/rmink/X/Prov", "workbook:Bråk")
    assert find_workbook("/rmink/X/Prov", store).name == "Bråk"


def test_create_and_answer_in_the_cloud(tmp_path, monkeypatch):
    fake = FakeCloud(monkeypatch, {"/": {"rmink"}, "/rmink": set()})
    store = FileStore(tmp_path / "d")
    created = create_workbook(
        "Bråk för åk 5",
        "rm2",
        store,
        client=FakeClient(
            [
                ([_block(type="text", text="Here goes.")], "end_turn"),
                ([_tool("c1", "write_workbook", WORKBOOK)], "tool_use"),
            ]
        ),
    )
    assert created.sent_as == "/rmink/Bråk/Bråk r01"
    assert pymupdf.open(stream=created.preview_png)  # a picture of the cover
    with pytest.raises(RoundError, match="redan"):
        again = FakeClient([([_tool("c1", "write_workbook", WORKBOOK)], "tool_use")])
        create_workbook("igen", "rm2", store, client=again)

    wb = store.load_workbook("Bråk")
    fake.documents[created.sent_as] = _synced(
        wb, tmp_path, {1: [_writing_in(wb, "s1f1")]}
    ).read_bytes()
    r = run_round(
        "Bråk",
        None,
        store,
        client=FakeClient(_answers({"id": "s1f1", "text": "9", "confident": False})),
    )
    assert r.sent_as == "/rmink/Bråk/Bråk r02 · 1 att kolla"
    assert "Bråk r01" in fake.folders["/rmink/Bråk/Tidigare"]
    assert store.linked("/rmink/Bråk/Tidigare/Bråk r01") == "workbook:Bråk"
    assert store.load_workbook("Bråk").document == "/rmink/Bråk/Bråk r01"


def test_mcp_workbook_round(tmp_path):
    import anyio
    from mcp import Client

    from rmink.mcp_server import server

    out = tmp_path / "Bråk.rmdoc"

    async def run():
        async with Client(server, raise_exceptions=True) as client:
            res = await client.call_tool(
                "create_workbook", {"workbook": WORKBOOK, "output_path": str(out)}
            )
            assert not res.is_error, res
            assert json.loads(res.content[0].text)["revision"] == 1

            wb = FileStore().load_workbook("Bråk")
            synced = _synced(wb, tmp_path, {1: [_writing_in(wb, "s1f1")]}, name="Bråk r01")
            res = await client.call_tool("read_workbook", {"document": str(synced)})
            assert [c.type for c in res.content] == ["text", "image"]
            assert "s1f1" in res.content[0].text

            res = await client.call_tool(
                "save_workbook_answers",
                {
                    "document": str(synced),
                    "answers": [{"id": "s1f1", "text": "9", "confident": True}],
                    "ink": "keep",
                    "output_path": str(tmp_path / "r02"),
                },
            )
            assert not res.is_error, res
            assert json.loads(res.content[0].text)["revision"] == 2

    anyio.run(run)
    assert FileStore().load_workbook("Bråk").field("s1f1").answer == "9"
    assert (tmp_path / "r02.rmdoc").exists()


def test_web_create_and_round(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    anthropic = pytest.importorskip("anthropic")
    from fastapi.testclient import TestClient

    from rmink.web.app import Limits, create_app

    monkeypatch.setenv("RMINK_ROUNDS_SECRET", "s3cret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake = FakeCloud(monkeypatch, {"/": {"rmink"}, "/rmink": set()})
    turns = [([_tool("c1", "write_workbook", WORKBOOK)], "tool_use")]
    turns += _answers({"id": "s1f1", "text": "9", "confident": True})
    claude = FakeClient(turns)
    monkeypatch.setattr(anthropic, "Anthropic", lambda: claude)
    client = TestClient(create_app(Limits(2_000_000, 3, 5, 60, 1)))
    auth = {"X-Rmink-Secret": "s3cret"}

    assert (
        client.post("/api/workbook/create", json={"topic": "Bråk"}, headers={}).status_code == 401
    )
    r = client.post("/api/workbook/create", json={"topic": "Bråk för åk 5"}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["sent_as"] == "/rmink/Bråk/Bråk r01"
    memory = r.json()["store"]
    assert memory["links"] == {"rmink/Bråk/Bråk r01": "workbook:Bråk"}

    wb = Workbook.model_validate_json(memory["drawings"]["workbook:bråk"])
    build_pdf(wb, RM2)
    fake.documents["/rmink/Bråk/Bråk r01"] = _synced(
        wb, tmp_path, {1: [_writing_in(wb, "s1f1")]}
    ).read_bytes()
    body = {"document": "/rmink/Bråk/Bråk r01", "ink": "keep", **memory}
    r = client.post("/api/rounds/run", json=body, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["sent_as"] == "/rmink/Bråk/Bråk r02"
    saved = Workbook.model_validate_json(r.json()["store"]["drawings"]["workbook:bråk"])
    assert saved.field("s1f1").answer == "9"
    kept = read_ink(fake.documents["/rmink/Bråk/Bråk r02"], RM2)
    assert {s.layer for s in kept.pages[1]} == {HANDWRITING_LAYER}


def test_tick_confirms_an_unsure_answer(tmp_path):
    store = FileStore(tmp_path / "d")
    wb = _wb()
    f = wb.field("s1f2")
    f.answer, f.confident, wb.revision = "3 < 5", False, 2
    store.save_workbook(wb)
    cover = pymupdf.open(stream=build_pdf(wb, RM2))[0].get_text()
    assert "sätt en bock" in cover
    assert workflow.revision_title(wb) == "Bråk r02 · 1 att kolla"

    tick = Stroke(np.array([(300.0, 0.0), (330.0, 30.0), (400.0, -40.0)]))
    tick.points += _writing_in(wb, "s1f2").points[0]
    synced = _synced(wb, tmp_path, {f.page: [tick]}, name="Bråk r02 · 1 att kolla")
    client = FakeClient(_answers({"id": "s1f2", "text": "3 < 5", "confident": True}))
    r = run_round(str(synced), None, store, client=client, send=False)
    assert "Earlier answer" in client.requests[0]["messages"][0]["content"][0]["text"]
    assert "tick" in client.requests[0]["system"]
    saved = store.load_workbook("Bråk")
    assert saved.field("s1f2").confident and not r.open_questions
    assert workflow.revision_title(saved) == "Bråk r03"
    assert "sätt en bock" not in pymupdf.open(stream=build_pdf(saved, RM2))[0].get_text()


def _solved(mode: str) -> Workbook:
    data = json.loads(json.dumps(WORKBOOK))
    data["mode"] = mode
    solutions = {"s1f1": "12/4 = 3, 3*3 = 9", "s1f2": "Dela i fyra delar och ta tre.", "s2f1": "20"}
    for s in data["sections"]:
        for f in s["fields"]:
            f["solution"] = solutions[f["id"]]
    data["sections"][0]["fields"][1]["points"] = 2
    wb = Workbook.model_validate(data)
    build_pdf(wb, RM2)
    return wb


def _layers(path):
    with zipfile.ZipFile(path) as zf:
        out = {}
        for n in zf.namelist():
            if n.endswith(".rm"):
                for g in rmscene.read_tree(io.BytesIO(zf.read(n))).root.children.values():
                    out[g.label.value] = g.visible.value
        return out


def test_practice_has_hidden_solutions_from_the_start(tmp_path):
    wb = _solved("practice")
    path = workflow.build_revision(wb, tmp_path / "r01", RM2)
    assert _layers(path) == {"Layer 1": True, "Facit": False}
    ink = read_ink(path.read_bytes(), RM2)
    facit = [s for s in ink.pages[1] if s.layer == "Facit"]
    assert facit
    # The solution ink sits under its box, and is never read as an answer.
    box = wb.field("s1f1").rect
    assert min(float(s.points[:, 1].min()) for s in facit) * 72 / RM2.dpi > box[3]
    assert not sort_ink(ink, wb, RM2).by_field
    assert "Facit" in pymupdf.open(stream=build_pdf(wb, RM2))[1].get_text()


def test_test_mode_has_no_solutions_before_grading(tmp_path):
    wb = _solved("test")
    path = workflow.build_revision(wb, tmp_path / "r01", RM2)
    assert not read_ink(path.read_bytes(), RM2).pages
    assert "Facit" not in pymupdf.open(stream=build_pdf(wb, RM2))[1].get_text()


def test_round_grades_and_adds_results(tmp_path):
    store = FileStore(tmp_path / "d")
    wb = _solved("test")
    store.save_workbook(wb)
    synced = _synced(
        wb,
        tmp_path,
        {1: [_writing_in(wb, "s1f1"), _writing_in(wb, "s1f2")], 2: [_writing_in(wb, "s2f1")]},
        name="Bråk r01",
    )
    client = FakeClient(
        # The first try leaves out a grade and is sent back.
        _answers(
            {"id": "s1f1", "text": "9", "confident": True, "verdict": ""},
            {"id": "s1f2", "text": "x", "confident": True, "verdict": "wrong"},
            {"id": "s2f1", "text": "20", "confident": True, "verdict": "correct"},
        )
        + _answers(
            {"id": "s1f1", "text": "9", "confident": True, "verdict": "correct", "awarded": 1},
            {
                "id": "s1f2",
                "text": "tre fjärdedelar",
                "confident": True,
                "verdict": "partial",
                "awarded": 1,
                "comment": "Förklara hur du delar.",
            },
            {"id": "s2f1", "text": "25", "confident": True, "verdict": "wrong", "awarded": 0},
        )
    )
    r = run_round(str(synced), None, store, client=client, send=False)
    assert "Solution (2 p)" in json.dumps(client.requests[0]["messages"][0]["content"][2:4])
    assert "grade the answer" in client.requests[1]["messages"][-1]["content"][0]["content"]
    saved = store.load_workbook("Bråk")
    assert saved.score() == (2.0, 4)
    assert workflow.revision_title(saved) == "Bråk r02 · 2 av 4 p"
    assert "2 av 4 poäng" in r.summary

    doc = pymupdf.open(stream=build_pdf(saved, RM2))
    assert doc.get_toc()[-1] == [1, "Resultat", doc.page_count]
    results = doc[-1]
    text = results.get_text()
    assert "2 av 4 poäng (50 %)" in text and "Förklara hur du delar." in text
    assert [ln["page"] for ln in results.get_links()] == [0, 1, 1, 2]
    assert "Resultat" in doc[0].get_text()
    # Now the test is graded, its solutions are on the tablet.
    path = workflow.build_revision(saved, tmp_path / "r02", RM2)
    assert _layers(path)["Facit"] is False
