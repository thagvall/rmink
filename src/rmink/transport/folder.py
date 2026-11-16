"""A folder on this computer as the place notebooks are left and fetched.

``/rmink/Bygg/Altan/Altan r02`` is ``<root>/rmink/Bygg/Altan/Altan r02.rmdoc``.
rmink needs no reMarkable Cloud for it; what carries the files between the
folder and the tablet (the USB web interface, a sync tool, a server of one's
own) is up to the user.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from rmink.transport.errors import ExistsError, NotFoundError, TransportError

SUFFIXES = (".rmdoc", ".zip")  # the same archive under both names


class FolderTransport:
    name = "folder"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    def __repr__(self) -> str:
        return f"folder:{self.root}"

    def _path(self, path: str) -> Path:
        parts = [p for p in path.split("/") if p]
        for p in parts:
            if p in (".", "..") or os.sep in p or (os.altsep and os.altsep in p):
                raise TransportError(f'"{path}" is not a path inside {self.root}')
        return self.root.joinpath(*parts)

    def _document(self, path: str) -> Path | None:
        base = self._path(path)
        if base == self.root:
            return None
        for suffix in SUFFIXES:
            file = base.with_name(base.name + suffix)
            if file.is_file():
                return file
        return None

    def _folder(self, path: str) -> Path:
        folder = self._path(path)
        if folder == self.root:
            folder.mkdir(parents=True, exist_ok=True)
        if not folder.is_dir():
            raise NotFoundError(f'"{path}" does not exist')
        return folder

    def ls(self, path: str = "/") -> list:
        from rmink.transport import Entry

        entries = []
        for item in sorted(self._folder(path).iterdir(), key=lambda p: p.name):
            if item.name.startswith("."):
                continue
            if item.is_dir():
                entries.append(Entry(item.name, True))
            elif item.suffix in SUFFIXES:
                entries.append(Entry(item.name[: -len(item.suffix)], False))
        return entries

    def get(self, path: str) -> bytes:
        file = self._document(path)
        if file is None:
            raise NotFoundError(f'"{path}" does not exist in {self.root}')
        return file.read_bytes()

    def put(
        self, file: Path, folder: str = "/", name: str | None = None, attempts: int = 20
    ) -> str:
        target = self._folder(folder)
        stem = name or file.stem
        base = folder.rstrip("/")
        for n in range(1, attempts + 2):
            used = stem if n == 1 else f"{stem}_{n}"
            if self._document(f"{base}/{used}") is None:
                # A sync tool watching the folder never sees half a notebook.
                partial = target / f".{used}.part"
                shutil.copyfile(file, partial)
                os.replace(partial, target / f"{used}.rmdoc")
                return used
        raise ExistsError(f'Too many notebooks named "{stem}"; pick another name')

    def mkdir(self, path: str) -> None:
        folder = self._path(path)
        self._folder(path.rstrip("/").rpartition("/")[0] or "/")  # the parent must exist
        folder.mkdir(exist_ok=True)

    def mv(self, src: str, dst: str) -> None:
        document = self._document(src)
        source = document or self._path(src)
        if document is None and (source == self.root or not source.is_dir()):
            raise NotFoundError(f'"{src}" does not exist')
        target = self._path(dst)
        if not target.parent.is_dir():
            raise NotFoundError(f'The folder of "{dst}" does not exist')
        if document is not None:
            if self._document(dst) is not None:
                raise ExistsError(dst)
            target = target.with_name(target.name + document.suffix)
        elif target.exists():
            raise ExistsError(dst)
        source.rename(target)

    def rmdir(self, path: str) -> None:
        folder = self._folder(path)
        if folder == self.root:
            raise TransportError("The root folder stays")
        left = list(folder.iterdir())
        if any(not f.name.startswith(".") or f.is_dir() for f in left):
            raise TransportError(f'Could not remove "{path}": it is not empty')
        for f in left:  # .DS_Store and the like
            f.unlink()
        folder.rmdir()
