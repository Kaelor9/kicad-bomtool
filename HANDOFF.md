# Overdragelse – KiCad BOM-tjek

> **Dette dokument er projektets index.** Det er skrevet, så en ny udvikler eller en ny AI-session kan samle
> projektet op uden at kende historikken. Læs afsnit 0–3 først. De øvrige afsnit er opslag.

Repo: <https://github.com/Kaelor9/kicad-bomtool> (offentligt) · Brugerens lokale klon: `C:\GitHub\kicad-bomtool`

---

## 0. Regler for at arbejde i projektet (gælder også for AI)

1. **Læs HANDOFF.md før du ændrer noget.** Brug den som index: afsnit 4 viser, hvor koden ligger, og afsnit 3
   viser, hvad der er i gang.
2. **Opdatér HANDOFF.md løbende, i samme commit som ændringen.** Det betyder:
   - **afsnit 1 (Status):** version, og hvad der er udgivet og hvad der ikke er;
   - **afsnit 3 (Åbne sager):** hvad der er i gang, og hvad der venter på brugeren;
   - det relevante faglige afsnit (5–9), hvis noget er bygget, valgt eller løst;
   - **afsnit 11 (Ændringslog):** én linje pr. ændring, med den nyeste øverst.
3. **Skriv fejl og deres løsning i afsnit 8**, så de ikke bliver gentaget.
4. **Skriv brugerens beslutninger i afsnit 7** med begrundelse. Spørg, før en beslutning bliver omgjort.
5. **Hold strukturen.** Tilføj til de eksisterende afsnit i stedet for at lave nye afsnit nederst.
   Fjern det, der ikke længere er sandt. Dokumentet skal beskrive nuet, og historikken hører til i afsnit 8 og 11.
6. **Sprog:** brugeren skriver dansk, så dette dokument er på dansk. Kode, kommentarer og commit-beskeder er
   på engelsk. Commit-beskeder slutter med `Co-Authored-By: …`-linjen (se afsnit 10).
7. **Udgivelse er brugerens valg.** Et `v*`-tag udgiver til alle brugere (selvopdatering), så tag kun, når
   brugeren beder om det. Slet aldrig tags, der allerede er pushet.

---

## 1. Status lige nu

| | |
|---|---|
| Seneste udgivelse | **v1.6.1** (2. nov. 2026) – `KiCadBOM-windows.zip` |
| På branch, ikke udgivet | (1) Programvinduet faldt tilbage til browseren. (2) Footprint aflæses fra databladets tegning, ens retning/skala i sammenligningen, printets bagside, klarere kolonner, genkendelse uden "diode for sikring" (se afsnit 3 og 11). Skal udgives som **v1.7.0** |
| Version i kildekoden | `bomtool/__init__.py` siger `1.0.0`. CI sætter den rigtige ud fra tagget |
| Tests | `python -m tests.test_units` → ALL PASSED · `python -m tests.test_pipeline` → OK (med KiCad-demoer, se afsnit 10) |

---

## 2. Målet med programmet

Et **kontrolprogram** til KiCad-projekter (KiCad 8 og 10, men 6–10 kan læses). Det skal kontrollere, at:

1. **Komponent ↔ footprint:** den komponent, der er valgt i KiCad, passer med det valgte footprint.
2. **Footprint ↔ datablad:** footprintet passer med databladets anbefalede footprint og pakketegning
   (mål, pads, pinout).
3. **Køb:** det hele passer med det, man rent faktisk køber hos grosisten (DigiKey, Mouser …), både varenummer,
   antal og lager.

Derudover skal det:

- **læse BOM'en direkte fra KiCad** (MPN, antal, datablad), uden at brugeren skal udfylde en skabelon;
- **sammenligne med grosist-BOM'er** (kurv/ordre-filer fra Mouser, DigiKey, LCSC …);
- **optimere pris og antal**, så man sparer mest (prisknæk, MOQ, fragt, moms);
- **finde alternativer**, når en del ikke kan købes, også ikke-pin-kompatible til udgåede IC'er;
- **give et lynhurtigt overblik** og kunne **eksportere en pæn BOM** (Excel) med alle oplysninger.

Brugeroplevelsen er et **rigtigt program i eget vindue** (ikke en browserfane). Tabellen med komponenter er i
midten, og **et kontrolpanel ligger til højre** (ingen popup-vinduer, der dækker tabellen) med fanerne
*Footprint · Datasheet · Purchase · Alternatives*. Derudover er der en lille **printvisning**, hvor den valgte
komponent lyser op.

---

## 3. Åbne sager / næste skridt

### I gang
- **"Programmet åbner i browseren i stedet for i sit eget vindue"**, rapporteret 2. nov. 2026 på v1.6.x.
  - **Mest sandsynlige årsag:** siden v1.6.0 er programmet en zip. Pakkes den ud med Stifinder, får alle
    filer mærket "hentet fra internettet" (Zone.Identifier). .NET nægter så at indlæse `Python.Runtime.dll`
    og WebView2-DLL'erne. Undtagelsen blev fanget, og programmet faldt stille tilbage til browseren.
    One-file-exe'en (≤ v1.5.0) pakkede sig selv ud i temp uden mærke, så den havde ikke problemet.
  - **Rettet på branch (ikke udgivet):** `bomtool/__main__.py`
    - fjerner mærket fra programmappens egne filer ved start (`unblock_program_folder`);
    - sender ikke længere en ikonfil til vinduet på Windows. pywebview bruger så exe'ens indbyggede ikon,
      og den crash-risiko, der lå bag v1.6.0/v1.6.1, er væk;
    - skriver årsagen til `%USERPROFILE%\.kicad_bomtool\window.log`, når vinduet ikke kan åbnes
      (exe'en har ingen konsol).
  - **Mangler:**
    1. Brugeren skal udgive næste version (`git tag v1.7.0 && git push origin v1.7.0` fra `main`, efter merge).
    2. Bekræft på Windows, at vinduet åbner.
    3. Åbner det stadig i browseren, så send indholdet af `window.log`, så den rigtige årsag kendes.
  - **Midlertidig løsning for brugeren:** højreklik zip'en → Egenskaber → "Fjern blokering", inden den
    pakkes ud. Eller tryk "Update now", som også virker i browseren.

- **Brugerens feedback 2. nov. 2026 (skærmbilleder af IC2, F1, BOOT1/RESET1, SOT-23-dele):**
  - **Lavet på branch:**
    - footprint aflæst fra databladets tegning (`bomtool/dsland.py`);
    - de to footprint-kasser flugter og har samme skala;
    - referencen vender som brugerens footprint;
    - F1 bliver ikke længere "genkendt" som diode;
    - kolonnerne har nu navne i stedet for "1 FP / 2 DS / 3 Buy";
    - "+2" forklares;
    - printets bagside kan vises;
    - pænere mållinjer.
  - **Ikke afklaret, kræver skærmbilleder fra brugeren:** C1, C9 og D8 "ser mærkelige ud", BOOT1/RESET1's
    footprint ser mærkeligt ud, og J8's mål ser mærkelige ud. Projektet ligger kun hos brugeren, så de dele kunne
    ikke ses. Målene er gjort generelt pænere (tekst uden for pilene, ingen 0-mål), men J8 er ikke set.
  - **"Vis det til venstre":** tolket som den tomme "Datasheet"-kasse ved siden af brugerens footprint. Den
    aflæste tegning vises dér, og den kan lægges oven på brugerens footprint med "+ Datasheet".

### Næste skridt (forslag)
- **Diodes Inc. land patterns** skriver bogstaver (X, Y, C …) på tegningen og værdierne i en tabel ved siden af.
  `dsland` læser kun tal på tegningen. Udvid med bogstav → tabel-opslag.
- **QFN med pads i forskellige størrelser** (fx TI VQFN-HR, TPS62902) aflæses ikke endnu: `_pads` tager kun én
  gruppe ens pads (+ én termisk pad).

### Venter på brugeren
- **Mouser** (status 2. nov. 2026):
  - **Search API:** nøglen er ikke udstedt. Mouser venter på en verifikationskode, som er sendt til brugerens
    iCloud-adresse (den i Mouser-kontoen, ikke Gmail). Brugeren skal finde mailen (tjek "Uønsket") eller bede
    Mouser (Live Chat / api@mouser.com) om at sende den igen.
  - **Order/Cart API-nøgle:** findes, men står som "Pending". Den hører til feltet "Mouser Cart API", ikke Search.
- **Nexar:** brugeren sætter Client ID/Secret ind (Evaluation app, Client Credentials er slået til). Nexar er ikke
  testet med en rigtig nøgle før. Felter, som planen ikke giver adgang til, kan kræve, at forespørgslen gøres mindre.
- Skærmbilleder af C1, C9, D8, BOOT1/RESET1 (Footprint-fanen) og J8.

---

## 4. Kodekort (hvor ligger hvad)

**Start og indpakning**

| Fil | Indhold |
|---|---|
| `bomtool/__main__.py` | Start. Åbner eget vindue (pywebview), og browseren er fallback. Her ligger også unblock af zip-filer og `window.log`. |
| `run_bomtool.py` | Indgang for PyInstaller (exe'en). |
| `start.bat` | Kør fra kilde på Windows (`py -3 -m bomtool`). |
| `build_exe.bat` | Lokalt PyInstaller-byg (`dist\KiCadBOM\`). |
| `.github/workflows/release.yml` | CI. Ved `v*`-tag: tests → egen bootloader → `--onedir` → zip + sha256 → GitHub Release. |
| `bomtool/updater.py` | Selvopdatering fra GitHub Releases. Zip og `install.cmd` til mappe-bygget; exe-swap til de gamle én-fils-versioner. |
| `bomtool/server.py` | Lokal HTTP-server (127.0.0.1) og alle `/api/*`-adresser. |
| `bomtool/config.py` | Indstillinger og nøgler i `~/.kicad_bomtool/config.json` (`app_dir()`, `cache_dir()`). |
| `bomtool/net.py` | `urlopen` med fallback CA-bundle (certifi). |
| `bomtool/i18n.py` | Oversætter backend-beskeder fra dansk til engelsk. |
| `tools/make_icon.py` | Tegner `bomtool/web/icon.ico` og `icon.png`. |

**Læsning af projektet**

| Fil | Indhold |
|---|---|
| `bomtool/vfs.py` | Uploadet projekt (zip eller filer) i hukommelsen. |
| `bomtool/sexpr.py` | Tolerant S-expression-parser (KiCad 6–10). |
| `bomtool/kicad.py` | Skematik-hierarki, PCB-footprints og libs, samlet til en flad komponentliste. |
| `bomtool/fields.py` | Finder MPN, producent og varenumre i felter og parser værdier ("4k7", "100nF 50V X7R"). |
| `bomtool/bom.py` | Grupperer komponenter i BOM-linjer. |
| `bomtool/analyze.py` | Hele analyse-pipelinen (baggrundstråd med fremdrift og stop). |

**Kontrol 1: komponent ↔ footprint**

| Fil | Indhold |
|---|---|
| `bomtool/packages.py` | Normaliserer og sammenligner pakkenavne (IPC-7351, chip-størrelser …). |
| `bomtool/footprint.py` | Footprint-geometri, reference-sammenligning og pin/pad-tjek. |
| `bomtool/fplib.py` | Indeks over KiCads ca. 15.100 footprints (genkendelse ud fra geometri og `by_mpn`). |

**Kontrol 2: footprint ↔ datablad**

| Fil | Indhold |
|---|---|
| `bomtool/datasheet.py` | Henter datablad og tjekker, om det er det rigtige, og pakkenavne. |
| `bomtool/dsland.py` | Aflæser databladets anbefalede footprint fra selve tegningen (vektorgrafik: pads, pile, mål). |
| `bomtool/dsdata.py` | Mål-, pad- og pin-tabeller fra databladets tekst. |
| `bomtool/dsimage.py` | Udsnit af databladets tegninger (pypdfium2, global lås `_PDFIUM`, som `dsland` også bruger). |
| `bomtool/fpcompare.py` | Sammenligningen: footprint mod datablad og beregnet IPC-landpattern. |

**Kontrol 3: køb**

| Fil | Indhold |
|---|---|
| `bomtool/providers.py` | DigiKey v4, Mouser og Nexar, normaliseret til én `Part`. |
| `bomtool/distbom.py` | Indlæser og matcher grosist-BOM'er. |
| `bomtool/tables.py` | Læser CSV, XLSX, XLS og HTML-xls til rækker. |
| `bomtool/pricing.py` | Prisknæk, MOQ, fragt og moms, og konsolidering af grosister. |
| `bomtool/alternatives.py` | Alternative dele. |

**Resultater og brugerflade**

| Fil | Indhold |
|---|---|
| `bomtool/export.py` | Excel-BOM. |
| `bomtool/history.py` | Gemte analyser og forskelle mellem to analyser. |
| `bomtool/web/index.html`, `app.js`, `style.css` | Brugerfladen. |
| `bomtool/web/footprint.js` | Footprint-tegning (`renderFootprint`, `renderFootprintPair` = to tegninger i samme skala, `fpOrientLike` = drej referencen som brugerens) og `BoardView` (printvisning med top/bund). |
| `bomtool/web/i18n.js` | Danske UI-tekster (UI'et er skrevet på engelsk). |

**Tests**

| Fil | Indhold |
|---|---|
| `tests/test_units.py` | Enhedstests. |
| `tests/test_pipeline.py` | End-to-end med en falsk grosist. |

**Brugerdata** ligger i `%USERPROFILE%\.kicad_bomtool\` (eller `BOMTOOL_HOME`): `config.json`, `cache/`,
`history/`, `webview/` (vinduets lager), `update/` (midlertidig) og `window.log`.

---

## 5. Hvad der er lavet

### Program og distribution
- **Eget vindue** (pywebview / Edge WebView2) med lokal server på 127.0.0.1. `--browser` bruger i stedet browseren,
  og `--no-browser` starter kun serveren. Hvis vinduet ikke kan åbnes, bruges browseren, og årsagen skrives i
  `window.log`.
- **`KiCadBOM-windows.zip`** (programmappen: `KiCadBOM.exe` + `_internal`) bygges af GitHub Actions ved hvert
  `v*`-tag (`.github/workflows/release.yml`) med PyInstaller `--onedir`, en selvkompileret bootloader, en
  sha256-fil og sit eget ikon (`bomtool/web/icon.ico`, tegnes af `tools/make_icon.py`). Ikonet sidder i exe'en,
  og vinduet tager det derfra.
- Ved start fjernes Windows' "hentet fra internettet"-mærke fra programmappens egne filer, så .NET vil
  indlæse vinduets DLL'er.
- **Selvopdatering** fra GitHub Releases (`bomtool/updater.py`):
  - tjekker sha256;
  - pakker zip'en ud i `~/.kicad_bomtool/update`, og et lille `install.cmd` venter på, at programmet lukker,
    kopierer filerne over programmappen med robocopy `/E` (sletter aldrig noget) og starter den nye version;
  - gamle én-fils-versioner (≤ 1.5.0) blev opdateret ved at omdøbe den kørende exe til `.old`. De kan ikke
    selv blive til en mappe, så de skal hente zip'en manuelt én gang;
  - "Update now" ligger også under Indstillinger.
- **Sprog:** engelsk er standard, dansk er valgfrit.
  - Backend-beskeder er skrevet på dansk og oversættes af `bomtool/i18n.py`.
  - UI-teksterne er engelske i JS, og de danske står i `web/i18n.js`.
- **Historik** over tidligere analyser (gz-JSON i `~/.kicad_bomtool/history`) og **sammenligning** mellem to
  analyser (fanen "Changes").
- **Stop-knap** til en kørende analyse.

### Kontrol 1: komponent ↔ footprint
- Parser S-expressions fra `.kicad_sch`, `.kicad_pcb` og `.kicad_mod`.
- PCB-footprints kobles til symboler via UUID-sti, ikke reference, og omdøbte referencer advares.
- Pakken aflæses fra footprint-navnet og fra MPN/grosist.
  - IPC-7351-navne afkodes: SOP→SOIC/MSOP/TSSOP/SSOP efter benspænd, SOT95→SOT-23, SOT65→SC-70.
  - Chip-størrelser (0402/0603/0805/1206/1210 …) sammenlignes, så fx 0603-footprint med 0805-del fanges.
- Kontroller af pins mod pads; pins med samme navn behandles som samme pad.
- **Footprint-genkendelse ud fra geometrien** (`bomtool/fplib.py`):
  - viser kun match på mindst 90 % lighed (`MIN_SIMILARITY`); under det var det gæt (0201 for 0402, diode for sikring);
  - biblioteker for én slags dele (Diode_, Inductor_, Connector …) vises ikke for en anden slags reference
    (`TYPED_LIBS`/`REF_KINDS`): F1 kan ikke blive en D_MELF;
  - indeks over ca. 15.100 KiCad-footprints, bygget i baggrunden første gang (ca. 90 s) og cachet som `fpindex-*.json.gz`;
  - fanger selvlavede footprints med dårlige navne;
  - `by_mpn` finder KiCads footprint til et varenummer, fx `SW_SPST_PTS810`.

### Kontrol 2: footprint ↔ datablad
- Datablade hentes og caches. Forkert datablad opdages via serie-præfikset (fx LT1963-datablad på en AP7365).
- Tekst udtrækkes med pypdf, og en indbygget lineær tokenizer er fallback. Følgende tabeller læses
  (`bomtool/dsdata.py`):
  - mål-tabeller (mm/inch);
  - pad-layout-tabeller;
  - pin-tabeller.
- **IPC-7351-landpattern beregnes** ud fra databladets mål (`bomtool/fpcompare.py`) og tegnes ved siden af brugerens footprint.
- **Databladets anbefalede footprint aflæses fra tegningen** (`bomtool/dsland.py`), når det er vektorgrafik:
  - pads er rektangler, der er udfyldte, omrids eller fire løse sider med runde hjørner (TI);
  - mållinjer er par af pilespidser, og tallet nærmest linjen er målet ("1.5 ± 0.05 (.059)" → 1.5, TI "6X (1.1)" → 1.1);
  - pilespidserne rammer pad-kanter eller centerlinjer, så kanterne fastlægges i mm ud fra tallene alene.
    Tegningens proportioner bruges aldrig, fordi mange tegninger ikke er i skala;
  - har databladet flere varianter (Bourns "Style 1/2"), vælges den, der ligner brugerens footprint mest;
  - padsene drejes og nummereres som brugerens, så de kan lægges oven på ("+ Datasheet");
  - under analysen giver det kontrollen "Footprint ↔ databladets tegning". Passer den, tilsidesætter den den
    generiske IPC-størrelse ("Pads ↔ komponentens fysiske mål").
  - Testet: Bourns MF-MSMF (begge styles) og TI TPL5010 (SOT-23-6).
- **Reference, når databladet ikke har mål som tekst:**
  - passive komponenter sammenlignes med delens rigtige størrelse;
  - andre komponenter sammenlignes med KiCads footprint til MPN'en.
- En **måltabel** viser forskellen (pads, pitch, pad-længde/-bredde, ydre mål, afstand mellem rækker).
- **Udsnit af databladets tegninger** (`bomtool/dsimage.py`, pypdfium2):
  - "anbefalet footprint" og "pakketegning" skæres ud af PDF'en;
  - kun synlig tekst tæller som overskrift;
  - indholdsfortegnelser, sætninger, tekst-regioner og billedtekster under figuren håndteres.
- Pinout-sammenligning symbol ↔ datablad. Ulæselige pin-tabeller skjules.

### Kontrol 3: køb
- DigiKey API v4 (OAuth client credentials) og Mouser Search API. Nexar/Octopart kan indtastes, men er ikke testet.
- **Grosist-BOM** indlæses fra CSV, XLSX, XLS og Mousers HTML-"xls" uden skabelon, og matches på MPN, varenummer,
  reference eller værdi+pakke.
- **Prisoptimering** (`bomtool/pricing.py`):
  - prisknæk, MOQ, multipla og reservedele (procent for passive);
  - forslag af typen "køb flere, det er billigere";
  - konsolidering af grosister, når fragtbesparelsen er større end merprisen.
- **Hel rulle** (MOQ langt over behovet) markeres "Købes ikke" og tæller ikke med i totalen.
- **Reel ordrepris:** fragt pr. grosist (gratis over en grænse) plus moms. Standard er Danmark: 25 % moms,
  DigiKey 185 kr. under 550 kr., Mouser gratis fra 550 kr. Alt kan rettes i Indstillinger.
- Læg i **DigiKey-kurv** (FastAdd-link) og **Mouser-kurv** (Cart API-nøgle). CSV-ordrelister pr. grosist.
- **Alternativer** (`bomtool/alternatives.py`) vises automatisk uden klik, med produktfoto og et lille footprint.
  - **Passive:** footprintet er facit, og specs (værdi, spænding, dielektrikum …) tages fra den valgte del.
  - **Aktive:** grosisternes erstatninger plus søgning på lignende funktion, grupperet som
    drop-in, samme pakke, skal tjekkes og kræver nyt layout. Det sidste dækker udgåede IC'er.
  - Sorteres efter største lager, med filteret "Minimum stock" (fx 50000) og derefter billigst.
- **Excel-eksport** (`bomtool/export.py`) med arkene BOM, Purchase, Excluded og Project.

### Brugerflade (`bomtool/web/`)
- **Overblik øverst:** fliser for de 3 kontroller plus ordrepris, og et klik filtrerer tabellen.
- **Faner:** Components, Purchase, Distributor BOM, Excluded og Changes.
- **Panelet til højre** åbner selv på den første kontrol med et problem.
- **Footprint-fanen:** dit footprint og referencen står ved siden af hinanden i samme skala og samme
  rammestørrelse, flugter (CSS subgrid), og referencen er drejet (0/90/180/270°, spejlet kun for bundside-dele),
  så pin-numrene ligger samme sted. Den lange forklaring står under tegningen.
- **Mållinjer:** teksten flyttes uden for pilene, når den ikke er plads, og mål på 0 vises ikke.
- **Kolonnerne** hedder "Part ↔ FP", "FP ↔ datasheet" og "Buyable" (før "1 FP / 2 DS / 3 Buy"). Fliserne har de
  samme navne uden numre.
- **Reservedele:** "+2" ved behovet har en forklaring ved hover. Passive får +10 %, dog mindst 2 stk.
  ("More options" før analysen).
- **Printvisning** (`footprint.js` → `BoardView`):
  - knapperne Top / Bottom / Both. Bottom viser printet nedefra (spejlvendt), og vælger man en del, der kun sidder
    på den skjulte side, vendes printet selv;
  - printkant og rigtige pads;
  - fejl er rødtonede og advarsler orange;
  - den valgte komponent lyser blåt, og resten dæmpes;
  - zoom og pan; klik på printet vælger komponenten.

### Tests
- `python -m tests.test_units`: 59+ enhedstjek. Nogle bruger rigtige projekter og springes over uden KiCad installeret.
- `python -m tests.test_pipeline`: hele analysen med en falsk grosist.
- Kør med `PYTHONIOENCODING=utf-8` på Windows (cp1252 kan ikke skrive → og ↔).

---

## 6. Hvad der mangler / idéer

### Ikke bygget (foreslået, men ikke valgt af brugeren endnu)
- **Skrive det valgte alternativ tilbage til KiCad** (MPN/felter i `.kicad_sch`). I dag ændrer et valg kun
  ordrelisten og kurven, ikke projektet.
- **Huske valg og kvitteringer** ("denne advarsel er OK") mellem analyser.
- **Live-tilstand:** genanalyse når projektfilerne ændres.
- **KiCad-plugin/knap**, så programmet startes fra KiCad.
- **Pris pr. antal print** (1/10/100 print i samme visning).
- **Lager-overvågning** med besked, når en del er ved at løbe tør eller bliver udgået.
- **PDF-godkendelsesrapport** til design review.

### Kendte begrænsninger
- **Mouser Search API-nøgle** er ikke udstedt endnu (se afsnit 3). Mouser er derfor kun testet med falske data og
  Mouser-BOM-filer.
- **Mousers fragtgebyr under 550 kr. (150 kr.)** er et skøn og bør tjekkes på mouser.dk. DigiKeys tal er fundet på digikey.dk.
- **Trykknapper og andre komponenter uden pakkenavn:** DigiKey oplyser hverken pakke eller størrelse. Alternativer kan
  kun pasform-tjekkes, når KiCad har et footprint opkaldt efter varenummeret; ellers står der "Footprint: unknown".
- **Datablad-udsnit er heuristik.** I ESP32-testprojektet rammer de fleste rigtigt, men nogle datablade giver intet
  billede (bevidst hellere intet end forkert), og et udsnit kan stadig tage lidt for meget med.
- Nogle datablade kan ikke hentes:
  - LCSC-sider er bot-beskyttet, og vi omgår det ikke bevidst;
  - links, der peger på en webside i stedet for en PDF, afvises;
  - nogle servere svarer HTTP 522.
- **Lagerstatus 0** hos DigiKey på cut tape købes stadig (restordre). Det vises med rødt lagertal, men der er ingen
  "vælg automatisk et alternativ".
- **Moms og fragt** regnes ens for alle valutaer. Standardværdierne er i DKK.
- `__version__` i kildekoden er `1.0.0`; den rigtige version sættes af CI ud fra tagget. Kørt fra kilde ser det
  derfor ud, som om der altid findes en opdatering.
- Ingen kodesignering af exe'en, så Windows SmartScreen kan advare ("Flere oplysninger → Kør alligevel").
  Kodesignering (ca. 1.000–3.000 kr./år) er den rigtige løsning, hvis det bliver et problem.
- **Programvinduet kan ikke testes i en Linux-container** (WinForms/.NET/WebView2). Ændringer i
  `bomtool/__main__.py` skal bekræftes af brugeren på Windows.

---

## 7. Valg der er truffet (og hvorfor)

| Valg | Begrundelse |
|---|---|
| **Eget programvindue (pywebview)** frem for ren browser-app ("option A") | Føles som et rigtigt program; browseren er kun fallback. |
| Python standardbibliotek + valgfri pakker | Kører uden installation; exe'en indeholder pypdf, pypdfium2, pillow, openpyxl, pywebview og certifi. |
| **Programmappe i zip (`--onedir`)** i stedet for én exe | Antivirus/Chrome meldte én-fils-exe'en som virus (se afsnit 8). |
| Vinduet får ikke en ikonfil på Windows | pywebview tager exe'ens indbyggede ikon. Ikonfiler fik .NET til at crashe. |
| **Panel til højre for tabellen, ingen popup** | Brugerens krav: compare-visningen må ikke skygge for tabellen. |
| **Alternativer for en forkert valgt del:** footprintet er facit, specs fra den valgte del | Brugerens valg: printet er lavet, så delen skal passe til footprintet. |
| **Alternativer sorteres efter største lager**, filter "Minimum stock", derefter billigst | Brugerens ønske. |
| **Engelsk som standard**, dansk valgfrit; backend-tekster skrives på dansk og oversættes | Dansk var originalsproget, så oversættelse via skabeloner var mindst indgribende. |
| Hel rulle markeres "Købes ikke" i stedet for at blive købt | En linje med 150.000 stk. til 18.000 kr. var en fejl, ikke et køb. |
| **Reel ordrepris** med fragt-grænser og moms | Brugeren vil se, hvad det faktisk koster. |
| Printvisning: komponenten farves, ingen ringe | Brugeren kunne ikke lide cirklerne. |
| Hellere intet datablad-billede end et forkert | Forkerte udsnit (tekstafsnit, indholdsfortegnelse) forvirrede mere, end de hjalp. |
| Passive tjekkes mod MPN-mønstre og IPC-størrelser, ikke mod datablad | Datablade for passive er generiske serie-datablade. |
| Offentligt GitHub-repo; releases via tags | Selvopdatering kræver offentlige releases. |
| API-nøgler gemmes kun lokalt i `~/.kicad_bomtool/config.json` | Sikkerhed: nøgler sendes kun til grosisternes egne API'er og aldrig i chat. |
| User-Agent forfalskes ikke for at komme forbi bot-beskyttelse | Etik og vilkår. |
| **HANDOFF.md er index og opdateres i hver ændring** | Brugerens ønske, så en anden AI kan samle projektet op. |
| **Databladets tegnede footprint slår IPC og generiske størrelser** | Det er producentens anbefaling. F1 (Bourns MF-MSMF050/40X) fulgte tegningen, men blev vist rødt mod en generisk 1812. |
| Tegninger læses ud fra tallene, aldrig ud fra proportionerne | Bourns tegner pads ikke i skala. Hellere intet footprint end et forkert. |
| Referencen drejes, så den vender som brugerens footprint | Brugerens ønske ("footprints skal vende ens"). |
| Genkendelse kun ved ≥ 90 % og kun i biblioteker for samme slags del | Brugeren syntes, det var mærkeligt, at en sikring blev "genkendt" som diode. |

---

## 8. Hvad der tidligere ikke har fungeret (og hvordan det blev løst)

**Byg, release og opdatering**
- **v1.6.x åbnede i browseren i stedet for eget vindue:** sandsynligvis fordi Stifinder mærker de udpakkede
  zip-filer som "fra internettet", og så vil .NET ikke indlæse DLL'erne. Undtagelsen blev fanget uden spor.
  Rettet på branch (afventer v1.7.0): unblock ved start og `window.log`. Se afsnit 3.
- **v1.5.0 og v1.6.0 lukkede ved start i programvinduet** (.NET `System.Drawing.Icon` ArgumentException): vinduet fik
  ikonet som `.png`, men WinForms tager kun `.ico`. v1.6.1 gav en `.ico` i stedet. Den `.ico` består af
  PNG-rammer, som .NET Framework heller ikke altid accepterer, så nu gives der slet ingen ikonfil på Windows.
  Fejlen ses i Windows' hændelseslog under ".NET Runtime". Bemærk, at en .NET-undtagelse i vinduets tråd crasher
  programmet, mens en Python-undtagelse i `webview.start` giver browser-fallback.
- **Chrome/Defender meldte "Virus detected" på `KiCadBOM.exe` (v1.5.0):** falsk alarm, typisk for én-fils
  PyInstaller-programmer (pakker sig ud i temp ved hver start, bootloader delt med malware) uden signatur, der
  opdaterer sig selv. Løst fra v1.6.0 med `--onedir` i en zip og en bootloader, CI selv kompilerer.
- **CI fejlede med `UnicodeEncodeError` (cp1252):** løst med `PYTHONIOENCODING: utf-8` i workflowet.
- **Opdateringen hang ved genstart af exe'en:** PyInstaller-miljøet blev arvet. Løst med `PYINSTALLER_RESET_ENVIRONMENT=1`.
- **Fjerne tags på GitHub må ikke slettes** (blev afvist som destruktivt). Lav et nyt versionstag i stedet.
- **gh CLI via winget hang på UAC:** den portable zip blev brugt i stedet.

**Datablade og PDF**
- **Regex-backtracking i den indbyggede PDF-læser frøs programmet:** erstattet af en lineær tokenizer.
- **LCSC-links redirectede til forsiden, og vi fik den forkerte PDF:** løst med streng `_datasheet_link` og et
  læsbarhedstjek.
- **"+85" (temperatur) blev læst som "LGA-85":** pin-parsing foretrækker nu eksplicitte suffikser.
- **Serveren crashede (exit 3), når to datablad-billeder blev hentet samtidig:** PDFium er ikke trådsikker, så der er
  en global lås i `dsimage.py`.
- **Datablad-udsnit ramte forkert:**
  - usynlig dubleret tekst i PDF'er, så nu tæller kun synlige overskrifter;
  - indholdsfortegnelser (med og uden prikker);
  - ordet "footprint" midt i en sætning eller fodnote, så generelle ord skal nu starte en kort linje;
  - tekstafsnit om lodning, så udsnit med mange ord og få tal afvises;
  - billedtekst under figuren (Espressif), så programmet nu beskærer opad.
- **ADUM1201's pin-tabel blev læst som "V", "V", "V" og vist som fejl:** tabeller med navne på ét bogstav skjules nu.
- **Seriedatablade med jokertegn ("FTSH-1xx"):** serie-tjekket bruger nu bogstaver plus første ciffer.

**Pakker og footprints**
- **IPC-navne gav falske fejl** (SSOP vs. TSSOP, "SOT23-3"): MSOP, TSSOP og SSOP accepteres som udskiftelige, når
  den ene side kommer fra et IPC-navn.
- **En bar "SOT-23" i TI-datablade passede ikke med SOT-23-8:** bar nævnelse matcher nu enhver SOT-23-variant.
- **Mål for 2-pad-komponenter blev mærket på forkert akse:** "på tværs" er nu linjen mellem de to terminaler.

**Datablad-tegninger (dsland)**
- **Bourns-tegningen er ikke i skala** (pads tegnet 23 × 40 pt, men 1.5 × 3.2 mm): en skala-baseret aflæsning gav
  forkerte pads. Løst ved kun at bruge mållinjer og tal.
- **Pilespidser blev taget som pads:** trekanter (3 hjørner) er nu pile, og kun former med hjørner på alle fire sider
  er pads.
- **Pad tegnet to gange** (flade + omrids): omridset "indeholdt" fladen, så begge blev smidt ud. Nu slås næsten ens
  former sammen.
- **Tal splittet forkert** ("3.2 ± 0.1" gav "2.0"): teksten samles nu tegn for tegn med pdfiums "loose" tegnbokse
  (punktummet har ellers en lav boks).
- **Usynlig tekst** i PDF'en ("1.0") stjal en mållinje: kun tal med synligt blæk tæller.
- **TI tegner hver pad-side og hvert hjørne som separate stier:** rektangler samles af løse linjer (`_line_rects`).
- **TI "4X (0.95)"** gælder for alle nabopar med samme afstand i tegningen.
- **Området under overskriften løb ind i grafer:** stopper nu ved næste overskrift eller grå sektionsbjælke.
- **pypdfium2 5.x** har `get_bounds()` i stedet for `get_pos()`. Begge håndteres.

**Pris og alternativer**
- **Pris på 78.908 kr.** fra tilbud, der kun fandtes som hel rulle: markeres nu som `impractical`.
- **Specs for passive forsvandt:** en dummy "1 50V" kunne ikke parses, så der bruges nu "1uF".
- **Alternativer til kontakter viste "Footprint: unknown":** sammenligning med KiCads footprint via `by_mpn` og
  fallback på `api_size`.

**Brugerflade**
- **Printvisningens streger blev for tykke ved zoom:** bruger nu non-scaling strokes.

**Arbejdsgang**
- **Heredoc i bash ødelagde `\b` og `\d` i patch-scripts:** skriv scripts med en fil-editor, og tjek for `\x08` bagefter.

---

## 9. Brugerens testprojekter og fund, der skal blive ved med at virke

- **Brugerens testprojekter** ligger i `C:\GitHub\` (alle KiCad 8):
  - **ESP32-S3-WROOM-1-N8R8 dev bard** er hovedtestprojektet. Mappen uden "dev bard" har kun `.kicad_pro` og backups.
  - LT3756-LUMOS-DRIVER, Marine-RGB-Light-Controller, STM32-BUILD-STM32G431CBT6 og new-lumos-driver.
- **Rigtige fund i brugerens projekter**, som programmet skal blive ved med at fange:

  | Del | Fund |
  |---|---|
  | C25 | 0603-footprint, 0805-del |
  | R2 | 0402-footprint, 0603-del |
  | C7 | 1206-footprint, 1210-del |
  | U1 | AP7365 med forkert datablad (LT1963) |
  | BOOT1 | byttede felter |
  | Lumos J1/J2 | passer ikke med Keystone-terminaler |
  | LT3756 | PCB'et passer ikke med skematikken |

---

## 10. Praktisk

- **Kør fra kilde:**

  ```
  python -m bomtool
  ```

  Kræver `pip install pywebview` for eget vindue; ellers bruges browseren. Brug `--browser` for at tvinge
  browseren. Port 8765, eller `PORT` fra miljøet.
- **Byg lokalt:** `build_exe.bat` (giver `dist\KiCadBOM\`, men med PyInstallers standard-bootloader).
- **Release** (kun når brugeren beder om det):

  ```
  git tag vX.Y.Z && git push origin vX.Y.Z
  ```

  CI bygger og udgiver, og programmet tilbyder derefter opdateringen.
- **Fejlfinding, hvis vinduet ikke åbner:** se `%USERPROFILE%\.kicad_bomtool\window.log`. Ved crash: se Windows'
  Logbog → Windows-logfiler → Program → ".NET Runtime"/"Application Error".
- **Test i en Linux-container (AI-session):** KiCad er ikke installeret. Hent biblioteket og demoerne:

  ```
  git clone --depth 1 https://gitlab.com/kicad/libraries/kicad-footprints.git <dir>/share/footprints
  git clone --depth 1 --filter=blob:none --sparse https://gitlab.com/kicad/code/kicad.git ksrc && (cd ksrc && git sparse-checkout set demos)
  ```

  Læg `demos` ved siden af `footprints` (`<dir>/share/demos`) og sæt `KICAD_FOOTPRINT_DIR=<dir>/share/footprints`.
  Kør derefter `python -m bomtool --no-browser` og styr brugerfladen med Playwright (Chromium er installeret).
  `openair-max`-demoen har dele på begge sider. Demoernes databladlinks går til LCSC (bot-beskyttet), så skift et
  link til en producent-PDF for at teste datablad-funktioner. Toshibas side afviser automatiske hentninger.
- **Commit-beskeder** er på engelsk og slutter med `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **AI-sessioner i skyen** arbejder på en `claude/*`-branch. Brugeren merger til `main` og tagger.

---

## 11. Ændringslog

Nyeste øverst. Én linje pr. ændring: dato · version/branch · hvad og hvorfor.

- 2026-11-02 · branch `claude/zealous-wozniak-h6k13i` · HANDOFF: status for Mouser- og Nexar-nøgler (ingen kodeændring).
- 2026-11-02 · branch `claude/zealous-wozniak-h6k13i` · Brugerens feedback på footprint-fanen:
  - `bomtool/dsland.py` aflæser databladets anbefalede footprint fra tegningen og bruges i analysen og i
    `fpcompare`;
  - de to footprints vises i samme skala, flugtende og med samme retning;
  - genkendelse kræver ≥ 90 % og samme slags del;
  - kolonnerne har navne i stedet for numre, og "+2" i reserve forklares;
  - printet kan vises fra bunden;
  - mållinjerne er pænere;
  - nye enhedstests: `test_dsland`, `test_recognise_kind`.
- 2026-11-02 · branch `claude/zealous-wozniak-h6k13i` · Programvinduet faldt tilbage til browseren på v1.6.x.
  Nu unblockes zip-udpakkede filer, Windows-vinduet får ikke en ikonfil, og fejlen logges i `window.log`.
  HANDOFF.md er omorganiseret til index (regler, status, åbne sager, kodekort, ændringslog), og `CLAUDE.md`
  peger hertil.
- 2026-11-02 · v1.6.1 · Vinduesikon som `.ico` (en `.png` crashede vinduet ved start).
- 2026-11-02 · v1.6.0 · Udgives som programmappe i zip med selvbygget bootloader (falsk virus-alarm).
- 2026-11-02 · v1.5.0 · Reel ordrepris, datablad-footprint ved siden af brugerens, programikon.
- Før det: v1.0.0–v1.4.0 (1.–2. nov. 2026). Kontrollerne, brugerfladen og selvopdateringen blev bygget.
  Se `git log`.
