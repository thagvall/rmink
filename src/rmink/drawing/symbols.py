"""Built-in drawing symbols as polylines in a unit box centred on the origin
(-0.5..0.5, y down). :func:`symbol_paths` scales, rotates and places them."""

from __future__ import annotations

import numpy as np


def _circle(r: float = 0.5, cx: float = 0.0, cy: float = 0.0, n: int = 32) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n + 1)
    return np.column_stack([cx + r * np.cos(t), cy + r * np.sin(t)])


def _arc(r: float, a0: float, a1: float, cx: float = 0.0, cy: float = 0.0) -> np.ndarray:
    t = np.radians(np.linspace(a0, a1, 16))
    return np.column_stack([cx + r * np.cos(t), cy + r * np.sin(t)])


def _poly(*pts: tuple[float, float]) -> np.ndarray:
    return np.array(pts, dtype=float)


_SQUARE = _poly((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5), (-0.5, -0.5))

# name -> (description shown in the legend by default, polylines)
SYMBOLS: dict[str, tuple[str, list[np.ndarray]]] = {
    "column": (
        "Pelare",
        [_SQUARE, _poly((-0.5, -0.5), (0.5, 0.5)), _poly((0.5, -0.5), (-0.5, 0.5))],
    ),
    "north": (
        "Norrpil",
        [_circle(0.4), _poly((-0.2, 0.25), (0, -0.5), (0.2, 0.25), (0, 0.1), (-0.2, 0.25))],
    ),
    "section": (
        "Snitt",
        [
            _circle(0.3),
            _poly((-0.3, 0), (0.3, 0)),
            _poly((0, -0.3), (0, -0.5)),
            _poly((-0.12, -0.38), (0, -0.5), (0.12, -0.38)),
        ],
    ),
    "level": (
        "Nivå",
        [_poly((-0.5, 0), (0.5, 0)), _poly((-0.25, -0.45), (0.25, -0.45), (0, 0), (-0.25, -0.45))],
    ),
    "door": (
        "Dörr",
        [
            _poly((-0.5, 0.5), (-0.5, -0.5)),
            _arc(1.0, -90, 0, -0.5, 0.5),
            _poly((-0.5, 0.5), (0.5, 0.5)),
        ],
    ),
    "window": (
        "Fönster",
        [
            _poly((-0.5, -0.12), (0.5, -0.12)),
            _poly((-0.5, 0), (0.5, 0)),
            _poly((-0.5, 0.12), (0.5, 0.12)),
        ],
    ),
    "outlet": (
        "Eluttag",
        [_circle(0.3), _poly((-0.12, -0.3), (-0.12, -0.5)), _poly((0.12, -0.3), (0.12, -0.5))],
    ),
    "light": (
        "Armatur",
        [_circle(0.4), _poly((-0.28, -0.28), (0.28, 0.28)), _poly((0.28, -0.28), (-0.28, 0.28))],
    ),
    "switch": (
        "Strömbrytare",
        [_circle(0.15), _poly((0.1, -0.1), (0.45, -0.45)), _poly((0.35, -0.55), (0.55, -0.35))],
    ),
    "drain": ("Golvbrunn", [_SQUARE, _circle(0.3)]),
    "bolt": ("Bult", [_circle(0.35), _poly((-0.5, 0), (0.5, 0)), _poly((0, -0.5), (0, 0.5))]),
    "weld": (
        "Svets",
        [_poly((-0.5, 0.3), (0.5, 0.3)), _poly((-0.25, 0.3), (0, -0.2), (0.25, 0.3))],
    ),
    "point": ("Punkt", [_poly((-0.3, 0), (0.3, 0)), _poly((0, -0.3), (0, 0.3)), _circle(0.15)]),
    "cross": ("Kryss", [_poly((-0.5, -0.5), (0.5, 0.5)), _poly((0.5, -0.5), (-0.5, 0.5))]),
    "tree": ("Träd", [_circle(0.5), _circle(0.06)]),
}


def symbol_paths(
    kind: str, at: tuple[float, float], size: float, rotation: float = 0.0
) -> list[np.ndarray]:
    """Polylines for symbol ``kind``; unknown kinds draw a labelled box."""
    _, paths = SYMBOLS.get(kind, ("", [_SQUARE]))
    a = np.radians(rotation)
    rot = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
    return [(p * size) @ rot + np.asarray(at) for p in paths]
