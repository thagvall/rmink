# rmink bygg video from real tablet pages

A silent, captioned video (60 s, Swedish) of the Garage drawing in `rmink/Bygg/Garage/`,
from the hand sketch (r00) to revision 8: the clean drawing, the alternatives
A–D for the slab, the user's handwritten answer "Alt B", r02 with B on the
drawing, every revision r01–r08, new handwritten answers on r07 and r08 with
them drawn in. 16:9 and 4:5, kept zoomed out (rings point things out).

`pages.py` renders each page of the downloaded `.rmdoc` notebooks as the tablet
shows them, and saves the user's own strokes (another CrdtId author than rmink's)
as SVG paths so the video writes them again. The engine is the one in
`promo/real-video/`.

```bash
# from the repo root, with the project venv
python -c "from rmink import cloud; t = cloud.load_token(); b = '/rmink/Bygg/Garage/'
names = ['Tidigare/Garage r00 skiss'] + [f'Tidigare/Garage r0{i} · 2 frågor' for i in range(1, 8)] + ['Garage r08 · 1 fråga']
[open(f'r{i:02d}.rmdoc', 'wb').write(cloud.get(t, b + n)) for i, n in enumerate(names)]"
python promo/bygg-video/pages.py promo/out/bygg $(for i in 0 1 2 3 4 5 6 7 8; do printf "r%02d=r%02d.rmdoc " $i $i; done)
python promo/bygg-video/render.py sv wide --stills 7,13,19,26,33,40,47,53   # review sheet
python promo/bygg-video/render.py sv wide    # → promo/out/rmink-bygg-real-sv-16x9.mp4
python promo/bygg-video/render.py sv tall    # → promo/out/rmink-bygg-real-sv-4x5.mp4
```

Ring positions in `video.html` are in rm2 screen pixels (1404 × 1872).

## The device

The tablet is the reMarkable 2 from `promo/laxa-video/`: light frame, dark metal
spine on the left, grey e-paper and the collapsed toolbar button. The document
name stands below the device, and the rings that point things out are black,
because nothing on the screen has colour.
