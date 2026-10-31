"""Write a workbook revision and put it on the tablet.

Workbooks live beside the drawings, in a folder of their own:

   rmink/
     Bråk/
       Bråk r02 · 1 att kolla   the revision to write in
       Tidigare/                earlier revisions, oldest first
     Skola/
       Bråk och division/       a group of workbooks (rmink.workbook.catalog)
         Bråk åk 5/
           Bråk åk 5 r01

Each revision is the PDF rebuilt with the answers read so far, plus ink:
- handwriting a round has read goes to the hidden "Handskrift" layer with
  ``ink="keep"``, or is dropped with ``ink="remove"`` (the default);
- handwriting kept by an earlier round stays on that layer either way;
- ink outside the boxes, and in boxes Claude could not read, stays as it was.

The solutions go on the hidden "Facit" layer when the workbook shows them
(a choice question's once it is done).
"""

from __future__ import annotations

import dataclasses
import logging
import tempfile
from pathlib import Path
from typing import Literal

import pymupdf

from rmink import cloud
from rmink.devices import DeviceProfile, get_device
from rmink.drawing.store import WORKBOOK_LINK, Store
from rmink.drawing.workflow import (
    _GLOB,
    ARCHIVE,
    RMINK_FOLDER,
    _move_into,
    drawing_folder,
    safe_name,
)
from rmink.model import Page, Stroke
from rmink.package.rmdoc import RmdocPage, UuidFactory, write_rmdoc
from rmink.workbook.build import FACIT_LAYER, build_pdf, solution_strokes
from rmink.workbook.model import LAYOUT, Workbook
from rmink.workbook.read import HANDWRITING_LAYER, Sorted
from rmink.writer.rm_v6 import write_page

log = logging.getLogger(__name__)

InkMode = Literal["remove", "keep"]


def revision_title(workbook: Workbook) -> str:
    """'Bråk r02 · 3 av 4 p · 1 att kolla': the score once graded, and the
    answers rmink was unsure of."""
    title = f"{safe_name(workbook.name)} r{workbook.revision:02d}"
    got, total = workbook.score()
    if workbook.graded() and total:
        title += f" · {got:g} av {total} p"
    if n := len(workbook.unsure()):
        title += f" · {n} att kolla"
    return title


def workbook_folder(workbook: Workbook) -> str:
    """'/rmink/Skola/Bråk och division/Bråk åk 5' for a workbook in a group,
    '/rmink/Bråk' for one without."""
    if not workbook.group:
        return drawing_folder(workbook.name)
    parts = [workbook.area, workbook.group, workbook.name]
    return "/".join([RMINK_FOLDER, *(safe_name(p) for p in parts if p)])


def _make_folders(token: str, folder: str) -> list[cloud.Entry]:
    """The entries of ``folder``, made with the folders above it if missing."""
    try:
        return cloud.ls(token, folder)
    except cloud.CloudNotFoundError:
        pass
    path = ""
    for part in folder.strip("/").split("/"):
        path += "/" + part
        cloud.mkdir(token, path)  # a folder that is there counts as made
    return []


def _on(strokes: list[Stroke], layer: str) -> list[Stroke]:
    return [dataclasses.replace(s, layer=layer) for s in strokes]


def build_revision(
    workbook: Workbook,
    output: Path,
    device: DeviceProfile,
    ink: Sorted | None = None,
    read: set[str] = frozenset(),
    mode: InkMode = "remove",
    seed: int | None = None,
) -> Path:
    """Write the revision as a PDF ``.rmdoc``. ``read`` holds the ids of the
    fields whose ink this round transcribed; ink in other fields stays visible."""
    ink = ink or Sorted()
    pdf = build_pdf(workbook, device)
    count = pymupdf.open(stream=pdf).page_count
    facit = solution_strokes(workbook, device)
    visible: dict[int, list[Stroke]] = {p: list(s) for p, s in ink.loose.items()}
    hidden: dict[int, list[Stroke]] = {p: list(s) for p, s in ink.kept.items()}
    for field_id, strokes in ink.by_field.items():
        f = workbook.field(field_id)
        if f is None or f.page < 0:
            continue
        if field_id not in read:
            visible.setdefault(f.page, []).extend(strokes)
        elif mode == "keep":
            hidden.setdefault(f.page, []).extend(strokes)

    uuids = UuidFactory(seed)
    author = uuids()
    pages = []
    for n in range(count):
        strokes = _on(visible.get(n, []), "Layer 1") + _on(hidden.get(n, []), HANDWRITING_LAYER)
        strokes += facit.get(n, [])
        if not strokes:
            pages.append(RmdocPage(b""))
            continue
        page = Page(device.width, device.height, strokes, ["Layer 1"])
        page.hidden_layers = {HANDWRITING_LAYER, FACIT_LAYER}
        pages.append(RmdocPage(write_page(page, device, author), None, page.layers))

    output = Path(output)
    write_rmdoc(
        output.with_suffix(".rmdoc"),
        revision_title(workbook),
        pages,
        [str(uuids()) for _ in pages],
        author,
        device,
        str(uuids()),
        now_ms=0 if seed is not None else None,
        pdf=pdf,
    )
    return output.with_suffix(".rmdoc")


def send_revision(workbook: Workbook, path: Path, token: str, store: Store) -> str:
    """Upload a revision to the workbook's folder, save the workbook with where
    it went and move the notebook this round read into ``Tidigare``. Returns
    the cloud path."""
    folder = workbook_folder(workbook)
    entries = _make_folders(token, folder)
    sent_as = f"{folder}/{cloud.put(path, token, folder=folder, name=revision_title(workbook))}"
    read = workbook.document
    workbook.sent_as = sent_as
    store.save_workbook(workbook)
    store.link(sent_as, WORKBOOK_LINK + workbook.name)

    parent, _, base = read.rpartition("/")
    if read and parent == folder and not _GLOB.search(read):
        archive = f"{folder}/{ARCHIVE}"
        try:
            if not any(e.folder and e.name == ARCHIVE for e in entries):
                cloud.mkdir(token, archive)
            moved = _move_into(token, read, archive, base)
            store.link(moved, WORKBOOK_LINK + workbook.name)
        except cloud.CloudError as e:
            log.warning("Could not move %s to %s: %s", read, archive, e)
    return sent_as


def move_to_group(workbook: Workbook, area: str, group: str, token: str, store: Store) -> str:
    """Move a workbook's folder, with its revisions and Tidigare, into
    rmink/<area>/<group>/ and save it with its new paths. Returns the new
    folder; a folder already there is left alone (CloudExistsError)."""
    old = workbook_folder(workbook)
    moved = workbook.model_copy(update={"area": area, "group": group})
    new = workbook_folder(moved)
    if old == new:
        return new
    _make_folders(token, new.rpartition("/")[0])
    cloud.mv(token, old, new)

    def renamed(path: str) -> str:
        return new + path[len(old) :] if path.startswith(old + "/") else path

    moved.sent_as, moved.document = renamed(workbook.sent_as), renamed(workbook.document)
    moved.log.append(f"r{moved.revision:02d}: flyttad till {new.removeprefix(RMINK_FOLDER + '/')}")
    store.save_workbook(moved)
    link = WORKBOOK_LINK + moved.name
    for e in cloud.ls(token, new):
        if e.folder and e.name == ARCHIVE:
            for old_rev in cloud.ls(token, f"{new}/{ARCHIVE}"):
                store.link(f"{new}/{ARCHIVE}/{old_rev.name}", link)
        elif not e.folder:
            store.link(f"{new}/{e.name}", link)
    return new


def relayout(workbook: Workbook, token: str, store: Store) -> str:
    """Send the workbook again in the current layout (:data:`LAYOUT`) as its
    next revision, with the answers so far; the current one moves to
    Tidigare. Run it when the current revision has no unread ink: ink drawn
    for the old boxes, also the hidden "Handskrift" layer, stays behind in
    Tidigare. Returns the cloud path."""
    wb = workbook.model_copy(deep=True)
    wb.layout = LAYOUT
    wb.revision += 1
    wb.document = wb.sent_as  # moves to Tidigare like a revision a round read
    wb.log.append(f"r{wb.revision:02d}: ny layout med större svarsrutor")
    with tempfile.TemporaryDirectory() as tmp:
        path = build_revision(wb, Path(tmp) / "wb.rmdoc", get_device(wb.device))
        return send_revision(wb, path, token, store)
