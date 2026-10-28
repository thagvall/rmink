"""Consistency checks for the construction knowledge base in knowledge/*.toml.

The data is not wired into the app yet; these tests keep the cross references
(material → hatch/rule, assembly → material, rule → target, term → ref) intact
while it grows.
"""

import tomllib
from pathlib import Path

import pytest

from rmink.drawing.model import DEFAULT_CATEGORIES

ROOT = Path(__file__).resolve().parents[1] / "knowledge"
FILES = ["terms", "drawing_standard", "materials", "assemblies", "rules", "markup", "hatches"]
RULE_KINDS = {"geometric", "attribute", "completeness", "manual"}
SEVERITIES = {"fel", "fråga", "info"}


@pytest.fixture(scope="module")
def kb():
    return {name: tomllib.loads((ROOT / f"{name}.toml").read_text("utf-8")) for name in FILES}


def _ids(items):
    return [item["id"] for item in items]


def _assert_unique(ids, what):
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"duplicate {what} ids: {dupes}"


@pytest.fixture(scope="module")
def ids(kb):
    std = kb["drawing_standard"]
    return {
        "drawing_type": set(_ids(std["drawing_type"])),
        "phase": set(_ids(std["phase"])),
        "title_block": set(_ids(std["title_block_field"])),
        "designation": set(_ids(std["designation"])),
        "group": set(_ids(kb["materials"]["group"])),
        "material": set(_ids(kb["materials"]["material"])),
        "assembly": set(_ids(kb["assemblies"]["assembly"])),
        "rule": set(_ids(kb["rules"]["rule"])),
        "hatch": set(_ids(kb["hatches"]["hatch"])),
        "vocabulary": set(kb["rules"]["vocabulary"]["targets"]),
    }


def _known(ids, *kinds):
    return set().union(*(ids[k] for k in kinds))


def test_every_file_has_a_version(kb):
    for name, data in kb.items():
        assert data.get("version"), f"{name}.toml has no version"


def test_ids_are_unique(kb):
    std = kb["drawing_standard"]
    for what, items in [
        ("drawing_type", std["drawing_type"]),
        ("phase", std["phase"]),
        ("line", std["line"]),
        ("group", kb["materials"]["group"]),
        ("material", kb["materials"]["material"]),
        ("assembly", kb["assemblies"]["assembly"]),
        ("rule", kb["rules"]["rule"]),
        ("hatch", kb["hatches"]["hatch"]),
        ("term", kb["terms"]["term"]),
        ("markup_type", kb["markup"]["markup_type"]),
        ("status", kb["markup"]["status"]),
    ]:
        _assert_unique(_ids(items), what)


def test_materials_reference_existing_groups_hatches_and_rules(kb, ids):
    for m in kb["materials"]["material"]:
        assert m["group"] in ids["group"], m["id"]
        assert m["hatch"] in ids["hatch"], m["id"]
        assert set(m["rules"]) <= ids["rule"], (m["id"], set(m["rules"]) - ids["rule"])
        assert m["required"] is not None and m["label_template"], m["id"]
        assert isinstance(m["ama_ref"], str), m["id"]


def test_hatches_are_used_by_existing_materials(kb, ids):
    for h in kb["hatches"]["hatch"]:
        unknown = set(h["used_for"]) - ids["material"]
        assert not unknown, (h["id"], unknown)


def test_assemblies_are_built_from_known_materials(kb, ids):
    for a in kb["assemblies"]["assembly"]:
        assert a["layers"], a["id"]
        for layer in a["layers"]:
            assert layer["material"] in ids["material"], (a["id"], layer["material"])
        assert set(a["rules"]) <= ids["rule"], (a["id"], set(a["rules"]) - ids["rule"])
        assert set(a["used_in"]) <= ids["drawing_type"], a["id"]


def test_rules_are_sourced_and_target_known_things(kb, ids):
    targets = _known(ids, "drawing_type", "material", "assembly", "vocabulary")
    for r in kb["rules"]["rule"]:
        assert r["kind"] in RULE_KINDS, r["id"]
        assert r["severity"] in SEVERITIES, r["id"]
        assert isinstance(r["verified"], bool), r["id"]
        assert r["source"] and r["message_sv"], r["id"]
        assert set(r["applies_to"]) <= targets, (r["id"], set(r["applies_to"]) - targets)
        if r["source"].startswith("BFS"):
            assert r["url"].startswith("https://rinfo.boverket.se/"), r["id"]
            assert r["verified"] and r.get("checked"), r["id"]
        if r["source"] == "praxis":
            # practice values never block: they are asked, not flagged as errors
            assert not r["verified"] and r["severity"] != "fel", r["id"]


def test_term_refs_resolve(kb, ids):
    known = _known(ids, *ids.keys())
    for t in kb["terms"]["term"]:
        assert t["ref"] == "" or t["ref"] in known, (t["id"], t["ref"])


def test_line_types_map_to_rmink_categories(kb):
    names = {c.name for c in DEFAULT_CATEGORIES}
    for line in kb["drawing_standard"]["line"]:
        assert line["rmink_category"] in names, line["id"]


def test_markup_statuses_map_to_annotation_status(kb):
    assert {s["rmink"] for s in kb["markup"]["status"]} <= {"open", "accepted", "rejected"}


def test_handwritten_synonyms_point_to_one_material(kb):
    owners: dict[str, str] = {}
    for m in kb["materials"]["material"]:
        for s in m["synonyms"]:
            key = s.casefold()
            owner = owners.setdefault(key, m["id"])
            assert owner == m["id"], f"'{s}' in {owner} and {m['id']}"
