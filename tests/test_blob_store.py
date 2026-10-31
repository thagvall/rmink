"""The Vercel Blob store for drawings and workbooks, against an in-memory Blob."""

import json
from types import SimpleNamespace

import pytest
from test_rounds import DRAWING
from test_workbook import WORKBOOK

from rmink import blob_cache
from rmink.drawing import store as store_mod
from rmink.drawing.model import Drawing
from rmink.drawing.store import BlobStore
from rmink.workbook.model import Workbook


class FakeBlob:
    class BlobNotFoundError(Exception):
        pass

    def __init__(self):
        self.files: dict[str, bytes] = {}

    def put_blob(self, pathname, body, **kw):
        self.files[pathname] = bytes(body)

    def get_blob(self, pathname, access):
        if pathname not in self.files:
            raise self.BlobNotFoundError(pathname)
        return SimpleNamespace(body=self.files[pathname])

    def query_blobs(self, prefix=None):
        return [SimpleNamespace(pathname=p) for p in sorted(self.files) if p.startswith(prefix)]


@pytest.fixture
def blob(monkeypatch):
    fake = FakeBlob()
    monkeypatch.setattr(BlobStore, "__init__", lambda self: setattr(self, "_blob", fake))
    monkeypatch.setattr(blob_cache, "enabled", lambda: True)
    for key in ("UPSTASH_REDIS_REST_URL", "KV_REST_API_URL"):
        monkeypatch.delenv(key, raising=False)
    return fake


def test_blob_store_keeps_every_version_and_reads_the_newest(blob):
    store = store_mod.server_store()
    assert isinstance(store, BlobStore)
    d = Drawing.model_validate(DRAWING | {"name": "Altan"})
    store.save(d)
    d.revision = 2
    store.save(d)
    assert store.load("Altan").revision == 2
    assert len([p for p in blob.files if "/drawing/altan/" in p]) == 2  # the history
    assert store.load("Nej") is None

    wb = Workbook.model_validate(WORKBOOK)
    store.save_workbook(wb)
    assert store.load_workbook("Bråk").title == wb.title
    store.link("/rmink/Bygg/Altan/Altan r02", "Altan")
    assert store.linked("rmink/Bygg/Altan/Altan r02") == "Altan"
    assert store.linked("/rmink/Annat") is None

    everything = store.everything()
    assert set(everything) == {"altan", "workbook:bråk"}
    assert json.loads(everything["altan"])["revision"] == 2


def test_web_lists_and_imports_from_the_browser(blob, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from rmink.web.app import Limits, create_app

    monkeypatch.setenv("RMINK_ROUNDS_SECRET", "s3cret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    app = TestClient(create_app(Limits(2_000_000, 3, 5, 60, 1)))
    auth = {"X-Rmink-Secret": "s3cret"}
    assert app.get("/api/rounds/saved", headers=auth).json() == {"server": True, "drawings": {}}

    old = Drawing.model_validate(DRAWING | {"name": "Bastu", "revision": 1}).model_dump_json()
    wb = Workbook.model_validate(WORKBOOK).model_dump_json()
    browser = {
        "drawings": {"bastu": old, "workbook:bråk": wb, "trasig": "{"},
        "links": {"rmink/Bastu/Bastu r01": "Bastu"},
    }
    r = app.post("/api/rounds/import", json=browser, headers=auth)
    assert r.status_code == 200 and sorted(r.json()["added"]) == ["Bastu", "Bråk"]
    saved = app.get("/api/rounds/saved", headers=auth).json()["drawings"]
    assert set(saved) == {"bastu", "workbook:bråk"}
    assert store_mod.server_store().linked("/rmink/Bastu/Bastu r01") == "Bastu"
    # Importing again adds nothing the server already has.
    assert app.post("/api/rounds/import", json=browser, headers=auth).json()["added"] == []


def test_file_store_lists_everything(tmp_path):
    from rmink.drawing.store import FileStore

    local = FileStore(tmp_path)
    local.save(Drawing.model_validate(DRAWING | {"name": "Garage"}))
    local.save_workbook(Workbook.model_validate(WORKBOOK))
    local.link("/rmink/Bygg/Garage/Garage r03", "Garage")
    assert set(local.everything()) == {"garage", "workbook:bråk"}
    assert local.links() == {"rmink/Bygg/Garage/Garage r03": "Garage"}
