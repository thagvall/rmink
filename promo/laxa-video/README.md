# rmink: läxan

A silent, captioned 60 s animation in Swedish: Alva, 9, and her dad do homework
at the kitchen table. Dad orders a test-mode workbook from Claude on the laptop,
Alva answers by hand, Claude reads and marks it, the next revision lands with
three right and one wrong, the Facit layer shows the thinking and Alva corrects
her answer.

The illustrations and pages are drawn in `video.html`, an SVG timeline with
`seek(t)`; the people and the pages are fictional. It follows what rmink does:
Claude with rmink runs on the computer, a test has no solutions until it is
marked, and new ink in an answered box is marked again.

```bash
python promo/laxa-video/render.py sv wide --stills 2,21,45,50   # review sheet
python promo/laxa-video/render.py sv wide    # → promo/out/rmink-laxa-sv-16x9.mp4
python promo/laxa-video/render.py sv tall    # → promo/out/rmink-laxa-sv-4x5.mp4
python promo/laxa-video/render.py sv phone   # → promo/out/rmink-laxa-sv-9x16.mp4 (stående, telefon)
```

## The device

The tablet is drawn as a reMarkable 2: grey e-paper with no colour on the screen,
a light frame with a dark metal spine on the left, and the toolbar down the left
of the screen. Facit is switched on with the layers button and the eye in the
layers panel. The page copies what rmink prints: `Rätt 1/1 p`, the grey `Facit`
label, the footer. Name and score sit beside the device, since they are the
document's name and Claude's report. The icons are drawn from a description, not
traced from a device screenshot; check them against a real toolbar.

## The voice

`voice.json` holds what is said and when. `promo/voice.py` reads it with Alma, a
Swedish Piper voice, stresses the last word of every sentence and lays the sound
on the finished videos, picture untouched:

```bash
python promo/voice.py promo/laxa-video/voice.json   # → promo/out/rmink-laxa-sv-*-alma.mp4
```

Alma is by Daniel Nylander, CC BY 4.0: credit the voice where the video is posted.
