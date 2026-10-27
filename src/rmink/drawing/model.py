"""The interpreted drawing: what a hand sketch *means*, as data.

A :class:`Drawing` is built by whoever interprets the sketch (Claude through the
MCP server, in practice) from the stroke groups :mod:`rmink.drawing.fit` finds,
and rendered to clean ink by :mod:`rmink.drawing.render`. It is saved between
revisions so the next round of markings can be matched to element ids.

Coordinates are device pixels on the sketch page (origin top-left), so a clean
revision lines up with the sketch it came from and with markings drawn on top
of it. Real-world sizes live in :class:`Dimension` values.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Point = tuple[float, float]
LineType = Literal["solid", "dashed", "dotted", "dashdot"]


class Category(BaseModel):
    """How one kind of element is drawn. ``color`` is a palette name (see
    :mod:`rmink.devices`); greyscale tablets use ``mono_color`` and tell
    categories apart by ``line_type`` and ``width`` instead."""

    name: str
    label: str = ""  # shown in the legend; defaults to the name
    color: str = "black"
    mono_color: Literal["black", "gray"] = "black"
    line_type: LineType = "solid"
    mono_line_type: LineType | None = None  # defaults to line_type
    width: float = 2.0  # device px


DEFAULT_CATEGORIES: list[Category] = [
    Category(name="default", label="Linje"),
    Category(name="structure", label="Bärande", width=4.0),
    Category(name="hidden", label="Dold", mono_color="gray", line_type="dashed"),
    Category(name="center", label="Centrumlinje", mono_color="gray", line_type="dashdot"),
    Category(name="electrical", label="El", color="red", mono_line_type="dotted"),
    Category(name="plumbing", label="VVS", color="blue", mono_line_type="dashed"),
    Category(name="change", label="Ändring", color="green", width=3.0),
    Category(name="dimension", label="Mått", color="gray", mono_color="gray", width=1.5),
    Category(name="comment", label="Kommentar", color="magenta", mono_color="gray", width=2.5),
    Category(name="text", label="Text", width=1.8),
]


class Element(BaseModel):
    id: str
    kind: Literal["line", "polyline", "rect", "circle", "arc", "text"]
    # line: 2 points; polyline: n points; rect: two opposite corners;
    # text: the baseline start. Circles and arcs use center/radius/angles.
    points: list[Point] = Field(default_factory=list)
    closed: bool = False
    center: Point | None = None
    radius: float | None = None
    start_angle: float = 0.0  # degrees, clockwise from +x as on screen
    end_angle: float = 360.0
    text: str | None = None
    size: float = 28.0  # text cap height, device px
    category: str = "default"
    line_type: LineType | None = None  # overrides the category
    note: str = ""
    source_groups: list[int] = Field(default_factory=list)


class Dimension(BaseModel):
    """A measured distance between two points, labelled as written in the
    sketch ("2400", "45°"). ``value`` is the number in ``unit`` when known."""

    id: str
    start: Point
    end: Point
    text: str
    value: float | None = None
    unit: str = "mm"
    offset: float = 40.0  # distance of the dimension line from the measured points, px
    category: str = "dimension"
    source_groups: list[int] = Field(default_factory=list)


class Symbol(BaseModel):
    id: str
    kind: str  # see rmink.drawing.symbols.SYMBOLS
    at: Point
    size: float = 40.0
    rotation: float = 0.0  # degrees
    label: str = ""
    category: str = "default"
    source_groups: list[int] = Field(default_factory=list)


class Annotation(BaseModel):
    """A remark on the drawing: a ring, arrow or cross the user drew to point
    at elements, with the note written next to it."""

    id: str
    kind: Literal["circle", "arrow", "cross", "highlight", "note"]
    targets: list[str] = Field(default_factory=list)  # element/dimension/symbol ids
    at: Point | None = None  # where to draw the marker; defaults to the targets
    text: str = ""
    status: Literal["open", "accepted", "rejected"] = "open"
    revision: int = 1  # revision the remark was made on
    source_groups: list[int] = Field(default_factory=list)


class LegendEntry(BaseModel):
    """One legend row: a symbol kind, or ``category:<name>`` for a line style."""

    key: str
    meaning: str


class SketchRef(BaseModel):
    """Where the drawing came from, to find new strokes in the next round."""

    document: str = ""  # cloud path or local file
    page: int = 1
    device: str = "rm2"
    # CRDT ids (author, counter) rmink wrote on the clean page it sent; any
    # other stroke on that page was added by the user afterwards.
    written_ids: list[tuple[int, int]] = Field(default_factory=list)


class Drawing(BaseModel):
    name: str
    revision: int = 1
    phase: str = ""  # e.g. "Förslag", "Granskning", "Beslut"
    date: str = ""
    categories: list[Category] = Field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    elements: list[Element] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)
    symbols: list[Symbol] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)
    legend: list[LegendEntry] = Field(default_factory=list)
    log: list[str] = Field(default_factory=list)  # one line per change, newest last
    sketch: SketchRef = Field(default_factory=SketchRef)

    def category(self, name: str) -> Category:
        for c in self.categories:
            if c.name == name:
                return c
        for c in DEFAULT_CATEGORIES:
            if c.name == name:
                return c
        return DEFAULT_CATEGORIES[0]

    def find(self, item_id: str) -> Element | Dimension | Symbol | None:
        for item in (*self.elements, *self.dimensions, *self.symbols):
            if item.id == item_id:
                return item
        return None
