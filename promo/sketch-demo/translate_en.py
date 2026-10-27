"""English version of the demo page: template.html -> template-en.html.

Exact replacements, longest first, then a check that no Swedish text is left.
The drawings themselves keep their Swedish labels (FÖRKLARINGAR, ANMÄRKNINGAR,
Ritning r1): that is what rmink writes on the tablet today.

Usage: python translate_en.py
"""

import re
import sys
from pathlib import Path

HERE = Path(__file__).parent

PAIRS = [
    # Header and section intros
    ("rmink · fas 1 · förslag", "rmink · phase 1 · proposal"),
    (
        'Från handskiss <span class="arrow">→</span> ren ritning, i omgångar',
        'From hand sketch <span class="arrow">→</span> clean drawing, in rounds',
    ),
    (
        "Skissa en 2D-ritning på reMarkable med mått, symboler och en liten legend. rmink och Claude ritar rent den, du markerar på plattan, och nästa revision tar hand om markeringarna. Alla streck nedan är riktig utdata från rmink.",
        "Sketch a 2D drawing on a reMarkable with measurements, symbols and a small legend. rmink and Claude draw it clean, you mark it up on the tablet, and the next revision deals with your marks. Every stroke below is real output from rmink.",
    ),
    (">Skiss till revision 2<", ">Sketch to revision 2<"),
    (">Varianter A och B<", ">Variants A and B<"),
    (">Nedslag i en detalj<", ">Zoom into a detail<"),
    (">Pappersskiss via mobilen<", ">Paper sketch via phone<"),
    (">Alla scenarier<", ">All scenarios<"),
    ("Scenario 5 · koncept", "Scenario 5 · concept"),
    (
        "Samma altan, två sätt att bära bjälklaget. Claude tar fram båda från samma ritningsmodell, och de hamnar som två sidor i samma anteckningsbok. Du väljer genom att rita på plattan.",
        "The same deck, two ways to carry the joists. Claude makes both from the same drawing model, and they land as two pages in one notebook. You choose by drawing on the tablet.",
    ),
    (
        "<b>Inte byggt än.</b> Varianterna är gjorda för hand i ritningsmodellen. Sidorna, spannen och vilka streck som räknas som nya kommer ändå från rminks riktiga renderare och gruppering.",
        "<b>Not built yet.</b> The variants are made by hand in the drawing model. The pages, the spans and which strokes count as new still come from rmink's real renderer and grouping.",
    ),
    ("Scenario 4 · koncept", "Scenario 4 · concept"),
    (
        "Ringa in ett hörn på översikten, så får du en detaljsida i större skala där pelaren och väggarna har sina riktiga mått. Där fortsätter diskussionen, och översikten får en markering som pekar på detaljen. Revisionerna följer fas för fas.",
        "Ring a corner on the overview and you get a detail page at a larger scale, where the post and the walls have their real sizes. The discussion carries on there, and the overview gets a mark that points to the detail. Revisions follow phase by phase.",
    ),
    (
        "<b>Inte byggt än.</b> Detaljsidan är gjord för hand i ritningsmodellen. Sidorna och vilka streck som räknas som nya kommer ändå från rminks riktiga renderare och gruppering.",
        "<b>Not built yet.</b> The detail page is made by hand in the drawing model. The pages and which strokes count as new still come from rmink's real renderer and grouping.",
    ),
    ("Scenario 6 · delvis byggt", "Scenario 6 · partly built"),
    ("Scenario 7 · delvis byggt", "Scenario 7 · partly built"),
    (
        "Alla har inte plattan med sig. En skiss på papper från ett möte fotas med mobilen i webbappen och går in i samma tolkning som skisserna från plattan. Den rena ritningen hamnar på plattan, och därifrån fortsätter omgångarna som vanligt.",
        "Not everyone has the tablet with them. A paper sketch from a meeting is photographed with the phone in the web app and goes through the same interpretation as sketches from the tablet. The clean drawing lands on the tablet, and the rounds carry on from there.",
    ),
    (
        "<b>Delvis byggt.</b> Kameraknappen, fotokonverteringen och Send to reMarkable finns redan i webbappen, och bläcket nedan kommer från just den konverteringen. Tolkningen till en ren ritning finns i dag via Claude och MCP. I webbappen är den fas 2.",
        "<b>Partly built.</b> The camera button, the photo conversion and Send to reMarkable are already in the web app, and the ink below comes from that very conversion. Turning it into a clean drawing works today through Claude and MCP. In the web app it is phase 2.",
    ),
    (
        "<b>Delvis byggt.</b> SVG-exporten finns och bilden till höger i steg 2 är dess riktiga utdata. PDF och DXF är nästa steg. Arket och CAD-vyn är ritade ur samma modell för att visa hur de skulle se ut.",
        "<b>Partly built.</b> The SVG export exists and the picture on the right in step 2 is its real output. PDF and DXF are next steps. The sheet and the CAD view are drawn from the same model to show how they would look.",
    ),
    (">Export och delning<", ">Export and sharing<"),
    (
        "Ritningen är data, så den kan lämna plattan i flera format: SVG att dela direkt, PDF att skriva ut i skala och DXF att öppna i CAD. Alla tre kommer ur samma ritningsmodell som revisionerna.",
        "The drawing is data, so it can leave the tablet in several formats: SVG to share right away, PDF to print to scale and DXF to open in CAD. All three come from the same drawing model as the revisions.",
    ),
    ("Sida 1 · A", "Page 1 · A"),
    ("Sida 2 · B", "Page 2 · B"),
    ("Sida 1 · översikt", "Page 1 · overview"),
    ("Sida 2 · detalj A", "Page 2 · detail A"),
    ("Mobilen · rmink.vercel.app", "Phone · rmink.vercel.app"),
    ('<div class="duo-label">Plattan</div>', '<div class="duo-label">Tablet</div>'),
    (
        '<div class="duo-label" data-role="vlabel">Mottagaren</div>',
        '<div class="duo-label" data-role="vlabel">Recipient</div>',
    ),
    ("Mobil<small>kamera</small>", "Phone<small>camera</small>"),
    ("rmink<small>foto till bläck</small>", "rmink<small>photo to ink</small>"),
    ("Claude<small>tolkning</small>", "Claude<small>interpretation</small>"),
    ("Claude<small>på begäran</small>", "Claude<small>on request</small>"),
    ("rmink<small>geometri</small>", "rmink<small>geometry</small>"),
    ("Mottagare<small>webb, skrivare, CAD</small>", "Recipient<small>web, printer, CAD</small>"),
    ("Platta<small>du</small>", "Tablet<small>you</small>"),
    ("Moln<small>synk</small>", "Cloud<small>sync</small>"),
    ("rmink<small>export</small>", "rmink<small>export</small>"),
    ("<h2>Åtta sätt att använda det</h2>", "<h2>Eight ways to use it</h2>"),
    (">Scenarier<", ">Scenarios<"),
    (
        "Demon överst visar scenario 1, 3 och 8, med en legend från scenario 2. Scenario 4 till 7 visas i egna animeringar ovan. Alla bygger på samma modell: ritningen sparas som data mellan omgångarna, så varje revision vet vad den förra innehöll.",
        "The demo at the top shows scenarios 1, 3 and 8, with a legend from scenario 2. Scenarios 4 to 7 have their own animations above. All of them build on the same model: the drawing is kept as data between rounds, so every revision knows what the previous one held.",
    ),
    ("<h3>Färg och gråskala</h3>", "<h3>Colour and greyscale</h3>"),
    (
        "<b>Paper Pro och Move:</b> varje kategori får en egen färg. El är röd, VVS blå, ändringar gröna och kommentarer magenta.",
        "<b>Paper Pro and Move:</b> every category gets its own colour. Electrical is red, plumbing blue, changes green and comments magenta.",
    ),
    (
        "<b>rm2 och Paper Pure:</b> samma kategorier skiljs åt med heldragen, streckad, prickad eller streckprickad linje och med olika tjocklek.",
        "<b>rm2 and Paper Pure:</b> the same categories are told apart by solid, dashed, dotted or dash-dot lines and by width.",
    ),
    (
        "<li>Byt platta under demon för att se skillnaden.</li>",
        "<li>Switch tablets in the demo to see the difference.</li>",
    ),
    ("<h3>Vem gör vad</h3>", "<h3>Who does what</h3>"),
    (
        "<li><b>Claude</b> läser handskrift och avgör vad varje grupp är: vägg, mått, symbol eller anmärkning.</li>",
        "<li><b>Claude</b> reads handwriting and decides what each group is: a wall, a measurement, a symbol or a remark.</li>",
    ),
    (
        "<li><b>rmink</b> sköter geometrin. Det räknar om linjer och cirklar, rätar upp hörn, kontrollerar måtten och ritar.</li>",
        "<li><b>rmink</b> handles the geometry. It fits lines and circles, squares up corners, checks the measurements and draws.</li>",
    ),
    (
        "<li>Tolkningen körs i användarens egen Claude, så rmink förblir gratis.</li>",
        "<li>The interpretation runs in the user's own Claude, so rmink stays free.</li>",
    ),
    ("<h3>Att verifiera på plattan</h3>", "<h3>To verify on a tablet</h3>"),
    (
        "<li>Behåller plattan rminks streck-id:n efter synk? Det krävs för att bara de nya strecken ska plockas upp.</li>",
        "<li>Does the tablet keep rmink's stroke ids after a sync? That is what lets only the new strokes be picked up.</li>",
    ),
    (
        "<li>Går lagret <code>Kommentarer</code> att välja och rita i?</li>",
        "<li>Can you select the <code>Kommentarer</code> (comments) layer and draw on it?</li>",
    ),
    (
        "<li>Hur väl läses riktiga handskrivna mått som <code>45°</code> och <code>Ø110</code>?</li>",
        "<li>How well are real handwritten measurements such as <code>45°</code> and <code>Ø110</code> read?</li>",
    ),
    (
        "rmink är gratis och öppen källkod. Skissen, markeringarna, varianterna, detaljen och fotot i demon är syntetiska, liksom PDF-arket och DXF-filen i exportdemon. Grupperna, måttkontrollen, renritningarna och vilka streck som räknas som nya kommer från rmink 2.2.1 med fas 1-koden.",
        "rmink is free and open source. The sketch, the marks, the variants, the detail and the photo in the demo are synthetic, as are the PDF sheet and the DXF file in the export demo. The groups, the measurement check, the clean drawings and which strokes count as new come from rmink 2.2.1 with the phase 1 code.",
    ),
    # Attributes
    ('aria-label="På sidan"', 'aria-label="On this page"'),
    ('aria-label="Demo: skiss till revision 2"', 'aria-label="Demo: sketch to revision 2"'),
    ('aria-label="Demo: varianter A och B"', 'aria-label="Demo: variants A and B"'),
    ('aria-label="Demo: nedslag i en detalj"', 'aria-label="Demo: zoom into a detail"'),
    ('aria-label="Demo: pappersskiss"', 'aria-label="Demo: paper sketch"'),
    ('aria-label="Demo: export"', 'aria-label="Demo: export"'),
    ('aria-label="Plattans skärm"', 'aria-label="Tablet screen"'),
    ('aria-label="Föregående steg"', 'aria-label="Previous step"'),
    ('aria-label="Nästa steg"', 'aria-label="Next step"'),
    ('aria-label="Platta"', 'aria-label="Tablet"'),
    ('aria-label="Steg"', 'aria-label="Steps"'),
    ('aria-label="Sida med variant A"', 'aria-label="Page with variant A"'),
    ('aria-label="Sida med variant B"', 'aria-label="Page with variant B"'),
    ('aria-label="Översiktssidan"', 'aria-label="Overview page"'),
    ('aria-label="Detaljsidan"', 'aria-label="Detail page"'),
    (
        'alt="Foto av en blyertsskiss på papper: ett förråd 3000 × 2400 med dörr och fönster"',
        'alt="Photo of a pencil sketch on paper: a 3000 × 2400 shed with a door and a window"',
    ),
    ("▶ Spela upp", "▶ Play"),
    ('"❚❚ Pausa"', '"❚❚ Pause"'),
    (
        "`Steg ${this.step + 1} av ${this.steps.length}`",
        "`Step ${this.step + 1} of ${this.steps.length}`",
    ),
    # Demo 1
    (
        "<b>Väggar V1–V4</b> <span>· bärande, linjerna räknas om till raka</span>",
        "<b>Walls V1–V4</b> <span>· load-bearing, the lines are fitted straight</span>",
    ),
    (
        "<b>Mått 4800</b> <span>· måttlinje + handskrivet tal</span>",
        "<b>Measurement 4800</b> <span>· dimension line + handwritten number</span>",
    ),
    (
        "<b>Mått 3600</b> <span>· lodrätt, läses nedifrån</span>",
        "<b>Measurement 3600</b> <span>· vertical, read from below</span>",
    ),
    (
        "<b>Pelare P1–P4</b> <span>· symbolen från legenden</span>",
        "<b>Posts P1–P4</b> <span>· the symbol from the legend</span>",
    ),
    (
        "<b>Brunn B1</b> <span>· blå cirkel = VVS</span>",
        "<b>Drain B1</b> <span>· blue circle = plumbing</span>",
    ),
    (
        "<b>Eluttag med ledning</b> <span>· röd penna = el</span>",
        "<b>Outlet with cable</b> <span>· red pen = electrical</span>",
    ),
    (
        "<b>Legend</b> <span>· pelare 90×90, brunn, el</span>",
        "<b>Legend</b> <span>· post 90×90, drain, electrical</span>",
    ),
    ("<b>Rubrik</b> <span>· “ALTAN”</span>", "<b>Title</b> <span>· “ALTAN” (deck)</span>"),
    ('title: "Skissa på plattan", chip: "Skissa"', 'title: "Sketch on the tablet", chip: "Sketch"'),
    ('"Altan · sida 1"', '"Altan · page 1"'),
    ('"Lager 1"', '"Layer 1"'),
    (
        "Du ritar fritt med pennan: väggar, två mått, pelare i hörnen, en brunn och ett eluttag. I hörnet skriver du vad symbolerna betyder. På Paper Pro kan pennfärgen redan säga något: blått för VVS, rött för el.",
        "You draw freely with the pen: walls, two measurements, posts in the corners, a drain and an outlet. In the corner you write what the symbols mean. On Paper Pro the pen colour can already say something: blue for plumbing, red for electrical.",
    ),
    (
        '[DATA.counts.sketch, "streck"], ["3", "pennfärger"], ["1", "sida"]',
        '[DATA.counts.sketch, "strokes"], ["3", "pen colours"], ["1", "page"]',
    ),
    ('title: "Synka och läs in", chip: "Synka"', 'title: "Sync and read", chip: "Sync"'),
    (
        "Plattan synkar till reMarkable Cloud. rmink hämtar anteckningsboken och läser varje streck tillbaka: punkter, penna, färg, lager och ett id som följer strecket.",
        "The tablet syncs to the reMarkable Cloud. rmink fetches the notebook and reads every stroke back: points, pen, colour, layer and an id that stays with the stroke.",
    ),
    (
        '[DATA.counts.sketch, "streck inlästa"], ["1", "lager"], [DATA.counts.sketch, "streck-id:n"]',
        '[DATA.counts.sketch, "strokes read"], ["1", "layer"], [DATA.counts.sketch, "stroke ids"]',
    ),
    ('title: "Gruppera och räkna om", chip: "Gruppera"', 'title: "Group and fit", chip: "Group"'),
    (
        "rmink delar upp skissen i numrerade grupper. Långa streck räknas om till linjer och cirklar med exakta koordinater. Handskrift, pilspetsar och små symboler hålls ihop i en grupp som Claude får läsa av i bilden.",
        "rmink splits the sketch into numbered groups. Long strokes are fitted to lines and circles with exact coordinates. Handwriting, arrowheads and small symbols stay together in a group that Claude reads from the picture.",
    ),
    (
        '[DATA.groups.length, "grupper"], [n("line"), "linjer"], [n("circle"), "cirkel"], [n("mark"), "text och symboler"]',
        '[DATA.groups.length, "groups"], [n("line"), "lines"], [n("circle"), "circle"], [n("mark"), "text and symbols"]',
    ),
    ('title: "Claude tolkar"', 'title: "Claude interprets"'),
    ('"rmink: grupper"', '"rmink: groups"'),
    (
        "Claude ser den numrerade bilden och grupplistan, och avgör vad varje grupp är. Koordinaterna tas från rminks anpassning, så Claude behöver aldrig gissa en position ur bilden. Legenden i hörnet styr vad symbolerna betyder.",
        "Claude sees the numbered picture and the group list, and decides what each group is. The coordinates come from rmink's fitting, so Claude never has to guess a position from the picture. The legend in the corner decides what the symbols mean.",
    ),
    (
        'title: "Ren ritning, revision 1", chip: "Ren ritning"',
        'title: "Clean drawing, revision 1", chip: "Clean drawing"',
    ),
    ('"Altan r1 · sida 1"', '"Altan r1 · page 1"'),
    ('"Ritning r1 · Kommentarer"', '"Ritning r1 · Kommentarer layers"'),
    (
        "rmink rätar upp linjerna, sätter ihop hörnen och ritar med riktiga pennstreck. Ritningen får måttlinjer med pilar, symboler, en förklaringsruta och ett revisionsblock. Den nya anteckningsboken landar på plattan, med originalskissen kvar som sida 2.",
        "rmink straightens the lines, joins the corners and draws with real pen strokes. The drawing gets dimension lines with arrows, symbols, a legend and a title block. The new notebook lands on the tablet, with the original sketch kept as page 2.",
    ),
    ("<b>${r.drawn_px} px ritat</b>", "<b>${r.drawn_px} px drawn</b>"),
    (
        '\'<span class="ok">stämmer</span>\' : "avviker"} med skalan',
        '\'<span class="ok">matches</span>\' : "differs"} with the scale',
    ),
    (
        'row("skala", `<b>${scale} mm per px</b> <span>· räknat ur de skrivna måtten. Avvikande mått flaggas så att Claude kan fråga.</span>`)',
        'row("scale", `<b>${scale} mm per px</b> <span>· worked out from the written measurements. Measurements that disagree are flagged so Claude can ask.</span>`)',
    ),
    (
        'title: "Markera på plattan", chip: "Markera"',
        'title: "Mark up on the tablet", chip: "Mark up"',
    ),
    ('"Lager: Kommentarer"', '"Layer: Kommentarer"'),
    (
        "I lagret Kommentarer ringar du in pelaren i hörnet och skriver “FLYTTA 200?”. Brunnen ska bort, så den kryssas över. Mer än så behövs inte.",
        "On the Kommentarer (comments) layer you ring the post in the corner and write “FLYTTA 200?” (move 200?). The drain should go, so you cross it out. Nothing more is needed.",
    ),
    ('stats([["3", "markeringar"], ["1", "lager"]])', 'stats([["3", "marks"], ["1", "layer"]])'),
    (
        'title: "Bara det nya plockas upp", chip: "Bara det nya"',
        'title: "Only what is new is picked up", chip: "Only new"',
    ),
    ('"rmink: nya streck"', '"rmink: new strokes"'),
    (
        "rmink vet vilka streck det själv skrev i r1 och filtrerar bort dem. Kvar blir bara dina markeringar. Claude kopplar varje markering till ett element: krysset är en ändring, ringen med texten en fråga.",
        "rmink knows which strokes it wrote in r1 and filters them out. Only your marks are left. Claude links each mark to an element: the cross is a change, the ring with the text a question.",
    ),
    ('"egna streck bortfiltrerade"', '"own strokes filtered out"'),
    ('"nya grupper"', '"new groups"'),
    (
        "<b>Kryss över B1</b> <span>· ändring: brunnen stryks</span>",
        "<b>Cross over B1</b> <span>· change: the drain is removed</span>",
    ),
    (
        "<b>Ring kring P3 + “FLYTTA 200?”</b> <span>· fråga: öppen anmärkning 1</span>",
        "<b>Ring around P3 + “FLYTTA 200?”</b> <span>· question: open remark 1</span>",
    ),
    ('"Altan r2 · sida 1"', '"Altan r2 · page 1"'),
    ('"Ritning r2 · Kommentarer"', '"Ritning r2 · Kommentarer layers"'),
    (
        "Brunnen är borta, även ur legenden. Frågan om P3 är anmärkning 1, med en numrerad ring på ritningen och i listan. Ändringsloggen visar vad som hänt mellan revisionerna. Nästa omgång börjar här.",
        "The drain is gone, from the legend too. The question about P3 is remark 1, with a numbered ring on the drawing and in the list. The change log shows what happened between revisions. The next round starts here.",
    ),
    (
        "<b>Renritad från skiss</b> <span>· Förslag</span>",
        "<b>Drawn clean from sketch</b> <span>· Proposal</span>",
    ),
    (
        "<b>Brunn B1 struken, P3 under diskussion</b> <span>· Granskning</span>",
        "<b>Drain B1 removed, P3 under discussion</b> <span>· Review</span>",
    ),
    # Demo 2
    (
        'title: "Utgångsläge: revision 2", chip: "Utgångsläge"',
        'title: "Starting point: revision 2", chip: "Start"',
    ),
    ('"Ritning r2"', '"Ritning r2 layer"'),
    (
        "Ritningen r2 är klar, men bjälklaget saknas. Du frågar Claude om bärlinorna ska gå längs eller tvärs, och ber om båda varianterna att jämföra på plattan.",
        "Drawing r2 is done, but the joists are missing. You ask Claude whether the beams should run along or across, and ask for both variants to compare on the tablet.",
    ),
    (
        'row("fråga", "<b>“Visa bärlina längs och tvärs som två sidor.”</b> <span>· i Claude, med rmink kopplat</span>", "plain")',
        'row("ask", "<b>“Show the beam along and across as two pages.”</b> <span>· in Claude, with rmink connected</span>", "plain")',
    ),
    (
        "<b>4 väggar, 4 pelare, 1 eluttag</b> <span>· anmärkning 1 om P3 är fortfarande öppen</span>",
        "<b>4 walls, 4 posts, 1 outlet</b> <span>· remark 1 about P3 is still open</span>",
    ),
    (
        'title: "Två varianter ur samma modell", chip: "Två varianter"',
        'title: "Two variants from one model", chip: "Two variants"',
    ),
    ('"Altan r3 varianter · sida 1"', '"Altan r3 variants · page 1"'),
    ('"Altan r3 varianter · sida 2"', '"Altan r3 variants · page 2"'),
    ('"Alternativ A"', '"Option A"'),
    ('"Alternativ B"', '"Option B"'),
    (
        "Claude kopierar ritningsmodellen två gånger och lägger till bärlinor på olika sätt. rmink ritar båda. Bara det som skiljer sig från r2 tillkommer på sidorna: linjer, pelare, mått, legend och logg.",
        "Claude copies the drawing model twice and adds beams in different ways. rmink draws both. Only what differs from r2 is added to the pages: lines, a post, a measurement, the legend and the log.",
    ),
    (
        "`<b>1 bärlina längs, mittpelare P5</b> <span>· spann ${mm(V.A.span)}</span>`",
        "`<b>1 beam along, centre post P5</b> <span>· span ${mm(V.A.span)}</span>`",
    ),
    (
        "`<b>2 bärlinor tvärs, inga nya pelare</b> <span>· spann ${mm(V.B.span)}</span>`",
        "`<b>2 beams across, no new posts</b> <span>· span ${mm(V.B.span)}</span>`",
    ),
    (
        'row("ändrat", `<b>${DATA2.A.pro.new.length} och ${DATA2.B.pro.new.length} nya streck</b> <span>· resten av sidorna är identiska med r2</span>`)',
        'row("changed", `<b>${DATA2.A.pro.new.length} and ${DATA2.B.pro.new.length} new strokes</b> <span>· the rest of the pages is identical to r2</span>`)',
    ),
    ('title: "Jämför"', 'title: "Compare"'),
    (
        "Eftersom båda varianterna är data går de att räkna på. Spann och balklängd tas ur modellen med samma skala som måtten, så jämförelsen bygger på det du skrev i skissen.",
        "Since both variants are data, you can measure them. Spans and beam lengths come from the model at the same scale as the measurements, so the comparison rests on what you wrote in the sketch.",
    ),
    ("<th>A · längs</th><th>B · tvärs</th>", "<th>A · along</th><th>B · across</th>"),
    ("<td>Bärlinor</td>", "<td>Beams</td>"),
    ("<td>Nya pelare</td>", "<td>New posts</td>"),
    ("<td>Största spann</td>", "<td>Largest span</td>"),
    ("<td>Balklängd totalt</td>", "<td>Total beam length</td>"),
    ('title: "Välj på plattan", chip: "Välj"', 'title: "Choose on the tablet", chip: "Choose"'),
    (
        "Du bläddrar mellan sidorna, kryssar över A och sätter en bock med “KÖR B” på B. Inga knappar, bara pennan.",
        "You flip between the pages, cross out A and tick B with “KÖR B” (go with B). No buttons, just the pen.",
    ),
    ('stats([["2", "sidor"], ["2", "markeringar"]])', 'stats([["2", "pages"], ["2", "marks"]])'),
    (
        'title: "Valet plockas upp", chip: "Valet"',
        'title: "The choice is picked up", chip: "Choice"',
    ),
    (
        "Som i granskningsrundan filtrerar rmink bort sina egna streck på båda sidorna. Claude läser det som är kvar: ett kryss över hela A och en bock med text på B.",
        "As in the review round, rmink filters out its own strokes on both pages. Claude reads what is left: a cross over all of A and a tick with text on B.",
    ),
    (
        "<b>Kryss över hela sidan</b> <span>· förkasta variant A</span>",
        "<b>Cross over the whole page</b> <span>· reject variant A</span>",
    ),
    (
        "<b>Bock + “KÖR B”</b> <span>· välj variant B</span>",
        "<b>Tick + “KÖR B”</b> <span>· choose variant B</span>",
    ),
    (
        'title: "Revision 3: B gäller", chip: "Revision 3"',
        'title: "Revision 3: B it is", chip: "Revision 3"',
    ),
    ('"förkastad"', '"rejected"'),
    ('"Altan r3 · sida 1"', '"Altan r3 · page 1"'),
    ('"Ritning r3 · Kommentarer"', '"Ritning r3 · Kommentarer layers"'),
    (
        "Variant B blir revision 3 med fasen Beslut. Loggen säger att B valdes och A förkastades, så det går att se varför ritningen ser ut som den gör. A finns kvar i varianthäftet om frågan kommer upp igen.",
        "Variant B becomes revision 3 in the Decision phase. The log says B was chosen and A rejected, so you can see why the drawing looks the way it does. A stays in the variants notebook in case the question comes up again.",
    ),
    (
        "<b>Brunn B1 struken</b> <span>· Granskning</span>",
        "<b>Drain B1 removed</b> <span>· Review</span>",
    ),
    (
        "<b>Variant B vald, A förkastad</b> <span>· Beslut</span>",
        "<b>Variant B chosen, A rejected</b> <span>· Decision</span>",
    ),
    # Demo 3
    ('["r1", "Renritad från skiss", "Förslag"]', '["r1", "Drawn clean from sketch", "Proposal"]'),
    ('["r2", "Brunn B1 struken", "Granskning"]', '["r2", "Drain B1 removed", "Review"]'),
    (
        '["r3", "Variant B vald, A förkastad", "Beslut"]',
        '["r3", "Variant B chosen, A rejected", "Decision"]',
    ),
    ('["r4", "Detalj A vid P3", "Detaljering"]', '["r4", "Detail A at P3", "Detailing"]'),
    (
        '["r5", "Vinkelbeslag i detalj A, typ öppen", "Detaljering"]',
        '["r5", "Angle bracket in detail A, type open", "Detailing"]',
    ),
    (
        'title: "Peka ut ett hörn", chip: "Peka ut"',
        'title: "Point out a corner", chip: "Point out"',
    ),
    ('"Altan r3 · sida 2", "tom"', '"Altan r3 · page 2", "empty"'),
    (
        "På r3 vill du diskutera hur pelaren P3 möter väggarna. Du ringar in hörnet och skriver “DETALJ” bredvid. Sida 2 är tom.",
        "On r3 you want to discuss how post P3 meets the walls. You ring the corner and write “DETALJ” (detail) next to it. Page 2 is empty.",
    ),
    (
        'title: "Nedslaget tolkas", chip: "Tolkas"',
        'title: "The zoom-in is interpreted", chip: "Interpret"',
    ),
    (
        "rmink filtrerar bort sina egna streck och hittar ringen och ordet. Claude ser vilka element ringen omsluter och förstår att det är ett nedslag, inte en ändring.",
        "rmink filters out its own strokes and finds the ring and the word. Claude sees which elements the ring encloses and understands that it asks for a detail view, not a change.",
    ),
    (
        "<b>Ring kring P3</b> <span>· omsluter pelaren P3 och väggändarna V2 och V3</span>",
        "<b>Ring around P3</b> <span>· encloses post P3 and the wall ends V2 and V3</span>",
    ),
    (
        "<b>“DETALJ”</b> <span>· gör en detaljvy av det inringade</span>",
        "<b>“DETALJ”</b> <span>· make a detail view of what is ringed</span>",
    ),
    (
        'title: "Detaljsidan skapas", chip: "Detaljsida"',
        'title: "The detail page is made", chip: "Detail page"',
    ),
    ('"Altan r4 · sida 1", "Ritning r4"', '"Altan r4 · page 1", "Ritning r4 layer"'),
    (
        '"Altan r4 · sida 2", "Detalj A · Kommentarer"',
        '"Altan r4 · page 2", "Detail A · Kommentarer"',
    ),
    ('"Altan r4 · sida 2", "Lager: Kommentarer"', '"Altan r4 · page 2", "Layer: Kommentarer"'),
    ('"Altan r4 · sida 2", "rmink: nya streck"', '"Altan r4 · page 2", "rmink: new strokes"'),
    (
        "Claude bygger detaljen i riktiga millimeter: pelaren 90 × 90 och väggarna 45 mm. rmink ritar den i skala 1:5 på en egen sida. Översikten får en streckad ring med bokstaven A som pekar på detaljen.",
        "Claude builds the detail in real millimetres: the post 90 × 90 and the walls 45 mm. rmink draws it at 1:5 on a page of its own. The overview gets a dashed ring with the letter A pointing to the detail.",
    ),
    (
        'row("skala", `<b>${DATA3.scale}</b> <span>· utsnitt ${DATA3.cut_mm} × ${DATA3.cut_mm} mm runt P3</span>`, "plain")',
        'row("scale", `<b>${DATA3.scale}</b> <span>· a ${DATA3.cut_mm} × ${DATA3.cut_mm} mm cut-out around P3</span>`, "plain")',
    ),
    (
        'row("mått", "<b>Pelare 90, vägg 45</b> <span>· ritade i sin riktiga storlek, inte uppskalade från skissen</span>", "plain")',
        'row("sizes", "<b>Post 90, wall 45</b> <span>· drawn at their real size, not scaled up from the sketch</span>", "plain")',
    ),
    (
        'row("länk", "<b>Ring A på översikten</b> <span>· detalj och översikt delar samma ritningsmodell</span>", "plain")',
        'row("link", "<b>Ring A on the overview</b> <span>· detail and overview share one drawing model</span>", "plain")',
    ),
    (
        'title: "Skissa vidare i detaljen", chip: "Skissa vidare"',
        'title: "Keep sketching in the detail", chip: "Keep sketching"',
    ),
    (
        "I detaljen finns plats för det som inte syns på översikten. Du ritar ett vinkelbeslag i innerhörnet, drar en pil och skriver “VINKELBESLAG?”.",
        "The detail has room for what the overview cannot show. You draw an angle bracket in the inner corner, add an arrow and write “VINKELBESLAG?” (angle bracket?).",
    ),
    (
        'title: "Det nya plockas upp", chip: "Det nya"',
        'title: "What is new is picked up", chip: "New"',
    ),
    (
        "Samma sak som på översikten: rmink känner igen sina egna streck på detaljsidan och lämnar resten åt Claude. Vinkeln blir ett beslag, frågetecknet en öppen fråga.",
        "Same as on the overview: rmink recognises its own strokes on the detail page and leaves the rest to Claude. The L shape becomes a bracket, the question mark an open question.",
    ),
    (
        "<b>L-form i innerhörnet</b> <span>· vinkelbeslag VB1, ritas rent</span>",
        "<b>L shape in the inner corner</b> <span>· angle bracket VB1, drawn clean</span>",
    ),
    (
        "<b>Pil + “VINKELBESLAG?”</b> <span>· fråga: vilket beslag, dimension och skruv</span>",
        "<b>Arrow + “VINKELBESLAG?”</b> <span>· question: which bracket, size and screws</span>",
    ),
    (
        'title: "Revision 5, fas för fas", chip: "Revision 5"',
        'title: "Revision 5, phase by phase", chip: "Revision 5"',
    ),
    ('"Altan r5 · sida 1", "Ritning r5"', '"Altan r5 · page 1", "Ritning r5 layer"'),
    (
        '"Altan r5 · sida 2", "Detalj A · Kommentarer"',
        '"Altan r5 · page 2", "Detail A · Kommentarer"',
    ),
    (
        "Beslaget är inritat i grönt som en ändring, och frågan om typ är anmärkning 1 på detaljsidan. Översiktens logg får en rad. Varje revision har sin fas, så historiken går att läsa från förslag till detaljering.",
        "The bracket is drawn in green as a change, and the question about its type is remark 1 on the detail page. The overview's log gets a line. Every revision has its phase, so the history reads from proposal to detailing.",
    ),
    # Demo 4
    (
        "<b>Väggar</b> <span>· två hörn kom som sammanhängande polylinjer</span>",
        "<b>Walls</b> <span>· two corners came as connected polylines</span>",
    ),
    (
        "<b>Fönster</b> <span>· dubbellinje i övre väggen</span>",
        "<b>Window</b> <span>· double line in the top wall</span>",
    ),
    (
        "<b>Dörr</b> <span>· dörrblad och slagbåge</span>",
        "<b>Door</b> <span>· door leaf and swing</span>",
    ),
    (
        "<b>Mått 3000</b> <span>· måttlinje + tal</span>",
        "<b>Measurement 3000</b> <span>· dimension line + number</span>",
    ),
    ("<b>Mått 2400</b> <span>· lodrätt</span>", "<b>Measurement 2400</b> <span>· vertical</span>"),
    (
        "<b>Text</b> <span>· “FÖRRÅD”, “DÖRR 9X21”, “TAKLUTNING 15°”</span>",
        "<b>Text</b> <span>· “FÖRRÅD” (shed), “DÖRR 9X21” (door), “TAKLUTNING 15°” (roof pitch)</span>",
    ),
    (
        "<b>Småbitar</b> <span>· korsningar i blyertsen, ignoreras</span>",
        "<b>Small bits</b> <span>· where pencil lines cross, ignored</span>",
    ),
    ('title: "Skiss på papper", chip: "Papper"', 'title: "A sketch on paper", chip: "Paper"'),
    (
        'doc: [["Kamera", ""], ["Plattan", "ingen anteckningsbok än"]]',
        'doc: [["Camera", ""], ["Tablet", "no notebook yet"]]',
    ),
    (
        'doc: [["rmink.vercel.app", "Take a photo"], ["Plattan", "ingen anteckningsbok än"]]',
        'doc: [["rmink.vercel.app", "Take a photo"], ["Tablet", "no notebook yet"]]',
    ),
    (
        "På ett möte vid förrådet ritar ni med blyerts på ett vanligt papper: väggar, dörr, fönster, två mått och taklutningen. Plattan ligger kvar hemma.",
        "At a meeting by the shed you draw in pencil on an ordinary sheet of paper: walls, a door, a window, two measurements and the roof pitch. The tablet is at home.",
    ),
    (
        'row("papper", "<b>A4, blyerts</b> <span>· skala ungefär 1:20, fotat lite snett i ojämnt ljus</span>", "plain")',
        'row("paper", "<b>A4, pencil</b> <span>· roughly 1:20, photographed a little skewed in uneven light</span>", "plain")',
    ),
    (
        'title: "Fota i webbappen", chip: "Fota"',
        'title: "Photograph it in the web app", chip: "Photo"',
    ),
    (
        "I rmink på mobilen trycker du på “Take a photo”. Bilden hamnar i fillistan med datum och tid som namn, precis som i dag.",
        "In rmink on the phone you tap “Take a photo”. The picture joins the file list, named by date and time, just as today.",
    ),
    (
        'row("finns", "<b>Kameraknappen</b> <span>· i webbappen sedan 2.1.1</span>", "plain")',
        'row("built", "<b>The camera button</b> <span>· in the web app since 2.1.1</span>", "plain")',
    ),
    ('title: "Bläck ur fotot", chip: "Bläck"', 'title: "Ink from the photo", chip: "Ink"'),
    (
        'doc: [["rmink.vercel.app", "Förhandsvisning"], ["Förhandsvisning", "bläck ur fotot"]]',
        'doc: [["rmink.vercel.app", "Preview"], ["Preview", "ink from the photo"]]',
    ),
    (
        "rminks fotokonvertering hittar blyertsstrecken och gör om dem till pennstreck. Bordet, skuggan och papperskanten blir inte bläck. Det här är rminks riktiga utdata för fotot till vänster.",
        "rmink's photo conversion finds the pencil lines and turns them into pen strokes. The table, the shadow and the paper edge do not become ink. This is rmink's real output for the photo on the left.",
    ),
    ('phone(this, "Konverterar…", { dim: true })', 'phone(this, "Converting…", { dim: true })'),
    (
        'stats([[DATA4.ink.length, "streck"], [DATA4.inkPoints, "punkter"], ["0", "streck från bordet"]])',
        'stats([[DATA4.ink.length, "strokes"], [DATA4.inkPoints, "points"], ["0", "strokes from the table"]])',
    ),
    (
        'row("finns", "<b>Foto till bläck</b> <span>· samma konvertering som för handskrift i dag</span>", "plain")',
        'row("built", "<b>Photo to ink</b> <span>· the same conversion as for handwriting today</span>", "plain")',
    ),
    (
        'title: "Gruppera och tolka", chip: "Tolka"',
        'title: "Group and interpret", chip: "Interpret"',
    ),
    (
        'doc: [["rmink.vercel.app", "Förhandsvisning"], ["Förhandsvisning", "rmink: grupper"]]',
        'doc: [["rmink.vercel.app", "Preview"], ["Preview", "rmink: groups"]]',
    ),
    (
        "Strecken grupperas som för en skiss från plattan. Ett foto ger lite stökigare grupper: hörn som hänger ihop och små bitar där blyertsen korsar sig. Claude sorterar ut vad som är vägg, öppning, mått och text, och hoppar över småbitarna.",
        "The strokes are grouped as for a tablet sketch. A photo gives slightly messier groups: corners that hang together and small bits where pencil lines cross. Claude sorts out walls, openings, measurements and text, and skips the small bits.",
    ),
    (
        'phone(this, "Rita rent · fas 2", { dim: true })',
        'phone(this, "Draw clean · phase 2", { dim: true })',
    ),
    ('title: "Ren ritning", actors: ["rmink"]', 'title: "Clean drawing", actors: ["rmink"]'),
    (
        'doc: [["rmink.vercel.app", "Förhandsvisning"], ["Förråd r1 · sida 1", "Ritning r1 · Kommentarer"]]',
        'doc: [["rmink.vercel.app", "Preview"], ["Förråd r1 · page 1", "Ritning r1 · Kommentarer layers"]]',
    ),
    (
        "Fotot var taget lite snett, men linjerna rätas upp och hörnen sätts ihop. Dörren får sin slagbåge, fönstret sin dubbellinje, och taklutningen följer med som text. Måtten kontrolleras mot varandra som vanligt.",
        "The photo was taken a little skewed, but the lines are straightened and the corners joined. The door gets its swing, the window its double line, and the roof pitch comes along as text. The measurements are checked against each other as usual.",
    ),
    ('title: "På plattan", chip: "Plattan"', 'title: "On the tablet", chip: "Tablet"'),
    (
        'doc: [["rmink.vercel.app", "Skickad"], ["Förråd r1 · sida 1", "Ritning r1 · Kommentarer"]]',
        'doc: [["rmink.vercel.app", "Sent"], ["Förråd r1 · page 1", "Ritning r1 · Kommentarer layers"]]',
    ),
    (
        "Ritningen landar på plattan med fotots bläck som sida 2. Därifrån går det som skisserna från plattan: markera, få nästa revision, prova varianter eller gör ett nedslag.",
        "The drawing lands on the tablet with the photo's ink as page 2. From there it works like a tablet sketch: mark it up, get the next revision, try variants or zoom into a detail.",
    ),
    ('phone(this, "Skickad till reMarkable ✓")', 'phone(this, "Sent to reMarkable ✓")'),
    (
        'row("finns", "<b>Send to reMarkable</b> <span>· i webbappen sedan 2.2.0</span>", "plain")',
        'row("built", "<b>Send to reMarkable</b> <span>· in the web app since 2.2.0</span>", "plain")',
    ),
    (
        'row("nästa", \'<b>Granskningsrunda</b> <span>· <a href="#flode">som i demon överst</a></span>\', "plain")',
        'row("next", \'<b>Review round</b> <span>· <a href="#flode">as in the demo at the top</a></span>\', "plain")',
    ),
    # Demo 5
    ('t(243, 181, 3.4, "REV 5 · DETALJERING")', 't(243, 181, 3.4, "REV 5 · DETAILING")'),
    ("<span>enhet mm · raster 50</span>", "<span>unit mm · grid 50</span>"),
    (
        'title: "Senaste revisionen", chip: "Revisionen"',
        'title: "The latest revision", chip: "Revision"',
    ),
    (
        'doc: [["Altan r5 · sida 1", "Ritning r5"], ["Export", ""]]',
        'doc: [["Altan r5 · page 1", "Ritning r5 layer"], ["Export", ""]]',
    ),
    (
        "Altan r5 ligger på plattan efter granskning, varianter och detaljering. Nu ska den till någon som inte har en reMarkable: en snickare, en granne, en konstruktör.",
        "Altan r5 is on the tablet after review, variants and detailing. Now it needs to reach someone without a reMarkable: a carpenter, a neighbour, an engineer.",
    ),
    ("<span>Välj format</span>", "<span>Choose a format</span>"),
    (
        '<b>SVG</b>dela</div><div class="file"><b>PDF</b>skriv ut</div>',
        '<b>SVG</b>share</div><div class="file"><b>PDF</b>print</div>',
    ),
    (
        'row("r5", "<b>Altan, Detaljering</b> <span>· 4 väggar, 2 bärlinor, 4 pelare, 1 eluttag, detalj A</span>", "plain")',
        'row("r5", "<b>Altan, Detailing</b> <span>· 4 walls, 2 beams, 4 posts, 1 outlet, detail A</span>", "plain")',
    ),
    ('title: "SVG: dela direkt", chip: "SVG"', 'title: "SVG: share right away", chip: "SVG"'),
    (
        'doc: [["Altan r5 · sida 1", "Ritning r5"], ["Webbläsare", "altan-r5.svg"]]',
        'doc: [["Altan r5 · page 1", "Ritning r5 layer"], ["Browser", "altan-r5.svg"]]',
    ),
    (
        "rmink skriver den rena sidan som SVG, samma streck som på plattan och med Paper Pros färger. Den öppnas i alla webbläsare och går att skicka i ett mejl eller en chatt.",
        "rmink writes the clean page as SVG, the same strokes as on the tablet, in Paper Pro's colours. It opens in any browser and can go in an email or a chat.",
    ),
    (
        'stats([[kb(DATA5.svgBytes), "filstorlek"], [DATA5.ov.pro.length, "linjer"]])',
        'stats([[kb(DATA5.svgBytes), "file size"], [DATA5.ov.pro.length, "lines"]])',
    ),
    (
        'row("finns", "<b>rmink draw --svg</b> <span>· eller save_revision med svg_path via MCP</span>", "plain")',
        'row("built", "<b>rmink draw --svg</b> <span>· or save_revision with svg_path over MCP</span>", "plain")',
    ),
    ('title: "PDF: skriv ut i skala", chip: "PDF"', 'title: "PDF: print to scale", chip: "PDF"'),
    (
        'doc: [["Altan r5 · sida 1", "Ritning r5"], ["Förhandsvisning", "Altan r5.pdf"]]',
        'doc: [["Altan r5 · page 1", "Ritning r5 layer"], ["Preview", "Altan r5.pdf"]]',
    ),
    (
        "För utskrift ritas samma modell om i millimeter på ett A4-ark, liggande i skala 1:25, med ram, titelblock och skalstock. Altanens 4800 mm blir 192 mm på papperet.",
        "For printing, the same model is redrawn in millimetres on an A4 sheet, landscape at 1:25, with a border, title block and scale bar. The deck's 4800 mm becomes 192 mm on paper.",
    ),
    (
        'row("skala", "<b>1:25 på A4 liggande</b> <span>· 4800 × 3600 mm blir 192 × 144 mm</span>", "plain")',
        'row("scale", "<b>1:25 on A4 landscape</b> <span>· 4800 × 3600 mm becomes 192 × 144 mm</span>", "plain")',
    ),
    (
        'row("ark", "<b>Ram, titelblock, skalstock</b> <span>· revision, fas och datum från modellen</span>", "plain")',
        'row("sheet", "<b>Border, title block, scale bar</b> <span>· revision, phase and date from the model</span>", "plain")',
    ),
    (
        'row("status", "<b>Nästa steg</b> <span>· arket här är ritat ur modellen för att visa idén</span>")',
        'row("status", "<b>Next step</b> <span>· the sheet here is drawn from the model to show the idea</span>")',
    ),
    ('title: "DXF: öppna i CAD", chip: "DXF"', 'title: "DXF: open in CAD", chip: "DXF"'),
    (
        'doc: [["Altan r5 · sida 1", "Ritning r5"], ["CAD", "altan-r5.dxf"]]',
        'doc: [["Altan r5 · page 1", "Ritning r5 layer"], ["CAD", "altan-r5.dxf"]]',
    ),
    (
        "Konstruktören får en DXF med geometrin i riktiga millimeter, räknad ur de handskrivna måtten och låst till ett raster på 50 mm. Varje kategori blir ett eget lager och pelarna ett block. Prova att slå av och på lagren.",
        "The engineer gets a DXF with the geometry in real millimetres, worked out from the handwritten measurements and locked to a 50 mm grid. Each category is a layer of its own and the posts are a block. Try switching the layers on and off.",
    ),
    (
        'stats([[DATA5.ents.length, "objekt"], [DATA5.layers.length, "lager"], [kb(DATA5.dxfBytes), "filstorlek"]])',
        'stats([[DATA5.ents.length, "objects"], [DATA5.layers.length, "layers"], [kb(DATA5.dxfBytes), "file size"]])',
    ),
    (
        'row("status", "<b>Nästa steg</b> <span>· filen ovan är skriven ur modellen för demon, inte av rmink</span>")',
        'row("status", "<b>Next step</b> <span>· the file above is written from the model for this demo, not by rmink</span>")',
    ),
    (
        'title: "Samma modell, tre format", chip: "Sammanfattning"',
        'title: "One model, three formats", chip: "Summary"',
    ),
    (
        'doc: [["Altan r5 · sida 1", "Ritning r5"], ["Export", "SVG · PDF · DXF"]]',
        'doc: [["Altan r5 · page 1", "Ritning r5 layer"], ["Export", "SVG · PDF · DXF"]]',
    ),
    (
        "Ingen av filerna är en bild av en bild. Alla tre ritas ur ritningsmodellen, så en ändring på plattan i nästa revision kommer med i alla format. Claude kan göra exporten på begäran: “skicka r5 som PDF till snickaren”.",
        "None of the files is a picture of a picture. All three are drawn from the drawing model, so a change on the tablet in the next revision shows up in every format. Claude can export on request: “send r5 as a PDF to the carpenter”.",
    ),
    ('cell("SVG · finns")', 'cell("SVG · built")'),
    ('cell("PDF · nästa steg")', 'cell("PDF · next step")'),
    ('cell("DXF · nästa steg")', 'cell("DXF · next step")'),
    (
        "<tr><th>Format</th><th>För</th><th>Status</th></tr>",
        "<tr><th>Format</th><th>For</th><th>Status</th></tr>",
    ),
    (
        '<tr><td>SVG</td><td>webb, mejl, chatt</td><td class="win">finns</td></tr>',
        '<tr><td>SVG</td><td>web, email, chat</td><td class="win">built</td></tr>',
    ),
    (
        "<tr><td>PDF</td><td>utskrift i skala</td><td>nästa steg</td></tr>",
        "<tr><td>PDF</td><td>printing to scale</td><td>next step</td></tr>",
    ),
    (
        "<tr><td>DXF</td><td>CAD, lager i mm</td><td>nästa steg</td></tr>",
        "<tr><td>DXF</td><td>CAD, layers in mm</td><td>next step</td></tr>",
    ),
    # Scenario cards
    (
        '{ t: "Renritning", st: "built", link: "#flode", d: "Handskiss med mått blir en ren ritning: raka linjer, måttkedjor, versaltext och revisionsblock. Skissen finns kvar som sida 2."',
        '{ t: "Clean drawing", st: "built", link: "#flode", d: "A hand sketch with measurements becomes a clean drawing: straight lines, dimension chains, capital lettering and a title block. The sketch stays as page 2."',
    ),
    (
        '{ t: "Legend styr symbolerna", st: "built", link: "#flode", d: "Skissens egen legend säger vad symbolerna och pilarna betyder. Ritningen får standardsymboler och en ren förklaringsruta."',
        '{ t: "The legend sets the symbols", st: "built", link: "#flode", d: "The sketch\'s own legend says what the symbols and arrows mean. The drawing gets standard symbols and a clean legend box."',
    ),
    (
        '{ t: "Granskningsrunda", st: "built", link: "#flode", d: "Ringa in, kryssa eller skriv på revisionen. Bara de nya strecken läses. Tydliga ändringar görs direkt, frågor blir numrerade anmärkningar."',
        '{ t: "Review round", st: "built", link: "#flode", d: "Ring, cross out or write on the revision. Only the new strokes are read. Clear changes are made straight away, questions become numbered remarks."',
    ),
    (
        '{ t: "Faser och nedslag", st: "later", link: "#nedslag", d: "Varje revision har fas och datum: förslag, granskning, beslut. Ett nedslag blir en detaljvy av ett element på en egen sida, där man skissar vidare."',
        '{ t: "Phases and detail views", st: "later", link: "#nedslag", d: "Every revision has a phase and a date: proposal, review, decision. Zooming in gives a detail view of an element on its own page, where you keep sketching."',
    ),
    (
        '{ t: "Varianter", st: "later", link: "#varianter", d: "Alternativ A och B från samma modell som separata sidor, t.ex. två balkplaceringar. Markera den som gäller på plattan."',
        '{ t: "Variants", st: "later", link: "#varianter", d: "Options A and B from the same model as separate pages, for example two beam layouts. Mark the one that wins on the tablet."',
    ),
    (
        '{ t: "Pappersskiss", st: "partial", link: "#pappersskiss", d: "Ett foto av en pappersskiss går in i samma tolkning, via kameraknappen i webbappen. Den som inte har plattan till hands kan också vara med."',
        '{ t: "Paper sketch", st: "partial", link: "#pappersskiss", d: "A photo of a paper sketch goes into the same interpretation, through the camera button in the web app. People without a tablet at hand can join in too."',
    ),
    (
        '{ t: "Export och delning", st: "partial", link: "#export", d: "Den rena sidan som SVG att dela med andra. PDF och DXF för CAD är nästa steg."',
        '{ t: "Export and sharing", st: "partial", link: "#export", d: "The clean page as SVG to share with others. PDF and DXF for CAD are next steps."',
    ),
    (
        '{ t: "Med och utan färg", st: "built", link: "#flode", d: "Samma ritning på alla plattor. Paper Pro och Move visar kategorierna i färg, rm2 och Paper Pure med linjetyp och tjocklek. Byt platta i demon."',
        '{ t: "With and without colour", st: "built", link: "#flode", d: "The same drawing on every tablet. Paper Pro and Move show the categories in colour, rm2 and Paper Pure by line type and width. Switch tablets in the demo."',
    ),
    (
        '{ built: "fas 1", partial: "delvis", later: "senare" }',
        '{ built: "phase 1", partial: "partly", later: "later" }',
    ),
    (
        '"Se i demon" : "Se konceptanimeringen"',
        '"See it in the demo" : "See the concept animation"',
    ),
    ('<text x="46" y="35">= PELARE</text>', '<text x="46" y="35">= POST</text>'),
    ('<text x="46" y="66">= BRUNN</text>', '<text x="46" y="66">= DRAIN</text>'),
    (
        '<text x="150" y="40">#1 kryss → stryk</text><text x="150" y="58">#2 ring → fråga</text>',
        '<text x="150" y="40">#1 cross → remove</text><text x="150" y="58">#2 ring → question</text>',
    ),
    ('<text x="168" y="30">DETALJ A</text>', '<text x="168" y="30">DETAIL A</text>'),
    # Numbers
    ('toLocaleString("sv-SE")', 'toLocaleString("en-GB")'),
    (
        'const kb = n => (n / 1000).toLocaleString("sv-SE", { maximumFractionDigits: 1 }) + " kB";',
        'const kb = n => (n / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1 }) + " kB";',
    ),
]

# Swedish words that should not survive in visible text (whole words, case-insensitive).
SWEDISH = re.compile(
    r"\b(och|att|med|på|är|som|ett|för|det|till|från|steg|sida|sidor|plattan|ritningen|skiss|nya|bara|"
    r"varianter|mått|vägg|väggar|pelare|fråga|kryss|bock|loggen|finns|senare|delvis|nästa|koncept|bläck|"
    r"ren|nedslag|detalj|dela|platta|du|färg|gråskala|brunn|eluttag|fönster|dörr|stämmer|skala|filstorlek|"
    r"linjer|grupper|streck|punkter|markeringar|tolkas|skickad|förkastad|översikt|beslut|förslag|granskning|"
    r"detaljering|alternativ|lager|mobilen|webbappen|kategorier|ingen|inte|även|också)\b",
    re.I,
)
# Things that are Swedish on purpose: what rmink writes on the drawings and
# the tablet's layer names, and handwriting quoted from the sketches.
ALLOWED = [
    "Ritning r",
    "Kommentarer",
    "FLYTTA 200?",
    "KÖR B",
    "DETALJ",
    "VINKELBESLAG",
    "FÖRRÅD",
    "DÖRR 9X21",
    "TAKLUTNING 15°",
    "ALTAN",
    "Förråd r1",
    "Altan",
    # Element ids the links point at, and DXF layer names.
    "#nedslag",
    "#varianter",
    "PELARE",
]
IDS = {"nedslag", "varianter", "pappersskiss", "flode", "export"}


def visible_text(s: str) -> list[str]:
    body = s[s.index("</style>") :]
    out = re.findall(r">([^<>]+)<", body)
    out += re.findall(r'"((?:[^"\\]|\\.)*)"', body[body.index("<script>") :])
    out += re.findall(r"`((?:[^`\\]|\\.)*)`", body[body.index("<script>") :])
    out += re.findall(r'(?:aria-label|alt)="([^"]+)"', s)
    return out


def main() -> int:
    s = (HERE / "template.html").read_text()
    missing = []
    for sv, en in sorted(PAIRS, key=lambda p: -len(p[0])):
        if sv not in s:
            missing.append(sv)
        s = s.replace(sv, en)
    if missing:
        print("not found in template:", *[m[:80] for m in missing], sep="\n  ")
    left = []
    for t in visible_text(s):
        clean = t
        for a in ALLOWED:
            clean = clean.replace(a, "")
        # Multi-line matches are code between two string literals, not text.
        if t.strip() in IDS or "\n" in t:
            continue
        if re.search(r"[åäöÅÄÖ]", clean) or SWEDISH.search(clean):
            left.append(t.strip()[:120])
    left = [x for x in dict.fromkeys(left) if x]
    if left:
        print("Swedish left:", *left, sep="\n  ")
    (HERE / "template-en.html").write_text(s)
    return 1 if (missing or left) else 0


if __name__ == "__main__":
    sys.exit(main())
