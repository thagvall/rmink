# rmink promo video

A 98-second, 1080×1350 (4:5) video in English and Swedish. It is rendered
frame by frame from `timeline.html` with Playwright and Chrome, then encoded
with ffmpeg.

```bash
# from the repo root, with the project venv (+ playwright, segno)
python promo/make_note.py en promo/out/note-en.jpg   # demo note "photo"
python promo/make_note.py sv promo/out/note-sv.jpg
python promo/make_face.py ~/Downloads/Tommy_porträtt_Linkedln_220531.jpg  # face scene
python promo/make_shade.py                           # the portrait in every shading style
python promo/build_data.py                           # convert with rmink → strokes.json
rmink web --port 8771 &                              # current UI for the app scene
python promo/capture_desktop.py en && python promo/capture_desktop.py sv
python promo/render.py en --stills 3,15,24,28,36,50,64,80        # quick review sheet
python promo/render.py en                            # → promo/out/rmink-promo-en.mp4
python promo/render.py sv
python promo/render.py en --cover 3.2 && python promo/render.py sv --cover 3.2
python promo/make_share.py    # → deploy/vercel/public: /video and /video/sv pages
```

`make_note.py` and `build_data.py` need the Caveat font in
`promo/out/assets/Caveat.ttf` (OFL, from github.com/google/fonts). Text lives
in `i18n.json`. The QR codes in the end card are generated with `segno`.
Facebook copy is in `post-texts.md`.
