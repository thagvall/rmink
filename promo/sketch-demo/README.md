# Sketch to drawing demo page

The animated page that shows the sketch-to-drawing scenarios (see
`docs/sketch-to-drawing.md`). Every stroke on it comes from rmink: the scripts
build sketches, run them through the real reading, grouping, rendering and
photo conversion code, and write the results as JSON for `template.html`.

Rebuild from the repo root with the project's virtualenv:

```bash
cd promo/sketch-demo
PY=../../.venv/bin/python
$PY photo.py forrad.jpg forrad.json   # synthetic phone photo of a paper sketch
$PY gen.py data.json                  # sketch, groups, r1, markings, r2
$PY gen2.py data2.json data.json      # variants A and B, r3
$PY gen3.py data3.json                # detail view, r4 and r5
$PY gen4.py data4.json                # paper sketch through photo conversion
$PY gen5.py data5.json                # SVG export, mm geometry, DXF
python3 build.py .                    # writes skiss-till-ritning.html
```

Each script reruns the ones before it, so `gen5.py` alone also refreshes the
data the earlier steps need. The variants, the detail view and the PDF and DXF
in the export demo are drawn by hand in the drawing model; rmink does not make
them yet.
