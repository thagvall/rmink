"""reMarkable device profiles.

Coordinates in `.rm` v6 files are expressed in "scene units". On the
reMarkable 2 one scene unit equals one screen pixel (226 DPI), with x measured
from the horizontal centre of the page and y from the top. Other devices are
believed to use the same unit with a larger page, but this is not documented;
`ink_scale` (scene units per device pixel) lets a calibration correct it
without a new release. Profiles can be overridden in
``~/.config/rmink/devices.toml``::

    [pro]
    ink_scale = 0.987
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

from rmscene.scene_items import PenColor


@dataclass(frozen=True)
class PaletteEntry:
    name: str
    color: PenColor
    rgb: tuple[int, int, int]


MONO_PALETTE: tuple[PaletteEntry, ...] = (
    PaletteEntry("black", PenColor.BLACK, (0, 0, 0)),
    PaletteEntry("gray", PenColor.GRAY, (125, 125, 125)),
)

# Approximate on-screen colours of the Paper Pro (Gallery 3) pen palette.
COLOR_PALETTE: tuple[PaletteEntry, ...] = MONO_PALETTE + (
    PaletteEntry("blue", PenColor.BLUE, (40, 80, 200)),
    PaletteEntry("red", PenColor.RED, (200, 40, 40)),
    PaletteEntry("green", PenColor.GREEN, (40, 150, 60)),
    PaletteEntry("yellow", PenColor.YELLOW, (240, 210, 40)),
    PaletteEntry("pink", PenColor.PINK, (230, 110, 170)),
    PaletteEntry("cyan", PenColor.CYAN, (60, 180, 220)),
    PaletteEntry("magenta", PenColor.MAGENTA, (170, 70, 180)),
)


@dataclass(frozen=True)
class DeviceProfile:
    key: str
    name: str
    width: int  # portrait canvas, device px
    height: int
    dpi: float
    color: bool
    ink_scale: float = 1.0  # scene units per device px
    paper_size: tuple[int, int] | None = None  # written to SceneInfo when set
    verified: bool = False

    @property
    def palette(self) -> tuple[PaletteEntry, ...]:
        return COLOR_PALETTE if self.color else MONO_PALETTE

    @property
    def px_per_mm(self) -> float:
        return self.dpi / 25.4


_BUILTIN: dict[str, DeviceProfile] = {
    p.key: p
    for p in (
        DeviceProfile("rm2", "reMarkable 2", 1404, 1872, 226, False, verified=True),
        DeviceProfile("pure", "reMarkable Paper Pure", 1404, 1872, 226, False),
        DeviceProfile(
            "pro", "reMarkable Paper Pro", 1620, 2160, 229, True, paper_size=(1620, 2160)
        ),
        DeviceProfile(
            "move", "reMarkable Paper Pro Move", 954, 1696, 264, True, paper_size=(954, 1696)
        ),
    )
}


def _config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "rmink" / "devices.toml"


@cache
def all_devices() -> dict[str, DeviceProfile]:
    devices = dict(_BUILTIN)
    path = _config_path()
    if path.is_file():
        overrides = tomllib.loads(path.read_text())
        for key, values in overrides.items():
            if key in devices:
                devices[key] = replace(devices[key], **values)
            else:
                devices[key] = DeviceProfile(key=key, **values)
    return devices


def get_device(key: str) -> DeviceProfile:
    try:
        return all_devices()[key]
    except KeyError:
        known = ", ".join(all_devices())
        raise ValueError(f"Unknown device {key!r}; choose one of: {known}") from None
