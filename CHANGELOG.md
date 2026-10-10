# Changelog

## 2.0.2 — 2026-10-10

- Fix: downloads from the web UI are served as `application/octet-stream` instead of `application/zip`. Safari on macOS unpacked the notebook into a folder, and once that folder was zipped again the tablet could not import it.
- New `rmink repair` command and a "Repair a notebook" option in the web UI. They turn such a re-zipped folder back into a working `.rmdoc`.

## 2.0.1 — 2026-10-10

- Web UI: large photos are shrunk in the browser before upload (at most 3200 px, as JPEG). Uploads get faster, and photos fit the request size limit of hosted deployments.
- Web UI: a clear message when the upload is over the server's limit.
- Ready-made Vercel deployment in `deploy/vercel/`; see `docs/hosting.md`.

## 2.0.0 — 2026-10-10 — rmink

Rewritten as `rmink`, a pure-Python converter.

- Writes native `.rm` **v6** pages via rmscene. drawj2d and Java are no longer needed.
- New inputs: PNG/JPG/WebP/TIFF/HEIC photos and images, and SVG. Scanned PDFs are detected automatically.
- Centerline tracing: handwriting becomes single strokes, with the line width preserved.
- Colour support for Paper Pro and Paper Pro Move: colours are clustered and mapped to the pen palette.
- Device profiles for rM2, Paper Pure, Paper Pro and Paper Pro Move, plus a `calibrate` command. The output was tested on a reMarkable 2: notebooks open, and erasing, lasso and stroke width work. Pure, Pro and Move are still marked beta.
- New CLI commands: `convert`, `preview`, `inspect`, `devices`, `calibrate`, `mcp`.
- MCP server and Claude skill.
- Licensed under AGPL-3.0-or-later. An optional support link (Stripe Payment Link via `RMINK_SUPPORT_URL`) appears in the web UI and README.
- Web UI (`rmink web`) with drag and drop, live preview and download. It ships with a Dockerfile and configurable limits for hosting.
- Fixes: file names no longer mangled by `strip(".pdf")`; `sizeInBytes` is now filled in; the `.content` author UUID matches the pages; no more relative template or output paths.

## 1.1.0

- Added Windows support
- Replaced pdf2image with PyMuPDF

## 1.0.0

- Initial release (Linux only)
