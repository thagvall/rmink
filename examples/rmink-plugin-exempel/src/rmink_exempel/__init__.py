"""An example rmink plugin: one small part of each kind.

Each part is an ordinary function or object; ``pyproject.toml`` tells rmink
where it is. The folder this file is in is also a content pack (``pack.toml``,
``knowledge/``, ``workbook/``), which needs no code at all.
"""

from __future__ import annotations

import json
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import typer

from rmink.ingest import VectorShape, VectorSource
from rmink.transport import Entry, FolderTransport, TransportError

# ----------------------------------------------------------------- transport
# rmink.transports: a function that takes what follows "zip:" and returns an
# object with ls, get, put, mkdir, mv and rmdir (rmink.transport.Transport).


class ZipTransport:
    """The whole tree of notebooks in one zip file. Each call unpacks the
    file, lets the folder transport do the work and packs it again."""

    name = "zip"

    def __init__(self, file: Path) -> None:
        self.file = file

    def __repr__(self) -> str:
        return f"zip:{self.file}"

    @contextmanager
    def _tree(self, write: bool = False) -> Iterator[FolderTransport]:
        with tempfile.TemporaryDirectory() as tmp:
            if self.file.is_file():
                with zipfile.ZipFile(self.file) as zf:
                    zf.extractall(tmp)
            yield FolderTransport(tmp)
            if write:
                with zipfile.ZipFile(self.file, "w") as zf:
                    for path in sorted(Path(tmp).rglob("*")):
                        zf.write(path, path.relative_to(tmp).as_posix())

    def ls(self, path: str = "/") -> list[Entry]:
        with self._tree() as tree:
            return tree.ls(path)

    def get(self, path: str) -> bytes:
        with self._tree() as tree:
            return tree.get(path)

    def put(self, file: Path, folder: str = "/", name: str | None = None) -> str:
        with self._tree(write=True) as tree:
            return tree.put(file, folder, name)

    def mkdir(self, path: str) -> None:
        with self._tree(write=True) as tree:
            tree.mkdir(path)

    def mv(self, src: str, dst: str) -> None:
        with self._tree(write=True) as tree:
            tree.mv(src, dst)

    def rmdir(self, path: str) -> None:
        with self._tree(write=True) as tree:
            tree.rmdir(path)


def open_zip(arg: str) -> ZipTransport:
    if not arg:
        raise TransportError('Give the zip file: "zip:~/rmink.zip"')
    return ZipTransport(Path(arg).expanduser())


# ------------------------------------------------------------------ importer
# rmink.importers, named after the file suffix: path, mode and pages in, a
# list of pages out (VectorSource or RasterSource from rmink.ingest).


def _lines(geometry: dict) -> Iterator[tuple[list, bool]]:
    kind, coords = geometry.get("type"), geometry.get("coordinates", [])
    if kind == "LineString":
        yield coords, False
    elif kind == "MultiLineString":
        yield from ((line, False) for line in coords)
    elif kind == "Polygon":
        yield from ((ring, True) for ring in coords)
    elif kind == "MultiPolygon":
        yield from ((ring, True) for polygon in coords for ring in polygon)
    elif kind == "GeometryCollection":
        for g in geometry.get("geometries", []):
            yield from _lines(g)


def load_geojson(path: Path, mode: str, pages: str | None = None) -> list[VectorSource]:
    """Lines and polygons of a GeoJSON file as one page, north up."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    features = data.get("features", [data]) if data.get("type") != "Feature" else [data]
    lines = [
        (np.array([p[:2] for p in coords], dtype=float), closed)
        for f in features
        for coords, closed in _lines(f.get("geometry") or f)
        if len(coords) >= 2
    ]
    if not lines:
        raise ValueError("no lines or polygons in the file")
    points = np.vstack([line for line, _ in lines])
    low, span = points.min(axis=0), np.maximum(np.ptp(points, axis=0), 1e-9)
    scale = 500.0 / span.max()  # the longer side becomes 500 pt

    def to_page(line: np.ndarray) -> np.ndarray:
        xy = (line - low) * scale
        xy[:, 1] = span[1] * scale - xy[:, 1]  # y down on the page
        return xy

    shapes = [
        VectorShape([to_page(line)], [closed], None, (0, 0, 0), 1.0) for line, closed in lines
    ]
    return [VectorSource(Path(path).name, span[0] * scale, span[1] * scale, shapes)]


# ------------------------------------------------------------------ exporter
# rmink.exporters, named after the format: a Drawing in, bytes (or str) out.


def export_geojson(drawing) -> str:
    """The drawing's lines, rectangles and texts as GeoJSON, in page pixels
    with y up."""

    def xy(point) -> list[float]:
        return [round(point[0], 2), round(-point[1], 2)]

    features = []
    for e in drawing.elements:
        if e.kind in ("line", "polyline"):
            ring = [xy(p) for p in e.points]
            closed = e.closed and len(ring) > 2
            geometry = (
                {"type": "Polygon", "coordinates": [ring + ring[:1]]}
                if closed
                else {"type": "LineString", "coordinates": ring}
            )
        elif e.kind == "rect" and len(e.points) == 2:
            (x0, y0), (x1, y1) = e.points
            ring = [xy(p) for p in ((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))]
            geometry = {"type": "Polygon", "coordinates": [ring]}
        elif e.kind in ("circle", "arc") and e.center:
            geometry = {"type": "Point", "coordinates": xy(e.center)}
        elif e.kind == "text" and e.points:
            geometry = {"type": "Point", "coordinates": xy(e.points[0])}
        else:
            continue
        properties = {"id": e.id, "kind": e.kind, "category": e.category}
        if e.text:
            properties["text"] = e.text
        if e.radius:
            properties["radius"] = e.radius
        features.append({"type": "Feature", "geometry": geometry, "properties": properties})
    collection = {"type": "FeatureCollection", "name": drawing.name, "features": features}
    return json.dumps(collection, ensure_ascii=False, indent=1)


# ------------------------------------------------------------------- command
# rmink.commands: a typer.Typer (or a plain function), added as `rmink exempel`.

app = typer.Typer(help="The example plugin: says what it brings.", invoke_without_command=True)


@app.callback()
def info() -> None:
    """Say what the example plugin brings."""
    typer.echo(_info())


def _info() -> str:
    return (
        "rmink-exempel brings: the transport zip:FILE, the pack exempel (symbol "
        "sauna_heater, term lave, workbook group kartor), .geojson in and geojson out."
    )


# ------------------------------------------------------------------ MCP tool
# rmink.mcp_tools: a function that gets the MCP server and adds tools to it.


def register(server) -> None:
    @server.tool()
    def exempel_info() -> str:
        """What the rmink example plugin brings."""
        return _info()
