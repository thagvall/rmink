"""Plugins and content packs, tried with the example plugin in examples/."""

import json
import logging
import tomllib
import zipfile
from importlib import metadata
from pathlib import Path

import pytest
from test_rounds import DRAWING
from typer.testing import CliRunner

from rmink import cli, ingest, knowledge, packs, plugins, transport
from rmink.drawing import symbols
from rmink.drawing.export import export, formats
from rmink.drawing.model import Drawing
from rmink.workbook import catalog

EXAMPLE = Path(__file__).parents[1] / "examples" / "rmink-plugin-exempel"
PACK = EXAMPLE / "src" / "rmink_exempel"


def _declared() -> dict[str, list[metadata.EntryPoint]]:
    """The entry points the example's pyproject.toml declares."""
    table = tomllib.loads((EXAMPLE / "pyproject.toml").read_text())["project"]["entry-points"]
    return {
        group: [metadata.EntryPoint(name, value, group) for name, value in entries.items()]
        for group, entries in table.items()
    }


@pytest.fixture
def installed(monkeypatch, tmp_path):
    """The example plugin as if pip had installed it; ``installed[group]`` takes more."""
    eps = _declared()
    monkeypatch.syspath_prepend(str(EXAMPLE / "src"))
    monkeypatch.delenv("RMINK_NO_PLUGINS")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setattr(plugins, "_entry_points", lambda group: tuple(eps.get(group, ())))
    packs.reset()
    yield eps
    packs.reset()


def test_the_example_declares_every_kind_of_part(installed):
    assert set(installed) == set(plugins.GROUPS)
    listing = plugins.listing()
    assert {i.group for i in listing} == set(plugins.GROUPS)
    assert not [i for i in listing if i.error]


def test_a_plugin_that_does_not_load_is_skipped(installed, caplog):
    installed["rmink.transports"].append(
        metadata.EntryPoint("trasig", "finns_inte:open", "rmink.transports")
    )
    with caplog.at_level(logging.WARNING):
        assert plugins.load("rmink.transports", "trasig") is None
    assert "did not load" in caplog.text
    broken = [i for i in plugins.listing() if i.error]
    assert [i.name for i in broken] == ["trasig"] and "ModuleNotFoundError" in broken[0].error
    with pytest.raises(transport.TransportError, match='no transport "trasig"'):
        transport.open("trasig:x")
    assert plugins.load("rmink.transports", "zip") is not None  # the others still work


def test_plugins_can_be_turned_off(installed, monkeypatch):
    monkeypatch.setenv("RMINK_NO_PLUGINS", "1")
    packs.reset()
    assert plugins.found("rmink.transports") == {} and packs.all_packs() == ()
    assert "sauna_heater" not in symbols.symbols()
    assert transport.names() == ["cloud", "folder", "usb"]


def test_built_in_names_stay(installed, tmp_path):
    installed["rmink.transports"].append(
        metadata.EntryPoint("folder", "rmink_exempel:open_zip", "rmink.transports")
    )
    installed["rmink.importers"].append(
        metadata.EntryPoint("pdf", "rmink_exempel:load_geojson", "rmink.importers")
    )
    installed["rmink.exporters"].append(
        metadata.EntryPoint("svg", "rmink_exempel:export_geojson", "rmink.exporters")
    )
    assert isinstance(transport.open(f"folder:{tmp_path}"), transport.FolderTransport)
    assert transport.names() == ["cloud", "folder", "usb", "zip"]
    assert ingest.plugin_suffixes() == {".geojson"}
    assert formats() == ["pdf", "svg", "geojson"]
    assert export(Drawing.model_validate(DRAWING), "svg").startswith(b"<svg")


def test_a_transport_from_a_plugin(installed, tmp_path):
    t = transport.open(f"zip:{tmp_path / 'rmink.zip'}")
    assert isinstance(t, transport.Transport) and repr(t).startswith("zip:")
    doc = tmp_path / "x.rmdoc"
    with zipfile.ZipFile(doc, "w") as zf:
        zf.writestr("a.content", "{}")
    t.mkdir("/rmink")
    assert t.put(doc, folder="/rmink", name="Altan") == "Altan"
    assert t.put(doc, folder="/rmink", name="Altan") == "Altan_2"
    assert [e.name for e in t.ls("/rmink")] == ["Altan", "Altan_2"]
    assert t.get("/rmink/Altan") == doc.read_bytes()
    assert "rmink/Altan.rmdoc" in zipfile.ZipFile(tmp_path / "rmink.zip").namelist()
    with pytest.raises(transport.TransportError, match="Give the zip file"):
        transport.open("zip")


def test_a_pack_adds_knowledge_symbols_and_groups(installed):
    assert [p.name for p in packs.all_packs()] == ["exempel"]
    data = knowledge.load()
    heater = next(s for s in data["symbols"]["symbol"] if s["id"] == "sauna_heater")
    assert heater["pack"] == "exempel"
    assert knowledge.validate(data) == []
    assert any(h["id"] == "sauna_heater" for h in knowledge.lookup("bastuaggregat"))
    assert any(h["id"] == "lave" for h in knowledge.lookup("bastulave", "term"))

    name, paths = symbols.symbols()["sauna_heater"]
    assert name == "Bastuaggregat" and len(paths) == 4
    assert len(symbols.symbol_paths("sauna_heater", (100, 100), 40)) == 4
    assert symbols.symbol_svg("sauna_heater").count("<path") == 4
    assert set(symbols.SYMBOLS) < set(symbols.symbols())  # the built-in ones are all there

    assert catalog.group("kartor").path == "SO/Kartor och skala"
    assert catalog.group("plus-minus").title == "Plus och minus"
    assert packs.check(PACK) == []


def test_the_users_own_files_go_on_top(installed, tmp_path):
    own = tmp_path / "config/rmink/knowledge"
    own.mkdir(parents=True)
    (own / "terms.toml").write_text(
        '[[term]]\nid = "lave"\nterm = "Lave"\nabbr = "LV"\nen = "Bench"\ncat = "inredning"\n'
        'syn = []\nref = ""\ndef = "Vår egen text."\n',
        encoding="utf-8",
    )
    packs.reset()
    assert [p.name for p in packs.all_packs()] == ["exempel", packs.USER]
    laves = [t for t in knowledge.load()["terms"]["term"] if t["id"] == "lave"]
    assert len(laves) == 1 and laves[0]["def"] == "Vår egen text." and laves[0]["pack"] == "egna"
    assert len(knowledge.builtin()["terms"]["term"]) + 1 == len(knowledge.load()["terms"]["term"])


def test_a_faulty_pack_entry_is_left_out_and_reported(installed, tmp_path, caplog):
    pack = tmp_path / "config/rmink/packs/trasigt"
    (pack / "knowledge").mkdir(parents=True)
    (pack / "pack.toml").write_text('name = "trasigt"\n')
    (pack / "knowledge/symbols.toml").write_text(
        '[[symbol]]\nid = "halv"\nname = "Halv"\n\n'
        '[[symbol]]\nid = "utanfor"\nname = "Utanför"\ndiscipline = ""\n'
        'drawing_types = ["planritning"]\nmeaning = "x"\nlabel = ""\nrequired_when = ""\n'
        'sketch = "x"\nsyn = []\nrules = ["finns-inte"]\nifc = ""\nifc_type = ""\nops = ""\n'
        "paths = [[[0, 0], [3, 3]]]\n",
        encoding="utf-8",
    )
    (pack / "knowledge/recept.toml").write_text("x = 1\n")
    packs.reset()
    with caplog.at_level(logging.WARNING):
        ids = {s["id"] for s in knowledge.load()["symbols"]["symbol"]}
    assert "halv" not in ids and "utanfor" not in ids and "sauna_heater" in ids
    assert "missing" in caplog.text

    problems = "\n".join(packs.check(pack))
    assert "symbols.symbol halv: missing" in problems
    assert "unknown rule finns-inte" in problems and "outside the unit box" in problems
    assert "recept.toml: not a file rmink reads" in problems
    assert packs.check(tmp_path) == [f"{tmp_path / 'pack.toml'} is missing"]


def test_an_importer_reads_a_new_file_type(installed, tmp_path):
    square = [[18.0, 59.0], [18.1, 59.0], [18.1, 59.1], [18.0, 59.1], [18.0, 59.0]]
    path = tmp_path / "tomt.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [square]}},
                    {
                        "type": "Feature",
                        "geometry": {"type": "LineString", "coordinates": square[:2]},
                    },
                ],
            }
        )
    )
    (page,) = ingest.load(path, "auto")
    assert isinstance(page, ingest.VectorSource) and len(page.shapes) == 2
    assert page.shapes[0].closed == [True] and page.shapes[0].subpaths[0][0].tolist() == [0, 500]

    out = tmp_path / "tomt.rmdoc"
    result = CliRunner().invoke(cli.app, ["convert", str(path), "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert out.is_file()

    (tmp_path / "tom.geojson").write_text('{"type": "FeatureCollection", "features": []}')
    with pytest.raises(ValueError, match="could not read tom.geojson: no lines"):
        ingest.load(tmp_path / "tom.geojson", "auto")
    with pytest.raises(ValueError, match="Unsupported input type"):
        ingest.load(tmp_path / "x.dwg", "auto")


def test_an_exporter_writes_a_new_format(installed, tmp_path):
    drawing = Drawing.model_validate(DRAWING)
    data = json.loads(export(drawing, "geojson"))
    assert data["name"] == drawing.name and data["features"]
    assert {f["properties"]["id"] for f in data["features"]} <= {e.id for e in drawing.elements}
    with pytest.raises(ValueError, match="Choose one of: pdf, svg, geojson"):
        export(drawing, "dwg")

    source = tmp_path / "altan.json"
    source.write_text(json.dumps(DRAWING))
    out = tmp_path / "altan.geojson"
    result = CliRunner().invoke(cli.app, ["export", str(source), "-f", "geojson", "-o", str(out)])
    assert result.exit_code == 0, result.output
    assert json.loads(out.read_text())["type"] == "FeatureCollection"


def test_a_plugin_adds_a_command_and_an_mcp_tool(installed):
    cli._plugin_commands()
    result = CliRunner().invoke(cli.app, ["exempel"])
    assert result.exit_code == 0 and "rmink-exempel brings" in result.output
    listed = CliRunner().invoke(cli.app, ["plugins"])
    assert listed.exit_code == 0
    assert "transports  zip" in listed.output and "pack        exempel" in listed.output

    pytest.importorskip("mcp")
    from rmink import mcp_server

    assert mcp_server._plugin_tools() == ["exempel"]


def test_checking_a_pack_from_the_command_line(installed, tmp_path):
    ok = CliRunner().invoke(cli.app, ["plugins", "check", str(PACK)])
    assert ok.exit_code == 0 and ok.output.strip().endswith("ok")
    (tmp_path / "pack.toml").write_text('description = "utan namn"\n')
    bad = CliRunner().invoke(cli.app, ["plugins", "check", str(tmp_path)])
    assert bad.exit_code == 1 and "name is missing" in bad.output
