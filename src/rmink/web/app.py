"""FastAPI application for the rmink web UI."""

from __future__ import annotations

import base64
import io
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import anyio
import pymupdf
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask

from rmink import api
from rmink.devices import all_devices
from rmink.ingest import IMAGE_SUFFIXES, parse_page_ranges
from rmink.options import ConvertOptions

_STATIC = Path(__file__).parent / "static"
_ALLOWED = IMAGE_SUFFIXES | {".pdf", ".svg"}
_PREVIEW_WIDTH = 720

# Module level so FastAPI can resolve the (string) annotations.
Files = Annotated[list[UploadFile], File()]
Opt = Annotated[str | None, Form()]


@dataclass(frozen=True)
class Limits:
    max_upload_bytes: int
    max_files: int
    max_pages: int
    timeout_s: float
    concurrency: int

    @classmethod
    def from_env(cls) -> Limits:
        env = os.environ.get
        return cls(
            max_upload_bytes=int(float(env("RMINK_MAX_UPLOAD_MB", "25")) * 1_000_000),
            max_files=int(env("RMINK_MAX_FILES", "20")),
            max_pages=int(env("RMINK_MAX_PAGES", "40")),
            timeout_s=float(env("RMINK_TIMEOUT_S", "120")),
            concurrency=int(env("RMINK_CONCURRENCY", "2")),
        )


def _safe_stem(name: str) -> str:
    stem = Path(name or "notebook").stem
    return re.sub(r"[^\w\- .]+", "", stem).strip() or "notebook"


def create_app(limits: Limits | None = None) -> FastAPI:
    limits = limits or Limits.from_env()
    limiter = anyio.CapacityLimiter(limits.concurrency)
    app = FastAPI(title="rmink", docs_url="/api/docs", redoc_url=None)

    async def _save_uploads(files: list[UploadFile], workdir: Path) -> list[Path]:
        if not files:
            raise HTTPException(400, "No files uploaded")
        if len(files) > limits.max_files:
            raise HTTPException(413, f"At most {limits.max_files} files per request")
        paths, total = [], 0
        for i, f in enumerate(files):
            suffix = Path(f.filename or "").suffix.lower()
            if suffix not in _ALLOWED:
                raise HTTPException(415, f"Unsupported file type: {f.filename}")
            # Uploaded names never touch the filesystem; only index + suffix.
            dest = workdir / f"{i:03d}_{_safe_stem(f.filename)[:60]}{suffix}"
            with dest.open("wb") as out:
                while chunk := await f.read(1 << 20):
                    total += len(chunk)
                    if total > limits.max_upload_bytes:
                        mb = limits.max_upload_bytes / 1e6
                        raise HTTPException(413, f"Upload exceeds {mb:.0f} MB")
                    out.write(chunk)
            paths.append(dest)
        return paths

    def _check_pages(paths: list[Path], pages: str | None) -> None:
        count = 0
        for p in paths:
            if p.suffix.lower() == ".pdf":
                try:
                    with pymupdf.open(p) as doc:
                        count += len(parse_page_ranges(pages, doc.page_count))
                except Exception as e:
                    raise HTTPException(422, f"Could not read PDF: {p.name[4:]}") from e
            else:
                count += 1
        if count > limits.max_pages:
            raise HTTPException(
                413, f"{count} pages requested; the limit is {limits.max_pages}. Use page ranges."
            )

    def _options(**kw) -> ConvertOptions:
        try:
            return ConvertOptions(**{k: v for k, v in kw.items() if v not in (None, "")})
        except ValidationError as e:
            raise HTTPException(422, e.errors(include_url=False)) from e

    async def _run(fn, *args):
        try:
            with anyio.fail_after(limits.timeout_s):
                return await anyio.to_thread.run_sync(fn, *args, limiter=limiter)
        except TimeoutError as e:
            raise HTTPException(504, "Conversion took too long; try fewer pages") from e
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            raise HTTPException(422, str(e)) from e

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (_STATIC / "index.html").read_text(encoding="utf-8")

    @app.get("/api/devices")
    def devices() -> list[dict]:
        return [
            {
                "key": d.key,
                "name": d.name,
                "width": d.width,
                "height": d.height,
                "color": d.color,
                "verified": d.verified,
            }
            for d in all_devices().values()
        ]

    @app.get("/api/limits")
    def get_limits() -> dict:
        return {
            "max_upload_mb": limits.max_upload_bytes / 1e6,
            "max_files": limits.max_files,
            "max_pages": limits.max_pages,
            "accept": sorted(_ALLOWED),
        }

    @app.post("/api/preview")
    async def preview(
        files: Files,
        device: Opt = None,
        mode: Opt = None,
        colors: Opt = None,
        fill: Opt = None,
        fit: Opt = None,
        threshold: Opt = None,
        simplify: Opt = None,
        pen: Opt = None,
        pages: Opt = None,
    ) -> dict:
        opts = _options(
            device=device, mode=mode, colors=colors, fill=fill, fit=fit,
            threshold=threshold, simplify=simplify, pen=pen, pages=pages,
        )  # fmt: skip
        with tempfile.TemporaryDirectory(prefix="rmink-") as tmp:
            paths = await _save_uploads(files, Path(tmp))
            _check_pages(paths, opts.pages)
            rendered = await _run(api.render, paths, opts)

        out_pages = []
        for label, page, img in zip(
            rendered.labels, rendered.document.pages, rendered.images, strict=True
        ):
            thumb = img.copy()
            thumb.thumbnail((_PREVIEW_WIDTH, _PREVIEW_WIDTH * 4))
            buf = io.BytesIO()
            thumb.save(buf, "PNG", optimize=True)
            out_pages.append(
                {
                    # Strip the "000_" upload prefix from labels.
                    "label": re.sub(r"^\d{3}_", "", label),
                    "strokes": len(page.strokes),
                    "points": page.point_count,
                    "image": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode(),
                }
            )
        return {"device": rendered.device.key, "pages": out_pages, "warnings": rendered.warnings}

    @app.post("/api/convert")
    async def convert(
        files: Files,
        name: Opt = None,
        device: Opt = None,
        mode: Opt = None,
        colors: Opt = None,
        fill: Opt = None,
        fit: Opt = None,
        threshold: Opt = None,
        simplify: Opt = None,
        pen: Opt = None,
        pages: Opt = None,
    ) -> FileResponse:
        tmp = Path(tempfile.mkdtemp(prefix="rmink-"))
        try:
            paths = await _save_uploads(files, tmp)
            notebook = _safe_stem(name) if name else _safe_stem(files[0].filename)
            opts = _options(
                name=notebook, device=device, mode=mode, colors=colors, fill=fill, fit=fit,
                threshold=threshold, simplify=simplify, pen=pen, pages=pages,
            )  # fmt: skip
            _check_pages(paths, opts.pages)
            out = tmp / f"{notebook}.rmdoc"
            result = await _run(api.convert, paths, out, opts)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
        headers = {"X-Rmink-Warnings": str(len(result.warnings))}
        return FileResponse(
            result.path,
            media_type="application/zip",
            filename=result.path.name,
            headers=headers,
            background=BackgroundTask(shutil.rmtree, tmp, ignore_errors=True),
        )

    return app
