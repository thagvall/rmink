"""Build a ``.rmdoc`` notebook archive from rendered pages.

Archive layout::

    {doc}.content
    {doc}.metadata
    {doc}/{page}.rm
    {doc}/{page}-metadata.json
    {doc}.thumbnails/{page}.png
"""

from __future__ import annotations

import json
import random
import time
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from rmink.devices import DeviceProfile

# The USB web interface rejects uploads above 100 MB (decimal).
UPLOAD_LIMIT_BYTES = 100_000_000
UPLOAD_WARN_MARGIN = 2_000_000


class UuidFactory:
    """UUID4 generator that is deterministic when seeded (for golden tests)."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed) if seed is not None else None

    def __call__(self) -> uuid.UUID:
        if self._rng is None:
            return uuid.uuid4()
        return uuid.UUID(int=self._rng.getrandbits(128), version=4)


def page_indices(count: int) -> list[str]:
    """Lexicographically increasing page ``idx`` values: ba, bb, ..., bz, ca, ...

    The first character runs b..z and the remaining characters a..z, widening
    the string when more pages are needed so ordering never breaks.
    """
    width = 2
    while 25 * 26 ** (width - 1) < count:
        width += 1
    result = []
    for i in range(count):
        digits = []
        n = i
        for _ in range(width - 1):
            n, r = divmod(n, 26)
            digits.append(chr(ord("a") + r))
        result.append(chr(ord("b") + n) + "".join(reversed(digits)))
    return result


@dataclass
class RmdocPage:
    rm_bytes: bytes
    thumbnail_png: bytes | None = None


@dataclass
class RmdocResult:
    path: Path
    doc_id: str
    size_bytes: int
    warnings: list[str] = field(default_factory=list)


def _content(
    page_ids: list[str], author_uuid: uuid.UUID, device: DeviceProfile, size_bytes: int
) -> dict:
    stamp = "1:2"
    return {
        "cPages": {
            "lastOpened": {"timestamp": stamp, "value": page_ids[0] if page_ids else ""},
            "original": {"timestamp": "0:0", "value": -1},
            "pages": [
                {
                    "id": pid,
                    "idx": {"timestamp": stamp, "value": idx},
                    "template": {"timestamp": stamp, "value": "Blank"},
                }
                for pid, idx in zip(page_ids, page_indices(len(page_ids)), strict=True)
            ],
            "uuids": [{"first": str(author_uuid), "second": 1}],
        },
        "coverPageNumber": -1,
        "customZoomCenterX": 0,
        "customZoomCenterY": device.height // 2,
        "customZoomOrientation": "portrait",
        "customZoomPageHeight": device.height,
        "customZoomPageWidth": device.width,
        "customZoomScale": 1,
        "documentMetadata": {},
        "extraMetadata": {
            "LastFinelinerv2Color": "Black",
            "LastFinelinerv2Size": "1",
            "LastPen": "Finelinerv2",
            "LastTool": "Finelinerv2",
        },
        "fileType": "notebook",
        "fontName": "",
        "formatVersion": 2,
        "lineHeight": -1,
        "margins": 125,
        "orientation": "portrait",
        "pageCount": len(page_ids),
        "pageTags": [],
        "sizeInBytes": str(size_bytes),
        "tags": [],
        "textAlignment": "justify",
        "textScale": 1,
        "zoomMode": "bestFit",
    }


def _metadata(name: str, now_ms: int) -> dict:
    return {
        "createdTime": str(now_ms),
        "lastModified": str(now_ms),
        "parent": "",
        "pinned": False,
        "type": "DocumentType",
        "visibleName": name,
    }


def size_warnings(size_bytes: int) -> list[str]:
    mb = size_bytes / 1_000_000
    if size_bytes > UPLOAD_LIMIT_BYTES:
        return [f"{mb:.1f} MB exceeds the 100 MB USB web interface limit; split the input."]
    if size_bytes > UPLOAD_LIMIT_BYTES - UPLOAD_WARN_MARGIN:
        return [f"{mb:.1f} MB is close to the 100 MB USB web interface limit."]
    return []


def write_rmdoc(
    path: Path,
    name: str,
    pages: list[RmdocPage],
    page_ids: list[str],
    author_uuid: uuid.UUID,
    device: DeviceProfile,
    doc_id: str,
    compress: bool = False,
    now_ms: int | None = None,
) -> RmdocResult:
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    payload_size = sum(len(p.rm_bytes) for p in pages)
    compression = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=compression) as zf:

        def add(arcname: str, data: bytes) -> None:
            # Fixed timestamp keeps archives byte-reproducible.
            info = zipfile.ZipInfo(arcname, date_time=(2024, 1, 1, 0, 0, 0))
            info.compress_type = compression
            zf.writestr(info, data)

        add(
            f"{doc_id}.content",
            json.dumps(_content(page_ids, author_uuid, device, payload_size), indent=4).encode(),
        )
        add(f"{doc_id}.metadata", json.dumps(_metadata(name, now_ms), indent=4).encode())
        for pid, page in zip(page_ids, pages, strict=True):
            add(f"{doc_id}/{pid}.rm", page.rm_bytes)
            add(
                f"{doc_id}/{pid}-metadata.json",
                json.dumps({"layers": [{"name": "Layer 1"}]}).encode(),
            )
            if page.thumbnail_png is not None:
                add(f"{doc_id}.thumbnails/{pid}.png", page.thumbnail_png)

    size = path.stat().st_size
    return RmdocResult(path=path, doc_id=doc_id, size_bytes=size, warnings=size_warnings(size))
