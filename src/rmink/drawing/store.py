"""Where drawings are kept between rounds.

A drawing is saved after every revision so the next round can tell the user's
new marks from rmink's own strokes. Locally that is a JSON file per drawing in
``~/.config/rmink/drawings``; on a hosted server it is Upstash Redis (the
Vercel KV integration), reached over its REST API.

On a hosted server without Redis, the owner's browser keeps them instead:
:class:`MemoryStore` is filled from the request and its changes go back in the
response.

Each store also remembers which drawing a notebook belongs to ("Altan r2" ->
"altan"), since the cloud may rename an upload ("Altan r2_2").

Workbooks (:mod:`rmink.workbook`) are kept the same way, beside the drawings;
a notebook linked to one is linked as "workbook:<name>".
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Protocol

from rmink.devices import config_dir
from rmink.drawing.model import Drawing
from rmink.workbook.model import Workbook

WORKBOOK_LINK = "workbook:"


def slug(name: str) -> str:
    return re.sub(r"[^\w\-]+", "-", name.strip().lower()).strip("-") or "drawing"


def guess_drawing_name(document: str) -> str:
    """'/rmink/Altan/Altan r03 · 2 frågor_2' -> 'Altan'. A notebook in a folder
    under /rmink belongs to the nearest folder above it other than Tidigare
    ('/rmink/Bastu/Bastuskiss' -> 'Bastu', '/rmink/Skola/Bråk och division/
    Bråk åk 5/Tidigare/Bråk åk 5 r01' -> 'Bråk åk 5'). Elsewhere it is the
    notebook name without folder, file extension, revision (or "r00 skiss"),
    open-question count and the cloud's _N suffix for taken names. Local
    Windows paths use backslashes."""
    if re.match(r"/rmink/[^/]+/", document):
        folders = [p for p in document.split("/")[2:-1] if p != "Tidigare"]
        if folders:
            return folders[-1]
    name = re.split(r"[/\\]", document.rstrip("/\\"))[-1]
    name = re.sub(r"\.(rmdoc|rm|zip)$", "", name, flags=re.I)
    name = re.sub(r"_\d+$", "", name)
    return re.sub(r"\s+r\d+(\s+(·.*|skiss))?$", "", name, flags=re.I)


class Store(Protocol):
    def save(self, drawing: Drawing) -> str: ...
    def load(self, name: str) -> Drawing | None: ...
    def link(self, document: str, name: str) -> None: ...
    def linked(self, document: str) -> str | None: ...
    def save_workbook(self, workbook: Workbook) -> str: ...
    def load_workbook(self, name: str) -> Workbook | None: ...


class FileStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or config_dir() / "drawings"

    def _path(self, name: str) -> Path:
        return self.root / f"{slug(name)}.json"

    def save(self, drawing: Drawing) -> str:
        path = self._path(drawing.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(drawing.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def load(self, name: str) -> Drawing | None:
        path = self._path(name)
        if not path.is_file():
            return None
        return Drawing.model_validate_json(path.read_text(encoding="utf-8"))

    def _links(self) -> dict[str, str]:
        path = self.root / "documents.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}

    def link(self, document: str, name: str) -> None:
        links = self._links() | {document.strip("/"): name}
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "documents.json").write_text(json.dumps(links, indent=2), encoding="utf-8")

    def linked(self, document: str) -> str | None:
        return self._links().get(document.strip("/"))

    def _workbook_path(self, name: str) -> Path:
        return self.root / "workbooks" / f"{slug(name)}.json"

    def save_workbook(self, workbook: Workbook) -> str:
        path = self._workbook_path(workbook.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(workbook.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def load_workbook(self, name: str) -> Workbook | None:
        path = self._workbook_path(name)
        if not path.is_file():
            return None
        return Workbook.model_validate_json(path.read_text(encoding="utf-8"))


class MemoryStore:
    """Drawings for one request, sent by the browser that keeps them.

    ``changed`` holds what a round saved, to send back to the browser."""

    def __init__(self, drawings: dict[str, str] | None = None, links: dict[str, str] | None = None):
        self.drawings = dict(drawings or {})
        self.links = dict(links or {})
        self.changed: dict[str, str] = {}

    def save(self, drawing: Drawing) -> str:
        key = slug(drawing.name)
        self.drawings[key] = self.changed[key] = drawing.model_dump_json()
        return f"browser:{key}"

    def load(self, name: str) -> Drawing | None:
        raw = self.drawings.get(slug(name))
        return Drawing.model_validate_json(raw) if raw else None

    def link(self, document: str, name: str) -> None:
        self.links[document.strip("/")] = name

    def linked(self, document: str) -> str | None:
        return self.links.get(document.strip("/"))

    # Kept among the drawings under their own key, so the browser stores them
    # with no changes.
    def save_workbook(self, workbook: Workbook) -> str:
        key = WORKBOOK_LINK + slug(workbook.name)
        self.drawings[key] = self.changed[key] = workbook.model_dump_json()
        return f"browser:{key}"

    def load_workbook(self, name: str) -> Workbook | None:
        raw = self.drawings.get(WORKBOOK_LINK + slug(name))
        return Workbook.model_validate_json(raw) if raw else None


class RedisStore:
    """Upstash Redis over REST: each command is a JSON array POSTed to the URL."""

    def __init__(self, url: str, token: str) -> None:
        import httpx

        self._client = httpx.Client(
            base_url=url, headers={"Authorization": f"Bearer {token}"}, timeout=15
        )

    def _cmd(self, *args: str):
        r = self._client.post("/", json=list(args))
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(f"Redis: {body['error']}")
        return body.get("result")

    def save(self, drawing: Drawing) -> str:
        key = f"rmink:drawing:{slug(drawing.name)}"
        self._cmd("SET", key, drawing.model_dump_json())
        return f"redis:{key}"

    def load(self, name: str) -> Drawing | None:
        raw = self._cmd("GET", f"rmink:drawing:{slug(name)}")
        return Drawing.model_validate_json(raw) if raw else None

    def link(self, document: str, name: str) -> None:
        self._cmd("SET", f"rmink:document:{document.strip('/')}", name)

    def linked(self, document: str) -> str | None:
        return self._cmd("GET", f"rmink:document:{document.strip('/')}")

    def save_workbook(self, workbook: Workbook) -> str:
        key = f"rmink:workbook:{slug(workbook.name)}"
        self._cmd("SET", key, workbook.model_dump_json())
        return f"redis:{key}"

    def load_workbook(self, name: str) -> Workbook | None:
        raw = self._cmd("GET", f"rmink:workbook:{slug(name)}")
        return Workbook.model_validate_json(raw) if raw else None


def redis_from_env() -> RedisStore | None:
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN")
    return RedisStore(url, token) if url and token else None


def default_store() -> Store:
    """Redis when the Upstash variables are set, else files."""
    return redis_from_env() or FileStore()
