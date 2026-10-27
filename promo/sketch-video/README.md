# Sketch to drawing pitch video

A silent, captioned video (about 2 min 40 s) that pitches the sketch-to-drawing
idea: the problem, the loop, then one chapter per scenario (clean drawing,
review round, variants, detail view, paper sketch, export) and what is built.
Swedish and English, each in 16:9 (1920×1080) and 4:5 (1080×1350).

`video.html` is a timeline driven by `window.seek(t)`; `render.py` screenshots
it frame by frame with Playwright and Chrome and encodes with ffmpeg, like the
promo video in `promo/`. All strokes come from the demo data, so build that
first (see `promo/sketch-demo/README.md`).

```bash
# from the repo root, with the project venv (+ playwright)
python promo/sketch-video/render.py sv wide --stills 4,22,40,58,90,122   # review sheet
python promo/sketch-video/render.py sv wide    # → promo/out/rmink-sketch-sv-16x9.mp4
python promo/sketch-video/render.py sv tall    # → promo/out/rmink-sketch-sv-4x5.mp4
python promo/sketch-video/render.py en wide
python promo/sketch-video/render.py en tall
```

Texts for both languages are in the `TX` table at the top of `video.html`.
The handwriting font is `promo/out/assets/Caveat.ttf`, as for the promo video.

## On the hosted site

`make_site.py` publishes the demo and the videos as a separate entry on
rmink.vercel.app, without touching the app's start page:

```bash
python promo/sketch-demo/translate_en.py       # English demo template (template-en.html)
python promo/sketch-video/render.py sv tall --cover 51 && python promo/sketch-video/render.py en tall --cover 51
python promo/sketch-video/make_site.py         # pages, videos and posters in deploy/vercel/public
python promo/sketch-video/make_site.py --shots # share images (1200 × 627) from the built pages
```

| URL | Page |
|---|---|
| `/sketch`, `/sketch/sv`, `/skiss` | interactive demo with "Watch the video" |
| `/sketch?demo`, `/sketch/sv?demo=sv` | the same with the 4:5 video open |
| `/sketch/video`, `/sketch/video/sv` | share links for LinkedIn: preview tags, then the page with the video open |

The routes are rewrites in `deploy/vercel/vercel.json`. LinkedIn caches link
previews; the share image names carry a content hash, and the Post Inspector
(linkedin.com/post-inspector) refreshes a cached card.
