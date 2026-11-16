# rmink bygg video: the sauna

A silent, captioned video (60 s, Swedish). Kim sketches a sauna indoors at the
cottage, Claude draws it clean and asks two questions, Kim answers on the SVAR
lines, and r02 goes to a meeting with the carpenter. The carpenter rings the
sauna door and writes "utåt", and r03 turns it, before the firm builds from r03.
16:9 and 4:5.

Kim, the firm, the sketch and the handwriting are made up. The pages are not
photos of a tablet, but they are rmink's own output: `pages.py` writes the
drawing as JSON, as Claude would, and builds r01-r03 with `build_revision`.
Nothing is sent or saved to the drawings folder. The device is the reMarkable 2
from `promo/laxa-video/`; its toolbar icons are drawn from a description.

```bash
# from the repo root, with the project venv
python promo/bastu-video/pages.py promo/out/bastu
python promo/bastu-video/render.py sv wide --stills 9,25,31,47,52   # review sheet
python promo/bastu-video/render.py sv wide    # promo/out/rmink-bastu-sv-16x9.mp4
python promo/bastu-video/render.py sv tall    # promo/out/rmink-bastu-sv-4x5.mp4
```

Positions on the page are in rm2 screen pixels (1404 x 1872).
