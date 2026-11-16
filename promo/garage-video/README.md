# rmink bygg video: the garage and alternatives A-D

A silent, captioned video (60 s, Swedish). A garage is drawn by hand with the
question "how thick, which alternatives?". Claude draws it clean, page 2 shows
alternatives A-D, the answer "Alt B" goes on the SVAR line, and r02 has B drawn in.
16:9 and 4:5.

What is real: the pages are the owner's Garage r01 and r02, and the answers are
the owner's strokes from the tablet, replayed in the order written. The
alternatives' figures, pros and cons come from page 2.

What is staged: r00 was not handwritten, so the sketch is redrawn with the same
content. The chat, the plot and the coloured layer stacks are illustrations (the
stacks are to scale, the page itself has grey hatching). The device is the
reMarkable 2 from `promo/laxa-video/`; its toolbar icons are drawn from a description.

The page images come from `promo/bygg-video/` (see its README) into
`promo/out/bygg/`.

```bash
# from the repo root, with the project venv
python promo/garage-video/render.py sv wide --stills 9,27,38,44,51   # review sheet
python promo/garage-video/render.py sv wide    # promo/out/rmink-garage-sv-16x9.mp4
python promo/garage-video/render.py sv tall    # promo/out/rmink-garage-sv-4x5.mp4
```
