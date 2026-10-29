---
name: rmink
description: Convert images, photos of handwriting or sketches, SVGs, logos and PDFs into native, editable reMarkable ink (.rmdoc notebooks with real pen strokes, not embedded images), and the other way round, turn a hand sketch made on the tablet (2D drawing with measurements, symbols, legend) into a clean, interpreted drawing revised in rounds. Use when the user wants something "on my reMarkable", "as ink", "editable on the tablet", asks to turn a picture/scan/PDF into a reMarkable notebook for rM2, Paper Pure, Paper Pro or Paper Pro Move, or wants a tablet sketch "cleaned up", "redrawn" or "digitised".
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

## Sketch → clean drawing (the other direction)

The user sketches a 2D drawing on the tablet (walls, beams, written lengths and
angles, symbols, arrows, a legend) and wants a clean, interpreted version back,
then marks that up in rounds. MCP tools: `read_sketch`, `drawing_reference`, `lookup_knowledge`,
`calculate`, `measure_drawing`,
`render_drawing_preview`, `save_revision`, `get_drawing`, plus `cloud_connect` /
`cloud_list`. CLI: `rmink cloud connect|ls|get|put`, `rmink sketch`, `rmink draw`.

1. **Get the sketch.** A local `.rmdoc`, or the cloud: `cloud_list`, then
   `read_sketch("/Altan", page=1, device="rm2")`. If not connected, ask the user
   for a one-time code from https://my.remarkable.com/device/browser/connect and
   call `cloud_connect`.
2. **Interpret.** Look at the numbered image and the group JSON together.
   Long strokes come with fitted `line`/`polyline`/`circle`/`arc` geometry: copy
   those coordinates into elements. Groups of `shape: "mark"` are handwriting,
   arrowheads or small symbols: read them from the image. Decide per group what
   it is: an element (and its category: structure, hidden, electrical…), a
   dimension (the written number plus the line it measures), a symbol, legend
   text, or a remark. Read `drawing_reference` once for the JSON format and the
   Swedish building knowledge (terms, materials with classes, assemblies, rules).
   Write materials the way a builder would ("gips 13" → Gips typ A 12,5) and ask
   when a required class is missing. Call `lookup_knowledge` for exact rule
   values and their source (BFS, PBL/PBF, ElSL) before citing one; practice
   values and permit rules are questions, never errors.
   The reference lists each symbol kind with its handwritten variants (N-pil,
   GB, TL/FL, fall 1:50); put the text written next to a symbol in its `label`.
   If the sketch has a legend, use it for symbol meanings and put it in
   `legend`. Ask the user about anything you cannot read rather than guessing.
3. **Check.** `render_drawing_preview` straightens lines, joins corners and
   compares written measurements with drawn lengths. Walls in a hand sketch
   meet at 90° unless a written angle says otherwise: lines within 12° of
   horizontal or vertical are squared, and a corner that overshoots or stops
   short is closed. A line meant to slope less than that (a roof pitch, a ramp)
   needs an angle dimension at one of its ends to keep its angle. Look at the
   preview before saving: walls square, boxes rectangular, openings and
   fixtures along their walls; fix and preview again. Show the preview; mention
   dimensions marked inconsistent (they are often a mis-read number, or a real
   error in the sketch worth pointing out). Never work out angles, lengths,
   areas, weights or quantities by hand: `measure_drawing` reads them from the
   geometry and `calculate` does the arithmetic (degrees, hypot, triangle,
   slope/pitch, area, volume, weight, count at c/c, sets). Angles the user
   wants to see go in `angles` as arcs; empty text shows the drawn angle.
   For "which one / how thick?", put 2–4 options in `alternatives` (an
   assembly's variants from `lookup_knowledge` come as ready options, lettered
   A, B, C …); they are drawn on a page after the drawing, and the user writes
   the letter on the SVAR line of the remark that asks.
4. **Save and send.** `save_revision(drawing, send=True)` writes
   "<name> r<N>" with the clean page first, the original sketch after it, and an
   empty "Kommentarer" layer for markings.
5. **Next round.** The user rings, crosses, arrows or annotates the revision
   on the tablet. `get_drawing(name)` + `read_sketch("/<name> r<N>",
   since_drawing=name)` returns only the new marks. Map each to the element ids
   it points at; apply clear edits (moved line, changed measurement), keep
   questions as `annotations` with status "open", resolve old ones
   ("accepted"/"rejected"), bump `revision`, append a `log` line, save again.

Colour: on `pro`/`move` categories keep their colours (electrical red, plumbing
blue, changes green, remarks magenta); on `rm2`/`pure` they become black/grey
with dashed, dotted and dash-dot lines and different widths.

## Notes

- Paper Pro / Move / Pure profiles are marked beta until their scale is
  verified; `rmink calibrate -d pro` writes a ruler page to check on hardware.
- Text in vector PDFs becomes outlined, hatched glyphs (not typed text).
- Never claim the file is on the tablet unless `send`/`cloud put` reported it
  as sent; otherwise rmink only writes the file.
