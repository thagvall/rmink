# rmink: ritningen på bygget (Open PDF Studio)

A silent, captioned 60 s video in Swedish: the Garage drawing as a true-scale A3
sheet, `rmink sheet send` lays it on the rm2 in landscape, the pen writes on it,
`rmink sheet pull` brings the ink back into the PDF, and Open PDF Studio shows
the ink on its own layer and the wall stroke as a measurement (2607 mm, 1:25).

Everything is real: the tablet pages and the 20 strokes come from
`output/ark/liggande/Garage A3 liggande hämtad.rmdoc` (rewritten in the order
written), the returned sheet is `… med bläck med mängder.pdf`, and the Open PDF
Studio pictures are screenshots of OPS 2026.45.0 on the Mac with that file open
(the layers shots are cropped so the file path in Egenskaper does not show).

```bash
L=output/ark/liggande
python promo/ops-video/pages.py promo/out/ops "$L/Garage A3 liggande hämtad.rmdoc" "$L/Garage A3 liggande.pdf"
# + promo/out/ops/sheet-ink.png (page 1 of the pulled PDF, 150 dpi, annots on)
# + promo/out/ops/ops-layers.png, ops-layers-off.png, ops-measure.png (OPS window at 2x)
python promo/ops-video/render.py sv phone --stills 2,15.8,24,35,41,48,56   # review sheet
python promo/ops-video/render.py sv phone   # → promo/out/rmink-ops-sv-9x16.mp4
python promo/ops-video/render.py sv wide    # → promo/out/rmink-ops-sv-16x9.mp4
```

Ring positions in `video.html` are in screenshot px (2x the OPS window, 1470×832).
