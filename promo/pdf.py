"""Build docs/bild-till-black.pdf: the promo video step by step, plus contours and shading.

    .venv/bin/python promo/pdf.py      # needs rmink, Pillow and Google Chrome

Part 1 is stills from timeline.html (the promo video, in Swedish) with a text per
step. Part 2 runs rmink on the same pictures as the video: the note as
handwriting, the logo as outlines with each fill and the portrait in every
shading style. The PDF is landscape and clickable: contents, chapter chips on
every page, previous/next and bookmarks.
"""

from __future__ import annotations

import functools
import html
import http.server
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / "docs" / "bild-till-black.pdf"
sys.path.insert(0, str(ROOT / "docs" / "diagrams"))

from pdf import chrome, wordmark  # noqa: E402  (docs/diagrams/pdf.py)


@dataclass
class Step:
    title: str
    text: str
    points: list[str] = field(default_factory=list)
    t: float | None = None  # a video still at this time
    images: list[tuple[str, Path]] = field(default_factory=list)  # (caption, picture)
    stats: list[tuple[str, str]] = field(default_factory=list)
    anchor: str = ""
    page: int = 0


@dataclass
class Chapter:
    key: str
    title: str
    steps: list[Step]
    anchor: str = ""


@dataclass
class Part:
    key: str
    title: str
    intro: str
    chapters: list[Chapter]
    cols: int = 10  # thumbnails per row on the part page
    ar: str = "4 / 5"  # their aspect ratio
    anchor: str = ""
    page: int = 0


# --- part 1: the video ------------------------------------------------------

VIDEO = [
    Chapter("foto", "Från foto till bläck", [
        Step("Dina handskrivna anteckningar …", "Utgångspunkten är ett vanligt foto av en handskriven lapp: en lista, en skiss av ett hus och en sol. Papperet är grått, ljuset ojämnt och bilden lite sned.",
             ["Foton, skannade sidor, whiteboards och skisser fungerar likadant."], t=3),
        Step("… som riktigt reMarkable-bläck", "rmink lägger inte fotot som en bild bakom anteckningarna. Varje linje blir ett eget pennstreck i plattans format, så resultatet går att sudda, flytta och färga om som om du skrivit det själv.",
             ["Pappersskuggor tas bort och bläcket tunnas ut till en mittlinje.", "Varje linje blir ett streck längs mitten, med linjens bredd."], t=11),
    ]),
    Chapter("webb", "Webbappen", [
        Step("1 · Släpp in ett foto", "Öppna rmink.vercel.app och släpp in en eller flera filer: foton, PNG, JPG, HEIC, SVG eller PDF. Inget konto behövs.", t=13),
        Step("2 · Se bläcket direkt", "Förhandsbilden visar exakt de streck som hamnar på plattan, med antal streck och punkter. Du ser resultatet innan du laddar ner något.", t=15),
        Step("3 · Välj din platta", "reMarkable 2, Paper Pure, Paper Pro eller Paper Pro Move. Plattan avgör sidans storlek och om färgerna behålls: Paper Pro och Move visar färg, rm2 och Pure gråskala.", t=19),
        Step("4 · Ladda ner anteckningsboken", "Du får en .rmdoc, en vanlig reMarkable-anteckningsbok. Den hamnar i Hämtade filer.", t=21),
        Step("5 · Ladda upp till plattan via USB", "Anslut plattan med kabel och öppna USB-webbgränssnittet. Dra in filen, så ligger anteckningsboken bland dina andra.",
             ["Send to reMarkable i webbappen skickar den också direkt via molnet."], t=27),
        Step("… eller dra in den i reMarkable-appen", "Filen går lika bra att dra in i reMarkables egen app på datorn. Den synkar sedan till plattan.", t=31),
    ]),
    Chapter("redigera", "Redigera på plattan", [
        Step("Sudda", "Eftersom allt är pennstreck kan du sudda en del av en rad, en bock eller ett ord, precis som med din egen handstil.", t=35),
        Step("Flytta", "Markera med lasson och flytta. Solen flyttas som en egen grupp streck.", t=39),
        Step("Färga om", "På Paper Pro och Move byter du färg på vilka streck som helst, till exempel rubriken.", t=41),
        Step("Precis som dina egna pennstreck", "Resultatet beter sig som något du ritat för hand på plattan. Du kan skriva vidare direkt i samma anteckningsbok.", t=43),
    ]),
    Chapter("ansikten", "Ansikten", [
        Step("Funkar med ansikten också", "Ett porträtt blir en linjeteckning. Konturerna och de mörka partierna följs av riktiga streck.", t=49),
        Step("Ändra storlek", "Teckningen är vektorstreck, så den kan skalas om med lasson utan att bli suddig.", t=51),
        Step("Rita vidare", "Rita glasögon, skriv en pratbubbla eller sudda bort en del. Porträttet är en del av anteckningsboken.", t=57),
    ]),
    Chapter("skuggor", "Skuggor", [
        Step("Behåll skuggorna", "Foton kan behålla sina gråtoner. Webbappen visar porträttet i alla sex stilar bredvid varandra: linjer, prickar, raster, hatchning, korshatch och blyerts.",
             ["Hur stilarna ser ut i full storlek finns i del 2."], t=63),
        Step("Välj stil, penna och tjocklek", "Klicka på en stil för att se den stort. Penna och linjetjocklek väljer du bredvid, till exempel fineliner, kulspets, märkpenna eller blyerts.", t=67),
    ]),
    Chapter("claude", "Claude", [
        Step("Eller be Claude", "rmink finns också som MCP-server. En engångsinstallation, så kan Claude Desktop eller Claude Code konvertera bilder åt dig.",
             ["claude mcp add rmink -- uvx --from 'rmink[mcp]' rmink mcp"], t=71),
        Step("Klart på några sekunder", "Be Claude göra om en bild till en anteckningsbok för din platta. Claude visar förhandsbilden och skapar filen, som du sedan lägger över via USB eller appen.", t=77),
    ]),
    Chapter("gratis", "Gratis och öppet", [
        Step("Foton, skisser, logotyper, PDF:er", "Samma verktyg för allt som ska bli bläck: handskrift, skisser, logotyper, porträtt och PDF:er, både vektor och skannade. Det fungerar på reMarkable 2, Paper Pure, Paper Pro och Paper Pro Move.", t=81),
        Step("Prova gratis", "rmink är gratis och öppen källkod. Det finns inga betalväggar, bara ett frivilligt stöd på 100 kr.",
             ["Appen: rmink.vercel.app", "Källkod: github.com/thagvall/rmink"], t=95),
    ]),
]


# --- part 2: contours and shading, made by rmink ----------------------------

SHADES = [
    ("none", "Linjer", "Bara konturerna och de mörkaste partierna, utan gråtoner. Det ger den lättaste filen och fungerar bäst om du vill rita vidare själv."),
    ("stipple", "Prickar", "Gråtonerna blir prickar som ligger tätare där bilden är mörkare, som en stipplad tuschteckning."),
    ("halftone", "Raster", "Ett jämnt rutnät av prickar som växer där bilden är mörk, som ett tidningsfoto."),
    ("hatch", "Hatchning", "Parallella linjer som ligger tätare i mörka partier. Det ger ett lugnt, grafiskt uttryck."),
    ("crosshatch", "Korshatch", "Fler linjeriktningar läggs på ju mörkare det är. Det ger djupast svärta och mest kontrast."),
    ("pencil", "Blyerts", "Blyertsstreck vars tryck följer tonen, så ljusa partier blir svaga och mörka kraftiga. Det är det mjukaste resultatet."),
]

FILLS = [
    ("hatch", "Hatchad fyllning", "Ytor fylls med tät hatchning i pennans färg, så loggan ser ifylld ut men består av raka streck."),
    ("outline", "Bara kontur", "Bara ytornas kanter ritas. Det ger få streck och är lätt att färglägga för hand."),
    ("none", "Ignorera ytor", "Bara tunna linjer följs och fyllda ytor hoppas över."),
]


def crop(img: Image.Image, pad: int = 24) -> Image.Image:
    """Cut the white page around the ink."""
    box = img.convert("L").point(lambda v: 255 if v < 248 else 0).getbbox() or (0, 0, *img.size)
    x0, y0, x1, y1 = box
    return img.crop((max(0, x0 - pad), max(0, y0 - pad), min(img.width, x1 + pad), min(img.height, y1 + pad)))


def examples(tmp: Path) -> list[Chapter]:
    from rmink.api import render, style_previews
    from rmink.options import ConvertOptions, FillMode, Mode

    def save(img: Image.Image, name: str) -> Path:
        path = tmp / name
        crop(img.convert("RGB")).save(path, optimize=True)
        return path

    note = HERE / "out" / "note-sv.jpg"
    r = render([note], ConvertOptions(device="pro", mode=Mode.centerline))
    hand = Step(
        "Handskrift och skiss", "Fotot av lappen körs som handskrift: papperet tas bort, bläcket tunnas ut och varje linje blir ett streck längs mitten. Färgerna mappas till Paper Pros pennfärger.",
        ["Läge: Handskrift / skiss (centerline)", "Platta: Paper Pro, färg"],
        images=[("Foto", note), ("rmink, Paper Pro", save(r.images[0], "note.png"))],
        stats=[(f"{len(r.document.pages[0].strokes):,}".replace(",", " "), "streck"),
               (f"{r.document.pages[0].point_count:,}".replace(",", " "), "punkter")],
    )

    logo_png = tmp / "logo-src.png"
    subprocess.run(["rsvg-convert", "-w", "1200", "-b", "white", "-o", logo_png, ROOT / "examples" / "logo.svg"], check=True)
    logos = []
    for key, title, text in FILLS:
        r = render([logo_png], ConvertOptions(device="pro", mode=Mode.outline, fill=FillMode(key)))
        logos.append(Step(
            title, text + " Färgerna grupperas och mappas till plattans pennfärger.",
            [f"Läge: Logo / solida former (outline)", f"Fyllning: {title.lower()}", "Platta: Paper Pro, färg"],
            images=[("Original (PNG)", logo_png), (f"rmink · {title.lower()}", save(r.images[0], f"logo-{key}.png"))],
            stats=[(f"{len(r.document.pages[0].strokes):,}".replace(",", " "), "streck"),
                   (f"{r.document.pages[0].point_count:,}".replace(",", " "), "punkter")],
        ))

    face = HERE / "out" / "face.jpg"
    previews = {p.style.value: p for p in style_previews(face, ConvertOptions(device="rm2"))}
    shades = []
    for key, title, text in SHADES:
        p = previews[key]
        shades.append(Step(
            title, text,
            [f"Skuggning: {title.lower()} (--shading {key})", "Platta: reMarkable 2, gråskala", "Täthet och kontrast går att justera."],
            images=[("Foto", face), (f"rmink · {title.lower()}", save(p.image, f"shade-{key}.png"))],
            stats=[(f"{p.strokes:,}".replace(",", " "), "streck"), (f"{p.points:,}".replace(",", " "), "punkter")],
        ))
    return [
        Chapter("handskrift", "Handskrift", [hand]),
        Chapter("logga", "Konturer i en logga", logos),
        Chapter("skuggning", "Skuggning av ett porträtt", shades),
    ]


# --- video stills -----------------------------------------------------------


# Seeks pages that have window.seek(t) but no ?t= parameter, once they are ready.
SEEK = "<script>{const t=+new URLSearchParams(location.search).get('t');const i=setInterval(()=>{if(window.ready){clearInterval(i);window.seek(t);}},20);}</script>"


def stills(tmp: Path, times: list[float], page: str = "timeline.html", size: tuple[int, int] = (1080, 1350),
           query: str = "lang=sv&t={t}", inject: str = "") -> dict[float, Path]:
    """Screenshots of a timeline page under promo/, one at a time: in parallel some scenes were caught half drawn.

    ``inject`` is appended to ``page`` as it is served, for example :data:`SEEK`.
    """

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if inject and self.path.split("?")[0] == "/" + page:
                body = ((HERE / page).read_text() + inject).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(HERE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    out = {}
    try:
        for t in times:
            png = tmp / f"t{t}.png"
            subprocess.run(
                [chrome(), "--headless", "--hide-scrollbars", f"--window-size={size[0]},{size[1]}", "--virtual-time-budget=40000",
                 f"--screenshot={png}", f"http://127.0.0.1:{server.server_address[1]}/{page}?{query.format(t=t)}"],
                check=True, capture_output=True,
            )
            jpg = png.with_suffix(".jpg")
            Image.open(png).convert("RGB").save(jpg, quality=88)
            out[t] = jpg
    finally:
        server.shutdown()
    return out


# --- pages ------------------------------------------------------------------

CSS = """
@page { size: A4 landscape; margin: 0; }
:root { --ink:#1d1d1b; --muted:#6b6a65; --line:#dcd8cd; --accent:#2b5fd9; --soft:#e6ecfb; --p1:#2b5fd9; --p2:#c2410c; }
* { box-sizing: border-box; }
html, body { margin: 0; background: #fff; color: var(--ink); font: 10.5pt/1.5 "Helvetica Neue", Helvetica, Arial, sans-serif;
  -webkit-print-color-adjust: exact; print-color-adjust: exact; }
a { color: var(--accent); text-decoration: none; }
code, .mono { font-family: "SF Mono", Menlo, monospace; font-size: 8.5pt; }
.pg { position: relative; width: 297mm; height: 210mm; overflow: hidden; break-after: page; padding: 18mm 10mm 12mm; display: flex; flex-direction: column; }
.pg:last-child { break-after: auto; }
.hdr { position: absolute; top: 0; left: 0; right: 0; height: 12mm; padding: 0 10mm; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--line); }
.hdr .wm { height: 7.5mm; width: auto; }
.hdr .crumb { font-size: 9pt; color: var(--muted); } .hdr .crumb b { color: var(--ink); }
.hdr .home { margin-left: auto; font-size: 9pt; border: 1px solid var(--line); border-radius: 99px; padding: 2px 10px; }
.ftr { position: absolute; bottom: 0; left: 0; right: 0; height: 9mm; padding: 0 10mm; display: flex; align-items: center; justify-content: space-between; font-size: 8.5pt; color: var(--muted); }
.ftr .nav a { margin-left: 14px; }

.cover { display: grid; grid-template-columns: 1fr 120mm; align-items: center; gap: 12mm; padding: 0 22mm; }
.cover .wm { width: 62mm; height: auto; }
.cover h1 { font-size: 32pt; font-weight: 300; margin: 8mm 0 4mm; line-height: 1.1; }
.cover .lede { font-size: 12.5pt; color: var(--muted); }
.cover .chips { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 10mm; }
.cover .chips a { border-radius: 99px; padding: 4px 14px; color: #fff; font-size: 10pt; }
.cover .chips a.p1 { background: var(--p1); } .cover .chips a.p2 { background: var(--p2); }
.cover .hero { display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; }
.cover .hero img { width: 100%; border-radius: 6px; border: 1px solid var(--line); }
.cover .meta { position: absolute; bottom: 12mm; left: 22mm; font-size: 9pt; color: var(--muted); }

.tochead { display: flex; align-items: flex-end; gap: 14px; border-bottom: 2px solid var(--ink); padding-bottom: 3mm; margin-bottom: 5mm; }
.tochead .wm { height: 17mm; width: auto; }
.tochead h2 { font-size: 22pt; font-weight: 300; margin: 0 0 1.5mm; }
.toc { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 10mm; align-items: start; }
.toc .pt:not(:first-child) { margin-top: 5mm !important; }
.toc .pt { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 11.5pt; color: var(--ink); margin: 0 0 1mm; }
.dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; } .dot.p1 { background: var(--p1); } .dot.p2 { background: var(--p2); }
.toc .ch { font-size: 8pt; text-transform: uppercase; letter-spacing: 1px; color: var(--muted); margin: 3mm 0 .5mm; display: block; }
.toc .r { display: flex; gap: 6px; align-items: baseline; font-size: 9.3pt; padding: .55mm 0; color: var(--ink); }
.toc .r .d { flex: 1; border-bottom: 1px dotted #bdb8aa; transform: translateY(-3px); }
.toc .r .p { color: var(--muted); font-variant-numeric: tabular-nums; }
.tocnote { margin: auto 0 3mm; font-size: 9pt; color: var(--muted); border-top: 1px solid var(--line); padding-top: 3mm; }

.divider .num { font-size: 10.5pt; letter-spacing: 3px; text-transform: uppercase; margin-top: 4mm; }
.divider.p1 .num { color: var(--p1); } .divider.p2 .num { color: var(--p2); }
.divider h2 { font-size: 30pt; font-weight: 300; margin: 1mm 0 3mm; }
.divider .intro { font-size: 11pt; max-width: 230mm; color: var(--muted); }
.divider .thumbs { margin-top: 6mm; display: grid; grid-template-columns: repeat(var(--cols), minmax(0, 1fr)); gap: 3mm; }
.divider .thumbs a { display: grid; gap: 1mm; color: var(--ink); font-size: 7.5pt; line-height: 1.25; }
.divider .thumbs img { width: 100%; aspect-ratio: var(--ar); object-fit: contain; background: #fff; border: 1px solid var(--line); border-radius: 4px; }

.step { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 9mm; flex: 1; min-height: 0; }
.pics { display: flex; gap: 5mm; min-height: 0; height: 100%; align-items: stretch; }
.pics figure { margin: 0; display: flex; flex-direction: column; gap: 1.5mm; min-height: 0; }
.pics img { height: 100%; min-height: 0; max-width: 100%; object-fit: contain; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
.pics.video img { height: 166mm; width: auto; }
.pics.video.wide { align-items: flex-start; } .pics.video.wide img { width: 186mm; height: auto; }
.cover.wide { grid-template-columns: 1fr 150mm; } .cover.wide .hero { grid-template-columns: 1fr; }
.pics.two figure { width: 92mm; } .pics.two figure:only-child { width: auto; max-width: 150mm; } .pics.two figure:only-child img { width: auto; max-height: 168mm; } .pics.two img { width: 100%; height: auto; max-height: 160mm; }
.pics figcaption { font-size: 8pt; color: var(--muted); font-family: "SF Mono", Menlo, monospace; }
.side { display: flex; flex-direction: column; gap: 3mm; min-height: 0; }
.side .eyebrow { font-family: "SF Mono", Menlo, monospace; font-size: 8pt; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.side .eyebrow b { color: var(--accent); font-weight: 500; }
.side h2 { font-size: 19pt; font-weight: 500; margin: 0; line-height: 1.15; }
.side p { margin: 0; font-size: 11pt; }
.side ul { margin: 0; padding-left: 1.1em; color: var(--muted); font-size: 9.8pt; display: grid; gap: 1mm; }
.stats { display: flex; gap: 8mm; } .stats div { display: grid; }
.stats strong { font-size: 20pt; font-weight: 500; line-height: 1; font-variant-numeric: tabular-nums; } .stats span { font-size: 8.5pt; color: var(--muted); }
.chips { margin-top: auto; display: flex; flex-wrap: wrap; gap: 4px; }
.chips a { border: 1px solid var(--line); border-radius: 6px; padding: 2px 7px; font-size: 8pt; color: var(--muted); }
.chips a b { font-family: "SF Mono", Menlo, monospace; font-weight: 500; color: var(--ink); margin-right: 4px; }
.chips a.cur { border-color: var(--accent); background: var(--soft); color: var(--ink); }
.p2 .chips a.cur { border-color: var(--p2); background: #fbe9df; }
.p2 .side .eyebrow b { color: var(--p2); }
"""


@dataclass
class Meta:
    """What differs between the PDFs built with :func:`build`."""

    name: str  # in the page title and footer, e.g. "bild till bläck"
    title: str  # cover heading, may hold <br>
    lede: str
    hero: list[Path]
    links: str  # extra cover links, HTML
    note: str  # under the contents
    wide: bool = False  # video stills are 16:9 instead of 4:5


def build(parts: list[Part], frames: dict[float, Path], version: str, meta: Meta) -> str:
    wm = wordmark()
    n = 3
    for p in parts:
        p.anchor, p.page = f"del-{p.key}", n
        n += 1
        for c in p.chapters:
            c.anchor = f"{c.key}-1"
            for k, s in enumerate(c.steps, 1):
                s.anchor, s.page = f"{c.key}-{k}", n
                n += 1
    total = n - 1
    flat = [(p, c, s) for p in parts for c in p.chapters for s in c.steps]
    esc = html.escape

    def hdr(crumb: str) -> str:
        return f'<div class="hdr">{wm}<span class="crumb">{crumb}</span><a class="home" href="#innehall">☰ Innehåll</a></div>'

    def ftr(page: int, nav: str = "") -> str:
        return f'<div class="ftr"><span>rmink · {meta.name}</span><span class="nav">{nav}</span><span>{page} / {total}</span></div>'

    def pic(s: Step) -> Path:
        return frames[s.t] if s.t is not None else s.images[-1][1]

    out = []
    out.append(f"""<section class="pg cover{' wide' if meta.wide else ''}"><div>{wm}
      <h1>{meta.title}</h1>
      <p class="lede">{meta.lede}</p>
      <div class="chips">{''.join(f'<a class="{p.key}" href="#{p.anchor}">Del {i} · {esc(p.title)}</a>' for i, p in enumerate(parts, 1))}</div></div>
      <div class="hero">{''.join(f'<img src="{h.as_uri()}">' for h in meta.hero)}</div>
      <div class="meta">rmink {version} · <a href="https://rmink.vercel.app">rmink.vercel.app</a> · {meta.links} · <a href="https://github.com/thagvall/rmink">github.com/thagvall/rmink</a></div></section>""")

    # Contents in three columns, whole chapters only, each column about a third of the rows.
    cols: list[list[str]] = [[], [], []]
    per = (sum(len(c.steps) + 1 for p in parts for c in p.chapters) + 2) / 3
    col, rows = 0, 0
    for i, p in enumerate(parts, 1):
        for c in p.chapters:
            if rows and rows + len(c.steps) / 2 > per * (col + 1) and col < 2:
                col += 1
            rows += len(c.steps) + 1
            if not cols[col] or (i > 1 and c is p.chapters[0]):
                cols[col].append(f'<a class="pt" href="#{p.anchor}"><span class="dot {p.key}"></span>Del {i} · {esc(p.title)}</a>')
            cols[col].append(f'<a class="ch" href="#{c.anchor}">{esc(c.title)}</a>')
            cols[col] += [f'<a class="r" href="#{s.anchor}">{esc(s.title)}<span class="d"></span><span class="p">{s.page}</span></a>' for s in c.steps]
    out.append(f"""<section class="pg" id="innehall"><div class="tochead">{wm}<h2>Innehåll</h2></div>
      <div class="toc">{''.join(f'<div>{"".join(c)}</div>' for c in cols)}</div>
      <p class="tocnote">Allt är klickbart: innehållet, kapitelknapparna längst ner på varje sida, miniatyrerna på delsidorna, ☰ Innehåll och Föregående/Nästa. {meta.note}</p>
      {ftr(2)}</section>""")

    for i, p in enumerate(parts, 1):
        steps = [(c, s) for c in p.chapters for s in c.steps]
        thumbs = "".join(f'<a href="#{s.anchor}"><img src="{pic(s).as_uri()}">{esc(s.title)}</a>' for c, s in steps)
        out.append(f"""<section class="pg divider {p.key}" id="{p.anchor}">{hdr(f"<b>Del {i}</b> · {esc(p.title)}")}
          <div class="num">Del {i}</div><h2>{esc(p.title)}</h2><p class="intro">{p.intro}</p>
          <div class="thumbs" style="--cols:{p.cols}; --ar:{p.ar}">{thumbs}</div>
          {ftr(p.page, f'<a href="#{steps[0][1].anchor}">Börja →</a>')}</section>""")
        for c in p.chapters:
            for k, s in enumerate(c.steps):
                idx = next(j for j, f in enumerate(flat) if f[2] is s)
                nav = (f'<a href="#{flat[idx - 1][2].anchor}">← Föregående</a>' if idx else "") + (
                    f'<a href="#{flat[idx + 1][2].anchor}">Nästa →</a>' if idx + 1 < len(flat) else "")
                if s.t is not None:
                    pics = f'<div class="pics video{' wide' if meta.wide else ''}"><img src="{frames[s.t].as_uri()}"></div>'
                else:
                    pics = '<div class="pics two">' + "".join(
                        f'<figure><img src="{path.as_uri()}"><figcaption>{esc(cap)}</figcaption></figure>' for cap, path in s.images) + "</div>"
                stats = '<div class="stats">' + "".join(f"<div><strong>{v}</strong><span>{esc(l)}</span></div>" for v, l in s.stats) + "</div>" if s.stats else ""
                points = "<ul>" + "".join(f"<li>{esc(x)}</li>" for x in s.points) + "</ul>" if s.points else ""
                # Chips: the chapter's steps, or for one-step chapters all chapters of the part.
                if len(c.steps) > 1:
                    chips = "".join(f'<a href="#{x.anchor}"{" class=cur" if x is s else ""}><b>{j}</b>{esc(x.title)}</a>' for j, x in enumerate(c.steps, 1))
                else:
                    chips = "".join(f'<a href="#{x.anchor}"{" class=cur" if x is c else ""}><b>{j}</b>{esc(x.title)}</a>' for j, x in enumerate(p.chapters, 1))
                out.append(f"""<section class="pg {p.key}" id="{s.anchor}">{hdr(f"<b>Del {i}</b> · {esc(c.title)}")}
                  <div class="step">{pics}<div class="side">
                    <span class="eyebrow">{esc(c.title)} · <b>{k + 1} av {len(c.steps)}</b></span>
                    <h2>{esc(s.title)}</h2><p>{esc(s.text)}</p>{stats}{points}
                    <nav class="chips">{chips}</nav></div></div>
                  {ftr(s.page, nav)}</section>""")
    return f'<!doctype html><html lang="sv"><head><meta charset="utf-8"><title>rmink · {meta.name}</title><style>{CSS}</style></head><body>{"".join(out)}</body></html>'


def main() -> None:
    import re

    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        frames = stills(tmp, sorted({s.t for c in VIDEO for s in c.steps if s.t is not None}))
        parts = [
            Part("p1", "Videon steg för steg", "Demovideon för rmink, bild för bild: från ett foto av en handskriven lapp, via webbappen och redigering på plattan, till ansikten, skuggor och Claude. Klicka på en bild för att gå till steget.", VIDEO),
            Part("p2", "Konturer och skuggning", "Samma bilder som i videon, körda genom rmink i full upplösning: lappen som handskrift, loggan med tre sätt att fylla ytor och porträttet i alla sex skuggstilar. Siffrorna är antal streck och punkter i resultatet.", examples(tmp), cols=5, ar="1 / 1"),
        ]
        doc = tmp / "doc.html"
        meta = Meta(
            "bild till bläck", "Från bild till<br>reMarkable-bläck",
            "Foton av handskrift, skisser, logotyper, porträtt och PDF:er blir riktiga pennstreck som går att sudda, flytta och färga om. Del 1 följer demovideon steg för steg, och del 2 visar konturerna och skuggstilarna i full storlek.",
            [frames[3], frames[11]], '<a href="https://rmink.vercel.app/video/sv">videon</a>', "Bilderna i del 2 är rminks riktiga utdata.",
        )
        doc.write_text(build(parts, frames, version, meta))
        subprocess.run(
            [chrome(), "--headless", "--disable-gpu", "--no-pdf-header-footer", "--generate-pdf-document-outline",
             "--allow-file-access-from-files", f"--print-to-pdf={OUT}", doc.as_uri()],
            check=True, capture_output=True,
        )
    print(f"{OUT.relative_to(ROOT)}: {sum(len(c.steps) for p in parts for c in p.chapters)} steg")


if __name__ == "__main__":
    main()
