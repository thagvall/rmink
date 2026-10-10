"""Crop a portrait photo for the face scene of the promo video.

Usage: python promo/make_face.py PORTRAIT.jpg [--box L,T,R,B]   → out/face.jpg

The default box fits the 1500 × 1500 LinkedIn portrait used in the video. The
photo stays out of git (out/ is ignored). Eye positions for the drawn glasses
are in build_data.py (FACE_EYES) in the same cropped pixel coordinates.
"""

import argparse
from pathlib import Path

from PIL import Image, ImageOps

OUT = Path(__file__).parent / "out"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path)
    ap.add_argument("--box", default="330,90,1250,1240", help="crop box L,T,R,B in source pixels")
    a = ap.parse_args()
    box = tuple(int(v) for v in a.box.split(","))
    img = ImageOps.exif_transpose(Image.open(a.src)).convert("RGB").crop(box)
    OUT.mkdir(exist_ok=True)
    img.save(OUT / "face.jpg", quality=95)
    print(OUT / "face.jpg", img.size)
