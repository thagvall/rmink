"""Render the portrait in every shading style for the shading scene.

Usage: python promo/make_shade.py   (after make_face.py has written out/face.jpg)
Writes out/shade-<style>.png, cropped to the portrait on the page.
"""

from pathlib import Path

from rmink.api import style_previews
from rmink.options import ConvertOptions

HERE = Path(__file__).parent
OUT = HERE / "out"
WIDTH = 600


def main() -> None:
    for p in style_previews(OUT / "face.jpg", ConvertOptions(device="rm2")):
        img = p.image
        # Crop the white page margins around the portrait.
        bbox = img.convert("L").point(lambda v: 255 if v < 250 else 0).getbbox() or (0, 0, *img.size)
        img = img.crop(bbox)
        img = img.resize((WIDTH, round(img.height * WIDTH / img.width)))
        img.save(OUT / f"shade-{p.style.value}.png", optimize=True)
        print(p.style.value, p.strokes, "strokes", img.size)


if __name__ == "__main__":
    main()
