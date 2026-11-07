"""Symbols as SVG in the format of Open PDF Studio's symbol library."""

from __future__ import annotations

import re

import pymupdf
import pytest

from rmink.drawing.symbols import SYMBOLS, symbol_svg


@pytest.mark.parametrize("kind", sorted(SYMBOLS))
def test_every_symbol_is_a_self_contained_stroke_svg(kind):
    svg = symbol_svg(kind)
    assert svg.startswith('<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" fill="none"')
    assert 'stroke="#000"' in svg and 'stroke-width="2"' in svg
    # The library's rules: no scripts, no links, no images, no text that needs a font.
    for banned in ("<script", "href", "url(", "<image", "<text", "<foreignObject"):
        assert banned not in svg
    numbers = [float(n) for n in re.findall(r"-?\d+\.\d+", svg)]
    assert numbers and all(0 <= n <= 64 for n in numbers)
    doc = pymupdf.open("svg", svg.encode())
    assert doc.page_count == 1


def test_an_unknown_symbol_is_refused():
    with pytest.raises(KeyError):
        symbol_svg("nothing")
