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
OVERLAP = 0.05  # share of a tile shown again on its neighbour
MAX_PAGES = 200
NUMBER_BUTTON = (30, 22)  # pt, big enough to hit with the pen
BACK_BUTTON = (58, 20)
BUTTON = (0.25, 0.25, 0.25)

Matrix = tuple[float, float, float, float, float, float]


class Tile(BaseModel):
    tablet_page: int  # 0-based page of the notebook
    sheet_page: int  # 0-based page of the sheet
    kind: str  # "overview" or "tile"
    matrix: Matrix  # (a, b, c, d, e, f): tablet pt -> displayed sheet pt
    links: list[tuple[float, float, float, float]] = []  # buttons on the page, tablet pt

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
    source: Source
    tiles: list[Tile]

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


def _spans(length: int | float, tile: float) -> list[float]:
    """Start of each tile along one side of a sheet, evenly spaced so that the
    last one does not end up almost on top of the one before."""
    if length <= tile:
        return [0.0]
    count = math.ceil((length - tile) / (tile * (1 - OVERLAP))) + 1
    return [i * (length - tile) / (count - 1) for i in range(count)]


def tile_rects(
    width: float, height: float, tablet: pymupdf.Rect, zoom: float
) -> list[pymupdf.Rect]:
    """The regions of a sheet, row by row; the whole sheet when it fits on one page."""
    fit = min(tablet.width / width, tablet.height / height)
    if zoom <= fit:
        return []
    w, h = tablet.width / zoom, tablet.height / zoom
    sheet = pymupdf.Rect(0, 0, width, height)
    return [
        pymupdf.Rect(x, y, x + w, y + h) & sheet
        for y in _spans(height, h)
        for x in _spans(width, w)
    ]


def _place(
    out: pymupdf.Document,
    src: pymupdf.Document,
    number: int,
    clip: pymupdf.Rect,
    derotate: pymupdf.Matrix,
    rotation: int,
    scale: float,
    tablet: pymupdf.Rect,
) -> None:
    page = out.new_page(width=tablet.width, height=tablet.height)
    if src[number].get_contents():
        target = pymupdf.Rect(0, 0, clip.width * scale, clip.height * scale)
        page.show_pdf_page(target, src, number, clip=clip * derotate, rotate=-rotation)


def _button(page: pymupdf.Page, rect: pymupdf.Rect, label: str, target: int, size: float) -> None:
    page.draw_rect(rect, color=BUTTON, fill=(1, 1, 1), width=0.6)
    page.insert_text((rect.x0 + 5, rect.y1 - 6), label, fontsize=size, color=BUTTON)
    page.insert_link(
        {"kind": pymupdf.LINK_GOTO, "from": rect, "page": target, "to": pymupdf.Point(0, 0)}
    )


def build_pack(
    source: bytes,
    device: DeviceProfile,
    name: str,
    session: str,
    zoom: float = 1.0,
    pages: str | None = None,
) -> Pack:
    """A PDF of tablet pages for ``source``, with its manifest embedded."""
    if zoom <= 0:
        raise ValueError("Zoom must be above 0")
    src = pymupdf.open(stream=source, filetype="pdf")
    if src.needs_pass:
        raise ValueError("The sheet is password protected")
    numbers = parse_page_ranges(pages, src.page_count)
    if not numbers:
        raise ValueError(f"The sheet has no such pages; it has {src.page_count}")
    tablet = pymupdf.Rect(0, 0, device.width * 72 / device.dpi, device.height * 72 / device.dpi)
    out = pymupdf.open()
    tiles: list[Tile] = []

    for number in numbers:
        page = src[number]
        width, height = page.rect.width, page.rect.height
        derotate, rotation = unrotate(page), page.rotation
        rects = tile_rects(width, height, tablet, zoom)
        if len(tiles) + len(rects) + 1 > MAX_PAGES:
            raise ValueError(f"Over {MAX_PAGES} tablet pages; use a lower zoom or fewer pages")
        page.set_rotation(0)

        fit = min(tablet.width / width, tablet.height / height)
        whole = pymupdf.Rect(0, 0, width, height)
        first = len(tiles)
        _place(out, src, number, whole, derotate, rotation, fit, tablet)
        tiles.append(
            Tile(
                tablet_page=len(tiles),
                sheet_page=number,
                kind="overview",
                matrix=(1 / fit, 0, 0, 1 / fit, 0, 0),
            )
        )
        for rect in rects:
            tiles.append(
                Tile(
                    tablet_page=len(tiles),
                    sheet_page=number,
                    kind="tile",
                    matrix=(1 / zoom, 0, 0, 1 / zoom, rect.x0, rect.y0),
                )
            )
            _place(out, src, number, rect, derotate, rotation, zoom, tablet)
        # After the tiles: adding a page invalidates a held one, and links need their target.
        overview = out[first]
        for n, rect in enumerate(rects, first + 1):
            box = rect * fit
            overview.draw_rect(box, color=(0.45, 0.45, 0.45), width=0.5)
            w, h = NUMBER_BUTTON
            button = pymupdf.Rect(box.x0 + 2, box.y0 + 2, box.x0 + 2 + w, box.y0 + 2 + h)
            _button(overview, button, str(n + 1), n, 12)
            tiles[first].links.append(tuple(button))
        for n in range(first + 1, len(tiles)):
            w, h = BACK_BUTTON
            button = pymupdf.Rect(tablet.x1 - w - 4, 4, tablet.x1 - 4, 4 + h)
            _button(out[n], button, "Översikt", first, 10)
            tiles[n].links.append(tuple(button))

    manifest = Manifest(
        rmink=version("rmink"),
        device=device.key,
        name=name,
        session=session,
        source=Source(name=name, sha256=hashlib.sha256(source).hexdigest(), pages=src.page_count),
        tiles=tiles,
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
) -> Manifest:
    """Write a notebook of tablet pages for the PDF at ``source``."""
    uuids = UuidFactory(seed)
    author = uuids()
    title = name or source.stem
    pack = build_pack(source.read_bytes(), device, title, str(uuids()), zoom, pages)
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
    )
    return pack.manifest


def read_manifest(pdf: bytes) -> dict | None:
    """The manifest embedded in a PDF, if any."""
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    return json.loads(doc.embfile_get(MANIFEST)) if MANIFEST in doc.embfile_names() else None
