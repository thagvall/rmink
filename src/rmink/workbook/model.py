"""A workbook: a linked PDF of sections with answer boxes to write in by hand.

Claude writes the :class:`Workbook` (title, sections, questions);
:mod:`rmink.workbook.build` lays it out as a PDF in the tablet's page format,
with a table of contents, links between sections and a ruled box per field.
After the user has written in the boxes, a round reads the ink per box, has
Claude transcribe it and writes the next revision with the answers set as PDF
text. The workbook is saved between rounds like a drawing.

Field rectangles are PDF points on the field's page (origin top-left), set by
the layout; they map to tablet pixels by ``dpi / 72``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points


class AnswerField(BaseModel):
    id: str
    prompt: str
    lines: int = Field(default=3, ge=1, le=20)  # ruled lines to write on
    answer: str = ""
    # False when the handwriting was hard to read: the revision marks the box.
    confident: bool = True
    page: int = -1  # PDF page index, set by the layout
    rect: Rect | None = None


class Section(BaseModel):
    id: str
    title: str
    text: str = ""  # explanation shown above the fields
    fields: list[AnswerField] = Field(default_factory=list)
    page: int = -1  # PDF page index of the section's first page


class Workbook(BaseModel):
    kind: Literal["workbook"] = "workbook"
    name: str  # folder and notebook name on the tablet
    title: str = ""
    intro: str = ""
    sections: list[Section] = Field(default_factory=list)
    revision: int = 1
    date: str = ""
    device: str = "rm2"
    document: str = ""  # the notebook the last round read
    sent_as: str = ""  # cloud path the current revision was sent to
    log: list[str] = Field(default_factory=list)

    def fields(self) -> list[AnswerField]:
        return [f for s in self.sections for f in s.fields]

    def field(self, field_id: str) -> AnswerField | None:
        return next((f for f in self.fields() if f.id == field_id), None)

    def unsure(self) -> list[AnswerField]:
        return [f for f in self.fields() if f.answer and not f.confident]
