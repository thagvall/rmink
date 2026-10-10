"""Convert the demo notes with rmink and export strokes as JSON for the video.

Usage: python promo/build_data.py   (after make_note.py has written out/note-{en,sv}.jpg)
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from rmink.api import render
from rmink.devices import COLOR_PALETTE
from rmink.geometry.transform import place
from rmink.options import ConvertOptions

HERE = Path(__file__).parent
OUT = HERE / "out"
RGB = {e.color: "#{:02x}{:02x}{:02x}".format(*e.rgb) for e in COLOR_PALETTE}

# Layout of make_note.py in source pixels (2400 x 3000).
ITEM_Y0, ITEM_STEP = 860, 300


def tag_for(cx: float, cy: float, color: str) -> str:
    if cy < 700:
        return "underline" if color == "RED" else "title"
    for i in range(4):
        top = ITEM_Y0 + i * ITEM_STEP - 40
        if top <= cy < top + 280:
            if cx < 440:
                return "tick" if color == "BLUE" else f"box{i}"
            return f"item{i}" if color != "BLUE" or cx < 1500 else "sketch"
    return "sketch"


def strokes_json(img_path: Path, device_key: str) -> dict:
    opts = ConvertOptions(device=device_key, seed=1)
    rendered = render([img_path], opts)
    device = rendered.device
    page = rendered.document.pages[0]
    w, h = Image.open(img_path).size
    pl = place(w, h, device, opts.fit, opts.margin_mm)
    strokes = []
    for s in page.strokes:
        pts = s.points
        # Back to source pixels to classify against the known note layout.
        src = (pts - [pl.offset_x, pl.offset_y]) / pl.scale
        cx, cy = src[:, 0].mean(), src[:, 1].mean()
        strokes.append(
            {
                "d": "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts),
                "w": round(float(np.median(s.widths) if s.widths is not None else s.width), 2),
                "c": RGB.get(s.color, "#000000"),
                "tag": tag_for(cx, cy, s.color.name),
                "bbox": [round(float(v), 1) for v in (*pts.min(axis=0), *pts.max(axis=0))],
            }
        )
    return {"width": device.width, "height": page.height, "strokes": strokes}


def wordmark(path: Path) -> None:
    font = ImageFont.truetype(str(OUT / "assets" / "Caveat.ttf"), 420)
    font.set_variation_by_axes([600])
    img = Image.new("RGB", (1500, 600), "white")
    ImageDraw.Draw(img).text((90, 20), "rmink", font=font, fill="black")
    img.save(path)


QR_CODES = {
    "qr-app": "https://rmink.vercel.app",
    "qr-support": "https://buy.stripe.com/7sY4gy4b1aQo0iI0SB1sQ00",
}


def qr_codes() -> None:
    import segno

    for name, url in QR_CODES.items():
        segno.make(url, error="m").save(
            OUT / f"{name}.svg", scale=10, border=2, dark="#1d1d1b", light="#ffffff"
        )


def main() -> None:
    qr_codes()
    data = {}
    for lang in ("en", "sv"):
        data[lang] = strokes_json(OUT / f"note-{lang}.jpg", "pro")
    wm = OUT / "wordmark.png"
    wordmark(wm)
    data["wordmark"] = strokes_json(wm, "pro")
    for s in data["wordmark"]["strokes"]:
        s["tag"] = "wordmark"
    (OUT / "strokes.json").write_text(json.dumps(data))
    for k, v in data.items():
        tags = {}
        for s in v["strokes"]:
            tags[s["tag"]] = tags.get(s["tag"], 0) + 1
        print(k, len(v["strokes"]), "strokes", dict(sorted(tags.items())))


if __name__ == "__main__":
    main()
