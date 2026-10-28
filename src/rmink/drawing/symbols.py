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


def _ellipse(rx: float, ry: float, cx: float = 0.0, cy: float = 0.0, n: int = 32) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n + 1)
    return np.column_stack([cx + rx * np.cos(t), cy + ry * np.sin(t)])


def _rect(x0: float, y0: float, x1: float, y1: float) -> np.ndarray:
    return _poly((x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0))


def _cloud(r: float = 0.4, bump: float = 0.1, n: int = 8) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, 16 * n + 1)
    rr = r + bump * np.abs(np.sin(n / 2 * t))
    return np.column_stack([rr * np.cos(t), rr * np.sin(t)])


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
    # Small-house plans: el, VVS, ventilation, kitchen, deck and revision marks.
    # See src/rmink/knowledge/data/symbols.toml for what each one means.
    "panel": ("Elcentral", [_rect(-0.5, -0.25, 0.5, 0.25), _poly((-0.5, 0.25), (0.5, -0.25))]),
    "outlet_double": (
        "Dubbeluttag",
        [
            _circle(0.3),
            _poly((-0.12, -0.3), (-0.12, -0.5)),
            _poly((0.12, -0.3), (0.12, -0.5)),
            _poly((-0.12, 0.3), (-0.12, 0.5)),
            _poly((0.12, 0.3), (0.12, 0.5)),
        ],
    ),
    "smoke": (
        "Brandvarnare",
        [
            _circle(0.4),
            _poly((-0.24, 0.06), (-0.12, -0.1), (0, 0.06), (0.12, -0.1), (0.24, 0.06)),
        ],
    ),
    "wc": ("WC", [_rect(-0.35, -0.5, 0.35, -0.26), _ellipse(0.28, 0.36, 0, 0.12)]),
    "basin": (
        "Tvättställ",
        [_rect(-0.5, -0.35, 0.5, 0.35), _ellipse(0.36, 0.22, 0, 0.04), _circle(0.04, 0, -0.26)],
    ),
    "shower": ("Dusch", [_SQUARE, _poly((-0.5, 0.5), (0.5, -0.5)), _circle(0.1)]),
    "stove": (
        "Spis",
        [_SQUARE, *(_circle(0.14, x, y) for x in (-0.22, 0.22) for y in (-0.22, 0.22))],
    ),
    "fridge": (
        "Kylskåp",
        [
            _SQUARE,
            _poly((-0.3, 0), (0.3, 0)),
            _poly((-0.15, -0.26), (0.15, 0.26)),
            _poly((0.15, -0.26), (-0.15, 0.26)),
        ],
    ),
    "radiator": (
        "Radiator",
        [
            _rect(-0.5, -0.12, 0.5, 0.12),
            *(_poly((x, -0.12), (x, 0.12)) for x in (-0.3, -0.1, 0.1, 0.3)),
        ],
    ),
    "supply_air": (
        "Tilluftsdon",
        [_circle(0.35), _poly((0, 0), (0, -0.5)), _poly((-0.1, -0.38), (0, -0.5), (0.1, -0.38))],
    ),
    "exhaust_air": (
        "Frånluftsdon",
        [_circle(0.35), _poly((0, -0.5), (0, 0)), _poly((-0.1, -0.12), (0, 0), (0.1, -0.12))],
    ),
    "slope": (
        "Fallriktning",
        [_poly((-0.5, 0), (0.3, 0)), _poly((0.3, -0.15), (0.5, 0), (0.3, 0.15), (0.3, -0.15))],
    ),
    "stair": (
        "Trappa, gångriktning",
        [
            _circle(0.08, -0.42, 0),
            _poly((-0.34, 0), (0.5, 0)),
            _poly((0.32, -0.14), (0.5, 0), (0.32, 0.14)),
        ],
    ),
    "pier": ("Plint", [_SQUARE, _rect(-0.25, -0.25, 0.25, 0.25)]),
    "railing": (
        "Räcke",
        [
            _poly((-0.5, 0), (0.5, 0)),
            *(_poly((x, 0), (x, 0.15)) for x in (-0.4, -0.2, 0, 0.2, 0.4)),
        ],
    ),
    "revision_cloud": ("Revisionsmoln", [_cloud()]),
    "revision": ("Revisionsmärke", [_poly((0, -0.45), (0.5, 0.4), (-0.5, 0.4), (0, -0.45))]),
    "detail": ("Detaljhänvisning", [_circle(0.45), _poly((-0.45, 0), (0.45, 0))]),
}


def symbol_paths(
    kind: str, at: tuple[float, float], size: float, rotation: float = 0.0
) -> list[np.ndarray]:
    """Polylines for symbol ``kind``; unknown kinds draw a labelled box."""
    _, paths = SYMBOLS.get(kind, ("", [_SQUARE]))
    a = np.radians(rotation)
    rot = np.array([[np.cos(a), np.sin(a)], [-np.sin(a), np.cos(a)]])
    return [(p * size) @ rot + np.asarray(at) for p in paths]
