"""Build docs/rmink-dokumentation.pdf from the diagrams and their READMEs.

    python docs/diagrams/pdf.py            # needs Google Chrome (or chromium)

The texts come from verksamhet/README.md and teknik/README.md, the pictures are
the exported .svg files (vector, so they zoom), and the header carries the
handwritten rmink wordmark from promo/out/strokes.json. The PDF is interactive:
a clickable table of contents, bookmarks, a link back to the contents on every
page and each diagram links to its full-size SVG on GitHub.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "docs" / "rmink-dokumentation.pdf"
GITHUB = "https://github.com/thagvall/rmink/blob/main/docs/diagrams"
CHROMES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "google-chrome",
    "chromium",
    "chromium-browser",
)


@dataclass
class Diagram:
    num: str
    title: str
    text: list[str]
    svg: Path
    group: str = ""
    src: Path | None = None  # the svg cropped to its drawing
    anchor: str = ""
    page: int = 0
    landscape: bool = True


@dataclass
class Part:
    key: str
    title: str
    intro: list[str]
    diagrams: list[Diagram] = field(default_factory=list)
    anchor: str = ""
    page: int = 0


# --- markdown ---------------------------------------------------------------


def inline(s: str) -> str:
    """The inline markdown the READMEs use: code, bold and links."""
    s = html.escape(s, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    # Links between the READMEs jump to that part; other relative links have no target in the PDF.
    s = re.sub(r"\[[^\]]+\]\(\.\./(verksamhet|teknik)/README\.md\)",
               lambda m: f'<a href="#del-{m.group(1)[:4].replace('tekn', 'tek')}">{m.group(1).capitalize()}</a>', s)
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)


def blocks(lines: list[str]) -> list[str]:
    """Paragraphs and bullet lists as HTML; code blocks and build notes are left out."""
    out, para, items, code = [], [], [], False
    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(i)}</li>" for i in items) + "</ul>")
            items.clear()
    for line in lines:
        if line.startswith("```"):
            code = not code
            flush()
            continue
        if code:
            continue
        if line.startswith("- "):
            if para:
                flush()
            items.append(line[2:])
        elif not line.strip():
            flush()
        else:
            para.append(line.strip())
    flush()
    # The READMEs end their intro with how to rebuild; that belongs in the repo, not the document.
    return [b for b in out if not re.search(r"build\.py|Bygg om|byggs av|Kommandot|skrivs över|Diagrammen byggs", b)]


def parse(path: Path, key: str, title: str) -> Part:
    lines = path.read_text().splitlines()[1:]
    part, group, head, buf = Part(key, title, []), "", None, []
    for line in lines:
        img = re.match(r"!\[[^\]]*\]\(([^)]+\.svg)\)", line)
        m = re.match(r"(#{2,3}) (?:(\d+)\. )?(.+)", line)
        if img and head:
            num, name = head
            svg = path.parent / img.group(1)
            part.diagrams.append(Diagram(num, name, blocks(buf), svg, group))
            head, buf = None, []
        elif m and m.group(2) is not None:
            head, buf = (m.group(2), m.group(3)), []
        elif m:
            group = m.group(3)
        elif head:
            buf.append(line)
        elif not part.diagrams and not group:
            part.intro.append(line)
    part.intro = blocks(part.intro)
    return part


# --- cropping ---------------------------------------------------------------

# Room left for the picture on a page, in mm, below the header and the text.
ROOM = {True: (281, 140), False: (194, 225)}


def crop(d: Diagram, tmp: Path) -> None:
    """Cut the draw.io page margin off the svg and pick the orientation that shows it largest."""
    from PIL import Image, ImageOps

    # Chrome, not rsvg: the draw.io labels are HTML in foreignObject, which only a browser draws.
    text = d.svg.read_text()
    size = re.search(r'width="([\d.]+)px" height="([\d.]+)px"', text)
    png = tmp / f"{d.svg.stem}.png"
    subprocess.run(
        [chrome(), "--headless", "--disable-gpu", "--hide-scrollbars", f"--screenshot={png}",
         f"--window-size={round(float(size[1]))},{round(float(size[2]))}", d.svg.as_uri()],
        check=True, capture_output=True,
    )
    gray = ImageOps.invert(Image.open(png).convert("L"))
    x0, y0, x1, y1 = gray.point(lambda v: 255 if v > 8 else 0).getbbox()
    pad = 6
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    w, h = x1 - x0, y1 - y0
    text = re.sub(r'width="[\d.]+px" height="[\d.]+px" viewBox="[^"]+"',
                  f'width="{w}px" height="{h}px" viewBox="{x0} {y0} {w} {h}"', text, count=1)
    d.src = tmp / d.svg.name
    d.src.write_text(text)
    scale = {o: min(rw / w, rh / h) for o, (rw, rh) in ROOM.items()}
    d.landscape = scale[True] >= scale[False]


# --- wordmark ---------------------------------------------------------------


def wordmark(color: str = "#1d1d1b") -> str:
    data = json.loads((ROOT / "promo" / "out" / "strokes.json").read_text())["wordmark"]["strokes"]
    x0 = min(s["bbox"][0] for s in data)
    y0 = min(s["bbox"][1] for s in data)
    x1 = max(s["bbox"][2] for s in data)
    y1 = max(s["bbox"][3] for s in data)
    pad = 20
    paths = "".join(
        f'<path d="{s["d"]}" stroke-width="{max(4, s["w"] * 1.1):.1f}"/>' for s in data
    )
    return (
        f'<svg class="wm" viewBox="{x0 - pad} {y0 - pad} {x1 - x0 + 2 * pad} {y1 - y0 + 2 * pad}" '
        f'fill="none" stroke="{color}" stroke-linecap="round" stroke-linejoin="round">{paths}</svg>'
    )


# --- pages ------------------------------------------------------------------


CSS = """
@page { margin: 0; size: A4 portrait; }
@page land { margin: 0; size: A4 landscape; }
:root { --paper:#ffffff; --surface:#ffffff; --ink:#1d1d1b; --muted:#6b6a65; --line:#dcd8cd;
        --accent:#2b5fd9; --verk:#c2410c; --tek:#2b5fd9; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: var(--paper); color: var(--ink);
  font: 10.5pt/1.5 "Helvetica Neue", Helvetica, Arial, sans-serif;
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }
a { color: var(--accent); text-decoration: none; }
code { font: 9pt "SF Mono", Menlo, monospace; background: #f1f1f1; padding: 0 3px; border-radius: 3px; }
.page { position: relative; width: 210mm; height: 297mm; overflow: hidden; break-after: page;
  padding: 24mm 16mm 18mm; display: flex; flex-direction: column; }
.page.land { page: land; width: 297mm; height: 210mm; padding: 19mm 8mm 11mm; }
.page.dg:not(.land) { padding: 19mm 8mm 11mm; }
.page:last-child { break-after: auto; }

/* running header and footer */
.hdr { position: absolute; top: 0; left: 0; right: 0; height: 14mm; padding: 0 16mm;
  display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--line); background: var(--surface); }
.land .hdr, .dg .hdr { padding: 0 8mm; height: 12mm; }
.dg .hdr .wm { height: 7.5mm; }
.hdr .wm { height: 9mm; width: auto; }
.hdr .crumb { color: var(--muted); font-size: 9pt; }
.hdr .crumb b { color: var(--ink); font-weight: 600; }
.hdr .toc-link { margin-left: auto; font-size: 9pt; border: 1px solid var(--line); border-radius: 99px; padding: 2px 10px; background: #fff; }
.ftr { position: absolute; bottom: 0; left: 0; right: 0; height: 10mm; padding: 0 16mm;
  display: flex; align-items: center; justify-content: space-between; font-size: 8.5pt; color: var(--muted); }
.land .ftr, .dg .ftr { padding: 0 8mm; height: 9mm; }
.ftr .nav a { margin-left: 12px; }

/* cover */
.page.cover { padding: 0; justify-content: center; align-items: center; text-align: center;
  background: var(--paper); }
.cover .wm { width: 120mm; height: auto; }
.cover h1 { font-size: 26pt; font-weight: 300; margin: 8mm 0 2mm; letter-spacing: .5px; }
.cover .sub { color: var(--muted); font-size: 12pt; margin: 0; }
.cover .chips { display: flex; gap: 10px; justify-content: center; margin-top: 14mm; }
.chip { display: inline-block; border-radius: 99px; padding: 5px 16px; font-size: 10.5pt; color: #fff; }
.chip.verk { background: var(--verk); } .chip.tek { background: var(--tek); }
.cover .meta { position: absolute; bottom: 16mm; left: 0; right: 0; color: var(--muted); font-size: 9.5pt; }
.cover .rule { width: 40mm; height: 3px; background: var(--accent); border-radius: 2px; margin: 8mm auto 0; }

/* table of contents */
.toc-head { display: flex; align-items: flex-end; gap: 14px; border-bottom: 2px solid var(--ink); padding-bottom: 4mm; margin-bottom: 5mm; }
.toc-head .wm { height: 20mm; width: auto; }
.toc-head h2 { margin: 0 0 2mm; font-size: 22pt; font-weight: 300; }
.toc { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 10mm; align-items: start; }
.toc .part { margin: 0; }
.toc .ptitle { display: flex; align-items: center; gap: 8px; font-size: 12.5pt; font-weight: 600; color: var(--ink); margin-bottom: 1.5mm; }
.toc .grp { font-size: 8pt; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin: 2.5mm 0 1mm; }
.toc .row { display: flex; align-items: baseline; gap: 6px; font-size: 9.6pt; padding: 1.1mm 0; color: var(--ink); break-inside: avoid; }
.toc .row .n { width: 6mm; color: var(--muted); font-variant-numeric: tabular-nums; }
.toc .row .dots { flex: 1; border-bottom: 1px dotted #bdb8aa; transform: translateY(-3px); }
.toc .row .p { font-variant-numeric: tabular-nums; color: var(--muted); }
.dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.dot.verk { background: var(--verk); } .dot.tek { background: var(--tek); }
.toc-note { margin: auto 0 4mm; font-size: 9pt; color: var(--muted); border-top: 1px solid var(--line); padding-top: 3mm; }

/* part divider */
.divider { justify-content: center; }
.divider .num { font-size: 11pt; letter-spacing: 3px; text-transform: uppercase; }
.divider.verk .num { color: var(--verk); } .divider.tek .num { color: var(--tek); }
.divider h2 { font-size: 34pt; font-weight: 300; margin: 1mm 0 4mm; line-height: 1.1; }
.divider .bar { height: 5px; width: 30mm; border-radius: 3px; margin-bottom: 5mm; }
.divider.verk .bar { background: var(--verk); } .divider.tek .bar { background: var(--tek); }
.divider .intro { font-size: 11pt; max-width: 230mm; }
.divider .list { margin-top: 6mm; display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.5mm 8mm; font-size: 10pt; }
.divider .list a { color: var(--ink); } .divider .list .n { color: var(--muted); display: inline-block; width: 7mm; }

/* diagram page: text first, picture below */
.dg .head { display: flex; align-items: baseline; gap: 4mm; margin-bottom: 1mm; }
.dg .badge { flex: none; width: 8mm; height: 8mm; border-radius: 50%; color: #fff; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center; font-size: 11pt; transform: translateY(1.5mm); }
.dg.verk .badge { background: var(--verk); } .dg.tek .badge { background: var(--tek); }
.dg h3 { margin: 0; font-size: 15pt; font-weight: 500; }
.dg .grp { font-size: 8pt; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin-left: 12mm; }
.dg .text { margin: 1mm 0 2.5mm 12mm; max-width: 250mm; font-size: 10pt; line-height: 1.4; }
.dg .text p { margin: 0 0 1mm; }
.dg .fig { flex: 1; min-height: 0; display: flex; flex-direction: column; align-items: center; }
.dg .fig a { flex: 1; min-height: 0; max-width: 100%; display: flex; justify-content: center; align-items: flex-start; }
.dg .fig img { max-width: 100%; max-height: 100%; background: #fff; border: 1px solid var(--line); border-radius: 4px; padding: 1.5mm; }
"""


def page(d: Diagram, part: Part, wm: str, total: int, prev: str, nxt: str) -> str:
    rel = d.svg.relative_to(HERE).as_posix()
    nav = (f'<a href="#{prev}">← Föregående</a>' if prev else "") + (f'<a href="#{nxt}">Nästa →</a>' if nxt else "")
    grp = f'<div class="grp">{html.escape(d.group)}</div>' if d.group else ""
    return f"""
<section class="page dg {part.key}{' land' if d.landscape else ''}" id="{d.anchor}">
  {header(wm, part, d.title)}
  <div class="head"><span class="badge">{d.num}</span><h3>{html.escape(d.title)}</h3></div>
  {grp}
  <div class="text">{''.join(d.text)}</div>
  <div class="fig">
    <a href="{GITHUB}/{rel}"><img src="{(d.src or d.svg).as_uri()}" alt="{html.escape(d.title)}"></a>
  </div>
  {footer(d.page, total, nav, f"Klicka på bilden för full storlek · {html.escape(d.svg.name)}")}
</section>"""


def header(wm: str, part: Part | None, title: str = "") -> str:
    crumb = f'<span class="crumb"><b>{html.escape(part.title)}</b>{" · " + html.escape(title) if title else ""}</span>' if part else ""
    return f'<div class="hdr">{wm}{crumb}<a class="toc-link" href="#innehall">☰ Innehåll</a></div>'


def footer(n: int, total: int, nav: str = "", note: str = "rmink · dokumentation") -> str:
    return f'<div class="ftr"><span>{note}</span><span class="nav">{nav}</span><span>{n} / {total}</span></div>'


def build(parts: list[Part], version: str) -> str:
    wm = wordmark()
    # Every section is exactly one page, so the page numbers are known before printing.
    n = 3  # cover, contents
    for i, p in enumerate(parts, 1):
        p.anchor, p.page = f"del-{p.key}", n
        n += 1
        for d in p.diagrams:
            d.anchor, d.page = f"{p.key}-{d.num}", n
            n += 1
    total = n - 1
    flat = [d for p in parts for d in p.diagrams]

    today = dt.date.today().isoformat()
    out = [f"""
<section class="page land cover">
  {wordmark()}
  <h1>Dokumentation</h1>
  <p class="sub">Handskrift, skisser och ritningar på reMarkable</p>
  <div class="rule"></div>
  <div class="chips">{''.join(f'<a class="chip {p.key}" href="#{p.anchor}">{html.escape(p.title)}</a>' for p in parts)}</div>
  <div class="meta">Version {version} · {today} · <a href="https://rmink.vercel.app">rmink.vercel.app</a> · <a href="https://github.com/thagvall/rmink">github.com/thagvall/rmink</a></div>
</section>"""]

    # One column per part, or per group within a part, so no list breaks across columns.
    toc = []
    for i, p in enumerate(parts, 1):
        groups = list(dict.fromkeys(d.group for d in p.diagrams))
        for g in groups:
            rows = [f'<div class="grp">{html.escape(g)}</div>'] if g else []
            rows += [f'<a class="row" href="#{d.anchor}"><span class="n">{d.num}</span>{html.escape(d.title)}<span class="dots"></span><span class="p">{d.page}</span></a>'
                     for d in p.diagrams if d.group == g]
            toc.append(f'<div class="part"><a class="ptitle" href="#{p.anchor}"><span class="dot {p.key}"></span>Del {i} · {html.escape(p.title)}</a>{"".join(rows)}</div>')
    out.append(f"""
<section class="page land" id="innehall">
  <div class="toc-head">{wm}<h2>Innehåll</h2></div>
  <div class="toc">{''.join(toc)}</div>
  <div class="toc-note">Allt i dokumentet är klickbart: innehållslistan, <b>☰ Innehåll</b> uppe till höger på varje sida, Föregående/Nästa längst ner och diagrammen, som öppnar SVG-filen i full storlek. Diagrammen är vektorbilder, så det går också att zooma in i PDF:en.</div>
  {footer(2, total)}
</section>""")

    for i, p in enumerate(parts, 1):
        items = "".join(f'<a href="#{d.anchor}"><span class="n">{d.num}</span>{html.escape(d.title)}</a>' for d in p.diagrams)
        out.append(f"""
<section class="page land divider {p.key}" id="{p.anchor}">
  {header(wm, p)}
  <div class="num">Del {i}</div>
  <h2>{html.escape(p.title)}</h2>
  <div class="bar"></div>
  <div class="intro">{''.join(p.intro)}</div>
  <div class="list">{items}</div>
  {footer(p.page, total)}
</section>""")
        for d in p.diagrams:
            k = flat.index(d)
            prev = flat[k - 1].anchor if k else ""
            nxt = flat[k + 1].anchor if k + 1 < len(flat) else ""
            out.append(page(d, p, wm, total, prev, nxt))

    return f'<!doctype html><html lang="sv"><head><meta charset="utf-8"><title>rmink · dokumentation</title><style>{CSS}</style></head><body>{"".join(out)}</body></html>'


def chrome() -> str:
    for c in CHROMES:
        if Path(c).exists() or shutil.which(c):
            return c
    sys.exit("Google Chrome or chromium is needed to print the PDF")


def main() -> None:
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    parts = [
        parse(HERE / "verksamhet" / "README.md", "verk", "Verksamhet"),
        parse(HERE / "teknik" / "README.md", "tek", "Teknik"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for d in (d for p in parts for d in p.diagrams):
            crop(d, Path(tmp))
        src = Path(tmp) / "doc.html"
        src.write_text(build(parts, version))
        subprocess.run(
            [chrome(), "--headless", "--disable-gpu", "--no-pdf-header-footer",
             "--generate-pdf-document-outline", "--allow-file-access-from-files",
             f"--print-to-pdf={OUT}", src.as_uri()],
            check=True, capture_output=True,
        )
    print(f"{OUT.relative_to(ROOT)}: {sum(len(p.diagrams) for p in parts)} diagram")


if __name__ == "__main__":
    main()
