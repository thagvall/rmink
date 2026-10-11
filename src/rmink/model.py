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

    @property
    def point_count(self) -> int:
        return sum(len(s) for s in self.strokes)


@dataclass
class Document:
    name: str
    pages: list[Page] = field(default_factory=list)
