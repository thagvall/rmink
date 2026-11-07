"""Let rmscene read pen colours newer than it knows.

The tablet's firmware adds colour codes (a highlighter on rm2 writes 14), and
rmscene then gives up on the whole stroke, so the ink silently goes missing.
An unknown code reads as a highlight colour: the stroke's points are what matter,
and a colour the tablet really knows comes with its own ``color_rgba``.
Importing this module is enough.
"""

from __future__ import annotations

from rmscene.scene_items import PenColor


def _unknown_color(cls: type[PenColor], value: object) -> PenColor:
    return cls.HIGHLIGHT


PenColor._missing_ = classmethod(_unknown_color)
