"""Serialise a :class:`~rmink.model.Page` to a reMarkable v6 ``.rm`` file.

This module is the only place that touches rmscene's (experimental) writer API.
The block layout mirrors what firmware 3.x produces for a notebook page with a
single layer: author ids, migration info, page info, scene info, the scene tree
(root + "Layer 1") and one ``SceneLineItemBlock`` per stroke, linked as a CRDT
sequence.
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


def _line_points(stroke: Stroke, device: DeviceProfile) -> list[si.Point]:
    pts = stroke.points.astype(np.float64)
    xs = (pts[:, 0] - device.width / 2) * device.ink_scale
    ys = pts[:, 1] * device.ink_scale

    if len(pts) > 1:
        d = np.diff(pts, axis=0)
        angles = np.arctan2(d[:, 1], d[:, 0])
        angles = np.append(angles, angles[-1])
    else:
        angles = np.zeros(1)
    directions = np.round((angles % (2 * math.pi)) * 255 / (2 * math.pi)).astype(int) % 256

    widths = stroke.widths if stroke.widths is not None else np.full(len(pts), stroke.width)
    # v2 points store width * 4 as uint16.
    widths_q = np.clip(np.round(widths * device.ink_scale * 4), 1, 65535).astype(int)
    pressures = (
        np.clip(np.round(stroke.pressures), 0, 255).astype(int)
        if stroke.pressures is not None
        else np.full(len(pts), _PRESSURE)
    )

    return [
        si.Point(
            x=float(x), y=float(y), speed=_SPEED, direction=int(a), width=int(w), pressure=int(p)
        )
        for x, y, a, w, p in zip(xs, ys, directions, widths_q, pressures, strict=True)
    ]


def page_blocks(page: Page, device: DeviceProfile, author_uuid: UUID) -> Iterator[Block]:
    yield AuthorIdsBlock(author_uuids={1: author_uuid})
    yield MigrationInfoBlock(migration_id=CrdtId(1, 1), is_device=True)
    yield PageInfoBlock(loads_count=1, merges_count=0, text_chars_count=0, text_lines_count=0)
    yield SceneInfo(
        current_layer=LwwValue(NULL_ID, LAYER_ID),
        background_visible=LwwValue(NULL_ID, True),
        root_document_visible=LwwValue(NULL_ID, True),
        paper_size=device.paper_size,
    )
    yield SceneTreeBlock(tree_id=LAYER_ID, node_id=NULL_ID, is_update=True, parent_id=ROOT_ID)
    yield TreeNodeBlock(si.Group(node_id=ROOT_ID))
    yield TreeNodeBlock(si.Group(node_id=LAYER_ID, label=LwwValue(CrdtId(0, 12), "Layer 1")))
    yield SceneGroupItemBlock(
        parent_id=ROOT_ID,
        item=CrdtSequenceItem(
            item_id=CrdtId(0, 13),
            left_id=NULL_ID,
            right_id=NULL_ID,
            deleted_length=0,
            value=LAYER_ID,
        ),
    )

    left = NULL_ID
    counter = FIRST_ITEM_COUNTER
    for stroke in page.strokes:
        if len(stroke) == 0:
            continue
        item_id = CrdtId(1, counter)
        line = si.Line(
            color=stroke.color,
            tool=stroke.pen,
            points=_line_points(stroke, device),
            thickness_scale=1.0,
            starting_length=0.0,
            color_rgba=stroke.rgba,
        )
        yield SceneLineItemBlock(
            parent_id=LAYER_ID,
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
