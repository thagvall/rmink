"""How notebooks get to the tablet and back.

A transport is a tree of folders and notebooks, each notebook a ``.rmdoc``:
the reMarkable Cloud (``cloud``), a folder on this computer (``folder:PATH``),
or one a plugin brings (``NAME:ARG``, entry point group ``rmink.transports``).
The workflows only use the six calls of :class:`Transport`, so drawings,
workbooks and sheets go their rounds the same way over any of them.

Which one is used: ``--via`` / ``$RMINK_TRANSPORT``, else ``[transport]
default`` in ``~/.config/rmink/config.toml``, else the cloud when connected.
See docs/plugins.md.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from rmink.transport.errors import AuthError, ExistsError, NotFoundError, TransportError
from rmink.transport.folder import FolderTransport

__all__ = [
    "AuthError", "CloudTransport", "Entry", "ExistsError", "FolderTransport", "NotFoundError",
    "Transport", "TransportError", "config_path", "default", "fetch", "names", "of", "open",
    "spec", "use",
]  # fmt: skip

ENV = "RMINK_TRANSPORT"
BUILTIN = ("cloud", "folder")


@dataclass(frozen=True)
class Entry:
    name: str
    folder: bool


@runtime_checkable
class Transport(Protocol):
    """Paths are absolute with ``/`` between folders; a notebook's path has no
    file extension ("/rmink/Bygg/Altan/Altan r02")."""

    name: str

    def ls(self, path: str = "/") -> list[Entry]:
        """Folders and notebooks in ``path``; :class:`NotFoundError` without it."""

    def get(self, path: str) -> bytes:
        """The notebook at ``path`` as .rmdoc bytes."""

    def put(self, file: Path, folder: str = "/", name: str | None = None) -> str:
        """Leave the .rmdoc ``file`` in ``folder`` (which must exist) as
        ``name`` (default: the file's name). A taken name becomes "name_2",
        "name_3"; returns the name used."""

    def mkdir(self, path: str) -> None:
        """Make the folder ``path``; its parent must exist. One that is
        already there counts as made."""

    def mv(self, src: str, dst: str) -> None:
        """Move a notebook or folder to the full path ``dst``;
        :class:`ExistsError` when that name is taken."""

    def rmdir(self, path: str) -> None:
        """Remove the empty folder ``path``."""


@dataclass(frozen=True)
class CloudTransport:
    """The user's reMarkable Cloud, through :mod:`rmink.cloud`."""

    token: str
    name = "cloud"

    def __repr__(self) -> str:  # never the token
        return "cloud"

    def ls(self, path: str = "/") -> list[Entry]:
        from rmink import cloud

        return cloud.ls(self.token, path)

    def get(self, path: str) -> bytes:
        from rmink import cloud

        return cloud.get(self.token, path)

    def put(self, file: Path, folder: str = "/", name: str | None = None) -> str:
        from rmink import cloud

        return cloud.put(file, self.token, folder=folder, name=name)

    def mkdir(self, path: str) -> None:
        from rmink import cloud

        cloud.mkdir(self.token, path)

    def mv(self, src: str, dst: str) -> None:
        from rmink import cloud

        cloud.mv(self.token, src, dst)

    def rmdir(self, path: str) -> None:
        from rmink import cloud

        cloud.rmdir(self.token, path)


def config_path() -> Path:
    from rmink.devices import config_dir

    return config_dir() / "config.toml"


def _config() -> dict:
    path = config_path()
    if not path.is_file():
        return {}
    return tomllib.loads(path.read_text(encoding="utf-8")).get("transport", {})


def spec() -> str | None:
    """The transport chosen with ``--via``/$RMINK_TRANSPORT or saved by
    ``rmink transport use``; None leaves it to the cloud."""
    return os.environ.get(ENV) or _config().get("default") or None


def use(value: str) -> Path:
    """Save ``value`` ("cloud", "folder:~/Sync/rmink") as the transport to
    use, after checking that it opens."""
    if value.partition(":")[0] != "cloud":
        open(value)
    path = config_path()
    data = tomllib.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if set(data) - {"transport"}:
        raise TransportError(f"{path} has other settings; set [transport] default there by hand")
    quoted = value.replace("\\", "\\\\").replace('"', '\\"')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[transport]\ndefault = "{quoted}"\n', encoding="utf-8")
    return path


def names() -> list[str]:
    """The transports there are: built in, then the plugins'."""
    from rmink import plugins

    return [*BUILTIN, *(n for n in plugins.found("rmink.transports") if n not in BUILTIN)]


def open(value: str) -> Transport:  # noqa: A001 - transport.open reads well
    """The transport ``value`` names: "cloud", "folder:PATH" or "PLUGIN:ARG"."""
    from rmink import plugins

    name, _, arg = value.strip().partition(":")
    if name == "cloud":
        from rmink import cloud

        token = cloud.load_token()
        if not token:
            raise AuthError(
                f"Not connected to reMarkable Cloud; run: rmink cloud connect CODE "
                f"({cloud.CONNECT_URL})"
            )
        return CloudTransport(token)
    if name == "folder":
        arg = arg or _config().get("folder", {}).get("path", "")
        if not arg:
            raise TransportError('Give the folder: "folder:~/Documents/rmink"')
        return FolderTransport(arg)
    factory = plugins.load("rmink.transports", name)
    if factory is None:
        raise TransportError(
            f'There is no transport "{name}". Choose one of: ' + ", ".join(names())
        )
    try:
        return factory(arg)
    except TransportError:
        raise
    except Exception as e:
        raise TransportError(f'The transport "{name}" did not open: {e}') from e


def default() -> Transport | None:
    """The transport to use, or None when none is chosen and the cloud is not
    connected."""
    if value := spec():
        return open(value)
    from rmink import cloud

    token = cloud.load_token()
    return CloudTransport(token) if token else None


def of(via: Transport | str) -> Transport:
    """``via`` as a transport; a string is a reMarkable Cloud device token."""
    return CloudTransport(via) if isinstance(via, str) else via


def fetch(source: str, via: Transport | str | None = None) -> bytes:
    """A notebook's bytes from a local ``.rmdoc`` file or, failing that, from
    that path in the transport."""
    path = Path(source).expanduser()
    if path.is_file():
        return path.read_bytes()
    t = of(via) if via is not None else default()
    if t is None:
        raise AuthError(
            f'"{source}" is not a local file and rmink is not connected to reMarkable '
            "Cloud; run `rmink cloud connect`, or `rmink transport use folder:PATH` to "
            "work from a folder"
        )
    return t.get(source if source.startswith("/") else "/" + source)
