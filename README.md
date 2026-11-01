# KiCad BOM-tjek

Lokalt værktøj der læser et KiCad-projekt (KiCad 6–10), laver BOM'en, kontrollerer footprints,
sammenligner med en grosist-BOM og finder priser og alternativer.

## Start

**Uden Python:** hent `KiCadBOM.exe` under [Releases](https://github.com/Kaelor9/kicad-bomtool/releases)
og dobbeltklik. Programmet åbner i sit eget vindue og opdaterer sig selv (se nedenfor).

**Med Python 3.10+** – ingen andre pakker er nødvendige:

```
start.bat            (Windows – dobbeltklik)
python -m bomtool    (alle platforme)
```

Programmet åbner i sit eget vindue (Edge WebView2, følger med Windows 10/11). Med `--browser` bruges
browseren i stedet. Den indbyggede server lytter kun lokalt (127.0.0.1).

Valgfrit: `pip install pypdf openpyxl xlrd` – bedre læsning af datablade, hurtigere .xlsx og gamle binære .xls-filer.
(.xlsx virker også uden; Mousers ".xls" er ofte HTML og virker altid.)

## Hvad den gør

Programmet er et **kontrolprogram**. Resultatet vises som komponenttabellen til venstre og et
kontrolpanel til højre for den valgte komponent (pil op/ned skifter). Hver linje kontrolleres i tre trin,
som også står som kolonner i tabellen:

| Trin | Spørgsmål | Panelet viser |
|---|---|---|
| 1 Footprint | Passer komponenten i KiCad med det valgte footprint? | footprintet med målestreger, pakke, ben ↔ pads, KiCad-bibliotek/producent-CAD |
| 2 Datablad | Passer footprintet med databladet? | databladets mål-tabel, land pattern og pinout side om side med footprintet, og selve tegningen |
| 3 Indkøb | Kan den købes som valgt? | grosist-BOM'en, priser og lager pr. sælger |

Er en komponent ikke på lager, udgået eller ikke fundet, søges der automatisk efter **alternativer**
(samme værdi/pakke, eller samme pakke og pinout for IC'er). Vælger du et alternativ, bruges det i
indkøbslisten og kurven – KiCad-projektet ændres ikke.

1. **Læser projektet** – zip-fil eller hele mappen. Følger hierarkiske ark (også genbrugte ark),
   multi-unit symboler, DNP, "Exclude from BOM", og springer monteringshuller/logoer over.
2. **Finder MPN, producent, datablad** – genkender felter som `MPN`, `Mfr. No`, `Manufacturer_Part_Number`,
   `Mouser`, `DigiKey`, `LCSC` osv. uanset stavemåde. Mangler MPN, prøves værdien, grosist-numre og
   (med API) et forslag til den billigste passive komponent der opfylder værdi + pakke + specs.
3. **Footprint-kontrol** – for hver BOM-linje:
   - footprint-navnet mod komponentens rigtige pakke (fra grosist-API, BOM-filen eller MPN-mønstre som GRM188 = 0603)
   - navnet mod footprintets egen geometri (antal pads, pitch)
   - chip-komponenter: om pads fysisk rammer komponentens terminaler (fanger fx 0402-pads til en 0603)
   - pad-for-pad mod producentens CAD-fil (upload `.kicad_mod` navngivet efter MPN eller footprint),
     ellers mod KiCad-biblioteket – inkl. rotation, spejling (pin 1 byttet) og enkeltpads der er flyttet
   - symbolets ben mod footprintets pads (ben der ikke bliver forbundet)
   - **databladet**: PDF'en hentes og læses; pakken på bestillingslinjen for dit MPN
     (fx "NE555DR … SOIC-8") sammenlignes med footprintet
   - visuelt overlay: dine pads (orange) oven på referencen (blå stiplet)
   - footprintets mål ved siden af databladets pakketabel (pitch, benbredde, benspænd, fod, termisk pad,
     krop), anbefalet land pattern og pinout symbol ↔ datablad – og databladet åbnet på tegningssiden
4. **Grosist-BOM** – CSV/TSV/XLSX/XLS/HTML fra Mouser, DigiKey, LCSC, Farnell, TME … uden skabelon.
   Kolonner findes automatisk (også når der er titelrækker over), og linjer matches på MPN, grosist-nr.,
   reference (R1, C3) eller værdi + pakke. Viser manglende, forkerte antal og ekstra varer i kurven.
5. **Priser** – med API-nøgler hentes prisknæk, lager, MOQ og pakning. Programmet køber den billigste
   mængde (ofte er 100 stk. billigere end 60) og foreslår "køb flere" når det koster næsten ingenting.
   Indkøbslister kan eksporteres som CSV, som Mouser/DigiKeys BOM-værktøjer kan læse.
6. **Alternativer** – passive: parametrisk søgning (samme værdi og pakke, mindst lige god spænding,
   tolerance, dielektrikum). Øvrige: grosisternes egne erstatninger, markeret "Passer / Passer ikke" på
   dit footprint (pakke og antal ben), "Samme / Anden pinout" ud fra kandidatens datablad og om de er
   fra samme grosist.
7. **Læg i kurv** – DigiKey: åbner digikey.com med varerne i kurven (FastAdd, ingen nøgle nødvendig).
   Mouser: opretter en kurv via Mousers Cart API og viser Mousers egen pris.
8. **Historik** – hver analyse gemmes. Fanen "Ændringer" viser hvad der er tilføjet, fjernet og ændret
   (værdi, footprint, MPN) siden sidst.

## API-nøgler (Indstillinger i programmet)

| Grosist | Hvor | Bemærkning |
|---|---|---|
| DigiKey | developer.digikey.com → opret app (Production) | Client ID + Secret. Kundenummer giver dine egne priser. |
| Mouser | mouser.dk → API Hub → Search API | Max 30 opslag/minut, 1000/dag – programmet holder sig under. |
| Mouser kurv | mouser.dk → API Hub → Cart/Order API | Valgfri – kun til "Læg i Mouser-kurv". |
| Nexar/Octopart | nexar.com/api | Dækker Farnell, TME, RS, Arrow m.fl. Gratis kvote er begrænset. |

Nøglerne gemmes i `%USERPROFILE%\.kicad_bomtool\config.json`, svar caches i 24 timer i samme mappe.
Datablade caches i `cache\datasheets`, historikken ligger i `history`.
Uden nøgler virker alt undtagen priser, lager, datablade fra grosist og alternativer.

## Begrænsninger

- Alternative IC'er er forslag – pinout og elektriske data skal altid tjekkes i databladet.
- Datablad-kontrollen læser tekst: pakkenavne, mål-tabeller og pin-tabeller. Står målene kun som
  tal på selve tegningen, vises tegningen i stedet, så du kan sammenligne med footprintets målestreger.
  Scannede PDF'er og produktsider (fx LCSC-links) kan ikke læses. Den sikreste kontrol er stadig
  at uploade producentens `.kicad_mod`.
- Mouser-kurven er bygget efter Mousers API-dokumentation, men ikke afprøvet med en rigtig nøgle.
- KiCad 5 (`.sch`) understøttes ikke – åbn og gem projektet i en nyere KiCad først.

## Opdateringer

Ved start tjekker programmet [GitHub Releases](https://github.com/Kaelor9/kicad-bomtool/releases) for en
nyere version og viser et banner. "Opdatér nu" henter den nye `.exe`, kontrollerer SHA-256-checksummen,
skifter filen ud og genstarter. Indstillinger, nøgler og historik ligger i `%USERPROFILE%\.kicad_bomtool`
og bevares. Tjekket kan slås fra under Indstillinger.

### Udgiv en ny version

```
git tag v1.1.0
git push origin v1.1.0
```

GitHub Actions (`.github/workflows/release.yml`) kører testene, bygger `KiCadBOM.exe` med versionsnummeret
fra tagget og lægger den og checksummen på en ny release. Alle der har programmet får den tilbudt.

## Test

```
python -m tests.test_units       # footprint, BOM-import, priser
python -m tests.test_pipeline    # hele flowet på KiCad-demoprojektet (kræver KiCad installeret)
```
