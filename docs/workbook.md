# Arbetsbok: länkad PDF där handstil blir text

Status: släppt i 2.9.0 (modulen `rmink.workbook`, CLI, MCP och webbsidan `/rounds`). Länkar,
koordinater, dolt lager och ett helt varv med Claude är verifierade på en rm2 (2026-10-30).

## Idé

Rundorna för ritningar visade att plattan och rmink kan skicka ett dokument fram och tillbaka.
En arbetsbok använder samma runda för pedagogiska dokument:

1. Claude skriver en arbetsbok om ett ämne: försättsblad med innehållsförteckning, avsnitt med
   en kort förklaring och frågor med linjerade svarsrutor.
2. rmink bygger en PDF i plattans format med klickbara länkar (innehåll → avsnitt, "<< Innehåll"
   tillbaka, "Nästa >>" vidare) och en outline som syns i plattans innehållspanel. Den hamnar
   som *Namn r01* i *rmink/Namn/*.
3. Man skriver svaren för hand i rutorna och låter plattan synka.
4. Nästa varv läser bläcket ruta för ruta. Claude får en bild av varje ruta med nytt bläck och
   skriver av svaret ordagrant (rättar inte). Revision *r02* får svaren som riktig PDF-text i
   rutorna. Den förra revisionen flyttas till *Tidigare*.

Svar som Claude är osäker på får ett "?" i marginalen, och revisionen heter då t.ex.
*Bråk r02 · 1 att kolla*. "?" gäller tolkningen av handstilen, inte om svaret är rätt.
Försättsbladet förklarar vad man gör:

- **Texten stämmer:** sätt en bock (✓) i rutan. Nästa varv tar bort "?" och låter texten vara.
- **Texten är fel:** skriv rättelsen i rutan. Nytt bläck i en besvarad ruta läses som en ändring
  eller ett tillägg till svaret.

## Handstilen efter varvet

Man väljer per varv:

- **Ta bort** (standard): bläcket som blev text försvinner.
- **Behåll**: bläcket flyttas till lagret *Handskrift*, som är dolt. Det går att tända i
  plattans lagerpanel för att jämföra med texten.

Det här gäller i båda lägena:

- Handstil som ett tidigare varv sparade i *Handskrift* ligger kvar där.
- Bläck utanför rutorna (anteckningar i marginalen) ligger kvar som det är. Små prickar från
  tryck på länkar tas bort.
- Bläck i en ruta som Claude inte kunde läsa ligger kvar synligt och läses igen nästa varv.
- Sidor man själv lagt till i dokumentet på plattan följer inte med till nästa revision. Varvets
  logg säger hur många.

## Använda

- **Webb** (`/rounds`, bara för ägaren): kortet *Ny arbetsbok* skapar en arbetsbok. Den syns sedan
  under *Ritningar och arbetsböcker* med *Kör nästa varv* och valet för handstilen.
- **CLI**:
  - `rmink workbook new "Bråk för åk 5" --name Bråk`
  - `rmink workbook round Bråk --ink keep`
- **MCP**: `create_workbook` (Claude skriver JSON:en själv), `read_workbook` (en bild per ruta med
  nytt bläck), `save_workbook_answers`.

## Hur det fungerar

- `workbook/model.py`: `Workbook`, `Section`, `AnswerField`. Ett fälts `rect` är PDF-punkter på
  fältets sida. Layouten beror inte på svaren, så rutorna ligger still mellan revisionerna.
- `workbook/build.py`: layout med pymupdf. Sidan har plattans storlek (rm2: 1404 × 1872 px vid
  226 dpi = 447,3 × 596,4 pt).
- `package/rmdoc.py`: med `pdf=` skrivs ett PDF-dokument (`fileType: "pdf"`, `<id>.pdf`, `redir`
  per sida). En sida utan bläck har ingen `.rm`.
- `workbook/read.py`: läser bläcket per PDF-sida (via `redir`) och sorterar det till rutor efter
  streckets mittpunkt, med 8 pt marginal.
- `workbook/workflow.py`: bygger revisionen och skickar den. Mappar och arkiv delas med
  ritningarna.
- `workbook/agent.py`: Claude via API. Ett verktygsanrop per jobb (`write_workbook`,
  `save_answers`). Ett ogiltigt svar skickas tillbaka med felet.
- Arbetsböcker sparas bredvid ritningarna (fil, Redis eller webbläsaren) under
  `workbook:<namn>`. Det gör att ett varv vet om ett dokument är en ritning eller en arbetsbok.

## Verifierat på rm2 (spike 2026-10-30)

| Fråga | Resultat |
| --- | --- |
| Interna PDF-länkar går att trycka på | Ja, både innehållsförteckningen och tillbaka/vidare |
| Outline i plattans innehållspanel | Ja |
| Koordinater | Scen = (pt − B/2) · 226/72, y = pt · 226/72. Samma som för anteckningsböcker när sidan har plattans format. Kryss i en rutas hörn hamnade exakt rätt. |
| Dolt lager (`visible = False`) | Ja: dolt när dokumentet öppnas och går att tända |
| Text i PDF:en | Syns som text. Plattans sökning söker däremot inte i PDF-text (inte heller "Procent" som fanns från början). Texten går att söka i och kopiera i datorappen och i en exporterad PDF. |

## Begränsningar

- Typsnittet är den inbyggda Helvetica (Latin-1). Pilar, grekiska bokstäver och liknande skrivs
  om till ASCII (`->`, `pi`, `sqrt`). Övriga tecken blir "?".
- Långa förklaringar krymps för att få plats. Claude ombeds hålla dem kring 120 ord per avsnitt.
- Paper Pro och Move har andra sidmått. Layouten följer enhetens profil, men koordinaterna är
  bara verifierade på rm2.
