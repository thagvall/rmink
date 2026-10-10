# On-device acceptance checklist

Run this per device and firmware version, then record the result in the table below.

1. `rmink calibrate -d <device> -o cal.rmdoc`, then upload the file and open it.
   - The long ticks should be 10 mm apart and the square should measure 50 mm. Allow ±1 mm over 100 mm.
   - If the scale is off, set `ink_scale` in `~/.config/rmink/devices.toml` and repeat.
2. Convert `examples/handwriting.jpg`, `examples/logo.svg` and `examples/document.pdf`
   into one notebook. Upload it.
3. On the tablet, check that:
   - [ ] the notebook opens and all pages render
   - [ ] the eraser removes parts of converted strokes
   - [ ] lasso selects and moves strokes
   - [ ] recolouring works (Pro/Move), and the logo colours look right
   - [ ] pages turn smoothly with no lag
   - [ ] the notebook syncs to the cloud and opens in the desktop app
4. After making an edit on the tablet, export the `.rmdoc` and run `rmink inspect` on it to compare.

| Device | Firmware | Scale OK | Editing OK | Notes |
|---|---|---|---|---|
| reMarkable 2 | | not measured | opens, eraser, lasso, stroke width OK (2026-10-10) | v6 + .rmdoc confirmed |
| Paper Pure | | | | |
| Paper Pro | | | | |
| Paper Pro Move | | | | |
