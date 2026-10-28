"""Consistency checks for the building knowledge in src/rmink/knowledge/data.

They keep the cross references (material → hatch/rule, assembly → material,
rule → target, term → ref) intact while the data grows, and check lookup()
and the prompt reference built from it.
"""

import pytest

from rmink import knowledge
from rmink.drawing.model import DEFAULT_CATEGORIES

LAW_SOURCES = {"PBL", "PBF", "ElSL"}
RULE_KINDS = {"geometric", "attribute", "completeness", "manual"}
SEVERITIES = {"fel", "fråga", "info"}


@pytest.fixture(scope="module")
def kb():
    return knowledge.load()


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
        "permit": set(_ids(kb["process"]["permit"])),
        "action": set(_ids(kb["process"]["action"])),
        "role": set(_ids(kb["process"]["role"])),
        "step": set(_ids(kb["process"]["step"])),
        "document": set(_ids(kb["process"]["document"])),
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
        ("symbol", kb["symbols"]["symbol"]),
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
    targets = _known(ids, "drawing_type", "phase", "material", "assembly", "vocabulary")
    for r in kb["rules"]["rule"]:
        assert r["kind"] in RULE_KINDS, r["id"]
        assert r["severity"] in SEVERITIES, r["id"]
        assert isinstance(r["verified"], bool), r["id"]
        assert r["source"] and r["message_sv"], r["id"]
        assert set(r["applies_to"]) <= targets, (r["id"], set(r["applies_to"]) - targets)
        if r["source"].startswith("BFS"):
            assert r["url"].startswith("https://rinfo.boverket.se/"), r["id"]
            assert r["verified"] and r.get("checked"), r["id"]
        if r["source"] in LAW_SOURCES:
            assert r["url"].startswith("https://data.riksdagen.se/"), r["id"]
            assert r["verified"] and r.get("checked"), r["id"]
        if r["source"] == "praxis":
            # practice values never block: they are asked, not flagged as errors
            assert not r["verified"] and r["severity"] != "fel", r["id"]


def test_process_actions_lead_to_known_permits_and_rules(kb, ids):
    outcomes = ids["permit"] | ids["role"]
    for a in kb["process"]["action"]:
        assert a["default"] in outcomes and a["then"] in outcomes, a["id"]
        assert set(a["rules"]) <= ids["rule"], (a["id"], set(a["rules"]) - ids["rule"])
    orders = [s["order"] for s in kb["process"]["step"]]
    assert orders == sorted(orders) == list(range(1, len(orders) + 1))
    sources = {s["id"] for s in kb["process"]["source"]}
    assert {"pbl", "pbf", "elsl"} <= sources


def test_term_refs_resolve(kb, ids):
    known = _known(ids, *ids.keys())
    for t in kb["terms"]["term"]:
        assert t["ref"] == "" or t["ref"] in known, (t["id"], t["ref"])


def test_symbol_catalogue_covers_every_drawn_symbol(kb, ids):
    import numpy as np

    from rmink.drawing.symbols import SYMBOLS

    catalogue = {s["id"]: s for s in kb["symbols"]["symbol"]}
    assert set(catalogue) == set(SYMBOLS)
    letters = {d["letter"] for d in kb["drawing_standard"]["discipline"]} | {""}
    for kind, (name, paths) in SYMBOLS.items():
        s = catalogue[kind]
        assert s["name"] == name, kind  # the legend says what the catalogue says
        assert s["discipline"] in letters, kind
        assert s["drawing_types"] and set(s["drawing_types"]) <= ids["drawing_type"], kind
        assert set(s["rules"]) <= ids["rule"], (kind, set(s["rules"]) - ids["rule"])
        assert s["meaning"] and s["sketch"] and s["syn"], kind
        # drawn inside the unit box, so size and the legend sample fit
        pts = np.vstack(paths)
        assert np.isfinite(pts).all() and np.abs(pts).max() <= 0.55, kind


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


@pytest.mark.parametrize(
    "query, kind, expected",
    [
        ("gips 13", "material", "gips_a"),
        ("C24", "material", "konstruktionsvirke"),
        ("imp 45x145", "material", "tryckimpregnerat"),
        ("YV1", "assembly", "yv_tra"),
        ("KA", "term", "kontrollansvarig"),
        ("ÖK", "term", "ok"),
        ("bfs9-racke-barn", "rule", "bfs9-racke-barn"),
        ("altan", "action", "altan"),
        ("N-pil", "symbol", "north"),
        ("GB", "symbol", "drain"),
        ("TL", "symbol", "supply_air"),
    ],
)
def test_lookup_finds_handwritten_and_coded_names(query, kind, expected):
    hits = knowledge.lookup(query)
    assert any(h["entry"] == kind and h["id"] == expected for h in hits), [
        (h["entry"], h["id"]) for h in hits
    ]


def test_lookup_expands_rules_and_hatch():
    (gips,) = knowledge.lookup("gips 13", kind="material", limit=1)
    assert gips["hatch"]["id"] == "skiva"
    assert {r["id"] for r in gips["rules"]} >= {"rmink-material-klass"}
    assert all("source" in r for r in gips["rules"])
    assert knowledge.lookup("") == []
    assert knowledge.lookup("xyzzy-inget") == []


def test_reference_is_compact_and_lists_every_material_rule_and_symbol(kb):
    ref = knowledge.reference()
    assert len(ref) < 20_000  # cached in every round; details go through lookup()
    for m in kb["materials"]["material"]:
        assert f"- {m['id']}:" in ref
    for r in kb["rules"]["rule"]:
        assert r["source"] == "rmink" or f"- {r['id']}:" in ref
    for s in kb["symbols"]["symbol"]:
        assert f"- {s['id']} = {s['name']}:" in ref


def test_texts_that_reach_the_drawing_have_glyphs(kb):
    from rmink.drawing.font import _PARSED, _letters

    texts = [r["message_sv"] + r["ref"] for r in kb["rules"]["rule"]]
    texts += [m["example"] for m in kb["materials"]["material"]]
    texts += [s["name"] + s["label"] for s in kb["symbols"]["symbol"]]
    drawn = {ch for t in texts for ch in _letters(t)} - set(" {}[]_")
    assert drawn <= set(_PARSED), sorted(drawn - set(_PARSED))


def test_reference_states_when_permits_come_back():
    # a 2,1 m deck next to the house needs a permit inside a detaljplan
    line = next(x for x in knowledge.reference().splitlines() if x.startswith("- altan:"))
    assert "1,8 m" in line and "3,6 m" in line
