# rmink promo video

A 60-second, 1080×1350 (4:5) video in English and Swedish. It is rendered
frame by frame from `timeline.html` with Playwright and Chrome, then encoded
with ffmpeg.

```bash
# from the repo root, with the project venv (+ playwright, segno)
python promo/make_note.py en promo/out/note-en.jpg   # demo note "photo"
python promo/make_note.py sv promo/out/note-sv.jpg
python promo/build_data.py                           # convert with rmink → strokes.json
rmink web --port 8771 &                              # current UI for the app scenes
python promo/capture_app.py en && python promo/capture_app.py sv
python promo/render.py en --stills 3,20,35,56        # quick review sheet
python promo/render.py en                            # → promo/out/rmink-promo-en.mp4
python promo/render.py sv
```

`make_note.py` and `build_data.py` need the Caveat font in
`promo/out/assets/Caveat.ttf` (OFL, from github.com/google/fonts). Text lives
in `i18n.json`. The QR codes in the end card are generated with `segno`.
Facebook copy is in `post-texts.md`.
