"""Lay out a :class:`Workbook` as a linked PDF in the tablet's page format.

The PDF page has the tablet's aspect and size (rm2: 1404 x 1872 px at 226 dpi
is 447.3 x 596.4 pt), so ink drawn on it maps to PDF points by ``72 / dpi``
with no offset: checked on an rm2 with crosses drawn on the corners of a box.

Page 1 is the cover with the table of contents, one link per section. Each
section starts on a new page with a link back to the contents and, at the
bottom of its last page, one to the next section. The outline (the tablet's
contents panel) lists the same sections. Answers are set inside their boxes as
real PDF text; an answer rmink was unsure of gets a "?" in the margin, and
the cover says to tick the box if the text is right or write the correction.

Under a box with a solution there is room for it: the solution itself is ink
on the hidden "Facit" layer (:func:`solution_strokes`), in rmink's
single-stroke capitals, since the tablet can hide layers but not PDF text.
Once answers are graded, a results page closes the workbook.

A choice question has a box per choice to cross. While it is open the boxes
are empty, with the hint from the last attempt under them; once done the
crosses are drawn in and the solution circles the right boxes.

The layout depends only on the saved workbook, so a round that rebuilds the
PDF of the revision it reads gets the same boxes the reader wrote in.
"""

from __future__ import annotations

import numpy as np
import pymupdf
from rmscene.scene_items import PenColor

from rmink.devices import DeviceProfile
from rmink.drawing.font import text_paths, text_width
from rmink.model import Stroke
from rmink.workbook.model import MAX_ATTEMPTS, AnswerField, Workbook, letter

FACIT_LAYER = "Facit"
SOLUTION_SIZE = 7.0  # pt, cap height of the solution ink
SOLUTION_LINE = 13.0  # pt between solution lines
SOLUTION_INDENT = 34.0  # pt, room for the "Facit" label
VERDICTS = {"correct": "Rätt", "partial": "Delvis rätt", "wrong": "Fel", "": "Inte rättad"}

MARGIN = 40.0
LINE = 26.0  # ruled line spacing in the answer boxes
BOX = 16.0  # pt, side of a choice box
CHOICE_GAP = 8.0  # pt between a choice box and its text
LINK = (0.0, 0.0, 0.6)
ANSWER = (0.0, 0.0, 0.45)
RULE = (0.75, 0.75, 0.75)
UNSURE = (0.65, 0.2, 0.6)

# The built-in Helvetica covers Latin-1 only.
_PLAIN = str.maketrans(
    {
        "→": "->",
        "←": "<-",
        "⇒": "=>",
        "≤": "<=",
        "≥": ">=",
        "≠": "!=",
        "≈": "~",
        "√": "sqrt",
        "π": "pi",
        "∞": "oo",
        "−": "-",
        "×": "x",
        "–": "-",
        "—": "-",
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "€": "EUR",
        "•": "*",
    }
)


def plain(text: str) -> str:
    text = text.translate(_PLAIN)
    return "".join(c if c in "\n\t" or _encodable(c) else "?" for c in text)


def _encodable(c: str) -> bool:
    try:
        c.encode("latin-1")
    except UnicodeEncodeError:
        return False
    return True


def page_size(device: DeviceProfile) -> tuple[float, float]:
    return device.width * 72 / device.dpi, device.height * 72 / device.dpi


def _text(page: pymupdf.Page, rect: pymupdf.Rect, text: str, size: float, **kw) -> float:
    """Write ``text`` in ``rect`` (shrinking it to fit) and return the height used."""
    text = plain(text)
    if not text.strip():
        return 0.0
    while True:
        rest = page.insert_textbox(rect, text, fontsize=size, **kw)
        if rest >= 0 or size <= 7:
            return rect.height - max(rest, 0)
        size -= 1


def _measure(text: str, width: float, size: float, **kw) -> float:
    """Height ``text`` takes when wrapped to ``width``."""
    doc = pymupdf.open()
    page = doc.new_page(width=width + 10, height=2000)
    return _text(page, pymupdf.Rect(0, 0, width, 2000), text, size, **kw)


def _link(page: pymupdf.Page, rect: pymupdf.Rect, label: str, target: int) -> None:
    page.draw_rect(rect, color=LINK, width=0.5)
    page.insert_text((rect.x0 + 6, rect.y1 - 7), plain(label), fontsize=11, color=LINK)
    page.insert_link(
        {"kind": pymupdf.LINK_GOTO, "from": rect, "page": target, "to": pymupdf.Point(0, 0)}
    )


def _answer(page: pymupdf.Page, f: AnswerField) -> None:
    box = pymupdf.Rect(f.rect)
    # A graded box has its verdict in the top right corner.
    right = -72 if f.verdict else -8
    _text(page, box + (8, 6, right, -4), f.answer, 14, color=ANSWER)
    if not f.confident:
        page.insert_text(
            (box.x0 - 16, box.y0 + 20), "?", fontsize=18, fontname="hebo", color=UNSURE
        )


def _cross(page: pymupdf.Page, rect: pymupdf.Rect) -> None:
    r = rect + (3, 3, -3, -3)
    page.draw_line(r.tl, r.br, color=ANSWER, width=1.6)
    page.draw_line(r.tr, r.bl, color=ANSWER, width=1.6)


def choice_note(f: AnswerField) -> str:
    return " (Välj ett.)" if f.kind == "single" else " (Välj alla som stämmer.)"


def feedback(f: AnswerField, mode: str) -> str:
    """The hint under an open choice question that has had a wrong attempt."""
    if not f.verdict or f.done(mode):
        return ""
    return f"Försök {f.attempts + 1} av {MAX_ATTEMPTS}. {f.comment}".strip()


def _choice_heights(f: AnswerField, width: float, mode: str) -> tuple[list[float], float]:
    """Row heights and the height of the hint under them."""
    text_w = width - BOX - CHOICE_GAP - (72 if f.verdict else 0)
    rows = [
        max(BOX + 8, _measure(f"{letter(i)}  {c.text}", text_w, 11) + 8)
        for i, c in enumerate(f.choices)
    ]
    hint = feedback(f, mode)
    return rows, (_measure(hint, width, 9) + 6 if hint else 0.0)


def _choices(
    page: pymupdf.Page, f: AnswerField, x0: float, x1: float, y: float, mode: str
) -> float:
    """Lay out the choice rows from ``y``; sets their boxes and the field's
    rect, and returns where the rows end."""
    rows, hint_h = _choice_heights(f, x1 - x0, mode)
    top = y
    done = f.done(mode)
    for i, (c, row_h) in enumerate(zip(f.choices, rows, strict=True)):
        box = pymupdf.Rect(x0, y + 4, x0 + BOX, y + 4 + BOX)
        page.draw_rect(box, color=(0, 0, 0), width=0.8)
        right = x1 - (72 if f.verdict else 0)
        _text(
            page,
            pymupdf.Rect(box.x1 + CHOICE_GAP, y + 5, right, y + row_h),
            f"{letter(i)}  {c.text}",
            11,
        )
        c.rect = (box.x0, box.y0, box.x1, box.y1)
        c.row = (x0, y, x1, y + row_h)
        if done and i in f.chosen:
            _cross(page, box)
        y += row_h
    f.rect = (x0, top, x1, y)
    if hint := feedback(f, mode):
        _text(page, pymupdf.Rect(x0, y + 2, x1, y + hint_h), hint, 9, color=UNSURE)
        y += hint_h
    return y


def solution_lines(text: str, width: float) -> list[str]:
    """``text`` wrapped to ``width`` pt in the single-stroke font."""
    lines = []
    for para in text.splitlines() or [""]:
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if line and text_width(trial, SOLUTION_SIZE) > width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return [ln for ln in lines if ln] or [""]


def _solution_width(box: tuple[float, float, float, float]) -> float:
    return box[2] - box[0] - SOLUTION_INDENT - 6


def solution_strokes(workbook: Workbook, device: DeviceProfile) -> dict[int, list[Stroke]]:
    """The solutions as ink for the "Facit" layer, by PDF page. Run after
    :func:`build_pdf`, which places them."""
    k = device.dpi / 72
    color = PenColor.RED if device.color else PenColor.BLACK
    out: dict[int, list[Stroke]] = {}
    for f in workbook.fields():
        if not workbook.shows_solution(f) or f.solution_rect is None:
            continue
        for i in f.correct_choices() if f.is_choice() else ():
            # A ring around each right box.
            x, y, x2, y2 = f.choices[i].rect
            cx, cy, r = (x + x2) / 2 * k, (y + y2) / 2 * k, (BOX / 2 + 4) * k
            t = np.linspace(0, 2 * np.pi, 33)
            ring = np.stack([cx + r * np.cos(t), cy + r * np.sin(t)], axis=1)
            out.setdefault(f.page, []).append(
                Stroke(ring, width=2.0, color=color, layer=FACIT_LAYER)
            )
        x0, y0, x1, _ = f.solution_rect
        width = _solution_width(f.solution_rect)
        for i, line in enumerate(solution_lines(f.solution_text(), width)):
            base = ((x0 + SOLUTION_INDENT) * k, (y0 + (i + 1) * SOLUTION_LINE - 3) * k)
            # The single-stroke font has × but no *.
            for path in text_paths(line.replace("*", "×"), base, SOLUTION_SIZE * k):
                out.setdefault(f.page, []).append(
                    Stroke(path, width=1.6, color=color, layer=FACIT_LAYER)
                )
    return out


def build_pdf(workbook: Workbook, device: DeviceProfile) -> bytes:
    """The workbook as PDF bytes. Sets each section's ``page`` and each field's
    ``page`` and ``rect`` in ``workbook``: the layout does not depend on the
    answers, so they stay the same from one revision to the next."""
    w, h = page_size(device)
    doc = pymupdf.open()
    doc.new_page(width=w, height=h)  # the cover, filled in last
    inner = w - 2 * MARGIN
    bottom = h - MARGIN - 34  # room for the "next" link

    def new_page(section_title: str, cont: bool) -> tuple[pymupdf.Page, float]:
        doc.new_page(width=w, height=h)
        page = doc[-1]
        _link(page, pymupdf.Rect(w - MARGIN - 100, 24, w - MARGIN, 46), "<< Innehåll", 0)
        if cont:
            page.insert_text((MARGIN, 40), plain(f"{section_title} (forts.)"), fontsize=10)
            return page, 64.0
        return page, 60.0

    # Page objects go stale when pages are added: keep indices.
    last_pages: list[int] = []
    for section in workbook.sections:
        page, y = new_page(section.title, cont=False)
        section.page = doc.page_count - 1
        y += (
            _text(
                page,
                pymupdf.Rect(MARGIN, y, w - MARGIN - 110, y + 80),
                section.title,
                20,
                fontname="hebo",
            )
            + 10
        )
        if section.text:
            y += _text(page, pymupdf.Rect(MARGIN, y, w - MARGIN, bottom), section.text, 11) + 14
        for f in section.fields:
            prompt = f.prompt + (choice_note(f) if f.is_choice() else "")
            prompt_h = _measure(prompt, inner, 11)
            if f.is_choice():
                rows, hint_h = _choice_heights(f, inner - 12, workbook.mode)
                box_h = sum(rows) + hint_h
            else:
                box_h = f.lines * LINE + 8
            sol_w = w - MARGIN - (MARGIN + 12) - SOLUTION_INDENT - 6
            sol = f.solution_text()
            sol_h = len(solution_lines(sol, sol_w)) * SOLUTION_LINE + 4 if sol else 0
            if y + prompt_h + 4 + box_h + sol_h > bottom and y > 80:
                page, y = new_page(section.title, cont=True)
            y += _text(page, pymupdf.Rect(MARGIN, y, w - MARGIN, y + prompt_h + 4), prompt, 11)
            y += 4
            if f.is_choice():
                end = _choices(page, f, MARGIN + 12, w - MARGIN, y, workbook.mode)
                box = pymupdf.Rect(f.rect)
                f.page = doc.page_count - 1
            else:
                box = pymupdf.Rect(MARGIN + 12, y, w - MARGIN, min(y + box_h, bottom))
                page.draw_rect(box, color=(0, 0, 0), width=0.8)
                for ly in range(1, f.lines):
                    yy = box.y0 + 4 + ly * LINE
                    if yy < box.y1 - 4:
                        page.draw_line((box.x0 + 6, yy), (box.x1 - 6, yy), color=RULE, width=0.4)
                f.page, f.rect = doc.page_count - 1, (box.x0, box.y0, box.x1, box.y1)
                end = box.y1
                if f.answer:
                    _answer(page, f)
            f.solution_rect = None
            if sol:
                f.solution_rect = (box.x0, end + 4, box.x1, end + 4 + sol_h)
                if workbook.shows_solution(f):
                    page.insert_text(
                        (box.x0, end + 4 + SOLUTION_LINE - 3), "Facit", fontsize=7, color=RULE
                    )
                if f.verdict:
                    mark = {"correct": "Rätt", "partial": "Delvis", "wrong": "Fel"}[f.verdict]
                    page.insert_text(
                        (box.x1 - 66, box.y0 + 12),
                        f"{mark} {f.awarded:g}/{f.points} p",
                        fontsize=8,
                        fontname="hebo",
                        color=ANSWER,
                    )
            y = end + 18 + sol_h
        last_pages.append(doc.page_count - 1)

    results = _results(doc, workbook, w, h) if workbook.graded() else None
    for last, nxt in zip(last_pages, workbook.sections[1:], strict=False):
        _link(
            doc[last],
            pymupdf.Rect(w - MARGIN - 100, h - MARGIN - 24, w - MARGIN, h - MARGIN),
            "Nästa >>",
            nxt.page,
        )

    cover = doc[0]
    y = 70.0
    y += (
        _text(
            cover,
            pymupdf.Rect(MARGIN, y, w - MARGIN, y + 90),
            workbook.title or workbook.name,
            24,
            fontname="hebo",
        )
        + 12
    )
    if workbook.intro:
        y += _text(cover, pymupdf.Rect(MARGIN, y, w - MARGIN, y + 160), workbook.intro, 11) + 16
    cover.insert_text((MARGIN, y + 14), "Innehåll", fontsize=16, fontname="hebo")
    y += 30
    # Leave room at the bottom for the note about unsure answers.
    entries = [(f"{n}. {s.title}", s.page) for n, s in enumerate(workbook.sections, 1)] + (
        [("Resultat", results)] if results is not None else []
    )
    row = max(16.0, min(30.0, (h - MARGIN - 70 - y) / max(len(entries), 1)))
    for label, target in entries:
        r = pymupdf.Rect(MARGIN, y, w - MARGIN, y + row - 6)
        _link(cover, r, f"{label}   ...   sid {target + 1}", target)
        y += row
    notes = []
    if any(f.is_choice() for f in workbook.fields()):
        notes.append(
            "Flerval: kryssa i rutan. Ångrar du dig, fyll i rutan helt eller stryk över raden."
        )
    if workbook.unsure():
        notes.append(
            "? vid en ruta: handstilen var svår att läsa. Stämmer texten, sätt en bock i "
            "rutan. Annars skriver du rättelsen i rutan. Nästa varv läser det."
        )
    if notes:
        _text(
            cover,
            pymupdf.Rect(MARGIN, h - MARGIN - 64, w - MARGIN, h - MARGIN - 14),
            "\n".join(notes),
            9,
            color=UNSURE,
        )
    footer = f"{workbook.name} r{workbook.revision:02d}" + (
        f" · {workbook.date}" if workbook.date else ""
    )
    cover.insert_text((MARGIN, h - MARGIN), plain(footer), fontsize=8, color=(0.4, 0.4, 0.4))

    toc = [[1, "Innehåll", 1]] + [[1, plain(s.title), s.page + 1] for s in workbook.sections]
    if results is not None:
        toc.append([1, "Resultat", results + 1])
    doc.set_toc(toc)
    doc.set_metadata({"title": plain(workbook.title or workbook.name), "creator": "rmink"})
    return doc.tobytes(garbage=3, deflate=True)


def _results(doc: pymupdf.Document, workbook: Workbook, w: float, h: float) -> int:
    """Add the results page(s) and return the index of the first. Each row
    links to its question."""
    bottom = h - MARGIN
    inner = w - 2 * MARGIN

    def new_page() -> tuple[pymupdf.Page, float]:
        doc.new_page(width=w, height=h)
        page = doc[-1]
        _link(page, pymupdf.Rect(w - MARGIN - 100, 24, w - MARGIN, 46), "<< Innehåll", 0)
        return page, 60.0

    page, y = new_page()
    first = doc.page_count - 1
    got, total = workbook.score()
    page.insert_text((MARGIN, y + 20), "Resultat", fontsize=20, fontname="hebo")
    y += 34
    if total:
        pct = round(100 * got / total)
        page.insert_text((MARGIN, y + 16), f"{got:g} av {total} poäng ({pct} %)", fontsize=15)
        y += 30
        if any(f.attempts > 1 for f in workbook.fields()):
            first_try = workbook.first_score()
            page.insert_text(
                (MARGIN, y + 12), f"Första försöket: {first_try:g} av {total} poäng", fontsize=11
            )
            y += 22
    n = 0
    for section in workbook.sections:
        if y + 40 > bottom:
            page, y = new_page()
        page.insert_text((MARGIN, y + 14), plain(section.title), fontsize=12, fontname="hebo")
        y += 22
        for f in section.fields:
            n += 1
            verdict = VERDICTS[f.verdict] if f.answer else "Inte besvarad"
            points = f" {f.awarded:g}/{f.points} p" if f.has_solution() and f.verdict else ""
            if f.attempts > 1:
                points += f", försök {f.attempts} (först {f.first_awarded or 0:g} p)"
            text = f"{n}. {f.prompt}\nSvar: {f.answer or '-'}\n{verdict}{points}"
            if f.comment and f.verdict != "correct":
                text += f" - {f.comment}"
            row_h = _measure(text, inner - 12, 9) + 6
            if y + row_h > bottom:
                page, y = new_page()
            rect = pymupdf.Rect(MARGIN, y, w - MARGIN, y + row_h)
            _text(page, rect + (6, 3, -6, 0), text, 9)
            page.draw_rect(rect, color=RULE, width=0.4)
            page.insert_link(
                {"kind": pymupdf.LINK_GOTO, "from": rect, "page": f.page, "to": pymupdf.Point(0, 0)}
            )
            y += row_h + 4
    return first
