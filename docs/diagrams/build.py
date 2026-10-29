# ruff: noqa: E501  (diagram texts read best on one line)
"""Build the draw.io diagrams of rmink and its building knowledge base.

    python docs/diagrams/build.py            # writes docs/diagrams/NN-*.drawio
    python docs/diagrams/build.py --export   # and an .svg next to each (needs draw.io)

The diagrams are made from the code and data they show: the knowledge base
TOML files, the symbol and hatch drawing code, the Drawing model, the CLI, MCP
and web routes. Run this after changing any of them; tests/test_diagrams.py
checks that nothing in the knowledge base is missing from them.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from drawio import (  # noqa: E402
    Diagram,
    esc,
    label,
    plain_lines,
    svg_fit,
    svg_paths,
    table,
    table_height,
    text_height,
)

GAP = 16


# --- layout helpers ---------------------------------------------------------


def note_box(d: Diagram, x, y, w, title, lines, kind="core", parent="1", sub="") -> float:
    """A box sized to its text; returns the y below it."""
    h = text_height(plain_lines(title, lines, sub), w)
    d.box(x, y, w, h, label(title, lines, sub), kind, parent=parent, hint=title)
    return y + h


def table_box(
    d: Diagram, x, y, title, head, rows, widths, kind="data", parent="1", sub="", hint=None
) -> tuple[str, float]:
    """A box holding a titled table; returns (id, y below it)."""
    w = sum(widths) + 16
    top = 22 + (16 if sub else 0)
    h = top + table_height(rows, widths) + 12
    sub_html = f'<br><font color="#333333">{esc(sub)}</font>' if sub else ""
    value = f"<b>{esc(title)}</b>{sub_html}{table(rows, head, widths)}"
    cid = d.box(x, y, w, h, value, kind, parent=parent, hint=hint or title)
    return cid, y + h


def columns(d: Diagram, x, y, col_w, n_cols, boxes, gap=GAP):
    """Place boxes (callables taking x, y and returning bottom y) in the
    shortest of ``n_cols`` columns. Returns the bottom of the tallest column."""
    bottoms = [y] * n_cols
    for make in boxes:
        c = bottoms.index(min(bottoms))
        bottoms[c] = make(x + c * (col_w + gap), bottoms[c]) + gap
    return max(bottoms)


def snake(d: Diagram, x, y, w, per_row, steps, gap_x=60, gap_y=50) -> float:
    """Boxes in rows, linked left to right and down to the next row's start.
    ``steps`` are (title, lines, kind); returns the y below the last row."""
    prev = None
    for r in range(0, len(steps), per_row):
        row = steps[r : r + per_row]
        h = max(text_height(plain_lines(t, ls), w) for t, ls, _ in row)
        for i, (title, lines, kind) in enumerate(row):
            cid = d.box(x + i * (w + gap_x), y, w, h, label(title, lines), kind, hint=title)
            if prev:
                if i == 0:
                    d.edge(prev, cid, exit=(0.5, 1), entry=(0.5, 0))
                else:
                    d.edge(prev, cid, exit=(1, 0.5), entry=(0, 0.5))
            prev = cid
        y += h + gap_y
    return y


def kb():
    from rmink import knowledge

    return knowledge.load()


def rules_by_id() -> dict[str, dict]:
    return {r["id"]: r for r in kb()["rules"]["rule"]}


def short(text: str, n: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def sv(x: float) -> str:
    return f"{x:g}".replace(".", ",")


# --- 1. system overview ---------------------------------------------------------


def cli_commands() -> list[str]:
    from rmink import cli

    out = [c.name or c.callback.__name__ for c in cli.app.registered_commands]
    for g in cli.app.registered_groups:
        out += [
            f"{g.name} {c.name or c.callback.__name__}"
            for c in g.typer_instance.registered_commands
        ]
    return out


def mcp_tools() -> list[str]:
    try:
        import asyncio

        from rmink import mcp_server

        return [t.name for t in asyncio.run(mcp_server.server.list_tools())]
    except ImportError:
        return ["(installera rmink[mcp] för att lista verktygen)"]


def web_routes() -> list[str]:
    try:
        from rmink.web import rounds
        from rmink.web.app import Limits, create_app
    except ImportError:
        return ["(installera rmink[web] för att lista routerna)"]
    app = create_app(Limits.from_env())
    hidden = {"/openapi.json", "/docs/oauth2-redirect"}
    out = [
        f"{'/'.join(sorted(r.methods - {'HEAD'}))} {r.path}"
        for r in app.routes
        if getattr(r, "methods", None) and r.path not in hidden
    ]
    out += [
        f"{'/'.join(sorted(r.methods))} {r.path}  (bara med nyckel)" for r in rounds.router().routes
    ]
    return out


def d01_overview() -> Diagram:
    d = Diagram(
        "01-systemoversikt",
        "1. rmink – systemöversikt",
        "Vem som använder vad, rmink:s delar och de externa system de pratar med. "
        "Listorna läses ur koden när diagrammet byggs.",
    )
    y0 = 100
    # users
    users = d.group(40, y0, 230, 470, "Användare och enheter", "device")
    u_browser = d.box(
        12,
        40,
        206,
        66,
        label("Webbläsare", ["rmink.vercel.app", "telefon eller dator"]),
        "device",
        users,
    )
    u_claude = d.box(
        12,
        120,
        206,
        66,
        label("Claude Desktop / Code", ["användarens egen Claude", "via MCP (stdio)"]),
        "claude",
        users,
    )
    u_term = d.box(
        12,
        200,
        206,
        66,
        label("Terminal", ["pip install rmink", "kommandot rmink"]),
        "device",
        users,
    )
    d.box(
        12,
        280,
        206,
        90,
        label(
            "reMarkable-platta",
            [
                "rm2, Paper Pure, Paper Pro, Move",
                "synkar via reMarkable Cloud",
                "eller USB-webbgränssnittet",
            ],
        ),
        "device",
        users,
    )
    d.box(
        12,
        384,
        206,
        70,
        label("Ägaren", ["/rounds med hemlig nyckel", "egen reMarkable-token på servern"]),
        "device",
        users,
    )

    # interfaces, in the order of the users they serve
    x1 = 310
    routes = web_routes()
    h_web = text_height(routes, 330) + 24
    g_web = d.box(
        x1, y0, 350, h_web, label("Webbapp (FastAPI, rmink.web)", routes), "interface", hint="web"
    )
    y = y0 + h_web + GAP
    tools = mcp_tools()
    h_mcp = text_height(tools, 330) + 24
    g_mcp = d.box(
        x1, y, 350, h_mcp, label("MCP-server (rmink.mcp_server)", tools), "interface", hint="mcp"
    )
    y += h_mcp + GAP
    cli = cli_commands()
    h_cli = text_height(cli, 330) + 24
    g_cli = d.box(x1, y, 350, h_cli, label("CLI (rmink.cli, Typer)", cli), "interface", hint="cli")
    y += h_cli + GAP
    note_box(
        d,
        x1,
        y,
        350,
        "Statiska sidor på Vercel",
        [
            "/sketch, /skiss, /sketch/video: demo av skiss → ritning",
            "/video: reklamfilm",
            "index.html, rounds.html, thanks.html",
        ],
        "interface",
    )

    # core
    x2 = 720
    core = d.group(x2, y0, 360, 700, "rmink-kärnan (src/rmink)", "core")
    y = 40
    parts = [
        (
            "api",
            [
                "render, convert: bild/PDF → anteckningsbok",
                "style_previews, inspect, calibration_sheet",
            ],
        ),
        ("ingest · extract · geometry · shade", ["PDF/SVG/bild → linjer, konturer, skuggning"]),
        ("writer/rm_v6 · package/rmdoc · render", [".rm v6, .rmdoc-paket, förhandsbilder"]),
        ("drawing", ["skiss → ritning: fit, workflow, agent, render, store, model, symbols"]),
        (
            "knowledge",
            [
                "9 TOML-filer: termer, ritstandard, symboler,",
                "material, konstruktioner, regler, process",
            ],
        ),
        ("calc", ["säker räknare: vinklar, lutning, U-värde, vikt, antal"]),
        ("cloud · blob_cache", ["rmapi-anrop, tokens, trädcache"]),
        ("devices · options · support", ["enhetsprofiler, inställningar, stödlänk"]),
    ]
    ids = {}
    for name, lines in parts:
        h = text_height(plain_lines(name, lines), 330)
        ids[name] = d.box(14, y, 332, h, label(name, lines), "core", core, hint=name)
        y += h + 10

    # external
    x3 = 1130
    ext = [
        (
            "reMarkable Cloud",
            ["sync 1.5: rotindex + filer per dokument", "nås bara via rmapi"],
            "external",
        ),
        (
            "rmapi (ddvk v0.0.35)",
            ["Go-binär, körs som underprocess", "medföljer på Vercel: bin/rmapi"],
            "external",
        ),
        ("Anthropic API", ["Claude Opus i revisionsrundorna", "ANTHROPIC_API_KEY"], "claude"),
        (
            "Vercel",
            ["Python-funktion app.py, region arn1", "maxDuration 300 s, statiska sidor"],
            "external",
        ),
        ("Vercel Blob", ["privat store rmink-cache", "rmapi-trädcachen, gzip"], "data"),
        ("Upstash Redis (valfri)", ["ritningar på servern i stället för i webbläsaren"], "data"),
        (
            "PyPI + GitHub Actions",
            ["CI: ruff + pytest", "Release: tagg → PyPI → GitHub release"],
            "external",
        ),
        ("Stripe", ["frivilligt stöd, 100 kr", "rmink är gratis"], "external"),
    ]
    y = y0
    eids = {}
    for name, lines, kind in ext:
        h = text_height(plain_lines(name, lines), 280)
        eids[name] = d.box(x3, y, 300, h, label(name, lines), kind, hint=name)
        y += h + GAP

    # storage
    note_box(
        d,
        40,
        y0 + 490,
        230,
        "Var data finns",
        [
            "Webbläsaren (localStorage): reMarkable-token för Send, rundornas ritningar och nyckel",
            "~/.config/rmink: cloud.toml, drawings/*.json, devices.toml",
            "Vercel Blob: trädcachen",
            "Plattan: rmink/<ritning>/ och Tidigare/",
        ],
        "data",
    )

    right, left = (1, 0.5), (0, 0.5)
    d.edge(u_browser, g_web, "HTTPS", exit=right, entry=(0, 0.2))
    d.edge(u_claude, g_mcp, "MCP", exit=right, entry=(0, 0.2))
    d.edge(u_term, g_cli, "kommandon", exit=right, entry=(0, 0.2))
    for g in (g_web, g_mcp, g_cli):
        d.edge(g, core, "", exit=right, entry=left)
    d.edge(
        ids["cloud · blob_cache"],
        eids["rmapi (ddvk v0.0.35)"],
        "underprocess",
        exit=right,
        entry=left,
    )
    d.edge(
        eids["rmapi (ddvk v0.0.35)"],
        eids["reMarkable Cloud"],
        "HTTPS",
        exit=(0.5, 0),
        entry=(0.5, 1),
    )
    d.edge(ids["drawing"], eids["Anthropic API"], "rundor", exit=right, entry=left)
    d.edge(
        ids["cloud · blob_cache"], eids["Vercel Blob"], "cache", dashed=True, exit=right, entry=left
    )
    d.legend(40, y0 + 760, ["interface", "core", "external", "data", "claude", "device"])
    return d


# --- 2. image/PDF to notebook ------------------------------------------------------


def d02_convert() -> Diagram:
    from rmink.devices import all_devices
    from rmink.options import FillMode, Mode, PenChoice, Shading

    d = Diagram(
        "02-bild-till-anteckningsbok",
        "2. Bild eller PDF → redigerbar anteckningsbok",
        "api.render / api.convert, samma kod för CLI, MCP och webben. Resultatet är riktiga pennstreck, inte en bild.",
    )
    steps = [
        (
            "0 Inställningar",
            [
                "options.ConvertOptions",
                f"läge: {', '.join(m.value for m in Mode)}",
                f"fyllning: {', '.join(m.value for m in FillMode)}",
                f"penna: {', '.join(p.value for p in PenChoice)}",
                "färger, bredd, marginal, sidor, punktbudget",
            ],
            "interface",
        ),
        (
            "1 Enhet",
            [
                "devices.get_device",
                "storlek, dpi, färg eller gråskala",
                "egna profiler i devices.toml",
            ],
            "core",
        ),
        (
            "2 Läs in (ingest)",
            [
                "pdf.py: vektor eller raster per sida",
                "svg.py: former, fyllning, streck",
                "image.py: PNG, JPEG, HEIC",
            ],
            "core",
        ),
        ("3 Placera", ["geometry/transform.place", "skala och marginal efter Fit"], "core"),
        (
            "4 Extrahera",
            [
                "vektor: konturer + skraffering, palettfärger, RDP",
                "raster: tröskel, färglager,",
                "tunna delar → centerlinje (skelett)",
                "tjocka delar → kontur + skraffering",
            ],
            "core",
        ),
        (
            "4b Skuggning",
            [
                f"stilar: {', '.join(s.value for s in Shading)}",
                "tonkarta → streck inom punktbudgeten",
            ],
            "core",
        ),
        ("5 Ordning och budget", ["läsordning, max antal punkter, förenkling"], "core"),
        (
            "6 Skriv .rm v6",
            ["writer/rm_v6.write_page", "lager, CRDT-id per streck (rmscene)"],
            "core",
        ),
        ("7 Förhandsbild", ["render/preview.render_rm", "samma streck som plattan visar"], "core"),
        (
            "8 Paketera .rmdoc",
            ["content, metadata, sidor, miniatyrer", "varning nära 100 MB-gränsen för USB"],
            "core",
        ),
        (
            "9 Resultat",
            [
                "ConvertResult: fil, sidor, statistik, varningar",
                "→ nedladdning, USB eller Send to reMarkable",
            ],
            "data",
        ),
    ]
    y = snake(d, 40, 110, 250, 4, steps)
    devs = [
        [
            k,
            p.name,
            f"{p.width}×{p.height}",
            str(p.dpi),
            "färg" if p.color else "gråskala",
            "ja" if p.verified else "nej",
        ]
        for k, p in all_devices().items()
    ]
    table_box(
        d,
        40,
        y + 10,
        "Enhetsprofiler (devices.py)",
        ["nyckel", "namn", "px", "dpi", "färg", "verifierad"],
        devs,
        [50, 190, 90, 40, 70, 70],
    )
    note_box(
        d,
        640,
        y + 10,
        560,
        "Sidvägar",
        [
            "repair: städar ett .rmdoc som macOS packat om (__MACOSX, ._*)",
            "inspect: sidor, lager och streck i en fil",
            "calibrate: mm-linjal och 50 mm-kvadrat för att kontrollera skalan",
            "ingest/rm.read_rmdoc: läser tillbaka streck med lager och CRDT-id (används av skiss → ritning)",
        ],
        "note",
    )
    return d


# --- 3. one round, swimlanes --------------------------------------------------------


def d03_round() -> Diagram:
    d = Diagram(
        "03-skiss-till-ritning",
        "3. Skiss → ritning: ett varv",
        "Från handritad skiss på plattan till renritad revision i samma mapp. Senare varv läser bara det användaren ritat sedan förra revisionen.",
    )
    lanes = ["Platta", "reMarkable Cloud", "rmink", "Claude", "Lagring"]
    kinds = ["device", "external", "core", "claude", "data"]
    lane_h, x0, y0, width = 170, 40, 100, 1950
    lane_ids = []
    for i, (name, kind) in enumerate(zip(lanes, kinds, strict=True)):
        lane_ids.append(d.group(x0, y0 + i * lane_h, width, lane_h - 8, name, kind, hint=name))
    lane = dict(zip(lanes, lane_ids, strict=True))

    def step(lane_name, col, title, lines, kind):
        h = text_height(plain_lines(title, lines), 200)
        return d.box(
            130 + col * 225,
            36,
            205,
            min(max(h, 90), lane_h - 50),
            label(title, lines),
            kind,
            lane[lane_name],
            hint=title,
        )

    s1 = step(
        "Platta",
        0,
        "1 Skissa",
        ["i rmink/ eller rmink/<Mapp>/", "mått, symboler, förklaring"],
        "device",
    )
    s2 = step(
        "reMarkable Cloud", 1, "2 Synk", ["plattan laddar upp", "anteckningsboken"], "external"
    )
    s3 = step(
        "rmink",
        2,
        "3 read_sketch",
        ["cloud.get → read_rmdoc", "fit.analyse: grupper,", "linje, cirkel, båge, märke"],
        "core",
    )
    s4 = step(
        "Claude",
        3,
        "4 Tolka",
        ["bild med numrerade grupper", "+ grupper som JSON", "+ kunskapsbas → Drawing"],
        "claude",
    )
    s5 = step(
        "rmink",
        4,
        "5 rectify + kontroll",
        ["räta väggar (12°), slut hörn", "check_dimensions: skala,", "avvikande mått och vinklar"],
        "core",
    )
    s6 = step(
        "Claude",
        5,
        "6 Granska bilden",
        ["render_preview", "rätta, fråga hellre än gissa"],
        "claude",
    )
    s7 = step(
        "rmink",
        6,
        "7 build_revision",
        ["ren sida, alternativ,", "skissen sist,", "lagret Kommentarer"],
        "core",
    )
    s8 = step(
        "Lagring",
        6,
        "8 Spara ritningen",
        ["Drawing-JSON + written_ids", "webbläsare, Redis eller fil"],
        "data",
    )
    s9 = step(
        "reMarkable Cloud",
        7,
        "9 send_revision",
        ["put i rmink/<namn>/", "läst bok → Tidigare/"],
        "external",
    )
    s10 = step("Platta", 7, "10 Markera", ["ringa, kryssa, skriv", "svar på SVAR-raden"], "device")
    for a, b, t in [
        (s1, s2, ""),
        (s2, s3, "rmapi get"),
        (s3, s4, "grupper"),
        (s4, s5, "Drawing"),
        (s5, s6, "bild + mätning"),
        (s6, s7, "save_revision"),
        (s7, s8, ""),
        (s7, s9, "rmapi put / mv"),
        (s9, s10, "synk"),
    ]:
        d.edge(a, b, t)
    d.edge(s10, s2, "nästa varv: bara nya streck", dashed=True)
    note_box(
        d,
        x0,
        y0 + 5 * lane_h + 10,
        900,
        "Nästa varv",
        [
            "rmink känner igen sina egna streck på deras CRDT-id (sketch.written_ids) och skickar bara användarens nya markeringar till Claude.",
            "Öppna anmärkningar numreras; svar på SVAR-raden eller vid ring N besvarar anmärkning N.",
            'Ändringar loggas som "r3: …" och visas under ÄNDRINGAR. Revisionen heter "<namn> r03 · 2 frågor" så länge frågor är öppna.',
        ],
        "note",
    )
    return d


# --- 4. the round's tool loop ---------------------------------------------------------


def d04_tools() -> Diagram:
    from rmink import calc

    d = Diagram(
        "04-rundans-verktyg",
        "4. Rundans verktygsloop",
        "drawing/agent.run_round: Claude arbetar med rmink:s verktyg tills revisionen är sparad. Samma verktyg finns i MCP-servern för användarens egen Claude.",
    )
    run_lines = [
        "1 namnet: länkad ritning, eller mappens / bokens namn",
        "2 föregående ritning ur lagringen",
        "3 read_sketch (bara nya streck efter första varvet)",
        "4 meddelande: intro, sparad Drawing, överlagsbild, grupper",
        "5 systemprompt + ritreferens + kunskapsreferens (cachad)",
        "6 högst 16 vändor, effort medium",
        "7 RoundResult: plats, revision, sammanfattning, frågor, kostnad",
    ]
    h_run = text_height(plain_lines("run_round", run_lines), 300)
    run = d.box(
        40, 110, 320, h_run, label("run_round(dokument, enhet, lagring)", run_lines), "core"
    )
    claude = d.box(
        420,
        180,
        220,
        120,
        label(
            "Claude (Opus)",
            ["väljer verktyg", "tolkar skiss och markeringar", "frågar hellre än gissar"],
        ),
        "claude",
    )
    d.edge(run, claude, "meddelanden", exit=(1, 0.3), entry=(0, 0.5))
    tools = [
        (
            "render_preview(drawing)",
            [
                "finalize: rectify, namn, revision, datum",
                "bild av ritningen och alternativsidan",
                "+ måttkontroll (check_dimensions)",
                "→ granska: väggar räta, lådor raka, öppningar längs väggen",
            ],
        ),
        (
            "measure(ids)",
            ["längd, area, hörnvinklar ur geometrin", "i mm via skalan från skrivna mått"],
        ),
        ("calculate(uttryck)", [", ".join(sorted(calc.FUNCTIONS))]),
        (
            "lookup_knowledge(fråga, sort)",
            [
                "material, konstruktion, variant, regel,",
                "åtgärd, symbol, term, ritningstyp, roll, skraffering",
            ],
        ),
        (
            "save_revision(drawing, sammanfattning)",
            ["en gång per varv", "build_revision → send_revision"],
        ),
    ]
    y = 100
    for name, lines in tools:
        h = text_height(plain_lines(name, lines), 380)
        t = d.box(720, y, 400, h, label(name, lines), "core", hint=name)
        d.edge(claude, t, "", exit=(1, 0.5), entry=(0, 0.5))
        y += h + GAP
    y_notes = max(110 + h_run, 300) + 30
    y_notes = note_box(
        d,
        40,
        y_notes,
        600,
        "Regler i prompten",
        [
            "Räta vinklar: väggar möts i 90° om ingen skriven vinkel säger annat; lutning under 12° kräver ett vinkelmått.",
            "Tal räknas aldrig i huvudet: measure och calculate.",
            "Regler citeras först efter lookup_knowledge; högst några per varv, viktigast först.",
            "Enhet skrivs med varje tal i anmärkningar och texter.",
            'Alternativ ("alternativ?", "hur tjock?"): 2–4 lösningar på en egen sida, val med bokstav på SVAR-raden.',
        ],
        "note",
    )
    note_box(
        d,
        40,
        y_notes + GAP,
        600,
        "Samma flöde via MCP",
        [
            "read_sketch → drawing_reference → lookup_knowledge / calculate / measure_drawing → render_drawing_preview → save_revision(send=True)",
            "Tolkningen sker i användarens egen Claude, så rmink förblir gratis.",
        ],
        "interface",
    )
    return d


# --- 5. revisions and folders --------------------------------------------------------


def d05_folders() -> Diagram:
    d = Diagram(
        "05-revisioner-och-mappar",
        "5. Revisioner, mappar och namn på plattan",
        "workflow.send_revision ordnar ritningarna som en bygghandlingsmapp: senaste revisionen överst, äldre i Tidigare/.",
    )
    tree = [
        (0, "rmink/", "", "external"),
        (1, "Garage", "ny skiss, väntar på första varvet", "device"),
        (1, "Bastu/", "mapp som användaren gjort", "external"),
        (2, "Bastuskiss", "skiss i egen mapp → ritningen heter Bastu", "device"),
        (1, "Altan/", "ritningens mapp", "external"),
        (2, "Altan r03 · 2 frågor", "revisionen att markera", "core"),
        (2, "Tidigare/", "äldre revisioner, äldst först", "external"),
        (3, "Altan r00 skiss", "originalskissen", "device"),
        (3, "Altan r01 · 1 fråga", "", "core"),
        (3, "Altan r02", "", "core"),
    ]
    y = 110
    for depth, name, comment, kind in tree:
        d.box(40 + depth * 28, y, 230, 26, esc(name), kind, valign="middle")
        if comment:
            d.text(370, y + 4, 260, 22, esc(comment), size=10, color="#333333")
        y += 32
    chain = [
        ("r00 skiss", ["handritad", "i rmink/ eller rmink/<Mapp>/"], "device"),
        (
            "r01 · 2 frågor",
            ["ren ritning", "ringar 1, 2 + ANMÄRKNINGAR", "SVAR-rad per fråga"],
            "core",
        ),
        (
            "markeringar",
            ["ringar, kryss, text", "svar på SVAR-raden", "i lagret Kommentarer"],
            "device",
        ),
        ("r02", ["svaren inarbetade", "frågor stängda", "r01 → Tidigare/"], "core"),
    ]
    prev = None
    for i, (t, lines, kind) in enumerate(chain):
        cid = d.box(680 + i * 230, 110, 200, 110, label(t, lines), kind, hint=t)
        if prev:
            d.edge(prev, cid, "varv" if i % 2 else "")
        prev = cid
    rows = [
        ["Namn på revision", '"<namn> r<NN>" + " · N frågor" när frågor är öppna'],
        ["Två siffror", "r03 sorterar rätt även efter r09"],
        [
            "Ritningens namn",
            "länkad ritning; annars mappen i rmink/<Mapp>/; annars bokens namn utan rNN och · frågor",
        ],
        ["Skissen", 'flyttas till Tidigare/ som "<namn> r00 skiss" (bara inom rmink/)'],
        ["Krock", 'rmapi döper om till "namn_2", "namn_3" …'],
        ["Egna böcker", "böcker utanför rmink/ flyttas aldrig"],
        ["Tecken", "/ * ? [ ] \\ byts mot - (rmapi tolkar dem som mönster)"],
        ["Lager", '"Ritning rNN" med rmink:s streck + tomt "Kommentarer" för användaren'],
        ["Sidor", "1 ren ritning · 2 alternativ (om några) · 3 skissen"],
    ]
    table_box(d, 680, 260, "Regler för namn och flytt", ["", ""], rows, [140, 560], "core")
    return d


# --- 6. cloud, cache and limits --------------------------------------------------------


def d06_cloud() -> Diagram:
    from rmink import cloud

    d = Diagram(
        "06-moln-cache-och-granser",
        "6. reMarkable Cloud, cache och gränser",
        "reMarkable Cloud har ingen fråga per mapp: rotindexet listar alla dokument och mappen står i varje dokuments metadata. Därför cachen.",
    )
    call = d.box(
        40,
        110,
        250,
        90,
        label("cloud.ls / get / put / mkdir / mv", ["varje anrop kör rmapi en gång"]),
        "core",
    )
    owner = d.box(
        360,
        110,
        240,
        90,
        label("Ägarens token?", ["= RMINK_CLOUD_TOKEN", "eller sparad cloud.toml"]),
        "core",
        extra="shape=rhombus;",
        align="center",
        valign="middle",
    )
    temp = d.box(
        360,
        260,
        240,
        100,
        label(
            "Tillfälligt hem",
            ["andras tokens (Send to reMarkable)", "ny tom katalog per anrop", "raderas efteråt"],
        ),
        "data",
    )
    last = d.box(
        680,
        110,
        300,
        150,
        label(
            "Bestående cache",
            [
                "$TMP/rmink-rmapi-cache-<hash>",
                "rmapi/tree.cache (≈3,6 MB)",
                "rmapi.conf med användartoken",
                "fcntl-lås: ett anrop i taget",
            ],
        ),
        "data",
    )
    blob = d.box(
        1060,
        110,
        280,
        150,
        label(
            "Vercel Blob",
            [
                "privat: rmink/rmapi-tree-<hash>.json.gz (≈0,8 MB)",
                "hämtas när instansen saknar cache",
                "laddas upp bara om den ändrats",
            ],
        ),
        "data",
    )
    d.edge(call, owner)
    d.edge(owner, temp, "nej")
    d.edge(owner, last, "ja")
    d.edge(last, blob, "restore / save", dashed=True)
    cold = [
        [
            "kall (ingen tree.cache)",
            cloud._COLD_CONCURRENT,
            f"{cloud._COLD_TIMEOUT_S} s",
            "≈2 900 anrop för ≈1 000 böcker, en gång",
        ],
        ["varm", "2", f"{cloud._TIMEOUT_S} s", "1 anrop (rotens hash) + det som ändrats"],
    ]
    table_box(
        d,
        40,
        400,
        "rmapi-körning",
        ["läge", "samtidiga", "tidsgräns", "kostnad"],
        cold,
        [170, 70, 70, 290],
        "core",
    )
    limits = [
        ["POST /token/json/2/user/new", "5", "ny användartoken"],
        ["GET /sync/v4/root", "30", "rotens hash; här kom 429 2026-10-28"],
        ["GET /sync/v3/files/<hash>", "48 000", "ett per index och metadata"],
    ]
    table_box(
        d,
        700,
        400,
        "Uppmätta gränser (X-Ratelimit-Limit, 2026-10-29)",
        ["endpoint", "gräns", "används till"],
        limits,
        [210, 60, 260],
        "external",
        sub="Reset 1–12, troligen sekunder; fönstren är inte dokumenterade",
    )
    note_box(
        d,
        40,
        560,
        600,
        "Skydd",
        [
            "/rounds når bara /rmink och det som ligger där: andra sökvägar och .. ger 403 innan rmapi körs.",
            '429 ger "wait a few minutes and try again" i stället för rmapis interna fel.',
            "Tokens maskeras i felmeddelanden och loggar.",
            "Upptäckten: varje rmapi-körning började tidigare med tom cache; en runda gjorde 4–5 sådana.",
        ],
        "note",
    )
    note_box(
        d,
        700,
        560,
        560,
        "Sync 1.5 i korthet",
        [
            "1 GET root → hash för rotindexet",
            "2 rotindexet: id + hash för alla dokument och mappar (platt lista)",
            "3 per dokument: dess index → .metadata (namn, förälder), .content, sidor",
            "Skrivning: nya filer + nytt rotindex + ny root (samma för put, mkdir och mv)",
        ],
        "external",
    )
    return d


# --- 7. release and deploy ----------------------------------------------------------


def d07_release() -> Diagram:
    d = Diagram(
        "07-release-och-drift",
        "7. Release och drift",
        "Sajten kör alltid en släppt version från PyPI; en push till main ändrar inte sajten förrän requirements.txt höjs.",
    )
    steps = [
        (
            "Ändring på main",
            [
                "git push origin rmink:main",
                "CI: ruff + pytest",
                "ubuntu, macos, windows × 3.11, 3.13",
            ],
            "core",
        ),
        ("Version + CHANGELOG", ["pyproject.toml version", "CHANGELOG.md"], "core"),
        ("Tagg vX.Y.Z", ["git tag -a, git push origin vX.Y.Z"], "core"),
        (
            "Release-arbetsflöde",
            ["tagg = version?", "bygg, twine check", "röktest: devices, convert, inspect"],
            "external",
        ),
        ("Godkännande", ["miljön pypi", "ägaren godkänner i GitHub Actions"], "device"),
        ("PyPI", ["Trusted Publishing", "+ GitHub release"], "external"),
        (
            "Vänta ≈3 min",
            ["PyPI:s simple index släpar", "annars hittar Vercel inte versionen"],
            "note",
        ),
        ("Höj deploy", ["deploy/vercel/requirements.txt", "rmink[web,rounds]==X.Y.Z"], "core"),
        (
            "Vercel-bygge",
            ["app.py + bin/rmapi + public/", "region arn1", "vid fel: vercel redeploy"],
            "external",
        ),
        ("Live", ["rmink.vercel.app", "/rounds, /sketch, /video"], "interface"),
    ]
    y = snake(d, 40, 110, 230, 5, steps, gap_x=30)
    note_box(
        d,
        40,
        y,
        760,
        "Miljövariabler på Vercel",
        [
            "RMINK_ROUNDS_SECRET + ANTHROPIC_API_KEY: slår på /rounds",
            "RMINK_CLOUD_TOKEN: ägarens reMarkable-token",
            "BLOB_READ_WRITE_TOKEN: trädcachen i Blob (store rmink-cache)",
            "RMINK_ROUND_EFFORT, RMINK_SUPPORT_URL, RMINK_SOURCE_URL, RMINK_DEMO_URL, RMINK_MAX_*",
            "UPSTASH_REDIS_REST_URL/TOKEN (valfritt): ritningar på servern",
        ],
        "data",
    )
    return d


# --- 8. the Drawing model ------------------------------------------------------------


def _type(ann) -> str:
    import typing

    origin, args = typing.get_origin(ann), typing.get_args(ann)
    if origin is typing.Literal:
        return " | ".join(str(a) for a in args)
    if origin in (list, tuple, dict) and args:
        return f"{origin.__name__}[{', '.join(_type(a) for a in args)}]"
    if args and str(origin) in ("typing.Union", "<class 'types.UnionType'>"):
        return " | ".join(_type(a) for a in args)
    return getattr(ann, "__name__", str(ann)).replace("typing.", "")


def _fields(model) -> list[str]:
    return [f"{name}: {short(_type(f.annotation), 60)}" for name, f in model.model_fields.items()]


def d08_model() -> Diagram:
    from rmink.drawing import model as m

    d = Diagram(
        "08-ritningsmodellen",
        "8. Ritningsmodellen (rmink.drawing.model)",
        "Det Claude bygger och rmink ritar. Fälten läses ur pydantic-modellerna när diagrammet byggs.",
    )
    ids, bottom = {}, {}

    def cls(name, x, y, w=400):
        f = _fields(getattr(m, name))
        h = text_height(f, w - 20) + 26
        ids[name] = d.box(
            x, y, w, h, label(name, f), "core", hint=name, extra="fontFamily=Courier New;"
        )
        bottom[name] = y + h
        return y + h + 24

    y = cls("Drawing", 80, 110)
    for name in ("LegendEntry", "SketchRef", "Category"):
        y = cls(name, 80, y + 20)
    y2 = 110
    for name in ("Element", "Dimension", "AngleDimension", "Symbol", "Annotation", "Alternatives"):
        y2 = cls(name, 560, y2)
    y3 = cls("Option", 1080, bottom["Alternatives"] - 160)
    cls("OptionLayer", 1080, y3)
    right, left = (1, 0.5), (0, 0.5)
    parts = [
        ("Element", "elements *"),
        ("Dimension", "dimensions *"),
        ("AngleDimension", "angles *"),
        ("Symbol", "symbols *"),
        ("Annotation", "annotations *"),
        ("Alternatives", "alternatives *"),
    ]
    for i, (name, t) in enumerate(parts):
        d.edge(ids["Drawing"], ids[name], t, exit=(1, 0.15 + 0.13 * i), entry=left)
    for i, (name, t) in enumerate(
        (("LegendEntry", "legend *"), ("SketchRef", "sketch"), ("Category", "categories *"))
    ):
        d.edge(ids["Drawing"], ids[name], t, exit=(0, 0.6 + 0.12 * i), entry=left)
    d.edge(ids["Alternatives"], ids["Option"], "options *", exit=right, entry=left)
    d.edge(ids["Option"], ids["OptionLayer"], "layers *", exit=(0.5, 1), entry=(0.5, 0))
    y = max(bottom.values()) + 40
    cats = [
        [c.name, c.label, c.color, c.mono_color, c.line_type, c.mono_line_type or "–", sv(c.width)]
        for c in m.DEFAULT_CATEGORIES
    ]
    table_box(
        d,
        40,
        y,
        "DEFAULT_CATEGORIES: hur varje sorts linje ritas",
        ["namn", "etikett", "färg", "gråskala", "linjetyp", "gråskala-typ", "bredd px"],
        cats,
        [80, 100, 70, 70, 70, 90, 60],
        "core",
    )
    note_box(
        d,
        700,
        y,
        600,
        "Ritningshuvudet (render._title_block)",
        [
            'NAMN · REV n · skede · datum · "Mått i mm"',
            "FÖRKLARINGAR: symboler och kategorier som används, två spalter",
            "ANMÄRKNINGAR: öppna frågor numrerade, var och en med en SVAR-rad",
            "ÄNDRINGAR: de sex senaste raderna i log",
            "Saknas ännu: skala, ritningsnummer och övriga fält i ritstandardens ritningshuvud",
        ],
        "note",
    )
    return d


# --- knowledge base ---------------------------------------------------------------

SOURCE_KIND = {"rmink": "rmink", "praxis": "practice"}


def source_kind(source: str) -> str:
    return SOURCE_KIND.get(source, "law")


def rule_tags(ids: list[str]) -> str:
    return ", ".join(ids) if ids else "–"


# --- 9. structure of the knowledge base ---------------------------------------------


def d09_structure() -> Diagram:
    from rmink import knowledge

    k = kb()
    d = Diagram(
        "09-kunskapsbasens-struktur",
        "9. Kunskapsbasens struktur (src/rmink/knowledge/data/*.toml)",
        f"Nio TOML-filer, version {k['terms'].get('version', '')}. Pilarna är korsreferenser som testas i tests/test_knowledge_data.py.",
    )

    def fields(f: str) -> list[str]:
        out = []
        for t, v in k[f].items():
            if t == "version":
                continue
            if isinstance(v, list) and v and isinstance(v[0], dict):
                keys = list(dict.fromkeys(key for item in v for key in item))
                out.append(f"[{t}] × {len(v)}")
                out.append("   " + ", ".join(keys))
            elif isinstance(v, dict):
                out.append(f"[{t}]: {', '.join(v)}")
        return out

    W = 470
    pos = {
        "terms": (40, 110),
        "drawing_standard": (40, 560),
        "symbols": (580, 110),
        "rules": (580, 400),
        "process": (580, 760),
        "markup": (580, 1020),
        "materials": (1120, 110),
        "assemblies": (1120, 400),
        "hatches": (1700, 110),
    }
    ids = {}
    for f, (x, y) in pos.items():
        lines = fields(f)
        h = text_height([f] + lines, W - 10) + 6
        ids[f] = d.box(x, y, W, h, label(f"{f}.toml", lines), "data", hint=f, size=10)
    refs = [
        ("materials", "rules", "material.rules", (0, 0.7), (1, 0.15)),
        ("assemblies", "rules", "assembly.rules", (0, 0.5), (1, 0.5)),
        ("assemblies", "materials", "layers[].material", (0.5, 0), (0.5, 1)),
        ("materials", "hatches", "material.hatch", (1, 0.3), (0, 0.3)),
        ("symbols", "rules", "symbol.rules", (0.5, 1), (0.5, 0)),
        ("process", "rules", "action.rules", (0.5, 0), (0.5, 1)),
        ("markup", "rules", "csv: Rule, Material", (1, 0.3), (1, 0.85)),
        ("terms", "rules", "term.ref (även material, konstruktion, process)", (1, 0.8), (0, 0.3)),
        ("terms", "drawing_standard", "term.ref", (0.5, 1), (0.5, 0)),
        ("symbols", "drawing_standard", "drawing_types", (0, 0.85), (1, 0.1)),
        ("rules", "drawing_standard", "applies_to: ritningstyp", (0, 0.7), (1, 0.4)),
    ]
    for a_, b_, t, ex, en in refs:
        d.edge(ids[a_], ids[b_], t, color="#888888", exit=ex, entry=en)
    kinds = [[k_, f"{f}.{t}"] for k_, (f, t) in knowledge.KINDS.items()]
    table_box(
        d,
        1700,
        400,
        "lookup_knowledge: sorter i sökordning",
        ["sort", "fil.tabell"],
        kinds,
        [110, 200],
        "core",
    )
    note_box(
        d,
        1120,
        760,
        760,
        "Så används kunskapsbasen",
        [
            "reference(): en kompakt sammanfattning (≈17 000 tecken) i rundans och MCP:s systemprompt.",
            "lookup(fråga, sort): hela poster vid behov; träff i namn, förkortning, synonymer och klasser väger tyngst.",
            "Poster byggs ut: regler blir korta sammanfattningar, material får sin skraffering, konstruktioner sina varianter.",
            "variant_facts(): tjocklek, vikt per m² och uppskattat U-värde räknas ur skikten.",
            "calc: densitet och λ hämtas ur materials.toml för weight() och u_value().",
        ],
        "note",
    )
    return d


# --- 10. laws and rules -----------------------------------------------------------


def d10_rules() -> Diagram:
    k = kb()
    rules = k["rules"]["rule"]
    d = Diagram(
        "10-lagar-och-regler",
        "10. Lagar, föreskrifter och granskningsregler",
        "BBR och EKS ersattes 2025-07-01 av BFS 2024:4–13 (övergången slutade 2026-07-01). "
        "fel = strider mot krav · fråga = något att ta ställning till · info = upplysning.",
    )
    # hierarchy
    src = {s["id"]: s for s in k["process"]["source"]}
    top = []
    for sid in ("pbl", "pbf", "elsl", "elsak_fs_2017_2"):
        s = src.get(sid)
        if s:
            lines = [
                f"konsoliderad t.o.m. {s['consolidated_to']}" if s.get("consolidated_to") else "",
                s.get("note", ""),
            ]
            top.append((s["name"], [x for x in lines if x]))
    y = 110
    x = 40
    tids = []
    for name, lines in top:
        h = max(80, text_height(plain_lines(name, lines), 250))
        tids.append(d.box(x, y, 260, h, label(name, lines), "law", hint=name))
        x += 275
    d.legend(x, 110, ["law", "practice", "rmink"], "Källa")
    req = [
        [str(r["n"]), r["name"], r.get("bfs") or "–"] for r in k["process"]["technical_requirement"]
    ]
    tr, y_req = table_box(
        d,
        x + 260,
        110,
        "PBL 8 kap. 4 §: tekniska egenskapskrav → Boverkets föreskrifter",
        ["", "krav", "föreskrift"],
        req,
        [20, 300, 140],
        "law",
    )
    d.edge(tids[0], tr, "8 kap. 4 §", exit=(0.5, 1), entry=(0.5, 1), points=[(170, y_req + 14)])

    order = [
        "rmink",
        "BFS 2024:9",
        "BFS 2024:12",
        "BFS 2024:13",
        "BFS 2024:8",
        "BFS 2024:7",
        "PBL",
        "PBF",
        "ElSL",
        "praxis",
    ]
    sources = order + sorted({r["source"] for r in rules} - set(order))
    widths = [150, 120, 190, 55, 40, 330]
    blocks = []
    for s in sources:
        rs = [r for r in rules if r["source"] == s]
        if not rs:
            continue
        rows = [
            [
                r["id"],
                r.get("ref", ""),
                r["title"],
                r["severity"],
                "ja" if r.get("verified") else "nej",
                short(r.get("message_sv", ""), 150),
            ]
            for r in rs
        ]

        def make(x, y, s=s, rows=rows):
            return table_box(
                d,
                x,
                y,
                f"{s} ({len(rows)} regler)",
                ["id", "lagrum", "regel", "grad", "verif.", "meddelande"],
                rows,
                widths,
                source_kind(s),
                hint=s,
            )[1]

        blocks.append(make)
    y_rules = max(y_req, 300) + 50
    columns(d, 40, y_rules, sum(widths) + 16, 2, blocks)
    return d


# --- 11. permits and process ---------------------------------------------------------


def d11_process() -> Diagram:
    k = kb()["process"]
    d = Diagram(
        "11-lov-och-process",
        "11. Lov, anmälan och byggprocessen för småhus",
        "Vilken prövning en åtgärd kräver, i vilken ordning det sker och vem som ansvarar. Källor: PBL, PBF, ElSL (process.toml).",
    )
    permits = {p["id"]: p for p in k["permit"]}
    y = 110
    pid = {}
    for p in k["permit"]:
        lines = [p.get("ref", ""), short(p.get("meaning", ""), 160)]
        h = text_height(plain_lines(p["name"], lines), 240)
        pid[p["id"]] = d.box(1580, y, 260, h, label(p["name"], lines), "law", hint=p["id"])
        y += h + 10
    roles = {r["id"]: r for r in k["role"]}
    rows = []
    for a in k["action"]:

        def name(x):
            return permits.get(x, roles.get(x, {"name": x}))["name"]

        rows.append(
            [
                a["name"],
                name(a["default"]),
                short(a.get("exempt_if", "") or "–", 170),
                name(a["then"]),
                short(a.get("unless", "") or "–", 120),
                rule_tags(a.get("rules", [])),
            ]
        )
    _, y_act = table_box(
        d,
        40,
        110,
        "Åtgärder → prövning",
        ["åtgärd", "normalt", "undantag om", "då", "utom om", "regler"],
        rows,
        [170, 90, 330, 80, 230, 170],
        "law",
    )
    steps = [
        (
            f"{s['order']} {s['name']}",
            [s.get("ref", "")]
            + [f"• {n}" for n in s.get("needs", [])][:5]
            + ([f"rmink: {s['rmink']}"] if s.get("rmink") else []),
            "core",
        )
        for s in sorted(k["step"], key=lambda s: s["order"])
    ]
    ys = snake(d, 40, y_act + 40, 280, 5, steps, gap_x=24)
    rrows = [
        [r["name"], r.get("abbr", ""), r.get("ref", ""), short(r.get("duty", ""), 200)]
        for r in k["role"]
    ]
    _, y2 = table_box(
        d,
        40,
        ys + 10,
        "Roller",
        ["roll", "", "lagrum", "ansvar"],
        rrows,
        [170, 40, 200, 520],
        "data",
    )
    docs = [
        [
            x["name"],
            x.get("ref", ""),
            "; ".join(x.get("contains", [])) or short(x.get("note", ""), 200),
        ]
        for x in k.get("document", [])
    ]
    table_box(
        d, 1000, ys + 10, "Dokument", ["", "lagrum", "innehåll"], docs, [130, 140, 360], "data"
    )
    return d


# --- 12. drawing standard -----------------------------------------------------------


def d12_standard() -> Diagram:
    k = kb()["drawing_standard"]
    from rmink.drawing.model import DEFAULT_CATEGORIES

    cats = {c.name: c.label for c in DEFAULT_CATEGORIES}
    d = Diagram(
        "12-ritstandard",
        "12. Ritstandard (drawing_standard.toml)",
        "I rmink:s egna ord efter Bygghandlingar 90 och SS-EN ISO 128 (linjer), 129 (mått), 5455 (skalor), 7200 (ritningshuvud), 7519 och 4157 (beteckningar).",
    )
    blocks = []
    types = [
        [
            t["name"],
            ", ".join(t["scales"]),
            short(t.get("shows", ""), 140),
            ", ".join(t.get("required", [])) or "–",
            "ja" if t.get("smallhouse") else "nej",
        ]
        for t in k["drawing_type"]
    ]
    blocks.append(
        lambda x, y: table_box(
            d,
            x,
            y,
            "Ritningstyper",
            ["typ", "skalor", "visar", "måste ha", "småhus"],
            types,
            [130, 110, 260, 200, 50],
            "data",
        )[1]
    )
    phases = [[str(p["order"]), p["name"], short(p.get("meaning", ""), 120)] for p in k["phase"]]
    pm = "; ".join(
        f"{a} → {b}" for a, b in k.get("phase_mapping", {}).items() if isinstance(b, str)
    )
    blocks.append(
        lambda x, y: table_box(
            d,
            x,
            y,
            "Skeden",
            ["", "skede", "innebär"],
            phases,
            [20, 160, 400],
            "data",
            sub=f"rmink: {pm}" if pm else "",
        )[1]
    )
    tb = [
        [f["name"], "ja" if f.get("required") else "nej", f.get("example", "")]
        for f in k["title_block_field"]
    ]
    blocks.append(
        lambda x, y: table_box(
            d,
            x,
            y,
            "Ritningshuvud",
            ["fält", "krav", "exempel"],
            tb,
            [200, 40, 300],
            "data",
            sub=f"Numrering {k['numbering']['pattern']}: {k['numbering']['example']}",
        )[1]
    )
    disc = [[x["letter"], x["name"]] for x in k["discipline"]]
    blocks.append(
        lambda x, y: table_box(d, x, y, "Discipliner", ["", ""], disc, [30, 250], "data")[1]
    )
    lines = [
        [
            ln["id"],
            ln["use"],
            ln["type"],
            ln["weight"],
            "–".join(sv(w) for w in ln["width_mm"]),
            f"{ln['rmink_category']} ({cats.get(ln['rmink_category'], '?')})",
        ]
        for ln in k["line"]
    ]
    blocks.append(
        lambda x, y: table_box(
            d,
            x,
            y,
            "Linjetyper → rmink-kategori",
            ["id", "används till", "typ", "vikt", "mm", "kategori"],
            lines,
            [90, 240, 60, 50, 60, 150],
            "data",
        )[1]
    )
    des = [[x["id"], x.get("pattern", ""), x.get("example", "")] for x in k["designation"]]
    blocks.append(
        lambda x, y: table_box(
            d, x, y, "Beteckningar", ["", "mönster", "exempel"], des, [110, 280, 150], "data"
        )[1]
    )
    dim = [[str(i + 1), r] for i, r in enumerate(k["dimensioning"]["rules"])]
    blocks.append(
        lambda x, y: table_box(
            d,
            x,
            y,
            f"Måttsättning (enhet {k['dimensioning']['unit']})",
            ["", "regel"],
            dim,
            [20, 600],
            "data",
        )[1]
    )
    sheet = k["sheet"]
    sh = [
        [n, f"{v[0]}×{v[1]} mm"]
        for n, v in sheet.items()
        if isinstance(v, list) and len(v) == 2 and n.startswith("A")
    ]
    blocks.append(
        lambda x, y: table_box(
            d,
            x,
            y,
            "Pappersformat",
            ["", ""],
            sh,
            [40, 120],
            "data",
            sub=f"texthöjder {', '.join(sv(t) for t in sheet['text_height_mm'])} mm",
        )[1]
    )
    rev = k["revision"]
    blocks.append(
        lambda x, y: note_box(
            d,
            x,
            y,
            620,
            "Revisioner",
            [
                rev["designation"],
                rev["cloud"],
                rev["triangle"],
                "Tabell: " + ", ".join(rev["table"]),
                "rmink: " + rev["rmink_mapping"],
            ],
            "data",
        )
    )
    blocks.append(
        lambda x, y: note_box(
            d,
            x,
            y,
            620,
            "Skalor",
            [", ".join(k["scales"]["preferred"]), k["scales"]["note"]],
            "data",
        )
    )
    blocks.append(
        lambda x, y: note_box(
            d,
            x,
            y,
            620,
            "Vad rmink ritar i dag",
            [
                'Har: namn, REV, skede, datum, "Mått i mm", förklaringar, anmärkningar med SVAR, ändringar, kategorier med linjetyp.',
                "Saknas: skala, ritningsnummer, projekt, fastighet, upprättad/granskad, ritningstyp i modellen.",
            ],
            "note",
        )
    )
    columns(d, 40, 110, 820, 2, blocks)
    return d


# --- 13. materials -----------------------------------------------------------------


def d13_materials() -> Diagram:
    k = kb()["materials"]
    d = Diagram(
        "13-material",
        f"13. Material ({len(k['material'])} st i {len(k['group'])} grupper)",
        "Klasser och vad ritningen måste ange, brandklass, densitet ρ (kg/m³), värmeledning λ (W/mK), skraffering och regler. Används för texter, vikt, U-värde och granskning.",
    )
    widths = [150, 190, 150, 70, 40, 45, 80, 170]
    blocks = []
    for g in k["group"]:
        ms = [m for m in k["material"] if m["group"] == g["id"]]
        rows = [
            [
                m["name"],
                ", ".join(m.get("classes", [])),
                ", ".join(m.get("required", [])) or "–",
                m.get("fire_class", "–") or "–",
                sv(m["density"]) if m.get("density") else "–",
                sv(m["lambda"]) if m.get("lambda") else "–",
                m.get("hatch", "–"),
                rule_tags(m.get("rules", [])),
            ]
            for m in ms
        ]

        def make(x, y, g=g, rows=rows, ms=ms):
            return table_box(
                d,
                x,
                y,
                f"{g['name']} ({len(rows)})",
                ["material", "klasser", "måste anges", "brand", "ρ", "λ", "skraffering", "regler"],
                rows,
                widths,
                "data",
                sub=f"id: {', '.join(m['id'] for m in ms)}",
                hint=g["id"],
            )[1]

        blocks.append(make)
    columns(d, 40, 110, sum(widths) + 16, 2, blocks)
    return d


# --- 14. assemblies as sections --------------------------------------------------------


def layer_stack_svg(layers: list[dict], max_w=150.0, max_h=320.0) -> tuple[str, float, float]:
    """A section through the layers, drawn with rmink's own hatches; returns
    (svg, width, height) in diagram px."""
    import numpy as np

    from rmink.drawing.render import _hatch, _material_hatch

    width = 100.0
    total = sum(max(lay["thickness_mm"], 0) for lay in layers) or 1
    scale = min(0.5, 600 / total)
    y = 0.0
    paths = []
    for lay in layers:
        t = lay["thickness_mm"]
        h = max(t * scale, 3 if t == 0 else 6)
        box = (0.0, y, width, y + h)
        paths.append(np.array([[0, y], [width, y], [width, y + h], [0, y + h], [0, y]], float))
        pattern, angle = _material_hatch(lay["material"])
        paths += _hatch(box, pattern, angle, 6.0)
        y += h
    return svg_fit(paths, (-1, -1, width + 1, y + 1), max_w, max_h, stroke=0.8)


def d14_assemblies() -> Diagram:
    k = kb()
    mats = {m["id"]: m for m in k["materials"]["material"]}
    d = Diagram(
        "14-konstruktioner",
        f"14. Konstruktioner ({len(k['assemblies']['assembly'])} byggdelar)",
        "Skikt utifrån och in (väggar) eller uppifrån och ner (bjälklag, tak, grund), ritade med rmink:s skrafferingar. 0 mm = folie eller ospecificerad tjocklek.",
    )
    blocks = []
    for a in k["assemblies"]["assembly"]:
        rows = [
            [
                mats[lay["material"]]["name"],
                sv(lay["thickness_mm"]) if lay["thickness_mm"] else "–",
                lay.get("note", ""),
            ]
            for lay in a["layers"]
        ]
        lines_req = [f"krav: {r}" for r in a.get("requirements", [])] + [
            f"granska: {r}" for r in a.get("review_points", [])
        ]

        def make(x, y, a=a, rows=rows, lines_req=lines_req):
            svg, w_img, h_img = layer_stack_svg(a["layers"], 160, 340)
            gid = d.group(x, y, 900, 10, f"{a['code']} {a['name']}", "data", hint=a["id"])
            t = a.get("typical_thickness_mm")
            info = [
                f"id {a['id']}",
                f"typisk tjocklek {sv(t)} mm" if t else "",
                f"används i {', '.join(a.get('used_in', []))}",
                f"regler: {rule_tags(a.get('rules', []))}",
            ]
            d.image(10 + (160 - w_img) / 2, 36, w_img, h_img, svg, gid)
            _, yb = table_box(
                d,
                190,
                36,
                "Skikt",
                ["material", "mm", "not"],
                rows,
                [200, 40, 420],
                "plain",
                parent=gid,
                hint=a["id"] + "_t",
            )
            yb = note_box(
                d, 190, yb + 8, 690, "", [x for x in info if x] + lines_req, "note", parent=gid
            )
            h = max(yb, 36 + h_img) + 14
            d.cells[[c.id for c in d.cells].index(gid)].geometry = (x, y, 900, h)
            d._abs[gid] = (x, y, 900, h)
            return y + h

        blocks.append(make)
    columns(d, 40, 110, 900, 2, blocks)
    return d


# --- 15. product alternatives ---------------------------------------------------------


def d15_variants() -> Diagram:
    from rmink import knowledge

    k = kb()
    assemblies = {a["id"]: a for a in k["assemblies"]["assembly"]}
    d = Diagram(
        "15-produktalternativ",
        f"15. Produktalternativ ({len(k['assemblies']['variant'])} varianter)",
        'Svar på "alternativ?" eller "hur tjock?": rundan lägger 2–4 lösningar på en egen sida; användaren skriver bokstaven på SVAR-raden. '
        "Tjocklek, vikt och U-värde räknas med variant_facts (λ-värdesmetoden, utan köldbryggor).",
    )
    mats = {m["id"]: m for m in k["materials"]["material"]}
    y = 110
    for aid in dict.fromkeys(v["assembly"] for v in k["assemblies"]["variant"]):
        a = assemblies[aid]
        vs = knowledge.variants(aid)
        gid = d.group(40, y, 60 + 380 * len(vs), 10, f"{a['code']} {a['name']}", "data", hint=aid)
        hmax = 0.0
        for i, v in enumerate(vs):
            f = knowledge.variant_facts(v)
            svg, w_img, h_img = layer_stack_svg(v["layers"], 120, 240)
            x = 20 + i * 380
            d.box(
                x,
                36,
                360,
                30,
                f"<b>{esc(v['key'])}  {esc(v['name'])}</b>",
                "core",
                gid,
                valign="middle",
            )
            d.image(x + (120 - w_img) / 2, 74, w_img, h_img, svg, gid)
            facts = [f"tjocklek ≈ {sv(f['thickness_mm'])} mm", f"vikt ≈ {f['weight_kg_m2']} kg/m²"]
            if "u_estimate" in f:
                facts.append(f"U ≈ {sv(f['u_estimate'])} W/m²K")
            facts.append(f"kostnad: {v.get('cost', '–')}")
            lines = (
                facts
                + [f"när: {v.get('when', '')}"]
                + [f"+ {p}" for p in v.get("pros", [])]
                + [f"− {c}" for c in v.get("cons", [])]
            )
            lines += [
                f"skikt: {', '.join(mats[lay['material']]['name'].split(' (')[0] + (' ' + sv(lay['thickness_mm']) if lay['thickness_mm'] else '') for lay in v['layers'])}"
            ]
            yb = note_box(d, x + 130, 74, 230, "", lines, "plain", parent=gid)
            hmax = max(hmax, yb, 74 + h_img)
        h = hmax + 16
        d.cells[[c.id for c in d.cells].index(gid)].geometry = (40, y, 60 + 380 * len(vs), h)
        d._abs[gid] = (40, y, 60 + 380 * len(vs), h)
        y += h + 30
    note_box(
        d,
        40,
        y,
        900,
        "Från val till ritning",
        [
            '1 Användaren skriver "alternativ?" vid en byggdel.',
            "2 lookup_knowledge ger konstruktionens varianter som färdiga Option-poster.",
            "3 render_alternatives ritar sidan ALTERNATIV · <namn>: snitt, fakta, för- och nackdelar.",
            "4 Användaren skriver bokstaven på anmärkningens SVAR-rad.",
            "5 Nästa varv sätter chosen och ritar in det valda alternativets skikt.",
        ],
        "note",
    )
    return d


# --- 16. symbols -----------------------------------------------------------------


def symbol_svg(kind: str, size=64) -> str:
    import numpy as np

    from rmink.drawing.symbols import symbol_paths

    paths = symbol_paths(kind, (0.0, 0.0), 1.0)
    pts = np.vstack(paths)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    pad = 0.08 * max(x1 - x0, y1 - y0, 0.1)
    return svg_paths(paths, (x0 - pad, y0 - pad, x1 + pad, y1 + pad), size, stroke=1.8)


DISCIPLINE_ORDER = [
    ("", "Orientering och allmänt"),
    ("A", "A Arkitekt"),
    ("K", "K Konstruktion"),
    ("E", "E El"),
    ("B", "B Brand"),
    ("V", "V Värme och sanitet"),
    ("L", "L Ventilation"),
    ("M", "M Mark"),
]


def d16_symbols() -> Diagram:
    k = kb()["symbols"]["symbol"]
    d = Diagram(
        "16-symboler",
        f"16. Symboler ({len(k)} st)",
        "Ritade med rmink:s egen geometri (drawing/symbols.py), som på plattan. Etikett = standardtext vid symbolen; handskrivet = det Claude känner igen i skissen.",
    )
    groups: dict[str, list[dict]] = {}
    for s in k:
        key = "rev" if s["id"].startswith("revision") else s.get("discipline", "")
        groups.setdefault(key, []).append(s)
    order = DISCIPLINE_ORDER + [("rev", "Revision")]
    y = 110
    for key, title in order:
        ss = groups.get(key, [])
        if not ss:
            continue
        per_row = 4
        cell_w, cell_h = 430, 122
        rows = (len(ss) + per_row - 1) // per_row
        gid = d.group(
            40,
            y,
            per_row * cell_w + 20,
            rows * cell_h + 40,
            f"{title} ({len(ss)})",
            "data",
            hint=f"disc_{key or 'allm'}",
        )
        for i, s in enumerate(ss):
            cx = 10 + (i % per_row) * cell_w
            cy = 34 + (i // per_row) * cell_h
            d.image(cx, cy + 4, 64, 64, symbol_svg(s["id"]), gid, hint=s["id"])
            lines = [
                f"id {s['id']} · etikett {s.get('label') or '–'}",
                short(s.get("meaning", ""), 110),
                f"handskrivet: {', '.join(s.get('syn', []))}",
                f"regler: {rule_tags(s.get('rules', []))}",
            ]
            d.box(
                cx + 72,
                cy,
                cell_w - 84,
                cell_h - 10,
                label(s["name"], lines),
                "plain",
                gid,
                hint=s["id"] + "_t",
                size=10,
            )
        y += rows * cell_h + 60
    return d


# --- 17. hatches -----------------------------------------------------------------


def hatch_svg(pattern: str, angle: float, size=90) -> str:
    import numpy as np

    from rmink.drawing.render import _hatch

    box = (0.0, 0.0, 120.0, 80.0)
    paths = [np.array([[0, 0], [120, 0], [120, 80], [0, 80], [0, 0]], float)] + _hatch(
        box, pattern, angle, 9.0
    )
    return svg_paths(paths, (-3, -23, 123, 103), size, stroke=1.0)


def d17_hatches() -> Diagram:
    k = kb()
    mats = {m["id"]: m["name"] for m in k["materials"]["material"]}
    hs = k["hatches"]["hatch"]
    d = Diagram(
        "17-skrafferingar",
        f"17. Skrafferingar ({len(hs)} st)",
        "Mönstren ritade med samma kod som alternativsidan (render._hatch). Avstånd i mm på papper; tomma mönster visas bara som kontur.",
    )
    per_row, cw, ch = 3, 560, 140
    for i, h in enumerate(hs):
        x = 40 + (i % per_row) * cw
        y = 110 + (i // per_row) * ch
        d.image(
            x, y, 110, 110, hatch_svg(h["pattern"], float(h.get("angle", 0) or 0)), hint=h["id"]
        )
        users = [mats.get(u, u) for u in h.get("used_for", [])]
        mats_using = [
            m["name"]
            for m in k["materials"]["material"]
            if m.get("hatch") == h["id"] and m["id"] not in h.get("used_for", [])
        ]
        lines = [
            f"id {h['id']} · mönster {h['pattern']} · vinkel {h.get('angle', '–')}° · avstånd {sv(h.get('spacing_mm', 0))} mm",
            f"används för: {', '.join(users) or '–'}",
        ]
        if mats_using:
            lines.append(f"också (via material): {', '.join(mats_using)}")
        lines.append(short(h.get("note", ""), 160))
        d.box(
            x + 120,
            y,
            cw - 140,
            ch - 16,
            label(h["name"], lines),
            "plain",
            hint=h["id"] + "_t",
            size=10,
        )
    return d


# --- 18. review and markup -----------------------------------------------------------


def d18_markup() -> Diagram:
    k = kb()["markup"]
    d = Diagram(
        "18-granskning-och-markeringar",
        "18. Granskning och markeringar (markup.toml)",
        "Granskningsmarkeringar i Bluebeam-stil, kopplade till rmink:s anmärkningar: ringar med nummer på ritningen och SVAR-rader i ritningshuvudet.",
    )
    types = [
        [
            t["name"],
            t.get("en", ""),
            t.get("meaning", ""),
            f"{t['mono']['line_type']} / {t['mono']['mark']}",
            t.get("color", ""),
            t.get("default_severity", ""),
        ]
        for t in k["markup_type"]
    ]
    _, y1 = table_box(
        d,
        40,
        110,
        "Markeringstyper",
        ["typ", "en", "betyder", "gråskala", "färg", "grad"],
        types,
        [80, 70, 330, 120, 60, 60],
        "data",
    )
    st = [[s["name"], s.get("rmink", ""), s.get("meaning", "")] for s in k["status"]]
    _, y_st = table_box(
        d,
        840,
        110,
        "Status → Annotation.status",
        ["status", "rmink", "betyder"],
        st,
        [100, 80, 330],
        "data",
    )
    pr = [[p["name"], p.get("meaning", "")] for p in k["priority"]]
    _, y2 = table_box(d, 840, y_st + GAP, "Prioritet", ["", ""], pr, [80, 430], "data")
    cols = [[c["name"], c.get("from", "")] for c in k["csv"]["columns"]]
    table_box(
        d,
        40,
        y1 + GAP,
        "CSV-export (kolumner)",
        ["kolumn", "från"],
        cols,
        [100, 520],
        "data",
        sub=k["csv"].get("note", ""),
    )
    note_box(
        d,
        840,
        y2 + GAP,
        520,
        "I rundorna",
        [
            "En öppen fråga blir en Annotation (ring, kryss eller hörnmarkeringar på stora mål) med nummer.",
            "ANMÄRKNINGAR listar dem med en SVAR-rad var.",
            "Svar på raden eller vid ringen besvarar frågan; nästa varv sätter accepted eller rejected.",
            'Revisionen heter "<namn> rNN · N frågor" så länge frågor är öppna.',
        ],
        "note",
    )
    return d


# --- 19. terms ---------------------------------------------------------------------


CAT_NAMES = {
    "ritning": "Ritning",
    "process": "Process och lov",
    "matt": "Mått och nivåer",
    "vagg": "Väggar",
    "regel": "Regler och klasser",
    "bjalklag": "Bjälklag",
    "grund": "Grund",
    "tak": "Tak",
    "altan": "Altan, räcke och trappa",
    "oppning": "Öppningar",
    "installation": "Installationer",
    "material": "Material",
    "byggdel": "Byggdelar",
}


def d19_terms() -> Diagram:
    terms = kb()["terms"]["term"]
    d = Diagram(
        "19-begrepp",
        f"19. Begrepp och förkortningar ({len(terms)} st)",
        "Hur Claude läser handskrivna ord och förkortningar. Hänvisning = id i material, konstruktion, regel, ritstandard eller process.",
    )
    widths = [150, 60, 110, 420]
    cats: dict[str, list[dict]] = {}
    for t in terms:
        cats.setdefault(t["cat"], []).append(t)
    blocks = []
    for c, ts in cats.items():
        rows = [
            [
                t["term"],
                t.get("abbr", "") or "",
                t.get("ref", "") or "",
                short(t.get("def", ""), 170),
            ]
            for t in ts
        ]

        def make(x, y, c=c, rows=rows):
            return table_box(
                d,
                x,
                y,
                f"{CAT_NAMES.get(c, c)} ({len(rows)})",
                ["begrepp", "förk.", "hänvisning", "betydelse"],
                rows,
                widths,
                "data",
                hint=c,
            )[1]

        blocks.append(make)
    columns(d, 40, 110, sum(widths) + 16, 2, blocks)
    return d


# --- main ------------------------------------------------------------------------

DIAGRAMS: list[Callable[[], Diagram]] = [
    d01_overview,
    d02_convert,
    d03_round,
    d04_tools,
    d05_folders,
    d06_cloud,
    d07_release,
    d08_model,
    d09_structure,
    d10_rules,
    d11_process,
    d12_standard,
    d13_materials,
    d14_assemblies,
    d15_variants,
    d16_symbols,
    d17_hatches,
    d18_markup,
    d19_terms,
]


def build(out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for make in DIAGRAMS:
        d = make()
        path = out / f"{d.name}.drawio"
        path.write_text(d.xml(), encoding="utf-8")
        written.append(path)
    return written


def export(paths: list[Path], fmt: str = "svg") -> None:
    exe = shutil.which("drawio") or "/Applications/draw.io.app/Contents/MacOS/draw.io"
    if not Path(exe).exists() and not shutil.which("drawio"):
        print("draw.io saknas: hoppar över export")
        return
    for p in paths:
        target = p.with_suffix(f".{fmt}")
        subprocess.run(
            [exe, "-x", "-f", fmt, "--theme", "light", "--border", "24", "-o", str(target), str(p)],
            check=True,
            capture_output=True,
        )
        if fmt == "svg":
            strip_text_fallbacks(target)
        print(f"  {target.name} ({target.stat().st_size // 1024} kB)")


def strip_text_fallbacks(svg: Path) -> None:
    """draw.io adds a PNG of every HTML label for viewers without
    foreignObject; browsers and GitHub do not need them, and they make the
    files ten times larger. Our own pictures are SVG, so they stay."""
    import re

    text = svg.read_text(encoding="utf-8")
    text = re.sub(r'<image [^>]*xlink:href="data:image/png;base64,[^"]*"[^>]*/>', "", text)
    svg.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=HERE)
    ap.add_argument("--export", action="store_true", help="also export .svg with draw.io")
    ap.add_argument("--png", action="store_true", help="also export .png (for checking)")
    args = ap.parse_args()
    paths = build(args.out)
    print(f"{len(paths)} diagram i {args.out}")
    if args.export:
        export(paths, "svg")
    if args.png:
        export(paths, "png")


if __name__ == "__main__":
    main()
