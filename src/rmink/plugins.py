"""Parts other packages bring to rmink, found through entry points.

A package declares what it brings in its ``pyproject.toml``::

    [project.entry-points."rmink.transports"]
    webdav = "rmink_webdav:open"

Nothing is imported until it is used, a plugin that fails to load is skipped
with a warning, and ``RMINK_NO_PLUGINS=1`` turns them all off. What each group
expects is in docs/plugins.md.
"""

from __future__ import annotations

import functools
import logging
import os
from dataclasses import dataclass
from importlib import metadata

log = logging.getLogger(__name__)

API_VERSION = 1

GROUPS = {
    "rmink.transports": "factory(arg: str) -> Transport, named by its scheme",
    "rmink.packs": "a package (or a function returning a folder) with pack.toml",
    "rmink.importers": "load(path, mode, pages) -> list[Source], named by file suffix",
    "rmink.exporters": "export(drawing) -> bytes, named by format",
    "rmink.commands": "a typer.Typer, named by the command",
    "rmink.mcp_tools": "register(server) -> None",
}

_failed: dict[tuple[str, str], str] = {}


def enabled() -> bool:
    return os.environ.get("RMINK_NO_PLUGINS", "") in ("", "0")


@functools.cache
def _scan(group: str) -> tuple[metadata.EntryPoint, ...]:
    return tuple(metadata.entry_points(group=group))


def _entry_points(group: str) -> tuple[metadata.EntryPoint, ...]:
    return _scan(group)


def reset() -> None:
    """Forget what was found (tests, or after installing a package)."""
    _scan.cache_clear()
    _failed.clear()


def found(group: str) -> dict[str, metadata.EntryPoint]:
    """The group's entry points by name, not yet imported. Of two with the
    same name the first by package name is used."""
    if not enabled():
        return {}
    out: dict[str, metadata.EntryPoint] = {}
    for ep in sorted(_entry_points(group), key=lambda e: (e.name, _package(e)[0])):
        if ep.name in out:
            log.warning("plugin %s %r from %s is hidden by %s", group, ep.name,
                        _package(ep)[0], _package(out[ep.name])[0])  # fmt: skip
            continue
        out[ep.name] = ep
    return out


def load(group: str, name: str):
    """The object the plugin ``name`` brings, or None when there is none or
    it does not load."""
    ep = found(group).get(name)
    if ep is None or (group, name) in _failed:
        return None
    try:
        return ep.load()
    except Exception as e:  # a plugin must never stop rmink
        _failed[group, name] = f"{type(e).__name__}: {e}"
        log.warning("plugin %s %r did not load: %s", group, name, _failed[group, name])
        return None


def load_all(group: str) -> dict[str, object]:
    return {n: obj for n in found(group) if (obj := load(group, n)) is not None}


def _package(ep: metadata.EntryPoint) -> tuple[str, str]:
    dist = getattr(ep, "dist", None)
    return (dist.name, dist.version) if dist is not None else ("?", "")


@dataclass(frozen=True)
class Info:
    group: str
    name: str
    package: str
    version: str
    target: str
    error: str = ""  # why it did not load


def listing(check: bool = True) -> list[Info]:
    """Every plugin installed; with ``check`` each is imported to see that it loads."""
    out = []
    for group in GROUPS:
        for name, ep in found(group).items():
            if check:
                load(group, name)
            out.append(Info(group, name, *_package(ep), ep.value, _failed.get((group, name), "")))
    return out
