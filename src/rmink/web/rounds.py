"""Revision rounds from the web: pick a notebook, run a round, see the result.

Owner-only. The router is mounted only when ``RMINK_ROUNDS_SECRET`` and
``ANTHROPIC_API_KEY`` are set, and every API call must carry the secret in the
``X-Rmink-Secret`` header. The reMarkable connection comes from
``RMINK_CLOUD_TOKEN`` and drawings are kept in Upstash Redis when its variables
are set (see :func:`rmink.drawing.store.default_store`).
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


class RunRequest(BaseModel):
    document: str
    device: str = "rm2"


def router() -> APIRouter:
    r = APIRouter()

    @r.get("/rounds", response_class=HTMLResponse, include_in_schema=False)
    def page() -> str:
        return (STATIC / "rounds.html").read_text(encoding="utf-8")

    @r.get("/api/rounds/documents")
    async def documents(path: str = "/", x_rmink_secret: str | None = Header(None)) -> dict:
        _check(x_rmink_secret)
        token = _token()
        try:
            entries = await anyio.to_thread.run_sync(cloud.ls, token, path)
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
        _token()
        from rmink.drawing.agent import RoundError, run_round
        from rmink.drawing.store import default_store

        try:
            result = await anyio.to_thread.run_sync(
                lambda: run_round(req.document, req.device, default_store())
            )
        except RoundError as e:
            raise HTTPException(422, str(e)) from e
        except cloud.CloudAuthError as e:
            raise HTTPException(401, str(e)) from e
        except cloud.CloudError as e:
            raise HTTPException(502, str(e)) from e
        return result.to_json()

    return r
