"""Command line interface: ``rmink convert|preview|inspect|devices|calibrate|mcp``."""

from __future__ import annotations

import json
import logging
import zipfile
from pathlib import Path
from typing import Annotated

import typer

from rmink import api
from rmink.devices import all_devices
from rmink.geometry.transform import Fit
from rmink.options import ConvertOptions, FillMode, Mode, PenChoice, Shading
from rmink.support import support_url

app = typer.Typer(
    help="Convert images, photos, SVGs and PDFs into native, editable reMarkable ink.",
    no_args_is_help=True,
    add_completion=False,
)

Inputs = Annotated[list[Path], typer.Argument(help="PDF, SVG or image files", exists=True)]
Device = Annotated[str, typer.Option("--device", "-d", help="rm2 | pure | pro | move")]
ModeOpt = Annotated[Mode, typer.Option(help="How ink is extracted")]
Colors = Annotated[str, typer.Option(help="auto | mono | number of colour clusters")]
PenOpt = Annotated[PenChoice, typer.Option(help="Tablet pen used for the strokes")]
Width = Annotated[float, typer.Option(help="Outline/hatch pen width in device px")]
FillOpt = Annotated[FillMode, typer.Option(help="How filled areas are drawn")]
ShadingOpt = Annotated[Shading, typer.Option(help="Grey tones for photos and images")]
Density = Annotated[float, typer.Option(help="Shading density (1 = normal)")]
Contrast = Annotated[float, typer.Option(help="Shading contrast (1 = normal)")]
FitOpt = Annotated[Fit, typer.Option(help="page: fit page | width: fit width | none: true size")]
Margin = Annotated[float, typer.Option(help="Page margin in mm")]
Threshold = Annotated[str, typer.Option(help="auto or a 0-255 ink threshold for rasters")]
Simplify = Annotated[float, typer.Option(help="Simplification tolerance in device px")]
ThickPx = Annotated[float, typer.Option(help="Raster ink wider than this is outlined")]
MaxPoints = Annotated[int, typer.Option(help="Point budget per page")]
Pages = Annotated[str | None, typer.Option(help="PDF pages, e.g. 1-3,7")]
Seed = Annotated[int | None, typer.Option(help="Deterministic UUIDs (for tests)")]
Verbose = Annotated[bool, typer.Option("--verbose", "-v")]


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING, format="%(levelname)s %(message)s"
    )


def _options(**kw) -> ConvertOptions:
    return ConvertOptions(**{k: v for k, v in kw.items() if v is not None})


@app.command()
def convert(
    inputs: Inputs,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output .rmdoc")] = None,
    name: Annotated[str | None, typer.Option(help="Notebook name on the tablet")] = None,
    device: Device = "rm2",
    mode: ModeOpt = Mode.auto,
    colors: Colors = "auto",
    pen: PenOpt = PenChoice.fineliner,
    width: Width = 2.0,
    fill: FillOpt = FillMode.hatch,
    shading: ShadingOpt = Shading.none,
    shade_density: Density = 1.0,
    shade_contrast: Contrast = 1.0,
    fit: FitOpt = Fit.page,
    margin: Margin = 5.0,
    threshold: Threshold = "auto",
    simplify: Simplify = 0.6,
    thick_px: ThickPx = 9.0,
    max_points: MaxPoints = 150_000,
    pages: Pages = None,
    preview: Annotated[Path | None, typer.Option(help="Also write a PNG preview")] = None,
    compress: Annotated[bool, typer.Option(help="Deflate the archive")] = False,
    seed: Seed = None,
    verbose: Verbose = False,
) -> None:
    """Convert inputs into one .rmdoc notebook (one page per image / PDF page)."""
    _setup_logging(verbose)
    opts = _options(
        device=device, mode=mode, colors=colors, pen=pen, width=width, fill=fill, shading=shading,
        shade_density=shade_density, shade_contrast=shade_contrast, fit=fit, margin_mm=margin,
        threshold=threshold, simplify=simplify, thick_px=thick_px,
        max_points=max_points, pages=pages, name=name, compress=compress, seed=seed,
    )  # fmt: skip
    try:
        result = api.convert(inputs, output, opts, preview=preview)
    except (ValueError, FileNotFoundError, RuntimeError) as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    for w in result.warnings:
        typer.secho(f"warning: {w}", fg="yellow", err=True)
    total = sum(p.strokes for p in result.pages)
    typer.echo(
        f"{result.path}  ({len(result.pages)} pages, {total} strokes, "
        f"{result.size_bytes / 1000:.0f} kB, {result.device})"
    )
    if result.preview_path:
        typer.echo(f"preview: {result.preview_path}")


@app.command()
def preview(
    inputs: Inputs,
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("preview.png"),
    device: Device = "rm2",
    mode: ModeOpt = Mode.auto,
    colors: Colors = "auto",
    pen: PenOpt = PenChoice.fineliner,
    width: Width = 2.0,
    fill: FillOpt = FillMode.hatch,
    shading: ShadingOpt = Shading.none,
    shade_density: Density = 1.0,
    shade_contrast: Contrast = 1.0,
    fit: FitOpt = Fit.page,
    threshold: Threshold = "auto",
    simplify: Simplify = 0.6,
    pages: Pages = None,
    verbose: Verbose = False,
) -> None:
    """Render what the converted ink will look like, without writing a notebook."""
    _setup_logging(verbose)
    opts = _options(
        device=device, mode=mode, colors=colors, pen=pen, width=width, fill=fill,
        shading=shading, shade_density=shade_density, shade_contrast=shade_contrast, fit=fit,
        threshold=threshold, simplify=simplify, pages=pages,
    )  # fmt: skip
    rendered = api.render(inputs, opts)
    api.save_preview(rendered.images, output)
    for w in rendered.warnings:
        typer.secho(f"warning: {w}", fg="yellow", err=True)
    typer.echo(str(output))


@app.command()
def inspect(path: Annotated[Path, typer.Argument(exists=True)]) -> None:
    """Show pages, strokes, pens and colours of a .rmdoc or .rm file."""
    typer.echo(json.dumps(api.inspect(path), indent=2))


@app.command()
def repair(
    path: Annotated[Path, typer.Argument(exists=True, help="Broken .rmdoc / .zip")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Fix a notebook that was unpacked and re-zipped (e.g. by Safari or Finder on a Mac)."""
    from rmink.package.rmdoc import repair_rmdoc

    stem = path.name.removesuffix(".zip").removesuffix(".rmdoc")
    dst = output or path.with_name(f"{stem}.rmdoc")
    if dst.resolve() == path.resolve():
        dst = path.with_name(f"{stem}-repaired.rmdoc")
    try:
        repair_rmdoc(path, dst)
    except (ValueError, zipfile.BadZipFile) as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    typer.echo(str(dst))


@app.command()
def devices() -> None:
    """List device profiles."""
    for d in all_devices().values():
        status = "verified" if d.verified else "beta"
        colour = "colour" if d.color else "mono"
        typer.echo(f"{d.key:6} {d.name:28} {d.width}x{d.height} {d.dpi:g} dpi {colour:6} {status}")


@app.command()
def calibrate(
    device: Device = "rm2",
    output: Annotated[Path, typer.Option("--output", "-o")] = Path("rmink-calibration.rmdoc"),
) -> None:
    """Write a ruler page; measure it on the tablet to verify the scale."""
    path = api.calibration_sheet(device, output)
    typer.echo(
        f"{path}\nOpen it on the tablet: the long ticks are 10 mm apart and the square is "
        "50 mm. If they are off, set ink_scale for this device in "
        "~/.config/rmink/devices.toml."
    )


@app.command()
def web(
    host: Annotated[str, typer.Option(help="Interface to bind")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port")] = 8765,
    open_browser: Annotated[bool, typer.Option("--open/--no-open")] = True,
) -> None:
    """Start the web UI: drop files, preview the ink, download the notebook."""
    try:
        import uvicorn

        from rmink.web import create_app
    except ImportError as e:
        typer.secho("The web UI needs: pip install 'rmink[web]'", fg="red", err=True)
        raise typer.Exit(1) from e
    url = f"http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}"
    typer.echo(f"rmink web UI on {url}  (Ctrl+C to stop)")
    if support := support_url():
        typer.echo(f"rmink is free. If it is useful to you, you can support it: {support}")
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")


@app.command()
def mcp() -> None:
    """Run the MCP server on stdio (for Claude and other MCP clients)."""
    try:
        from rmink.mcp_server import main
    except ImportError as e:
        typer.secho("The MCP server needs: pip install 'rmink[mcp]'", fg="red", err=True)
        raise typer.Exit(1) from e
    main()


if __name__ == "__main__":
    app()
