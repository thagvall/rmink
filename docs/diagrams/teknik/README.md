# Teknik: hur rmink och kunskapsbasen är byggda

Här finns nitton tekniska diagram över hur rmink fungerar och vad kunskapsbasen för byggritningar innehåller. Verksamhetens bild av processerna, med roller och system, finns i [../verksamhet](../verksamhet/README.md). Varje diagram finns som `.drawio`, som går att öppna och redigera i [draw.io](https://www.drawio.com), och som `.svg` för att visa.

Diagrammen **byggs ur koden**:
- **Kunskapsbasen:** TOML-filerna i `src/rmink/knowledge/data/`.
- **Symboler och skrafferingar:** ritas med rmink:s egen kod, så de ser ut som på plattan.
- **Ritningsmodellen:** fälten läses ur pydantic-modellerna.
- **Gränssnitten:** CLI-kommandon, MCP-verktyg och webbroutes listas ur appen.

Bygg om dem efter en ändring:

```
python docs/diagrams/build.py --export
```

Kommandot bygger både teknik/ och verksamhet/. `--export` kräver draw.io desktop, med kommandot `drawio` eller appen i /Applications. Utan `--export` skrivs bara `.drawio`-filerna. `tests/test_diagrams.py` kontrollerar att varje material, regel, symbol, konstruktion, variant, skraffering, begrepp, åtgärd och ritningstyp finns med i diagrammen. Det testet behöver inte draw.io.

En ändring som görs för hand i draw.io skrivs över nästa gång diagrammen byggs. Ändra därför i `build.py`, eller i datan, i stället.

## App och funktion

### 1. Systemöversikt
Användare och enheter, gränssnitten (webbapp, MCP, CLI, statiska sidor), rmink-kärnans delar och de externa systemen: reMarkable Cloud via rmapi, Anthropic, Vercel, Blob, PyPI och Stripe. Visar också var data lagras.

![Systemöversikt](01-systemoversikt.svg)

### 2. Bild eller PDF → anteckningsbok
Konverteringens steg 0–9, från inställningar till `.rmdoc`, med enhetsprofilerna.

![Bild till anteckningsbok](02-bild-till-anteckningsbok.svg)

### 3. Skiss → ritning: ett varv
Simbanor för platta, moln, rmink, Claude och lagring, från skiss till markerad revision och nästa varv.

![Skiss till ritning](03-skiss-till-ritning.svg)

### 4. Rundans verktygsloop
`run_round`, Claudes verktyg och reglerna i prompten. Samma flöde finns via MCP.

![Rundans verktyg](04-rundans-verktyg.svg)

### 5. Revisioner, mappar och namn
Mappen `rmink/` på plattan, livscykeln från r00 skiss via r01 · frågor till r02, och reglerna för namn och flytt.

![Revisioner och mappar](05-revisioner-och-mappar.svg)

### 6. Moln, cache och gränser
Varför reMarkable Cloud kräver en cache, var den ligger (lokalt och i Vercel Blob), kall och varm körning, uppmätta gränser och skydd.

![Moln och cache](06-moln-cache-och-granser.svg)

### 7. Release och drift
Från ändring på main via tagg, PyPI och godkännande till höjningen på Vercel. Visar också miljövariablerna.

![Release](07-release-och-drift.svg)

### 8. Ritningsmodellen
Klassdiagram över `Drawing` och dess delar, linjekategorierna och ritningshuvudet.

![Ritningsmodellen](08-ritningsmodellen.svg)

## Kunskapsbasen

### 9. Struktur
De nio TOML-filerna med tabeller och fält, korsreferenserna mellan dem och sökordningen i `lookup_knowledge`.

![Kunskapsbasens struktur](09-kunskapsbasens-struktur.svg)

### 10. Lagar, föreskrifter och granskningsregler
PBL, PBF, ElSL och ELSÄK-FS; PBL 8 kap. 4 § mot BFS 2024; alla regler per källa med lagrum, grad och meddelande.

![Lagar och regler](10-lagar-och-regler.svg)

### 11. Lov, anmälan och byggprocessen
Vilken prövning en åtgärd kräver, med undantag; processens steg från ansökan till slutbesked; roller och dokument.

![Lov och process](11-lov-och-process.svg)

### 12. Ritstandard
Ritningstyper och skalor, skeden, ritningshuvudet, discipliner, linjetyper, beteckningar, måttsättning, pappersformat och revisioner. Visar också vad rmink ritar i dag.

![Ritstandard](12-ritstandard.svg)

### 13. Material
Alla material per grupp, med klasser, vad ritningen måste ange, brandklass, ρ, λ, skraffering och regler.

![Material](13-material.svg)

### 14. Konstruktioner
Varje byggdel som skiktsnitt med rmink:s skrafferingar, skiktlista, krav, granskningspunkter och regler.

![Konstruktioner](14-konstruktioner.svg)

### 15. Produktalternativ
Varianterna för platta på mark, yttervägg och altan, med snitt, tjocklek, vikt, U-värde, kostnad samt för- och nackdelar. Visar också vägen från "alternativ?" till vald lösning.

![Produktalternativ](15-produktalternativ.svg)

### 16. Symboler
Alla symboler per disciplin, ritade som på plattan, med etikett, betydelse, handskrivna varianter och regler.

![Symboler](16-symboler.svg)

### 17. Skrafferingar
Mönstren som riktiga prover, med vilka material som använder dem.

![Skrafferingar](17-skrafferingar.svg)

### 18. Granskning och markeringar
Markeringstyper, status mot `Annotation.status`, prioritet och CSV-export, och hur det hänger ihop med anmärkningar och SVAR-rader.

![Granskning](18-granskning-och-markeringar.svg)

### 19. Begrepp och förkortningar
Alla begrepp per kategori, med förkortning, hänvisning och betydelse.

![Begrepp](19-begrepp.svg)
