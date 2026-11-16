"""The USB transport (rmink.transport.usb) against a stand-in for the tablet's
USB web interface: list with POST /documents/<id>, fetch with
GET /download/<id>/rmdoc, upload to the folder listed last with POST /upload."""

import io
import json
import re
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from typer.testing import CliRunner

from rmink import cli, transport


class Tablet:
    """Folders and notebooks by id, as the tablet keeps them."""

    def __init__(self):
        self.items = {}  # id -> {"name", "folder", "parent", "data", "modified"}
        self.listed = ""  # the folder listed last: where an upload goes
        self.clock = 0
        self.uploads = []
        self.rmdoc = True  # False: software before 3.9, which hands out a PDF

    def add(self, name, parent="", data=None):
        self.clock += 1
        item_id = f"id-{self.clock}"
        self.items[item_id] = {
            "name": name, "folder": data is None, "parent": parent, "data": data,
            "modified": f"2026-11-16T10:00:{self.clock:02d}Z",
        }  # fmt: skip
        return item_id

    def listing(self, parent):
        return [
            {
                "ID": i,
                "VissibleName": item["name"],
                "Type": "CollectionType" if item["folder"] else "DocumentType",
                "Parent": parent,
                "ModifiedClient": item["modified"],
            }
            for i, item in self.items.items()
            if item["parent"] == parent
        ]


@pytest.fixture
def tablet():
    state = Tablet()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, body, kind="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path.startswith("/documents/"):
                folder = self.path.removeprefix("/documents/")
                if folder and folder not in state.items:
                    return self._send(404, b"{}")
                state.listed = folder
                return self._send(200, json.dumps(state.listing(folder)).encode())
            if self.path == "/upload":
                name = re.search(rb'filename="([^"]+)"', body).group(1).decode()
                data = body.split(b"\r\n\r\n", 1)[1].rsplit(b"\r\n--", 1)[0]
                assert name.endswith(".rmdoc")
                # Like the tablet (measured on rm2): the notebook is named by the
                # visibleName inside the archive, not by the file name.
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    meta = next(n for n in zf.namelist() if n.endswith(".metadata"))
                    stem = json.loads(zf.read(meta))["visibleName"]
                state.uploads.append((state.listed, stem))
                state.add(stem, state.listed, data)
                return self._send(201, b'{"status":"Upload successful"}')
            self._send(404, b"{}")

        def do_GET(self):
            m = re.fullmatch(r"/download/([^/]+)/rmdoc", self.path)
            if not m or m.group(1) not in state.items:
                return self._send(404, b"{}")
            data = state.items[m.group(1)]["data"] if state.rmdoc else b"%PDF-1.4"
            self._send(200, data, "application/octet-stream")

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.host = f"127.0.0.1:{server.server_port}"
    yield state
    server.shutdown()
    server.server_close()


def _rmdoc(path, text="{}"):
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a.content", text)
        zf.writestr("a.metadata", json.dumps({"visibleName": "namnet inuti", "parent": ""}))
        zf.writestr("a/page.rm", b"ink")
    return path


def _files(data):
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        return {n: zf.read(n) for n in zf.namelist()}


def test_list_fetch_and_upload_over_the_cable(tablet, tmp_path):
    rmink = tablet.add("rmink")
    ark = tablet.add("Ark", rmink)
    doc = _rmdoc(tmp_path / "x.rmdoc", "ny")
    tablet.add("Skiss", rmink, _rmdoc(tmp_path / "s.rmdoc", "skiss").read_bytes())

    t = transport.open(f"usb:{tablet.host}")
    assert isinstance(t, transport.Transport) and repr(t) == f"usb:{tablet.host}"
    assert t.ls("/") == [transport.Entry("rmink", True)]
    assert set(t.ls("/rmink")) == {transport.Entry("Ark", True), transport.Entry("Skiss", False)}
    assert zipfile.ZipFile(tmp_path / "s.rmdoc").read("a.content") == b"skiss"
    assert t.get("/rmink/Skiss") == (tmp_path / "s.rmdoc").read_bytes()

    assert t.put(doc, folder="/rmink/Ark", name="Ritning å") == "Ritning å"
    assert t.put(doc, folder="/rmink/Ark", name="Ritning å") == "Ritning å_2"  # never over one
    assert tablet.uploads == [(ark, "Ritning å"), (ark, "Ritning å_2")]
    # What comes back is the notebook that went up, under the name put gave it.
    back, sent = _files(t.get("/rmink/Ark/Ritning å_2")), _files(doc.read_bytes())
    assert json.loads(back.pop("a.metadata"))["visibleName"] == "Ritning å_2"
    assert json.loads(sent.pop("a.metadata"))["visibleName"] == "namnet inuti"
    assert back == sent
    assert t.put(doc) == "x" and tablet.uploads[-1] == ("", "x")
    with pytest.raises(transport.TransportError, match="not a notebook file"):
        (tmp_path / "trasig.rmdoc").write_bytes(b"inte en zip")
        t.put(tmp_path / "trasig.rmdoc")

    with pytest.raises(transport.NotFoundError, match='"/rmink/Saknas" does not exist'):
        t.ls("/rmink/Saknas")
    with pytest.raises(transport.NotFoundError):
        t.get("/rmink/Ark/Saknas")
    with pytest.raises(transport.NotFoundError):
        t.put(doc, folder="/rmink/Bygg")


def test_of_two_notebooks_with_one_name_the_newest_is_read(tablet, tmp_path):
    tablet.add("Altan", "", b"PK-old")
    tablet.add("Altan", "", b"PK-new")
    assert transport.open(f"usb:{tablet.host}").get("/Altan") == b"PK-new"


def test_what_the_interface_cannot_do_is_said_plainly(tablet, tmp_path):
    tablet.add("rmink")
    t = transport.open(f"usb:{tablet.host}")
    t.mkdir("/rmink")  # there already: fine
    with pytest.raises(
        transport.TransportError, match='Make the folder "/rmink/Ark" on the tablet'
    ):
        t.mkdir("/rmink/Ark")
    with pytest.raises(transport.TransportError, match="cannot move or rename"):
        t.mv("/rmink/a", "/rmink/b")
    with pytest.raises(transport.TransportError, match="cannot remove"):
        t.rmdir("/rmink")

    tablet.rmdoc = False
    tablet.add("Gammal", "", b"x")
    with pytest.raises(transport.TransportError, match="older than 3.9"):
        t.get("/Gammal")


def test_a_tablet_that_is_not_plugged_in():
    t = transport.open("usb:127.0.0.1:9")
    t.timeout = 2
    with pytest.raises(transport.TransportError, match="does not answer.*USB web interface"):
        t.ls("/")


def test_a_sheet_goes_out_and_comes_back_over_usb(tablet, examples, tmp_path):
    runner, via = CliRunner(), ["--via", f"usb:{tablet.host}"]
    send = [*via, "sheet", "send", str(examples["pdf"]), "-o", str(tmp_path / "a.rmdoc"), "--send"]
    refused = runner.invoke(cli.app, send)
    assert refused.exit_code == 1  # the folders are not there yet, and USB cannot make them
    assert 'Make the folder "/rmink" on the tablet' in str(refused.exception)

    tablet.add("Ark", tablet.add("rmink"))
    sent = runner.invoke(cli.app, send)
    assert sent.exit_code == 0, sent.output
    assert "Sent as '/rmink/Ark/document'" in sent.output

    pdf = tmp_path / "med.pdf"
    pulled = runner.invoke(
        cli.app,
        [*via, "sheet", "pull", "/rmink/Ark/document", str(examples["pdf"]), "-o", str(pdf)],
    )
    assert pulled.exit_code == 0, pulled.output
    assert pdf.is_file()


def test_the_check_command(tablet, tmp_path):
    tablet.add("rmink")
    tablet.add("Skiss", "", _rmdoc(tmp_path / "s.rmdoc").read_bytes())
    result = CliRunner().invoke(cli.app, ["--via", f"usb:{tablet.host}", "transport", "check"])
    assert result.exit_code == 0, result.output
    assert "1 folders, 1 notebooks" in result.output and "hands out notebooks" in result.output
    down = CliRunner().invoke(cli.app, ["--via", "usb:127.0.0.1:9", "transport", "check"])
    assert down.exit_code == 1 and "does not answer" in down.output


def test_usb_is_built_in_and_opens_without_touching_the_tablet(tmp_path, monkeypatch):
    from rmink.transport.usb import UsbTransport

    monkeypatch.setattr(transport, "config_path", lambda: tmp_path / "config.toml")
    assert "usb" in transport.BUILTIN
    assert repr(transport.open("usb")) == "usb:10.11.99.1"
    transport.use("usb")  # saving the choice needs no tablet
    assert isinstance(transport.default(), UsbTransport)
