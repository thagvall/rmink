"""A calculator for drawings, so numbers come from code and not from guessing.

:func:`evaluate` runs one arithmetic expression safely (no names, attributes
or calls beyond the functions below). Trigonometry is in degrees, as on a
drawing. Helpers cover what a builder reaches for:

- right triangles and any triangle: ``hypot(3600, 1200)``, ``leg(5, 3)``,
  ``triangle(3, 4, 5)`` (angles opposite each side and the area)
- slopes and roof pitch: ``slope(1200, 3600)``, ``pitch(27)`` give degrees,
  1:x and percent
- areas and volumes: ``area([(0, 0), (4, 0), (4, 3)])``, ``circle(d)``,
  ``cylinder(d, h)``
- weight from a material's density in the knowledge base:
  ``weight(0.045 * 0.195 * 4.8, "C24")`` in kg for a volume in m³
- quantities: ``count(4800, 600)`` pieces at c/c spacing including both ends,
  ``pieces(23.5, 4.8)`` lengths to buy, ``waste(42, 10)`` with 10 % waste
- sets: ``{"A1", "A2"} | {"A2", "A3"}``, ``&``, ``-``, ``^``, ``len``, ``in``

Units are whatever you put in; the helpers never convert between mm and m.
"""

from __future__ import annotations

import ast
import math
import operator

MAX_LENGTH = 1000


class CalcError(ValueError):
    """The expression could not be evaluated; the message says why."""


def format_angle(deg: float) -> str:
    """Degrees as written on a Swedish drawing: "38,7°", "90°"."""
    text = f"{deg:.1f}".rstrip("0").rstrip(".")
    return text.replace(".", ",") + "°"


def _number(x) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise CalcError(f"expected a number, got {x!r}")
    return x


def _slope(deg: float) -> dict:
    t = math.tan(math.radians(deg))
    return {
        "deg": deg,
        "ratio": f"1:{1 / t:.3g}" if t > 1e-12 else "plan",
        "percent": t * 100,
    }


def slope(rise: float, run: float) -> dict:
    """Pitch of a rise over a horizontal run: degrees, 1:x and percent."""
    if _number(run) <= 0:
        raise CalcError("run must be positive")
    return _slope(math.degrees(math.atan2(_number(rise), run)))


def pitch(deg: float) -> dict:
    """A pitch in degrees as 1:x and percent."""
    if not 0 <= _number(deg) < 90:
        raise CalcError("pitch must be 0–90°")
    return _slope(deg)


def leg(c: float, a: float) -> float:
    """The other leg of a right triangle with hypotenuse c and leg a."""
    if _number(a) > _number(c):
        raise CalcError("a leg cannot be longer than the hypotenuse")
    return math.sqrt(c * c - a * a)


def triangle(a: float, b: float, c: float) -> dict:
    """Angles A, B, C (opposite sides a, b, c) in degrees, and the area."""
    a, b, c = sides = (_number(a), _number(b), _number(c))
    longest = max(sides)
    if min(sides) <= 0 or longest >= sum(sides) - longest:
        raise CalcError("these sides do not make a triangle")

    def angle(opp, x, y):  # law of cosines
        cos = (x * x + y * y - opp * opp) / (2 * x * y)
        return math.degrees(math.acos(max(-1.0, min(1.0, cos))))

    s = (a + b + c) / 2
    return {
        "A": angle(a, b, c),
        "B": angle(b, a, c),
        "C": angle(c, a, b),
        "area": math.sqrt(max(0.0, s * (s - a) * (s - b) * (s - c))),
    }


def area(points) -> float:
    """Area of a polygon from its corners (shoelace formula)."""
    pts = [(_number(x), _number(y)) for x, y in points]
    if len(pts) < 3:
        raise CalcError("a polygon needs at least 3 corners")
    pairs = zip(pts, pts[1:] + pts[:1], strict=True)
    twice = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in pairs)
    return abs(twice) / 2


def circle(d: float) -> float:
    """Area of a circle with diameter d."""
    return math.pi * _number(d) ** 2 / 4


def cylinder(d: float, h: float) -> float:
    """Volume of a cylinder (a round pier, a tube of concrete) with diameter d."""
    return circle(d) * _number(h)


def density(material: str) -> float:
    """Approximate density in kg/m³ of a material in the knowledge base."""
    from rmink import knowledge

    hits = knowledge.lookup(str(material), kind="material", limit=1)
    if not hits or not hits[0].get("density"):
        raise CalcError(f"no density for {material!r}")
    return hits[0]["density"]


def weight(volume_m3: float, material: str) -> float:
    """Weight in kg of a volume in m³ of a material (approximate density)."""
    return _number(volume_m3) * density(material)


def count(length: float, cc: float) -> int:
    """Pieces at c/c spacing along a length, both ends included (joists, studs)."""
    if _number(cc) <= 0:
        raise CalcError("spacing must be positive")
    return math.floor(_number(length) / cc + 1e-9) + 1


def pieces(total: float, piece: float) -> int:
    """Whole pieces of one length needed for a total length."""
    if _number(piece) <= 0:
        raise CalcError("piece length must be positive")
    return math.ceil(_number(total) / piece - 1e-9)


def waste(quantity: float, percent: float) -> float:
    """A quantity with a waste allowance in percent."""
    return _number(quantity) * (1 + _number(percent) / 100)


def _deg(f):
    return lambda x: f(math.radians(_number(x)))


def _adeg(f):
    return lambda *x: math.degrees(f(*map(_number, x)))


FUNCTIONS = {
    "sin": _deg(math.sin),
    "cos": _deg(math.cos),
    "tan": _deg(math.tan),
    "asin": _adeg(math.asin),
    "acos": _adeg(math.acos),
    "atan": _adeg(math.atan),
    "atan2": _adeg(math.atan2),
    "rad": math.radians,
    "deg": math.degrees,
    "sqrt": math.sqrt,
    "hypot": math.hypot,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "min": min,
    "max": max,
    "sum": sum,
    "len": len,
    "set": set,
    "leg": leg,
    "triangle": triangle,
    "slope": slope,
    "pitch": pitch,
    "area": area,
    "circle": circle,
    "cylinder": cylinder,
    "density": density,
    "weight": weight,
    "count": count,
    "pieces": pieces,
    "waste": waste,
}
CONSTANTS = {"pi": math.pi, "e": math.e}

_ARITH = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_SET_OPS = {
    ast.BitOr: operator.or_,
    ast.BitAnd: operator.and_,
    ast.Sub: operator.sub,
    ast.BitXor: operator.xor,
}
_COMPARE = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def _eval(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float, str)):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        raise CalcError(f"unknown name {node.id!r}")
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_eval(x) for x in node.elts]
    if isinstance(node, ast.Set):
        return {_eval(x) for x in node.elts}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        x = _number(_eval(node.operand))
        return -x if isinstance(node.op, ast.USub) else x
    if isinstance(node, ast.BinOp):
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(left, (set, frozenset)) and isinstance(right, (set, frozenset)):
            if type(node.op) not in _SET_OPS:
                raise CalcError("sets take |, &, - and ^")
            return _SET_OPS[type(node.op)](left, right)
        if type(node.op) not in _ARITH:
            raise CalcError("unsupported operator")
        left, right = _number(left), _number(right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 64 or abs(left) > 1e12):
            raise CalcError("power too large")
        try:
            return _ARITH[type(node.op)](left, right)
        except ZeroDivisionError:
            raise CalcError("division by zero") from None
    if isinstance(node, ast.Compare):
        left = _eval(node.left)
        for op, comp in zip(node.ops, node.comparators, strict=True):
            right = _eval(comp)
            if not _COMPARE[type(op)](left, right):
                return False
            left = right
        return True
    if isinstance(node, ast.Subscript):
        value, key = _eval(node.value), _eval(node.slice)
        try:
            return value[key]
        except (KeyError, IndexError, TypeError):
            raise CalcError(f"no item {key!r}") from None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        f = FUNCTIONS.get(node.func.id)
        if f is None:
            raise CalcError(f"unknown function {node.func.id!r}")
        args = [_eval(a) for a in node.args]
        kwargs = {k.arg: _eval(k.value) for k in node.keywords if k.arg}
        try:
            return f(*args, **kwargs)
        except CalcError:
            raise
        except (TypeError, ValueError, OverflowError) as e:
            raise CalcError(f"{node.func.id}: {e}") from None
    raise CalcError(f"not allowed: {ast.dump(node)[:60]}")


def _clean(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CalcError("the result is not a finite number")
        value = round(value, 6)
        return 0.0 if value == 0 else value
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_clean(v) for v in value), key=repr)
    return value


def evaluate(expression: str):
    """The value of ``expression``: a number, bool, list (sets come back
    sorted) or dict. Raises :class:`CalcError` with a readable reason."""
    if len(expression) > MAX_LENGTH:
        raise CalcError("expression too long")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise CalcError(f"syntax error: {e.msg}") from None
    return _clean(_eval(tree))
