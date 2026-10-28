# Changelog

## 2.5.0 — 2026-10-28

- Revision rounds know Swedish building practice. Claude's cached reference now includes:
  - terms and abbreviations, including handwritten variants ("gips 13" → Gips typ A 12,5)
  - materials with the quality classes a drawing must state (C24, NTR A/AB, gips typ A/F/H, betong C25/30 + XC2, EPS 100 …)
  - typical small-house assemblies (YV1, IV1, PL1, ALT1 …)
  - review rules with their source: BFS 2024 (which replaced BBR), PBL/PBF and the Electrical Safety Act. Practice values and permit rules are raised as questions, never as errors.
- A new tool, `lookup_knowledge`, returns full entries with exact values and sources, both in rounds and over MCP; `drawing_reference` includes the summary. The data lives in `src/rmink/knowledge/data/*.toml`; see `docs/knowledge.md`.
- Long remarks and change-log lines in the title block wrap onto the next line instead of being cut off at 70 characters.
- The drawing font has §, –, ;, …, ≤, ≥, ≈, λ and É, so rule references such as "(BFS 2024:9 2 kap. 11 §)" are drawn in full.

## 2.4.1 — 2026-10-27

- `/rounds`: the file browser opens in the `rmink` folder, and "Välj anteckningsbok" on a drawing opens that drawing's own folder.
- `/rounds`: only a wrong key returns to the key prompt. An expired reMarkable connection is now shown as an error instead of logging out in a loop.
- `/rounds`: a slow listing of a folder you already left no longer replaces the folder you opened.

## 2.4.0 — 2026-10-27

- Revision rounds are filed like a drawing folder on a building project:
  - each drawing gets its own folder, `rmink/<drawing>/`, holding only the revision to mark up
  - earlier revisions and the original sketch move to `Tidigare/`
  - revisions are named `Altan r03 · 2 frågor`: two-digit revision numbers keep name order and time order the same, and the count shows which revisions wait for answers
  - rmink only moves notebooks that are in the `rmink` folder
- Every open remark under ANMÄRKNINGAR gets a SVAR line to write the answer on, and the title block shows the revision date.
- `/rounds` lists your drawings, each with its latest revision, open questions, history and a one-tap "Kör nästa varv". New sketches are picked from the `rmink` folder, with the full file browser as a fallback.
- `rmink round Altan` runs the next round on the drawing's latest revision. `rmink draw --send` and the MCP tool `save_revision(send=True)` file revisions the same way.

## 2.3.1 — 2026-10-27

- `/rounds` keeps drawings between rounds in the browser, so a hosted server needs no database. Upstash Redis is still used when it is configured.

## 2.3.0 — 2026-10-27

- Sketch to clean drawing (experimental, not yet verified on a tablet): read a hand-drawn page back from a notebook or the reMarkable Cloud, let Claude interpret it, and get a clean revision with straight lines, dimension lines, symbols, a legend and a title block. Mark the revision up on the tablet, and the next round picks up only your new marks. Colour tablets show categories in colour; rm2 and Paper Pure use line types. MCP tools: `read_sketch`, `drawing_reference`, `render_drawing_preview`, `save_revision`, `get_drawing`. CLI: `rmink sketch` and `rmink draw`. See `docs/sketch-to-drawing.md`.
- `rmink cloud connect|ls|get|put`, and the MCP tools `cloud_connect` and `cloud_list`. The CLI and MCP server keep the token in `~/.config/rmink/cloud.toml`.
- Notebooks can have more than one layer per page. Single-layer output is unchanged.
- Revision rounds with Claude (experimental): `rmink round DOCUMENT` and, on a hosted server configured for it, an owner-only `/rounds` page. Pick a marked-up notebook and the next clean revision is sent to the tablet, with questions as open remarks on the drawing. Needs `rmink[rounds]` and an Anthropic API key; drawings are kept in `~/.config/rmink/drawings` or Upstash Redis.

## 2.2.1 — 2026-10-24

- Web UI: the shading previews are about twice as fast, so they also appear for camera photos in Safari on iPhone. If they still fail, the strip says why instead of disappearing.

## 2.2.0 — 2026-10-24

- Web UI: "Send to reMarkable" uploads the notebook straight to the reMarkable Cloud, so it syncs to the tablet without USB. It uses [rmapi](https://github.com/ddvk/rmapi) (set `RMINK_RMAPI` or have `rmapi` on the PATH; the button is hidden otherwise). The first time it asks for a one-time code from my.remarkable.com; the connection is kept only in the browser. Notebooks land in *My files*, and a taken name gets `_2`, `_3` and so on.

## 2.1.1 — 2026-10-11

- Web UI on phones: a "Take a photo" button opens the camera, and the photo joins the file list like any other upload. It is named by date and time, because iOS calls every camera shot image.jpg.
- Web UI on phones: the upload area says "Choose files" instead of "Drop files here".

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
