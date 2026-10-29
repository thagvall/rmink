import os
import subprocess
import zipfile
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from rmink import cloud  # noqa: E402
from rmink.web.app import Limits, create_app  # noqa: E402


class FakeRmapi:
    """Stands in for the rmapi binary: one valid code, one valid token."""

    def __init__(self):
        self.calls = []
        self.uploaded = []
        self.existing = set()
        self.documents = {"Altan": b"PK-fake-rmdoc"}
        self.folders = {"/"}

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
        elif args[1:3] == ["-ni", "ls"]:
            if token != "tok.en-1":
                err, code = "missing token, not asking, aborting", 1
            elif args[3] != "/" and args[3] not in self.folders:
                name = args[3].rsplit("/", 1)[-1]
                err, code = f"ERROR: main.go:86: Error:  no matches for '{name}'", 1
            else:
                out = "[d]\tProjekt\n" + "".join(f"[f]\t{n}\n" for n in self.documents)
        elif args[1:3] == ["-ni", "get"]:
            name = args[3].strip("/")
            if token != "tok.en-1":
                err, code = "missing token, not asking, aborting", 1
            elif name not in self.documents:
                err, code = "file doesn't exist", 1
            else:
                (Path(kw["cwd"]) / f"{name}.rmdoc").write_bytes(self.documents[name])
        elif args[1:3] == ["-ni", "mkdir"]:
            if args[3] in self.folders:
                err = "Error: entry already exists"
            elif (args[3].rsplit("/", 1)[0] or "/") not in self.folders:
                err = "Error: directory doesn't exist"
            else:
                self.folders.add(args[3])
        elif args[1:3] == ["-ni", "mv"]:
            if args[4] in self.existing:
                err = "Error: destination entry already exists"
            elif args[4].rsplit("/", 1)[0] not in self.folders:
                err = "Error: directory doesn't exist"
        elif args[1:3] == ["-ni", "put"]:
            path = Path(args[3])
            if token != "tok.en-1":
                err, code = "missing token, not asking, aborting", 1
            elif args[4] not in self.folders:
                err = "Error: directory doesn't exist"
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


def test_ls_and_get(rmapi):
    entries = cloud.ls("tok.en-1")
    assert entries == [cloud.Entry("Projekt", True), cloud.Entry("Altan", False)]
    assert cloud.get("tok.en-1", "/Altan") == b"PK-fake-rmdoc"
    with pytest.raises(cloud.CloudError):
        cloud.get("tok.en-1", "/Missing")
    with pytest.raises(cloud.CloudAuthError):
        cloud.ls("expired-token")


def test_folders(rmapi, examples, tmp_path):
    with pytest.raises(cloud.CloudNotFoundError):
        cloud.ls("tok.en-1", "/rmink")
    with pytest.raises(cloud.CloudError, match="doesn't exist"):
        cloud.mkdir("tok.en-1", "/rmink/Altan")
    cloud.mkdir("tok.en-1", "/rmink")
    cloud.mkdir("tok.en-1", "/rmink")  # already there counts as made
    cloud.mkdir("tok.en-1", "/rmink/Altan")
    assert cloud.ls("tok.en-1", "/rmink/Altan") is not None

    doc = tmp_path / "x.rmdoc"
    with zipfile.ZipFile(doc, "w") as zf:
        zf.writestr("a.content", "{}")
    assert cloud.put(doc, "tok.en-1", folder="/rmink/Altan", name="Altan r01 · 1 fråga") == (
        "Altan r01 · 1 fråga"
    )
    assert rmapi.uploaded[-1] == "Altan r01 · 1 fråga.rmdoc"
    assert rmapi.calls[-1][0][-1] == "/rmink/Altan"
    with pytest.raises(cloud.CloudNotFoundError):
        cloud.put(doc, "tok.en-1", folder="/rmink/Garage")

    cloud.mv("tok.en-1", "/rmink/Altan", "/rmink/Altan/Altan r00 skiss")
    rmapi.existing.add("/rmink/Altan/Taken")
    with pytest.raises(cloud.CloudExistsError):
        cloud.mv("tok.en-1", "/rmink/x", "/rmink/Altan/Taken")
    with pytest.raises(cloud.CloudError, match="doesn't exist"):
        cloud.mv("tok.en-1", "/rmink/x", "/rmink/Altan/Tidigare/x")


def test_token_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("RMINK_CLOUD_TOKEN", raising=False)
    assert cloud.load_token() is None
    path = cloud.save_token("tok.en-1")
    if os.name != "nt":  # Windows has no Unix modes; the profile folder's ACL protects it
        assert path.stat().st_mode & 0o777 == 0o600
    assert cloud.load_token() == "tok.en-1"
    monkeypatch.setenv("RMINK_CLOUD_TOKEN", "from-env")
    assert cloud.load_token() == "from-env"


@pytest.mark.skipif(os.name == "nt", reason="no lasting cache on Windows")
def test_owner_keeps_the_tree_cache(tmp_path, monkeypatch):
    # Without it every rmapi run fetches every notebook's metadata, and the
    # cloud answers 429 after a few rounds.
    monkeypatch.setattr(cloud.tempfile, "tempdir", str(tmp_path))
    monkeypatch.setenv("RMINK_RMAPI", "/opt/rmapi")
    monkeypatch.setenv("RMINK_CLOUD_TOKEN", "owner.tok-1")
    seen = []

    def run(args, input, env, **kw):
        # Where Go's os.UserCacheDir points: XDG_CACHE_HOME on Linux, $HOME on macOS.
        for cache in (Path(env["XDG_CACHE_HOME"]), Path(env["HOME"]) / "Library" / "Caches"):
            seen.append((cache / "rmapi" / "tree.cache").exists())
        (Path(env["XDG_CACHE_HOME"]) / "rmapi").mkdir(exist_ok=True)
        (Path(env["XDG_CACHE_HOME"]) / "rmapi" / "tree.cache").write_text("tree")
        # rmapi adds the user token it fetched to its config.
        conf = Path(env["RMAPI_CONFIG"])
        seen.append("usertoken" in conf.read_text())
        conf.write_text(conf.read_text().splitlines()[0] + "\nusertoken: u\n")
        return subprocess.CompletedProcess(args, 0, "[d]\trmink\n", "")

    monkeypatch.setattr(cloud.subprocess, "run", run)
    cloud.ls("owner.tok-1", "/rmink")
    cloud.ls("owner.tok-1", "/rmink")
    assert seen == [False, False, False, True, True, True]

    seen.clear()
    cloud.ls("someone.else-1")
    cloud.ls("someone.else-1")
    assert seen == [False, False, False] * 2
    assert len([p for p in tmp_path.iterdir() if p.name.startswith("rmink-rmapi-cache-")]) == 1


def test_rate_limit_message():
    proc = subprocess.CompletedProcess(
        [],
        1,
        "",
        "ERROR: 2026/10/28 16:15:06 main.go:80: failed to build documents tree, "
        "last error: failed to mirror cannot get root hash request failed with status 429",
    )
    assert "wait a few minutes" in cloud._message(proc)


def test_rmapi_runs_two_requests_at_a_time(tmp_path, monkeypatch):
    monkeypatch.delenv("RMAPI_CONCURRENT", raising=False)
    assert cloud._env(tmp_path)["RMAPI_CONCURRENT"] == "2"
    monkeypatch.setenv("RMAPI_CONCURRENT", "1")
    assert cloud._env(tmp_path)["RMAPI_CONCURRENT"] == "1"
