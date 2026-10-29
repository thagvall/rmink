"""MCP server exposing rmink to Claude and other MCP clients.

Run with ``rmink mcp`` (stdio). Register in Claude Code with::

    claude mcp add rmink -- uvx --from 'rmink[mcp]' rmink mcp
"""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

from mcp.server.mcpserver import Image, MCPServer

from rmink import api, calc, cloud, knowledge
from rmink.devices import all_devices, get_device
from rmink.drawing import workflow
from rmink.drawing.model import Drawing
from rmink.drawing.render import page_svg, render_alternatives, render_drawing
from rmink.drawing.symbols import SYMBOLS
from rmink.model import Document
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
        "\n\n"
        "Sketch to clean drawing (the other direction): the user hand-sketches a 2D drawing "
        "on the tablet (lines, written measurements, symbols, a legend) and gets a clean, "
        "interpreted revision back. Loop: `read_sketch` (numbered stroke groups with fitted "
        "lines/circles/polylines, plus an image) -> build a Drawing JSON from the groups, "
        "reusing their fitted coordinates (never estimate coordinates from the image) -> "
        "`render_drawing` to check it and the measurements -> `save_revision` (writes "
        "'<name> r<NN>', optionally sends it to rmink/<name>/ on the tablet). In the next "
        "round the user marks up that revision on the tablet (rings, arrows, crosses, notes, "
        "ideally on the 'Kommentarer' layer, answers on the SVAR line of a remark): "
        "`get_drawing` + `read_sketch` of its sketch.sent_as with since_drawing returns only "
        "the new marks; turn them into annotations or edits, bump `revision`, add a `log` "
        "line and save again. Read `drawing_reference` once for the JSON format, symbols and "
        "categories."
        "\n\n"
        "Workbooks: a linked PDF (table of contents, sections, ruled answer boxes) the user "
        "writes answers in by hand. Write one with `create_workbook` (see its JSON format) "
        "and send it to rmink/<name>/. After the user has written and synced, "
        "`read_workbook` returns a picture of each box with new handwriting; transcribe each "
        "exactly as written (do not correct it) and pass the answers to "
        "`save_workbook_answers`, which sets them as PDF text in the next revision."
    ),
)

# Notebooks read by read_sketch, so save_revision can add the sketch page
# without downloading it again.
_documents: dict[str, Document] = {}


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


@server.tool()
def cloud_connect(code: str) -> str:
    """Connect rmink to the user's reMarkable Cloud with a one-time code from
    https://my.remarkable.com/device/browser/connect, and remember the connection."""
    path = cloud.save_token(cloud.connect(code))
    return f"Connected; the token is stored in {path}"


@server.tool()
def cloud_list(path: str = "/") -> list[dict]:
    """List documents and folders in the user's reMarkable Cloud (needs cloud_connect)."""
    token = cloud.load_token()
    if not token:
        raise cloud.CloudAuthError("Not connected; call cloud_connect with a one-time code")
    return [{"name": e.name, "folder": e.folder} for e in cloud.ls(token, path)]


@server.tool()
def read_sketch(
    document: str, page: int = 1, device: str = "rm2", since_drawing: str | None = None
) -> list:
    """Read a hand-drawn page as numbered stroke groups, with fitted shapes.

    Args:
        document: Local .rmdoc/.rm path, or a document path in the reMarkable Cloud
            such as "/Altan".
        page: 1-based page number.
        device: rm2 | pure | pro | move — the tablet it was drawn on.
        since_drawing: Name of a saved drawing; only strokes added after that revision
            was written are returned (the user's markings on it).

    Returns an image with every group boxed and numbered, and JSON: per group its
    shape (line, polyline, closed, circle, arc, or "mark" for handwriting, arrowheads and
    small symbols that you should read from the image), bounding box, pen colour,
    layer and fitted geometry in page pixels.
    """
    dev = get_device(device)
    since = workflow.load_drawing(since_drawing) if since_drawing else None
    sketch = workflow.read_sketch(document, page, dev, since)
    _documents[document] = sketch.document
    return [
        Image(data=sketch.overlay_png(dev), format="png"),
        json.dumps(sketch.summary()),
    ]


@server.tool()
def drawing_reference() -> str:
    """The Drawing JSON format, built-in symbols and line categories, plus a summary
    of Swedish building knowledge (terms, materials, assemblies, rules)."""
    return json.dumps(
        {
            "schema": Drawing.model_json_schema(),
            "symbols": {k: v[0] for k, v in SYMBOLS.items()},
            "categories": [c.model_dump() for c in Drawing(name="x").categories],
            "notes": [
                "Coordinates are page pixels of the sketch (origin top-left).",
                "Set sketch.document/page/device to where the sketch came from.",
                "sketch.sent_as is set by save_revision(send=True): the notebook to read "
                "next round. Leave it as it is.",
                "Dimension text is shown as written; value is the number in unit.",
                "Legend entries use a symbol kind or 'category:<name>' as key; "
                "left empty, a legend is made from the symbols and categories used.",
                "Annotations with status 'open' are drawn as numbered rings and listed "
                "under ANMÄRKNINGAR, each with a SVAR line for the user's answer; "
                "accepted/rejected ones are hidden.",
                "Use 'knowledge' to read Swedish terms and write materials the way a builder "
                "would; ask in an open annotation when a required class is missing. "
                "lookup_knowledge gives exact rule values and sources.",
                "Angles: an AngleDimension in `angles` is drawn as an arc between its legs "
                "with the degrees; empty text shows the drawn angle. Never work out angles, "
                "lengths, areas, weights or quantities by hand: use measure_drawing and "
                "calculate.",
                "Alternatives: for 'which one / how thick?', put 2-4 options in "
                "`alternatives` (lookup_knowledge on an assembly lists its variants; a "
                "variant hit has a ready 'option'; letter them A, B, C … in order), add an "
                "open annotation asking for the "
                "key, and they are drawn on a page after the drawing. When the user picks "
                "one, set `chosen` and draw that option's layers.",
            ],
            "knowledge": knowledge.reference(),
        },
        ensure_ascii=False,
    )


@server.tool()
def lookup_knowledge(query: str, kind: str | None = None) -> str:
    """Look up Swedish building knowledge for a drawing.

    Args:
        query: A term, abbreviation or handwritten variant ("gips 13", "imp", "ÖK"),
            a material, an assembly code ("YV1"), a rule id or a permit question ("altan").
        kind: Optionally one of material, assembly, rule, action, term, drawing_type,
            role, hatch.

    Returns JSON entries, best match first, with classes, layers, exact values and the
    legal source of each rule (BFS, PBL/PBF, ElSL) or "praxis" when it is practice only.
    """
    return json.dumps(knowledge.lookup(query, kind) or "No match.", ensure_ascii=False)


@server.tool()
def calculate(expression: str) -> str:
    """Evaluate one arithmetic expression exactly, instead of working it out by hand.

    Args:
        expression: Python-like arithmetic. Trigonometry is in degrees (sin, cos, tan,
            asin, acos, atan, atan2); also sqrt, hypot, round, floor, ceil, min, max,
            sum, len; leg(c, a); triangle(a, b, c) -> angles A, B, C and area;
            slope(rise, run) and pitch(deg) -> degrees, 1:x and percent;
            area([(x, y), ...]); circle(d); cylinder(d, h); weight(volume_m3, material)
            in kg from the knowledge base's density; count(length, cc) pieces at c/c
            spacing, both ends included; pieces(total, length); waste(quantity, percent);
            sets with |, &, -, ^ and in.

    Returns the value as JSON, or the reason it could not be evaluated.
    """
    try:
        return json.dumps(calc.evaluate(expression), ensure_ascii=False)
    except calc.CalcError as e:
        return f"Error: {e}"


@server.tool()
def measure_drawing(drawing: dict, ids: list[str]) -> str:
    """Lengths, areas and angles read from a Drawing's geometry.

    Args:
        drawing: Drawing JSON (see drawing_reference).
        ids: One element or dimension id for its length (plus area and corner angles
            when it is closed, or corner angles along a polyline); two line ids for the
            angle between them.

    Returns JSON. Lengths and areas are in the unit of the written dimensions when they
    give a scale, else in page pixels. Put the corner angles on the drawing as `angles`
    (AngleDimension) when the user asks to see them.
    """
    return json.dumps(workflow.measure(workflow.drawing_from_json(drawing), ids))


@server.tool()
def render_drawing_preview(drawing: dict, rectify: bool = True) -> list:
    """Render a Drawing as it will look on the tablet, and check the measurements.

    Args:
        drawing: Drawing JSON (see drawing_reference).
        rectify: Square lines within 12° of horizontal/vertical (walls in a hand sketch
            meet at 90°; a line with an angle dimension at an end keeps its angle unless
            within 4°), join endpoints that almost meet and close overshooting corners.

    Returns the preview image and JSON with the (rectified) drawing and a measurement
    check: the common scale and dimensions whose drawn length disagrees with it by more
    than 10 % (worth asking the user about).
    """
    d = workflow.drawing_from_json(drawing)
    if rectify:
        d = workflow.rectify(d)
    dev = get_device(d.sketch.device)
    page = render_drawing(d, dev)
    from rmink.render.preview import render_lines
    from rmink.writer.rm_v6 import page_lines

    images = []
    for p in [page, render_alternatives(d, dev)]:
        if p is None:
            continue
        img = render_lines(page_lines(p, dev), dev, p.height)
        img.thumbnail((1200, 1200))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        images.append(Image(data=buf.getvalue(), format="png"))
    report = {"measurements": workflow.check_dimensions(d), "drawing": d.model_dump(mode="json")}
    return [*images, json.dumps(report)]


@server.tool()
def save_revision(
    drawing: dict,
    output_path: str | None = None,
    rectify: bool = True,
    include_sketch: bool = True,
    send: bool = False,
    svg_path: str | None = None,
) -> dict:
    """Write the clean drawing as the notebook "<name> r<NN>" and save the drawing
    for the next round.

    Args:
        drawing: Drawing JSON (see drawing_reference).
        output_path: Where to write the .rmdoc (default: ~/.config/rmink/drawings/).
        rectify: As in render_drawing_preview.
        include_sketch: Add the sketch page (sketch.document/page) after the clean page.
        send: Upload the notebook to rmink/<name>/ in the user's reMarkable Cloud (needs
            cloud_connect). The notebook the round read moves to rmink/<name>/Tidigare/ when
            it lies in rmink/. A sketch the user put in a folder rmink/<folder>/ belongs to
            that folder: name the drawing after the folder.
        svg_path: Also write the clean page as SVG, for sharing.
    """
    d = workflow.drawing_from_json(drawing)
    if rectify:
        d = workflow.rectify(d)
    dev = get_device(d.sketch.device)
    sketch_page = None
    if include_sketch and d.sketch.document:
        doc = _documents.get(d.sketch.document) or workflow.open_document(d.sketch.document, dev)
        if 1 <= d.sketch.page <= len(doc.pages):
            sketch_page = doc.pages[d.sketch.page - 1]
    name = workflow.revision_title(d)
    output = Path(output_path) if output_path else workflow.drawings_dir() / f"{name}.rmdoc"
    rev = workflow.build_revision(d, output, sketch_page)
    result = {"path": str(rev.path), "saved_drawing": str(rev.saved_to), "name": name}
    if svg_path:
        Path(svg_path).write_text(page_svg(render_drawing(rev.drawing, dev), dev))
        result["svg"] = svg_path
    if send:
        token = cloud.load_token()
        if not token:
            raise cloud.CloudAuthError("Not connected; call cloud_connect with a one-time code")
        result["sent_as"] = workflow.send_revision(rev, token)
    return result


@server.tool()
def get_drawing(name: str) -> dict:
    """The saved Drawing JSON of the latest revision of ``name``."""
    return workflow.load_drawing(name).model_dump(mode="json")


def _workbook_result(r, output: Path | None) -> dict:
    out = {"workbook": r.drawing, "revision": r.revision, "summary": r.summary}
    if r.sent_as:
        out["sent_as"] = r.sent_as
    if output:
        out["path"] = str(output.with_suffix(".rmdoc"))
    if r.open_questions:
        out["unsure"] = r.open_questions
    return out


def _workbook_output(output_path: str | None, send: bool, name: str) -> Path | None:
    if output_path:
        return Path(output_path)
    return None if send else workflow.drawings_dir() / "workbooks" / f"{name}.rmdoc"


@server.tool()
def create_workbook(
    workbook: dict, device: str = "rm2", send: bool = False, output_path: str | None = None
) -> dict:
    """Lay out a new workbook as a linked PDF in the tablet's page format: a cover with
    the table of contents, each section on its own pages with links back and on, and a
    ruled box per field. Saved for later rounds; ``send`` puts it in rmink/<name>/.

    Args:
        workbook: {"name": short folder name, "title", "intro", "sections": [{"id",
            "title", "text": a short explanation (plain text, about 120 words at most),
            "fields": [{"id": unique, "prompt": the question, "lines": ruled lines for
            the answer, 1-12}]}]}. Use Latin-1 characters only (3/4, x^2, sqrt(2)).
        device: rm2 | pure | pro | move.
        send: Upload to the user's reMarkable Cloud (needs cloud_connect).
        output_path: Where to write the .rmdoc (default when not sending:
            ~/.config/rmink/drawings/workbooks/).
    """
    from rmink.drawing.store import default_store
    from rmink.workbook.agent import check_workbook, start_workbook

    wb = check_workbook(workbook)
    output = _workbook_output(output_path, send, wb.name)
    return _workbook_result(
        start_workbook(wb, device, default_store(), send, output=output), output
    )


@server.tool()
def read_workbook(document: str) -> list:
    """The answer boxes the user wrote in since the last revision of a workbook: for each,
    its id, question and earlier answer, and a picture of the box with the new ink.

    Args:
        document: A workbook name (its latest revision), a cloud path or a local .rmdoc.
    """
    from rmink.drawing.store import default_store
    from rmink.workbook.agent import open_round

    r = open_round(document, None, default_store())
    out: list = []
    for _, text, png in r.boxes():
        out += [text, Image(data=png, format="png")]
    return out


@server.tool()
def save_workbook_answers(
    document: str,
    answers: list[dict],
    ink: str = "remove",
    send: bool = False,
    output_path: str | None = None,
) -> dict:
    """Set the transcribed answers as text in the workbook and write the next revision.

    Args:
        document: As given to read_workbook.
        answers: [{"id": box id, "text": exactly what was written, "confident": false
            when any part is a guess}], one per box read_workbook returned; an empty text
            leaves the box's ink as it is. A tick alone in an answered box confirms the
            earlier answer: give it unchanged with confident true.
        ink: "remove" drops the handwriting that was read; "keep" moves it to a hidden
            layer "Handskrift" the user can show again.
        send: Upload to the workbook's folder; the revision read moves to Tidigare.
        output_path: Where to write the .rmdoc when not sending.
    """
    from rmink.drawing.store import default_store
    from rmink.workbook.agent import finish_round, open_round

    if ink not in ("remove", "keep"):
        raise ValueError('ink is "remove" or "keep"')
    store = default_store()
    r = open_round(document, None, store)
    checked = r.check({"answers": answers})
    output = _workbook_output(output_path, send, r.workbook.name)
    result = finish_round(r, checked, store, ink, send, output=output)
    return _workbook_result(result, output)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
