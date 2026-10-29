# ruff: noqa: E501
"""A small writer for draw.io (mxGraph) files, for the diagrams build.py makes.

Positions are absolute pixels on the page (or relative to a container). Labels
are HTML, so a box can hold a heading, lines and tables. There is no layout
engine: build.py places things in columns and grids and uses ``text_height``
to stack them without overlap.
"""

from __future__ import annotations

import base64
import html
import math
from dataclasses import dataclass, field
from xml.sax.saxutils import quoteattr

# One colour per kind of thing, the same on every page.
KINDS: dict[str, tuple[str, str, str]] = {
    # kind: (fill, stroke, legend text)
    "interface": ("#dae8fc", "#6c8ebf", "Gränssnitt"),
    "core": ("#d5e8d4", "#82b366", "rmink-kod"),
    "external": ("#eeeeee", "#666666", "Externt system"),
    "data": ("#fff2cc", "#d6b656", "Data och lagring"),
    "law": ("#f8cecc", "#b85450", "Lag, förordning, föreskrift"),
    "practice": ("#e1d5e7", "#9673a6", "Praxis och branschregler"),
    "rmink": ("#d5e8d4", "#82b366", "rmink-regel"),
    "claude": ("#ffe6cc", "#d79b00", "Claude"),
    "device": ("#f5f5f5", "#333333", "reMarkable-platta"),
    "note": ("#ffffff", "#999999", "Anmärkning"),
    "fel": ("#f8cecc", "#b85450", "fel"),
    "fråga": ("#ffe6cc", "#d79b00", "fråga"),
    "info": ("#dae8fc", "#6c8ebf", "info"),
    "plain": ("#ffffff", "#666666", ""),
}

FONT = "Helvetica"
CHAR_W = 6.4  # average px per character at font size 11, a little generous
LINE_H = 13.8  # px per line at font size 11


def esc(text: object) -> str:
    return html.escape(str(text), quote=False)


def text_height(lines: list[str], width: float, size: float = 11, pad: float = 14) -> float:
    """A safe height for ``lines`` of plain text wrapped in ``width`` px."""
    per_line = max(8, int((width - 12) / (CHAR_W * size / 11)))
    rows = sum(max(1, math.ceil(len(line) / per_line)) for line in lines)
    return rows * LINE_H * size / 11 + pad


def label(title: str = "", lines: list[str] | None = None, sub: str = "") -> str:
    """HTML for a box: bold title, an optional grey subtitle, then lines."""
    parts = []
    if title:
        parts.append(f"<b>{esc(title)}</b>")
    if sub:
        parts.append(f'<font color="#333333">{esc(sub)}</font>')
    parts += [esc(x) for x in lines or []]
    return "<br>".join(parts)


def plain_lines(title: str = "", lines: list[str] | None = None, sub: str = "") -> list[str]:
    """The text of ``label`` as lines, for ``text_height``."""
    return [x for x in [title, sub] if x] + list(lines or [])


def table(rows: list[list[str]], head: list[str] | None = None, widths: list[int] | None = None):
    """An HTML table for a label; cells are escaped here."""

    def cells(row, tag):
        out = []
        for i, c in enumerate(row):
            w = f' width="{widths[i]}"' if widths and i < len(widths) else ""
            out.append(f'<{tag} valign="top" align="left"{w}>{esc(c)}</{tag}>')
        return "".join(out)

    body = "".join(f"<tr>{cells(r, 'td')}</tr>" for r in rows)
    top = f'<tr style="font-weight:bold">{cells(head, "td")}</tr>' if head else ""
    return (
        '<table style="border-collapse:collapse;font-size:10px" cellpadding="1" '
        f'cellspacing="0" border="0">{top}{body}</table>'
    )


def table_height(rows: list[list[str]], widths: list[int], head: bool = True) -> float:
    """A safe height for ``table`` at font size 10."""
    total = 0.0
    for row in rows + ([row for row in rows[:1]] if head else []):
        lines = 1
        for c, w in zip(row, widths, strict=False):
            per_line = max(4, int((w - 4) / 5.2))
            lines = max(lines, math.ceil(max(1, len(str(c))) / per_line))
        total += lines * 12.8 + 1.5
    return total


@dataclass
class Cell:
    id: str
    value: str
    style: str
    parent: str = "1"
    geometry: tuple[float, float, float, float] | None = None
    source: str | None = None
    target: str | None = None
    points: list[tuple[float, float]] = field(default_factory=list)

    def xml(self) -> str:
        attrs = (
            f"id={quoteattr(self.id)} value={quoteattr(self.value)} style={quoteattr(self.style)}"
        )
        attrs += f" parent={quoteattr(self.parent)}"
        if self.source:
            attrs += f' edge="1" source={quoteattr(self.source)} target={quoteattr(self.target)}'
            pts = ""
            if self.points:
                pts = (
                    '<Array as="points">'
                    + "".join(f'<mxPoint x="{x:.0f}" y="{y:.0f}"/>' for x, y in self.points)
                    + "</Array>"
                )
            return f'<mxCell {attrs}><mxGeometry relative="1" as="geometry">{pts}</mxGeometry></mxCell>'
        x, y, w, h = self.geometry
        return (
            f'<mxCell {attrs} vertex="1"><mxGeometry x="{x:.0f}" y="{y:.0f}" '
            f'width="{w:.0f}" height="{h:.0f}" as="geometry"/></mxCell>'
        )


class Diagram:
    def __init__(self, name: str, title: str, subtitle: str = "") -> None:
        self.name, self.title = name, title
        self.cells: list[Cell] = []
        self._n = 0
        self._abs: dict[str, tuple[float, float, float, float]] = {}
        self.text(40, 20, 1400, 34, f"<b>{esc(title)}</b>", size=22)
        if subtitle:
            self.text(40, 56, 1400, 22, esc(subtitle), size=12, color="#333333")

    def _id(self, hint: str | None) -> str:
        self._n += 1
        base = "".join(c if c.isalnum() else "_" for c in (hint or "c"))[:40]
        return f"{base}_{self._n}"

    def _add(self, cell: Cell, parent_abs=(0.0, 0.0)) -> str:
        self.cells.append(cell)
        if cell.geometry:
            x, y, w, h = cell.geometry
            self._abs[cell.id] = (x + parent_abs[0], y + parent_abs[1], w, h)
        return cell.id

    def _origin(self, parent: str) -> tuple[float, float]:
        if parent == "1":
            return (0.0, 0.0)
        x, y, _, _ = self._abs[parent]
        return (x, y)

    def box(
        self,
        x,
        y,
        w,
        h,
        value,
        kind="core",
        parent="1",
        hint=None,
        extra="",
        rounded=True,
        size=11,
        align="left",
        valign="top",
    ) -> str:
        fill, stroke, _ = KINDS[kind]
        style = (
            f"rounded={int(rounded)};arcSize=6;whiteSpace=wrap;html=1;fillColor={fill};"
            f"strokeColor={stroke};fontFamily={FONT};fontSize={size};align={align};"
            f"verticalAlign={valign};spacing=6;{extra}"
        )
        cid = self._id(hint)
        return self._add(Cell(cid, value, style, parent, (x, y, w, h)), self._origin(parent))

    def text(self, x, y, w, h, value, size=11, color="#000000", parent="1", align="left") -> str:
        style = (
            f"text;html=1;whiteSpace=wrap;fontFamily={FONT};fontSize={size};fontColor={color};"
            f"align={align};verticalAlign=top;spacing=2;"
        )
        return self._add(
            Cell(self._id("t"), value, style, parent, (x, y, w, h)), self._origin(parent)
        )

    def group(self, x, y, w, h, title, kind="plain", parent="1", hint=None, size=13) -> str:
        """A container with a title bar; children use coordinates inside it."""
        fill, stroke, _ = KINDS[kind]
        style = (
            f"swimlane;html=1;whiteSpace=wrap;startSize=28;fillColor={fill};strokeColor={stroke};"
            f"fontFamily={FONT};fontSize={size};fontStyle=1;swimlaneFillColor=#ffffff;"
            "rounded=1;arcSize=2;collapsible=0;"
        )
        cid = self._id(hint or title)
        return self._add(Cell(cid, esc(title), style, parent, (x, y, w, h)), self._origin(parent))

    def image(self, x, y, w, h, svg: str, parent="1", hint="img") -> str:
        data = base64.b64encode(svg.encode()).decode()
        style = (
            "shape=image;html=1;verticalAlign=top;imageAspect=1;aspect=fixed;"
            f"image=data:image/svg+xml,{data};"
        )
        return self._add(
            Cell(self._id(hint), "", style, parent, (x, y, w, h)), self._origin(parent)
        )

    def edge(
        self,
        src,
        dst,
        value="",
        dashed=False,
        color="#333333",
        parent="1",
        extra="",
        points: list[tuple[float, float]] | None = None,
        curved=False,
        exit: tuple[float, float] | None = None,
        entry: tuple[float, float] | None = None,
    ) -> str:
        """An arrow; ``exit``/``entry`` pin it to a side, as fractions of the box
        (1, 0.5 = middle of the right side)."""
        if exit:
            extra += f"exitX={exit[0]};exitY={exit[1]};exitDx=0;exitDy=0;"
        if entry:
            extra += f"entryX={entry[0]};entryY={entry[1]};entryDx=0;entryDy=0;"
        style = (
            f"edgeStyle={'none' if curved else 'orthogonalEdgeStyle'};rounded=1;html=1;"
            f"fontFamily={FONT};fontSize=10;strokeColor={color};endArrow=block;endFill=1;"
            f"labelBackgroundColor=#ffffff;{'dashed=1;' if dashed else ''}{extra}"
        )
        cell = Cell(self._id("e"), esc(value) if value else "", style, parent)
        cell.source, cell.target, cell.points = src, dst, points or []
        self.cells.append(cell)
        return cell.id

    def legend(self, x, y, kinds: list[str], title="Teckenförklaring") -> float:
        """Coloured swatches for ``kinds``; returns the y below the legend."""
        gid = self.group(x, y, 230, 36 + 24 * len(kinds), title, hint="legend", size=11)
        for i, k in enumerate(kinds):
            self.box(10, 34 + 24 * i, 26, 16, "", k, parent=gid, rounded=False)
            self.text(44, 32 + 24 * i, 180, 20, esc(KINDS[k][2]), size=11, parent=gid)
        return y + 36 + 24 * len(kinds)

    def bounds(self) -> tuple[float, float]:
        right = bottom = 0.0
        for x, y, w, h in self._abs.values():
            right, bottom = max(right, x + w), max(bottom, y + h)
        return right + 40, bottom + 40

    def xml(self) -> str:
        w, h = self.bounds()
        body = "".join(c.xml() for c in self.cells)
        model = (
            f'<mxGraphModel dx="{w:.0f}" dy="{h:.0f}" grid="1" gridSize="10" guides="1" '
            f'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" background="#ffffff" '
            f'pageWidth="{w:.0f}" pageHeight="{h:.0f}" math="0" shadow="0">'
            f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root></mxGraphModel>'
        )
        return (
            '<mxfile host="rmink" agent="docs/diagrams/build.py">'
            f"<diagram id={quoteattr(self.name)} name={quoteattr(self.title)}>{model}</diagram>"
            "</mxfile>\n"
        )


def svg_paths(paths, box: tuple[float, float, float, float], size: float, stroke=1.6) -> str:
    """Polylines fitted into a ``size`` px square SVG, keeping aspect."""
    import numpy as np

    x0, y0, x1, y1 = box
    scale = (size - 8) / max(x1 - x0, y1 - y0, 1e-6)
    ox = (size - (x1 - x0) * scale) / 2 - x0 * scale
    oy = (size - (y1 - y0) * scale) / 2 - y0 * scale
    lines = []
    for p in paths:
        p = np.asarray(p, dtype=float)
        pts = " ".join(f"{x * scale + ox:.1f},{y * scale + oy:.1f}" for x, y in p)
        lines.append(f'<polyline points="{pts}"/>')
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size:.0f}" height="{size:.0f}" '
        f'viewBox="0 0 {size:.0f} {size:.0f}"><g fill="none" stroke="#000" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
        + "".join(lines)
        + "</g></svg>"
    )


def svg_fit(paths, box, max_w: float, max_h: float, stroke=1.0) -> tuple[str, float, float]:
    """Polylines in an SVG that keeps the box's aspect within max_w × max_h;
    returns (svg, width, height)."""
    x0, y0, x1, y1 = box
    scale = min(max_w / max(x1 - x0, 1e-6), max_h / max(y1 - y0, 1e-6))
    w, h = (x1 - x0) * scale, (y1 - y0) * scale
    lines = []
    for p in paths:
        pts = " ".join(f"{(x - x0) * scale:.1f},{(y - y0) * scale:.1f}" for x, y in p)
        lines.append(f'<polyline points="{pts}"/>')
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h:.0f}" '
        f'viewBox="0 0 {w:.1f} {h:.1f}"><g fill="none" stroke="#000" stroke-width="{stroke}" '
        'stroke-linecap="round" stroke-linejoin="round">' + "".join(lines) + "</g></svg>"
    )
    return svg, w, h
