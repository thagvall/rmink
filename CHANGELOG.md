# Changelog

## 2.0.0 (unreleased) — rmink

Rewritten as `rmink`, a pure-Python converter.

- Writes native `.rm` **v6** pages via rmscene. drawj2d and Java are no longer needed.
- New inputs: PNG/JPG/WebP/TIFF/HEIC photos and images, and SVG. Scanned PDFs are detected automatically.
- Centerline tracing: handwriting becomes single strokes, with the line width preserved.
- Colour support for Paper Pro and Paper Pro Move: colours are clustered and mapped to the pen palette.
- Device profiles for rM2, Paper Pure, Paper Pro and Paper Pro Move, plus a `calibrate` command.
- New CLI commands: `convert`, `preview`, `inspect`, `devices`, `calibrate`, `mcp`.
- MCP server and Claude skill.
- Fixes: file names no longer mangled by `strip(".pdf")`; `sizeInBytes` is now filled in; the `.content` author UUID matches the pages; no more relative template or output paths.

## 1.1.0

- Added Windows support
- Replaced pdf2image with PyMuPDF

## 1.0.0

- Initial release (Linux only)
