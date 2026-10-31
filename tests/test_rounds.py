import json
from types import SimpleNamespace

import numpy as np
import pytest

from rmink import cloud
from rmink.devices import get_device
from rmink.drawing import workflow
from rmink.drawing.agent import RoundError, run_round
from rmink.drawing.font import text_paths
from rmink.drawing.model import Annotation, Drawing
from rmink.drawing.render import COMMENT_LAYER, render_drawing
from rmink.drawing.store import FileStore, RedisStore, guess_drawing_name
from rmink.ingest.rm import read_rmdoc
from rmink.model import Page, Stroke
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.writer.rm_v6 import write_page

RM2 = get_device("rm2")


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for key in (
        "RMINK_CLOUD_TOKEN",
        "UPSTASH_REDIS_REST_URL",
        "KV_REST_API_URL",
        "BLOB_READ_WRITE_TOKEN",
        "BLOB_STORE_ID",
    ):
        monkeypatch.delenv(key, raising=False)


def _write(path, name, page):
    uu = UuidFactory(4)
    author = uu()
    write_rmdoc(
        path, name, [RmdocPage(write_page(page, RM2, author))], [str(uu())], author, RM2, str(uu())
    )
    return path


@pytest.fixture
def sketch(tmp_path):
    strokes = [
        Stroke(np.linspace((200, 300), (1200, 300), 30)),
        Stroke(np.linspace((1200, 300), (1200, 1000), 30)),
        Stroke(np.linspace((1200, 1000), (200, 1000), 30)),
        Stroke(np.linspace((200, 1000), (200, 300), 30)),
    ]
    strokes += [Stroke(p) for p in text_paths("4800", (640, 260), 34)]
    return _write(tmp_path / "Altan.rmdoc", "Altan", Page(RM2.width, RM2.height, strokes))


DRAWING = {
    "name": "anything",
    "elements": [
        {"id": "V1", "kind": "rect", "points": [[200, 300], [1200, 1000]], "category": "structure"}
    ],
    "dimensions": [{"id": "M1", "start": [200, 300], "end": [1200, 300], "text": "4800"}],
}


def _block(**kw):
    return SimpleNamespace(**kw)


def _tool(id_, name, args):
    return _block(type="tool_use", id=id_, name=name, input=args)


class FakeClient:
    """Plays back a fixed list of assistant turns and records each request."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kw):
        # Snapshot: the round keeps appending to the same list.
        self.requests.append(kw | {"messages": list(kw["messages"])})
        content, stop = self.turns.pop(0)
        response = SimpleNamespace(
            content=content,
            stop_reason=stop,
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0),
        )  # fmt: skip

        class Ctx:
            def __enter__(self):
                return SimpleNamespace(get_final_message=lambda: response)

            def __exit__(self, *a):
                return False

        return Ctx()


def _turns(drawing=DRAWING):
    return [
        ([_tool("t1", "render_preview", {"drawing": drawing})], "tool_use"),
        ([_tool("t2", "save_revision", {"drawing": drawing, "summary": "Renritad."})], "tool_use"),
        ([_block(type="text", text="Klart.")], "end_turn"),
    ]  # fmt: skip


def test_guess_drawing_name():
    assert guess_drawing_name("/Projekt/Altan r2_2") == "Altan"
    assert guess_drawing_name("/tmp/Altan r1.rmdoc") == "Altan"
    assert guess_drawing_name("Altan") == "Altan"
    assert guess_drawing_name("/rmink/Altan/Altan r03 · 2 frågor") == "Altan"
    assert guess_drawing_name("/rmink/Altan/Tidigare/Altan r12 · 1 fråga_2") == "Altan"
    assert guess_drawing_name(r"C:\Users\me\AppData\Local\Temp\x\Altan.rmdoc") == "Altan"
    assert guess_drawing_name("C:\\ritningar\\Garage r02.rmdoc") == "Garage"
    assert guess_drawing_name("/rmink/Altan/Tidigare/Altan r00 skiss") == "Altan"
    assert guess_drawing_name("/rmink/Bastu/Bastuskiss") == "Bastu"
    school = "/rmink/Skola/Bråk och division/Bråk åk5"
    assert guess_drawing_name(f"{school}/Bråk åk5 r02 · 3 av 4 p") == "Bråk åk5"
    assert guess_drawing_name(f"{school}/Tidigare/Bråk åk5 r01") == "Bråk åk5"


def test_revision_title():
    d = Drawing(name="Plan 1/2", revision=3)
    assert workflow.revision_title(d) == "Plan 1-2 r03"
    assert workflow.drawing_folder("Plan 1/2") == "/rmink/Plan 1-2"
    d.annotations = [Annotation(id="a1", kind="note", text="Höjd?")]
    assert workflow.revision_title(d) == "Plan 1-2 r03 · 1 fråga"
    d.annotations += [
        Annotation(id="a2", kind="circle", text="Bredd?"),
        Annotation(id="a3", kind="cross", text="Klar", status="accepted"),
    ]
    d.revision = 12
    assert workflow.revision_title(d) == "Plan 1-2 r12 · 2 frågor"


def test_first_round(sketch, tmp_path):
    store = FileStore(tmp_path / "drawings")
    client = FakeClient(_turns())
    r = run_round(str(sketch), "rm2", store, client=client, send=False)
    assert (r.drawing, r.revision, r.summary) == ("Altan", 1, "Renritad.")
    assert r.preview_png[:4] == b"\x89PNG" and r.usage["usd"] > 0
    saved = store.load("Altan")
    assert saved.revision == 1 and saved.sketch.written_ids
    # The first request carries the sketch picture and the groups; tool
    # results carry the preview picture.
    first = client.requests[0]["messages"][0]["content"]
    assert [c["type"] for c in first] == ["text", "image", "text"]
    assert "First round" in first[0]["text"]
    preview_result = client.requests[1]["messages"][-1]["content"][0]
    assert preview_result["content"][0]["type"] == "image"
    assert client.requests[0]["fallbacks"] == "default"


def test_second_round_reads_only_new_marks(sketch, tmp_path):
    store = FileStore(tmp_path / "drawings")
    run_round(str(sketch), "rm2", store, client=FakeClient(_turns()), send=False)
    saved = store.load("Altan")
    rev = workflow.build_revision(
        saved, tmp_path / "Altan r1.rmdoc", store=FileStore(tmp_path / "x")
    )
    clean = read_rmdoc(rev.path, RM2).pages[0]
    t = np.linspace(0, 2 * np.pi, 40)
    ring = Stroke(
        np.column_stack([1200 + 50 * np.cos(t), 1000 + 50 * np.sin(t)]), layer=COMMENT_LAYER
    )
    marked = Page(clean.width, clean.height, clean.strokes + [ring], clean.layer_names)
    doc = _write(tmp_path / "Altan r1 marked.rmdoc", "Altan r1", marked)
    store.link(str(doc), "Altan")

    client = FakeClient(_turns())
    r = run_round(str(doc), "rm2", store, client=client, send=False)
    assert r.revision == 2
    first = client.requests[0]["messages"][0]["content"]
    assert "Round 2" in first[0]["text"] and '"groups": [{' in first[2]["text"]
    assert first[2]["text"].count('"group":') == 1  # only the ring


def test_no_new_marks(sketch, tmp_path):
    store = FileStore(tmp_path / "drawings")
    run_round(str(sketch), "rm2", store, client=FakeClient(_turns()), send=False)
    saved = store.load("Altan")
    rev = workflow.build_revision(
        saved, tmp_path / "Altan r1.rmdoc", store=FileStore(tmp_path / "x")
    )
    store.link(str(rev.path), "Altan")
    with pytest.raises(RoundError, match="Inga nya"):
        run_round(str(rev.path), "rm2", store, client=FakeClient([]), send=False)


def test_invalid_drawing_is_reported_back(sketch, tmp_path):
    turns = [
        (
            [_block(type="tool_use", id="t1", name="render_preview", input={"drawing": {"x": 1}})],
            "tool_use",
        )
    ]
    turns += _turns()
    client = FakeClient(turns)
    run_round(str(sketch), "rm2", FileStore(tmp_path / "d"), client=client, send=False)
    error = client.requests[1]["messages"][-1]["content"][0]
    assert error["is_error"] is True


def test_round_has_building_knowledge(sketch, tmp_path):
    turns = [([_tool("k1", "lookup_knowledge", {"query": "gips 13"})], "tool_use")]
    client = FakeClient(turns + _turns())
    run_round(str(sketch), "rm2", FileStore(tmp_path / "d"), client=client, send=False)
    first = client.requests[0]
    assert "lookup_knowledge" in {t["name"] for t in first["tools"]}
    reference = first["system"][1]
    assert "gips_a" in reference["text"] and reference["cache_control"]
    result = client.requests[1]["messages"][-1]["content"][0]
    assert result["is_error"] is False and '"gips_a"' in result["content"]


def test_round_calculates_and_measures(sketch, tmp_path):
    turns = [
        ([_tool("c1", "calculate", {"expression": "count(4800, 600)"})], "tool_use"),
        ([_tool("m1", "measure", {"ids": ["V1"]})], "tool_use"),
        ([_tool("c2", "calculate", {"expression": "x"})], "tool_use"),
    ]
    client = FakeClient(_turns()[:1] + turns + _turns()[1:])
    run_round(str(sketch), "rm2", FileStore(tmp_path / "d"), client=client, send=False)
    assert {"calculate", "measure"} <= {t["name"] for t in client.requests[0]["tools"]}
    assert "never work out angles" in client.requests[0]["system"][0]["text"]
    results = [r["messages"][-1]["content"][0] for r in client.requests[2:5]]
    assert results[0]["content"] == "9" and not results[0]["is_error"]
    measured = json.loads(results[1]["content"])
    assert measured["items"][0]["area"] == pytest.approx(4800 * 3360)
    assert results[2]["is_error"] and "unknown name" in results[2]["content"]


def test_round_shows_the_alternatives_page(sketch, tmp_path):
    from rmink import knowledge

    option = knowledge.lookup("pl1_a", kind="variant", limit=1)[0]["option"]
    drawing = {**DRAWING, "alternatives": [{"id": "x", "question": "Platta?", "options": [option]}]}
    client = FakeClient(_turns(drawing))
    run_round(str(sketch), "rm2", FileStore(tmp_path / "d"), client=client, send=False)
    assert "Alternatives:" in client.requests[0]["system"][0]["text"]
    result = client.requests[1]["messages"][-1]["content"][0]["content"]
    assert [b["type"] for b in result] == ["image", "image", "text"]


def test_redis_store(monkeypatch):
    data = {}

    def cmd(self, *args):
        if args[0] == "SET":
            data[args[1]] = args[2]
            return "OK"
        return data.get(args[1])

    monkeypatch.setattr(RedisStore, "__init__", lambda self, url, token: None)
    monkeypatch.setattr(RedisStore, "_cmd", cmd)
    store = RedisStore("https://x", "t")
    store.save(Drawing(name="Altan", revision=3))
    assert store.load("altan").revision == 3 and store.load("missing") is None
    store.link("/Altan r3", "Altan")
    assert store.linked("Altan r3") == "Altan"


def test_rounds_router(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from rmink.web.app import Limits, create_app

    limits = Limits(2_000_000, 3, 5, 60, 1)
    monkeypatch.delenv("RMINK_ROUNDS_SECRET", raising=False)
    assert TestClient(create_app(limits)).get("/rounds").status_code == 404

    monkeypatch.setenv("RMINK_ROUNDS_SECRET", "s3cret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("RMINK_CLOUD_TOKEN", "tok.en-1")
    client = TestClient(create_app(limits))
    assert client.get("/rounds").status_code == 200
    assert client.get("/api/rounds/documents").status_code == 401
    assert (
        client.get("/api/rounds/documents", headers={"X-Rmink-Secret": "nope"}).status_code == 401
    )

    listed = []

    def ls(token, path="/"):
        listed.append(path)
        return [cloud.Entry("Altan r1", False)]

    monkeypatch.setattr(cloud, "ls", ls)
    auth = {"X-Rmink-Secret": "s3cret"}
    r = client.get("/api/rounds/documents", headers=auth)
    assert r.json()["entries"] == [{"name": "Altan r1", "folder": False, "path": "/rmink/Altan r1"}]
    # The page reaches the rmink folder and nothing above or beside it.
    for path in ("/", "/Projekt", "/rminkx", "/rmink/../Projekt", "rmink/./x"):
        r = client.get("/api/rounds/documents", params={"path": path}, headers=auth)
        assert r.status_code == 403, path
    assert listed == ["/rmink"]

    def no_folder(token, path="/"):
        raise cloud.CloudNotFoundError(path)

    monkeypatch.setattr(cloud, "ls", no_folder)
    r = client.get("/api/rounds/documents?path=/rmink", headers={"X-Rmink-Secret": "s3cret"})
    assert r.status_code == 200 and r.json() == {"path": "/rmink", "entries": [], "missing": True}

    import rmink.drawing.agent as agent
    from rmink.drawing.store import MemoryStore

    fake = agent.RoundResult(
        "Altan r2", "Altan", 2, "Klart.", ["Vilken höjd?"], None, 12.0, {"usd": 0.4}
    )
    seen = {}

    def fake_round(document, device, store):
        # Without Redis the drawings come from the browser and go back to it.
        assert isinstance(store, MemoryStore)
        seen["previous"] = store.load("Altan")
        store.save(Drawing(name="Altan", revision=2))
        store.link("Altan r2", "Altan")
        return fake

    monkeypatch.setattr(agent, "run_round", fake_round)
    for document in ("/Altan r1", "/rmink", "Altan", "/rmink/../Altan r1", "/etc/passwd"):
        r = client.post("/api/rounds/run", json={"document": document}, headers=auth)
        assert r.status_code == 403, document
    body = {
        "document": "/rmink/Altan r1",
        "drawings": {"altan": Drawing(name="Altan", revision=1).model_dump_json()},
        "links": {"Altan r1": "Altan"},
    }
    r = client.post("/api/rounds/run", json=body, headers={"X-Rmink-Secret": "s3cret"})
    assert r.status_code == 200 and r.json()["sent_as"] == "Altan r2"
    assert seen["previous"].revision == 1
    back = r.json()["store"]
    assert Drawing.model_validate_json(back["drawings"]["altan"]).revision == 2
    assert back["links"] == {"Altan r1": "Altan", "Altan r2": "Altan"}


class FakeCloud:
    """The folders of a reMarkable Cloud, for the calls send_revision makes.

    ``folders`` maps each folder path to the names in it; a name is a folder
    when its path is a key too. Like rmapi, paths are looked up by name."""

    def __init__(self, monkeypatch, folders, documents=None):
        self.folders = {k: set(v) for k, v in folders.items()}
        self.documents = documents or {}
        self.calls = []
        self.fail_moves_to = None  # moves to paths containing this fail
        for name in ("ls", "mkdir", "put", "mv", "get"):
            monkeypatch.setattr(cloud, name, getattr(self, name))
        monkeypatch.setenv("RMINK_CLOUD_TOKEN", "tok.en-1")

    @staticmethod
    def _split(path):
        parent, _, name = path.rpartition("/")
        return parent or "/", name

    def ls(self, token, path="/"):
        if path not in self.folders:
            raise cloud.CloudNotFoundError(path)
        base = path.rstrip("/")
        return [cloud.Entry(n, f"{base}/{n}" in self.folders) for n in self.folders[path]]

    def mkdir(self, token, path):
        self.calls.append(("mkdir", path))
        parent, name = self._split(path)
        if parent not in self.folders:
            raise cloud.CloudError("directory doesn't exist")
        if name in self.folders[parent]:
            return  # a folder that is already there, or a notebook by that name
        self.folders[parent].add(name)
        self.folders[path] = set()

    def put(self, path, token, attempts=20, folder="/", name=None):
        self.calls.append(("put", folder, name))
        assert folder in self.folders, f"no folder {folder}"
        stem, n = name or path.stem, 2
        used = stem
        while used in self.folders[folder]:
            used, n = f"{stem}_{n}", n + 1
        self.folders[folder].add(used)
        self.documents[f"{folder}/{used}"] = path.read_bytes()
        return used

    def mv(self, token, src, dst):
        self.calls.append(("mv", src, dst))
        if self.fail_moves_to and self.fail_moves_to in dst:
            raise cloud.CloudError("boom")
        (sp, sn), (dp, dn) = self._split(src), self._split(dst)
        if dp not in self.folders:
            raise cloud.CloudError("directory doesn't exist")
        if dn in self.folders[dp]:
            raise cloud.CloudExistsError(dst)
        self.folders[sp].remove(sn)
        self.folders[dp].add(dn)
        # A folder moves with everything in it.
        for tree in (self.folders, self.documents):
            for key in [k for k in tree if k == src or k.startswith(src + "/")]:
                tree[dst + key[len(src) :]] = tree.pop(key)
        if dst not in self.folders:
            self.documents.setdefault(dst, b"")

    def get(self, token, path):
        return self.documents[path]


def _mark_up(rmdoc, tmp_path):
    """The revision with a ring drawn on it, as the tablet would sync it."""
    clean = read_rmdoc(rmdoc, RM2).pages[0]
    t = np.linspace(0, 2 * np.pi, 40)
    ring = Stroke(
        np.column_stack([1200 + 50 * np.cos(t), 1000 + 50 * np.sin(t)]), layer=COMMENT_LAYER
    )
    marked = Page(clean.width, clean.height, clean.strokes + [ring], clean.layer_names)
    return _write(tmp_path / "marked.rmdoc", "marked", marked).read_bytes()


def test_rounds_file_revisions_in_the_drawing_folder(sketch, tmp_path, monkeypatch):
    fake = FakeCloud(
        monkeypatch,
        {"/": {"rmink"}, "/rmink": {"Altan", "Garage"}},
        {"/rmink/Altan": sketch.read_bytes()},
    )
    store = FileStore(tmp_path / "drawings")
    with_question = DRAWING | {
        "annotations": [{"id": "a1", "kind": "circle", "targets": ["V1"], "text": "Höjd?"}]
    }
    r = run_round("/rmink/Altan", "rm2", store, client=FakeClient(_turns(with_question)))

    # A new drawing goes under rmink/Bygg; the sketch is filed under Tidigare.
    folder = "/rmink/Bygg/Altan"
    assert r.sent_as == f"{folder}/Altan r01 · 1 fråga"
    assert fake.folders["/rmink"] == {"Bygg", "Garage"}
    assert fake.folders[folder] == {"Altan r01 · 1 fråga", "Tidigare"}
    assert fake.folders[f"{folder}/Tidigare"] == {"Altan r00 skiss"}
    assert ("mv", "/rmink/Altan", f"{folder}/Tidigare/Altan r00 skiss") in fake.calls
    assert store.load("Altan").area == "Bygg"
    saved = store.load("Altan")
    assert saved.sketch.sent_as == r.sent_as and saved.date
    assert store.linked(r.sent_as) == "Altan"

    # The next round runs on the drawing's name, reads the latest revision and
    # moves it to Tidigare. The open remark is listed by its number on the page.
    fake.documents[r.sent_as] = _mark_up(fake.documents[r.sent_as], tmp_path)
    client = FakeClient(_turns())
    r2 = run_round("Altan", "rm2", store, client=client)
    intro = client.requests[0]["messages"][0]["content"][0]["text"]
    assert "Round 2" in intro and 'Open remarks on the page: 1 = a1 "Höjd?"' in intro
    assert r2.sent_as == f"{folder}/Altan r02"
    assert fake.folders[folder] == {"Altan r02", "Tidigare"}
    assert fake.folders[f"{folder}/Tidigare"] == {"Altan r00 skiss", "Altan r01 · 1 fråga"}
    assert store.linked(f"{folder}/Tidigare/Altan r01 · 1 fråga") == "Altan"


def test_a_sketch_in_its_own_folder_stays_in_that_folder(sketch, tmp_path, monkeypatch):
    fake = FakeCloud(
        monkeypatch,
        {"/": {"rmink"}, "/rmink": {"Bastu"}, "/rmink/Bastu": {"Bastuskiss"}},
        {"/rmink/Bastu/Bastuskiss": sketch.read_bytes()},
    )
    store = FileStore(tmp_path / "d")
    r = run_round("/rmink/Bastu/Bastuskiss", "rm2", store, client=FakeClient(_turns()))
    assert r.sent_as == "/rmink/Bastu/Bastu r01"
    assert fake.folders["/rmink"] == {"Bastu"}
    assert fake.folders["/rmink/Bastu"] == {"Bastu r01", "Tidigare"}
    assert fake.folders["/rmink/Bastu/Tidigare"] == {"Bastu r00 skiss"}


def test_notebooks_outside_rmink_stay_put(sketch, tmp_path, monkeypatch):
    fake = FakeCloud(monkeypatch, {"/": {"Altan"}}, {"/Altan": sketch.read_bytes()})
    r = run_round("/Altan", "rm2", FileStore(tmp_path / "d"), client=FakeClient(_turns()))
    assert r.sent_as == "/rmink/Bygg/Altan/Altan r01"
    assert fake.folders["/"] == {"Altan", "rmink"}
    assert not [c for c in fake.calls if c[0] == "mv"]
    assert ("mkdir", "/rmink") in fake.calls and ("mkdir", "/rmink/Bygg/Altan") in fake.calls


def test_a_failed_move_does_not_fail_the_round(sketch, tmp_path, monkeypatch):
    fake = FakeCloud(
        monkeypatch,
        {"/": {"rmink"}, "/rmink": {"Garage"}},
        {"/rmink/Garage": sketch.read_bytes()},
    )
    fake.fail_moves_to = "/Tidigare/"
    store = FileStore(tmp_path / "d")
    r = run_round("/rmink/Garage", "rm2", store, client=FakeClient(_turns()))
    assert r.sent_as == "/rmink/Bygg/Garage/Garage r01"
    assert store.load("Garage").sketch.sent_as == r.sent_as
    # The sketch could not be filed under Tidigare, so it stays in rmink.
    assert fake.folders["/rmink"] == {"Bygg", "Garage"}
    assert fake.folders["/rmink/Bygg/Garage"] == {"Garage r01", "Tidigare"}


def test_open_remarks_get_answer_lines():
    d = Drawing.model_validate(DRAWING)
    without = render_drawing(d, RM2)
    d.annotations = [
        Annotation(id="a1", kind="circle", targets=["V1"], text="Höjd?"),
        Annotation(id="a2", kind="cross", targets=["M1"], text="Stämmer måttet?"),
    ]
    with_remarks = render_drawing(d, RM2)
    # Rings, badges, the remark texts and three SVAR lines under each remark.
    answer_lines = [
        s for s in with_remarks.strokes
        if len(s.points) == 2 and s.points[0][1] == s.points[1][1] and s.width == 1.2
    ]  # fmt: skip
    assert len(answer_lines) == 2 * 3
    assert _bottom(with_remarks) - _bottom(without) > 2 * (66 + 2 * 66)


def _bottom(page):
    return max(float(s.points[:, 1].max()) for s in page.strokes)


def test_long_remarks_and_log_lines_wrap_instead_of_being_cut():
    from rmink.drawing.render import _wrap

    text = (
        "r1: Altan 4800×3600 på 6 plintar ritad från skissen, "
        "ca 480 från husväggen, med materialtext"
    )
    lines = _wrap(text, 16, 600, 3)
    assert len(lines) > 1 and " ".join(lines) == text
    assert _wrap("ord " * 200, 16, 600, 2)[-1].endswith("…")

    d = Drawing.model_validate(DRAWING)
    d.log = ["r1: kort"]
    short = render_drawing(d, RM2)
    d.log = [text * 2]
    assert _bottom(render_drawing(d, RM2)) - _bottom(short) >= 22


def test_a_small_sketch_is_enlarged_to_the_page():
    small = Drawing.model_validate(
        {
            "name": "Hus",
            "elements": [
                {"id": "V1", "kind": "rect", "points": [[400, 600], [900, 860]]},
                {"id": "T1", "kind": "text", "points": [[920, 560]], "text": "SKORSTEN"},
                {"id": "C1", "kind": "circle", "center": [500, 700], "radius": 20},
            ],
            "dimensions": [{"id": "M1", "start": [400, 860], "end": [900, 860], "text": "10"}],
            "symbols": [{"id": "S1", "kind": "door", "at": [600, 860], "size": 40}],
            "annotations": [{"id": "a1", "kind": "note", "at": [650, 700], "text": "?"}],
        }
    )
    fitted = workflow.fit_to_page(small, RM2)
    (x0, y0), (x1, y1) = fitted.elements[0].points
    k = (x1 - x0) / 500
    assert k > 1.5 and (y1 - y0) / 260 == pytest.approx(k, rel=0.01)
    # From the top: the highest text's cap line is at FIT_TOP.
    t = fitted.elements[1]
    assert t.points[0][1] - t.size == pytest.approx(workflow.FIT_TOP, abs=0.2)
    assert x0 >= workflow.FIT_MARGIN and x1 <= RM2.width - workflow.FIT_MARGIN
    # The text stays its size and on the page; the rest scales with the walls.
    from rmink.drawing.font import text_width

    t = fitted.elements[1]
    assert t.size == small.elements[1].size
    assert t.points[0][0] + text_width(t.text, t.size) <= RM2.width - workflow.FIT_MARGIN / 2
    assert fitted.elements[2].radius == pytest.approx(20 * k, rel=0.01)
    assert fitted.symbols[0].size == pytest.approx(40 * k, rel=0.01)
    assert fitted.dimensions[0].text == "10"
    assert fitted.annotations[0].at != small.annotations[0].at
    # Measurements come out the same, and fitting again changes nothing.
    before, after = (workflow.measure(d, ["V1"])["items"][0] for d in (small, fitted))
    assert after["length"] == pytest.approx(before["length"], rel=0.01)
    assert after["area"] == pytest.approx(before["area"], rel=0.02)
    assert workflow.fit_to_page(fitted, RM2) == fitted


def test_a_drawing_that_fills_the_page_is_left_alone():
    big = Drawing.model_validate(
        DRAWING | {"elements": [{"id": "V1", "kind": "rect", "points": [[100, 300], [1300, 900]]}]}
    )
    assert workflow.fit_to_page(big, RM2) == big


def test_new_area_follows_the_sketch():
    assert workflow.new_area("/rmink/Altan") == "Bygg"
    assert workflow.new_area("/Skisser/Altan") == "Bygg"
    assert workflow.new_area("/rmink/Bygg/Altan") == "Bygg"
    assert workflow.new_area("/rmink/Bygg/Altan/skiss") == "Bygg"
    assert workflow.new_area("/rmink/Garage/skiss") == ""  # a folder of its own
    assert workflow.drawing_folder("Altan", "Bygg") == "/rmink/Bygg/Altan"
    assert workflow.drawing_folder("Altan") == "/rmink/Altan"


def test_a_sketch_in_a_bygg_folder_gets_its_revisions_there(sketch, tmp_path, monkeypatch):
    fake = FakeCloud(
        monkeypatch,
        {"/": {"rmink"}, "/rmink": {"Bygg"}, "/rmink/Bygg": {"Bod"}, "/rmink/Bygg/Bod": {"skiss"}},
        {"/rmink/Bygg/Bod/skiss": sketch.read_bytes()},
    )
    r = run_round(
        "/rmink/Bygg/Bod/skiss", "rm2", FileStore(tmp_path / "d"), client=FakeClient(_turns())
    )
    assert r.sent_as == "/rmink/Bygg/Bod/Bod r01"
    assert fake.folders["/rmink/Bygg/Bod/Tidigare"] == {"Bod r00 skiss"}


def test_move_an_old_drawing_into_bygg_and_resend(sketch, tmp_path, monkeypatch):
    fake = FakeCloud(
        monkeypatch,
        {"/": {"rmink"}, "/rmink": {"Garage"}, "/rmink/Garage": {"skiss"}},
        {"/rmink/Garage/skiss": sketch.read_bytes()},
    )
    store = FileStore(tmp_path / "d")
    with_question = DRAWING | {
        "annotations": [{"id": "a1", "kind": "circle", "targets": ["V1"], "text": "Höjd?"}]
    }
    r = run_round("/rmink/Garage/skiss", "rm2", store, client=FakeClient(_turns(with_question)))
    assert r.sent_as == "/rmink/Garage/Garage r01 · 1 fråga"  # made before areas
    old = store.load("Garage")
    assert old.area == ""

    folder = workflow.move_to_area(old, "Bygg", "tok", store)
    assert folder == "/rmink/Bygg/Garage"
    assert "Garage" not in fake.folders["/rmink"]
    moved = store.load("Garage")
    assert moved.area == "Bygg" and moved.sketch.sent_as == f"{folder}/Garage r01 · 1 fråga"
    assert store.linked(f"{folder}/Tidigare/Garage r00 skiss") == "Garage"

    sent_as = workflow.resend(moved, "tok", store)
    assert sent_as == f"{folder}/Garage r02 · 1 fråga"
    assert fake.folders[f"{folder}/Tidigare"] == {"Garage r00 skiss", "Garage r01 · 1 fråga"}
    again = store.load("Garage")
    assert again.revision == 2 and again.log[-1].startswith("r2: ny layout")
    pages = read_rmdoc(fake.documents[sent_as], RM2).pages
    assert len(pages) == 2  # the drawing and the sketch
    # The next round reads the new revision.
    fake.documents[sent_as] = _mark_up(fake.documents[sent_as], tmp_path)
    r3 = run_round("Garage", "rm2", store, client=FakeClient(_turns()))
    assert r3.sent_as == f"{folder}/Garage r03"


def test_upgrade_refuses_unread_marks_and_web_upgrades(sketch, tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from rmink.drawing.store import MemoryStore
    from rmink.web.app import Limits, create_app

    monkeypatch.setenv("RMINK_ROUNDS_SECRET", "s3cret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake = FakeCloud(
        monkeypatch,
        {"/": {"rmink"}, "/rmink": {"Bastu"}, "/rmink/Bastu": {"skiss"}},
        {"/rmink/Bastu/skiss": sketch.read_bytes()},
    )
    browser = MemoryStore()
    r = run_round("/rmink/Bastu/skiss", "rm2", browser, client=FakeClient(_turns()))
    memory = {"drawings": browser.drawings, "links": browser.links}
    app = TestClient(create_app(Limits(2_000_000, 3, 5, 60, 1)))
    auth = {"X-Rmink-Secret": "s3cret"}

    marked = fake.documents[r.sent_as]
    fake.documents[r.sent_as] = _mark_up(marked, tmp_path)
    refused = app.post("/api/drawing/upgrade", json={"name": "Bastu", **memory}, headers=auth)
    assert refused.status_code == 409 and "varv" in refused.json()["detail"]
    assert "Bygg" not in fake.folders["/rmink"]  # nothing moved

    fake.documents[r.sent_as] = marked
    ok = app.post("/api/drawing/upgrade", json={"name": "Bastu", **memory}, headers=auth)
    assert ok.status_code == 200, ok.text
    assert ok.json()["sent_as"] == "/rmink/Bygg/Bastu/Bastu r02"
    saved = Drawing.model_validate_json(ok.json()["store"]["drawings"]["bastu"])
    assert saved.area == "Bygg" and saved.revision == 2


def test_a_drawing_off_the_page_is_brought_back():
    big = Drawing.model_validate(
        DRAWING
        | {
            "elements": [{"id": "V1", "kind": "rect", "points": [[400, -300], [2200, 900]]}],
            "dimensions": [{"id": "M1", "start": [400, -300], "end": [2200, -300], "text": "9"}],
        }
    )
    fitted = workflow.fit_to_page(big, RM2)
    lo, hi = workflow._extent(fitted)
    assert lo[0] >= 0 and lo[1] >= 0 and hi[0] <= RM2.width and hi[1] <= RM2.height
    assert workflow.fit_to_page(fitted, RM2) == fitted


def test_remarks_keep_the_drawing_page_one_screen(tmp_path):
    many = Drawing.model_validate(
        DRAWING
        | {
            "annotations": [
                {"id": f"a{i}", "kind": "circle", "targets": ["V1"], "text": f"Fråga {i}?"}
                for i in range(3)
            ]
        }
    )
    rev = workflow.build_revision(many, tmp_path / "r.rmdoc", store=FileStore(tmp_path / "d"))
    apart = bool(rev.drawing.sketch.remarks_page)
    assert render_drawing(rev.drawing, RM2, remarks_apart=apart).height <= RM2.height
    lo, hi = workflow._extent(rev.drawing)
    assert hi[1] - lo[1] >= RM2.height * workflow.FIT_FLOOR - 1  # but not tiny


def _many_remarks(n=5):
    return Drawing.model_validate(
        DRAWING
        | {
            "annotations": [
                {"id": f"a{i}", "kind": "circle", "targets": ["V1"], "text": f"Fråga {i}?"}
                for i in range(n)
            ]
        }
    )


def test_many_remarks_go_on_a_page_of_their_own(sketch, tmp_path):
    store = FileStore(tmp_path / "d")
    page = read_rmdoc(sketch.read_bytes(), RM2).pages[0]
    rev = workflow.build_revision(_many_remarks(), tmp_path / "r.rmdoc", page, store=store)
    d = rev.drawing
    assert d.sketch.remarks_page == 2
    pages = read_rmdoc(rev.path.read_bytes(), RM2).pages
    assert len(pages) == 3  # drawing, remarks, sketch
    assert all(p.height <= RM2.height for p in pages[:2])
    # The drawing gets the room back: bigger than the smallest allowed.
    lo, hi = workflow._extent(d)
    assert hi[1] - lo[1] > RM2.height * workflow.FIT_FLOOR + 50

    # An answer on the remarks page reaches the round as writing under the drawing.
    answer = Stroke(np.linspace((300, 400), (700, 400), 20), layer=COMMENT_LAYER)
    remarks = pages[1]
    synced = [pages[0], Page(remarks.width, remarks.height, remarks.strokes + [answer]), pages[2]]
    uu = UuidFactory(4)
    author = uu()
    path = tmp_path / "synced.rmdoc"
    write_rmdoc(
        path,
        "synced",
        [RmdocPage(write_page(p, RM2, author)) for p in synced],
        [str(uu()) for _ in synced],
        author,
        RM2,
        str(uu()),
    )
    seen = workflow.read_sketch(str(path), 1, RM2, since=d)
    new = [
        s
        for s in seen.page.strokes
        if s.id and tuple(s.id) not in set(map(tuple, d.sketch.written_ids))
    ]
    assert len(new) == 1
    assert new[0].points[:, 1].min() == pytest.approx(pages[0].height + 400, abs=1)


def test_resend_keeps_the_sketch_page_after_the_remarks(sketch, tmp_path, monkeypatch):
    fake = FakeCloud(
        monkeypatch,
        {"/": {"rmink"}, "/rmink": {"Bygg"}, "/rmink/Bygg": {"Bod"}, "/rmink/Bygg/Bod": {"skiss"}},
        {"/rmink/Bygg/Bod/skiss": sketch.read_bytes()},
    )
    store = FileStore(tmp_path / "d")
    run_round(
        "/rmink/Bygg/Bod/skiss",
        "rm2",
        store,
        client=FakeClient(_turns(_many_remarks().model_dump())),
    )
    d = store.load("Bod")
    assert d.sketch.remarks_page == 2
    sent_as = workflow.resend(d, "tok", store)
    pages = read_rmdoc(fake.documents[sent_as], RM2).pages
    original = read_rmdoc(sketch.read_bytes(), RM2).pages[0]
    assert len(pages) == 3 and len(pages[2].strokes) == len(original.strokes)
