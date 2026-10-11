"""MCP server exposing rmink to Claude and other MCP clients.

Run with ``rmink mcp`` (stdio). Register in Claude Code with::

    claude mcp add rmink -- uvx --from 'rmink[mcp]' rmink mcp
"""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from rmink import api
from rmink.devices import all_devices
from rmink.options import ConvertOptions

server = MCPServer(
    "rmink",
    instructions=(
        "Convert images, photos of handwriting, SVGs and PDFs into native, editable "
        "reMarkable ink (.rmdoc). Typical loop: call `preview_ink` to see the result, "
        "adjust options (mode, threshold, simplify, colors, pen, width, shading), then "
        "`convert_to_rmdoc`. For photos and portraits, `shading` turns grey tones into "
        "dots, halftone, hatching or pencil strokes; compare styles with `preview_ink`. "
        "Modes: 'auto' (default), 'vector' for PDFs/SVGs, 'centerline' for handwriting and "
        "sketches, 'outline' for logos and solid shapes. The .rmdoc is transferred by the "
        "user via the reMarkable USB web interface (http://10.11.99.1) or the desktop app."
    ),
)


def _opts(
    device: str,
    mode: str,
    colors: str,
    fill: str,
    fit: str,
    threshold: str,
    simplify: float,
    pages: str | None,
    pen: str,
    width: float,
    shading: str,
    shade_density: float,
    name: str | None = None,
) -> ConvertOptions:
    return ConvertOptions(
        device=device, mode=mode, colors=colors, fill=fill, fit=fit,
        threshold=threshold, simplify=simplify, pages=pages, pen=pen, width=width,
        shading=shading, shade_density=shade_density, name=name,
    )  # fmt: skip


@server.tool()
def convert_to_rmdoc(
    inputs: list[str],
    output_path: str | None = None,
    device: str = "rm2",
    mode: str = "auto",
    colors: str = "auto",
    fill: str = "hatch",
    fit: str = "page",
    threshold: str = "auto",
    simplify: float = 0.6,
    pages: str | None = None,
    name: str | None = None,
    pen: str = "fineliner",
    width: float = 2.0,
    shading: str = "none",
    shade_density: float = 1.0,
) -> dict:
    """Convert files (PDF, SVG, PNG/JPG photos) into one editable reMarkable notebook.

    Args:
        inputs: Absolute paths of input files; each image / PDF page becomes a page.
        output_path: Where to write the .rmdoc (default: next to the first input).
        device: rm2 | pure | pro | move. Colour is only kept on pro and move.
        mode: auto | vector | centerline | outline.
        colors: auto | mono | number of colour clusters for raster inputs.
        fill: hatch | outline | none — how filled areas are drawn.
        fit: page | width | none (true size).
        threshold: auto or 0-255 ink threshold for raster inputs.
        simplify: Simplification tolerance in device pixels (higher = fewer points).
        pages: PDF page ranges like "1-3,7".
        name: Notebook name shown on the tablet.
        pen: fineliner | ballpoint | marker | pencil — the tablet pen for the strokes.
        width: Pen width for outlines, hatching and shading, in device pixels.
        shading: none | stipple | halftone | hatch | crosshatch | pencil — grey tones
            of photos as dots, a dot screen, lines, crossed lines or pencil pressure.
        shade_density: Shading density, 1 = normal (higher = more dots/lines).
    """
    opts = _opts(
        device, mode, colors, fill, fit, threshold, simplify, pages,
        pen, width, shading, shade_density, name,
    )  # fmt: skip
    result = api.convert([Path(p) for p in inputs], output_path and Path(output_path), opts)
    return result.model_dump(mode="json")


@server.tool()
def preview_ink(
    inputs: list[str],
    device: str = "rm2",
    mode: str = "auto",
    colors: str = "auto",
    fill: str = "hatch",
    fit: str = "page",
    threshold: str = "auto",
    simplify: float = 0.6,
    pages: str | None = None,
    pen: str = "fineliner",
    width: float = 2.0,
    shading: str = "none",
    shade_density: float = 1.0,
) -> Image:
    """Render how the converted strokes will look on the tablet (PNG), without writing
    a notebook. Use this to tune options before calling convert_to_rmdoc. Takes the
    same options as convert_to_rmdoc (pen, width, shading, shade_density included)."""
    opts = _opts(
        device, mode, colors, fill, fit, threshold, simplify, pages,
        pen, width, shading, shade_density,
    )  # fmt: skip
    rendered = api.render([Path(p) for p in inputs], opts)
    with tempfile.TemporaryDirectory() as tmp:
        path = api.save_preview(rendered.images, Path(tmp) / "preview.png")
        from PIL import Image as PILImage

        img = PILImage.open(path)
        # Keep the image small enough for a model context.
        img.thumbnail((1200, 1200))
        buf = io.BytesIO()
        img.save(buf, "PNG")
    return Image(data=buf.getvalue(), format="png")


@server.tool()
def inspect_rmdoc(path: str) -> dict:
    """Summarise a .rmdoc or .rm file: pages, stroke and point counts, pens, colours."""
    return api.inspect(Path(path))


@server.tool()
def list_devices() -> list[dict]:
    """List supported reMarkable device profiles."""
    return [
        {
            "key": d.key,
            "name": d.name,
            "width": d.width,
            "height": d.height,
            "dpi": d.dpi,
            "color": d.color,
            "verified": d.verified,
        }
        for d in all_devices().values()
    ]


@server.tool()
def calibration_sheet(device: str, output_path: str) -> str:
    """Write a ruler/calibration notebook for checking the scale on a real device."""
    return str(api.calibration_sheet(device, Path(output_path)))


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
