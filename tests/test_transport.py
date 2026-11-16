"""Transports: the folder, how one is chosen, and rounds that run over it."""

import shutil
import zipfile

import pytest
from test_rounds import DRAWING, FakeClient, _mark_up, _turns, sketch  # noqa: F401
from typer.testing import CliRunner

from rmink import cloud, transport
from rmink.cli import app
from rmink.drawing.agent import run_round
from rmink.drawing.store import FileStore
from rmink.transport import CloudTransport, FolderTransport


@pytest.fixture(autouse=True)
def config_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("RMINK_CLOUD_TOKEN", raising=False)
    monkeypatch.setattr(transport, "config_path", lambda: tmp_path / "config/rmink/config.toml")


def _rmdoc(path, text="{}"):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a.content", text)
    return path


def test_folder_keeps_notebooks_as_rmdoc_files(tmp_path):
    t = FolderTransport(tmp_path / "tree")
    assert t.ls("/") == []  # the root is made when first used
    with pytest.raises(transport.NotFoundError):
        t.ls("/rmink")
    with pytest.raises(transport.NotFoundError):
        t.mkdir("/rmink/Altan")  # the parent must exist
    t.mkdir("/rmink")
    t.mkdir("/rmink")  # already there counts as made
    t.mkdir("/rmink/Altan")

    doc = _rmdoc(tmp_path / "x.rmdoc")
    assert t.put(doc, folder="/rmink/Altan", name="Altan r01 · 1 fråga") == "Altan r01 · 1 fråga"
    assert t.put(doc, folder="/rmink/Altan", name="Altan r01 · 1 fråga") == "Altan r01 · 1 fråga_2"
    assert (tmp_path / "tree/rmink/Altan/Altan r01 · 1 fråga.rmdoc").is_file()
    assert t.put(doc) == "x"
    with pytest.raises(transport.NotFoundError):
        t.put(doc, folder="/rmink/Garage")

    assert t.ls("/rmink/Altan") == [
        transport.Entry("Altan r01 · 1 fråga", False),
        transport.Entry("Altan r01 · 1 fråga_2", False),
    ]
    assert t.ls("/") == [transport.Entry("rmink", True), transport.Entry("x", False)]
    assert t.get("/rmink/Altan/Altan r01 · 1 fråga") == doc.read_bytes()
    with pytest.raises(transport.NotFoundError):
        t.get("/rmink/Altan/Saknas")


def test_folder_moves_and_removes(tmp_path):
    t = FolderTransport(tmp_path / "tree")
    t.mkdir("/rmink")
    t.mkdir("/rmink/Altan")
    t.mkdir("/rmink/Altan/Tidigare")
    doc = _rmdoc(tmp_path / "x.rmdoc")
    t.put(doc, folder="/rmink/Altan", name="a")
    t.put(doc, folder="/rmink/Altan", name="b")

    t.mv("/rmink/Altan/a", "/rmink/Altan/Tidigare/a r00 skiss")
    assert t.ls("/rmink/Altan/Tidigare") == [transport.Entry("a r00 skiss", False)]
    with pytest.raises(transport.ExistsError):
        t.mv("/rmink/Altan/b", "/rmink/Altan/Tidigare/a r00 skiss")
    with pytest.raises(transport.NotFoundError):
        t.mv("/rmink/Altan/b", "/rmink/Saknas/b")
    with pytest.raises(transport.NotFoundError):
        t.mv("/rmink/Altan/saknas", "/rmink/Altan/c")

    t.mkdir("/rmink/Bygg")
    t.mv("/rmink/Altan", "/rmink/Bygg/Altan")  # a folder moves with what is in it
    assert t.get("/rmink/Bygg/Altan/Tidigare/a r00 skiss")
    t.mkdir("/rmink/Altan")
    with pytest.raises(transport.ExistsError):
        t.mv("/rmink/Altan", "/rmink/Bygg/Altan")

    with pytest.raises(transport.TransportError, match="not empty"):
        t.rmdir("/rmink/Bygg")
    (tmp_path / "tree/rmink/Altan/.DS_Store").write_text("")
    t.rmdir("/rmink/Altan")  # what the file manager left behind does not count
    assert not (tmp_path / "tree/rmink/Altan").exists()


def test_folder_never_leaves_its_root(tmp_path):
    t = FolderTransport(tmp_path / "tree")
    _rmdoc(tmp_path / "secret.rmdoc")
    for call in (lambda: t.get("/../secret"), lambda: t.ls("/.."), lambda: t.mkdir("/../x")):
        with pytest.raises(transport.TransportError, match="not a path inside"):
            call()
    with pytest.raises(transport.TransportError):
        t.rmdir("/")


def test_a_zip_from_an_older_rmapi_is_a_notebook_too(tmp_path):
    t = FolderTransport(tmp_path)
    _rmdoc(tmp_path / "Gammal.zip")
    assert t.ls("/") == [transport.Entry("Gammal", False)]
    assert t.get("/Gammal")
    t.mkdir("/a")
    t.mv("/Gammal", "/a/Gammal")
    assert (tmp_path / "a/Gammal.zip").is_file()


def test_which_transport_is_used(tmp_path, monkeypatch):
    assert transport.default() is None  # nothing chosen, not connected
    with pytest.raises(transport.AuthError, match="rmink transport use"):
        transport.fetch("/rmink/Altan")

    cloud.save_token("tok.en-1")
    assert transport.default() == CloudTransport("tok.en-1")
    assert "tok" not in repr(transport.default())

    saved = transport.use(f"folder:{tmp_path / 'a'}")  # the saved choice goes before the cloud
    assert saved == transport.config_path()
    assert transport.default().root == (tmp_path / "a").resolve()

    monkeypatch.setenv("RMINK_TRANSPORT", f"folder:{tmp_path / 'b'}")  # --via goes before both
    assert transport.default().root == (tmp_path / "b").resolve()
    monkeypatch.setenv("RMINK_TRANSPORT", "cloud")
    assert transport.default() == CloudTransport("tok.en-1")

    with pytest.raises(transport.TransportError, match="Choose one of: cloud, folder"):
        transport.open("ftp:example")
    with pytest.raises(transport.TransportError, match="Give the folder"):
        transport.use("folder")


def test_a_token_is_still_a_transport(tmp_path):
    assert transport.of("tok.en-1") == CloudTransport("tok.en-1")
    folder = FolderTransport(tmp_path)
    assert transport.of(folder) is folder
    assert cloud.CloudError is transport.TransportError
    assert cloud.CloudNotFoundError is transport.NotFoundError and cloud.Entry is transport.Entry


def test_fetch_reads_a_local_file_before_the_transport(tmp_path, monkeypatch):
    local = _rmdoc(tmp_path / "local.rmdoc", "local")
    assert transport.fetch(str(local)) == local.read_bytes()
    tree = FolderTransport(tmp_path / "tree")
    tree.put(_rmdoc(tmp_path / "x.rmdoc", "tree"), name="Altan")
    monkeypatch.setenv("RMINK_TRANSPORT", f"folder:{tmp_path / 'tree'}")
    assert transport.fetch("Altan") == transport.fetch("/Altan") == tree.get("/Altan")


def test_rounds_run_over_a_folder_without_the_cloud(sketch, tmp_path, monkeypatch):  # noqa: F811
    tree = tmp_path / "tree"
    (tree / "rmink").mkdir(parents=True)
    shutil.copy(sketch, tree / "rmink/Altan.rmdoc")
    monkeypatch.setenv("RMINK_TRANSPORT", f"folder:{tree}")
    store = FileStore(tmp_path / "drawings")
    with_question = DRAWING | {
        "annotations": [{"id": "a1", "kind": "circle", "targets": ["V1"], "text": "Höjd?"}]
    }
    r = run_round("/rmink/Altan", "rm2", store, client=FakeClient(_turns(with_question)))

    folder = tree / "rmink/Bygg/Altan"
    assert r.sent_as == "/rmink/Bygg/Altan/Altan r01 · 1 fråga"
    assert (folder / "Altan r01 · 1 fråga.rmdoc").is_file()
    assert (folder / "Tidigare/Altan r00 skiss.rmdoc").is_file()
    assert not (tree / "rmink/Altan.rmdoc").exists()

    # The user writes on r01 and puts the file back; the next round reads it there.
    r01 = folder / "Altan r01 · 1 fråga.rmdoc"
    r01.write_bytes(_mark_up(r01.read_bytes(), tmp_path))
    r2 = run_round("Altan", "rm2", store, client=FakeClient(_turns()))
    assert r2.sent_as == "/rmink/Bygg/Altan/Altan r02"
    assert sorted(p.name for p in folder.iterdir()) == ["Altan r02.rmdoc", "Tidigare"]
    assert sorted(p.name for p in (folder / "Tidigare").iterdir()) == [
        "Altan r00 skiss.rmdoc",
        "Altan r01 · 1 fråga.rmdoc",
    ]


def test_sheets_go_out_and_come_back_through_a_folder(examples, tmp_path):
    tree, runner = tmp_path / "tree", CliRunner()
    via = ["--via", f"folder:{tree}"]
    out = tmp_path / "ark.rmdoc"
    sent = runner.invoke(
        app, [*via, "sheet", "send", str(examples["pdf"]), "-o", str(out), "--send"]
    )
    assert sent.exit_code == 0, sent.output
    assert "Sent as '/rmink/Ark/document'" in sent.output
    assert (tree / "rmink/Ark/document.rmdoc").is_file()

    listed = runner.invoke(app, [*via, "transport", "ls", "/rmink/Ark"])
    assert listed.exit_code == 0 and "document" in listed.output

    pdf = tmp_path / "med.pdf"
    pulled = runner.invoke(
        app, [*via, "sheet", "pull", "/rmink/Ark/document", str(examples["pdf"]), "-o", str(pdf)]
    )
    assert pulled.exit_code == 0, pulled.output
    assert pdf.is_file()


def test_without_a_transport_the_cli_says_how_to_get_one(examples, tmp_path):
    result = CliRunner().invoke(
        app, ["sheet", "pull", "/rmink/Ark/x", str(examples["pdf"]), "-o", str(tmp_path / "o.pdf")]
    )
    assert result.exit_code == 1
    assert "rmink cloud connect" in result.output and "transport use folder:PATH" in result.output
