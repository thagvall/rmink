"""Revision rounds from the web: run the next round of a drawing, or the first
round of a new sketch in the rmink folder, and see the result.

Owner-only. The router is mounted only when ``RMINK_ROUNDS_SECRET`` and
``ANTHROPIC_API_KEY`` are set, and every API call must carry the secret in the
``X-Rmink-Secret`` header. The reMarkable connection comes from
``RMINK_CLOUD_TOKEN``, and the page only reaches the rmink folder and what is
in it: other paths are refused before rmapi runs. Drawings are kept in the
owner's browser: the page sends them with each round and stores what comes
back. With Upstash Redis configured
(see :func:`rmink.drawing.store.redis_from_env`) they are kept there instead.
"""

from __future__ import annotations

import hmac
import os
from pathlib import Path

import anyio
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from rmink import cloud

STATIC = Path(__file__).parent / "static"


def enabled() -> bool:
    return bool(os.environ.get("RMINK_ROUNDS_SECRET") and os.environ.get("ANTHROPIC_API_KEY"))


def _check(secret: str | None) -> None:
    expected = os.environ.get("RMINK_ROUNDS_SECRET", "")
    if not expected or not hmac.compare_digest((secret or "").encode(), expected.encode()):
        raise HTTPException(401, "Fel nyckel")


def _token() -> str:
    token = cloud.load_token()
    if not token:
        raise HTTPException(503, "RMINK_CLOUD_TOKEN saknas på servern")
    return token


def _in_rmink(path: str, folder_ok: bool = True) -> str:
    """``path`` as "/rmink/...", or 403 if it points anywhere else."""
    parts = [p for p in path.strip().split("/") if p]
    if not parts or parts[0] != "rmink" or any(p in (".", "..") for p in parts):
        raise HTTPException(403, "Bara mappen rmink och det som ligger i den")
    if len(parts) == 1 and not folder_ok:
        raise HTTPException(403, "Välj en anteckningsbok i rmink")
    return "/" + "/".join(parts)


class RunRequest(BaseModel):
    document: str
    device: str = "rm2"
    # The browser's saved drawings (name slug -> Drawing JSON) and which
    # notebook belongs to which drawing; ignored when Redis is configured.
    drawings: dict[str, str] = {}
    links: dict[str, str] = {}


def router() -> APIRouter:
    r = APIRouter()

    @r.get("/rounds", response_class=HTMLResponse, include_in_schema=False)
    def page() -> str:
        return (STATIC / "rounds.html").read_text(encoding="utf-8")

    @r.get("/api/rounds/documents")
    async def documents(path: str = "/rmink", x_rmink_secret: str | None = Header(None)) -> dict:
        _check(x_rmink_secret)
        path = _in_rmink(path)
        token = _token()
        try:
            entries = await anyio.to_thread.run_sync(cloud.ls, token, path)
        except cloud.CloudNotFoundError:
            # No rmink folder yet: the page tells the owner to make one.
            return {"path": path, "entries": [], "missing": True}
        except cloud.CloudAuthError as e:
            raise HTTPException(401, str(e)) from e
        except cloud.CloudError as e:
            raise HTTPException(502, str(e)) from e
        base = path.rstrip("/")
        return {
            "path": path,
            "entries": [
                {"name": e.name, "folder": e.folder, "path": f"{base}/{e.name}"} for e in entries
            ],
        }

    @r.post("/api/rounds/run")
    async def run(req: RunRequest, x_rmink_secret: str | None = Header(None)) -> dict:
        _check(x_rmink_secret)
        document = _in_rmink(req.document, folder_ok=False)
        _token()
        from rmink.drawing.agent import RoundError, run_round
        from rmink.drawing.store import MemoryStore, redis_from_env

        store = redis_from_env() or MemoryStore(req.drawings, req.links)
        try:
            result = await anyio.to_thread.run_sync(lambda: run_round(document, req.device, store))
        except RoundError as e:
            raise HTTPException(422, str(e)) from e
        except cloud.CloudAuthError as e:
            raise HTTPException(401, str(e)) from e
        except cloud.CloudError as e:
            raise HTTPException(502, str(e)) from e
        out = result.to_json()
        if isinstance(store, MemoryStore):
            out["store"] = {"drawings": store.changed, "links": store.links}
        return out

    return r
