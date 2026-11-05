# rmink skola video from real tablet pages

A silent, captioned video (about 51 s, Swedish) made from a real workbook on the
tablet, *Plus och minus* in `rmink/Skola/Matematik/Plus och minus/`: the app's
folder view, the cover, the pupil's own handwriting (written again stroke by
stroke from the `.rm` file), *Kör nästa varv*, the marked revision r02, the
Facit layer and the results page (6 av 41 p). 16:9 and 4:5.

The pages are not redrawn: `pages.py` renders each PDF page of the downloaded
`.rmdoc` files with the ink on, as the tablet shows them. The folder view is a
screenshot of the reMarkable desktop app, saved as `promo/out/real/app-folder.png`.

```bash
# download the revisions (from the repo root, with the project venv)
python -c "from rmink import cloud; t = cloud.load_token(); b = '/rmink/Skola/Matematik/Plus och minus/Plus och minus'
open('r02.rmdoc', 'wb').write(cloud.get(t, b + '/Plus och minus r02 · 6 av 41 p'))
open('r01.rmdoc', 'wb').write(cloud.get(t, b + '/Tidigare/Plus och minus r01_2'))"
python promo/real-video/pages.py promo/out/real r01=r01.rmdoc r02=r02.rmdoc
python promo/real-video/render.py sv wide --stills 7,13,19,26,32,38,44   # review sheet
python promo/real-video/render.py sv wide    # → promo/out/rmink-skola-real-sv-16x9.mp4
python promo/real-video/render.py sv tall    # → promo/out/rmink-skola-real-sv-4x5.mp4
```

The camera positions and rings in `video.html` are in page pixels of the 200 dpi
renders (1243 × 1657); they were measured with PyMuPDF's `search_for` on the PDF.
