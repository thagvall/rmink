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
"""

from __future__ import annotations

import pymupdf

from rmink.devices import DeviceProfile
from rmink.workbook.model import AnswerField, Workbook

MARGIN = 40.0
LINE = 26.0  # ruled line spacing in the answer boxes
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
    _text(page, box + (8, 6, -8, -4), f.answer, 14, color=ANSWER)
    if not f.confident:
        page.insert_text(
            (box.x0 - 16, box.y0 + 20), "?", fontsize=18, fontname="hebo", color=UNSURE
        )


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
            prompt_h = _measure(f.prompt, inner, 11)
            box_h = f.lines * LINE + 8
            if y + prompt_h + 4 + box_h > bottom and y > 80:
                page, y = new_page(section.title, cont=True)
            y += _text(page, pymupdf.Rect(MARGIN, y, w - MARGIN, y + prompt_h + 4), f.prompt, 11)
            y += 4
            box = pymupdf.Rect(MARGIN + 12, y, w - MARGIN, min(y + box_h, bottom))
            page.draw_rect(box, color=(0, 0, 0), width=0.8)
            for ly in range(1, f.lines):
                yy = box.y0 + 4 + ly * LINE
                if yy < box.y1 - 4:
                    page.draw_line((box.x0 + 6, yy), (box.x1 - 6, yy), color=RULE, width=0.4)
            f.page, f.rect = doc.page_count - 1, (box.x0, box.y0, box.x1, box.y1)
            if f.answer:
                _answer(page, f)
            y = box.y1 + 18
        last_pages.append(doc.page_count - 1)

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
    row = max(16.0, min(30.0, (h - MARGIN - 70 - y) / max(len(workbook.sections), 1)))
    for n, section in enumerate(workbook.sections, 1):
        r = pymupdf.Rect(MARGIN, y, w - MARGIN, y + row - 6)
        _link(cover, r, f"{n}. {section.title}   ...   sid {section.page + 1}", section.page)
        y += row
    if workbook.unsure():
        _text(
            cover,
            pymupdf.Rect(MARGIN, h - MARGIN - 64, w - MARGIN, h - MARGIN - 14),
            "? vid en ruta: handstilen var svår att läsa. Stämmer texten, sätt en bock i "
            "rutan. Annars skriver du rättelsen i rutan. Nästa varv läser det.",
            9,
            color=UNSURE,
        )
    footer = f"{workbook.name} r{workbook.revision:02d}" + (
        f" · {workbook.date}" if workbook.date else ""
    )
    cover.insert_text((MARGIN, h - MARGIN), plain(footer), fontsize=8, color=(0.4, 0.4, 0.4))

    doc.set_toc([[1, "Innehåll", 1]] + [[1, plain(s.title), s.page + 1] for s in workbook.sections])
    doc.set_metadata({"title": plain(workbook.title or workbook.name), "creator": "rmink"})
    return doc.tobytes(garbage=3, deflate=True)
