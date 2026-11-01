"""rmink skola: the groups and topics workbooks are written for, from
``data/skola.toml``.

A group ("Bråk och division") collects workbooks that belong together and is
a folder on the tablet, ``rmink/Skola/<subject>/<group>/<workbook>/``. A topic is what
one workbook practises; its brief goes to Claude with the grade.
"""

from __future__ import annotations

import functools
import tomllib
from importlib import resources

from pydantic import BaseModel, Field

AREA = "Skola"


class Topic(BaseModel):
    id: str
    title: str
    grades: list[int] = Field(default_factory=list)
    brief: str = ""


class Group(BaseModel):
    id: str
    title: str
    area: str = ""  # the subject, "Matte"
    folder: str = ""  # a folder in rmink/Skola/ the group's folder goes in, "Matematik"
    description: str = ""
    topic: list[Topic] = Field(default_factory=list)

    @property
    def path(self) -> str:
        """Where the group is under rmink/Skola/: "Matematik/Bråk och division"."""
        return f"{self.folder}/{self.title}" if self.folder else self.title

    def find(self, topic_id: str) -> Topic | None:
        return next((t for t in self.topic if t.id == topic_id), None)


@functools.cache
def load() -> list[Group]:
    text = (resources.files(__package__) / "data" / "skola.toml").read_text("utf-8")
    return [Group.model_validate(g) for g in tomllib.loads(text)["group"]]


def group(group_id: str) -> Group:
    """The group with id (or title) ``group_id``; ``ValueError`` names the ones there are."""
    for g in load():
        if group_id in (g.id, g.title, g.path):
            return g
    raise ValueError(
        f'Det finns ingen grupp "{group_id}". Välj en av: ' + ", ".join(g.id for g in load())
    )


def group_path(value: str) -> str:
    """The folder path under rmink/Skola/ for ``value``: a catalogue group's
    id, title or path, or a group of one's own ("Matematik/Geometri",
    "Engelska"). ``ValueError`` says what is wrong with it."""
    try:
        return group(value).path
    except ValueError:
        pass
    parts = [p.strip() for p in value.strip().strip("/").split("/")]
    if not 1 <= len(parts) <= 2 or not all(parts):
        raise ValueError(
            f'"{value}" är ingen grupp: ge en grupp som "Grammatik" eller "Matematik/Algebra".'
        )
    if any(len(p) > 40 or any(ch in p for ch in "*?[]\\") for p in parts):
        raise ValueError(f'"{value}": ett gruppnamn är högst 40 tecken, utan * ? [ ] \\.')
    return "/".join(parts)


def groups_prompt(extra: list[str] = ()) -> str:
    """The groups there are, for Claude to place a workbook in one of them
    or name a new one."""
    lines = [f"- {g.path}: {g.description}" for g in load()]
    lines += [f"- {p}" for p in extra if p not in {g.path for g in load()}]
    folders = list(dict.fromkeys(g.folder for g in load() if g.folder))
    return (
        'Give the workbook a "group": the folder under rmink/Skola/ it belongs in. '
        "The groups there are:\n" + "\n".join(lines) + "\n"
        "Use one of them, exactly as written, when the workbook fits it. When none "
        "fits, name a new group: a short Swedish name for the area (1-3 words), "
        "under the subject's folder ("
        + ", ".join(f'"{f}/"' for f in folders)
        + ': "Svenska/Läsförståelse"), or for another subject under a folder named '
        'after it ("NO/Kemi").'
    )


def topic_request(
    group_id: str, topic_id: str = "", grade: int | None = None, extra: str = ""
) -> str:
    """What Claude is asked for: the topic's brief, pitched to ``grade``, plus
    the user's own wishes. Without a topic the whole group is the subject."""
    g = group(group_id)
    if topic_id:
        t = g.find(topic_id)
        if t is None:
            raise ValueError(
                f'"{g.title}" har inget moment "{topic_id}". Välj ett av: '
                + ", ".join(t.id for t in g.topic)
            )
        lines = [f"En arbetsbok i {g.area.lower() or 'skolan'}: {t.title} ({g.title}).", t.brief]
    else:
        lines = [
            f"En arbetsbok i {g.area.lower() or 'skolan'} som blandar momenten i {g.title}: "
            + ", ".join(t.title for t in g.topic)
            + "."
        ]
    if grade:
        lines.append(
            f"Eleven går i årskurs {grade}. Anpassa språk, exempel och svårighet till det, "
            "börja lätt och öka svårigheten avsnitt för avsnitt."
        )
    if extra.strip():
        lines.append(extra.strip())
    return "\n\n".join(lines)


def to_json() -> list[dict]:
    """The catalogue for the web page and MCP: groups with their topics, without briefs."""
    return [
        {
            "id": g.id,
            "title": g.title,
            "path": g.path,
            "area": g.area,
            "description": g.description,
            "topics": [{"id": t.id, "title": t.title, "grades": t.grades} for t in g.topic],
        }
        for g in load()
    ]
