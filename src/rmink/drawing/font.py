"""A single-stroke font for drawing labels, in the upright capitals of
technical lettering. Each glyph is a few polylines on a grid 4 units wide with
the cap height 6, y pointing down from the cap line to the baseline.

Lowercase letters are drawn as capitals, except the ``m`` of units such as
"mm", "m" and "m2", so they keep reading as units.
"""

from __future__ import annotations

import re

import numpy as np

_UNIT = re.compile(r"(?<![A-Za-zÅÄÖåäö])(mm|m)(?=[0-9²³]?(?![A-Za-zÅÄÖåäö]))")

_A = "0,6 2,0 4,6; 0.7,4 3.3,4"
_O = "1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,1 1,0"
_P = "0,6 0,0 3,0 4,1 4,2 3,3 0,3"
_UMLAUT = "; 1.2,-1.1 1.2,-0.6; 2.8,-1.1 2.8,-0.6"

_GLYPHS: dict[str, str] = {
    "A": _A,
    "B": "0,6 0,0 3,0 4,1 4,2 3,3 0,3; 3,3 4,4 4,5 3,6 0,6",
    "C": "4,1 3,0 1,0 0,1 0,5 1,6 3,6 4,5",
    "D": "0,0 0,6 2.5,6 4,4.5 4,1.5 2.5,0 0,0",
    "E": "4,0 0,0 0,6 4,6; 0,3 3,3",
    "F": "4,0 0,0 0,6; 0,3 3,3",
    "G": "4,1 3,0 1,0 0,1 0,5 1,6 3,6 4,5 4,3 2.5,3",
    "H": "0,0 0,6; 4,0 4,6; 0,3 4,3",
    "I": "1,0 3,0; 2,0 2,6; 1,6 3,6",
    "J": "4,0 4,5 3,6 1,6 0,5",
    "K": "0,0 0,6; 4,0 0,4; 1.3,3 4,6",
    "L": "0,0 0,6 4,6",
    "M": "0,6 0,0 2,3 4,0 4,6",
    "N": "0,6 0,0 4,6 4,0",
    "O": _O,
    "P": _P,
    "Q": _O + "; 2.5,4.5 4,6",
    "R": _P + "; 2,3 4,6",
    "S": "4,1 3,0 1,0 0,1 0,2 1,3 3,3 4,4 4,5 3,6 1,6 0,5",
    "T": "0,0 4,0; 2,0 2,6",
    "U": "0,0 0,5 1,6 3,6 4,5 4,0",
    "V": "0,0 2,6 4,0",
    "W": "0,0 1,6 2,3 3,6 4,0",
    "X": "0,0 4,6; 4,0 0,6",
    "Y": "0,0 2,3 4,0; 2,3 2,6",
    "Z": "0,0 4,0 0,6 4,6",
    "Å": _A + "; 1.5,-0.9 2,-1.5 2.5,-0.9 2,-0.3 1.5,-0.9",
    "Ä": _A + _UMLAUT,
    "Ö": _O + _UMLAUT,
    "Ø": _O + "; 0,6.5 4,-0.5",
    "m": "0,6 0,3; 0,3.8 0.8,3 1.6,3 2,3.8 2,6; 2,3.8 2.8,3 3.6,3 4,3.8 4,6",
    "0": _O,
    "1": "1,1 2,0 2,6; 1,6 3,6",
    "2": "0,1 1,0 3,0 4,1 4,2 0,6 4,6",
    "3": "0,1 1,0 3,0 4,1 4,2 3,3 1.5,3; 3,3 4,4 4,5 3,6 1,6 0,5",
    "4": "3,6 3,0 0,4 4,4",
    "5": "4,0 0,0 0,3 3,3 4,4 4,5 3,6 1,6 0,5",
    "6": "3.5,0 1.5,0 0,1.5 0,5 1,6 3,6 4,5 4,4 3,3 1,3 0,4",
    "7": "0,0 4,0 1.5,6",
    "8": "1,3 0,2 0,1 1,0 3,0 4,1 4,2 3,3 1,3 0,4 0,5 1,6 3,6 4,5 4,4 3,3",
    "9": "4,2 3,3 1,3 0,2 0,1 1,0 3,0 4,1 4,5 3,6 1,6",
    "²": "0,0.6 0.5,0 1.5,0 2,0.6 2,1.2 0,3 2,3",
    "³": "0,0.4 0.5,0 1.5,0 2,0.5 1.5,1.5 0.8,1.5; 1.5,1.5 2,2.2 1.5,3 0.5,3 0,2.6",
    ".": "0.3,5.7 0.7,6",
    ",": "0.8,5.4 0.2,7",
    "-": "0.5,3 3.5,3",
    "+": "0.5,3 3.5,3; 2,1.5 2,4.5",
    "=": "0.5,2.2 3.5,2.2; 0.5,3.8 3.5,3.8",
    "/": "0,6 3,0",
    ":": "0.5,1.8 0.5,2.2; 0.5,4.8 0.5,5.2",
    "(": "1.3,0 0.3,1 0,3 0.3,5 1.3,6",
    ")": "0,0 1,1 1.3,3 1,5 0,6",
    "'": "0.3,0 0.3,1.5",
    '"': "0.3,0 0.3,1.5; 1.3,0 1.3,1.5",
    "“": "0.6,0 0.2,1.4; 1.6,0 1.2,1.4",
    "”": "0.6,0 0.2,1.4; 1.6,0 1.2,1.4",
    "’": "0.6,0 0.2,1.4",
    "°": "0.2,0.3 0.8,0 1.4,0.3 1.6,0.9 1.4,1.5 0.8,1.8 0.2,1.5 0,0.9 0.2,0.3",
    "±": "0.5,2.5 3.5,2.5; 2,1 2,4; 0.5,5.5 3.5,5.5",
    "×": "0.8,2 3.2,4.4; 3.2,2 0.8,4.4",
    "?": "0,1 1,0 3,0 4,1 4,2 2,3.2 2,4.4; 2,5.7 2,6",
    "!": "0.3,0 0.3,4.4; 0.3,5.7 0.3,6",
    "<": "4,1 0,3 4,5",
    ">": "0,1 4,3 0,5",
    "→": "0,3 4,3; 2.8,1.8 4,3 2.8,4.2",
    "%": "0,6 4,0; 0.5,0.5 1,0.5; 3,5.5 3.5,5.5",
    # rule references and values: "(BFS 2024:9 2 kap. 11 §)", "≤ 100", "λ 0,036"
    "§": "3,0.8 2.2,0 0.8,0 0,0.8 0.4,1.6 2.6,2.8 3,3.6 2.6,4.4; "
    "0.4,1.6 0,2.4 0.4,3.2 2.6,4.4 3,5.2 2.2,6 0.8,6 0,5.2",
    "–": "0,3 3,3",
    ";": "0.4,2 0.4,2.4; 0.5,5.6 0.1,6.8",
    "≤": "4,0.5 0,2.3 4,4.1; 0,5.5 4,5.5",
    "≥": "0,0.5 4,2.3 0,4.1; 0,5.5 4,5.5",
    "≈": "0,2.4 1,1.8 3,2.6 4,2; 0,4.4 1,3.8 3,4.6 4,4",
    "Λ": "0,6 2,0 4,6",
    "É": "4,0 0,0 0,6 4,6; 0,3 3,3; 1.6,-0.6 2.6,-1.4",
}

_SPACE = 3.0
_GAP = 1.6


def _parse(spec: str) -> list[np.ndarray]:
    return [
        np.array([[float(v) for v in pt.split(",")] for pt in part.split()])
        for part in spec.split(";")
        if part.strip()
    ]


_PARSED = {ch: _parse(spec) for ch, spec in _GLYPHS.items()}


def _glyph(ch: str) -> list[np.ndarray] | None:
    return _PARSED.get(ch)


def _letters(text: str) -> str:
    """Upper-case ``text`` but keep the m of units lower case."""
    keep = {i for m in _UNIT.finditer(text) for i in range(m.start(), m.end())}
    return "".join(ch if i in keep else ch.upper() for i, ch in enumerate(text))


def text_width(text: str, size: float) -> float:
    """Width of ``text`` in px at cap height ``size``."""
    s = size / 6
    w = 0.0
    for ch in _letters(text):
        g = _glyph(ch)
        w += _SPACE if g is None else max(float(p[:, 0].max()) for p in g) + _GAP
    return max(w - _GAP, 0.0) * s


def text_paths(
    text: str, origin: tuple[float, float], size: float, angle: float = 0.0
) -> list[np.ndarray]:
    """Polylines for ``text`` with its baseline starting at ``origin``,
    rotated ``angle`` degrees clockwise (screen coordinates)."""
    s = size / 6
    x = 0.0
    paths = []
    for ch in _letters(text):
        g = _glyph(ch)
        if g is None:
            x += _SPACE
            continue
        for p in g:
            # Glyph y runs 0 (cap line) .. 6 (baseline); the origin is on the baseline.
            paths.append(np.column_stack([p[:, 0] + x, p[:, 1] - 6]) * s)
        x += max(float(p[:, 0].max()) for p in g) + _GAP
    a = np.radians(angle)
    rot = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
    return [p @ rot + np.asarray(origin) for p in paths]
