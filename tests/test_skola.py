"""rmink skola: the catalogue of groups and topics, and workbooks in a group's folder."""

import pytest
from test_rounds import FakeClient, FakeCloud, _tool
from test_workbook import WORKBOOK, _answers, _synced, _writing_in

from rmink.drawing.agent import RoundError
from rmink.drawing.store import FileStore
from rmink.workbook import catalog, workflow
from rmink.workbook.agent import create_workbook, find_workbook, run_round
from rmink.workbook.model import Workbook


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for key in ("RMINK_CLOUD_TOKEN", "UPSTASH_REDIS_REST_URL", "KV_REST_API_URL"):
        monkeypatch.delenv(key, raising=False)


def test_catalogue_is_valid():
    groups = catalog.load()
    assert {g.title for g in groups} >= {"Plus och minus", "Bråk och division"}
    assert len({g.id for g in groups}) == len(groups)
    for g in groups:
        assert g.topic, g.id
        assert len({t.id for t in g.topic}) == len(g.topic), g.id
        for t in g.topic:
            assert t.grades and all(1 <= n <= 9 for n in t.grades), t.id
            assert t.grades == sorted(t.grades), t.id
            assert len(t.brief) > 80, t.id
            # The workbook PDF is Latin-1: keep the briefs to it as well.
            t.brief.encode("latin-1")


def test_topic_request():
    text = catalog.topic_request("brak-division", "forlanga-forkorta", 5, "Med pizzor.")
    assert "Förlänga och förkorta (Bråk och division)" in text
    assert "1/2 = 2/4" in text
    assert "årskurs 5" in text
    assert text.endswith("Med pizzor.")
    mixed = catalog.topic_request("Plus och minus")
    assert "Negativa tal" in mixed and "årskurs" not in mixed
    with pytest.raises(ValueError, match="plus-minus"):
        catalog.group("geometri")
    with pytest.raises(ValueError, match="forkorta"):
        catalog.topic_request("brak-division", "pizza")


def test_workbook_folder():
    wb = Workbook(name="Bråk åk 5", area="Skola", group="Bråk och division")
    assert workflow.workbook_folder(wb) == "/rmink/Skola/Bråk och division/Bråk åk 5"
    assert workflow.workbook_folder(Workbook(name="Bråk")) == "/rmink/Bråk"


def test_create_in_a_group_and_answer(tmp_path, monkeypatch):
    fake = FakeCloud(monkeypatch, {"/": {"rmink"}, "/rmink": set()})
    store = FileStore(tmp_path / "d")
    client = FakeClient([([_tool("c1", "write_workbook", WORKBOOK)], "tool_use")])
    created = create_workbook(
        "",
        "rm2",
        store,
        client=client,
        group="brak-division",
        topic_id="brak-av-antal",
        grade=4,
    )
    request = client.requests[0]["messages"][0]["content"][0]["text"]
    assert "Bråk av ett antal" in request and "årskurs 4" in request
    folder = "/rmink/Skola/Bråk och division/Bråk"
    assert created.sent_as == f"{folder}/Bråk r01"
    wb = store.load_workbook("Bråk")
    assert (wb.area, wb.group) == ("Skola", "Bråk och division")

    fake.documents[created.sent_as] = _synced(
        wb, tmp_path, {1: [_writing_in(wb, "s1f1")]}
    ).read_bytes()
    r = run_round(
        created.sent_as,
        None,
        store,
        client=FakeClient(_answers({"id": "s1f1", "text": "9", "confident": True})),
    )
    assert r.sent_as == f"{folder}/Bråk r02"
    assert "Bråk r01" in fake.folders[f"{folder}/Tidigare"]
    # Without the link, the nearest folder still names the workbook.
    assert find_workbook(f"{folder}/Tidigare/Bråk r01_2", FileStore(tmp_path / "d")).name == "Bråk"


def test_unknown_group_costs_no_call(tmp_path):
    client = FakeClient([])
    with pytest.raises(RoundError, match="ingen grupp"):
        create_workbook("", "rm2", FileStore(tmp_path / "d"), client=client, group="geometri")
    assert client.requests == []


def test_web_catalog(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from rmink.web.app import Limits, create_app

    monkeypatch.setenv("RMINK_ROUNDS_SECRET", "s3cret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    client = TestClient(create_app(Limits(2_000_000, 3, 5, 60, 1)))
    assert client.get("/api/workbook/catalog").status_code == 401
    r = client.get("/api/workbook/catalog", headers={"X-Rmink-Secret": "s3cret"})
    assert r.status_code == 200
    group = next(g for g in r.json() if g["id"] == "plus-minus")
    assert group["topics"][0]["id"] == "talkamrater" and "brief" not in group["topics"][0]
    monkeypatch.setenv("RMINK_CLOUD_TOKEN", "tok")
    auth = {"X-Rmink-Secret": "s3cret"}
    r = client.post("/api/workbook/create", json={"topic": ""}, headers=auth)
    assert r.status_code == 422


def test_move_into_a_group(tmp_path, monkeypatch):
    fake = FakeCloud(monkeypatch, {"/": {"rmink"}, "/rmink": set()})
    store = FileStore(tmp_path / "d")
    client = FakeClient([([_tool("c1", "write_workbook", WORKBOOK)], "tool_use")])
    created = create_workbook("Bråk för åk 5", "rm2", store, client=client)
    wb = store.load_workbook("Bråk")
    fake.documents[created.sent_as] = _synced(
        wb, tmp_path, {1: [_writing_in(wb, "s1f1")]}
    ).read_bytes()
    run_round(
        "Bråk",
        None,
        store,
        client=FakeClient(_answers({"id": "s1f1", "text": "9", "confident": True})),
    )

    folder = workflow.move_to_group(
        store.load_workbook("Bråk"), "Skola", "Bråk och division", "tok", store
    )
    assert folder == "/rmink/Skola/Bråk och division/Bråk"
    assert "Bråk" not in fake.folders["/rmink"]
    assert fake.folders[f"{folder}/Tidigare"] == {"Bråk r01"}
    moved = store.load_workbook("Bråk")
    assert (moved.group, moved.sent_as) == ("Bråk och division", f"{folder}/Bråk r02")
    assert moved.document == f"{folder}/Bråk r01"
    assert store.linked(f"{folder}/Tidigare/Bråk r01") == "workbook:Bråk"
    assert workflow.move_to_group(moved, "Skola", "Bråk och division", "tok", store) == folder

    # The next round reads the moved revision and files it in the new folder.
    fake.documents[moved.sent_as] = _synced(
        moved, tmp_path, {moved.field("s2f1").page: [_writing_in(moved, "s2f1")]}, name="again"
    ).read_bytes()
    r = run_round(
        "Bråk",
        None,
        store,
        client=FakeClient(_answers({"id": "s2f1", "text": "20", "confident": True})),
    )
    assert r.sent_as == f"{folder}/Bråk r03"
    assert fake.folders[f"{folder}/Tidigare"] == {"Bråk r01", "Bråk r02"}


def test_web_move_into_a_group(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from rmink.drawing.store import MemoryStore
    from rmink.web.app import Limits, create_app

    monkeypatch.setenv("RMINK_ROUNDS_SECRET", "s3cret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake = FakeCloud(monkeypatch, {"/": {"rmink"}, "/rmink": set()})
    browser = MemoryStore()
    client = FakeClient([([_tool("c1", "write_workbook", WORKBOOK)], "tool_use")])
    create_workbook("Plus och minus", "rm2", browser, client=client)
    memory = {"drawings": browser.drawings, "links": browser.links}
    app = TestClient(create_app(Limits(2_000_000, 3, 5, 60, 1)))
    auth = {"X-Rmink-Secret": "s3cret"}

    body = {"name": "Bråk", "group": "plus-minus", **memory}
    r = app.post("/api/workbook/move", json=body, headers=auth)
    assert r.status_code == 200, r.text
    folder = "/rmink/Skola/Plus och minus/Bråk"
    assert r.json()["folder"] == folder
    assert fake.folders[folder] == {"Bråk r01"}
    back = r.json()["store"]
    assert back["links"]["rmink/Skola/Plus och minus/Bråk/Bråk r01"] == "workbook:Bråk"
    moved = Workbook.model_validate_json(back["drawings"]["workbook:bråk"])
    assert (moved.group, moved.sent_as) == ("Plus och minus", f"{folder}/Bråk r01")

    missing = app.post("/api/workbook/move", json=body | {"name": "Nej"}, headers=auth)
    assert missing.status_code == 404
    bad = app.post("/api/workbook/move", json=body | {"group": "geometri"}, headers=auth)
    assert bad.status_code == 422
