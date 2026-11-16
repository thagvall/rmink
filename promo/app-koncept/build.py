"""Build promo/app-koncept/index.html (the clickable app concept) from index.src.html:
the real skola catalog and two real rmink pages go in as data.

Usage: python promo/app-koncept/build.py
"""

import base64
import io
import json
import tomllib
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = ROOT / "promo" / "out"


def jpeg(path: Path, width: int, crop: float = 1.0) -> str:
    im = Image.open(path).convert("RGB")
    im = im.crop((0, 0, im.width, int(im.height * crop)))
    im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def catalog() -> list[dict]:
    data = tomllib.loads((ROOT / "src/rmink/workbook/data/skola.toml").read_text())
    return [
        {"title": g["title"], "area": g["area"], "folder": g["folder"], "description": g["description"],
         "topics": [{"title": t["title"], "grades": t["grades"]} for t in g["topic"]]}
        for g in data["group"]
    ]  # fmt: skip


html = (HERE / "index.src.html").read_text()
html = html.replace("{{CATALOG}}", json.dumps(catalog(), ensure_ascii=False))
html = html.replace("{{IMG_SKOLA}}", jpeg(OUT / "real/r01-p02-facit.png", 620, crop=0.62))
html = html.replace("{{IMG_BYGG}}", jpeg(OUT / "ops/sheet-ink.png", 640))
(HERE / "index.html").write_text(html)
print(len(html) // 1024, "kB")
