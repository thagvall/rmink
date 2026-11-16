"""Swedish building knowledge for drawings, from the TOML files in ``data/``.

Terms and abbreviations, the drawing standard, symbols, materials with their
quality classes, typical assemblies, review rules (BFS, PBL/PBF, ElSL, practice) and
the permit process. ``reference()`` is a compact summary for Claude's system
prompt; ``lookup()`` returns full entries on demand, so the prompt stays small.
See docs/knowledge.md.
"""

from __future__ import annotations

import copy
import functools
import logging
import re
import tomllib
from importlib import resources

log = logging.getLogger(__name__)

FILES = (
    "terms", "drawing_standard", "symbols", "materials", "assemblies", "rules", "markup",
    "hatches", "process",
)  # fmt: skip

# lookup kind -> (file, table); on equal score, earlier kinds come first
KINDS = {
    "material": ("materials", "material"),
    "assembly": ("assemblies", "assembly"),
    "variant": ("assemblies", "variant"),
    "rule": ("rules", "rule"),
    "action": ("process", "action"),
    "symbol": ("symbols", "symbol"),
    "term": ("terms", "term"),
    "drawing_type": ("drawing_standard", "drawing_type"),
    "role": ("process", "role"),
    "hatch": ("hatches", "hatch"),
}

# Fields that name an entry (a hit here ranks above a hit in the description).
_NAME_FIELDS = ("id", "term", "abbr", "en", "name", "code", "title", "syn", "synonyms", "classes")
_TEXT_FIELDS = (
    "def", "note", "meaning", "duty", "shows", "message_sv", "exempt_if", "unless", "when",
)  # fmt: skip


@functools.cache
def builtin() -> dict[str, dict]:
    """The knowledge rmink ships, without packs."""
    data = resources.files(__package__) / "data"
    return {name: tomllib.loads((data / f"{name}.toml").read_text("utf-8")) for name in FILES}


@functools.cache
def load() -> dict[str, dict]:
    """The knowledge with the installed packs on top (see :mod:`rmink.packs`).
    A pack's entry with a fault (:func:`validate`) is left out with a warning,
    so a broken pack never breaks a drawing round."""
    data = merged()
    if data is builtin():
        return data
    for _ in range(5):  # leaving one out can orphan another
        faults = _problems(data)
        bad = {(file, table, key) for file, table, key, _ in faults}
        dropped = False
        for file, table, key, what in faults:
            log.warning("knowledge %s.%s %s: %s", file, table, key, what)
        for file, table in {(f, t) for f, t, _ in bad}:
            entries = data[file].get(table, [])
            keep = [
                e for e in entries
                if "pack" not in e or (file, table, (_key(e) or ("", "?"))[1]) not in bad
            ]  # fmt: skip
            dropped |= len(keep) != len(entries)
            data[file][table] = keep
        if not dropped:
            break
    return data


def _key(entry: dict) -> tuple[str, object] | None:
    for field in ("id", "letter", "n"):
        if field in entry:
            return field, entry[field]
    return None


def _merge(base: dict, layer: dict, pack: str) -> None:
    for name, value in layer.items():
        if name == "version":
            continue
        if isinstance(value, list) and all(isinstance(v, dict) for v in value):
            table = base.setdefault(name, [])
            at = {_key(e): i for i, e in enumerate(table)}
            for entry in value:
                entry = {**entry, "pack": pack}
                key = _key(entry)
                if key is not None and key in at:
                    table[at[key]] = entry
                else:
                    at[key] = len(table)
                    table.append(entry)
        elif isinstance(value, dict) and isinstance(base.get(name), dict):
            for k, v in value.items():
                old = base[name].get(k)
                if isinstance(old, list) and isinstance(v, list):
                    base[name][k] = old + [x for x in v if x not in old]
                else:
                    base[name][k] = v
        else:
            base[name] = value


def merged(packs_: tuple | None = None) -> dict[str, dict]:
    """The built-in knowledge with ``packs_`` (default: the installed ones)
    read on top. An entry with the id of one that is there replaces it, any
    other is added, and each says which ``pack`` it came from."""
    from rmink import packs

    layers = {name: packs.knowledge_layers(name, packs_) for name in FILES}
    if not any(layers.values()):
        return builtin()
    data = copy.deepcopy(builtin())
    for name, found in layers.items():
        for pack, layer in found:
            _merge(data[name], layer, pack)
    return data


def _required(table: list[dict]) -> set[str]:
    """The fields every built-in entry of a table has: the code reads them
    without asking, so a pack's entries need them too."""
    return set.intersection(*(set(e) for e in table)) if table else set()


def _problems(data: dict[str, dict]) -> list[tuple[str, str, object, str]]:
    """(file, table, id, what is wrong) for each fault in ``data``."""
    out: list[tuple[str, str, object, str]] = []
    base = builtin()

    def ids(file: str, table: str) -> set:
        return {e.get("id") for e in data[file].get(table, [])}

    for file in FILES:
        for table, entries in data[file].items():
            if not (isinstance(entries, list) and all(isinstance(e, dict) for e in entries)):
                continue
            need = _required(base[file].get(table, []))
            for e in entries:
                if "pack" in e and (missing := sorted(need - set(e))):
                    key = (_key(e) or ("", "?"))[1]
                    out.append((file, table, key, "missing " + ", ".join(missing)))

    std = data["drawing_standard"]
    rules, materials = ids("rules", "rule"), ids("materials", "material")
    types, hatches = ids("drawing_standard", "drawing_type"), ids("hatches", "hatch")
    targets = (
        types | ids("drawing_standard", "phase") | materials | ids("assemblies", "assembly")
        | set(data["rules"].get("vocabulary", {}).get("targets", []))
    )  # fmt: skip

    def refs(file: str, table: str, field: str, known: set, what: str) -> None:
        for e in data[file].get(table, []):
            value = e.get(field, [])
            unknown = set(value if isinstance(value, list) else [value]) - known - {""}
            if unknown:
                names = ", ".join(sorted(map(str, unknown)))
                out.append((file, table, e.get("id", "?"), f"unknown {what} {names}"))

    refs("materials", "material", "group", ids("materials", "group"), "group")
    refs("materials", "material", "hatch", hatches, "hatch")
    refs("materials", "material", "rules", rules, "rule")
    refs("hatches", "hatch", "used_for", materials, "material")
    refs("assemblies", "assembly", "rules", rules, "rule")
    refs("assemblies", "assembly", "used_in", types, "drawing type")
    refs("assemblies", "variant", "assembly", ids("assemblies", "assembly"), "assembly")
    refs("rules", "rule", "applies_to", targets, "target")
    refs("symbols", "symbol", "rules", rules, "rule")
    refs("symbols", "symbol", "drawing_types", types, "drawing type")
    for table in ("assembly", "variant"):
        for e in data["assemblies"].get(table, []):
            for layer in e.get("layers", []):
                if layer.get("material") not in materials:
                    what = f"unknown material {layer.get('material')}"
                    out.append(("assemblies", table, e.get("id", "?"), what))
    letters = {d.get("letter") for d in std.get("discipline", [])} | {""}
    for s in data["symbols"].get("symbol", []):
        if s.get("discipline", "") not in letters:
            out.append(("symbols", "symbol", s.get("id", "?"), "unknown discipline"))
        if "paths" in s and (why := _bad_paths(s["paths"])):
            out.append(("symbols", "symbol", s.get("id", "?"), f"paths {why}"))
    return out


def validate(data: dict[str, dict]) -> list[str]:
    """What is wrong with knowledge ``data`` (from :func:`merged`): entries
    from packs that lack a field the built-in ones all have, references to
    ids that do not exist, and symbol geometry that does not fit the unit box.
    An empty list when it holds together."""
    return [f"{file}.{table} {key}: {what}" for file, table, key, what in _problems(data)]


def _bad_paths(paths: object) -> str:
    """Why ``paths`` is not symbol geometry, or "" when it is: polylines of at
    least two [x, y] points inside the unit box (-0.5..0.5, y down)."""
    if not isinstance(paths, list) or not paths:
        return "must be a list of polylines"
    for line in paths:
        if not isinstance(line, list) or len(line) < 2:
            return "has a polyline with fewer than two points"
        for point in line:
            ok = (
                isinstance(point, list)
                and len(point) == 2
                and all(isinstance(c, (int, float)) and not isinstance(c, bool) for c in point)
            )
            if not ok:
                return "has a point that is not [x, y]"
            if max(abs(point[0]), abs(point[1])) > 0.55:
                return "go outside the unit box (-0.5..0.5)"
    return ""


def _fold(text: str) -> str:
    text = text.casefold().replace("×", "x").replace("*", "x")
    return re.sub(r"\s+", " ", text).strip()


def _words(text: str) -> set[str]:
    return set(re.findall(r"[\wåäö/+±.,-]+", text))


def _values(item: dict, fields: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for f in fields:
        v = item.get(f)
        if isinstance(v, str) and v:
            out.append(v)
        elif isinstance(v, list):
            out += [x for x in v if isinstance(x, str)]
    return out


def _score(query: str, item: dict) -> int:
    words = _words(query)
    best = 0
    for name in map(_fold, _values(item, _NAME_FIELDS)):
        if name == query:
            return 3
        # a multi-word name inside the query ("gips 13" in "gips 13 dubbel"),
        # or a short name as a whole word ("imp" in "imp 45x145")
        if (" " in name and name in query) or name in words:
            best = max(best, 2)
    if best == 0 and len(query) >= 4:
        text = " ".join(map(_fold, _values(item, _NAME_FIELDS + _TEXT_FIELDS)))
        if query in text:
            best = 1
    return best


def _rule_brief(rule_id: str) -> dict | None:
    for r in load()["rules"]["rule"]:
        if r["id"] == rule_id:
            return {k: r.get(k) for k in ("id", "title", "source", "ref", "severity", "verified")}
    return None


def _expand(kind: str, item: dict) -> dict:
    out = {"entry": kind, **item}
    if rules := item.get("rules"):
        out["rules"] = [b for r in rules if (b := _rule_brief(r))]
    if kind == "material":
        hatches = {h["id"]: h for h in load()["hatches"]["hatch"]}
        if h := hatches.get(item.get("hatch", "")):
            out["hatch"] = {"id": h["id"], "name": h["name"], "note": h["note"]}
    if kind == "assembly":
        out["variants"] = [f"{v['key']} {v['id']}: {v['name']}" for v in variants(item["id"])]
    if kind == "variant":
        out.update(variant_facts(item))
        out["option"] = option(item)
    return out


def _sv(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def option(variant: dict, key: str | None = None) -> dict:
    """A variant as an alternative for a drawing's alternatives page
    (rmink.drawing.model.Option): layer texts, facts, pros and cons."""
    materials = {m["id"]: m for m in load()["materials"]["material"]}
    layers = []
    for layer in variant["layers"]:
        name = materials[layer["material"]]["name"].split(" (")[0]
        d = layer["thickness_mm"]
        head = f"{name} {_sv(d)}" if d else name
        text = f"{head}: {layer['note']}" if layer.get("note") else head
        layers.append({"text": text, "thickness_mm": d, "material": layer["material"]})
    f = variant_facts(variant)
    facts = [f"Tjocklek ≈ {_sv(f['thickness_mm'])} mm"]
    if "u_estimate" in f:
        facts.append(f"U ≈ {_sv(round(f['u_estimate'], 2))} W/m²K (uppskattning)")
    if f["weight_kg_m2"]:
        facts.append(f"Vikt ≈ {f['weight_kg_m2']} kg/m²")
    facts.append(f"Kostnad: {variant['cost']}")
    return {
        "key": key or variant["key"],
        "title": variant["name"],
        "variant": variant["id"],
        "layers": layers,
        "facts": facts,
        "pros": list(variant["pros"]),
        "cons": list(variant["cons"]) + ([variant["note"]] if variant.get("note") else []),
    }


def variants(assembly_id: str) -> list[dict]:
    """The alternatives to an assembly, A first."""
    found = [v for v in load()["assemblies"].get("variant", []) if v["assembly"] == assembly_id]
    return sorted(found, key=lambda v: v["key"])


def variant_facts(variant: dict) -> dict:
    """Computed facts for comparing variants: total thickness, weight per m²
    from the materials' densities and, for heated parts, an estimated U-value."""
    from rmink import calc

    materials = {m["id"]: m for m in load()["materials"]["material"]}
    thickness = weight = 0.0
    seen_zone = None
    for layer in variant["layers"]:
        d = layer["thickness_mm"]
        share = layer.get("fraction", 1.0)
        # layers sharing a zone (studs and insulation) add their thickness once
        if share < 1 and seen_zone == d:
            pass
        else:
            thickness += d
        seen_zone = d if share < 1 else None
        weight += d / 1000 * share * materials[layer["material"]].get("density", 0)
    facts = {"thickness_mm": round(thickness, 1), "weight_kg_m2": round(weight)}
    if variant.get("u_kind"):
        u = calc.u_value(variant["layers"], variant["u_kind"])
        facts["u_estimate"] = round(u["U"], 3)
        facts["u_note"] = u["note"]
    return facts


def symbol(kind: str) -> dict | None:
    """The catalogue entry of a drawn symbol, with its IFC class and its symbol in
    Open PDF Studio's library, or None for a kind that is not in the catalogue."""
    return next((s for s in load()["symbols"]["symbol"] if s["id"] == kind), None)


def _table(kind: str) -> list[dict]:
    file, table = KINDS[kind]
    return load()[file].get(table, [])


def lookup(query: str, kind: str | None = None, limit: int = 6) -> list[dict]:
    """Entries matching ``query`` (an id, term, abbreviation, handwritten
    variant such as "gips 13", or words from a description), best first."""
    q = _fold(query)
    if not q:
        return []
    kinds = [kind] if kind in KINDS else list(KINDS)
    hits = [
        (score, n, k, item)
        for n, k in enumerate(kinds)
        for item in _table(k)
        if (score := _score(q, item))
    ]
    hits.sort(key=lambda h: (-h[0], h[1]))
    return [_expand(k, item) for _, _, k, item in hits[:limit]]


def reference() -> str:
    """A compact summary for the system prompt. Details via lookup()."""
    kb = load()
    std, mat = kb["drawing_standard"], kb["materials"]
    lines = [
        f"Swedish building knowledge (rmink, version {kb['rules']['version']}). Use the "
        "lookup_knowledge tool for full entries: material classes, assembly layers, exact "
        "rule values and their legal source.",
        "",
        "Rules: BBR/EKS are replaced by BFS 2024:4-13 (the old rules could not be used after "
        "2026-07-01). Severity 'fel' = breaks a stated number; 'fråga' = a performance "
        "requirement or practice value, ask instead of flagging; 'info' = a note. Practice "
        "values (source 'praxis', e.g. railing 1.1 m, 2h+d) are never errors. Permit rules "
        "(PBL/PBF) are always questions: rmink does not know whether the plot is inside a "
        "detaljplan. Write remarks briefly, with the source in parentheses, e.g. "
        "'(BFS 2024:9 2 kap. 11 §)'.",
        "",
        "Drawing types (scales): "
        + "; ".join(f"{d['name']} ({', '.join(d['scales'])})" for d in std["drawing_type"]),
        "Phases: " + ", ".join(p["name"] for p in std["phase"]),
        "Title block (required): "
        + ", ".join(f["name"] for f in std["title_block_field"] if f["required"]),
        "",
        "Abbreviations: "
        + "; ".join(
            f"{t['abbr']}={t['term']}"
            for t in kb["terms"]["term"]
            if t["abbr"] and t["abbr"] != t["term"]
        ),
        "",
        "Materials (id: name | classes | must state | example):",
    ]
    for m in mat["material"]:
        lines.append(
            f"- {m['id']}: {m['name']} | {', '.join(m['classes'])} | "
            f"{', '.join(m['required'])} | {m['example']}"
        )
    lines += [
        "",
        "Symbols (kind = legend name: handwritten as; label written next to it):",
    ]
    for s in kb["symbols"]["symbol"]:
        line = f"- {s['id']} = {s['name']}: {', '.join(s['syn'][:4])}"
        if s["label"]:
            line += f"; label '{s['label']}'"
        lines.append(line)
    lines += ["", "Assemblies (code id: name):"]
    lines += [f"- {a['code']} {a['id']}: {a['name']}" for a in kb["assemblies"]["assembly"]]
    lines += ["", "Variants to compare (assembly: key id name, cost, U≈ estimate):"]
    for a in kb["assemblies"]["assembly"]:
        for v in variants(a["id"]):
            facts = variant_facts(v)
            u = f", U≈{facts['u_estimate']}" if "u_estimate" in facts else ""
            lines.append(f"- {a['code']}: {v['key']} {v['id']} {v['name']}, {v['cost']}{u}")
    lines += ["", "Rules (id: title [source ref] severity):"]
    lines += [
        f"- {r['id']}: {r['title']} [{r['source']} {r['ref']}] {r['severity']}"
        for r in kb["rules"]["rule"]
        if r["source"] != "rmink"
    ]
    lines += ["", "Permit decisions (action: default; exempt if …; changes if …):"]
    for a in kb["process"]["action"]:
        line = f"- {a['id']}: {a['name']} → {a['default']}"
        if a["exempt_if"]:
            line += f"; {a['then']} if: {a['exempt_if']}"
        if a["unless"]:
            line += f"; but: {a['unless']}"
        lines.append(line)
    return "\n".join(lines)
