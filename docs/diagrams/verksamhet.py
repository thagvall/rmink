# ruff: noqa: E501
"""The business diagrams: who does what, in which system, along each process.

Each chain is plain data for ``kedja.chain`` (lanes = roles, columns = phases,
cards = steps coloured by system). Red verbs happen outside rmink today:
at the municipality, on paper or by e-mail, or are planned. Built by
build.py into docs/diagrams/verksamhet/.
"""

from __future__ import annotations

from drawio import FONT, Diagram, esc
from kedja import HEADING, chain

LH = 172
R, B, T, L = (1, 0.5), (0.5, 1), (0.5, 0), (0, 0.5)  # right, bottom, top, left


def link(frm, to, text, exit, entry):
    return (frm, to, text, (*exit, *entry))


# --- 0. process map ----------------------------------------------------------------


PHASES = [
    (
        "Idé",
        "#DEEAF6",
        ["vad ska byggas", "altan, friggebod,", "tillbyggnad, badrum"],
        ["Byggherre"],
        "4",
    ),
    (
        "Skiss",
        "#E2EFDA",
        ["för hand på plattan", "mått, symboler", "i rmink/<projekt>/"],
        ["Byggherre", "Hantverkare"],
        "1",
    ),
    (
        "Ren ritning",
        "#E2EFDA",
        ["rmink + Claude ritar", "räta vinklar, skala", "frågor i stället för gissningar"],
        ["rmink", "Claude"],
        "1",
    ),
    (
        "Revisioner och val",
        "#E2EFDA",
        ["markera, svara, välja", "r01 → r02 → r03", "alternativ med U-värde"],
        ["Byggherre", "Hantverkare", "Claude"],
        "2, 3",
    ),
    (
        "Lov och anmälan",
        "#E4DFEC",
        ["lov eller lovfritt?", "bygglovshandling", "ansökan i kommunen"],
        ["Byggherre", "Byggnadsnämnd", "KA"],
        "4",
    ),
    (
        "Bygge",
        "#FCE4D6",
        ["ritningen i fält", "ändringar = nya varv", "beslut på SVAR-raden"],
        ["Hantverkare", "Elinstallatör", "KA"],
        "4",
    ),
    ("Relation", "#F2F2F2", ["som byggt", "hela historiken", "i Tidigare/"], ["Byggherre"], "4"),
]


def d00_processkarta() -> Diagram:
    d = Diagram(
        "00-processkarta",
        "rmink i byggprojektet: från idé till relationshandling",
        "Varje fas med vad rmink gör, vilka roller som deltar och vilket kedjediagram som visar detaljerna.",
        title_color=HEADING,
        title_size=26,
    )
    w, gap, x0, y0 = 236, 10, 40, 110
    for i, (name, fill, does, roles, ref) in enumerate(PHASES):
        x = x0 + i * (w + gap)
        style = (
            f"shape=step;perimeter=stepPerimeter;fixedSize=1;size=22;whiteSpace=wrap;html=1;"
            f"fillColor={fill};strokeColor=#1F4E79;strokeWidth=2;fontFamily={FONT};fontSize=18;"
            "fontStyle=1;fontColor=#1F4E79;"
        )
        d.raw(x, y0, w, 64, esc(name), style, hint=f"fas{i}")
        body = (
            "<b>I fasen:</b><br>"
            + "<br>".join(esc(t) for t in does)
            + "<br><br><b>Roller:</b><br>"
            + esc(", ".join(roles))
            + f'<br><br><font color="#1F4E79"><b>Se kedja {esc(ref)}</b></font>'
        )
        d.raw(
            x + 6,
            y0 + 80,
            w - 16,
            196,
            body,
            f"rounded=1;arcSize=4;whiteSpace=wrap;html=1;fillColor=#FFFFFF;strokeColor=#BFBFBF;fontFamily={FONT};fontSize=14;align=left;verticalAlign=top;spacing=10;fontColor=#262626;",
            hint=f"fasbox{i}",
        )
    y = y0 + 300
    ways = [
        (
            "rmink på webben",
            "rmink.vercel.app: bild eller PDF till redigerbar anteckningsbok, Send to reMarkable. /rounds: ägarens revisionsvarv med ett tryck.",
            "#DAEEF3",
        ),
        (
            "rmink i din egen Claude",
            "MCP-servern: Claude Desktop eller Claude Code tolkar skissen med rmink:s verktyg. Ingen kostnad för rmink, du använder ditt eget Claude-konto.",
            "#FCE4D6",
        ),
        (
            "rmink är gratis",
            "Ingen betalvägg. Frivilligt stöd på 100 kr via Stripe. Källkoden är öppen (AGPL).",
            "#E2EFDA",
        ),
    ]
    for i, (h, t, fill) in enumerate(ways):
        d.raw(
            40 + i * 576,
            y,
            556,
            96,
            f"<b>{esc(h)}</b><br>{esc(t)}",
            f"rounded=1;arcSize=6;whiteSpace=wrap;html=1;fillColor={fill};strokeColor=#1F4E79;fontFamily={FONT};fontSize=15;align=left;verticalAlign=top;spacing=12;fontColor=#262626;",
        )
    chains = [
        "1 Från handskiss till ren ritning",
        "2 Revisionsvarv: ändringar och svar",
        "3 Val mellan alternativ",
        "4 Bygglov och byggprocessen",
        "5 Bild eller PDF till reMarkable",
    ]
    d.text(
        40,
        y + 116,
        1700,
        26,
        "<b>Kedjediagram:</b> " + esc(" · ".join(chains)),
        size=15,
        color=HEADING,
    )
    return d


# --- 1. sketch to drawing ---------------------------------------------------------------


def d01_skiss() -> Diagram:
    roles = [
        ("hus", "**Byggherre / husägare**\nreMarkable-platta", LH),
        ("moln", "**reMarkable Cloud**\nsynkar plattan", LH),
        ("rmink", "**rmink**\n/rounds · MCP", LH),
        ("claude", "**Claude**\ntolkar och frågar", LH),
        ("kb", "**Kunskapsbas**\nBFS 2024 · PBL · material", LH),
        ("hant", "**Hantverkare**\nplatta · telefon", LH),
    ]
    steps = [
        (
            "skiss",
            "hus",
            0,
            "platta",
            "1 · skissar",
            "Handskiss",
            ["i rmink/ eller egen mapp", "mått, symboler, förklaring", "med pennan på plattan"],
        ),
        (
            "synk",
            "moln",
            1,
            "moln",
            "2 · synkar",
            "Anteckningsbok",
            ["plattan laddar upp själv", "ingen export, ingen USB"],
        ),
        (
            "start",
            "rmink",
            1,
            "rmink",
            "3 · startar varv",
            "Kör första varvet",
            ["välj skissen i rmink/", "ett tryck, cirka 1 minut"],
        ),
        (
            "las",
            "rmink",
            2,
            "rmink",
            "4 · läser",
            "Streck i grupper",
            ["linjer, cirklar, text", "numrerade för Claude"],
        ),
        (
            "tolka",
            "claude",
            2,
            "claude",
            "5 · tolkar",
            "Ritningsmodell",
            ["väggar, mått, symboler", "frågar hellre än gissar"],
        ),
        (
            "krav",
            "kb",
            3,
            "kb",
            "6 · slår upp",
            "Krav och material",
            ["räcken, glas: BFS 2024:9", "material med klass", "typkonstruktioner"],
        ),
        (
            "kontroll",
            "rmink",
            3,
            "rmink",
            "7 · kontrollerar",
            "Vinklar och mått",
            ["väggar möts i 90°", "skala ur skrivna mått", "avvikelse blir en fråga"],
        ),
        (
            "granska",
            "claude",
            3,
            "claude",
            "8 · granskar",
            "Bilden före sparande",
            ["ser förhandsbilden", "rättar och ritar om"],
        ),
        (
            "lev",
            "rmink",
            4,
            "rmink",
            "9 · levererar",
            "r01 · 2 frågor",
            ["ren ritning + skissen", "frågor med SVAR-rad", "förklaringar, ändringslogg"],
        ),
        (
            "ut",
            "moln",
            4,
            "moln",
            "10 · synkar",
            "Till plattan",
            ["överst i rmink/<projekt>/", "skissen till Tidigare/"],
        ),
        (
            "mark",
            "hus",
            5,
            "platta",
            "11 · markerar",
            "Svar och ändringar",
            ["svar på SVAR-raden", "ringar, kryss, ny text", "→ nästa varv (kedja 2)"],
        ),
        (
            "dela",
            "hant",
            5,
            "dok",
            "!12 · ser ritningen",
            "Delad ritning",
            ["skärmbild eller utskrift", "SVG-export finns,", "delning inte inbyggd"],
        ),
    ]
    links = [
        link("skiss", "synk", "", R, T),
        link("synk", "start", "hämtas", B, T),
        link("start", "las", "", R, L),
        link("las", "tolka", "bild + grupper", B, T),
        link("tolka", "kontroll", "ritningsmodell", R, L),
        link("tolka", "krav", "slår upp", B, L),
        link("kontroll", "granska", "", B, T),
        link("krav", "granska", "regler", T, B),
        link("granska", "lev", "sparar", R, L),
        link("lev", "ut", "", T, B),
        link("ut", "mark", "", R, B),
        link("lev", "dela", "SVG", B, L),
    ]
    return chain(
        "01-fran-skiss-till-ritning",
        "1. Från handskiss till ren ritning: första varvet",
        roles,
        ["Skissa", "Synka och starta", "Läsa och tolka", "Kontrollera", "Leverera", "Markera"],
        steps,
        links,
        ["platta", "moln", "rmink", "claude", "kb", "dok"],
        note='Rött = görs utanför rmink i dag. Ritningen hamnar i samma mapp som skissen; skissen sparas i Tidigare/ som "<namn> r00 skiss".',
    )


# --- 2. revision rounds ---------------------------------------------------------------


def d02_revision() -> Diagram:
    roles = [
        ("hus", "**Byggherre / husägare**\nreMarkable-platta", LH),
        ("hant", "**Hantverkare / konstruktör**\nsvarar på tekniska frågor", LH),
        ("moln", "**reMarkable Cloud**\nsynkar plattan", LH),
        ("rmink", "**rmink**\n/rounds · MCP", LH),
        ("claude", "**Claude**\ntolkar markeringar", LH),
        ("kb", "**Kunskapsbas**\nBFS 2024 · PBL", LH),
    ]
    steps = [
        (
            "ring",
            "hus",
            0,
            "platta",
            "1 · markerar",
            "Ändring på ritningen",
            ["ring, kryss, överstrykning", "i lagret Kommentarer", "skriv det nya bredvid"],
        ),
        (
            "svar",
            "hant",
            0,
            "platta",
            "2 · svarar",
            "Svar på SVAR-raden",
            ['fråga 2: "45×195 C24"', "bokstav vid alternativ"],
        ),
        (
            "synk",
            "moln",
            1,
            "moln",
            "3 · synkar",
            "Markerad revision",
            ["samma anteckningsbok", "inget att exportera"],
        ),
        (
            "nytt",
            "rmink",
            2,
            "rmink",
            "4 · kör nästa varv",
            "Bara nya streck",
            ["egna streck känns igen", "öppna frågor numreras"],
        ),
        (
            "tolka",
            "claude",
            3,
            "claude",
            "5 · tolkar",
            "Ändring eller svar?",
            ["ändring → in i ritningen", "svar → frågan stängs", "oklart → ny fråga"],
        ),
        (
            "regel",
            "kb",
            3,
            "kb",
            "6 · kontrollerar",
            "Mot regler",
            ["till exempel räckeshöjd", "glas, trappor, brand"],
        ),
        (
            "rev",
            "rmink",
            4,
            "rmink",
            "7 · ritar",
            "r02 · 1 fråga",
            ['ÄNDRINGAR: "r2: …"', "svaren inarbetade", "kvarstående frågor"],
        ),
        (
            "ark",
            "moln",
            5,
            "moln",
            "8 · arkiverar",
            "r01 → Tidigare/",
            ["hela historiken kvar", "äldst först"],
        ),
        (
            "ata",
            "hus",
            5,
            "dok",
            "!9 · dokumenterar",
            "Beslut och ÄTA",
            ["SVAR-rader = beslutslogg", "export till CSV planerad"],
        ),
    ]
    links = [
        link("ring", "synk", "", R, T),
        link("svar", "synk", "", R, L),
        link("synk", "nytt", "hämtas", R, T),
        link("nytt", "tolka", "nya markeringar", R, T),
        link("tolka", "regel", "slår upp", B, T),
        link("tolka", "rev", "ändrad ritning", R, B),
        link("rev", "ark", "", R, B),
        link("rev", "ata", "beslut", T, L),
    ]
    return chain(
        "02-revisionsvarv",
        "2. Revisionsvarv: ändringar och svar blir en ny revision",
        roles,
        ["Markera", "Synka", "Läsa nytt", "Tolka", "Ny revision", "Arkivera"],
        steps,
        links,
        ["platta", "moln", "rmink", "claude", "kb", "dok"],
        note='Rött = görs utanför rmink i dag. Revisionen heter "<namn> rNN · N frågor" så länge frågor är öppna; varje varv tar ungefär en minut.',
    )


# --- 3. alternatives ------------------------------------------------------------------


def d03_alternativ() -> Diagram:
    roles = [
        ("hus", "**Byggherre / husägare**\nreMarkable-platta", LH),
        ("hant", "**Hantverkare / konstruktör**\nråd om utförande", LH),
        ("claude", "**Claude**\nsammanställer", LH),
        ("kb", "**Kunskapsbas**\nkonstruktioner och varianter", LH),
        ("rmink", "**rmink**\nräknar och ritar", LH),
    ]
    steps = [
        (
            "fraga",
            "hus",
            0,
            "platta",
            "1 · frågar",
            '"alternativ?"',
            ["skrivs vid byggdelen", "plattan, väggen, altanen", 'eller "hur tjock?"'],
        ),
        (
            "tolk",
            "claude",
            1,
            "claude",
            "2 · förstår",
            "Vilken byggdel",
            ["kopplar frågan till", "konstruktionen i ritningen"],
        ),
        (
            "var",
            "kb",
            1,
            "kb",
            "3 · slår upp",
            "Varianter A–E",
            ["platta på mark: 5", "yttervägg: 4", "altan: 4"],
        ),
        (
            "rakna",
            "rmink",
            2,
            "rmink",
            "4 · räknar",
            "Tjocklek, vikt, U",
            ["U-värde: λ-metoden", "vikt ur densitet", "utan köldbryggor"],
        ),
        (
            "samm",
            "claude",
            2,
            "claude",
            "5 · sammanställer",
            "2–4 lösningar",
            ["för- och nackdelar", "kostnadsnivå", "när den passar"],
        ),
        (
            "sida",
            "rmink",
            3,
            "rmink",
            "6 · ritar",
            "Sidan ALTERNATIV",
            ["snitt med skraffering", "fakta i siffror", "A, B, C …"],
        ),
        (
            "rad",
            "hant",
            3,
            "platta",
            "7 · ger råd",
            "Utförande och pris",
            ["tillgång, arbetssätt", "pris i området"],
        ),
        (
            "valj",
            "hus",
            4,
            "platta",
            "8 · väljer",
            "Bokstav på SVAR-raden",
            ['till exempel "B"', "går att ändra nästa varv"],
        ),
        (
            "in",
            "rmink",
            5,
            "rmink",
            "9 · ritar in",
            "Valt alternativ",
            ["skikten i sektion och text", "frågan stängs"],
        ),
        (
            "ver",
            "hant",
            5,
            "dok",
            "!10 · verifierar",
            "Energi och bärförmåga",
            ["U-värdet är en uppskattning", "energiberäkning, BFS 2026:9", "konstruktör vid behov"],
        ),
    ]
    links = [
        link("fraga", "tolk", "", R, T),
        link("tolk", "var", "slår upp", B, T),
        link("var", "rakna", "skikt", R, (0.3, 0)),
        link("rakna", "samm", "fakta", (0.7, 0), (0.7, 1)),
        link("samm", "sida", "", R, (0.3, 0)),
        link("sida", "rad", "alternativsidan", (0.7, 0), (0.7, 1)),
        link("rad", "valj", "", R, (0.3, 1)),
        link("valj", "in", "nästa varv", (0.7, 1), L),
        link("in", "ver", "", T, B),
    ]
    return chain(
        "03-val-mellan-alternativ",
        '3. Val mellan alternativ: "hur tjock?" blir ett beslut',
        roles,
        ["Fråga", "Hämta varianter", "Räkna", "Jämföra", "Välja", "Rita in"],
        steps,
        links,
        ["platta", "claude", "kb", "rmink", "dok"],
        note="Rött = görs utanför rmink. Varianterna finns i dag för platta på mark (PL1), yttervägg (YV1) och altan på plintar (ALT1).",
    )


# --- 4. permit and building process ------------------------------------------------------


def d04_lov() -> Diagram:
    roles = [
        ("bh", "**Byggherre / husägare**\nreMarkable-platta", LH),
        ("rm", "**rmink + Claude**\nritningar per skede", LH),
        ("ka", "**Kontrollansvarig (KA)**\nnär det krävs", LH),
        ("nam", "**Byggnadsnämnden**\nkommunen", LH),
        ("hant", "**Hantverkare / entreprenör**\nplattan i fält", LH),
        ("el", "**Elinstallatör**\nauktoriserad (ElSL)", LH),
    ]
    steps = [
        (
            "ide",
            "bh",
            0,
            "platta",
            "1 · skissar",
            "Idéskiss",
            ["altan, friggebod, tillbyggnad", "mått och placering"],
        ),
        (
            "lov",
            "rm",
            1,
            "rmink",
            "2 · prövar",
            "Lov eller lovfritt?",
            ["åtgärden mot PBL 9 kap.", "komplementbyggnad ≤ 30 m²", "nära gräns: 4,5 m"],
        ),
        (
            "bl",
            "rm",
            2,
            "rmink",
            "3 · ritar",
            "Bygglovshandling",
            ["plan, sektion, fasad", "skede: bygglovshandling", "krav blir frågor"],
        ),
        (
            "ans",
            "bh",
            2,
            "kommun",
            "!4 · ansöker",
            "Ansökan / anmälan",
            ["kommunens e-tjänst", "fastighetsbeteckning", "KA om det krävs"],
        ),
        (
            "samr",
            "nam",
            3,
            "kommun",
            "!5 · håller",
            "Tekniskt samråd",
            ["kontrollplanen fastställs", "startbesked ges"],
        ),
        (
            "kp",
            "ka",
            3,
            "dok",
            "!6 · upprättar",
            "Kontrollplan",
            ["kontroller, vem, när", "rmink: förslag ur reglerna", "(planerat)"],
        ),
        (
            "bh2",
            "rm",
            4,
            "rmink",
            "7 · ritar om",
            "Revision vid ändring",
            ["SVAR-rader = beslut", "underlag för ÄTA"],
        ),
        (
            "bygg",
            "hant",
            4,
            "platta",
            "8 · bygger",
            "Ritningen i fält",
            ["alltid senaste revisionen", "ändringar = nya varv"],
        ),
        (
            "elinst",
            "el",
            4,
            "dok",
            "!9 · installerar",
            "Elinstallation",
            ["auktoriserad elinstallatör", "ElSL 4 §, 24–27 §§"],
        ),
        (
            "utl",
            "ka",
            5,
            "dok",
            "!10 · intygar",
            "Utlåtande",
            ["kontrollerna gjorda", "inför slutsamråd"],
        ),
        (
            "slut",
            "nam",
            5,
            "kommun",
            "!11 · beslutar",
            "Slutbesked",
            ["byggnaden får tas i bruk", "PBL 10 kap. 34–38 §§"],
        ),
        (
            "rel",
            "rm",
            5,
            "rmink",
            "12 · ritar",
            "Relationshandling",
            ["som byggt", "skede: relationshandling"],
        ),
    ]
    links = [
        link("ide", "lov", "", R, T),
        link("lov", "bl", "", R, L),
        link("bl", "ans", "ritningar", T, B),
        link("ans", "samr", "ansökan", R, L),
        link("samr", "kp", "", T, B),
        link("samr", "bygg", "startbesked", R, (0.3, 0)),
        link("bygg", "bh2", "ändring", (0.7, 0), (0.7, 1)),
        link("bh2", "rel", "som byggt", R, L),
        link("kp", "utl", "", R, L),
        link("elinst", "utl", "", R, (0, 0.85)),
        link("utl", "slut", "", B, T),
    ]
    return chain(
        "04-bygglov-och-byggprocess",
        "4. Bygglov och byggprocessen för småhus, med rmink",
        roles,
        ["Idé och skiss", "Lovfråga", "Ansökan", "Samråd och start", "Utförande", "Slutbesked"],
        steps,
        links,
        ["platta", "rmink", "kommun", "dok"],
        note="Rött = sker hos kommunen, på papper eller hos andra aktörer. rmink stöder med ritningar per skede och frågor ur PBL, PBF, ElSL och BFS 2024;\nprövningen görs alltid av byggnadsnämnden. Kontrollansvarig krävs inte för anmälan, komplementbyggnader eller små ändringar av småhus.",
    )


# --- 5. image or PDF to reMarkable ------------------------------------------------------------


def d05_bild() -> Diagram:
    roles = [
        ("anv", "**Användare**\ntelefon eller dator", LH),
        ("webb", "**rmink på webben**\nrmink.vercel.app", LH),
        ("moln", "**reMarkable Cloud**", LH),
        ("platta", "**reMarkable-platta**\nrm2, Paper Pure, Pro, Move", LH),
    ]
    steps = [
        (
            "fil",
            "anv",
            0,
            "webb",
            "1 · väljer",
            "Bild, PDF eller foto",
            ["kamera eller fil", "PDF, SVG, PNG, JPEG, HEIC"],
        ),
        (
            "stil",
            "anv",
            1,
            "webb",
            "2 · väljer stil",
            "Linjer och skuggning",
            ["linjer eller konturer", "prickar, raster, blyerts", "penna och färger"],
        ),
        (
            "prev",
            "webb",
            1,
            "webb",
            "3 · visar",
            "Förhandsbild",
            ["samma streck som plattan", "stilarna sida vid sida"],
        ),
        (
            "konv",
            "webb",
            2,
            "rmink",
            "4 · konverterar",
            "Redigerbara streck",
            [".rmdoc, inte en bild", "färg på Pro och Move"],
        ),
        (
            "kopp",
            "anv",
            3,
            "webb",
            "5 · kopplar",
            "Engångskod",
            ["från my.remarkable.com", "en gång per webbläsare"],
        ),
        (
            "send",
            "webb",
            3,
            "rmink",
            "6 · skickar",
            "Send to reMarkable",
            ["direkt till molnet", "eller ladda ner .rmdoc"],
        ),
        (
            "synk",
            "moln",
            4,
            "moln",
            "7 · synkar",
            "Anteckningsbok",
            ["dyker upp på plattan", "inom någon minut"],
        ),
        (
            "usb",
            "platta",
            4,
            "dok",
            "!8 · alternativ",
            "USB eller appen",
            [".rmdoc via USB-webben", "eller reMarkable-appen"],
        ),
        (
            "anv2",
            "platta",
            5,
            "platta",
            "9 · använder",
            "Redigera på plattan",
            ["sudda, flytta, rita vidare", "som egna pennstreck"],
        ),
    ]
    links = [
        link("fil", "stil", "", R, L),
        link("stil", "prev", "", B, T),
        link("prev", "konv", "", R, L),
        link("konv", "send", "", R, L),
        link("kopp", "send", "token", B, T),
        link("send", "synk", "", R, T),
        link("synk", "anv2", "", R, T),
        link("konv", "usb", "ladda ner", B, L),
        link("usb", "anv2", "", R, L),
    ]
    return chain(
        "05-bild-eller-pdf-till-remarkable",
        "5. Bild eller PDF till reMarkable: redigerbara pennstreck",
        roles,
        ["Välja", "Förhandsgranska", "Konvertera", "Skicka", "Synka", "Använda"],
        steps,
        links,
        ["webb", "rmink", "moln", "platta", "dok"],
        note="Rött = alternativ väg utanför rmink. Token för Send to reMarkable sparas bara i användarens webbläsare.",
    )


DIAGRAMS = [d00_processkarta, d01_skiss, d02_revision, d03_alternativ, d04_lov, d05_bild]


def build(out) -> list:
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for make in DIAGRAMS:
        d = make()
        path = out / f"{d.name}.drawio"
        path.write_text(d.xml(), encoding="utf-8")
        written.append(path)
    return written
