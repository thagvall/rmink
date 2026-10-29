"""Device-independent intermediate representation of converted ink.

All coordinates are in *device pixels* with the origin at the top-left corner of
the page. The writer converts them to reMarkable scene coordinates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from rmscene.scene_items import Pen, PenColor


@dataclass
class Stroke:
    points: np.ndarray  # (N, 2) float32, device px
    width: float = 2.0  # nominal stroke width in device px
    widths: np.ndarray | None = None  # optional per-point width (N,), device px
    pen: Pen = Pen.FINELINER_2
    color: PenColor = PenColor.BLACK
    rgba: tuple[int, int, int, int] | None = None
    pressures: np.ndarray | None = None  # optional per-point pressure (N,), 0-255
    layer: str = "Layer 1"  # name of the tablet layer the stroke is on
    id: tuple[int, int] | None = None  # (author, counter) CrdtId when read from a .rm file

    def __post_init__(self) -> None:
        self.points = np.asarray(self.points, dtype=np.float32).reshape(-1, 2)
        if self.widths is not None:
            self.widths = np.asarray(self.widths, dtype=np.float32).reshape(-1)
            if len(self.widths) != len(self.points):
                raise ValueError("widths must have one entry per point")
        if self.pressures is not None:
            self.pressures = np.asarray(self.pressures, dtype=np.float32).reshape(-1)
            if len(self.pressures) != len(self.points):
                raise ValueError("pressures must have one entry per point")

    def __len__(self) -> int:
        return len(self.points)


@dataclass
class Page:
    width: int  # device px
    height: int  # device px; may exceed the screen height for tall content
    strokes: list[Stroke] = field(default_factory=list)
    # Layers to create in this order, including empty ones for the user to draw on.
    layer_names: list[str] = field(default_factory=list)
    # Layers written switched off; the user can show them in the layer panel.
    hidden_layers: set[str] = field(default_factory=set)

    @property
    def point_count(self) -> int:
        return sum(len(s) for s in self.strokes)

    @property
    def layers(self) -> list[str]:
        """``layer_names`` followed by any other layer the strokes use."""
        names = dict.fromkeys([*self.layer_names, *(s.layer for s in self.strokes)])
        return list(names) or ["Layer 1"]


@dataclass
class Document:
    name: str
    pages: list[Page] = field(default_factory=list)
