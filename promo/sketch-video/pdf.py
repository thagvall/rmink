"""Build docs/revisionsvarv.pdf: the sketch-to-drawing video step by step, plus the /rounds page.

    .venv/bin/python promo/sketch-video/pdf.py      # needs Pillow, rsvg-convert and Google Chrome
    .venv/bin/python promo/sketch-video/pdf.py --video deploy/vercel/public/promo/sketch/rmink-sketch-sv-16x9.mp4
                                                    # only the video, frames from the mp4 → docs/skissvideon.pdf

Part 1 is stills from video.html (16:9, Swedish), one page per caption. Part 2
shows /rounds, the owner's page for running revision rounds. That page needs a
key and shows the owner's own drawings, so it is rendered here from
src/rmink/web/static/rounds.html with example data from the demo (Altan) and
a stubbed API. The PDF says so. Layout and paging come from promo/pdf.py.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = ROOT / "docs" / "revisionsvarv.pdf"

_spec = importlib.util.spec_from_file_location("promo_pdf", HERE.parent / "pdf.py")
P = importlib.util.module_from_spec(_spec)
sys.modules["promo_pdf"] = P
_spec.loader.exec_module(P)
Step, Chapter, Part, Meta = P.Step, P.Chapter, P.Part, P.Meta


# --- part 1: the video ------------------------------------------------------

VIDEO = [
    Chapter("ide", "Idén", [
        Step("Från handskiss till ren ritning", "En idé för rmink, och hur långt den har kommit. Videon följer en altan från en handskiss på plattan till en ren ritning i flera revisioner.", t=5),
        Step("Ritningar diskuteras i omgångar", "Någon skissar för hand, man pratar om en del i taget, och sedan ritas allt om. Igen. Varje omgång kostar en ny ritning.", t=16),
        Step("Tänk tvärtom", "Skissa på plattan och få tillbaka en ren ritning. Markera den, så kommer nästa revision. Loopen är skissa, renritas, markera och ny revision.", t=26),
    ]),
    Chapter("renritning", "1 · Renritning", [
        Step("Skissen blir data", "rmink läser varje streck och delar upp skissen i numrerade grupper. Långa streck blir linjer och cirklar med exakta koordinater.", t=33),
        Step("Claude tolkar", "Vad är vägg, mått eller pelare? Claude avgör vad varje grupp är, och legenden i hörnet säger vad symbolerna betyder. Blå penna betyder VVS och röd penna el.", t=42),
        Step("Ren ritning, revision 1", "Raka linjer och hörn, måttlinjer med pilar, symboler, legend och revisionsruta, som riktiga pennstreck på plattan. Måtten 4800 och 3600 stämmer med skissen.", t=54),
        Step("Med och utan färg", "Paper Pro visar kategorierna i färg. rm2 och Paper Pure skiljer dem åt med linjetyp och tjocklek.", t=62),
    ]),
    Chapter("granskning", "2 · Granskning", [
        Step("Markera med pennan", "Ring in pelaren och skriv en fråga. Kryssa över brunnen. Det behövs inga formulär.", t=68.5),
        Step("Bara det nya läses", "rmink känner igen sina egna streck och lämnar bara dina markeringar åt Claude. Krysset blir en ändring och ringen med texten en fråga.", t=74),
        Step("Revision 2", "Brunnen är borta. Frågan om pelaren blir anmärkning 1, och loggen visar vad som ändrats.", t=79.5),
    ]),
    Chapter("varianter", "3 · Varianter (koncept)", [
        Step("Två förslag sida vid sida", "Ska bärlinan gå längs eller tvärs? Claude tar fram båda ur samma ritning, som två sidor i samma anteckningsbok.", t=85.5),
        Step("Jämför", "Varianterna är data, så de går att räkna på: bärlinor, nya pelare, största spann och balklängd.", t=90),
        Step("Välj med pennan", "Kryss på A och bock på B. B blir revision 3, och loggen säger varför.", t=95.5),
    ]),
    Chapter("nedslag", "4 · Nedslag (koncept)", [
        Step("Zooma in på ett hörn", "Ring in hörnet vid pelaren och skriv DETALJ.", t=100.5),
        Step("En detaljsida i skala 1:5", "Pelaren 90 × 90 och väggarna 45 mm ritas i riktiga mått. Översikten får en ring A som pekar dit.", t=106),
        Step("Fortsätt i detaljen", "Skissa ett vinkelbeslag. Det ritas rent, och frågan om typ blir en anmärkning.", t=111.5),
    ]),
    Chapter("papper", "5 · Pappersskiss", [
        Step("Ingen platta med?", "Fota pappersskissen med mobilen, direkt i rmink.", t=116.5),
        Step("Bläck ur fotot", "Det är samma fotokonvertering som rmink har i dag. Bordet och papperskanten blir inte bläck.", t=122),
        Step("Ren ritning på plattan", "Fotot tolkas som en skiss från plattan och skickas till din reMarkable.", t=127.5),
    ]),
    Chapter("export", "6 · Export", [
        Step("Dela utan platta", "Alla format ritas ur samma modell, så nästa revision följer med överallt.",
             ["SVG för att dela direkt finns redan.", "PDF i 1:25 på A4 är nästa steg.", "DXF med lager i mm är nästa steg."], t=141.5),
    ]),
    Chapter("laget", "Läget", [
        Step("Var står vi?", "Det här finns i fas 1: läsa sidor från plattan och molnet, gruppering och renritning, granskningsrundor och revisioner, färg och gråskala samt SVG-export och mobilfoto.",
             ["Nästa steg: testa på en riktig rm2, riktiga skisser, renritning i webbappen och sedan varianter, nedslag, PDF och DXF."], t=153.5),
        Step("Skissa du. Vi ritar rent.", "rmink är gratis och öppen källkod.", ["rmink.vercel.app", "github.com/thagvall/rmink"], t=160),
    ]),
]


# --- part 2: /rounds with example data --------------------------------------

def strokes_png(strokes: list[dict], path: Path) -> Path:
    """A demo page (pen strokes as SVG paths) as a PNG, for the round's preview."""
    paths = "".join(f'<path d="{s["d"]}" stroke="{s["c"]}" stroke-width="{s["w"]}"/>' for s in strokes)
    svg = path.with_suffix(".svg")
    svg.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="40 120 1360 1500" width="680" height="750">'
                   f'<rect x="40" y="120" width="1360" height="1500" fill="#fff"/>'
                   f'<g fill="none" stroke-linecap="round" stroke-linejoin="round">{paths}</g></svg>')
    subprocess.run(["rsvg-convert", "-o", path, svg], check=True)
    return path


def rounds_example(tmp: Path) -> dict:
    """What the page needs: a browser memory with two drawings, a folder listing and one round's answer."""
    final = json.loads((ROOT / "promo" / "sketch-demo" / "data2.json").read_text())["final"]["pro"]
    final = final["same"] + final["new"]  # r03: what r02 had plus the new strokes
    preview = base64.b64encode(strokes_png(final, tmp / "altan-r03.png").read_bytes()).decode()
    altan = {
        "name": "Altan", "revision": 2, "date": "2026-10-27",
        "annotations": [{"status": "open", "text": "P3: flytta 200 mm? Bärlinan längs eller tvärs?"}],
        "sketch": {"sent_as": "/rmink/Altan/Altan r02", "device": "pro"},
        "log": ["r01 Renritad från skiss · Förslag", "r02 Brunn B1 struken, P3 under diskussion · Granskning"],
    }
    field = lambda q, a, sol, ok=True: {"prompt": q, "answer": a, "confident": ok, "solution": sol, "verdict": "right" if a else None, "awarded": 1 if a else 0, "points": 1}
    brak = {
        "kind": "workbook", "name": "Bråk", "revision": 2, "date": "2026-10-29", "mode": "practice", "device": "rm2",
        "sections": [{"fields": [field("1/2 + 1/4", "3/4", "3/4"), field("0,25 i procent", "25 %", "25 %"),
                                 field("3/5 av 40", "24", "24", ok=False), field("Förläng 2/3 till tolftedelar", None, "8/12")]}],
        "sent_as": "/rmink/Bråk/Bråk r02", "log": ["r01 Skapad · 4 frågor", "r02 3 svar lästa"],
    }
    return {
        "memory": {"drawings": {"Altan": json.dumps(altan), "Bråk": json.dumps(brak)}, "links": {}},
        "entries": [{"name": "Altan", "path": "/rmink/Altan", "folder": True},
                    {"name": "Bråk", "path": "/rmink/Bråk", "folder": True},
                    {"name": "Förråd", "path": "/rmink/Förråd", "folder": False}],
        "run": {"sent_as": "/rmink/Altan/Altan r03", "drawing": "Altan", "revision": 3,
                "summary": "Bocken på sida 2 väljer variant B: två bärlinor tvärs, utan nya pelare. Frågan om P3 är besvarad och stängd, och r02 ligger nu i Tidigare.",
                "open_questions": [], "preview_png": preview, "store": None, "seconds": 52,
                "usage": {"input_tokens": 6100, "cache_read_input_tokens": 17800, "cache_creation_input_tokens": 0, "output_tokens": 2300, "usd": 0.09}},
    }


# Runs before the page script: the browser memory, the key and a fake API.
STUB = """<script>
const EX = __EX__;
try { localStorage.clear(); if (__KEY__) localStorage.setItem("rmink.roundsSecret", "exempel");
  localStorage.setItem("rmink.roundsMemory", JSON.stringify(EX.memory)); localStorage.setItem("rmink.roundsDevice", "pro"); } catch {}
window.fetch = async (url) => {
  const body = String(url).includes("/documents") ? { entries: EX.entries, missing: false } : EX.run;
  await new Promise(r => setTimeout(r, 30));
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
};
</script>"""

# Per state: the cards to show and what to do once the page is up.
STATES = {
    "nyckel": (False, "header, #login", ""),
    "lista": (True, "header, #drawings", "document.querySelectorAll('details').forEach(d => d.open = true);"),
    "skiss": (True, "#pick", "setTimeout(() => [...document.querySelectorAll('#list .item')].find(b => b.textContent.startsWith('Förråd')).click(), 200);"),
    "varv": (True, "#result", "setTimeout(() => document.querySelector('#drawing-list button.run').click(), 200);"),
    "arbetsbok": (True, "#create", "document.querySelector('#topic').value = 'Bråk och procent för åk 5, med vardagsexempel'; document.querySelector('#wbname').value = 'Bråk';"),
}


def rounds_shots(tmp: Path) -> dict[str, Path]:
    page = (ROOT / "src" / "rmink" / "web" / "static" / "rounds.html").read_text()
    ex = json.dumps(rounds_example(tmp))
    out = {}
    for name, (key, show, after) in STATES.items():
        hide = f"<style>main > *:not({show}) {{ display: none !important; }} body {{ padding-bottom: 0 !important; }}</style>"
        doc = page.replace("<head>", "<head>" + STUB.replace("__EX__", ex).replace("__KEY__", "true" if key else "false"), 1)
        doc = doc.replace("</body>", f"{hide}<script>{after}</script></body>")
        src = tmp / f"rounds-{name}.html"
        src.write_text(doc)
        png = tmp / f"rounds-{name}.png"
        subprocess.run([P.chrome(), "--headless", "--hide-scrollbars", "--force-device-scale-factor=2", "--window-size=640,1500",
                        "--blink-settings=preferredColorScheme=1",  # light, like the rest of the PDF
                        "--virtual-time-budget=5000", f"--screenshot={png}", src.as_uri()], check=True, capture_output=True)
        img = Image.open(png).convert("RGB")
        bg = Image.new("RGB", img.size, img.getpixel((2, 2)))
        x0, y0, x1, y1 = ImageChops.difference(img, bg).getbbox()
        img.crop((max(0, x0 - 30), max(0, y0 - 30), min(img.width, x1 + 30), min(img.height, y1 + 30))).save(png)
        out[name] = png
    return out


def rounds_chapters(shots: dict[str, Path]) -> list[Chapter]:
    ex = "Exempeldata från demon (Altan och en arbetsbok), inte riktiga ritningar."
    return [Chapter("rounds", "Sidan /rounds", [
        Step("Nyckel", "Sidan är bara för ägaren. Första gången skriver du in nyckeln, samma som RMINK_ROUNDS_SECRET på servern. Den sparas i webbläsaren.",
             ["Adress: rmink.vercel.app/rounds", "Utan nyckel visas bara den här rutan."], images=[("rounds · nyckel", shots["nyckel"])]),
        Step("Ritningar och arbetsböcker", "Ritningar och arbetsböcker du kört varv på sparas i webbläsaren, den senaste först. Varje kort visar revision, datum, öppna frågor och historik, och nästa varv är ett tryck bort.",
             ["En ritning visar sina öppna frågor, som besvaras på SVAR-raderna på plattan.", "En arbetsbok visar hur många frågor som är besvarade, poängen och svar att kolla.", ex],
             images=[("rounds · ritningar och arbetsböcker", shots["lista"])]),
        Step("Ny skiss", "Lägg skissen i mappen rmink på plattan. Välj den här, välj platta och kör första varvet. Anteckningsbokens namn blir ritningens namn, och en skiss i en egen mapp under rmink får mappens namn.",
             ["Mappar i rmink är ritningar, och lösa anteckningsböcker är nya skisser.", ex], images=[("rounds · ny skiss", shots["skiss"])]),
        Step("Kör nästa varv", "Markera eller skriv på plattan, låt den synka och tryck på Kör nästa varv. rmink läser bara de nya strecken, och Claude tolkar dem. Den nya revisionen hamnar i rmink/<namn> och den förra flyttas till Tidigare.",
             ["Resultatet visar sammanfattning, öppna frågor, förhandsbild, tid och kostnad.", ex], images=[("rounds · resultat av ett varv", shots["varv"])]),
        Step("Ny arbetsbok", "Claude skriver en arbetsbok med innehållsförteckning, avsnitt och svarsrutor och lägger den i rmink/<namn>. Skriv svaren för hand, låt plattan synka och kör nästa varv, så blir handstilen text.",
             ["Övning: facit ligger i ett dolt lager från början.", "Prov: facit och resultat kommer efter rättningen."], images=[("rounds · ny arbetsbok", shots["arbetsbok"])]),
    ])]


def mp4_stills(tmp: Path, mp4: Path, times: list[float]) -> dict[float, Path]:
    """Frames straight out of a rendered video, at the same times as the timeline stills."""
    out = {}
    for t in times:
        jpg = tmp / f"v{t}.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-ss", str(t), "-i", mp4, "-frames:v", "1", "-q:v", "2", "-y", jpg], check=True)
        out[t] = jpg
    return out


def print_pdf(tmp: Path, html: str, out: Path) -> None:
    doc = tmp / "doc.html"
    doc.write_text(html)
    subprocess.run(
        [P.chrome(), "--headless", "--disable-gpu", "--no-pdf-header-footer", "--generate-pdf-document-outline",
         "--allow-file-access-from-files", f"--print-to-pdf={out}", doc.as_uri()],
        check=True, capture_output=True,
    )


def video_only(tmp: Path, mp4: Path, version: str) -> Path:
    """The video alone, in two parts: the idea and what is built, then the concepts and where it stands."""
    out = ROOT / "docs" / "skissvideon.pdf"
    frames = mp4_stills(tmp, mp4, sorted({s.t for c in VIDEO for s in c.steps}))
    parts = [
        Part("p1", "Idén och fas 1", "Problemet och idén, och sedan det som finns i fas 1: skissen blir data, Claude tolkar, revision 1 ritas rent och en granskningsrunda ger revision 2. Klicka på en bild för att gå till steget.", VIDEO[:3], cols=5, ar="16 / 9"),
        Part("p2", "Koncept och läget", "Det som visas som koncept: varianter, nedslag i en detalj, pappersskiss via mobilen och export. Sist kommer vad som finns i dag och vad som är nästa steg.", VIDEO[3:], cols=5, ar="16 / 9"),
    ]
    meta = Meta(
        "skissvideon", "Från handskiss till<br>ren ritning",
        f"Skissvideon bild för bild, med en sida per textruta och förklarande text. Bilderna är tagna ur {mp4.name}.",
        [frames[54]], '<a href="https://rmink.vercel.app/sketch/video/sv">videon</a> · <a href="https://rmink.vercel.app/sketch/sv">demon</a>',
        f"Bilderna är tagna ur {mp4.name}.", wide=True,
    )
    print_pdf(tmp, P.build(parts, frames, version, meta), out)
    return out


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--video", type=Path, help="only the video, with frames from this mp4 (writes docs/skissvideon.pdf)")
    args = ap.parse_args()
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        if args.video:
            out = video_only(tmp, args.video.resolve(), version)
            print(f"{out.relative_to(ROOT)}: {sum(len(c.steps) for c in VIDEO)} steg")
            return
        frames = P.stills(tmp, sorted({s.t for c in VIDEO for s in c.steps}), page="sketch-video/video.html",
                          size=(1920, 1080), inject=P.SEEK)
        parts = [
            Part("p1", "Videon steg för steg", "Videon om skiss till ritning, bild för bild: problemet, idén, och ett kapitel per scenario, det vill säga renritning, granskning, varianter, nedslag, pappersskiss och export. Sist kommer vad som finns i dag. Klicka på en bild för att gå till steget.", VIDEO, cols=6, ar="16 / 9"),
            Part("p2", "Sidan /rounds", "På /rounds kör ägaren revisionsvarven från webben, utan Claude Desktop: välj en skiss, kör första varvet och sedan ett varv i taget efter varje omgång markeringar på plattan. Arbetsböcker skapas och rättas på samma sida. Bilderna är sidan som den ser ut med exempeldata från demon.", rounds_chapters(rounds_shots(tmp)), cols=5, ar="3 / 4"),
        ]
        meta = Meta(
            "revisionsvarv", "Från handskiss till<br>ren ritning, i varv",
            "Skissa på plattan, få tillbaka en ren ritning, markera den och få nästa revision. Del 1 följer videon steg för steg, och del 2 visar sidan /rounds där varven körs.",
            [frames[54]], '<a href="https://rmink.vercel.app/sketch/video/sv">videon</a> · <a href="https://rmink.vercel.app/sketch/sv">demon</a>',
            "Bilderna i del 2 visar /rounds med exempeldata.", wide=True,
        )
        print_pdf(tmp, P.build(parts, frames, version, meta), OUT)
    print(f"{OUT.relative_to(ROOT)}: {sum(len(c.steps) for p in parts for c in p.chapters)} steg")


if __name__ == "__main__":
    main()
