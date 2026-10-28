import json

import anyio
from typer.testing import CliRunner

from rmink.cli import app


def test_cli_convert_inspect_devices(examples, tmp_path):
    runner = CliRunner()
    out = tmp_path / "x.rmdoc"
    png = tmp_path / "x.png"
    r = runner.invoke(
        app, ["convert", str(examples["photo"]), "-o", str(out), "--preview", str(png)]
    )
    assert r.exit_code == 0, r.output
    assert out.exists() and png.exists()

    r = runner.invoke(app, ["inspect", str(out)])
    assert r.exit_code == 0
    info = json.loads(r.output)
    assert info["page_count"] == 1 and info["pages"][0]["strokes"] > 0
    assert "version=6" in info["pages"][0]["header"]

    r = runner.invoke(app, ["devices"])
    assert "rm2" in r.output and "move" in r.output


def test_cli_rejects_unknown_device(examples, tmp_path):
    r = CliRunner().invoke(app, ["convert", str(examples["svg"]), "--device", "kindle"])
    assert r.exit_code == 1


def test_cli_calibrate(tmp_path):
    out = tmp_path / "cal.rmdoc"
    r = CliRunner().invoke(app, ["calibrate", "--device", "pro", "-o", str(out)])
    assert r.exit_code == 0 and out.exists()


def test_mcp_tools(examples, tmp_path):
    from mcp import Client

    from rmink.mcp_server import server

    async def run():
        async with Client(server, raise_exceptions=True) as client:
            tools = {t.name for t in (await client.list_tools()).tools}
            assert {"convert_to_rmdoc", "preview_ink", "inspect_rmdoc", "list_devices"} <= tools

            out = tmp_path / "mcp.rmdoc"
            res = await client.call_tool(
                "convert_to_rmdoc",
                {"inputs": [str(examples["svg"])], "output_path": str(out), "device": "pro"},
            )
            assert not res.is_error, res
            assert out.exists()

            res = await client.call_tool("preview_ink", {"inputs": [str(examples["photo"])]})
            assert not res.is_error
            assert any(c.type == "image" for c in res.content)

            res = await client.call_tool("lookup_knowledge", {"query": "C24"})
            assert not res.is_error and "konstruktionsvirke" in res.content[0].text
            res = await client.call_tool("drawing_reference", {})
            assert "Gipsskiva normal" in res.content[0].text

    anyio.run(run)
