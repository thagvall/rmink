"""Content packs: knowledge, symbols and workbook groups as data, no code.

A pack is a folder::

    pack.toml            name, version, description, api = 1
    knowledge/*.toml     the file names and tables of rmink/knowledge/data
    workbook/*.toml      [[group]] tables as in rmink/workbook/data/skola.toml

Packs are read on top of what rmink ships, later ones over earlier: packages
with an ``rmink.packs`` entry point, then the folders in
``~/.config/rmink/packs/``, then the user's own ``~/.config/rmink/knowledge/``
and ``~/.config/rmink/workbook/``. An entry with the id of one that is there
replaces it; any other is added. See docs/plugins.md.
"""

from __future__ import annotations

import functools
import logging
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from rmink import plugins

log = logging.getLogger(__name__)

USER = "egna"  # the pack made of the user's own files in the config folder


@dataclass(frozen=True)
class Pack:
    name: str
    version: str
    description: str
    root: object  # a Path or an importlib.resources Traversable
    origin: str  # the package or folder it comes from


def _toml(file) -> dict | None:
    try:
        return tomllib.loads(file.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        log.warning("pack file %s was skipped: %s", file, e)
        return None


def read_pack(root, origin: str) -> Pack | None:
    """The pack in the folder ``root``, or None (with a warning) when it has
    no usable ``pack.toml`` or is made for a newer rmink."""
    manifest = root / "pack.toml"
    if not manifest.is_file():
        log.warning("%s has no pack.toml and is not read as a pack", origin)
        return None
    meta = _toml(manifest)
    if meta is None or not meta.get("name"):
        log.warning("%s: pack.toml needs a name", origin)
        return None
    if int(meta.get("api", 1)) > plugins.API_VERSION:
        log.warning("pack %s needs a newer rmink (api %s)", meta["name"], meta["api"])
        return None
    return Pack(
        str(meta["name"]), str(meta.get("version", "")), str(meta.get("description", "")),
        root, origin,
    )  # fmt: skip


def _plugin_root(obj):
    if callable(obj):
        obj = obj()
    if isinstance(obj, (str, Path)):
        return Path(obj)
    return resources.files(obj)  # a module or package


@functools.cache
def all_packs() -> tuple[Pack, ...]:
    if not plugins.enabled():
        return ()
    from rmink.devices import config_dir

    out: list[Pack] = []
    for name, ep in plugins.found("rmink.packs").items():
        obj = plugins.load("rmink.packs", name)
        if obj is None:
            continue
        try:
            pack = read_pack(_plugin_root(obj), f"plugin {name} ({ep.value})")
        except Exception as e:  # a plugin must never stop rmink
            log.warning("pack plugin %r was skipped: %s", name, e)
            continue
        if pack:
            out.append(pack)
    config = config_dir()
    if (config / "packs").is_dir():
        for folder in sorted(p for p in (config / "packs").iterdir() if p.is_dir()):
            if pack := read_pack(folder, str(folder)):
                out.append(pack)
    if (config / "knowledge").is_dir() or (config / "workbook").is_dir():
        out.append(Pack(USER, "", "Your own files", config, str(config)))
    return tuple(out)


def reset() -> None:
    """Read packs and everything built from them again (tests, a new pack)."""
    from rmink import knowledge
    from rmink.drawing import symbols
    from rmink.workbook import catalog

    plugins.reset()
    all_packs.cache_clear()
    knowledge.load.cache_clear()
    symbols.symbols.cache_clear()
    catalog.load.cache_clear()


def knowledge_layers(file: str, packs: tuple[Pack, ...] | None = None) -> list[tuple[str, dict]]:
    """``knowledge/<file>.toml`` of each pack that has it, as (pack, data)."""
    out = []
    for pack in all_packs() if packs is None else packs:
        path = pack.root / "knowledge" / f"{file}.toml"
        if path.is_file() and (data := _toml(path)) is not None:
            out.append((pack.name, data))
    return out


def workbook_groups(packs: tuple[Pack, ...] | None = None) -> list[tuple[str, dict]]:
    """The ``[[group]]`` tables of every pack's ``workbook/*.toml``, as (pack, group)."""
    out = []
    for pack in all_packs() if packs is None else packs:
        folder = pack.root / "workbook"
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir(), key=lambda p: p.name):
            if path.name.endswith(".toml") and (data := _toml(path)) is not None:
                out += [(pack.name, g) for g in data.get("group", [])]
    return out


def check(folder: Path) -> list[str]:
    """What is wrong with the pack in ``folder``, read on top of what rmink
    ships; an empty list when it is fine."""
    from pydantic import ValidationError

    from rmink import knowledge
    from rmink.workbook import catalog

    folder = Path(folder)
    problems: list[str] = []
    manifest = folder / "pack.toml"
    if not manifest.is_file():
        return [f"{manifest} is missing"]
    try:
        meta = tomllib.loads(manifest.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
        return [f"pack.toml: {e}"]
    if not meta.get("name"):
        problems.append("pack.toml: name is missing")
    if int(meta.get("api", 1)) > plugins.API_VERSION:
        problems.append(f"pack.toml: api {meta['api']} is newer than this rmink's")
    pack = Pack(str(meta.get("name", folder.name)), "", "", folder, str(folder))

    if (folder / "knowledge").is_dir():
        for path in sorted((folder / "knowledge").iterdir()):
            if path.suffix != ".toml":
                continue
            if path.stem not in knowledge.FILES:
                problems.append(
                    f"knowledge/{path.name}: not a file rmink reads; the names are "
                    + ", ".join(knowledge.FILES)
                )
                continue
            try:
                tomllib.loads(path.read_text(encoding="utf-8"))
            except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
                problems.append(f"knowledge/{path.name}: {e}")
        problems += knowledge.validate(knowledge.merged((pack,)))
    seen = set()
    for _, g in workbook_groups((pack,)):
        try:
            group = catalog.Group.model_validate(g)
        except ValidationError as e:
            problems.append(f"workbook group {g.get('id', '?')}: {e.errors()[0]['msg']}")
            continue
        if group.id in seen:
            problems.append(f"workbook group {group.id}: twice in the pack")
        seen.add(group.id)
    return problems
