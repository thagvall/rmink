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
    """Render a Drawing JSON as a clean revision notebook "<name> r<NN>"; --send puts it
    in rmink/<name>/ in your cloud."""
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
    out = output or drawing.with_name(f"{workflow.revision_title(d)}.rmdoc")
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
        typer.echo(f"Sent as {workflow.send_revision(rev, _token())!r}")


@app.command(name="round")
def round_(
    document: Annotated[
        str,
        typer.Argument(
            help='A drawing name ("Altan": its latest revision), a cloud path like '
            '"/rmink/Garage", or a local .rmdoc'
        ),
    ],
    device: Device = "rm2",
    effort: Annotated[str, typer.Option(help="low | medium | high | xhigh | max")] = "medium",
    send: Annotated[bool, typer.Option("--send/--no-send", help="Upload the revision")] = True,
) -> None:
    """Run one revision round with Claude (needs ANTHROPIC_API_KEY and rmink[rounds])."""
    try:
        from rmink.drawing.agent import RoundError, run_round
    except ImportError as e:
        typer.secho("Rounds need: pip install 'rmink[rounds]'", fg="red", err=True)
        raise typer.Exit(1) from e
    from rmink.drawing.store import default_store

    try:
        r = run_round(document, device, default_store(), effort=effort, send=send)
    except RoundError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    where = f"sent as {r.sent_as!r}" if r.sent_as else "not sent"
    cost = r.usage["usd"]
    typer.echo(f"{r.drawing} r{r.revision:02d} ({where}) in {r.seconds:.0f} s, about {cost} USD")
    typer.echo(r.summary)
    for q in r.open_questions:
        typer.echo(f"  ? {q}")


@app.command()
def upgrade(
    name: Annotated[str, typer.Argument(help="A saved drawing, e.g. Garage")],
) -> None:
    """Move a drawing made before 2.13 into rmink/Bygg/ and send it again drawn the
    current way: enlarged to the page, three answer lines per remark."""
    from rmink import cloud
    from rmink.drawing import workflow

    try:
        d = workflow.load_drawing(name)
    except FileNotFoundError as e:
        raise typer.BadParameter(str(e)) from e
    try:
        sent_as = workflow.upgrade(d, _token())
    except cloud.CloudError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"{d.name}: sent as {sent_as!r}")


@app.command("store-push")
def store_push(
    url: Annotated[str, typer.Option(help="The rmink site")] = "https://rmink.vercel.app",
    secret: Annotated[
        str, typer.Option(prompt=True, hide_input=True, envvar="RMINK_ROUNDS_SECRET")
    ] = "",
) -> None:
    """Copy the drawings and workbooks saved on this computer to the site's database,
    so /rounds shows them. The site keeps any newer revision it already has."""
    import httpx

    from rmink.drawing.store import FileStore

    local = FileStore()
    body = {"drawings": local.everything(), "links": local.links()}
    r = httpx.post(
        url.rstrip("/") + "/api/rounds/import",
        json=body,
        headers={"X-Rmink-Secret": secret},
        timeout=120,
    )
    if r.status_code != 200:
        typer.secho(f"error: {r.status_code} {r.text}", fg="red", err=True)
        raise typer.Exit(1)
    added = r.json()["added"]
    typer.echo(f"Added {len(added)}: {', '.join(added) or '-'} ({len(body['links'])} links sent)")


workbook_app = typer.Typer(
    help="Workbooks: a linked PDF with answer boxes; handwritten answers become text."
)
app.add_typer(workbook_app, name="workbook")


def _print_round(r) -> None:
    where = f"sent as {r.sent_as!r}" if r.sent_as else "not sent"
    cost = r.usage.get("usd", 0)
    typer.echo(f"{r.drawing} r{r.revision:02d} ({where}) in {r.seconds:.0f} s, about {cost} USD")
    typer.echo(r.summary)
    for q in r.open_questions:
        typer.echo(f"  ? {q}")


@workbook_app.command("new")
def workbook_new(
    topic: Annotated[
        str, typer.Argument(help='What it is about, e.g. "Bråk för åk 5"; with --group, wishes')
    ] = "",
    name: Annotated[str | None, typer.Option(help="Folder name on the tablet")] = None,
    group: Annotated[
        str | None, typer.Option(help="rmink skola group, e.g. brak-division (see: catalog)")
    ] = None,
    topic_id: Annotated[
        str | None, typer.Option(help="The group's topic, e.g. forlanga-forkorta")
    ] = None,
    grade: Annotated[int | None, typer.Option(min=1, max=9, help="School year, 1-9")] = None,
    mode: Annotated[
        str, typer.Option(help="practice: solutions hidden from the start; test: after grading")
    ] = "practice",
    device: Device = "rm2",
    effort: Annotated[str, typer.Option(help="low | medium | high | xhigh | max")] = "medium",
    send: Annotated[bool, typer.Option("--send/--no-send", help="Upload it")] = True,
) -> None:
    """Have Claude write a workbook and put it in rmink/<name>/, or in
    rmink/Skola/<group>/<name>/ with --group (needs ANTHROPIC_API_KEY)."""
    if mode not in ("practice", "test"):
        raise typer.BadParameter("--mode is practice or test")
    if not group and len(topic.strip()) < 3:
        raise typer.BadParameter("Say what it is about, or pick a --group")
    try:
        from rmink.workbook.agent import RoundError, create_workbook
    except ImportError as e:
        typer.secho("Workbooks need: pip install 'rmink[rounds]'", fg="red", err=True)
        raise typer.Exit(1) from e
    from rmink.drawing.store import default_store

    try:
        r = create_workbook(
            topic,
            device,
            default_store(),
            name=name,
            effort=effort,
            send=send,
            mode=mode,
            group=group,
            topic_id=topic_id,
            grade=grade,
        )
    except RoundError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    _print_round(r)


@workbook_app.command("catalog")
def workbook_catalog() -> None:
    """List the rmink skola groups and topics a workbook can be written for."""
    from rmink.workbook import catalog

    for g in catalog.load():
        typer.echo(f"{g.id}: {g.title} ({g.area})")
        for t in g.topic:
            grades = f"åk {t.grades[0]}-{t.grades[-1]}" if t.grades else ""
            typer.echo(f"  {t.id:28} {t.title}  {grades}")


@workbook_app.command("move")
def workbook_move(
    name: Annotated[str, typer.Argument(help="The workbook, e.g. Bråktest")],
    group: Annotated[
        str, typer.Option(help="rmink skola group, e.g. procent or Matematik/Geometri")
    ],
) -> None:
    """Move a workbook, with its earlier revisions, into rmink/Skola/<group>/."""
    from rmink import cloud
    from rmink.drawing.store import default_store
    from rmink.workbook import catalog, workflow

    store = default_store()
    wb = store.load_workbook(name)
    if wb is None:
        raise typer.BadParameter(f'No saved workbook "{name}"')
    try:
        title = catalog.group_path(group)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    token = cloud.load_token()
    if not token:
        typer.secho("error: rmink is not connected to reMarkable Cloud", fg="red", err=True)
        raise typer.Exit(1)
    try:
        folder = workflow.move_to_group(wb, catalog.AREA, title, token, store)
    except cloud.CloudError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"{wb.name} is in {folder}")


@workbook_app.command("relayout")
def workbook_relayout(
    name: Annotated[str, typer.Argument(help="The workbook, e.g. Bråktest")],
) -> None:
    """Send a workbook again in the current layout (bigger answer boxes) as its next
    revision. Run a round first if you have written in it since the last one."""
    from rmink import cloud
    from rmink.drawing.store import default_store
    from rmink.workbook import workflow
    from rmink.workbook.model import LAYOUT

    store = default_store()
    wb = store.load_workbook(name)
    if wb is None:
        raise typer.BadParameter(f'No saved workbook "{name}"')
    if wb.layout >= LAYOUT:
        typer.echo(f"{wb.name} already has the current layout")
        return
    token = cloud.load_token()
    if not token:
        typer.secho("error: rmink is not connected to reMarkable Cloud", fg="red", err=True)
        raise typer.Exit(1)
    try:
        sent_as = workflow.relayout(wb, token, store)
    except cloud.CloudError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"{wb.name}: sent as {sent_as!r}")


@workbook_app.command("round")
def workbook_round(
    document: Annotated[
        str,
        typer.Argument(
            help='A workbook name ("Bråk": its latest revision), a cloud path or a .rmdoc'
        ),
    ],
    ink: Annotated[
        str, typer.Option(help="remove: drop the handwriting read; keep: hide it in a layer")
    ] = "remove",
    effort: Annotated[str, typer.Option(help="low | medium | high | xhigh | max")] = "medium",
    send: Annotated[bool, typer.Option("--send/--no-send", help="Upload the revision")] = True,
) -> None:
    """Read the handwritten answers and send the next revision with them as text."""
    if ink not in ("remove", "keep"):
        raise typer.BadParameter("--ink is remove or keep")
    try:
        from rmink.workbook.agent import RoundError, run_round
    except ImportError as e:
        typer.secho("Workbooks need: pip install 'rmink[rounds]'", fg="red", err=True)
        raise typer.Exit(1) from e
    from rmink.drawing.store import default_store

    try:
        r = run_round(document, None, default_store(), ink=ink, effort=effort, send=send)
    except RoundError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    _print_round(r)


sheet_app = typer.Typer(
    help="PDF sheets on the tablet: send one, write on it, and pull the ink back onto the PDF."
)
app.add_typer(sheet_app, name="sheet")

SHEET_FOLDER = "rmink/Ark"


@sheet_app.command("send")
def sheet_send(
    source: Annotated[Path, typer.Argument(exists=True, help="PDF sheet")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output .rmdoc")] = None,
    device: Device = "rm2",
    zoom: Annotated[float, typer.Option(help="1 shows the sheet at its printed size")] = 1.0,
    pages: Pages = None,
    orientation: Annotated[
        str, typer.Option(help="auto turns the pages as most sheets lie; or portrait, landscape")
    ] = "auto",
    legend: Annotated[
        str,
        typer.Option(
            help="auto finds the legend or title block in the bottom right corner; "
            "none; or x0,y0,x1,y1 in mm from the sheet's top left"
        ),
    ] = "auto",
    send: Annotated[bool, typer.Option(help=f"Upload to {SHEET_FOLDER}/ in your cloud")] = False,
) -> None:
    """Cut a PDF into tablet pages: an overview, then tiles that know their place on the sheet.

    Pages lie as the sheets do. A legend found is pasted beside every tile, or put on a
    page of its own when it would be too small there."""
    from rmink import cloud
    from rmink.bridge.sheet import layout, parse_legend, write_pack
    from rmink.devices import get_device

    out = output or source.with_suffix(".rmdoc")
    try:
        manifest = write_pack(
            source, out, get_device(device), zoom, pages,
            orientation=orientation, legend=parse_legend(legend),
        )  # fmt: skip
    except ValueError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"{out} ({len(manifest.tiles)} tablet pages, {manifest.orientation})")
    for row in layout(manifest):
        if row["legend"]:
            x0, y0, x1, y1 = row["legend_mm"]
            where = f"legend {x0},{y0},{x1},{y1} mm, {row['legend']}"
        else:
            where = "no legend" + (" found; give one with --legend" if legend == "auto" else "")
        typer.echo(f"  sheet page {row['sheet_page']}: {row['tablet_pages']} pages, {where}")
    if send:
        token = _token()
        cloud.mkdir(token, "/rmink")
        cloud.mkdir(token, f"/{SHEET_FOLDER}")
        name = cloud.put(out, token, folder=f"/{SHEET_FOLDER}", name=manifest.name)
        typer.echo(f"Sent as {f'/{SHEET_FOLDER}/{name}'!r}")


@sheet_app.command("pull")
def sheet_pull(
    notebook: Annotated[str, typer.Argument(help="A .rmdoc, or the notebook's path in your cloud")],
    sheet: Annotated[Path, typer.Argument(exists=True, help="The PDF the notebook was made from")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output PDF")] = None,
) -> None:
    """Add a notebook's ink to the sheet as PDF annotations, each stroke one annotation."""
    from rmink import cloud
    from rmink.bridge.ink_pdf import pull

    local = Path(notebook)
    data = local.read_bytes() if local.is_file() else cloud.get(_token(), notebook)
    out = output or sheet.with_name(f"{sheet.stem} med bläck.pdf")
    try:
        result = pull(data, sheet.read_bytes())
    except ValueError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    out.write_bytes(result.pdf)
    typer.echo(f"{out}: {result.added} strokes added, {result.skipped} already there")
    if result.added_pages:
        msg = f"{result.added_pages} pages added on the tablet have no place on the sheet"
        typer.secho(f"warning: {msg}", fg="yellow", err=True)
    if result.unread:
        msg = f"{result.unread} blocks could not be read; some ink may be missing"
        typer.secho(f"warning: {msg}", fg="yellow", err=True)
    if result.on_legend:
        msg = f"{result.on_legend} strokes on the pasted legend were left out"
        typer.secho(f"warning: {msg}", fg="yellow", err=True)


def _notebook(path: str) -> bytes:
    from rmink import cloud

    local = Path(path)
    return local.read_bytes() if local.is_file() else cloud.get(_token(), path)


@sheet_app.command("points")
def sheet_points(
    notebook: Annotated[str, typer.Argument(help="A .rmdoc, or the notebook's path in your cloud")],
    sheet: Annotated[Path, typer.Argument(exists=True, help="The PDF from rmink sheet pull")],
    output: Annotated[Path, typer.Option("--output", "-o", help="Folder to write to")] = Path(
        "punkter"
    ),
) -> None:
    """Group the ink into numbered points: points.json to fill in, and an image of each."""
    from rmink.bridge.points import find_points, point_image

    points = find_points(_notebook(notebook))
    output.mkdir(parents=True, exist_ok=True)
    data = sheet.read_bytes()
    for p in points.points:
        (output / f"{p.id}.png").write_bytes(point_image(data, p))
    (output / "points.json").write_text(points.model_dump_json(indent=1), encoding="utf-8")
    typer.echo(f"{output / 'points.json'}: {len(points.points)} points")


@sheet_app.command("punch")
def sheet_punch(
    points: Annotated[Path, typer.Argument(exists=True, help="points.json, filled in")],
    sheet: Annotated[Path, typer.Argument(exists=True, help="The PDF from rmink sheet pull")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output PDF")] = None,
) -> None:
    """Add the points to the sheet as numbered comments, and write the list as CSV."""
    from rmink.bridge.points import Points, points_csv, write_points

    data = Points.model_validate_json(points.read_text(encoding="utf-8"))
    out = output or sheet.with_name(f"{sheet.stem} med punkter.pdf")
    try:
        pdf, added, skipped = write_points(sheet.read_bytes(), data)
    except ValueError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    out.write_bytes(pdf)
    table = out.with_suffix(".csv")
    table.write_bytes(points_csv(data).encode("utf-8"))
    typer.echo(f"{out}: {added} points added, {skipped} already there; list in {table}")


@sheet_app.command("status-send")
def sheet_status_send(
    points: Annotated[Path, typer.Argument(exists=True, help="points.json")],
    sheet: Annotated[Path, typer.Argument(exists=True, help="The PDF with the points")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output .rmdoc")] = None,
    people: Annotated[str, typer.Option("--ansvariga", help="Who to cross, e.g. El,VVS,Bygg")] = "",
    device: Device = "rm2",
    send: Annotated[bool, typer.Option(help=f"Upload to {SHEET_FOLDER}/ in your cloud")] = False,
) -> None:
    """A status list for the tablet: a row per point, with boxes to cross."""
    from rmink import cloud
    from rmink.bridge.points import Points
    from rmink.bridge.review import write_status_notebook
    from rmink.devices import get_device

    data = Points.model_validate_json(points.read_text(encoding="utf-8"))
    out = output or points.with_name(f"{data.name} status.rmdoc")
    names = [n.strip() for n in people.split(",") if n.strip()]
    count = write_status_notebook(data, sheet.read_bytes(), out, get_device(device), names)
    typer.echo(f"{out} ({count} tablet pages)")
    if send:
        token = _token()
        cloud.mkdir(token, "/rmink")
        cloud.mkdir(token, f"/{SHEET_FOLDER}")
        name = cloud.put(out, token, folder=f"/{SHEET_FOLDER}", name=out.stem)
        typer.echo(f"Sent as {f'/{SHEET_FOLDER}/{name}'!r}")


@sheet_app.command("status-pull")
def sheet_status_pull(
    notebook: Annotated[str, typer.Argument(help="A .rmdoc, or the notebook's path in your cloud")],
    points: Annotated[Path, typer.Argument(exists=True, help="points.json; it is updated")],
    sheet: Annotated[Path, typer.Argument(exists=True, help="The PDF with the points")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output PDF")] = None,
) -> None:
    """Read the crosses and set status and responsible on the sheet and in the list."""
    from rmink.bridge.points import Points, points_csv, update_points
    from rmink.bridge.review import read_status

    data = Points.model_validate_json(points.read_text(encoding="utf-8"))
    try:
        result = read_status(_notebook(notebook), data)
        pdf, missing = update_points(sheet.read_bytes(), result.points)
    except ValueError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    out = output or sheet.with_name(f"{sheet.stem} status.pdf")
    out.write_bytes(pdf)
    table = out.with_suffix(".csv")
    table.write_bytes(points_csv(result.points).encode("utf-8"))
    points.write_text(result.points.model_dump_json(indent=1), encoding="utf-8")
    for point, change in result.changed.items():
        typer.echo(f"{point}: {change}")
    typer.echo(f"{out}: {len(result.changed)} points changed; list in {table}")
    if result.unclear:
        msg = f"unclear, not changed: {', '.join(result.unclear)}"
        typer.secho(f"warning: {msg}", fg="yellow", err=True)
    if missing:
        msg = f"not on the sheet: {', '.join(missing)}"
        typer.secho(f"warning: {msg}", fg="yellow", err=True)


@sheet_app.command("measure")
def sheet_measure(
    notebook: Annotated[str, typer.Argument(help="A .rmdoc, or the notebook's path in your cloud")],
    sheet: Annotated[Path, typer.Argument(exists=True, help="The sheet, or the PDF from pull")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output PDF")] = None,
    scale: Annotated[
        int | None, typer.Option(help="N in 1:N, for a sheet that does not say its scale")
    ] = None,
) -> None:
    """Lengths and counts: a straight stroke is a length, a small cross or ring one of something."""
    from rmink.bridge.takeoff import find_quantities, quantities_csv, write_quantities

    data = sheet.read_bytes()
    takeoff = find_quantities(_notebook(notebook), data, scale)
    if takeoff.unscaled and not takeoff.quantities:
        typer.secho("error: the sheet has no scale; give one with --scale", fg="red", err=True)
        raise typer.Exit(1)
    out = output or sheet.with_name(f"{sheet.stem} med mängder.pdf")
    pdf, added, skipped = write_quantities(data, takeoff, scale)
    out.write_bytes(pdf)
    table = out.with_suffix(".csv")
    table.write_bytes(quantities_csv(takeoff).encode("utf-8"))
    for kind, group, n, total in takeoff.totals():
        if kind == "length":
            typer.echo(f"{group}: {n} lengths, {total / 1000:.2f} m")
        else:
            typer.echo(f"{group}: {n}")
    typer.echo(f"{out}: {added} added, {skipped} already there; list in {table}")
    typer.echo("Lengths are as drawn by hand, not taken from the drawing.")
    if takeoff.underlines:
        msg = f"{takeoff.underlines} straight strokes beside writing were taken for underlines"
        typer.secho(f"note: {msg}", fg="yellow", err=True)
    if takeoff.unscaled:
        msg = f"{takeoff.unscaled} marks on pages without a scale were left out; use --scale"
        typer.secho(f"warning: {msg}", fg="yellow", err=True)


@sheet_app.command("drawing")
def sheet_drawing(
    drawing: Annotated[Path, typer.Argument(exists=True, help="Drawing JSON")],
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Output PDF")] = None,
    paper: Annotated[str, typer.Option(help="a4 | a3 | a2 | a1")] = "a3",
    scale: Annotated[int | None, typer.Option(help="N in 1:N; by default the largest fit")] = None,
    rectify: Annotated[bool, typer.Option("--rectify/--no-rectify")] = True,
) -> None:
    """Put a clean drawing on a sheet at a true scale, with its categories as PDF layers."""
    from rmink.bridge.drawing_pdf import drawing_pdf
    from rmink.drawing import workflow

    d = workflow.drawing_from_json(drawing.read_text(encoding="utf-8"))
    if rectify:
        d = workflow.rectify(d)
    out = output or drawing.with_suffix(".pdf")
    try:
        sheet = drawing_pdf(d, paper, scale)
    except ValueError as e:
        typer.secho(f"error: {e}", fg="red", err=True)
        raise typer.Exit(1) from e
    out.write_bytes(sheet.pdf)
    typer.echo(f"{out}: 1:{sheet.scale} on {sheet.paper.upper()}")
    for w in sheet.warnings:
        typer.secho(f"warning: {w}", fg="yellow", err=True)


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
