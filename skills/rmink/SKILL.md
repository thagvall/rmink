---
name: rmink
description: Convert images, photos of handwriting or sketches, SVGs, logos and PDFs into native, editable reMarkable ink (.rmdoc notebooks with real pen strokes, not embedded images). Use when the user wants something "on my reMarkable", "as ink", "editable on the tablet", or asks to turn a picture/scan/PDF into a reMarkable notebook for rM2, Paper Pure, Paper Pro or Paper Pro Move.
---

# rmink: anything → editable reMarkable ink

`rmink` turns inputs into a `.rmdoc` notebook whose pages are v6 pen strokes, so
the result can be erased, lassoed, moved and recoloured on the tablet.

## Setup

```bash
uvx rmink --help          # or: pip install rmink
```

If the `rmink` MCP server is connected, prefer its tools (`preview_ink`,
`convert_to_rmdoc`, `inspect_rmdoc`); otherwise use the CLI below.

## Workflow

1. **Ask which device** if unknown: `rm2` (default), `pure`, `pro` (colour),
   `move` (colour). Colour is only kept on `pro`/`move`.
2. **Pick a mode** from the input:
   | Input | Mode |
   |---|---|
   | Photo/scan of handwriting, sketch, whiteboard | `centerline` (or `auto`) |
   | Logo, icon, clip art, solid shapes | `auto` or `outline` |
   | PDF/SVG with real text and vector drawings | `vector` (or `auto`) |
   | Scanned PDF (image only) | `auto` (detects it) or `centerline` |
3. **Preview first**, look at the PNG, then tune:
   ```bash
   rmink preview INPUT -d pro -o /tmp/preview.png
   ```
   - Missing faint strokes → `--threshold 200` (higher = more ink)
   - Background noise / shadows as ink → `--threshold 120`
   - Too many points / jagged → `--simplify 1.2`
   - Thick marker strokes traced as outlines → raise `--thick-px`
   - Fills look like stripes you don't want → `--fill outline` or `--fill none`
   - Photo or portrait that should keep its grey tones → `--shading stipple`,
     `halftone`, `hatch`, `crosshatch` or `pencil`; `--shade-density 0.6` for fewer
     dots/lines, `--shade-contrast 1.4` for punchier shadows
   - Pen and line width: `--pen fineliner|ballpoint|marker|pencil`, `--width 3`
4. **Convert**:
   ```bash
   rmink convert INPUT... -d pro -o notebook.rmdoc --name "My notes" --preview notebook.png
   ```
   Multiple inputs become one notebook; each image / PDF page is a page.
   `--pages 1-3,7` limits PDF pages; `--fit width` keeps tall content readable
   (the page extends downwards).
5. **Check** with `rmink inspect notebook.rmdoc` (stroke/point counts, pens).
   Keep pages under ~150k points; the converter enforces `--max-points`.
6. **Tell the user how to transfer it**: connect the tablet by USB, enable
   Settings → Storage → USB web interface, open http://10.11.99.1 and drag the
   `.rmdoc` in (100 MB limit), or drag it into the reMarkable desktop app.

## Notes

- Paper Pro / Move / Pure profiles are marked beta until their scale is
  verified; `rmink calibrate -d pro` writes a ruler page to check on hardware.
- Text in vector PDFs becomes outlined, hatched glyphs (not typed text).
- Never claim the file is on the tablet — rmink only writes the file.
