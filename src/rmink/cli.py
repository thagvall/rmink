"""Command line interface: ``rmink convert|preview|inspect|devices|calibrate|mcp``, the
``rmink cloud`` group, and ``rmink sketch|draw`` for turning sketches into clean drawings."""

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


cloud_app = typer.Typer(help="reMarkable Cloud: connect, list, download and upload notebooks.")
app.add_typer(cloud_app, name="cloud")


def _token() -> str:
    from rmink import cloud

    token = cloud.load_token()
    if not token:
        typer.secho(f"Not connected; run: rmink cloud connect CODE ({cloud.CONNECT_URL})",
                    fg="red", err=True)  # fmt: skip
        raise typer.Exit(1)
    return token


@cloud_app.command("connect")
def cloud_connect(
    code: Annotated[str, typer.Argument(help="One-time code from my.remarkable.com")],
) -> None:
    """Connect to your reMarkable Cloud and remember the connection."""
    from rmink import cloud

    typer.echo(f"Connected; token saved in {cloud.save_token(cloud.connect(code))}")


@cloud_app.command("ls")
def cloud_ls(path: Annotated[str, typer.Argument()] = "/") -> None:
    """List documents and folders."""
    from rmink import cloud

    for e in cloud.ls(_token(), path):
        typer.echo(f"{'[d]' if e.folder else '   '} {e.name}")


@cloud_app.command("get")
def cloud_get(
    path: Annotated[str, typer.Argument(help='Document path, e.g. "/Altan"')],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
) -> None:
    """Download a notebook as .rmdoc."""
    from rmink import cloud

    dst = output or Path(f"{path.rstrip('/').rsplit('/', 1)[-1]}.rmdoc")
    dst.write_bytes(cloud.get(_token(), path))
    typer.echo(str(dst))


@cloud_app.command("put")
def cloud_put(path: Annotated[Path, typer.Argument(exists=True)]) -> None:
    """Upload a .rmdoc to the root of your cloud."""
    from rmink import cloud

    typer.echo(f"Sent as {cloud.put(path, _token())!r}")


@app.command()
def sketch(
    document: Annotated[str, typer.Argument(help='Local .rmdoc or cloud path like "/Altan"')],
    page: Annotated[int, typer.Option(help="1-based page")] = 1,
    device: Device = "rm2",
    since: Annotated[str | None, typer.Option(help="Saved drawing: only newer strokes")] = None,
    overlay: Annotated[Path | None, typer.Option(help="Write the numbered groups as PNG")] = None,
) -> None:
    """Read a hand-drawn page as numbered stroke groups with fitted shapes (JSON)."""
    from rmink.devices import get_device
    from rmink.drawing import workflow

    dev = get_device(device)
    since_d = workflow.load_drawing(since) if since else None
    sk = workflow.read_sketch(document, page, dev, since_d)
    if overlay:
        overlay.write_bytes(sk.overlay_png(dev))
    typer.echo(json.dumps(sk.summary(), indent=2))


@app.command()
def draw(
    drawing: Annotated[Path, typer.Argument(exists=True, help="Drawing JSON")],
    output: Annotated[Path | None, typer.Option("--output", "-o")] = None,
    svg: Annotated[Path | None, typer.Option(help="Also write the clean page as SVG")] = None,
    rectify: Annotated[bool, typer.Option("--rectify/--no-rectify")] = True,
    send: Annotated[bool, typer.Option(help="Upload to reMarkable Cloud")] = False,
) -> None:
    """Render a Drawing JSON as a clean revision notebook "<name> r<N>"."""
    from rmink import cloud
    from rmink.devices import get_device
    from rmink.drawing import workflow
    from rmink.drawing.render import page_svg, render_drawing

    d = workflow.drawing_from_json(drawing.read_text(encoding="utf-8"))
    if rectify:
        d = workflow.rectify(d)
    sketch_page = None
    if d.sketch.document:
        doc = workflow.open_document(d.sketch.document, get_device(d.sketch.device))
        if 1 <= d.sketch.page <= len(doc.pages):
            sketch_page = doc.pages[d.sketch.page - 1]
    out = output or drawing.with_name(f"{d.name} r{d.revision}.rmdoc")
    rev = workflow.build_revision(d, out, sketch_page)
    if svg:
        dev = get_device(d.sketch.device)
        svg.write_text(page_svg(render_drawing(rev.drawing, dev), dev), encoding="utf-8")
    for row in workflow.check_dimensions(rev.drawing)["dimensions"]:
        if not row["consistent"]:
            msg = f"{row['id']} {row['text']!r} is drawn {row['deviation_pct']:+}% off scale"
            typer.secho(f"warning: {msg}", fg="yellow", err=True)
    typer.echo(str(rev.path))
    if send:
        typer.echo(f"Sent as {cloud.put(rev.path, _token())!r}")


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
