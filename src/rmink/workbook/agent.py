"""Claude's two jobs for a workbook, through the API.

:func:`create_workbook` has Claude write a workbook on a topic and sends the
first revision to the tablet. :func:`run_round` reads what the user wrote in
the answer boxes since the last revision, sends Claude a picture of each box
with new ink, and writes the next revision with the transcribed answers set in
the PDF. Each is one tool call; a call that does not validate is sent back
with the error, a few times at most.
"""

from __future__ import annotations

import datetime
import json
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from rmink import cloud
from rmink.devices import DeviceProfile, get_device
from rmink.drawing.agent import (
    FALLBACK_BETA,
    MODEL,
    PRICE_CACHE_READ,
    PRICE_IN,
    PRICE_OUT,
    RoundError,
    RoundResult,
    _image_block,
)
from rmink.drawing.store import WORKBOOK_LINK, Store, guess_drawing_name
from rmink.workbook import workflow
from rmink.workbook.build import build_pdf
from rmink.workbook.model import AnswerField, Workbook
from rmink.workbook.read import Ink, Sorted, field_png, read_ink, sort_ink

CREATE_PROMPT = """\
You write a workbook for a reMarkable tablet: a PDF with a table of contents \
and linked sections, where the reader writes answers by hand in ruled boxes. \
A later round reads the handwriting and sets it as text in the boxes.

Write it in the language of the request (Swedish unless the request says \
otherwise). Teach, then practise: each section opens with a short explanation \
(at most about 120 words, plain text, no Markdown) and has 1 to 5 fields. A \
field is one question or task; "lines" is how many ruled lines its answer \
needs (1 for a number, 3-6 for an explanation). Use 3 to 8 sections that build \
on each other. Use plain characters: write 3/4, x^2, sqrt(2), and avoid \
symbols outside Latin-1 such as arrows or Greek letters. Give "name" as a short \
folder name (1-3 words). Ids are short and unique: s1, s2 for sections and \
s1f1, s1f2 for fields.

Call write_workbook once with the whole workbook."""

TRANSCRIBE_PROMPT = """\
You read handwriting from a reMarkable tablet. Each picture is one answer box \
of a workbook, with the question it answers and, if the box was answered in an \
earlier round, that answer.

Transcribe what the reader wrote, exactly: do not correct spelling, grammar or \
mathematics, since the answer is theirs to check. Keep line breaks. Write \
mathematics in plain text (3/4, x^2, sqrt(2)). Leave out crossed-out writing. \
When the box already has an answer, the picture shows only the new ink: \
return the whole new answer, the old one with the additions or corrections \
the new ink makes. A tick (a check mark) on its own in an answered box means \
the reader confirms the earlier answer: return it unchanged with confident \
true. Set confident to false when any word or figure is a guess. Return an \
empty text for a box with nothing legible (a stray mark).

Call save_answers once with an entry for every box."""

FIELD_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "prompt": {"type": "string"},
        "lines": {"type": "integer", "minimum": 1, "maximum": 12},
    },
    "required": ["id", "prompt", "lines"],
}
CREATE_TOOL = {
    "name": "write_workbook",
    "description": "Save the workbook; rmink lays it out as a PDF and sends it to the tablet.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "title": {"type": "string"},
            "intro": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "text": {"type": "string"},
                        "fields": {"type": "array", "items": FIELD_SCHEMA},
                    },
                    "required": ["id", "title", "text", "fields"],
                },
            },
        },
        "required": ["name", "title", "intro", "sections"],
    },
}
ANSWERS_TOOL = {
    "name": "save_answers",
    "description": "Save the transcribed answers, one entry per box.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "text": {"type": "string"},
                        "confident": {"type": "boolean"},
                    },
                    "required": ["id", "text", "confident"],
                },
            }
        },
        "required": ["answers"],
    },
}


def _call(client, system: str, tool: dict, content: list[dict], check, effort: str | None):
    """Ask Claude for one call of ``tool`` and return ``check(input)``; a
    ``ValueError`` from ``check`` goes back to Claude to fix. Returns the
    result and the token usage."""
    usage = dict.fromkeys(
        ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"),
        0,
    )
    messages: list[dict] = [{"role": "user", "content": content}]
    for _ in range(3):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=system,
            tools=[tool],
            messages=messages,
            output_config={"effort": effort or os.environ.get("RMINK_ROUND_EFFORT", "medium")},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            response = stream.get_final_message()
        for key in usage:
            usage[key] += getattr(response.usage, key, 0) or 0
        if response.stop_reason == "refusal":
            raise RoundError("Claude avböjde.")
        if response.stop_reason == "max_tokens":
            raise RoundError("Svaret blev för långt; försök igen.")
        messages.append({"role": "assistant", "content": response.content})
        calls = [b for b in response.content if b.type == "tool_use" and b.name == tool["name"]]
        if not calls:
            messages.append({"role": "user", "content": f"Call {tool['name']} now."})
            continue
        try:
            return check(calls[0].input if isinstance(calls[0].input, dict) else {}), usage
        except ValueError as e:
            error = f"Not valid: {e}"[:2000]
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": calls[0].id,
                            "content": error,
                            "is_error": True,
                        }
                    ],
                }
            )
    raise RoundError("Claude gav inget giltigt svar; försök igen.")


def _cost(usage: dict) -> dict:
    usd = (
        usage["input_tokens"] * PRICE_IN
        + usage["cache_creation_input_tokens"] * PRICE_IN * 1.25
        + usage["cache_read_input_tokens"] * PRICE_CACHE_READ
        + usage["output_tokens"] * PRICE_OUT
    ) / 1e6
    return usage | {"usd": round(usd, 3)}


def _preview(workbook: Workbook, page: int = 0) -> bytes:
    import pymupdf

    doc = pymupdf.open(stream=build_pdf(workbook, get_device(workbook.device)))
    return doc[min(page, doc.page_count - 1)].get_pixmap(dpi=80).tobytes("png")


def _write(
    wb: Workbook,
    device: DeviceProfile,
    store: Store,
    send: bool,
    output: Path | None,
    marks: Sorted | None = None,
    read: set[str] = frozenset(),
    ink: workflow.InkMode = "remove",
) -> str | None:
    """Write the revision (to ``output``, if given), save the workbook and
    send the revision if asked; returns where it was sent."""
    with tempfile.TemporaryDirectory() as tmp:
        path = workflow.build_revision(
            wb, output or Path(tmp) / "wb.rmdoc", device, marks, read, ink
        )
        if not send:
            store.save_workbook(wb)
            return None
        token = cloud.load_token()
        if not token:
            raise RoundError("rmink är inte kopplat till reMarkable Cloud")
        return workflow.send_revision(wb, path, token, store)


def check_workbook(args: dict) -> Workbook:
    """A workbook from Claude's JSON; ``ValueError`` says what to fix."""
    try:
        wb = Workbook.model_validate(args)
    except Exception as e:  # pydantic ValidationError
        raise ValueError(str(e)) from e
    if not wb.sections or not wb.fields():
        raise ValueError("The workbook needs sections with fields.")
    ids = [f.id for f in wb.fields()]
    if len(ids) != len(set(ids)):
        raise ValueError("Field ids must be unique.")
    return wb


def start_workbook(
    wb: Workbook,
    device_key: str,
    store: Store,
    send: bool = True,
    started: float | None = None,
    output: Path | None = None,
) -> RoundResult:
    """Write revision 1 of a new workbook, save it and send it to
    rmink/<name>/ on the tablet."""
    started = time.monotonic() if started is None else started
    if store.load_workbook(wb.name) is not None:
        raise RoundError(
            f'Det finns redan en arbetsbok som heter "{wb.name}"; välj ett annat namn.'
        )
    device = get_device(device_key)
    wb.revision = 1
    wb.device = device.key
    wb.date = datetime.date.today().isoformat()
    wb.log.append(f"r01 {wb.date}: skapad, {len(wb.sections)} avsnitt, {len(wb.fields())} frågor")
    sent_as = _write(wb, device, store, send, output)
    return RoundResult(
        sent_as=sent_as,
        drawing=wb.name,
        revision=1,
        summary=f"{wb.title}: {len(wb.sections)} avsnitt och {len(wb.fields())} frågor.",
        open_questions=[],
        preview_png=_preview(wb),
        seconds=time.monotonic() - started,
    )


def create_workbook(
    topic: str,
    device_key: str,
    store: Store,
    client=None,
    name: str | None = None,
    effort: str | None = None,
    send: bool = True,
) -> RoundResult:
    """Have Claude write a workbook on ``topic`` and send revision 1."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    started = time.monotonic()
    request = topic.strip() + (f'\n\nName the workbook "{name}".' if name else "")
    wb, usage = _call(
        client,
        CREATE_PROMPT,
        CREATE_TOOL,
        [{"type": "text", "text": request}],
        check_workbook,
        effort,
    )
    if name:
        wb.name = name
    result = start_workbook(wb, device_key, store, send, started)
    result.usage = _cost(usage)
    return result


def find_workbook(document: str, store: Store) -> Workbook | None:
    """The saved workbook ``document`` (a cloud path, local file or workbook
    name) belongs to, if any."""
    linked = store.linked(document) or ""
    if linked.startswith(WORKBOOK_LINK):
        return store.load_workbook(linked.removeprefix(WORKBOOK_LINK))
    if linked:
        return None  # a drawing's notebook
    return store.load_workbook(guess_drawing_name(document))


@dataclass
class OpenRound:
    """A workbook revision as the tablet synced it, its new ink sorted into boxes."""

    workbook: Workbook
    document: str  # the cloud path read, or "" for a local file
    device: DeviceProfile
    ink: Ink
    marks: Sorted

    def boxes(self) -> list[tuple[AnswerField, str, bytes]]:
        """Each box with new ink: the field, what Claude needs to know about it
        and a picture of it."""
        out = []
        for field_id, strokes in self.marks.by_field.items():
            f = self.workbook.field(field_id)
            section = next(s for s in self.workbook.sections if f in s.fields)
            text = f'Box {f.id}, section "{section.title}". Question: {f.prompt}'
            if f.answer:
                text += f"\nEarlier answer: {json.dumps(f.answer, ensure_ascii=False)}"
            out.append((f, text, field_png(self.ink.pdf, f, strokes, self.device)))
        return out

    def check(self, args: dict) -> dict[str, dict]:
        """``{"answers": [{id, text, confident}]}`` as answers by box id; one
        entry per box with new ink."""
        answers = {}
        for a in args.get("answers") or []:
            if not isinstance(a, dict) or a.get("id") not in self.marks.by_field:
                raise ValueError(f"Unknown box {a!r}; the boxes are {list(self.marks.by_field)}.")
            answers[a["id"]] = {
                "text": str(a.get("text") or "").strip(),
                "confident": bool(a.get("confident", True)),
            }
        if missing := set(self.marks.by_field) - set(answers):
            raise ValueError(f"No entry for {sorted(missing)}.")
        return answers


def open_round(document: str, device_key: str | None, store: Store) -> OpenRound:
    """Fetch ``document`` (a cloud path, a local .rmdoc or a workbook name:
    its latest revision) and sort the ink written since rmink wrote it."""
    wb = find_workbook(document, store)
    if wb is None:
        raise RoundError(f'Ingen sparad arbetsbok för "{document}".')
    local = Path(document).expanduser()
    if local.is_file():
        data, document = local.read_bytes(), ""
    else:
        if "/" not in document and wb.sent_as:
            document = wb.sent_as
        document = document if document.startswith("/") else "/" + document
        token = cloud.load_token()
        if not token:
            raise RoundError("rmink är inte kopplat till reMarkable Cloud")
        data = cloud.get(token, document)
    device = get_device(device_key or wb.device)
    try:
        written = read_ink(data, device)
    except ValueError as e:
        raise RoundError(f'"{document or local.name}" är ingen arbetsbok från rmink.') from e
    build_pdf(wb, device)  # sets the field boxes, also for workbooks saved without them
    marks = sort_ink(written, wb, device)
    if not marks.by_field:
        raise RoundError(
            "Inget nytt i svarsrutorna sedan förra revisionen. Har plattan hunnit synka?"
        )
    return OpenRound(wb, document, device, written, marks)


def finish_round(
    r: OpenRound,
    answers: dict[str, dict],
    store: Store,
    ink: workflow.InkMode = "remove",
    send: bool = True,
    started: float | None = None,
    output: Path | None = None,
) -> RoundResult:
    """Set the answers (from :meth:`OpenRound.check`) and send the next revision."""
    started = time.monotonic() if started is None else started
    wb = r.workbook
    read = set()
    for field_id, a in answers.items():
        if a["text"]:
            f = wb.field(field_id)
            f.answer, f.confident = a["text"], a["confident"]
            read.add(field_id)

    wb.revision += 1
    wb.date = datetime.date.today().isoformat()
    wb.document = r.document
    wb.device = r.device.key
    unsure = len([f for f in wb.unsure() if f.id in read])
    note = f"r{wb.revision:02d} {wb.date}: {len(read)} svar lästa" + (
        f", {unsure} osäkra" if unsure else ""
    )
    if unread := len(r.marks.by_field) - len(read):
        note += f", {unread} gick inte att läsa"
    if r.ink.added_pages:
        note += f", {r.ink.added_pages} egna sidor kom inte med"
    wb.log.append(note)
    sent_as = _write(wb, r.device, store, send, output, r.marks, read, ink)
    first = min((wb.field(i).page for i in read), default=0)
    return RoundResult(
        sent_as=sent_as,
        drawing=wb.name,
        revision=wb.revision,
        summary=note.split(": ", 1)[1].capitalize() + ".",
        open_questions=[f"{f.prompt} → {f.answer}" for f in wb.unsure() if f.id in read],
        preview_png=_preview(wb, first),
        seconds=time.monotonic() - started,
    )


def run_round(
    document: str,
    device_key: str | None,
    store: Store,
    ink: workflow.InkMode = "remove",
    client=None,
    effort: str | None = None,
    send: bool = True,
) -> RoundResult:
    """Have Claude read the answers written in ``document`` and send the next
    revision."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    started = time.monotonic()
    r = open_round(document, device_key, store)
    content: list[dict] = []
    for _, text, png in r.boxes():
        content += [{"type": "text", "text": text}, _image_block(png)]
    answers, usage = _call(client, TRANSCRIBE_PROMPT, ANSWERS_TOOL, content, r.check, effort)
    result = finish_round(r, answers, store, ink, send, started)
    result.usage = _cost(usage)
    return result
