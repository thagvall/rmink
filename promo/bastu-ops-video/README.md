# rmink: bastun, från skiss till Open PDF Studio

A captioned 60 s video in Swedish, built on the user's own sauna drawing
(rmink/Bygg/Bastu on the tablet): the first hand sketch, the clean r01 with four
questions, the answers written with the pen, r06 and r10, the drawing as a
true-scale A3 PDF, and Open PDF Studio with the layers switched off and on and
the gable measured. 16:9, 4:5 and 9:16.

What is real: the sketch strokes (Bastu r00 skiss), the pages r01, r05, r06 and
r10, the handwritten answers on r05 page 2, the PDF, and the Open PDF Studio
screenshots (2026.45.0; all layers on, then Matt, Text and Symboler off, and a
distance along the gable: 2001 mm at 1:20). What is not: the cottage, the hands
and the chat are illustrations, and the PDF is made from r10 written out again in
`pages.py`, since the drawing's JSON lives in the browser's /rounds storage and
not on disk. The right-hand panel of Open PDF Studio is cropped away: it shows
the file path and the user name.

```bash
# the notebooks, from the tablet: rmink cloud get "rmink/Bygg/Bastu/…" -o promo/out/bastu-real/rNN.rmdoc
R=promo/out/bastu-real
python promo/bygg-video/pages.py $R r01=$R/r01.rmdoc r05=$R/r05.rmdoc r06=$R/r06.rmdoc r10=$R/r10.rmdoc
python promo/bastu-ops-video/pages.py promo/out/bastu-ops $R/r00.rmdoc
# + promo/out/bastu-ops/ops-all.png, ops-1.png, ops-2.png, ops-3.png, ops-measure.png
#   (the OPS window at 1470 x 825, captured at 2x)
python promo/bastu-ops-video/render.py sv wide --stills 8,23,28,34.5,39.8,46.5,53   # review sheet
python promo/bastu-ops-video/render.py sv wide    # → promo/out/rmink-bastu-ops-sv-16x9.mp4
python promo/bastu-ops-video/render.py sv tall    # → promo/out/rmink-bastu-ops-sv-4x5.mp4
python promo/bastu-ops-video/render.py sv phone   # → promo/out/rmink-bastu-ops-sv-9x16.mp4
python promo/voice.py promo/bastu-ops-video/voice.json   # → …-alma.mp4, with Alma's voice
```
