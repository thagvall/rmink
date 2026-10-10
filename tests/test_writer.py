import io
import json
import uuid
import zipfile

import numpy as np
from rmscene.scene_items import Pen, PenColor
from rmscene.scene_stream import AuthorIdsBlock, read_blocks, read_tree

from rmink.api import convert
from rmink.devices import get_device
from rmink.model import Page, Stroke
from rmink.options import ConvertOptions
from rmink.render.preview import read_lines
from rmink.writer.rm_v6 import write_page


def _page(device):
    t = np.linspace(0, 2 * np.pi, 60)
    return Page(
        device.width,
        device.height,
        [
            Stroke([[100, 100], [500, 100], [500, 500]], width=3),
            Stroke(np.c_[800 + 100 * np.cos(t), 400 + 100 * np.sin(t)], color=PenColor.BLUE),
            Stroke([[50, 1000], [60, 1010]], pen=Pen.MARKER_2, widths=[4, 8]),
        ],
    )


def test_round_trip_preserves_strokes():
    device = get_device("rm2")
    page = _page(device)
    author = uuid.uuid4()
    data = write_page(page, device, author)
    assert data.startswith(b"reMarkable .lines file, version=6")

    lines = read_lines(data)
    assert len(lines) == 3
    assert [ln.tool for ln in lines] == [Pen.FINELINER_2, Pen.FINELINER_2, Pen.MARKER_2]
    assert lines[1].color == PenColor.BLUE
    # x is stored relative to the page centre.
    p0 = lines[0].points[0]
    assert abs(p0.x - (100 - device.width / 2)) < 1e-3 and abs(p0.y - 100) < 1e-3
    assert [p.width for p in lines[2].points] == [16, 32]

    tree = read_tree(io.BytesIO(data))
    assert len(list(tree.walk())) == 3
    authors = [b for b in read_blocks(io.BytesIO(data)) if isinstance(b, AuthorIdsBlock)]
    assert authors[0].author_uuids[1] == author


def test_rmdoc_structure_and_author_match(examples, tmp_path):
    out = tmp_path / "doc.rmdoc"
    result = convert([examples["svg"], examples["pdf"]], out, ConvertOptions(seed=1))
    assert result.path == out and len(result.pages) == 3
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        content_name = next(n for n in names if n.endswith(".content"))
        doc_id = content_name.removesuffix(".content")
        content = json.loads(zf.read(content_name))
        pages = content["cPages"]["pages"]
        assert content["pageCount"] == len(pages) == 3
        assert [p["idx"]["value"] for p in pages] == ["ba", "bb", "bc"]
        author = content["cPages"]["uuids"][0]["first"]
        for p in pages:
            data = zf.read(f"{doc_id}/{p['id']}.rm")
            block = next(b for b in read_blocks(io.BytesIO(data)) if isinstance(b, AuthorIdsBlock))
            assert str(block.author_uuids[1]) == author
            assert f"{doc_id}.thumbnails/{p['id']}.png" in names
        assert int(content["sizeInBytes"]) > 0
        meta = json.loads(zf.read(f"{doc_id}.metadata"))
        assert meta["visibleName"] == "logo" and meta["type"] == "DocumentType"


def test_seeded_output_is_reproducible(examples, tmp_path):
    a, b = tmp_path / "a.rmdoc", tmp_path / "b.rmdoc"
    convert([examples["svg"]], a, ConvertOptions(seed=7))
    convert([examples["svg"]], b, ConvertOptions(seed=7))
    assert a.read_bytes() == b.read_bytes()
