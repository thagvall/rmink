"""The reMarkable USB web interface as a transport: rounds over the cable,
without a reMarkable Cloud subscription.

The tablet serves its files at http://10.11.99.1 while it is plugged in and
*Settings → Storage → USB web interface* ("USB connection" on newer software)
is on. That interface can list folders, hand out a notebook as ``.rmdoc``
(system software 3.9 and later) and take an upload into the folder listed
last. It cannot make, move, rename or remove anything, so:

- a folder rmink needs has to be made on the tablet by hand; ``mkdir`` says
  which one,
- ``mv`` and ``rmdir`` fail with a message, and rmink then leaves the notebook
  a round read where it is instead of moving it to ``Tidigare``.

Measured on an rm2 (2026-11-16): an upload lands in the folder listed last,
and the tablet names it after ``visibleName`` inside the archive, not after
the file. The interface is documented by its users, not by reMarkable
(remarkable.guide/tech/usb-web-interface.html), and may change with the
tablet's software.
"""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile
from pathlib import Path

from rmink.transport.errors import ExistsError, NotFoundError, TransportError

HOST = "10.11.99.1"
TIMEOUT_S = 20
UPLOAD_LIMIT_BYTES = 100_000_000  # the interface's own limit


class UsbTransport:
    name = "usb"

    def __init__(self, host: str = HOST, timeout: float = TIMEOUT_S) -> None:
        self.base = host if "://" in host else f"http://{host}"
        self.base = self.base.rstrip("/")
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"usb:{self.base.removeprefix('http://')}"

    # --- HTTP

    def _request(self, method: str, path: str, body: bytes | None = None, headers=None) -> bytes:
        request = urllib.request.Request(
            self.base + path, data=body, method=method, headers=headers or {}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise NotFoundError(f"The tablet has nothing at {path}") from e
            detail = e.read()[:200].decode("utf-8", "replace").strip()
            raise TransportError(f"The tablet answered {e.code} for {path}: {detail}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise TransportError(
                f"The tablet does not answer at {self.base}. Plug it in with the cable, wake "
                "it, and turn on Settings → Storage → USB web interface (USB connection)."
            ) from e

    def _list(self, folder_id: str = "") -> list[dict]:
        """The entries of a folder. Listing also makes it the folder the next
        upload goes to."""
        data = self._request("POST", f"/documents/{folder_id}")
        try:
            entries = json.loads(data)
        except ValueError as e:
            raise TransportError("The tablet's file list could not be read") from e
        return entries if isinstance(entries, list) else []

    @staticmethod
    def _name(entry: dict) -> str:
        # The interface spells it "VissibleName"; newer software may not.
        return str(entry.get("VissibleName") or entry.get("VisibleName") or "")

    @staticmethod
    def _is_folder(entry: dict) -> bool:
        return entry.get("Type") == "CollectionType"

    # --- paths

    def _find(self, entries: list[dict], name: str, folder: bool | None = None) -> dict | None:
        """The entry called ``name``; of several, the one changed last (the
        tablet allows two notebooks with one name)."""
        hits = [
            e
            for e in entries
            if self._name(e) == name and (folder is None or self._is_folder(e) == folder)
        ]
        return max(hits, key=lambda e: str(e.get("ModifiedClient", "")), default=None)

    def _folder(self, path: str) -> tuple[str, list[dict]]:
        """The id and entries of the folder at ``path``, listed last so an
        upload lands in it."""
        folder_id, entries = "", self._list()
        walked = ""
        for part in (p for p in path.split("/") if p):
            walked += "/" + part
            entry = self._find(entries, part, folder=True)
            if entry is None:
                raise NotFoundError(f'"{walked}" does not exist on the tablet')
            folder_id = str(entry["ID"])
            entries = self._list(folder_id)
        return folder_id, entries

    @staticmethod
    def _split(path: str) -> tuple[str, str]:
        parent, _, name = path.rstrip("/").rpartition("/")
        return parent or "/", name

    # --- the six calls

    def ls(self, path: str = "/") -> list:
        from rmink.transport import Entry

        _, entries = self._folder(path)
        return [Entry(self._name(e), self._is_folder(e)) for e in entries if self._name(e)]

    def get(self, path: str) -> bytes:
        parent, name = self._split(path)
        _, entries = self._folder(parent)
        entry = self._find(entries, name, folder=False)
        if entry is None:
            raise NotFoundError(f'"{path}" does not exist on the tablet')
        data = self._request("GET", f"/download/{entry['ID']}/rmdoc")
        if not data.startswith(b"PK"):
            raise TransportError(
                f'The tablet did not hand out "{path}" as a notebook file. Its system '
                "software may be older than 3.9, which is when the USB interface learned to."
            )
        return data

    def put(
        self, file: Path, folder: str = "/", name: str | None = None, attempts: int = 20
    ) -> str:
        file = Path(file)
        if file.stat().st_size > UPLOAD_LIMIT_BYTES:
            raise TransportError(f"{file.name} is over the USB interface's 100 MB limit")
        stem = name or file.stem
        folder_id, entries = self._folder(folder)
        taken = {self._name(e) for e in entries}
        used = stem
        for n in range(2, attempts + 2):
            if used not in taken:
                break
            used = f"{stem}_{n}"
        else:
            raise ExistsError(f'Too many notebooks named "{stem}"; pick another name')
        self._list(folder_id)  # the upload goes to the folder listed last
        boundary = uuid.uuid4().hex
        quoted = urllib.parse.quote(f"{used}{file.suffix or '.rmdoc'}", safe=" .-_()")
        body = (
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{quoted}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + _named(file, used)
            + f"\r\n--{boundary}--\r\n".encode()
        )
        self._request(
            "POST", "/upload", body,
            {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Origin": self.base,
                "Referer": self.base + "/",
            },
        )  # fmt: skip
        return used

    def mkdir(self, path: str) -> None:
        parent, name = self._split(path)
        _, entries = self._folder(parent)
        if self._find(entries, name, folder=True) is None:
            raise TransportError(
                f'The USB interface cannot make folders. Make the folder "{path}" on the '
                "tablet and run this again."
            )

    def mv(self, src: str, dst: str) -> None:
        raise TransportError(
            f'The USB interface cannot move or rename: "{src}" stays where it is. '
            f'Move it to "{dst}" on the tablet if you want it there.'
        )

    def rmdir(self, path: str) -> None:
        raise TransportError(f'The USB interface cannot remove "{path}"; do it on the tablet.')

    def check(self) -> list[str]:
        """What the tablet can do over the cable, for ``rmink transport check``."""
        entries = self._list()
        folders = sum(self._is_folder(e) for e in entries)
        lines = [f"The tablet answers: {folders} folders, {len(entries) - folders} notebooks."]
        notebook = next((e for e in entries if e.get("fileType", "notebook") == "notebook"
                         and not self._is_folder(e)), None)  # fmt: skip
        if notebook is not None:
            try:
                self.get("/" + self._name(notebook))
                lines.append("It hands out notebooks as .rmdoc, so rounds can read what you write.")
            except TransportError as e:
                lines.append(f"Fetching a notebook failed: {e}")
        lines.append(
            "It cannot make or move folders: make the rmink folders on the tablet by hand."
        )
        return lines


def _named(file: Path, name: str) -> bytes:
    """The .rmdoc ``file`` with ``name`` as its notebook name. The tablet names
    an uploaded notebook after the ``visibleName`` inside the archive, not
    after the file (measured on rm2), so the name is set there."""
    out = io.BytesIO()
    try:
        with zipfile.ZipFile(file) as zin, zipfile.ZipFile(out, "w") as zout:
            for info in zin.infolist():
                data = zin.read(info)
                if info.filename.endswith(".metadata") and "/" not in info.filename:
                    meta = json.loads(data)
                    meta["visibleName"] = name
                    data = json.dumps(meta, ensure_ascii=False).encode("utf-8")
                zout.writestr(info, data)
    except (zipfile.BadZipFile, ValueError) as e:
        raise TransportError(f"{file.name} is not a notebook file: {e}") from e
    return out.getvalue()
