# rmink

**Turn images, photos of handwriting, SVGs, logos and PDFs into native, editable
reMarkable ink.**

Most tools put a picture *behind* your notes. rmink writes real pen strokes
(`.rm` v6, the format of firmware 3.x) into a `.rmdoc` notebook, so on the
tablet you can erase part of a converted sketch, lasso a word and move it, or
recolour a diagram.

| Input | What happens |
|---|---|
| Photo or scan of handwriting, sketches, whiteboards | Paper shadows are removed, the ink is skeletonised, and each line becomes **one stroke along its centre**, with the line's width |
| Logos, icons, illustrations (PNG/JPG) | Colours are clustered and mapped to the tablet's pen colours. Thin lines are traced; solid areas are outlined and hatched |
| Vector PDF / SVG | Paths become strokes directly. Text glyphs are outlined and filled |
| Scanned PDF | Detected automatically and traced like a photo |

Supported devices: **reMarkable 2**, **Paper Pure**, **Paper Pro** (colour)
and **Paper Pro Move** (colour).

## Install

```bash
pip install rmink            # or run without installing: uvx rmink ...
pip install 'rmink[mcp]'     # + MCP server for Claude and other agents
pip install 'rmink[heic]'    # + iPhone HEIC photos
```

Every command also works without installing anything: `uvx rmink convert notes.jpg`
(needs [uv](https://docs.astral.sh/uv/)).

## Use

```bash
rmink convert notes.jpg                          # -> notes.rmdoc for reMarkable 2
rmink convert logo.png -d pro --preview logo.png # colour, plus a PNG preview
rmink convert paper.pdf --pages 1-3 --fit width -o paper.rmdoc
rmink convert a.jpg b.jpg c.pdf --name "Week 41" # several inputs -> one notebook
rmink preview sketch.jpg -o preview.png          # preview only, no notebook
rmink inspect paper.rmdoc                        # pages, strokes, pens, colours
rmink repair broken.rmdoc.zip                    # fix a notebook a Mac unpacked and re-zipped
rmink devices                                    # device profiles
rmink calibrate -d pro                           # ruler page for checking scale
```

Useful options: `--mode auto|vector|centerline|outline`,
`--colors auto|mono|N`, `--pen fineliner|ballpoint|marker|pencil`,
`--width <px>`, `--fill hatch|outline|none`, `--threshold auto|0-255`,
`--simplify <px>`, `--max-points <n>`.

**Shading.** Photos and portraits can keep their grey tones:
`--shading stipple` (dots, denser where darker), `halftone` (a dot screen with
growing dots), `hatch` (lines, closer where darker), `crosshatch` (more line
directions where darker) or `pencil` (pencil strokes whose pressure follows the
tone). Tune with `--shade-density` and `--shade-contrast`. The web UI shows a
small preview of every style side by side, so you can pick one before you
download. Run `rmink convert --help` for the full list.

### Web UI

```bash
pip install 'rmink[web]'
rmink web                     # opens http://localhost:8765
```

Drop files on the page, choose a device and options, and the preview updates
as you change them. When it looks right, download the `.rmdoc`.

To host it for others, deploy `deploy/vercel/` on Vercel (see [hosting](https://github.com/thagvall/rmink/blob/main/docs/hosting.md)), or use the included `Dockerfile`
(`docker build -t rmink . && docker run -p 8765:8765 rmink`). The per-request
limits can be tightened with `RMINK_MAX_UPLOAD_MB`, `RMINK_MAX_FILES`,
`RMINK_MAX_PAGES`, `RMINK_TIMEOUT_S` and `RMINK_CONCURRENCY`; see
`src/rmink/web/__init__.py`. Uploads are deleted as soon as the request
finishes.

**Getting it onto the tablet:** connect the tablet by USB, turn on
*Settings → Storage → USB web interface*, open <http://10.11.99.1> and drag the
`.rmdoc` in (100 MB limit). Alternatively, drag it into the reMarkable desktop app.

**Or send it through the reMarkable Cloud:** if
[rmapi](https://github.com/ddvk/rmapi) is installed (or `RMINK_RMAPI` points at
it), the web UI shows a *Send to reMarkable* button. The first time, it asks
for a one-time code from <https://my.remarkable.com/device/browser/connect>;
the connection is remembered in your browser. Notebooks land in the root of
*My files*.

If a Mac turned the download into a folder or a `.zip` and the tablet will not
import it, run `rmink repair` on it, or use *Repair a notebook* in the web UI.

## Use with Claude

**MCP server** (Claude Code, Claude Desktop, any MCP client):

```bash
claude mcp add rmink -- uvx --from 'rmink[mcp]' rmink mcp
```

Tools:

- `preview_ink` returns a PNG, so the model can look at the result and tune the options before converting.
- `convert_to_rmdoc` writes the notebook.
- `inspect_rmdoc`, `list_devices` and `calibration_sheet`.

**Skill:** copy `skills/rmink/` into `~/.claude/skills/`. It covers choosing a
mode, the preview → tune → convert loop, and transferring the file.

## Workbooks

Claude writes a workbook on a topic: a PDF in the tablet's page format with a
linked table of contents, short sections and ruled answer boxes. You write the
answers by hand. The next round reads each box, has Claude transcribe it word
for word, grades it against Claude's solution, and sends a new revision with the
answers set as PDF text and a results page at the end. The handwriting is
either removed or kept on a hidden layer. The solutions are on a hidden
"Facit" layer, from the start in practice mode or after grading in a test.
Questions can also be multiple choice ("choose one" or "choose all that
apply"). rmink reads and grades the crosses itself. In practice mode a wrong
answer gets a hint and a new attempt, up to three in all.

```bash
rmink workbook new "Fractions for year 5" --name Fractions --mode test   # needs rmink[rounds]
rmink workbook round Fractions --ink keep
```

The MCP tools are `create_workbook`, `read_workbook` and `save_workbook_answers`.
The owner's `/rounds` page can do the same. Details are in
[docs/workbook.md](https://github.com/thagvall/rmink/blob/main/docs/workbook.md) (Swedish).

## How it works

```
input ─► ingest ─┬─ vector (PDF→SVG with text as paths, SVG) ─► paths → strokes, fills → outline + hatch
                 └─ raster (photos, scans, images)
                       background normalisation + Otsu/Sauvola → ink mask
                       colour clustering (CIELAB k-means) → device palette
                       per component: thin → skeleton graph → centerline strokes (+ width)
                                      thick → contours + hatching
                       optional shading: tone map → dots / dot screen / hatching / pencil pressure
        ─► simplify (RDP), smooth (Chaikin), chain, reading order, point budget
        ─► .rm v6 via rmscene ─► .rmdoc (content/metadata/thumbnails)
```

Diagrams of the whole app and the building knowledge base (in Swedish, built
from the code) are in [`docs/diagrams/`](docs/diagrams/README.md).

Code layout: `src/rmink/` contains `ingest/`, `extract/`, `geometry/`,
`color/`, `writer/rm_v6.py`, `package/rmdoc.py`, `render/preview.py`, `api.py`,
`cli.py`, `mcp_server.py` and `web/` (FastAPI plus a single static page).

## Device notes

The reMarkable 2 coordinate system is well known: 1404×1872, with x measured
from the page centre. The other profiles assume the same scene unit on a
larger canvas, and are marked *beta* until that is confirmed on hardware.
Print `rmink calibrate -d <device>` and measure it; if it is off, override the
profile in `~/.config/rmink/devices.toml`:

```toml
[pro]
ink_scale = 0.99
```

See [docs/device-acceptance.md](https://github.com/thagvall/rmink/blob/main/docs/device-acceptance.md) for the on-device checklist.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest            # unit, round-trip, fidelity, CLI and MCP tests
python examples/make_examples.py
```

Releases: see [docs/releasing.md](https://github.com/thagvall/rmink/blob/main/docs/releasing.md).

The fidelity tests render the *parsed* output and compare it with the source
ink, checking precision and recall within 3 px. That way the tests cover the
writer as well as the tracing.

## Support

rmink is free, and that is not going to change. If it saves you time and you
want to say thanks, you can [support it with 100 kr](https://buy.stripe.com/7sY4gy4b1aQo0iI0SB1sQ00) via Stripe.
The money pays for the hosted web service and further development. Starring
the repo and reporting how it works on your tablet in an
[issue](https://github.com/thagvall/rmink/issues) helps a lot too.

## License

rmink is free software under the [GNU AGPL-3.0](https://github.com/thagvall/rmink/blob/main/LICENSE) or later. This is
required by PyMuPDF, which is AGPL. If you host a modified version as a web
service, you have to offer its source code to the people who use it.
Hosted instances set `RMINK_SOURCE_URL` so the footer links to the source.

Not affiliated with or endorsed by reMarkable AS. "reMarkable" is a trademark
of reMarkable AS.

## History

This project began as [`pdf2rmnotebook`](https://github.com/simon-rechermann/py_pdf2rmnotebook) by Simon Rechermann, a wrapper around drawj2d that wrote
v5 pages in black fineliner only. That version lives on at the tag `v1.1.0`.
rmink 2.0 replaces it with a pure-Python pipeline: no Java, v6 output, colour,
image input, centerline tracing and an agent interface.
