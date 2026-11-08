"""Cut a PDF sheet into tablet pages, keeping exact track of where each came from.

The tablet shows a PDF page scaled to fit, so rmink builds its own PDF with
pages of exactly the tablet's size, and a tablet point then maps to a sheet
point by a matrix recorded per page. A sheet gets an overview page whose numbers
open its tiles, then the tiles, each with a button back. At zoom 1 a tile shows
the sheet at its printed size. Tiles overlap a little, so a note on a seam fits
on one. The tablet draws a dot where a link is tapped, so the buttons are
recorded for :mod:`rmink.bridge.ink_pdf` to leave those dots out.

Sheet coordinates are as the page is displayed: points from the top left corner
of the visible page, after /Rotate, /CropBox and /UserUnit. PyMuPDF's clip and
annotation calls work in the unrotated page instead, hence :func:`unrotate`.
"""

from __future__ import annotations

import functools
import hashlib
import json
import math
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

import pymupdf
from pydantic import BaseModel

from rmink.devices import DeviceProfile
from rmink.ingest import parse_page_ranges
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc

FORMAT = "rmink/sheet"
MANIFEST = "rmink.manifest.json"
PLACEMENT = "rmink.placement.json"  # from rmink sheet drawing: where its parts lie
OVERLAP = 0.05  # share of a tile shown again on its neighbour
MAX_PAGES = 200
NUMBER_BUTTON = (30, 22)  # pt, big enough to hit with the pen
BACK_BUTTON = (58, 20)
LEGEND_BUTTON = (74, 20)
BUTTON = (0.25, 0.25, 0.25)
MM = 72 / 25.4
LEGEND_SHARE = 0.3  # most of a tile's width or height the pasted legend may take
LEGEND_TEXT = 1.8  # mm: smaller legend text on the tablet gets a page of its own
LEGEND_PAD = 4.0  # pt
ORIENTATIONS = ("auto", "portrait", "landscape")
LEGEND_GOAL = 2.2  # mm: legend text on the tablet need not be larger than this
SHRINK = (1.0, 0.975, 0.95, 0.925, 0.9)  # a tile may show the sheet this much smaller to save pages
MARGIN = 3 * MM  # kept round what is drawn on the sheet

Matrix = tuple[float, float, float, float, float, float]
Box = tuple[float, float, float, float]


class Tile(BaseModel):
    tablet_page: int  # 0-based page of the notebook
    sheet_page: int  # 0-based page of the sheet
    kind: str  # "overview", "legend" or "tile"
    matrix: Matrix  # (a, b, c, d, e, f): tablet pt -> displayed sheet pt
    links: list[Box] = []  # buttons on the page, tablet pt
    blocked: list[Box] = []  # tablet pt where ink is not on the sheet: the pasted legend

    def to_sheet(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.matrix
        return a * x + c * y + e, b * x + d * y + f

    def to_tablet(self, x: float, y: float) -> tuple[float, float]:
        a, b, c, d, e, f = self.matrix
        det = a * d - b * c
        x, y = x - e, y - f
        return (d * x - c * y) / det, (a * y - b * x) / det


class Source(BaseModel):
    name: str
    sha256: str
    pages: int


class Manifest(BaseModel):
    format: str = FORMAT
    version: int = 1
    rmink: str
    device: str
    name: str
    session: str  # one per notebook; ids of its strokes start with it
    orientation: str = "portrait"  # of the tablet pages
    source: Source
    tiles: list[Tile]
    legends: dict[int, Box] = {}  # sheet page -> the legend found on it, sheet pt

    def tile(self, tablet_page: int) -> Tile | None:
        return next((t for t in self.tiles if t.tablet_page == tablet_page), None)


@dataclass
class Pack:
    pdf: bytes
    manifest: Manifest


def unrotate(page: pymupdf.Page) -> pymupdf.Matrix:
    """Displayed page points -> unrotated page points. PyMuPDF's own
    ``derotation_matrix`` is off on a page with a /UserUnit."""
    w, h = page.rect.width, page.rect.height
    if page.rotation == 90:
        return pymupdf.Matrix(0, -1, 1, 0, 0, w)
    if page.rotation == 180:
        return pymupdf.Matrix(-1, 0, 0, -1, w, h)
    if page.rotation == 270:
        return pymupdf.Matrix(0, 1, -1, 0, h, 0)
    return pymupdf.Matrix(1, 0, 0, 1, 0, 0)


def _spans(
    length: float, tile: float, start: float = 0.0, side: float | None = None
) -> list[float]:
    """Start of each tile along ``length`` from ``start``, evenly spaced so that the
    last one does not end up almost on top of the one before. A lone tile is
    centred on it, kept within ``side``."""
    if length <= tile:
        middle = start + (length - tile) / 2
        return [max(0.0, min(middle, (side or length) - tile))]
    count = math.ceil((length - tile) / (tile * (1 - OVERLAP))) + 1
    return [start + i * (length - tile) / (count - 1) for i in range(count)]


def tile_rects(
    width: float,
    height: float,
    tablet: pymupdf.Rect,
    zoom: float,
    drawn: pymupdf.Rect | None = None,
) -> list[pymupdf.Rect]:
    """The regions of a sheet, row by row, covering ``drawn`` (all of it by
    default); none when the whole sheet fits on one page."""
    fit = min(tablet.width / width, tablet.height / height)
    if zoom <= fit:
        return []
    sheet = pymupdf.Rect(0, 0, width, height)
    drawn = sheet if drawn is None else drawn & sheet
    w, h = tablet.width / zoom, tablet.height / zoom
    return [
        pymupdf.Rect(x, y, x + w, y + h) & sheet
        for y in _spans(drawn.height, h, drawn.y0, height)
        for x in _spans(drawn.width, w, drawn.x0, width)
    ]


def _tiles(
    width: float, height: float, tablet: pymupdf.Rect, zoom: float, drawn: pymupdf.Rect
) -> tuple[float, list[pymupdf.Rect]]:
    """The zoom, at most a little below ``zoom``, that needs the fewest tiles, and them."""
    best = (zoom, tile_rects(width, height, tablet, zoom, drawn))
    for k in SHRINK[1:]:
        rects = tile_rects(width, height, tablet, zoom * k, drawn)
        if len(rects) < len(best[1]):
            best = (zoom * k, rects)
    return best


def drawn_box(page: pymupdf.Page) -> pymupdf.Rect:
    """What is drawn or written on the sheet, displayed pt, without blank margins."""
    show = ~unrotate(page)
    found = pymupdf.Rect()
    for d in page.get_drawings():
        white = d.get("color") is None and d.get("fill") in (None, (1.0, 1.0, 1.0))
        if not white:
            found |= d["rect"] * show
    for w in page.get_text("words"):
        found |= pymupdf.Rect(w[:4]) * show
    for image in page.get_image_info():
        found |= pymupdf.Rect(image["bbox"]) * show
    if found.is_empty:
        return page.rect
    return (found + (-MARGIN, -MARGIN, MARGIN, MARGIN)) & page.rect


def tablet_size(device: DeviceProfile, orientation: str) -> pymupdf.Rect:
    w, h = device.width * 72 / device.dpi, device.height * 72 / device.dpi
    return pymupdf.Rect(0, 0, h, w) if orientation == "landscape" else pymupdf.Rect(0, 0, w, h)


def choose_orientation(src: pymupdf.Document, numbers: list[int], orientation: str) -> str:
    """The tablet pages lie as most of the sheets do; the tablet turns its menus with them."""
    if orientation not in ORIENTATIONS:
        raise ValueError(f"Orientation is one of {', '.join(ORIENTATIONS)}")
    if orientation != "auto":
        return orientation
    wide = sum(src[n].rect.width > src[n].rect.height for n in numbers)
    return "landscape" if wide * 2 > len(numbers) else "portrait"


# --- the legend --------------------------------------------------------------


def find_legend(page: pymupdf.Page) -> pymupdf.Rect | None:
    """The framed box of text in the sheet's bottom right corner, the title block or
    legend, with the boxes of text stacked on it; displayed sheet pt. A guess."""
    show = ~unrotate(page)
    big = page.rect.width * page.rect.height / 4
    words = [pymupdf.Rect(w[:4]) * show for w in page.get_text("words")]

    def text(r: pymupdf.Rect) -> int:
        return sum(r.contains(w) for w in words)

    edge = drawn_box(page)
    boxes = [
        r
        for r in (d["rect"] * show for d in page.get_drawings())
        if r.width > 20 * MM and r.height > 8 * MM and r.width * r.height < big
    ]
    corner = [
        r
        for r in boxes
        if r.width > 30 * MM
        and r.height > 15 * MM
        and r.x1 > edge.x1 - 30 * MM
        and r.y1 > edge.y1 - 30 * MM
        and text(r) >= 5
    ]
    if not corner:
        return _text_corner(words, edge, big)
    legend = max(corner, key=lambda r: r.width * r.height)
    grown = True
    while grown:
        grown = False
        for r in boxes:
            joined = legend | r
            if (
                r.y0 < legend.y0 - 1
                and legend.y0 - 10 * MM <= r.y1 <= legend.y0 + 2 * MM
                and r.x0 >= legend.x0 - 5 * MM
                and r.x1 <= legend.x1 + 5 * MM
                and joined.width * joined.height < big
                and text(r) >= 3
            ):
                legend, grown = joined, True
    return legend


def _text_corner(words: list[pymupdf.Rect], edge: pymupdf.Rect, big: float) -> pymupdf.Rect | None:
    """Without a frame: the text gathered round the word nearest the bottom right
    corner of what is drawn, word by word while the gaps are small."""
    x, y = edge.x0 + edge.width / 2, edge.y0 + edge.height * 0.4
    near = [w for w in words if w.x0 > x and w.y0 > y]
    if not near:
        return None
    legend = max(near, key=lambda w: w.x1 + w.y1)
    gap = 10 * MM
    grown = True
    while grown:
        grown = False
        for w in near:
            joined = legend | w
            if not legend.contains(w) and joined.width * joined.height < big:
                if (legend + (-gap, -gap, gap, gap)).intersects(w):
                    legend, grown = joined, True
    inside = sum(legend.contains(w) for w in words)
    if (
        inside < 10
        or legend.width < 30 * MM
        or legend.height < 15 * MM
        or legend.x1 < edge.x1 - 60 * MM
        or legend.y1 < edge.y1 - 40 * MM
    ):
        return None
    return legend + (-2, -2, 2, 2)


def _placed_legend(src: pymupdf.Document, number: int) -> pymupdf.Rect | None:
    """The title block of a drawing from rmink sheet drawing, which says where it is."""
    if PLACEMENT not in src.embfile_names():
        return None
    place = json.loads(src.embfile_get(PLACEMENT))
    box = place.get("legend")
    return pymupdf.Rect(box) if box and place.get("page") == number else None


def _text_size(page: pymupdf.Page, legend: pymupdf.Rect) -> float:
    """Usual size of the legend's text, pt; 7 when it has none to read."""
    found = page.get_text("dict", clip=legend * unrotate(page))
    sizes = sorted(
        span["size"]
        for block in found["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        if span["text"].strip()
    )
    return sizes[len(sizes) // 2] if sizes else 7.0


@dataclass
class _Strip:
    """The legend pasted on every tile, beside the part of the sheet the tile shows."""

    area: pymupdf.Rect  # the tile's view of the sheet, tablet pt
    box: pymupdf.Rect  # the legend, tablet pt

    @property
    def blocked(self) -> Box:
        if self.area.x1 < self.box.x0:  # on the right
            return (self.area.x1, 0, self.box.x1 + LEGEND_PAD, self.area.y1)
        return (0, self.area.y1, self.area.x1, self.box.y1 + LEGEND_PAD)


def _strip(legend: pymupdf.Rect, tablet: pymupdf.Rect, text: float) -> _Strip | None:
    """The legend on the side of a tile where it is largest, no larger than printed;
    None when its text would be too small to read there."""
    pad, top = LEGEND_PAD, BACK_BUTTON[1] + 2 * LEGEND_PAD
    right = min(
        1.0,
        (tablet.width * LEGEND_SHARE - 2 * pad) / legend.width,
        (tablet.height - top - pad) / legend.height,
    )
    bottom = min(
        1.0,
        (tablet.width - 2 * pad) / legend.width,
        (tablet.height * LEGEND_SHARE - 2 * pad) / legend.height,
    )
    goal = LEGEND_GOAL * MM / text
    right, bottom = min(right, goal), min(bottom, goal)
    if text * max(right, bottom) / MM < LEGEND_TEXT:
        return None
    # The side the legend fits at its size, or nearer it; then the one costing least.
    lost_right = (legend.width * right + 2 * pad) / tablet.width
    lost_bottom = (legend.height * bottom + 2 * pad) / tablet.height
    on_right = (round(right, 3), -lost_right) >= (round(bottom, 3), -lost_bottom)
    scale = right if on_right else bottom
    w, h = legend.width * scale, legend.height * scale
    if on_right:
        x = tablet.x1 - w - 2 * pad
        box = pymupdf.Rect(x + pad, tablet.y1 - pad - h, tablet.x1 - pad, tablet.y1 - pad)
        return _Strip(pymupdf.Rect(0, 0, x, tablet.y1), box)
    y = tablet.y1 - h - 2 * pad
    box = pymupdf.Rect(tablet.x1 - pad - w, y + pad, tablet.x1 - pad, tablet.y1 - pad)
    return _Strip(pymupdf.Rect(0, 0, tablet.x1, y), box)


# --- the pages ---------------------------------------------------------------


def _show(
    page: pymupdf.Page,
    src: pymupdf.Document,
    number: int,
    clip: pymupdf.Rect,
    derotate: pymupdf.Matrix,
    rotation: int,
    scale: float,
    at: tuple[float, float] = (0, 0),
) -> None:
    """``clip`` of the sheet, in displayed sheet pt, at ``scale`` from ``at`` on the page."""
    if src[number].get_contents():
        x, y = at
        target = pymupdf.Rect(x, y, x + clip.width * scale, y + clip.height * scale)
        page.show_pdf_page(target, src, number, clip=clip * derotate, rotate=-rotation)


@functools.cache
def _font() -> pymupdf.Font:
    return pymupdf.Font("helv")


def _button(page: pymupdf.Page, rect: pymupdf.Rect, label: str, target: int, size: float) -> None:
    page.draw_rect(rect, color=BUTTON, fill=(1, 1, 1), width=0.6)
    # Not insert_text: it takes a font named "helv" in the sheet for its own and
    # adds none, and readers then draw the label without its Ö.
    writer = pymupdf.TextWriter(page.rect)
    writer.append((rect.x0 + 5, rect.y1 - 6), label, font=_font(), fontsize=size)
    writer.write_text(page, color=BUTTON)
    page.insert_link(
        {"kind": pymupdf.LINK_GOTO, "from": rect, "page": target, "to": pymupdf.Point(0, 0)}
    )


def _legend_for(src: pymupdf.Document, number: int, legend: str | Box) -> pymupdf.Rect | None:
    page = src[number]
    if legend == "none":
        return None
    if legend == "auto":
        found = _placed_legend(src, number) or find_legend(page)
    else:
        found = pymupdf.Rect(legend) & page.rect
    return found if found and not found.is_empty else None


def build_pack(
    source: bytes,
    device: DeviceProfile,
    name: str,
    session: str,
    zoom: float = 1.0,
    pages: str | None = None,
    orientation: str = "auto",
    legend: str | Box = "auto",
) -> Pack:
    """A PDF of tablet pages for ``source``, with its manifest embedded.

    ``legend`` is "auto", "none" or a box in displayed sheet pt on every page.
    A legend found goes on every tile beside the sheet, or, when it would be too
    small there to read, on a page of its own that every tile has a button to."""
    if zoom <= 0:
        raise ValueError("Zoom must be above 0")
    src = pymupdf.open(stream=source, filetype="pdf")
    if src.needs_pass:
        raise ValueError("The sheet is password protected")
    numbers = parse_page_ranges(pages, src.page_count)
    if not numbers:
        raise ValueError(f"The sheet has no such pages; it has {src.page_count}")
    orientation = choose_orientation(src, numbers, orientation)
    tablet = tablet_size(device, orientation)
    out = pymupdf.open()
    tiles: list[Tile] = []
    legends: dict[int, Box] = {}

    for number in numbers:
        page = src[number]
        width, height = page.rect.width, page.rect.height
        derotate, rotation = unrotate(page), page.rotation
        found = _legend_for(src, number, legend)
        strip = _strip(found, tablet, _text_size(page, found)) if found else None
        area = strip.area if strip else tablet
        page_zoom, rects = _tiles(width, height, area, zoom, drawn_box(page))
        if not rects:
            found = strip = None  # the overview shows it all
        if found:
            legends[number] = tuple(found)
        own_page = found is not None and strip is None
        if len(tiles) + len(rects) + 1 + own_page > MAX_PAGES:
            raise ValueError(f"Over {MAX_PAGES} tablet pages; use a lower zoom or fewer pages")
        page.set_rotation(0)

        fit = min(tablet.width / width, tablet.height / height)
        first = len(tiles)
        _show(out.new_page(width=tablet.width, height=tablet.height), src, number,
              pymupdf.Rect(0, 0, width, height), derotate, rotation, fit)  # fmt: skip
        tiles.append(
            Tile(
                tablet_page=first,
                sheet_page=number,
                kind="overview",
                matrix=(1 / fit, 0, 0, 1 / fit, 0, 0),
            )
        )
        if own_page:
            top = BACK_BUTTON[1] + 2 * LEGEND_PAD
            z = min(
                (tablet.width - 2 * LEGEND_PAD) / found.width,
                (tablet.height - top - LEGEND_PAD) / found.height,
            )
            at = (LEGEND_PAD, top)
            _show(out.new_page(width=tablet.width, height=tablet.height), src, number,
                  found, derotate, rotation, z, at)  # fmt: skip
            tiles.append(
                Tile(
                    tablet_page=len(tiles),
                    sheet_page=number,
                    kind="legend",
                    matrix=(1 / z, 0, 0, 1 / z, found.x0 - at[0] / z, found.y0 - at[1] / z),
                )
            )
        for rect in rects:
            tile_page = out.new_page(width=tablet.width, height=tablet.height)
            _show(tile_page, src, number, rect, derotate, rotation, page_zoom)
            tile = Tile(
                tablet_page=len(tiles),
                sheet_page=number,
                kind="tile",
                matrix=(1 / page_zoom, 0, 0, 1 / page_zoom, rect.x0, rect.y0),
            )
            if strip:
                band = pymupdf.Rect(strip.blocked)
                tile_page.draw_rect(band, color=None, fill=(1, 1, 1), width=0)
                _show(tile_page, src, number, found, derotate, rotation,
                      strip.box.width / found.width, tuple(strip.box.tl))  # fmt: skip
                edge = (band.tl, band.bl) if band.x0 > 0 else (band.tl, band.tr)
                tile_page.draw_line(*edge, color=(0.45, 0.45, 0.45), width=0.8)
                tile.blocked.append(strip.blocked)
            tiles.append(tile)

        # After the tiles: adding a page invalidates a held one, and links need their target.
        overview = out[first]
        first_tile = first + 1 + own_page
        for n, rect in enumerate(rects, first_tile):
            box = rect * fit
            overview.draw_rect(box, color=(0.45, 0.45, 0.45), width=0.5)
            w, h = NUMBER_BUTTON
            button = pymupdf.Rect(box.x0 + 2, box.y0 + 2, box.x0 + 2 + w, box.y0 + 2 + h)
            _button(overview, button, str(n + 1), n, 12)
            tiles[first].links.append(tuple(button))
        if found:
            box = found * fit
            overview.draw_rect(box, color=(0.45, 0.45, 0.45), width=0.8, dashes="[3 2] 0")
            if own_page:
                w, h = LEGEND_BUTTON
                button = pymupdf.Rect(box.x1 - w - 2, box.y0 - h - 2, box.x1 - 2, box.y0 - 2)
                _button(overview, button, "Förklaring", first + 1, 10)
                tiles[first].links.append(tuple(button))
        for n in range(first + 1, len(tiles)):
            w, h = BACK_BUTTON
            button = pymupdf.Rect(tablet.x1 - w - 4, 4, tablet.x1 - 4, 4 + h)
            _button(out[n], button, "Översikt", first, 10)
            tiles[n].links.append(tuple(button))
            if own_page and n >= first_tile:
                lw, lh = LEGEND_BUTTON
                key = pymupdf.Rect(button.x0 - lw - 6, 4, button.x0 - 6, 4 + lh)
                _button(out[n], key, "Förklaring", first + 1, 10)
                tiles[n].links.append(tuple(key))

    manifest = Manifest(
        rmink=version("rmink"),
        device=device.key,
        name=name,
        session=session,
        orientation=orientation,
        source=Source(name=name, sha256=hashlib.sha256(source).hexdigest(), pages=src.page_count),
        tiles=tiles,
        legends=legends,
    )
    out.embfile_add(MANIFEST, manifest.model_dump_json(indent=1).encode())
    return Pack(out.tobytes(garbage=3, deflate=True), manifest)


def write_pack(
    source: Path,
    output: Path,
    device: DeviceProfile,
    zoom: float = 1.0,
    pages: str | None = None,
    name: str | None = None,
    seed: int | None = None,
    orientation: str = "auto",
    legend: str | Box = "auto",
) -> Manifest:
    """Write a notebook of tablet pages for the PDF at ``source``."""
    uuids = UuidFactory(seed)
    author = uuids()
    title = name or source.stem
    pack = build_pack(
        source.read_bytes(), device, title, str(uuids()), zoom, pages, orientation, legend
    )
    count = len(pack.manifest.tiles)
    write_rmdoc(
        output,
        title,
        [RmdocPage(b"") for _ in range(count)],
        [str(uuids()) for _ in range(count)],
        author,
        device,
        str(uuids()),
        now_ms=0 if seed is not None else None,
        pdf=pack.pdf,
        orientation=pack.manifest.orientation,
    )
    return pack.manifest


def parse_legend(value: str) -> str | Box:
    """ "auto", "none", or a box "x0,y0,x1,y1" in mm from the sheet's top left -> pt."""
    if value in ("auto", "none"):
        return value
    try:
        x0, y0, x1, y1 = (float(v) * MM for v in value.split(","))
    except ValueError:
        x0 = y0 = x1 = y1 = 0.0
    if x1 <= x0 or y1 <= y0:
        raise ValueError('The legend is "auto", "none" or x0,y0,x1,y1 in mm from the top left')
    return (x0, y0, x1, y1)


def layout(manifest: Manifest) -> list[dict]:
    """Per sheet page: its tablet pages and where its legend went."""
    out = []
    for number in dict.fromkeys(t.sheet_page for t in manifest.tiles):
        tiles = [t for t in manifest.tiles if t.sheet_page == number]
        legend = manifest.legends.get(number)
        if legend is None:
            where = None
        elif any(t.kind == "legend" for t in tiles):
            where = "own page"
        else:
            where = "beside each tile"
        out.append(
            {
                "sheet_page": number + 1,
                "tablet_pages": len(tiles),
                "legend": where,
                "legend_mm": [round(v / MM) for v in legend] if legend else None,
            }
        )
    return out


def put_embedded(doc: pymupdf.Document, name: str, data: bytes) -> None:
    """Add or replace an embedded file, keeping the others as they are.

    PyMuPDF adds files at the end of the name tree, which the PDF wants sorted, and
    then deletes the wrong one: replacing a file could remove another, even one of
    the user's. So the tree is written anew, sorted, every time."""
    names = doc.embfile_names()
    files = {}
    for n in names:
        info = doc.embfile_info(n)
        files[n] = (doc.embfile_get(n), info.get("filename") or n, info.get("description") or "")
    files[name] = (data, name, files.get(name, (b"", name, ""))[2])
    if names:
        doc.xref_set_key(doc.pdf_catalog(), "Names/EmbeddedFiles", "null")
    for n in sorted(files):
        content, filename, desc = files[n]
        doc.embfile_add(n, content, filename=filename, desc=desc)


def read_manifest(pdf: bytes) -> dict | None:
    """The manifest embedded in a PDF, if any."""
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return json.loads(doc.embfile_get(MANIFEST)) if MANIFEST in doc.embfile_names() else None
