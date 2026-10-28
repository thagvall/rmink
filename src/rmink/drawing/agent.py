"""One revision round, run by Claude through the API.

The round reads the notebook from the reMarkable Cloud before calling Claude:
the saved drawing (if any), the stroke groups and a picture of the page with
the groups numbered. On the first round the groups are the whole sketch; on
later rounds only the strokes the user added since rmink wrote the page.
Claude then has three tools: ``render_preview`` to check a drawing,
``lookup_knowledge`` for building terms, materials and rules (rmink.knowledge),
and ``save_revision`` to write the next revision and send it to the tablet.

The loop is written out (not the SDK's beta tool runner) because the tools
return pictures, and it keeps every assistant turn unchanged as the API
requires for thinking blocks.
"""

from __future__ import annotations

import base64
import datetime
import io
import json
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from rmink import cloud, knowledge
from rmink.devices import get_device
from rmink.drawing import workflow
from rmink.drawing.model import Drawing
from rmink.drawing.render import render_drawing
from rmink.drawing.store import Store, guess_drawing_name
from rmink.drawing.symbols import SYMBOLS
from rmink.render.preview import render_lines
from rmink.writer.rm_v6 import page_lines

MODEL = "claude-opus-5-5"
# Per million tokens, for the cost shown after a round.
PRICE_IN, PRICE_OUT, PRICE_CACHE_READ = 4.0, 20.0, 0.2
FALLBACK_BETA = "server-side-fallback-2026-07-01"

ROUND_PROMPT = """\
You run one revision round of a hand-drawn 2D drawing for a user of a \
reMarkable tablet. rmink, the tool you work through, reads the user's pen \
strokes, fits lines and circles to them and draws your Drawing model back to \
the tablet as clean, editable pen strokes. The user marks up each revision \
with the pen and asks for the next round.

What you get:
- The saved Drawing (JSON) from the previous revision, or none on the first round.
- A picture of the page with stroke groups boxed and numbered, and the groups \
as JSON. On the first round the groups are the whole sketch. On later rounds \
they are only the strokes the user added since rmink wrote the page; rmink's \
own strokes are shown faded for context.
- The Drawing format, symbols and categories below.

How to work:
1. Decide what each group is. Long strokes come with fitted geometry: reuse \
those coordinates, never estimate coordinates from the picture. Groups of shape \
"mark" are handwriting, arrowheads or small symbols: read them from the picture.
2. On the first round, build the Drawing from the sketch: elements, dimensions \
(the written number and the line it measures), symbols, the legend if the \
sketch has one. Set revision 1.
3. On later rounds, classify each mark: a change (crossed out, redrawn, a new \
measurement), a question or remark, an answer to an open annotation, or a \
request for a detail view. Open annotations are numbered rings on the drawing \
and listed under ANMÄRKNINGAR below it, each with an answer line ("SVAR:"); \
writing on or just under the answer line of remark N, or next to ring N, \
answers remark N (the message lists which annotation each number is). Apply \
clear changes. Keep questions as annotations with status "open". When the user \
answered an open annotation, apply the answer and set it "accepted" or \
"rejected". Add one short line per change to `log`, prefixed with the new \
revision ("r3: ...").
4. When something is unclear, do not guess: add an open annotation on the \
element with a short question. The user answers on paper next round.
5. Call render_preview with the full Drawing to see it and the measurement \
check. Fix what is off (a measurement that disagrees with the others is often \
a misread number; ask about it if you cannot tell).
6. Call save_revision once with the final Drawing and a two-sentence summary \
for the user. Then stop.

Building knowledge: the reference below lists Swedish terms, abbreviations, \
materials with their quality classes, typical assemblies and review rules. Use \
it to read the sketch the way a builder would: "gips 13" is gypsum board type A \
12,5 mm, "C24" a strength class. Write material texts the way the reference's \
examples do. When a material lacks a class the reference says it must state \
(strength class, NTR class, exposure class), ask in an open annotation instead \
of guessing. Call lookup_knowledge for the exact values and legal source of a \
rule before citing it; raise a rule as an open annotation only when the \
drawing shows the situation it covers, at most a few per round, the most \
important first. Read handwritten symbols with the reference's symbol list: \
use the matching kind, put the text written next to it (+0,00, A, 10x21, \
1:50) in the symbol's label, and ask when a mark could be two symbols.

Write annotation texts, log lines and the summary in the user's language: \
Swedish when the sketch is in Swedish. Keep coordinates in page pixels.
"""


@dataclass
class RoundResult:
    sent_as: str | None
    drawing: str
    revision: int
    summary: str
    open_questions: list[str]
    preview_png: bytes | None
    seconds: float
    usage: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "sent_as": self.sent_as,
            "drawing": self.drawing,
            "revision": self.revision,
            "summary": self.summary,
            "open_questions": self.open_questions,
            "preview_png": base64.b64encode(self.preview_png).decode()
            if self.preview_png
            else None,
            "seconds": round(self.seconds, 1),
            "usage": self.usage,
        }


class RoundError(Exception):
    """The round could not finish; the message is safe to show the user."""


def _reference() -> str:
    return json.dumps(
        {
            "schema": Drawing.model_json_schema(),
            "symbols": {k: v[0] for k, v in SYMBOLS.items()},
            "categories": [c.model_dump() for c in Drawing(name="x").categories],
        }
    )


def _image_block(png: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(png).decode(),
        },
    }


def _png(img, max_side: int = 1100) -> bytes:
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def _resolve(document: str, store: Store) -> str:
    """A bare drawing name ("Altan") means the notebook its last revision was
    sent as; a cloud path gets its leading slash."""
    if Path(document).expanduser().is_file():
        return document
    if "/" not in document and (saved := store.load(document)) and saved.sketch.sent_as:
        return saved.sketch.sent_as
    return document if document.startswith("/") else "/" + document


TOOLS = [
    {
        "name": "render_preview",
        "description": "Render a Drawing as it will look on the tablet. Returns the picture and a "
        "measurement check: the common scale and dimensions that disagree with it.",
        "input_schema": {
            "type": "object",
            "properties": {"drawing": {"type": "object", "description": "The full Drawing JSON."}},
            "required": ["drawing"],
        },
        "eager_input_streaming": True,
    },
    {
        "name": "save_revision",
        "description": "Write the Drawing as the next revision, send it to the user's tablet and "
        "save it for the next round. Call once, at the end.",
        "input_schema": {
            "type": "object",
            "properties": {
                "drawing": {"type": "object", "description": "The full, final Drawing JSON."},
                "summary": {"type": "string", "description": "Two sentences for the user."},
            },
            "required": ["drawing", "summary"],
        },
        "eager_input_streaming": True,
    },
    {
        "name": "lookup_knowledge",
        "description": "Look up Swedish building knowledge: a term, abbreviation or handwritten "
        "variant ('gips 13', 'imp', 'ÖK'), a material, an assembly code (YV1), a rule id or a "
        "permit question. Returns full entries with classes, layers, exact values and sources.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "kind": {"type": "string", "enum": list(knowledge.KINDS)},
            },
            "required": ["query"],
        },
    },
]


def run_round(
    document: str,
    device_key: str,
    store: Store,
    client=None,
    effort: str | None = None,
    send: bool = True,
) -> RoundResult:
    """Run one round on ``document``: a cloud path like "/rmink/Altan/Altan r02",
    a local .rmdoc, or the name of a saved drawing, which means the notebook
    its last revision was sent as. ``client`` is an ``anthropic.Anthropic``;
    tests pass a fake."""
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    started = time.monotonic()
    device = get_device(device_key)
    document = _resolve(document, store)
    name = store.linked(document) or guess_drawing_name(document)
    previous = store.load(name)

    sketch = workflow.read_sketch(document, 1, device, previous)
    if previous is not None and not sketch.groups:
        raise RoundError("Inga nya markeringar sedan förra revisionen. Har plattan hunnit synka?")

    if previous is None:
        intro = f'First round. Notebook "{document}". Name the drawing "{name}".'
        saved = "none"
    else:
        intro = (
            f'Round {previous.revision + 1} of "{previous.name}". Notebook "{document}". '
            "The groups are only the user's new marks."
        )
        remarks = [a for a in previous.annotations if a.status == "open"]
        if remarks:
            intro += "\nOpen remarks on the page: " + "; ".join(
                f"{n} = {a.id} {json.dumps(a.text, ensure_ascii=False)}"
                for n, a in enumerate(remarks, 1)
            )
        saved = previous.model_dump_json()
    messages: list[dict] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"{intro}\n\nSaved Drawing:\n{saved}"},
                _image_block(sketch.overlay_png(device, scale=0.6)),
                {"type": "text", "text": "Groups:\n" + json.dumps(sketch.summary())},
            ],
        }
    ]
    system = [
        {"type": "text", "text": ROUND_PROMPT},
        {
            "type": "text",
            "text": "Drawing reference:\n" + _reference() + "\n\n" + knowledge.reference(),
            "cache_control": {"type": "ephemeral"},
        },
    ]

    state: dict = {"saved": None, "preview": None}
    usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }

    def finalize(d: Drawing) -> Drawing:
        # The round owns naming, numbering and where the sketch came from.
        d = workflow.rectify(d)
        d.name = previous.name if previous else name
        d.revision = previous.revision + 1 if previous else 1
        d.date = datetime.date.today().isoformat()
        d.sketch.document = document
        d.sketch.page = 1
        d.sketch.device = device.key
        d.sketch.sent_as = ""
        return d

    def preview(d: Drawing) -> bytes:
        page = render_drawing(d, device)
        return _png(render_lines(page_lines(page, device), device, page.height))

    def call_tool(tool_name: str, args: dict) -> tuple[list[dict] | str, bool]:
        if tool_name == "lookup_knowledge":
            hits = knowledge.lookup(str(args.get("query") or ""), args.get("kind"))
            return json.dumps(hits or "No match.", ensure_ascii=False), False
        try:
            d = finalize(Drawing.model_validate(args.get("drawing") or {}))
        except Exception as e:  # pydantic ValidationError or a cut-off input
            return f"The drawing is not valid: {e}"[:2000], True
        if tool_name == "render_preview":
            png = preview(d)
            state["preview"] = png
            check = json.dumps(workflow.check_dimensions(d))
            return [_image_block(png), {"type": "text", "text": check}], False
        if tool_name == "save_revision":
            if state["saved"]:
                return "Already saved this round.", True
            with tempfile.TemporaryDirectory() as tmp:
                rev = workflow.build_revision(
                    d, Path(tmp) / f"{workflow.revision_title(d)}.rmdoc", sketch.page, store=store
                )
                sent_as = None
                if send:
                    token = cloud.load_token()
                    if not token:
                        raise RoundError("rmink är inte kopplat till reMarkable Cloud")
                    sent_as = workflow.send_revision(rev, token, store)
            state["saved"] = {
                "drawing": rev.drawing,
                "sent_as": sent_as,
                "summary": str(args.get("summary") or ""),
            }
            state["preview"] = rev.preview_png
            return json.dumps({"sent_as": sent_as, "revision": d.revision}), False
        return f"Unknown tool {tool_name}", True

    effort = effort or os.environ.get("RMINK_ROUND_EFFORT", "medium")
    for _ in range(12):
        with client.beta.messages.stream(
            model=MODEL,
            max_tokens=32000,
            system=system,
            tools=TOOLS,
            messages=messages,
            output_config={"effort": effort},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        ) as stream:
            response = stream.get_final_message()
        for key in usage:
            usage[key] += getattr(response.usage, key, 0) or 0
        if response.stop_reason == "refusal":
            raise RoundError("Claude avböjde den här ritningen.")
        if response.stop_reason == "max_tokens":
            raise RoundError("Svaret blev för långt; försök igen.")
        messages.append({"role": "assistant", "content": response.content})
        calls = [b for b in response.content if b.type == "tool_use"]
        if not calls:
            break
        results = []
        for call in calls:
            args = call.input if isinstance(call.input, dict) else {}
            content, is_error = call_tool(call.name, args)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": content,
                    "is_error": is_error,
                }
            )
        messages.append({"role": "user", "content": results})
    else:
        raise RoundError("Varvet tog för många steg.")

    saved = state["saved"]
    if not saved:
        raise RoundError("Claude sparade ingen revision.")
    d: Drawing = saved["drawing"]
    cost = (
        usage["input_tokens"] * PRICE_IN
        + usage["cache_creation_input_tokens"] * PRICE_IN * 1.25
        + usage["cache_read_input_tokens"] * PRICE_CACHE_READ
        + usage["output_tokens"] * PRICE_OUT
    ) / 1e6
    return RoundResult(
        sent_as=saved["sent_as"],
        drawing=d.name,
        revision=d.revision,
        summary=saved["summary"],
        open_questions=[a.text for a in d.annotations if a.status == "open"],
        preview_png=state["preview"],
        seconds=time.monotonic() - started,
        usage=usage | {"usd": round(cost, 3)},
    )
