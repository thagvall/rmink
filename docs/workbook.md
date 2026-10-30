# Arbetsbok: länkad PDF där handstil blir text

Status: släppt i 2.9.0, facit och resultat i 2.10.0, flerval i 2.11.0, grupper (rmink skola) i 2.12.0 (modulen `rmink.workbook`, CLI, MCP och webbsidan `/rounds`). Länkar,
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

## Facit och resultat

Claude skriver ett facit för varje fråga: det väntade svaret med det viktigaste steget, och hur
många poäng frågan ger (oftast 1). Facit ritas under rutan i rminks enstreckstypsnitt, i lagret
*Facit*, som är dolt. Plattan kan dölja lager men inte PDF-text, och därför är facit bläck och
inte text. Under rutan står "Facit" i ljusgrått när lagret finns.

Man väljer läge när arbetsboken skapas:

- **Övning** (standard): facitlagret finns redan i r01. Tänd det för att jämföra själv.
- **Prov**: r01 har inget facit. Facit kommer i den första rättade revisionen.

I varvet rättar Claude varje svar mot facit: *rätt*, *delvis rätt* eller *fel*, med poäng och en
kort kommentar när svaret inte är rätt. Likvärdiga svar räknas som rätt, till exempel 2/4 för
1/2. Rätt metod med ett räknefel ger delvis rätt. Betyget står i rutans övre högra hörn. En sida **Resultat** sist i dokumentet visar poängen
totalt och per fråga, och varje rad länkar till frågan. Resultatsidan finns i innehållsförteckningen
och i plattans innehållspanel, och revisionen heter t.ex. *Bråk r02 · 3 av 4 p*.

Rättas ett svar om (en rättelse eller en bock) rättas det igen. Arbetsböcker utan facit, som de
från 2.9.0, fungerar som förut utan rättning.

## Flerval

En fråga kan också vara flerval, med alternativen A, B, C… och en ruta per alternativ. Claude
blandar in flerval där det passar. Frågan säger vilken typ den är:

- **Välj ett:** exakt ett alternativ är rätt.
- **Välj alla som stämmer:** ett eller flera alternativ är rätt.

Kryssa i rutan för att välja ett alternativ. Har du ångrat dig fyller du i rutan helt eller drar
ett streck genom raden. Försättsbladet förklarar det.

**Läsning.** rmink läser kryssen själv, så det kostar inget och går fort:
- Bläck i en ruta är ett kryss.
- Täcker bläcket minst halva rutan är rutan ifylld, alltså ångrad.
- Ett streck över minst halva raden ångrar raden.

Allt annat skickas till Claude som en bild av frågan, till exempel en ring runt texten eller en
ruta som är fylld till 30–50 %. Ett varv med bara tydliga kryss gör inget anrop alls.

**Poäng.** Claude skriver vilka alternativ som är rätta och en mening om varför varje alternativ
är rätt eller fel.
- *Välj ett:* rätt alternativ ger frågans poäng.
- *Välj alla som stämmer:* varje rätt kryss ger +1 och varje fel kryss −1, aldrig under 0, skalat
  till frågans poäng. Är A och C rätt (2 p) ger A, C och D 1 p.

**Försök.** I **övningsläget** får ett fel svar en ledtråd i nästa revision, till exempel
"Försök 2 av 3. Du valde A. A: En tredjedel är mindre än en halv.". Ledtråden förklarar varför det
man valde är fel, men säger inte vad som är rätt. Rutorna är tomma igen för ett nytt försök, och
man har högst tre försök. Facit kommer i lagret *Facit* när frågan är rätt eller efter sista
försöket: en ring runt varje rätt ruta och förklaringen. I **provläget** låses frågan när den är
rättad, och facit kommer direkt. Bläck på en låst fråga ligger kvar som en anteckning.

**Resultat.** Resultatsidan visar *Första försöket: x av y poäng* bredvid slutpoängen och, per
fråga, hur många försök det tog.

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

## rmink skola: grupper

Arbetsböcker för skolan samlas i grupper efter område. Katalogen finns i
`src/rmink/workbook/data/skola.toml` (modulen `rmink.workbook.catalog`):

- **Plus och minus:** talkamrater, ental/tiotal/hundratal, huvudräkning över tiotalet, uppställning
  med minnessiffra, subtraktion med växling, pröva och uppskatta, textuppgifter, decimaltal,
  negativa tal.
- **Bråk och division:** division som delning, division med rest, kort division, bråk som del av en
  helhet, bråk av ett antal, bråk som division, förlänga och förkorta, jämföra bråk, blandad form,
  addera och subtrahera bråk, multiplicera och dividera bråk, bråk–decimaltal–procent.

Varje moment har en beskrivning för Claude (vad som ska övas, i vilken ordning och vilka typiska fel
uppgifterna ska fånga) och de årskurser det passar. Man väljer grupp, moment (eller *blanda alla*)
och årskurs. Önskemål i fritext läggs till. En arbetsbok i en grupp hamnar i
`rmink/Skola/<grupp>/<namn>/`:

    rmink/
      Skola/
        Bråk och division/
          Förkorta åk 5/
            Förkorta åk 5 r02 · 4 av 5 p
            Tidigare/

En befintlig arbetsbok flyttas in i en grupp med `rmink workbook move <namn> --group <grupp>`, eller
med *Flytta till grupp…* på arbetsbokens kort på `/rounds` om den är sparad i webbläsaren.
Mappen flyttas med alla revisioner och *Tidigare*, och nästa varv fortsätter där.

Nya grupper (gånger, geometri, svenska …) läggs till i TOML-filen utan kodändring. Arbetsböcker
utan grupp fungerar som förut i `rmink/<namn>/`.

## Använda

- **Webb** (`/rounds`, bara för ägaren): kortet *Ny arbetsbok* skapar en arbetsbok. Den syns sedan
  under *Ritningar och arbetsböcker* med *Kör nästa varv* och valet för handstilen.
- **CLI**:
  - `rmink workbook new "Bråk för åk 5" --name Bråk --mode test`
  - `rmink workbook new --group brak-division --topic-id forlanga-forkorta --grade 5`
  - `rmink workbook catalog` listar grupper och moment
  - `rmink workbook round Bråk --ink keep`
- **MCP**: `list_school_topics`, `create_workbook` (Claude skriver JSON:en själv, valfri `group`), `read_workbook` (en bild per ruta med
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
