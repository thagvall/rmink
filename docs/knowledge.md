# Kunskapsbas för byggritningar – analys och struktur

*Etapp 0, 0b (process enligt PBL/PBF och behörighet för el) och 1 (inkopplad i referenstexten med uppslagsverktyg), 2026-10-28.*

Detta dokument beskriver kunskapen som behövs för att rmink ska kunna stödja dagligt ritande och avstämning av byggritningar. Det gäller både när en ritning skapas, ändras, ses över och kvalitetsgranskas, och när en lösning från ett tidigare projekt ska återanvändas. Datan ligger i [`src/rmink/knowledge/data/`](../src/rmink/knowledge/data) som TOML-filer och läses av modulen `rmink.knowledge`. Punkterna 1 och 2 i avsnitt 5 är inkopplade; resten är förslag.

Fokus är **småhus, altaner och hantverkare**: trä, gips, plintar och trall, med planer och sektioner i 1:20 och 1:50. Det matchar de skisser som rmink tolkar idag.

## 1. Källor och vad vi får använda

| Källa | Vad den är | Licens | I rmink |
|---|---|---|---|
| **BFS 2024:4–13** | Boverkets nya byggregler. De ersatte BBR och EKS den 1 juli 2025, och de gamla reglerna gick inte att använda efter 1 juli 2026. Energi regleras separat i BFS 2026:9. | Offentliga föreskrifter som är fria att citera | Regel-ID, paragraf, parametervärde och URL. Värdena är kontrollerade mot källtexten (`verified = true`). |
| **PBL (2010:900) och PBF (2011:338)** | Lov, anmälan, startbesked, kontrollplan och kontrollansvarig. Konsoliderad lydelse t.o.m. SFS 2026:1583 respektive 2026:1722. Sedan 2025-12-01 heter *friggebod* och *attefallshus* **komplementbyggnad** och **komplementbostadshus**. | Offentlig | `process.toml` (beslutsträd, roller, steg) plus 9 regler, alla kontrollerade mot lagtexten på data.riksdagen.se. |
| **Elsäkerhetslag (2016:732)** | Vem som får utföra elinstallationsarbete | Offentlig | Regeln `elsl-behorighet` är kontrollerad. Undantagen för privatpersoner (ELSÄK-FS 2017:2) är **inte** kontrollerade, eftersom föreskriftens PDF leder om till en webbsida. |
| **AMA Hus 24, AMA AF** (Svensk Byggtjänst) | Referensverk som blir bindande först när en kod åberopas i en teknisk beskrivning | Upphovsrätt och licens | Bara ett tomt fält `ama_ref` per varuslag. Den som har licens fyller i via en lokal overlay (avsnitt 6). |
| **CoClass / BSAB** | Klassning av byggdelar och referensbeteckningar | Licens | Inte med ännu. Kan bli ett valfritt kodfält. |
| **Bygghandlingar 90**, **SS-EN ISO 128 / 129 / 5455 / 7200 / 7519** | Hur ritningar redovisas: linjer, mått, skalor, ritningshuvud, beteckningar | Betalda standarder | Bara allmänt kända begrepp med egna ord. Skrafferingarna är märkta *rmink-konvention* och ska alltid förklaras på ritningen. |
| **Bluebeam Revu** | Granskningsverktyg. Markups List har Subject, Status och egna kolumner. Tool Chest har standardiserade markeringar. Studio Sessions används för gemensam granskning. | Proprietärt | Samma *indelning* av anmärkningar (typ, status, prioritet) och en CSV-kolumnlista för export. Ingen kopia av gränssnittet. |

### Huvudfynd: de nya reglerna har få siffror

BFS 2024-serien är **funktionsbaserad**. Flera BBR-värden som hantverkare kan utantill står inte längre i föreskriftstexten. Det gäller till exempel räckeshöjd 1,1 m, trappans steghöjd och vissa dörrbredder. Kontrollerat i BFS 2024:9 och 2024:12:

- Räcken (BFS 2024:9 2 kap. 11 §): skyddet ska ha "sådan höjd att det med hänsyn till ytans avsedda användning och fallhöjden begränsar risken". Det finns **ingen fast höjd**. Där yngre barn kan vistas gäller däremot exakta mått: klätterskydd upp till 0,8 m, spjälavstånd högst 100 mm, högst 50 mm under räcket och inga horisontella öppningar på 110–230 mm.
- Trappor (2 kap. 5–9 §§): "utformade så att personer kan förflytta sig säkert". Den enda siffran är att öppningar mellan plansteg får vara högst 100 mm.
- Tillgänglighet (BFS 2024:12) har få mått: ramp högst 1:12 och hiss med en kortsida på minst 1 100 mm. Rullstolsmåtten 0,70×1,30 m, vändcirkel 1,50 m och fri passage 0,90 m står i BFS 2024:13 2 kap. 1 §, i kapitlet om tomter.

**Konsekvens för appen:** rmink ska skilja mellan tre slags regler:
1. **Krav med siffra**, som 100 mm, 2,00 m fri höjd, 1:12, 8 m och 75 % RF. Bryter ritningen mot ett sådant krav blir anmärkningen ett *fel*.
2. **Funktionskrav**, som "skydd mot fall där risk finns". De blir en *fråga*.
3. **Praxis**, som räcke 1,1 m eller 2h+d ≈ 600–630 mm. De ger bara en *fråga*, med `verified = false`.

`tests/test_knowledge_data.py` ser till att en praxisregel aldrig kan få nivån *fel*.

## 2. Segmentering: sex lager

```
 begrepp (terms) ─┐
                  ▼
 varugrupp → varuslag → produkttyp → kvalitet/klass → redovisning på ritning
   (group)   (material)  (product_types)  (classes)    (label_template + hatch)
                  │                                             │
                  ▼                                             ▼
          typkonstruktion (assembly) ── lagerföljd ──►  ritningsstandard
          YV1, IV1, PL1, ALT1 …                         (drawing_standard)
                  │                                             │
                  └──────────────► regel (rule) ◄───────────────┘
                                      │
                                      ▼
                              anmärkning (markup) → ANMÄRKNINGAR + SVAR
```

| Fil | Innehåll | Omfång |
|---|---|---|
| `terms.toml` | Termer och förkortningar SV/EN, med synonymer för handskrift | 160 termer |
| `drawing_standard.toml` | Ritningsslag, skalor, skeden, revision, ritningshuvud, numrering, discipliner, linjer, måttsättning, beteckningar, pappersformat | 9 ritningsslag, 7 skeden, 8 linjetyper |
| `materials.toml` | Varuslag i 11 grupper med klasser, obligatoriska uppgifter, textmall, skraffering och brandklass | 42 varuslag |
| `assemblies.toml` | Typkonstruktioner med lager, krav och granskningsfrågor | 12 byggdelar |
| `rules.toml` | Granskningsregler med källa och paragraf | 53 regler (10 rmink, 24 BFS, 7 PBL, 2 PBF, 1 ElSL, 9 praxis) |
| `markup.toml` | Typer, status, prioritet och CSV-kolumner för anmärkningar | 5 typer, 5 statusar |
| `hatches.toml` | Skrafferingsmönster per material | 12 mönster |
| `process.toml` | Tillståndsformer, beslutsträd för småhusåtgärder, roller, processteg, handlingar, PBL 8 kap. 4 § kopplat till BFS | 6 tillståndsformer, 9 åtgärder, 7 roller, 5 steg |

### Kvaliteter: varför klassen är det viktiga

Ett varuslag är inte entydigt förrän klassen står. "Regel 45×195" säger inget om bärförmågan, men "Regel 45×195 C24 c600" gör det. Därför har varje varuslag en lista `required`. Om något i listan saknas på ritningen blir det en fråga enligt regeln `rmink-material-klass`. Exempel på hur klasserna är indelade:

| Varugrupp | Klassystem | Exempel |
|---|---|---|
| Konstruktionsvirke | Hållfasthetsklass | C14 · C18 · **C24** · C30 (visuellt T1–T3) |
| Tryckimpregnerat | NTR-klass efter fuktbelastning | **AB** ovan mark · **A** i markkontakt · M i havsvatten |
| Limträ | Hållfasthetsklass | GL28h · **GL30c** · GL32c (h = homogent, c = kombinerat) |
| Gipsskiva | Typ enligt EN 520 | **A** normal · F brand · H fukt · E utvändig |
| OSB | EN 300 | OSB/2 torrt · **OSB/3** fuktigt |
| Betong | Hållfasthet **och** exponering | C25/30 + XC2 (grund) · XF3/XF4 (frost) |
| Armering | Stålsort, ø, delning | B500B ø6 s150 |
| Cellplast | Tryckklass | EPS 80 … EPS 300 · XPS 300 |
| Makadam | Fraktion | 0–32 (bärlager) · 16–32 (kapillärbrytande) |
| Infästning | Korrosionsskydd | elförzinkad inne · varmförzinkad · A2 · A4 nära hav |
| Glas | Brottkaraktär | härdat · laminerat (krävs under 0,6 m i bostad) |

## 3. Hur begreppen syns på ritningen

Ett begrepp kan visas på sex sätt. Varje sätt motsvarar en mekanism i rmink, eller saknas idag:

| Mekanism | Exempel | rmink idag |
|---|---|---|
| **Linjetyp och linjebredd** | Bärande i snitt grov 0,5–0,7, dolt streckat, centrum punktstreckat | `Category.line_type/width` (`src/rmink/drawing/model.py:37`) |
| **Skraffering** | Betong: diagonaler med punkter. Mineralull: våglinje. Trä i snitt: kryss | Saknas. `geometry/hatch.py` kan bara rita enkla scanlines |
| **Text enligt mall** | `Regel 45×195 C24 c600`, `Betong C25/30 XC2` | `Element(kind="text")`, utan struktur |
| **Symbol** | Norrpil, nivå ▽, sektion, dörr med slagbåge, golvbrunn | ✅ 33 symboler i `SYMBOLS` (`src/rmink/drawing/symbols.py`). Betydelse, disciplin, ritningsslag, när den krävs, text vid symbolen och handritade varianter finns i `symbols.toml` |
| **Vinkel** | Taklutning 27°, snedskuret hörn | ✅ `AngleDimension` (båge och gradtal), räknas med `rmink.calc` |
| **Kod som hänvisar** | YV1, D1, A-A, 3/A-50-01 | Saknas |
| **Ritningshuvud** | Projekt, nummer, skala, skede, revision | Bara namn, revision, skede och datum (`src/rmink/drawing/render.py:234`) |

Detaljerat per byggdel. Tabellen visar vad som ska synas i varje ritningsslag och vanlig skala:

| Begrepp | Plan 1:50 | Sektion 1:20 | Detalj 1:5 | Fasad 1:50 |
|---|---|---|---|---|
| Yttervägg YV1 | Grov konturlinje + kod `YV1` | Alla skikt med skraffering, text per skikt | Skikt, ångspärrens skarvar, luftspalt | Panelens riktning och kulör |
| Bärande regel | Ingår i väggen | Kryss i snitt + `45×195 C24 c600` | Kryss eller årsringar, infästning | – |
| Platta på mark | – | Betongmönster + EPS + makadam, nivåer ÖK och UK | Kantbalk, köldbrygga, dränering | Sockel, marklinje |
| Plint | Kvadrat med c-mått | Plint + UK-nivå + makadam | Beslag mot bärlina | Syns under trallen |
| Trall | Riktning med pil + text | Kryss i snitt, spalt | Skruv, spalt mot fasad | Kantbräda |
| Räcke | Tunn linje vid kant | Höjd från färdig trall, spjälavstånd | Stolpens infästning | Spjälor, handledare |
| Trappa | Pil i gångriktningen, antal steg | Steghöjd × stegdjup, ledstång | Vange, plansteg | Syns från sidan |
| Nivå | ▽ + `FG +0,000` | ▽ med nivå vid varje bjälklag | – | Marklinje, nock |
| Brandcellsgräns | Streckad markering + `EI 30` | – | Genomföringar | – |
| Revision | Ändringsmoln + triangel | Samma | Samma | Samma |

**Symbolkatalogen** (`symbols.toml`) har en post per ritad symbol, grupperade så här:
- **Orientering:** norrpil, snitt, nivå, detaljhänvisning, punkt, kryss.
- **Bygg:** dörr, fönster, pelare, plint, trappa med gångriktning, räcke, bult, svets.
- **El:** elcentral, eluttag, dubbeluttag, strömbrytare, armatur, brandvarnare.
- **VVS:** golvbrunn, fallriktning, WC, tvättställ, dusch, radiator.
- **Ventilation:** tilluft och frånluft.
- **Kök:** spis och kylskåp.
- **Mark:** träd.
- **Revision:** revisionsmärke och revisionsmoln.

Varje post anger vad symbolen betyder, vilken text som står vid den (`+0,00`, `A`, `10x21`, `1:50`), hur den brukar se ut handritad och vilka granskningsregler som hör till. Geometrin är rmink:s egen. Elsymbolerna liknar IEC 60617 men kopierar den inte. Därför förklaras varje använd symbol i FÖRKLARINGAR.

## 4. Arbetsgång för typiska småhusprojekt

| Projekt | Ritningar som behövs | Skede | Viktigaste granskningspunkter (regel-ID) |
|---|---|---|---|
| **Altan på plint** | Plan 1:50, sektion 1:20, eventuellt detalj räcke 1:5 | Skiss → granskning → bygghandling | `pbl-altan-mur-plank`, `bfs9-skydd-mot-fall`, `bfs9-racke-barn`, `bfs9-plan-dorr-trappa`, `praxis-ntr-markkontakt`, `praxis-frostfritt`, `praxis-infastning-korrosion` |
| **Komplementbyggnad / uthus** | Situationsplan 1:400, plan, sektion och fasad 1:50 | Bygglovs- eller anmälningshandling | `pbl-komplementbyggnad`, `pbl-narhet-grans` (4,5 m), `pbl-varde`, `bfs7-avstand-byggnader` (8 m; undantag ≤ 15 m²), `praxis-taklutning` |
| **Tillbyggnad** | Situationsplan, plan, sektion, fasad, konstruktion | Bygglov → bygghandling | `pbl-tillbyggnad-30`, `pbl-narhet-grans`, `pbf-anmalan`, `bfs12-tillbyggnad-niva`, `bfs7-byggnadsklass`, `bfs8-dagsljus`, `bfs8-fukt-75rf`, YV1/BJL1 enligt typlistan |
| **Badrum (våtrum)** | Plan 1:20 med brunn och fall, väggutveckling | Bygghandling | `praxis-vatrum-branschregler`, `bfs12-hygienrum`, `bfs9-tappvarmvatten`, IV-V, `pbf-anmalan` (VA-installation), `elsl-behorighet` |

### 4b. Vilken prövning krävs? (`process.toml`)

Lagtexten ger en snabb första sortering för varje småhusåtgärd. rmink vet inte om tomten ligger inom detaljplan, så svaret blir alltid en **fråga** och aldrig ett fel.

| Åtgärd | Utgångsläge | Lovfri när | Lovplikten kommer tillbaka när |
|---|---|---|---|
| Komplementbyggnad / komplementbostadshus | Bygglov | Inom plan: ≤ 30,0 m² BYA, nock ≤ 4,0 m, ≤ 45,0 m² totalt. Utanför plan: 50,0 m², 4,5 m och 65,0 m² (PBL 9:4–5) | < 4,5 m till gräns utan skriftligt grannmedgivande (9:34–35), q-märkt eller värdefullt (9:37) |
| Tillbyggnad av bostadshus | Bygglov | ≤ 30,0 m² bruttoarea eller öppenarea sammanlagt, inte över taknocken (9:10) | Samma som ovan. Väsentlig ändring av bärande delar kräver ändå **anmälan** (PBF 6:1) |
| Altan, mur, plank | Lovfri | – | Inom plan: > 1,8 m över mark inom 3,6 m från byggnad, eller > 1,2 m längre bort (9:19) |
| Bärande ändring, eldstad, ventilation, VA | **Anmälan** | – | – (PBF 6:1) |
| Ytterligare bostad i enbostadshus | Bygglov | Alltid, utom komplementbostadshus (9:17) | Totalförsvarsområde, värdefullt (9:36–37) |
| Solceller | Lovfri | ≤ 11 kW (9:17 a) | Värdefullt område (9:37) |
| Elinstallation | – | – | Får bara utföras av auktoriserad elinstallatör eller via ett elinstallationsföretags egenkontrollprogram (ElSL 27 §) |

**Processen** för en lov- eller anmälningspliktig åtgärd är: ansökan eller anmälan → tekniskt samråd → **startbesked** → utförande med kontroller → **slutbesked**. Varje steg har en motsvarighet i rmink:
- Skede *Bygglovshandling*: ritningshuvudet behöver fastighetsbeteckning och byggherre (PBL 9:86).
- Skede *Bygghandling*: först efter startbesked.
- Ändringar under bygget blir nya revisionsvarv, och SVAR-raderna dokumenterar besluten. Det ger underlag för ÄTA.
- Skede *Relationshandling*: inför slutbesked.

En **kontrollansvarig** behövs inte för anmälan, komplementbyggnad, mur, plank eller altan, eller små ändringar av småhus (PBF 7:5). Kontrollplanens innehåll (PBL 10:6) kan genereras från de regler som träffar ritningen.

**Kommande ändringar:** drygt 30 bestämmelser i PBL och PBF har nya lydelser som börjar gälla 2027-01-01, bland annat om kontrollplan och den nya rollen **byggbedömare** (SFS 2026:712). PBF 6 kap. 3 § upphör 2027-12-01. `process.toml` och lagreglerna behöver kontrolleras igen efter de datumen.

### Varianter och alternativsidan

`assemblies.toml` har varianter (`[[variant]]`) av de typkonstruktioner där valet är vanligast:

| Typ | Varianter |
|---|---|
| PL1 platta på mark | A standard 300 EPS · B lågenergi 400 EPS · C förstärkt 150 betong · D XPS · E skumglas |
| YV1 yttervägg | A 195+45 · B 220+70 · C utvändig isolering · D PIR invändigt |
| ALT1 altan | A tryckimpregnerad · B värmebehandlad · C lärk · D komposit |

Varje variant har:
- lager i samma format som typkonstruktionen
- när den passar, för- och nackdelar med egna ord
- en kostnadsnivå (låg, medel eller hög), relativt de andra och utan priser
- `u_kind`, så att ett ungefärligt U-värde kan räknas ur materialens λ

Tjocklek, vikt per m² och U-värde räknas med `knowledge.variant_facts` och `calc.u_value`. U-värdet räknas med λ-värdesmetoden, där reglar och isolering utgör en zon och allt utanför luftspalten utelämnas. Köldbryggor vid anslutningar räknas inte, och för platta på mark inte heller markens isolerande verkan. Värdet är alltså en jämförelse mellan alternativen, inte en energiberäkning.

## 5. Hur rmink kan använda kunskapen (senare etapper)

Varje punkt anger var i koden den kopplas in.

1. **✅ Inkopplad. Bättre tolkning (låg kostnad).** Lägg en sammanfattning av termer, förkortningar, varuslag med klasser och ritningsstandard i Claudes cachade referensblock:
   - `agent._reference()` i `src/rmink/drawing/agent.py:117`
   - `drawing_reference` i `src/rmink/mcp_server.py:238`

   Med det kan Claude normalisera "gips 13" till *Gips typ A 12,5* och "imp 45×145" till *Regel 45×145 NTR AB*. Det kan också fråga efter klass i stället för att gissa, och prompten i `ROUND_PROMPT` (agent.py:42) säger redan att Claude ska fråga när något är oklart.
2. **✅ Inkopplad. Verktyget `lookup_knowledge(query)`** i rundans verktygsloop (agent.py:156) och i MCP. Claude hämtar detaljer om ett varuslag, en typkonstruktion eller en regel när det behövs, så att prompten förblir liten.
3. **Modellfält** i `Drawing` (`src/rmink/drawing/model.py:131`):
   - `scale` och `title_block` (fälten i `drawing_standard.toml`)
   - `drawing_type`
   - `Element.material` och `Element.assembly`
   - `Annotation.type`, `Annotation.rule` och `Annotation.priority`

   Gamla `phase`-värden mappas via `[phase_mapping]`.
4. **Granskare `check_drawing()`.** Den kör reglerna av typerna `completeness`, `attribute` och `geometric` deterministiskt mot `Drawing`. För geometriska regler används skalan från `check_dimensions` (`src/rmink/drawing/workflow.py:211`). Resultatet blir `Annotation`, med regel-ID i texten, och hamnar i det befintliga flödet ANMÄRKNINGAR/SVAR. Reglerna av typen `manual` blir en checklista till Claude.
5. **Skraffering och förklaringar.** Bygg ut `geometry/hatch.py` med vinkel och mönster (kors, punkt, våg, ådring) och låt `src/rmink/drawing/render.py` fylla slutna element som har `material`. FÖRKLARINGAR visar då mönsterrutan och klassen.
6. **Typkonstruktioner som mallar.** När Claude känner igen en yttervägg föreslår det `YV1` och visar lagren. Användaren svarar på SVAR-raden ("YV1 ok" eller "byt till 45×170"). Så återanvänds lösningar mellan projekt.
7. **Export i Bluebeam-stil.** `rmink export --markups out.csv` med kolumnerna i `markup.toml [csv]`. Anmärkningarna kan då läsas in i ett granskningsverktyg eller i Excel.
8. **Skill.** Generera `skills/rmink/references/*.md` från TOML-filerna, så att Claude via MCP har samma kunskap utan att den underhålls på två ställen.
9. **Overlay.** `~/.config/rmink/knowledge/*.toml` läses ovanpå de inbyggda filerna. Den som har licens kan lägga in AMA-text, och ett företag kan lägga in egna typkonstruktioner och förkortningar. Inget av det skickas till repot.

Ordningen ovan går från liten insats och stor nytta till större insats. Punkt 1 och 2 kräver ingen ändring av ritningsmodellen.

## 6. Underhåll

- Varje fil har `version` (datum). Regler från BFS har `checked` (datum) och en URL till grundförfattningen på rinfo.boverket.se. **Ändringsförfattningar som tillkommit efter 2026-10-28 är inte kontrollerade.** Lagregler (PBL, PBF, ElSL) länkar till den konsoliderade texten på data.riksdagen.se.
- `pytest tests/test_knowledge_data.py` kontrollerar:
  - att ID:n är unika och att alla korsreferenser finns
  - att BFS- och lagregler har källa, länk och datum
  - att praxisregler aldrig blir *fel*
  - att en handskriven synonym bara pekar på ett varuslag
  - att åtgärderna i `process.toml` leder till kända tillståndsformer och regler

### Stickprov att kontrollera mot källan

| Regel | Värde | Källa |
|---|---|---|
| `bfs9-racke-barn` | 0,8 m klätterskydd · 100 mm · 50 mm · 110–230 mm | [BFS 2024:9](https://rinfo.boverket.se/BFS2024-9/pdf/BFS2024-9.pdf) 2 kap. 11 § |
| `bfs9-fri-hojd` | 2,00 m | BFS 2024:9 2 kap. 25 § |
| `bfs12-ramp-lutning` | 1:12 | [BFS 2024:12](https://rinfo.boverket.se/BFS2024-12/pdf/BFS2024-12.pdf) 2 kap. 4 § |
| `bfs7-avstand-byggnader` | 8 m; komplementbyggnad ≤ 15 m² undantagen | [BFS 2024:7](https://rinfo.boverket.se/BFS2024-7/pdf/BFS2024-7.pdf) 6 kap. 5 § och 10 § |
| `bfs8-fukt-75rf` | 75 % RF | [BFS 2024:8](https://rinfo.boverket.se/BFS2024-8/pdf/BFS2024-8.pdf) 7 kap. 1 § |
| `pbl-altan-mur-plank` | 1,8 m inom 3,6 m · 1,2 m längre bort | [PBL](https://data.riksdagen.se/dokument/sfs-2010-900.text) 9 kap. 19 § |
| `pbl-tillbyggnad-30` | 30,0 m², inte över nock | PBL 9 kap. 10 § |
| `pbf-anmalan` | Rivning > 50,0 m², bärande, brand, eldstad/ventilation, VA | [PBF](https://data.riksdagen.se/dokument/sfs-2011-338.text) 6 kap. 1 § |
| `elsl-behorighet` | Auktoriserad elinstallatör eller egenkontrollprogram | [ElSL](https://data.riksdagen.se/dokument/sfs-2016-732.text) 4 §, 27 § |

### Att verifiera med användare eller fackperson

- **Elarbeten som privatpersoner får göra själva.** Exemplet "byta uttag eller strömbrytare mot likvärdig, högst 16 A och 400 V" kommer från sekundära källor. Det behöver kontrolleras mot Elsäkerhetsverkets gällande föreskrift.
- **Lagändringar 2027.** Kontrollera PBL 10 kap. och PBF 7 kap. igen efter 2027-01-01.
- **Skrafferingar.** Stämmer rmink-konventionen med det hantverkare och konstruktörer förväntar sig?
- **Typkonstruktioner.** Dimensionerna (bärlina 2×45×170, plint c1800 och så vidare) är typexempel. Vilka varianter används oftast?
- **Förkortningar.** Tillverkarnas prefix (GN/GF/GU) varierar. Vilka skriver användarna faktiskt?
- **Synonymer.** Samla handskrivna varianter från riktiga skisser (till exempel `rmink/Test`).
