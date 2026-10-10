import io
import zipfile

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from rmink.web.app import Limits, create_app  # noqa: E402


@pytest.fixture
def client():
    return TestClient(create_app(Limits(2_000_000, 3, 5, 60, 1)))


def _upload(path, name=None):
    return ("files", (name or path.name, path.read_bytes()))


def test_index_and_metadata(client):
    r = client.get("/")
    assert r.status_code == 200 and "rmink" in r.text
    devices = client.get("/api/devices").json()
    assert {d["key"] for d in devices} >= {"rm2", "pure", "pro", "move"}
    assert client.get("/api/limits").json()["max_files"] == 3


def test_preview_returns_page_images(client, examples):
    r = client.post(
        "/api/preview",
        files=[_upload(examples["photo"]), _upload(examples["svg"])],
        data={"device": "pro", "simplify": "0.8"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["device"] == "pro" and len(body["pages"]) == 2
    assert body["pages"][0]["label"] == "handwriting.jpg"
    assert body["pages"][0]["image"].startswith("data:image/png;base64,")
    assert all(p["strokes"] > 0 for p in body["pages"])


def test_convert_downloads_rmdoc(client, examples):
    r = client.post(
        "/api/convert",
        files=[_upload(examples["pdf"])],
        data={"name": "My notes", "pages": "1"},
    )
    assert r.status_code == 200, r.text
    assert "My%20notes.rmdoc" in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert sum(n.endswith(".rm") for n in zf.namelist()) == 1
        meta = next(n for n in zf.namelist() if n.endswith(".metadata"))
        assert b'"My notes"' in zf.read(meta)


def test_rejects_bad_input(client, examples, tmp_path):
    bad = tmp_path / "x.exe"
    bad.write_bytes(b"MZ")
    assert client.post("/api/preview", files=[_upload(bad)]).status_code == 415

    r = client.post("/api/preview", files=[_upload(examples["svg"])], data={"device": "kindle"})
    assert r.status_code == 422 and "kindle" in r.json()["detail"]

    r = client.post("/api/preview", files=[_upload(examples["svg"])] * 4)
    assert r.status_code == 413

    big = tmp_path / "big.png"
    big.write_bytes(b"0" * 2_100_000)
    assert client.post("/api/preview", files=[_upload(big)]).status_code == 413


def test_page_limit(client, examples):
    r = client.post("/api/preview", files=[_upload(examples["pdf"])] * 3)
    assert r.status_code == 413 and "limit" in r.json()["detail"]


def test_support_links_follow_env(client, monkeypatch):
    monkeypatch.setenv("RMINK_SUPPORT_URL", "https://buy.stripe.com/test_abc")
    monkeypatch.setenv("RMINK_SOURCE_URL", "https://github.com/example/rmink")
    limits = client.get("/api/limits").json()
    assert limits["support_url"] == "https://buy.stripe.com/test_abc"
    assert limits["source_url"] == "https://github.com/example/rmink"

    monkeypatch.setenv("RMINK_SUPPORT_URL", "")
    assert client.get("/api/limits").json()["support_url"] == ""

    assert 'id="support-btn"' in client.get("/").text
    r = client.get("/thanks")
    assert r.status_code == 200 and "Thank you" in r.text
