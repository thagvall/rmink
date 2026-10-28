"""Variants of typical assemblies and the alternatives page of a revision."""

import math

import numpy as np
import pytest

from rmink import knowledge
from rmink.calc import evaluate, u_value
from rmink.devices import get_device
from rmink.drawing import workflow
from rmink.drawing.model import Alternatives, Drawing, Option
from rmink.drawing.render import render_alternatives

RM2 = get_device("rm2")
COSTS = {"låg", "medel", "hög"}
U_KINDS = {"", "wall", "roof", "floor", "ground"}


@pytest.fixture(scope="module")
def kb():
    return knowledge.load()


def test_variants_are_built_from_known_assemblies_and_materials(kb):
    assemblies = {a["id"] for a in kb["assemblies"]["assembly"]}
    materials = {m["id"] for m in kb["materials"]["material"]}
    seen = set()
    for v in kb["assemblies"]["variant"]:
        assert v["assembly"] in assemblies, v["id"]
        assert (v["assembly"], v["key"]) not in seen, v["id"]
        seen.add((v["assembly"], v["key"]))
        assert v["cost"] in COSTS and v["u_kind"] in U_KINDS, v["id"]
        assert v["name"] and v["when"] and v["pros"] and v["cons"], v["id"]
        for layer in v["layers"]:
            assert layer["material"] in materials, (v["id"], layer["material"])
            assert 0 < layer.get("fraction", 1.0) <= 1, v["id"]
    # the three assemblies where the choice is most common have alternatives
    for a in ("platta_pa_mark", "yv_tra", "altan_plint"):
        assert len(knowledge.variants(a)) >= 3, a


def test_variant_u_values_are_plausible(kb):
    for v in kb["assemblies"]["variant"]:
        if v["u_kind"]:
            u = u_value(v["layers"], v["u_kind"])
            assert not u["skipped"] and 0.05 < u["U"] < 0.5, (v["id"], u)
    slabs = knowledge.variants("platta_pa_mark")
    pl1 = {v["key"]: knowledge.variant_facts(v)["u_estimate"] for v in slabs}
    assert pl1["B"] < pl1["A"]  # more insulation, lower U


def test_u_value():
    # 200 mm at λ 0,04 between the surface resistances of a wall
    assert u_value([(200, 0.04)], "wall")["U"] == pytest.approx(1 / (0.13 + 5 + 0.04))
    # layers outside a ventilated gap do not count, and the outside acts like the inside
    vent = u_value([(22, "panel_tra"), (28, "luftspalt"), (200, 0.04)], "wall")
    assert vent["U"] == pytest.approx(1 / (0.13 + 5 + 0.13))
    # studs and insulation share a zone: λ is weighted by area
    zone = u_value([(195, 0.13, 0.12), (195, 0.036, 0.88)], "wall")
    lam = 0.12 * 0.13 + 0.88 * 0.036
    assert zone["U"] == pytest.approx(1 / (0.17 + 0.195 / lam))
    assert "markens" in u_value([(300, "cellplast_eps")], "ground")["note"]
    assert evaluate("u_value([(200, 0.04)], 'wall')['U']") == pytest.approx(0.193424, abs=1e-6)


def test_lookup_offers_variants_and_ready_options():
    (pl1,) = knowledge.lookup("PL1", kind="assembly", limit=1)
    assert any(v.startswith("B pl1_b") for v in pl1["variants"])
    (b,) = knowledge.lookup("pl1_b", kind="variant", limit=1)
    opt = Option(**b["option"])  # valid for a drawing as it is
    assert opt.key == "B" and opt.layers[1].thickness_mm == 400
    assert any(f.startswith("U ≈ 0,08") for f in opt.facts)
    assert any("Kostnad: medel" == f for f in opt.facts)
    assert "Variants to compare" in knowledge.reference()


def test_option_texts_have_glyphs(kb):
    from rmink.drawing.font import _PARSED, _letters

    texts = []
    for v in kb["assemblies"]["variant"]:
        o = knowledge.option(v)
        texts += [o["title"], *o["facts"], *o["pros"], *o["cons"]]
        texts += [layer["text"] for layer in o["layers"]]
    drawn = {ch for t in texts for ch in _letters(t)} - {" "}
    assert drawn <= set(_PARSED), sorted(drawn - set(_PARSED))


def _choice(chosen=""):
    opts = [Option(**knowledge.option(v)) for v in knowledge.variants("platta_pa_mark")[:3]]
    return Alternatives(id="alt1", question="Bottenplatta", options=opts, chosen=chosen)


def test_alternatives_page():
    assert render_alternatives(Drawing(name="x"), RM2) is None
    assert render_alternatives(Drawing(name="x", alternatives=[_choice("B")]), RM2) is None
    page = render_alternatives(Drawing(name="Garage", alternatives=[_choice()]), RM2)
    assert page is not None and len(page.strokes) > 300  # three hatched sections and texts
    assert page.height >= RM2.height
    assert all(math.isfinite(float(s.points.sum())) for s in page.strokes)


def test_revision_has_the_alternatives_page(tmp_path):
    from rmink.drawing.store import FileStore
    from rmink.ingest.rm import read_rmdoc
    from rmink.model import Page, Stroke

    sketch = Page(RM2.width, RM2.height, [Stroke(np.linspace((100, 100), (900, 400), 20))])
    store = FileStore(tmp_path / "drawings")
    d = Drawing(name="Garage", alternatives=[_choice()])
    rev = workflow.build_revision(d, tmp_path / "Garage r1.rmdoc", sketch, seed=1, store=store)
    assert len(read_rmdoc(rev.path, RM2).pages) == 3  # drawing, alternatives, sketch
    d.alternatives[0].chosen = "A"
    rev = workflow.build_revision(d, tmp_path / "Garage r2.rmdoc", sketch, seed=1, store=store)
    assert len(read_rmdoc(rev.path, RM2).pages) == 2
