# rmink skola video

A silent, captioned video (about 67 s) on rmink skola: the subjects (maths,
Swedish, English, years 1–9), an everyday maths word problem with the working
written by hand, creating a test on `/rounds`, the pupil writing by hand,
handing it in with *Kör nästa varv*, the marked revision, the results page, a
wrong answer with its comment, and the hidden Facit layer. The first examples
are all right; the mistake comes later in its own chapter. Swedish and English, each in 16:9 (1920×1080) and
4:5 (1080×1350).

`video.html` is a timeline driven by `window.seek(t)`; `render.py` screenshots
it frame by frame with Playwright and Chrome and encodes with ffmpeg, like the
other promo videos. The workbook pages and the phone are drawn in HTML from
the texts in the `TX` table at the top of `video.html`; nothing else is needed
than the handwriting font `promo/out/assets/Caveat.ttf`.

```bash
# from the repo root, with the project venv (+ playwright)
python promo/school-video/render.py sv wide --stills 3,10,19,27,35,42,48,55,60   # review sheet
python promo/school-video/render.py sv wide    # → promo/out/rmink-skola-sv-16x9.mp4
python promo/school-video/render.py sv tall    # → promo/out/rmink-skola-sv-4x5.mp4
python promo/school-video/render.py en wide
python promo/school-video/render.py en tall
```

Open `video.html?t=27` through a local server (`python -m http.server -d promo`)
to look at one moment in a browser.
