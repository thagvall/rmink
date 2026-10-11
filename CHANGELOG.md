# Changelog

## 2.1.0 — 2026-10-11

- Shading: photos and portraits can keep their grey tones as stippling, a halftone dot screen, hatching, cross-hatching or pencil strokes whose pressure follows the tone (`--shading`, `--shade-density`, `--shade-contrast`; the same options in the web UI and the MCP tools).
- Web UI: a "Shading" strip shows the first photo in every style side by side; click one to preview and download it.
- Web UI: pen and line thickness are now visible next to the other options (thickness was not settable before).
- `rmink preview` takes `--pen`; the MCP tools take `pen` and `width`.
- Strokes can carry per-point pressure; the preview draws pencil lighter at low pressure.

## 2.0.6 — 2026-10-10

- Web UI: link previews. The start page has a title, a description and a share image (`/og.jpg`), so a link to rmink on LinkedIn and other sites shows a card instead of a bare "rmink".

## 2.0.5 — 2026-10-10

- Web UI: a "Watch the demo" button next to the support button opens the demo video (English or Swedish) in a dialog. `/?demo` opens it on load, `/?demo=sv` in Swedish. Set `RMINK_DEMO_URL=""` to hide it.
- Web UI on phones: a single preview uses the full width.

## 2.0.4 — 2026-10-10

- Web UI on phones: the preview comes right after the file list instead of below all the options, with a smaller empty state and two previews per row.

## 2.0.3 — 2026-10-10

- Support rmink with 100 kr: a Stripe link in the web UI (button, a dismissible note after downloads, footer), in `rmink web` and in the README. Set `RMINK_SUPPORT_URL=""` to hide it, for example in a fork.

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
