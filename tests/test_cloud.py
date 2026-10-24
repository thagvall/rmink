import subprocess
import zipfile
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from rmink.web import cloud  # noqa: E402
from rmink.web.app import Limits, create_app  # noqa: E402


class FakeRmapi:
    """Stands in for the rmapi binary: one valid code, one valid token."""

    def __init__(self):
        self.calls = []
        self.uploaded = []
        self.existing = set()

    def __call__(self, args, input, env, **kw):
        self.calls.append((args, input, env))
        conf = Path(env["RMAPI_CONFIG"])
        token = None
        if conf.exists():
            token = conf.read_text().split(":", 1)[1].strip()
        out, err, code = "", "", 0
        if args[1:] == ["ls", "/"]:
            if input.strip() == "goodcode":
                conf.write_text("devicetoken: tok.en-1\nusertoken: u\n")
            else:
                err, code = "failed to create a new device token", 1
        elif args[1:3] == ["-ni", "put"]:
            path = Path(args[3])
            if token != "tok.en-1":
                err, code = "missing token, not asking, aborting", 1
            elif path.stem in self.existing:
                err = "entry already exists (use --force to recreate)"
            else:
                with zipfile.ZipFile(path) as zf:
                    names = zf.namelist()
                # The cloud rejects thumbnail file names from rmapi.
                assert names and not any(".thumbnails/" in n for n in names)
                self.uploaded.append(path.name)
                out = f"uploading: [{path}]...OK\n"
        return subprocess.CompletedProcess(args, code, out, err)


@pytest.fixture
def rmapi(monkeypatch):
    fake = FakeRmapi()
    monkeypatch.setenv("RMINK_RMAPI", "/opt/rmapi")
    monkeypatch.setattr(cloud.subprocess, "run", fake)
    return fake


@pytest.fixture
def client():
    return TestClient(create_app(Limits(2_000_000, 3, 5, 60, 1)))


def _upload(path):
    return ("files", (path.name, path.read_bytes()))


def test_limits_report_cloud(client, rmapi, monkeypatch):
    assert client.get("/api/limits").json()["cloud"] is True
    monkeypatch.delenv("RMINK_RMAPI")
    monkeypatch.setattr(cloud.shutil, "which", lambda _: None)
    assert client.get("/api/limits").json()["cloud"] is False
    r = client.post("/api/cloud/connect", data={"code": "goodcode"})
    assert r.status_code == 503


def test_connect(client, rmapi):
    assert client.post("/api/cloud/connect", data={"code": "short"}).status_code == 422
    r = client.post("/api/cloud/connect", data={"code": " GoodCode "})
    assert r.status_code == 200, r.text
    assert r.json() == {"token": "tok.en-1"}
    args, stdin, env = rmapi.calls[-1]
    assert stdin == "goodcode\n"
    # Each run gets its own config, outside the server user's home.
    assert env["HOME"] != str(Path.home()) and not Path(env["RMAPI_CONFIG"]).exists()
    r = client.post("/api/cloud/connect", data={"code": "badcode1"})
    assert r.status_code == 502 and "did not accept" in r.json()["detail"]


def test_send(client, rmapi, examples):
    def send(token, name="My notes"):
        return client.post(
            "/api/cloud/send",
            files=[_upload(examples["pdf"])],
            data={"name": name, "pages": "1", "token": token},
        )

    r = send("tok.en-1")
    assert r.status_code == 200, r.text
    assert r.json() == {"name": "My notes", "warnings": 0}
    assert rmapi.uploaded == ["My notes.rmdoc"]
    assert rmapi.calls[-1][0][-1] == "/"

    # A taken name gets a number, as "name_2".
    rmapi.existing.update({"My notes", "My notes_2"})
    r = send("tok.en-1")
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "My notes_3"
    assert rmapi.uploaded[-1] == "My notes_3.rmdoc"

    rmapi.existing.update({"Full", *(f"Full_{n}" for n in range(2, 22))})
    r = send("tok.en-1", name="Full")
    assert r.status_code == 409 and "Too many" in r.json()["detail"]

    assert send("revoked").status_code == 401
    assert send("bad token!").status_code == 401
    r = client.post("/api/cloud/send", files=[_upload(examples["pdf"])])
    assert r.status_code == 422


def test_send_reports_rmapi_failure(client, rmapi, examples, monkeypatch):
    def broken(args, **kw):
        return subprocess.CompletedProcess(args, 1, "", "Error: network unreachable")

    monkeypatch.setattr(cloud.subprocess, "run", broken)
    r = client.post(
        "/api/cloud/send",
        files=[_upload(examples["svg"])],
        data={"token": "tok.en-1"},
    )
    assert r.status_code == 502 and "network unreachable" in r.json()["detail"]


def test_index_has_send_button(client):
    assert 'id="send"' in client.get("/").text
