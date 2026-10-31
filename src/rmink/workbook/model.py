"""A workbook: a linked PDF of sections with answer boxes to write in by hand.

Claude writes the :class:`Workbook` (title, sections, questions);
:mod:`rmink.workbook.build` lays it out as a PDF in the tablet's page format,
with a table of contents, links between sections and a ruled box per field.
After the user has written in the boxes, a round reads the ink per box, has
Claude transcribe it and writes the next revision with the answers set as PDF
text. The workbook is saved between rounds like a drawing.

Each field can have a solution. It is written as ink on the hidden layer
"Facit": from the start in a practice workbook, and after the first round
in a test. Rounds grade the answers against it, and a results page at the
end shows how it went.

A field can instead be a multiple-choice question: "single" (one right
choice) or "multi" (all that apply). The reader crosses the boxes; rmink reads
and grades the crosses itself, and only asks Claude about unclear ink. In
practice a wrong answer gets a hint and a new attempt, up to
:data:`MAX_ATTEMPTS`; the solution comes once the question is done.

Field rectangles are PDF points on the field's page (origin top-left), set by
the layout; they map to tablet pixels by ``dpi / 72``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Rect = tuple[float, float, float, float]  # x0, y0, x1, y1 in PDF points
Verdict = Literal["", "correct", "partial", "wrong"]
Kind = Literal["text", "single", "multi"]
MAX_ATTEMPTS = 3  # attempts at a choice question in practice
# Layout of new workbooks. A saved workbook keeps the layout it was made with,
# so a round finds the boxes where the reader wrote: 1 is the first (small
# boxes), 2 has taller lines, bigger choice boxes and fills each page.
LAYOUT = 2


def letter(i: int) -> str:
    return "ABCDEFGH"[i]


class Choice(BaseModel):
    text: str
    correct: bool = False
    # Why it is right or wrong: the hint after a wrong cross, without giving
    # the right choice away.
    why: str = ""
    rect: Rect | None = None  # the box to cross, set by the layout
    row: Rect | None = None  # the box and its text


class AnswerField(BaseModel):
    id: str
    prompt: str
    kind: Kind = "text"
    choices: list[Choice] = Field(default_factory=list)
    lines: int = Field(default=3, ge=1, le=20)  # ruled lines to write on
    answer: str = ""
    # False when the handwriting was hard to read: the revision marks the box.
    confident: bool = True
    page: int = -1  # PDF page index, set by the layout
    rect: Rect | None = None
    solution: str = ""  # the expected answer, with the key step
    points: int = Field(default=1, ge=0, le=20)
    # Grading of the current answer; empty until a round has graded it.
    verdict: Verdict = ""
    awarded: float = 0.0
    comment: str = ""  # why it is not right, for the results page
    solution_rect: Rect | None = None  # where the solution ink goes, set by the layout
    # Choice questions: the crossed choices of the last attempt, how many
    # attempts there have been and the points of the first.
    chosen: list[int] = Field(default_factory=list)
    attempts: int = 0
    first_awarded: float | None = None

    def is_choice(self) -> bool:
        return self.kind != "text"

    def correct_choices(self) -> set[int]:
        return {i for i, c in enumerate(self.choices) if c.correct}

    def has_solution(self) -> bool:
        return bool(self.solution) or self.is_choice()

    def solution_text(self) -> str:
        if not self.is_choice():
            return self.solution
        right = sorted(self.correct_choices())
        text = "Rätt: " + ", ".join(letter(i) for i in right) + "."
        whys = " ".join(self.choices[i].why for i in right if self.choices[i].why)
        return f"{text} {whys or self.solution}".strip()

    def done(self, mode: str) -> bool:
        """A choice question is done when it is right, after the last attempt,
        and in a test after the first grading."""
        if not self.verdict:
            return False
        return self.verdict == "correct" or mode == "test" or self.attempts >= MAX_ATTEMPTS


class Section(BaseModel):
    id: str
    title: str
    text: str = ""  # explanation shown above the fields
    fields: list[AnswerField] = Field(default_factory=list)
    page: int = -1  # PDF page index of the section's first page


class Workbook(BaseModel):
    kind: Literal["workbook"] = "workbook"
    name: str  # folder and notebook name on the tablet
    # practice: the solutions are on the tablet (hidden) from the start;
    # test: they come with the first graded revision.
    mode: Literal["practice", "test"] = "practice"
    layout: int = 1  # see LAYOUT; saved workbooks without it are layout 1
    title: str = ""
    intro: str = ""
    # rmink skola: the area and group it belongs to ("Skola", "Bråk och
    # division"), which put it in rmink/<area>/<group>/<name>/ on the tablet.
    area: str = ""
    group: str = ""
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

    def graded(self) -> bool:
        return any(f.verdict for f in self.fields())

    def score(self) -> tuple[float, int]:
        """Points awarded and points possible, over the fields with a solution."""
        fields = [f for f in self.fields() if f.has_solution()]
        return sum(f.awarded for f in fields), sum(f.points for f in fields)

    def first_score(self) -> float:
        """Points as if every choice question had only had its first attempt."""
        return sum(
            f.awarded if f.first_awarded is None else f.first_awarded
            for f in self.fields()
            if f.has_solution()
        )

    def show_solutions(self) -> bool:
        return self.mode == "practice" or self.graded()

    def shows_solution(self, f: AnswerField) -> bool:
        """Whether the revision has ``f``'s solution on the "Facit" layer: a
        choice question's once it is done, so a new attempt is not given away."""
        if f.is_choice():
            return f.done(self.mode)
        return bool(f.solution) and self.show_solutions()

    def open_for_answers(self, f: AnswerField) -> bool:
        return not (f.is_choice() and f.done(self.mode))
