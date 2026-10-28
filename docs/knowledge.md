# Kunskapsbas för byggritningar – analys och struktur

*Etapp 0, 2026-10-28.*

Detta dokument beskriver kunskapen som behövs för att rmink ska kunna stödja dagligt ritande och avstämning av byggritningar. Det gäller både när en ritning skapas, ändras, ses över och kvalitetsgranskas, och när en lösning från ett tidigare projekt ska återanvändas. Datan ligger i [`knowledge/`](../knowledge) som TOML-filer. Den är ännu inte inkopplad i appen, och avsnitt 6 visar var den ska kopplas in.

Fokus är **småhus, altaner och hantverkare**: trä, gips, plintar och trall, med planer och sektioner i 1:20 och 1:50. Det matchar de skisser som rmink tolkar idag.

## 1. Källor och vad vi får använda

| Källa | Vad den är | Licens | I rmink |
|---|---|---|---|
| **BFS 2024:4–13** | Boverkets nya byggregler. De ersatte BBR och EKS den 1 juli 2025, och de gamla reglerna gick inte att använda efter 1 juli 2026. Energi regleras separat i BFS 2026:9. | Offentliga föreskrifter som är fria att citera | Regel-ID, paragraf, parametervärde och URL. Värdena är kontrollerade mot källtexten (`verified = true`). |
| **PBL 9 kap.** (lovbefriade åtgärder) | Lag. Ändrad 2025-12-01: *friggebod* och *attefallshus* heter nu **komplementbyggnad** och **komplementbostadshus**. | Offentlig | En regel som ställer en fråga. Värdena kommer från kommunala sammanfattningar och är **inte** verifierade mot lagtexten. |
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
| `terms.toml` | Termer och förkortningar SV/EN, med synonymer för handskrift | 139 termer |
| `drawing_standard.toml` | Ritningsslag, skalor, skeden, revision, ritningshuvud, numrering, discipliner, linjer, måttsättning, beteckningar, pappersformat | 9 ritningsslag, 7 skeden, 8 linjetyper |
| `materials.toml` | Varuslag i 11 grupper med klasser, obligatoriska uppgifter, textmall, skraffering och brandklass | 42 varuslag |
| `assemblies.toml` | Typkonstruktioner med lager, krav och granskningsfrågor | 12 byggdelar |
| `rules.toml` | Granskningsregler med källa och paragraf | 43 regler (10 rmink, 24 BFS, 1 PBL, 8 praxis) |
| `markup.toml` | Typer, status, prioritet och CSV-kolumner för anmärkningar | 5 typer, 5 statusar |
| `hatches.toml` | Skrafferingsmönster per material | 12 mönster |

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
| **Symbol** | Norrpil, nivå ▽, sektion, dörr med slagbåge, golvbrunn | `SYMBOLS` (`src/rmink/drawing/symbols.py:26`), 15 st |
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

## 4. Arbetsgång för typiska småhusprojekt

| Projekt | Ritningar som behövs | Skede | Viktigaste granskningspunkter (regel-ID) |
|---|---|---|---|
| **Altan på plint** | Plan 1:50, sektion 1:20, eventuellt detalj räcke 1:5 | Skiss → granskning → bygghandling | `bfs9-skydd-mot-fall`, `bfs9-racke-barn`, `bfs9-plan-dorr-trappa`, `praxis-ntr-markkontakt`, `praxis-frostfritt`, `praxis-infastning-korrosion` |
| **Komplementbyggnad / uthus** | Situationsplan 1:400, plan, sektion och fasad 1:50 | Bygglovs- eller anmälningshandling | `pbl-komplementbyggnad` (yta, nockhöjd, 4,5 m till gräns), `bfs7-avstand-byggnader` (8 m; undantag ≤ 15 m²), `praxis-taklutning` |
| **Tillbyggnad** | Situationsplan, plan, sektion, fasad, konstruktion | Bygglov → bygghandling | `bfs12-tillbyggnad-niva`, `bfs7-byggnadsklass`, `bfs8-dagsljus`, `bfs8-fukt-75rf`, YV1/BJL1 enligt typlistan |
| **Badrum (våtrum)** | Plan 1:20 med brunn och fall, väggutveckling | Bygghandling | `praxis-vatrum-branschregler`, `bfs12-hygienrum`, `bfs9-tappvarmvatten`, IV-V |

## 5. Hur rmink kan använda kunskapen (senare etapper)

Varje punkt anger var i koden den kopplas in.

1. **Bättre tolkning (låg kostnad).** Lägg en sammanfattning av termer, förkortningar, varuslag med klasser och ritningsstandard i Claudes cachade referensblock:
   - `agent._reference()` i `src/rmink/drawing/agent.py:117`
   - `drawing_reference` i `src/rmink/mcp_server.py:238`

   Med det kan Claude normalisera "gips 13" till *Gips typ A 12,5* och "imp 45×145" till *Regel 45×145 NTR AB*. Det kan också fråga efter klass i stället för att gissa, och prompten i `ROUND_PROMPT` (agent.py:42) säger redan att Claude ska fråga när något är oklart.
2. **Verktyget `lookup_knowledge(query)`** i rundans verktygsloop (agent.py:156) och i MCP. Claude hämtar detaljer om ett varuslag, en typkonstruktion eller en regel när det behövs, så att prompten förblir liten.
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

- Varje fil har `version` (datum). Regler från BFS har `checked` (datum) och en URL till grundförfattningen på rinfo.boverket.se. **Ändringsförfattningar som tillkommit efter 2026-10-28 är inte kontrollerade.**
- `pytest tests/test_knowledge_data.py` kontrollerar att ID:n är unika, att alla korsreferenser finns, att BFS-regler har källa och datum, att praxisregler aldrig blir *fel* och att en handskriven synonym bara pekar på ett varuslag.

### Stickprov att kontrollera mot källan

| Regel | Värde | Källa |
|---|---|---|
| `bfs9-racke-barn` | 0,8 m klätterskydd · 100 mm · 50 mm · 110–230 mm | [BFS 2024:9](https://rinfo.boverket.se/BFS2024-9/pdf/BFS2024-9.pdf) 2 kap. 11 § |
| `bfs9-fri-hojd` | 2,00 m | BFS 2024:9 2 kap. 25 § |
| `bfs12-ramp-lutning` | 1:12 | [BFS 2024:12](https://rinfo.boverket.se/BFS2024-12/pdf/BFS2024-12.pdf) 2 kap. 4 § |
| `bfs7-avstand-byggnader` | 8 m; komplementbyggnad ≤ 15 m² undantagen | [BFS 2024:7](https://rinfo.boverket.se/BFS2024-7/pdf/BFS2024-7.pdf) 6 kap. 5 § och 10 § |
| `bfs8-fukt-75rf` | 75 % RF | [BFS 2024:8](https://rinfo.boverket.se/BFS2024-8/pdf/BFS2024-8.pdf) 7 kap. 1 § |

### Att verifiera med användare eller fackperson

- **PBL komplementbyggnad.** Värdena 30 m², nock 4,0 m, 45 m² totalt och 4,5 m till gräns kommer från kommunala sammanfattningar och ska kontrolleras mot lagtexten i 9 kap.
- **Skrafferingar.** Stämmer rmink-konventionen med det hantverkare och konstruktörer förväntar sig?
- **Typkonstruktioner.** Dimensionerna (bärlina 2×45×170, plint c1800 och så vidare) är typexempel. Vilka varianter används oftast?
- **Förkortningar.** Tillverkarnas prefix (GN/GF/GU) varierar. Vilka skriver användarna faktiskt?
- **Synonymer.** Samla handskrivna varianter från riktiga skisser (till exempel `rmink/Test`).
