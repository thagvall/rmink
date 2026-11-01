"""Serialise a :class:`~rmink.model.Page` to a reMarkable v6 ``.rm`` file.

This module is the only place that touches rmscene's (experimental) writer API.
The block layout mirrors what firmware 3.x produces for a notebook page: author
ids, migration info, page info, scene info, the scene tree (root + one group per
layer, the first being "Layer 1" by default) and one ``SceneLineItemBlock`` per
stroke, linked as a CRDT sequence within its layer.
"""

from __future__ import annotations

import io
import math
from collections.abc import Iterator
from uuid import UUID

import numpy as np
from rmscene import scene_items as si
from rmscene.crdt_sequence import CrdtSequenceItem
from rmscene.scene_stream import (
    AuthorIdsBlock,
    Block,
    MigrationInfoBlock,
    PageInfoBlock,
    SceneGroupItemBlock,
    SceneInfo,
    SceneLineItemBlock,
    SceneTreeBlock,
    TreeNodeBlock,
    write_blocks,
)
from rmscene.tagged_block_common import CrdtId, LwwValue

from rmink.devices import DeviceProfile
from rmink.model import Page, Stroke

ROOT_ID = CrdtId(0, 1)
LAYER_ID = CrdtId(0, 11)
NULL_ID = CrdtId(0, 0)
FIRST_ITEM_COUNTER = 16

# Speed is not meaningful for converted ink; pressure is unless a stroke sets it.
_PRESSURE = 200
_SPEED = 100


def _line_points(strokes: list[Stroke], device: DeviceProfile) -> list[list[si.Point]]:
    """The v6 points of each stroke, computed for all strokes at once: shading
    makes tens of thousands of short strokes, and per-stroke numpy calls were
    most of the time of writing a page."""
    if not strokes:
        return []
    lens = np.array([len(s) for s in strokes])
    pts = np.concatenate([s.points for s in strokes]).astype(np.float64)
    xs = (pts[:, 0] - device.width / 2) * device.ink_scale
    ys = pts[:, 1] * device.ink_scale

    # Each point points to the next one; a stroke's last point repeats the
    # direction before it, and a single point has direction 0.
    ends = np.cumsum(lens) - 1
    d = np.diff(pts, axis=0, append=pts[-1:])
    angles = np.arctan2(d[:, 1], d[:, 0])
    angles[ends] = np.where(lens > 1, angles[np.maximum(ends - 1, 0)], 0.0)
    directions = np.round((angles % (2 * math.pi)) * 255 / (2 * math.pi)).astype(int) % 256

    widths = np.concatenate(
        [s.widths if s.widths is not None else np.full(len(s), s.width) for s in strokes]
    )
    # v2 points store width * 4 as uint16.
    widths_q = np.clip(np.round(widths * device.ink_scale * 4), 1, 65535).astype(int)
    pressures = np.concatenate(
        [
            np.clip(np.round(s.pressures), 0, 255).astype(int)
            if s.pressures is not None
            else np.full(len(s), _PRESSURE)
            for s in strokes
        ]
    )

    points = [
        si.Point(x=x, y=y, speed=_SPEED, direction=a, width=w, pressure=p)
        for x, y, a, w, p in zip(
            xs.tolist(),
            ys.tolist(),
            directions.tolist(),
            widths_q.tolist(),
            pressures.tolist(),
            strict=True,
        )
    ]
    starts = np.concatenate([[0], np.cumsum(lens)]).tolist()
    return [points[a:b] for a, b in zip(starts, starts[1:], strict=False)]


def _layer_ids(count: int, first_free: int) -> list[tuple[CrdtId, CrdtId, CrdtId]]:
    """(node, label, sequence item) ids per layer. The first layer uses the ids
    firmware gives "Layer 1"; later ones take counters after the strokes."""
    ids = [(LAYER_ID, CrdtId(0, 12), CrdtId(0, 13))]
    for i in range(count - 1):
        c = first_free + 3 * i
        ids.append((CrdtId(1, c), CrdtId(1, c + 1), CrdtId(1, c + 2)))
    return ids


def page_blocks(page: Page, device: DeviceProfile, author_uuid: UUID) -> Iterator[Block]:
    layers = page.layers
    by_layer = {name: [s for s in page.strokes if s.layer == name and len(s)] for name in layers}
    n_strokes = sum(len(v) for v in by_layer.values())
    ids = _layer_ids(len(layers), FIRST_ITEM_COUNTER + n_strokes)

    yield AuthorIdsBlock(author_uuids={1: author_uuid})
    yield MigrationInfoBlock(migration_id=CrdtId(1, 1), is_device=True)
    yield PageInfoBlock(loads_count=1, merges_count=0, text_chars_count=0, text_lines_count=0)
    yield SceneInfo(
        current_layer=LwwValue(NULL_ID, LAYER_ID),
        background_visible=LwwValue(NULL_ID, True),
        root_document_visible=LwwValue(NULL_ID, True),
        paper_size=device.paper_size,
    )
    for node, _, _ in ids:
        yield SceneTreeBlock(tree_id=node, node_id=NULL_ID, is_update=True, parent_id=ROOT_ID)
    yield TreeNodeBlock(si.Group(node_id=ROOT_ID))
    for name, (node, label, _) in zip(layers, ids, strict=True):
        visible = LwwValue(label, name not in page.hidden_layers)
        yield TreeNodeBlock(si.Group(node_id=node, label=LwwValue(label, name), visible=visible))
    left_layer = NULL_ID
    for node, _, seq in ids:
        yield SceneGroupItemBlock(
            parent_id=ROOT_ID,
            item=CrdtSequenceItem(
                item_id=seq,
                left_id=left_layer,
                right_id=NULL_ID,
                deleted_length=0,
                value=node,
            ),
        )
        left_layer = seq

    counter = FIRST_ITEM_COUNTER
    for name, (node, _, _) in zip(layers, ids, strict=True):
        left = NULL_ID
        strokes = by_layer[name]
        for stroke, points in zip(strokes, _line_points(strokes, device), strict=True):
            item_id = CrdtId(1, counter)
            line = si.Line(
                color=stroke.color,
                tool=stroke.pen,
                points=points,
                thickness_scale=1.0,
                starting_length=0.0,
                color_rgba=stroke.rgba,
            )
            yield SceneLineItemBlock(
                parent_id=node,
                item=CrdtSequenceItem(
                    item_id=item_id, left_id=left, right_id=NULL_ID, deleted_length=0, value=line
                ),
            )
            left = item_id
            counter += 1


def page_lines(page: Page, device: DeviceProfile) -> list[si.Line]:
    """The lines ``write_page`` would store, without serialising them."""
    return [
        b.item.value
        for b in page_blocks(page, device, UUID(int=0))
        if isinstance(b, SceneLineItemBlock)
    ]


def write_page(page: Page, device: DeviceProfile, author_uuid: UUID) -> bytes:
    buf = io.BytesIO()
    write_blocks(buf, page_blocks(page, device, author_uuid))
    return buf.getvalue()
