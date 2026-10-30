# Changelog

## 2.10.0 — 2026-10-30

- Workbooks get solutions and grading.
  - Claude writes a solution and points for every question. The solution is drawn under the box in rmink's single-stroke capitals, on a hidden layer "Facit" that can be shown in the layer panel.
  - Two modes: in a practice workbook (the default) the solutions are on the tablet from the start. In a test (`--mode test`, or "Prov" on `/rounds`) they come with the first graded revision.
  - Rounds grade each answer against the solution: correct, partial or wrong, with points and a short comment when it is not right. Equivalent answers count as correct, and the right method with an arithmetic slip is partial. The verdict is shown in the box.
  - A results page at the end shows the score and one row per question. Each row links to its question, and the page is listed in the contents and the outline. The revision is named e.g. "Procent r02 · 3 av 5 p".
  - Workbooks without solutions, like those from 2.9.0, work as before.

## 2.9.0 — 2026-10-30

- Workbooks: Claude writes a workbook on a topic, and you answer it by hand on the tablet.
  - The workbook is a PDF in the tablet's page format: a cover with a linked table of contents, sections that link back to the contents and on to the next section, and ruled answer boxes. The outline shows up in the tablet's contents panel.
  - The next round reads each box with new ink. Claude transcribes it word for word, without correcting it, and the new revision has the answers set as PDF text in the boxes. It goes in `rmink/<name>/` like a drawing, and the previous revision moves to `Tidigare`.
  - The handwriting that was read is either removed or kept on a hidden layer, "Handskrift", that can be shown in the layer panel. Ink outside the boxes, and ink Claude could not read, stays as it is.
  - An answer Claude is unsure of gets a "?" in the margin, and the revision is named e.g. "Bråk r02 · 1 att kolla". A tick in the box confirms the text. Writing in an answered box corrects it.
  - Ways to use it: `rmink workbook new` / `rmink workbook round`, the MCP tools `create_workbook`, `read_workbook` and `save_workbook_answers`, and the owner's `/rounds` page. See `docs/workbook.md`.
- `write_rmdoc` can write PDF documents (`pdf=`), and the writer can write hidden layers (`Page.hidden_layers`).

## 2.8.0 — 2026-10-29

- Walls in a hand sketch meet at 90°. `rectify` squares lines within 12° of horizontal or vertical (it was 4°), so a wall drawn a little askew comes out straight.
  - A corner where a horizontal and a vertical line overshoot or stop short of each other is closed.
  - The closing edge of a closed shape is squared too, so a box drawn skewed comes out as a rectangle.
  - A line with an angle dimension at one of its ends keeps its slope unless it is within 4°. Give a low roof pitch or a ramp an angle dimension to keep it.
- Rounds check the preview before saving: walls square, boxes rectangular, openings and fixtures along their walls. Claude fixes what is off and previews again. The MCP skill and `docs/sketch-to-drawing.md` describe the same rules.

## 2.7.7 — 2026-10-29

- The first listing after a cold start no longer times out. With an empty cache, rmapi reads every notebook's metadata, and 2 requests at a time could not finish within 90 s, so no cache was saved and every attempt started over. An rmapi run without a cache now gets 270 s and 6 parallel requests, once. Runs with a cache keep 2 requests and 90 s.

## 2.7.6 — 2026-10-29

- On Vercel the rmapi tree cache survives cold starts. The owner's cache is kept gzipped in a private Vercel Blob store and fetched when a new instance starts without one, so a cold start makes one request to Blob instead of about 2,900 to reMarkable Cloud. It is uploaded only when rmapi has changed it. This needs a Blob store connected to the project (`BLOB_STORE_ID` or `BLOB_READ_WRITE_TOKEN`) and `vercel-blob`, which is now part of the `rounds` extra. Without them, or if Blob fails, rmink works as before.

## 2.7.5 — 2026-10-29

- Even fewer calls to reMarkable Cloud:
  - rmapi now makes at most 2 requests at a time instead of 20 (`RMAPI_CONCURRENT`, which you can still set yourself). A sync with an empty cache gets the metadata of every notebook, and on a large account that burst set off the cloud's rate limit.
  - The owner's rmapi config is kept with the cache, so the user token is reused. Before, each run fetched a new one from the token endpoint, which allows the fewest requests.

  On an account with about 1,000 notebooks, one listing makes about 2,870 requests with an empty cache and 1 with a warm one.

## 2.7.4 — 2026-10-28

- Fewer calls to reMarkable Cloud. Each rmapi run used to start with an empty cache and fetch the metadata of every notebook on the account, so a few rounds in a row got the account rate limited (HTTP 429). The owner's token (`RMINK_CLOUD_TOKEN` on the server, or the token saved for the CLI and MCP server) now keeps rmapi's cache between runs. Other users' uploads still get a fresh temporary cache for each request.
- A 429 from the cloud says "wait a few minutes and try again" instead of rmapi's internal error.
- The Glöm button names the drawing on its second step: "Glöm Altan? Tryck igen".

## 2.7.3 — 2026-10-28

- The rounds page reaches only the `rmink` folder and what is in it. The server refuses any other path before rmapi runs, and the page's folder path starts at rmink with no way up to the tablet's root. "Annan anteckningsbok…" is now "Mappar i rmink…".
- A "Glöm" button on each drawing card on the rounds page. Two taps remove the drawing from this browser; the notebooks stay on the tablet.

## 2.7.2 — 2026-10-28

- A sketch you put in a folder under `rmink/` (for example `rmink/Bastu/Bastuskiss`) now stays in that folder. The drawing is named after the folder ("Bastu r01"), and the sketch moves to `Tidigare/` as "Bastu r00 skiss". Before, the round named the drawing after the notebook and made a new folder `rmink/Bastuskiss/`.

## 2.7.1 — 2026-10-28

- Open remarks on a large target, such as a long text or a whole wall, are marked with corner marks around it instead of a large ring that runs through other texts. The number goes at the first corner where nothing is drawn. Small targets keep their small ring.

## 2.7.0 — 2026-10-28

- Alternatives. Ask "hur tjock?" or "alternativ?" on a drawing, and the round puts 2–4 solutions on their own page after the drawing. Each one shows:
  - a small hatched section with a text for each layer
  - thickness, an estimated U-value, weight per m² and a cost level
  - pros and cons

  You choose by writing the letter on the remark's SVAR line. The next round sets `chosen` and draws that option's layers.
- Variants of typical assemblies in `assemblies.toml`:
  - platta på mark: standard, lågenergi, förstärkt, XPS, skumglas
  - yttervägg: standard, tjockare, utvändig isolering, PIR invändigt
  - altan: tryckimpregnerad, värmebehandlad, lärk, komposit

  `lookup_knowledge` lists an assembly's variants and returns each one as a ready option.
- `calculate` has `u_value(layers, kind)`: an estimated U-value with the λ-value method, counting studs and insulation as one zone and ignoring layers outside a ventilated gap. Materials have typical λ values, and there is a new material, skumglas (cellglasgranulat).
- The drawing font has · and a lower-case λ.
- Dimensions say their unit: "4800" is drawn as "4800 mm", and the title block says "Mått i mm". A dimension that already has a unit or text ("2,1 m", "45°", "c600") is drawn as written. `show_units: false` on a drawing leaves only the note in the title block. Rounds write units with every number in remarks.
- An angle's degrees move along the arc, or out from it, when a line runs where they would go, e.g. a king post down the middle of a ridge angle. They no longer sit on top of the line.

## 2.6.0 — 2026-10-28

- Angles on drawings. An angle dimension is drawn as an arc with arrows between two legs and its degrees ("38,7°"). Write "visa vinklarna" on a drawing and the round puts out the corner angles. A written angle that disagrees with the drawing by more than 2° becomes a question.
- Numbers come from code, not from Claude's head. Two new tools, in rounds and over MCP:
  - `measure` (MCP: `measure_drawing`) reads lengths, areas and corner angles off the drawing, in mm using the scale of the written dimensions.
  - `calculate` evaluates an expression safely. It covers:
    - trigonometry in degrees, hypotenuse and legs, any triangle from three sides
    - roof pitch as degrees, 1:x and percent
    - areas and volumes
    - weight from the approximate densities now in `materials.toml`
    - pieces at c/c spacing, lengths to buy, waste
    - set operations
- The drawing font has √, so a worked-out length such as "√(3600² + 1800²) ≈ 4025 mm" is drawn in full.
- A sketch archived as "Altan r00 skiss" names its drawing "Altan" when a round is run on it.
- 18 new drawing symbols for small-house plans, 33 in all:
  - el: elcentral, dubbeluttag, brandvarnare
  - VVS: WC, tvättställ, dusch, radiator, fallriktning
  - ventilation: tilluft and frånluft
  - kitchen: spis and kylskåp
  - building: trappa with walking direction, plint, räcke
  - drawing: detaljhänvisning, revisionsmärke and revisionsmoln
- A symbol catalogue, `symbols.toml`, says for each symbol:
  - what it means and which discipline and drawing types use it
  - when a drawing needs it
  - the text written next to it
  - how it usually looks when drawn by hand
  - which review rules apply

  Rounds read handwritten symbols with it ("N-pil", "GB", "fall 1:50"), and `lookup_knowledge` finds them.

## 2.5.1 — 2026-10-28

- Windows: a round on a local notebook such as `C:\ritningar\Altan.rmdoc` now names the drawing "Altan". Before, the whole path became the name, and the next round failed with "'NoneType' object has no attribute 'sketch'".

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
