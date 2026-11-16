"""A clean drawing in another program's format.

``pdf`` (a sheet at a true scale, :mod:`rmink.bridge.drawing_pdf`) and ``svg``
(the tablet page) are built in; a plugin adds a format with an
``rmink.exporters`` entry point named after it, ``export(drawing) -> bytes``
(or ``str``, written as UTF-8). See docs/plugins.md.
"""

from __future__ import annotations

from rmink import plugins
from rmink.drawing.model import Drawing

BUILTIN = ("pdf", "svg")


def formats() -> list[str]:
    return [*BUILTIN, *(n for n in plugins.found("rmink.exporters") if n not in BUILTIN)]


def export(drawing: Drawing, fmt: str) -> bytes:
    """``drawing`` in the format ``fmt``; ``ValueError`` names the formats there are."""
    fmt = fmt.lower().lstrip(".")
    if fmt == "pdf":
        from rmink.bridge.drawing_pdf import drawing_pdf

        return drawing_pdf(drawing, "a3", None).pdf
    if fmt == "svg":
        from rmink.devices import get_device
        from rmink.drawing.render import page_svg, render_drawing

        device = get_device(drawing.sketch.device)
        return page_svg(render_drawing(drawing, device), device).encode("utf-8")
    exporter = plugins.load("rmink.exporters", fmt) if fmt not in BUILTIN else None
    if exporter is None:
        raise ValueError(f'No export format "{fmt}". Choose one of: ' + ", ".join(formats()))
    try:
        data = exporter(drawing)
    except Exception as e:
        raise ValueError(f'The exporter "{fmt}" failed: {e}') from e
    if isinstance(data, str):
        data = data.encode("utf-8")
    if not isinstance(data, (bytes, bytearray)):
        raise ValueError(f'The exporter "{fmt}" returned {type(data).__name__}, not bytes')
    return bytes(data)
