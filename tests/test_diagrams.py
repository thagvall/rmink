"""The draw.io diagrams in docs/diagrams are built from the code and the
knowledge base; this checks that every entry still reaches them."""

import html
import importlib.util
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from rmink import knowledge

DIAGRAMS = Path(__file__).resolve().parents[1] / "docs" / "diagrams"


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    sys.path.insert(0, str(DIAGRAMS))
    try:
        spec = importlib.util.spec_from_file_location("diagram_build", DIAGRAMS / "build.py")
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        out = tmp_path_factory.mktemp("diagrams")
        return build.build(out / "teknik")
    finally:
        sys.path.remove(str(DIAGRAMS))


def _cells(path: Path) -> list[ET.Element]:
    return list(ET.parse(path).getroot().iter("mxCell"))


def test_every_diagram_is_valid_drawio(built):
    assert len(built) == 19
    for path in built:
        cells = _cells(path)
        ids = [c.get("id") for c in cells]
        assert len(ids) == len(set(ids)), path.name
        for c in cells:
            if c.get("edge"):
                assert c.get("source") in ids and c.get("target") in ids, path.name
            if c.get("parent") is not None:
                assert c.get("parent") in ids, path.name


def test_the_knowledge_base_is_all_there(built):
    text = html.unescape(" ".join(c.get("value", "") for p in built for c in _cells(p)))
    kb = knowledge.load()
    expected = (
        [m["name"] for m in kb["materials"]["material"]]
        + [r["id"] for r in kb["rules"]["rule"]]
        + [s["id"] for s in kb["symbols"]["symbol"]]
        + [a["code"] for a in kb["assemblies"]["assembly"]]
        + [v["name"] for v in kb["assemblies"]["variant"]]
        + [h["id"] for h in kb["hatches"]["hatch"]]
        + [t["term"] for t in kb["terms"]["term"]]
        + [a["name"] for a in kb["process"]["action"]]
        + [t["name"] for t in kb["drawing_standard"]["drawing_type"]]
    )
    missing = [x for x in expected if x not in text]
    assert not missing, missing


def test_business_chains_are_valid_drawio(tmp_path):
    sys.path.insert(0, str(DIAGRAMS))
    try:
        import verksamhet

        built = verksamhet.build(tmp_path)
    finally:
        sys.path.remove(str(DIAGRAMS))
    assert len(built) == 6
    for path in built:
        cells = _cells(path)
        ids = [c.get("id") for c in cells]
        assert len(ids) == len(set(ids)), path.name
        for c in cells:
            if c.get("edge"):
                assert c.get("source") in ids and c.get("target") in ids, path.name
