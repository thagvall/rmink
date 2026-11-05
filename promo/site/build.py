"""Build the public site pages into deploy/vercel/public: the home page in both
languages, /skola and /bygg. Run from the repo root:

    python promo/site/build.py            # pages
    python promo/site/build.py --images   # also the pictures, from promo/out

site.css and site.js in deploy/vercel/public are hand-written. Pictures need
Pillow and the local promo/out, which is why they are a separate step.
"""

from __future__ import annotations

import html
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "deploy" / "vercel" / "public"
OUT = ROOT / "promo" / "out"
SITE = "https://rmink.vercel.app"
GITHUB = "https://github.com/thagvall/rmink"
SUPPORT = "https://buy.stripe.com/7sY4gy4b1aQo0iI0SB1sQ00"
RMAPI = "https://github.com/ddvk/rmapi"
CONNECT = "https://my.remarkable.com/device/browser/connect"
MCP_ADD = "claude mcp add rmink -- uvx --from 'rmink[mcp]' rmink mcp"

FONTS = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&family=IBM+Plex+Mono:wght@400;500&display=swap">"""
ICON = """<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%23222'/%3E%3Cpath d='M7 22c4-9 7-12 9-6s5 3 9-6' stroke='%23fff' stroke-width='2.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E">"""

# Runs before the page paints. Picks the language for / and /sv: an explicit
# choice wins (?demo=sv from a link, ?lang= from the switch), then a saved one,
# then the browser's.
LANG_SCRIPT = """<script>
(function () {
  var q = new URLSearchParams(location.search), lang = q.get("lang"), demo = q.get("demo"), saved = null;
  try {
    if (lang) localStorage.setItem("rmink.lang", lang);
    saved = localStorage.getItem("rmink.lang");
  } catch (e) {}
  if (%(english)s && (demo === "sv" || (demo !== "en" && lang !== "en" && saved !== "en"
      && (saved === "sv" || navigator.language.indexOf("sv") === 0)))) {
    q.delete("lang");
    var s = q.toString();
    location.replace("/sv" + (s ? "?" + s : "") + location.hash);
  } else if (lang) {
    q.delete("lang");
    var t = q.toString();
    history.replaceState(null, "", location.pathname + (t ? "?" + t : "") + location.hash);
  }
})();
</script>"""

TEXT = {
    "en": {
        "file": "home.html", "path": "/", "other": "Svenska", "other_lang": "sv", "other_href": "/sv?lang=sv",
        "home": "/", "sketch": "/sketch", "skola": "/skola", "bygg": "/bygg",
        "title": "rmink: write by hand, rmink does the rest",
        "desc": "Free and open source. Photos become real reMarkable pen strokes, sketches become clean "
                "drawings and workbooks get marked, right on your tablet.",
        "image_alt": "rmink on a reMarkable",
        "nav": ("What it does", "rmink for", "Video"),
        "open_tool": "Open the tool", "copy": "Copy", "copied": "Copied", "close": "Close",
        "h1": ("Write by hand.", "rmink does the rest."),
        "lede": "Photos become real pen strokes, sketches become clean drawings and workbooks get marked, "
                "right on your reMarkable. Not a picture behind your notes.",
        "try": "Try it free", "watch": "Watch the video",
        "free_note": "Free and open source. No account needed.",
        "photo": "a photo", "ink": "real, editable ink on the tablet",
        "abilities_eyebrow": "What it does",
        "abilities_h": "Three things your pen can do with rmink",
        "abilities_lede": "The first works in your browser right now. The other two run in your own Claude.",
        "open_tag": "Open in your browser", "claude_tag": "With your Claude",
        "cards": [
            ("Image to ink", "Notes, sketches, logos and PDFs become strokes you can erase, lasso, move and "
             "recolour, like your own handwriting.", "open", "/app", "Open the tool", "note-ink-en.png"),
            ("Sketch to drawing", "Sketch on the tablet and get a clean drawing with dimensions, symbols and "
             "a title block. Mark it up with the pen and the next revision comes back.",
             "claude", "/sketch", "See the interactive demo", "bygg-r08.png"),
            ("Workbooks", "Claude writes a linked workbook. You answer by hand, your handwriting becomes "
             "text and the answers are marked, with the solutions on a hidden layer.",
             "claude", "/skola", "Read more (in Swedish)", "skola-marked.png"),
        ],
        "also": ["Five grey-tone styles", "PDF and SVG as vectors", "Send straight to your reMarkable",
                 "Take a photo with your phone", "Several files in one notebook"],
        "for_eyebrow": "rmink for",
        "for_h": "Made for a particular job",
        "for_lede": "The same pen, aimed at one audience and one need. These are in Swedish for now, "
                    "because their content follows Swedish school years and building rules.",
        "audience": [
            ("skola", "/skola", "Teachers, parents and pupils", "Practise by hand, with no screens to tap.",
             "8 groups · 65 topics · years 1–9", "Read more (in Swedish)", "skola-answers.png"),
            ("bygg", "/bygg", "Anyone who builds, draws or reviews small buildings",
             "From hand sketch to drawing, in revision rounds.",
             "33 drawing symbols · 53 review rules · 43 materials", "Read more (in Swedish)", "bygg-r00.png"),
        ],
        "how_eyebrow": "Image to ink",
        "how_h": "From photo to tablet",
        "how": [
            ("Drop in a photo", "A photo of your notes, a sketch, a logo or a PDF. On a phone you can take the photo right there."),
            ("See the ink", "Pick your tablet and a style. The preview shows exactly what you will get."),
            ("Put it on the tablet", "Send it straight to reMarkable, or download the notebook and copy it over."),
        ],
        "claude_h": "rmink in your own Claude",
        "claude_p": "Sketches, drawings and workbooks run in your own Claude, on your own Claude account. "
                    "Add rmink as an MCP server in Claude Code or Claude Desktop and ask.",
        "claude_note": "You also need rmapi to reach your tablet, and you run a few commands in a terminal.",
        "free_h": "Free, and it stays that way",
        "free_p": "rmink is open source under AGPL-3.0. If it saves you time, you are welcome to support it with 100 kr.",
        "source": "Source code", "support": "Support rmink · 100 kr",
        "foot_tools": "Tools", "foot_for": "rmink for", "foot_about": "About",
        "foot_image": "Image to ink", "foot_sketch": "Sketch to drawing", "foot_video": "Watch the video",
        "devices": "Tested on reMarkable 2. Paper Pro, Paper Pure and Move are in beta.",
        "legal": "rmink is free software (AGPL-3.0). Not affiliated with or endorsed by reMarkable AS.",
        "video": "/promo/rmink-promo-en.mp4", "poster": "/promo/poster-en.jpg",
    },
    "sv": {
        "file": "home-sv.html", "path": "/sv", "other": "English", "other_lang": "en", "other_href": "/?lang=en",
        "home": "/sv", "sketch": "/sketch/sv", "skola": "/skola", "bygg": "/bygg",
        "title": "rmink: skriv för hand, rmink gör resten",
        "desc": "Gratis och öppen källkod. Foton blir riktiga reMarkable-pennstreck, skisser blir rena "
                "ritningar och arbetsböcker rättas, direkt på din platta.",
        "image_alt": "rmink på en reMarkable",
        "nav": ("Förmågor", "rmink för", "Film"),
        "open_tool": "Öppna verktyget", "copy": "Kopiera", "copied": "Kopierat", "close": "Stäng",
        "h1": ("Skriv för hand.", "rmink gör resten."),
        "lede": "Foton blir riktiga pennstreck, skisser blir rena ritningar och arbetsböcker rättas, "
                "direkt på din reMarkable. Inte en bild bakom anteckningarna.",
        "try": "Prova gratis", "watch": "Se filmen",
        "free_note": "Gratis och öppen källkod. Inget konto behövs.",
        "photo": "ett foto", "ink": "riktigt, redigerbart bläck på plattan",
        "abilities_eyebrow": "Förmågor",
        "abilities_h": "Tre saker pennan kan göra med rmink",
        "abilities_lede": "Den första fungerar i webbläsaren direkt. De andra två körs i din egen Claude.",
        "open_tag": "Öppet i webbläsaren", "claude_tag": "Med din Claude",
        "cards": [
            ("Bild till bläck", "Anteckningar, skisser, logotyper och PDF:er blir streck du kan sudda, lassa, "
             "flytta och färga om, precis som din egen handstil.", "open", "/app", "Öppna verktyget", "note-ink-sv.png"),
            ("Skiss till ritning", "Skissa på plattan och få tillbaka en ren ritning med mått, symboler och "
             "ritningshuvud. Markera med pennan så kommer nästa revision.",
             "claude", "/bygg", "Läs om rmink bygg", "bygg-r08.png"),
            ("Arbetsböcker", "Claude skriver en länkad arbetsbok. Du svarar för hand, handstilen blir text och "
             "svaren rättas, med facit i ett dolt lager.", "claude", "/skola", "Läs om rmink skola", "skola-marked.png"),
        ],
        "also": ["Fem gråtonsstilar", "PDF och SVG som vektorer", "Skicka direkt till din reMarkable",
                 "Ta fotot med mobilen", "Flera filer i en anteckningsbok"],
        "for_eyebrow": "rmink för",
        "for_h": "Gjort för ett visst jobb",
        "for_lede": "Samma penna, riktad mot en publik och ett behov.",
        "audience": [
            ("skola", "/skola", "För lärare, föräldrar och elever", "Öva för hand, utan skärmar att klicka i.",
             "8 grupper · 65 moment · åk 1–9", "Läs om rmink skola", "skola-answers.png"),
            ("bygg", "/bygg", "För dig som bygger, ritar eller granskar småhus",
             "Från handskiss till ritning, i revisionsvarv.",
             "33 ritsymboler · 53 granskningsregler · 43 varuslag", "Läs om rmink bygg", "bygg-r00.png"),
        ],
        "how_eyebrow": "Bild till bläck",
        "how_h": "Från foto till platta",
        "how": [
            ("Släpp in ett foto", "Ett foto av anteckningar, en skiss, en logotyp eller en PDF. I mobilen tar du fotot direkt."),
            ("Se bläcket", "Välj platta och stil. Förhandsvisningen visar precis vad du får."),
            ("Lägg det på plattan", "Skicka direkt till reMarkable, eller ladda ner anteckningsboken och lägg över den."),
        ],
        "claude_h": "rmink i din egen Claude",
        "claude_p": "Skisser, ritningar och arbetsböcker körs i din egen Claude, på ditt eget Claude-konto. "
                    "Lägg till rmink som MCP-server i Claude Code eller Claude Desktop och fråga på.",
        "claude_note": "Du behöver också rmapi för att nå plattan, och du kör några kommandon i en terminal.",
        "free_h": "Gratis, och det förblir så",
        "free_p": "rmink är öppen källkod under AGPL-3.0. Om det sparar dig tid får du gärna stötta med 100 kr.",
        "source": "Källkod", "support": "Stöd rmink · 100 kr",
        "foot_tools": "Verktyg", "foot_for": "rmink för", "foot_about": "Om",
        "foot_image": "Bild till bläck", "foot_sketch": "Skiss till ritning", "foot_video": "Se filmen",
        "devices": "Testat på reMarkable 2. Paper Pro, Paper Pure och Move är i beta.",
        "legal": "rmink är fri programvara (AGPL-3.0). Fristående från reMarkable AS.",
        "video": "/promo/rmink-promo-sv.mp4", "poster": "/promo/poster-sv.jpg",
    },
}


def e(text: str) -> str:
    return html.escape(text, quote=True)


def head(t: dict, *, lang: str, title: str, desc: str, path: str, image: str, extra: str = "") -> str:
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{SITE}{path}">
{extra}<meta property="og:type" content="website">
<meta property="og:site_name" content="rmink">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{SITE}{path}">
<meta property="og:image" content="{SITE}{image}">
<meta property="og:image:secure_url" content="{SITE}{image}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="627">
<meta property="og:image:alt" content="{e(t["image_alt"])}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:image" content="{SITE}{image}">
{ICON}
{FONTS}
<link rel="stylesheet" href="/site.css">
"""


def bar(t: dict, lang_link: bool = True) -> str:
    switch = (
        f'<a class="lang" href="{t["other_href"]}" lang="{t["other_lang"]}">{t["other"]}</a>' if lang_link else ""
    )
    return f"""<header class="bar"><div class="wrap">
  <a class="brand" href="{t["home"]}">rmink</a>
  <nav>
    <a href="{t["home"]}#abilities">{t["nav"][0]}</a>
    <a href="{t["home"]}#for">{t["nav"][1]}</a>
    <button type="button" data-video="default">{t["nav"][2]}</button>
    {switch}
  </nav>
  <a class="btn primary small" href="/app">{t["open_tool"]}</a>
</div></header>
"""


def footer(t: dict) -> str:
    return f"""<footer><div class="wrap">
  <div class="cols">
    <div><b>{t["foot_tools"]}</b><ul>
      <li><a href="/app">{t["foot_image"]}</a></li>
      <li><a href="{t["sketch"]}">{t["foot_sketch"]}</a></li>
      <li><a href="{t["home"]}#claude">{t["claude_h"]}</a></li>
    </ul></div>
    <div><b>{t["foot_for"]}</b><ul>
      <li><a href="/skola">rmink skola</a></li>
      <li><a href="/bygg">rmink bygg</a></li>
    </ul></div>
    <div><b>{t["foot_about"]}</b><ul>
      <li><a href="{GITHUB}" rel="noopener">{t["source"]}</a></li>
      <li><a href="{SUPPORT}" rel="noopener">{t["support"]}</a></li>
    </ul></div>
  </div>
  <p>{t["devices"]}</p>
  <p>{t["legal"]}</p>
</div></footer>
"""


def dialog(t: dict) -> str:
    return f"""<dialog id="video-dialog" aria-label="{t["nav"][2]}">
  <button type="button" class="close" aria-label="{t["close"]}">×</button>
  <video controls playsinline preload="none"></video>
</dialog>
<script src="/site.js" defer></script>
"""


def cmd(t: dict, command: str) -> str:
    return (
        f'<div class="cmd"><code>{e(command)}</code>'
        f'<button type="button" data-copy="{e(command)}" data-done="{t["copied"]}">{t["copy"]}</button></div>'
    )


def home(lang: str) -> str:
    t = TEXT[lang]
    alternate = (
        f'<link rel="alternate" hreflang="en" href="{SITE}/">\n'
        f'<link rel="alternate" hreflang="sv" href="{SITE}/sv">\n'
    )
    cards = "\n".join(
        f"""    <article class="card">
      <div class="sheet"><img src="/home/{img}" alt="" loading="lazy" width="800" height="1067"></div>
      <span class="tag{" open" if tag == "open" else ""}">{t["open_tag"] if tag == "open" else t["claude_tag"]}</span>
      <h3>{name}</h3>
      <p>{text}</p>
      <a class="more" href="{href}">{link} →</a>
    </article>"""
        for name, text, tag, href, link, img in t["cards"]
    )
    audience = "\n".join(
        f"""    <article class="card audience">
      <div class="body">
        <p class="who">{who}</p>
        <h3>rmink {key}</h3>
        <p class="need">{need}</p>
        <p class="facts">{facts}</p>
        <a class="more" href="{href}">{link} →</a>
      </div>
      <div class="sheet"><img src="/home/{img}" alt="" loading="lazy" width="800" height="1067"></div>
    </article>"""
        for key, href, who, need, facts, link, img in t["audience"]
    )
    also = "".join(f"<li>{x}</li>" for x in t["also"])
    how = "\n".join(f"    <li><h3>{a}</h3><p>{b}</p></li>" for a, b in t["how"])
    return (
        head(t, lang=lang, title=t["title"], desc=t["desc"], path=t["path"], image="/og.jpg", extra=alternate)
        + LANG_SCRIPT % {"english": "true" if lang == "en" else "false"}
        + f"""
</head>
<body data-video="{t["video"]}" data-poster="{t["poster"]}">
{bar(t)}
<main>
<section class="hero"><div class="wrap">
  <div class="text">
    <h1><span>{t["h1"][0]}</span><span class="stroke">{t["h1"][1]}</span></h1>
    <p class="lede">{t["lede"]}</p>
    <div class="actions">
      <a class="btn primary" href="/app">{t["try"]}</a>
      <button type="button" class="btn" data-video="default"><span class="play" aria-hidden="true">▶</span> {t["watch"]}</button>
    </div>
    <p class="note">{t["free_note"]}</p>
  </div>
  <figure class="stack">
    <img class="photo" src="/home/note-photo-{lang}.jpg" alt="{t["photo"]}" width="480" height="600">
    <div class="tablet"><img src="/home/note-ink-{lang}.png" alt="{t["ink"]}" width="800" height="1067"></div>
  </figure>
</div></section>

<section id="abilities"><div class="wrap">
  <div class="head">
    <span class="eyebrow">{t["abilities_eyebrow"]}</span>
    <h2>{t["abilities_h"]}</h2>
    <p class="lede">{t["abilities_lede"]}</p>
  </div>
  <div class="grid">
{cards}
  </div>
  <ul class="also">{also}</ul>
</div></section>

<section id="for"><div class="wrap">
  <div class="head">
    <span class="eyebrow">{t["for_eyebrow"]}</span>
    <h2>{t["for_h"]}</h2>
    <p class="lede">{t["for_lede"]}</p>
  </div>
  <div class="grid two">
{audience}
  </div>
</div></section>

<section id="how"><div class="wrap">
  <div class="head">
    <span class="eyebrow">{t["how_eyebrow"]}</span>
    <h2>{t["how_h"]}</h2>
  </div>
  <ol class="steps">
{how}
  </ol>
</div></section>

<section id="claude"><div class="wrap split">
  <div class="prose">
    <h2>{t["claude_h"]}</h2>
    <p>{t["claude_p"]}</p>
    {cmd(t, MCP_ADD)}
    <p class="note">{t["claude_note"]}</p>
  </div>
  <div class="prose">
    <h2>{t["free_h"]}</h2>
    <p>{t["free_p"]}</p>
    <div class="actions">
      <a class="btn small" href="{GITHUB}" rel="noopener">{t["source"]}</a>
      <a class="btn small" href="{SUPPORT}" rel="noopener">{t["support"]}</a>
    </div>
  </div>
</div></section>
</main>
{footer(t)}{dialog(t)}</body>
</html>
"""
    )


def get_started(t: dict, prompt: str, example: str) -> str:
    return f"""<section id="kom-igang"><div class="wrap split">
  <div class="prose">
    <span class="eyebrow">{t["claude_tag"]}</span>
    <h2>Kom igång</h2>
    <p>Det här körs i din egen Claude, på ditt eget Claude-konto. Hos rmink är det gratis. Du behöver kunna
    köra några kommandon i en terminal, och <a href="https://docs.astral.sh/uv/" rel="noopener">uv</a> installerat.</p>
    <p class="warn">Testat på reMarkable 2. Övriga plattor är i beta, och koordinaterna i arbetsböcker är bara
    verifierade på rm2.</p>
  </div>
  <ol class="steps" style="grid-template-columns:minmax(0,1fr)">
    <li><h3>Lägg till rmink i Claude</h3>{cmd(t, MCP_ADD)}</li>
    <li><h3>Installera rmapi</h3><p>Med <a href="{RMAPI}" rel="noopener">rmapi</a> kommer rmink åt din platta
    via reMarkable Cloud.</p></li>
    <li><h3>Koppla plattan</h3><p>Hämta en engångskod på
    <a href="{CONNECT}" rel="noopener">my.remarkable.com</a> och ge den till Claude.</p></li>
    <li><h3>{prompt}</h3>{cmd(t, example)}</li>
  </ol>
</div></section>
"""


def vertical(*, path: str, title: str, desc: str, eyebrow: str, h1: tuple[str, str], lede: str,
             folder: str, video: str, watch: str, steps: str, steps_h: str, body: str, image: str) -> str:  # fmt: skip
    t = dict(TEXT["sv"])
    return (
        head(t, lang="sv", title=title, desc=desc, path=path, image=image)
        + f"""</head>
<body data-video="/promo/{folder}/{video}.mp4" data-poster="/promo/{folder}/poster.jpg">
{bar(t, lang_link=False)}
<main>
<section class="hero"><div class="wrap">
  <div class="text">
    <span class="eyebrow">{eyebrow}</span>
    <h1><span>{h1[0]}</span><span class="stroke">{h1[1]}</span></h1>
    <p class="lede">{lede}</p>
    <div class="actions">
      <a class="btn primary" href="#kom-igang">Kom igång</a>
      <button type="button" class="btn" data-video="default"><span class="play" aria-hidden="true">▶</span> {watch}</button>
    </div>
    <span class="tag">{t["claude_tag"]}</span>
  </div>
  <button type="button" class="poster" data-video="default" aria-label="{watch}">
    <img src="/promo/{folder}/poster.jpg" alt="" width="864" height="1080"><span>▶ {watch}</span>
  </button>
</div></section>

<section><div class="wrap">
  <div class="head"><span class="eyebrow">Riktiga sidor, inte en mockup</span><h2>{steps_h}</h2></div>
  <ol class="steps four">
{steps}
  </ol>
</div></section>
{body}</main>
{footer(t)}{dialog(t)}</body>
</html>
"""
    )


def step(img: str, h: str, p: str) -> str:
    return (
        f'    <li><div class="tablet"><img src="/home/{img}" alt="" loading="lazy" width="800" height="1067"></div>'
        f"<h3>{h}</h3><p>{p}</p></li>"
    )


def skola() -> str:
    catalog = tomllib.loads((ROOT / "src/rmink/workbook/data/skola.toml").read_text(encoding="utf-8"))
    groups = catalog["group"]
    subjects: dict[str, list[str]] = {}
    for g in groups:
        subjects.setdefault(g.get("folder", ""), []).append(g["title"])
    rows = "".join(
        f"<div><b>{subject}</b><span>{', '.join(names)}</span></div>" for subject, names in subjects.items()
    )
    topics = sum(len(g["topic"]) for g in groups)
    steps = "\n".join([
        step("skola-cover.png", "Claude skriver", "En arbetsbok med innehåll, länkar och svarsrutor landar i rätt ämnesmapp."),
        step("skola-answers.png", "Eleven svarar", "Med pennan, som på papper. Skriv i rutan och kryssa i flerval."),
        step("skola-marked.png", "rmink rättar", "Handstilen blir text och varje svar får poäng och kommentar."),
        step("skola-facit.png", "Tänd facit", "Facit ligger i ett dolt lager: rätt svar och hur man tänker."),
    ])  # fmt: skip
    body = (
        f"""<section><div class="wrap">
  <div class="head"><span class="eyebrow">Det här ingår</span>
    <h2>{len(groups)} grupper och {topics} moment, årskurs 1–9</h2>
    <p class="lede">Eller be om något eget: Claude skriver en arbetsbok om vilket ämne som helst och lägger den i en egen mapp.</p>
  </div>
  <div class="facts-list">{rows}</div>
</div></section>
"""
        + get_started(TEXT["sv"], "Be om en arbetsbok", "Gör en arbetsbok i Plus och minus för årskurs 3")
    )
    return vertical(
        path="/skola",
        title="rmink skola: skriv för hand, rmink rättar",
        desc="Arbetsböcker på din reMarkable. Claude skriver dem, eleven svarar för hand och rmink rättar. "
             "Matematik, svenska och engelska för årskurs 1–9.",
        eyebrow="rmink skola", h1=("Skriv för hand.", "rmink rättar."),
        lede="Arbetsböcker på din reMarkable. Claude skriver dem, eleven svarar för hand, och svaren rättas "
             "direkt på plattan. Inga tangentbord, inga skärmar att klicka i.",
        folder="skola", video="rmink-skola-real-sv-4x5", watch="Se filmen (52 s)",
        steps=steps, steps_h="Ett varv i en arbetsbok", body=body, image="/promo/skola/og.jpg",
    )  # fmt: skip


def bygg() -> str:
    steps = "\n".join([
        step("bygg-r00.png", "Du skissar", "För hand på plattan: mått, text och frågor."),
        step("bygg-r01.png", "rmink ritar rent", "Raka linjer, måttlinjer och ritningshuvud. Svara med pennan på SVAR-raderna."),
        step("bygg-alt.png", "Välj alternativ", "Upp till fyra lösningar med lager, U-värde, vikt och kostnadsnivå."),
        step("bygg-r08.png", "Nästa revision", "Äldre revisioner flyttas till Tidigare. Garaget här är revision 8."),
    ])  # fmt: skip
    body = (
        """<section><div class="wrap">
  <div class="head"><span class="eyebrow">Det här ingår</span>
    <h2>Mer än raka streck</h2>
    <p class="lede">Claude slår upp, och rmink räknar i kod i stället för att gissa.</p>
  </div>
  <div class="facts-list">
    <div><b>Mått och mängder</b><span>Längder, areor, vinklar, taklutning, mängder och vikt.</span></div>
    <div><b>Kunskapsbas</b><span>160 termer, 43 varuslag, 12 typkonstruktioner och 53 granskningsregler med källa (BFS, PBL, PBF, ElSL).</span></div>
    <div><b>33 ritsymboler</b><span>Även handritade varianter känns igen.</span></div>
  </div>
  <p class="warn" style="margin-top:28px">Ritningarna är ett underlag, inte konstruktionshandlingar. Konstruktör och kommun har sista ordet.</p>
  <p style="margin-top:20px"><a href="/sketch/sv">Prova den interaktiva demon →</a></p>
</div></section>
"""
        + get_started(TEXT["sv"], "Rita rent en skiss", "Rita rent skissen Garage i mappen rmink på min reMarkable")
    )
    return vertical(
        path="/bygg",
        title="rmink bygg: skissa du, rmink ritar rent",
        desc="Skissa på din reMarkable och få tillbaka en ren ritning med mått och symboler. Markera med "
             "pennan och nästa revision kommer. För småhus, altaner och garage.",
        eyebrow="rmink bygg", h1=("Skissa du.", "rmink ritar rent."),
        lede="Från handskiss till ritning, i revisionsvarv, för småhus, altaner och garage. Du markerar med "
             "pennan på plattan, och nästa revision kommer tillbaka dit.",
        folder="bygg", video="rmink-bygg-real-sv-4x5", watch="Se filmen (60 s)",
        steps=steps, steps_h="Ett garage, från skiss till revision 8", body=body, image="/promo/bygg/og.jpg",
    )  # fmt: skip


def images() -> None:
    """Scale the real output in promo/out for the web. Pages are cropped to the
    tablet's shape so the cards and frames line up."""
    from PIL import Image

    dest = PUBLIC / "home"
    dest.mkdir(exist_ok=True)

    def page(src: Path, name: str, width: int = 800) -> None:
        im = Image.open(src).convert("RGB")
        im = im.crop((0, 0, im.width, min(im.height, round(im.width * 4 / 3))))
        im = im.resize((width, round(width * 4 / 3)), Image.LANCZOS)
        # A few greys are enough for black ink on white, and far smaller.
        im.quantize(32).save(dest / name, optimize=True)

    for lang in ("en", "sv"):
        page(OUT / f"note-{lang}-preview.png", f"note-ink-{lang}.png")
        photo = Image.open(OUT / f"note-{lang}.jpg").convert("RGB")
        photo.thumbnail((480, 600))
        photo.save(dest / f"note-photo-{lang}.jpg", quality=82, optimize=True)
    for src, name in {
        "bygg/r00-p01.png": "bygg-r00.png",
        "bygg/r01-p01.png": "bygg-r01.png",
        "bygg/r01-p02.png": "bygg-alt.png",
        "bygg/r08-p01.png": "bygg-r08.png",
        "real/r01-p01.png": "skola-cover.png",
        "real/r01-p02.png": "skola-answers.png",
        "real/r02-p02.png": "skola-marked.png",
        "real/r02-p02-facit.png": "skola-facit.png",
    }.items():
        page(OUT / src, name)


def main() -> None:
    if "--images" in sys.argv:
        images()
    pages = {
        "home.html": home("en"),
        "home-sv.html": home("sv"),
        "skola.html": skola(),
        "bygg.html": bygg(),
    }
    for name, content in pages.items():
        (PUBLIC / name).write_text(content, encoding="utf-8")
        print(name, len(content))
    # The rewrites these pages need, for a quick look when something 404s.
    print(json.dumps(sorted(pages)))


if __name__ == "__main__":
    main()
