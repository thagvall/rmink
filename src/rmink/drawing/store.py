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

import hashlib
import json
import os
import re
import time
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

    def everything(self) -> dict[str, str]:
        """Every saved drawing and workbook as JSON, keyed like the browser
        keeps them ("<slug>", "workbook:<slug>")."""
        out = {p.stem: p.read_text(encoding="utf-8") for p in self.root.glob("*.json")}
        out.pop("documents", None)
        for p in (self.root / "workbooks").glob("*.json"):
            out[WORKBOOK_LINK + p.stem] = p.read_text(encoding="utf-8")
        return out

    def links(self) -> dict[str, str]:
        return self._links()


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


class BlobStore:
    """Drawings, workbooks and links in a private Vercel Blob store, for the
    hosted site, where instances keep nothing between requests.

    Blob serves an overwritten file from its cache for a while, so a drawing
    is never overwritten: each save is a new file, ``drawing/<slug>/<time>.json``,
    and a load reads the newest one a listing (which is not cached) shows.
    The older files are the drawing's history."""

    PREFIX = "rmink/store/"

    def __init__(self) -> None:
        from vercel.blob import sync as blob

        self._blob = blob

    def _put(self, path: str, text: str) -> None:
        self._blob.put_blob(
            self.PREFIX + path,
            text.encode(),
            access="private",
            content_type="application/json",
            allow_overwrite=True,
        )

    def _get(self, path: str) -> str | None:
        try:
            return self._blob.get_blob(self.PREFIX + path, access="private").body.decode()
        except self._blob.BlobNotFoundError:
            return None

    def _save(self, kind: str, name: str, text: str) -> str:
        path = f"{kind}/{slug(name)}/{time.time_ns() // 1000:016d}.json"
        self._put(path, text)
        return f"blob:{path}"

    def _latest(self, kind: str, name: str) -> str | None:
        prefix = f"{self.PREFIX}{kind}/{slug(name)}/"
        paths = [b.pathname for b in self._blob.query_blobs(prefix=prefix)]
        return self._get(max(paths).removeprefix(self.PREFIX)) if paths else None

    def save(self, drawing: Drawing) -> str:
        return self._save("drawing", drawing.name, drawing.model_dump_json())

    def load(self, name: str) -> Drawing | None:
        raw = self._latest("drawing", name)
        return Drawing.model_validate_json(raw) if raw else None

    def save_workbook(self, workbook: Workbook) -> str:
        return self._save("workbook", workbook.name, workbook.model_dump_json())

    def load_workbook(self, name: str) -> Workbook | None:
        raw = self._latest("workbook", name)
        return Workbook.model_validate_json(raw) if raw else None

    @staticmethod
    def _link_path(document: str) -> str:
        return f"link/{hashlib.sha1(document.strip('/').encode()).hexdigest()}.json"

    def link(self, document: str, name: str) -> None:
        # A notebook keeps its owner, so a link is written once and not changed.
        self._put(self._link_path(document), json.dumps({"document": document, "name": name}))

    def linked(self, document: str) -> str | None:
        raw = self._get(self._link_path(document))
        return json.loads(raw)["name"] if raw else None

    def everything(self) -> dict[str, str]:
        """The newest JSON of every drawing and workbook, keyed like the
        browser keeps them: "<slug>" and "workbook:<slug>"."""
        newest: dict[str, str] = {}
        for kind in ("drawing", "workbook"):
            for b in self._blob.query_blobs(prefix=f"{self.PREFIX}{kind}/"):
                name = b.pathname.removeprefix(f"{self.PREFIX}{kind}/").split("/")[0]
                key = name if kind == "drawing" else WORKBOOK_LINK + name
                newest[key] = max(newest.get(key, ""), b.pathname)
        out = {}
        for key, path in newest.items():
            if raw := self._get(path.removeprefix(self.PREFIX)):
                out[key] = raw
        return out


def redis_from_env() -> RedisStore | None:
    url = os.environ.get("UPSTASH_REDIS_REST_URL") or os.environ.get("KV_REST_API_URL")
    token = os.environ.get("UPSTASH_REDIS_REST_TOKEN") or os.environ.get("KV_REST_API_TOKEN")
    return RedisStore(url, token) if url and token else None


def server_store() -> RedisStore | BlobStore | None:
    """Where the hosted site keeps drawings: Redis when the Upstash variables
    are set, else the Vercel Blob store when there is one; None leaves them
    in the browser."""
    from rmink import blob_cache

    return redis_from_env() or (BlobStore() if blob_cache.enabled() else None)


def default_store() -> Store:
    """Redis or Blob when configured (:func:`server_store`), else files."""
    return server_store() or FileStore()
