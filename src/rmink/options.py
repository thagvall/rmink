"""Conversion options and results shared by the API, CLI and MCP server."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field
from rmscene.scene_items import Pen

from rmink.geometry.transform import Fit


class Mode(StrEnum):
    auto = "auto"  # vectors for vector PDFs/SVGs; centerline + outline for rasters
    vector = "vector"  # PDF/SVG paths only
    centerline = "centerline"  # trace raster ink as single-line strokes
    outline = "outline"  # trace raster ink as outlines (+ hatch fill)


class FillMode(StrEnum):
    hatch = "hatch"  # outline plus scanline hatching for thick areas
    outline = "outline"  # outline only
    none = "none"  # ignore fills


class PenChoice(StrEnum):
    fineliner = "fineliner"
    ballpoint = "ballpoint"
    marker = "marker"
    pencil = "pencil"

    @property
    def pen(self) -> Pen:
        return {
            "fineliner": Pen.FINELINER_2,
            "ballpoint": Pen.BALLPOINT_2,
            "marker": Pen.MARKER_2,
            "pencil": Pen.PENCIL_2,
        }[self.value]


class ConvertOptions(BaseModel):
    device: str = Field("rm2", description="rm2 | pure | pro | move")
    mode: Mode = Mode.auto
    colors: str = Field(
        "auto",
        description="'auto' (palette colours on colour devices, black on mono), 'mono', "
        "or a number of colour clusters",
    )
    pen: PenChoice = PenChoice.fineliner
    width: float = Field(2.0, gt=0, description="Pen width for outlines/hatching, device px")
    fill: FillMode = FillMode.hatch
    fit: Fit = Fit.page
    margin_mm: float = Field(5.0, ge=0)
    threshold: str = Field("auto", description="'auto' or a 0-255 gray level for ink")
    simplify: float = Field(0.6, ge=0, description="RDP tolerance in device px")
    thick_px: float = Field(
        9.0, gt=0, description="Raster ink wider than this (device px) is outlined, not traced"
    )
    max_points: int = Field(150_000, gt=0, description="Point budget per page")
    pages: str | None = Field(None, description="PDF page ranges, e.g. '1-3,7'")
    name: str | None = None
    compress: bool = False
    seed: int | None = Field(None, description="Make UUIDs deterministic")


class PageStats(BaseModel):
    label: str
    strokes: int
    points: int
    height_px: int


class ConvertResult(BaseModel):
    path: Path
    name: str
    device: str
    size_bytes: int
    pages: list[PageStats]
    warnings: list[str] = []
    preview_path: Path | None = None
