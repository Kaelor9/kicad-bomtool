# Overdragelse – KiCad BOM-tjek

Status pr. 2. november 2026, version **v1.6.0**. Skrevet så en ny udvikler (eller en ny AI-session) kan
fortsætte uden at kende historikken.

Repo: <https://github.com/Kaelor9/kicad-bomtool> (offentligt) · lokalt: `C:\GitHub\kicad-bomtool`

---

## 1. Målet med programmet

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

Brugeroplevelsen: tabellen med komponenter i midten, og **et kontrolpanel til højre** (ingen popup-vinduer,
der dækker tabellen) med fanerne *Footprint · Datasheet · Purchase · Alternatives*, plus en lille
**printvisning**, hvor den valgte komponent lyser op.

---

## 2. Hvad der er lavet

### Program og distribution
- **Eget vindue** (pywebview / Edge WebView2) med lokal server på 127.0.0.1. `--browser` bruger i stedet browseren,
  og `--no-browser` starter kun serveren.
- **`KiCadBOM-windows.zip`** (programmappen: `KiCadBOM.exe` + `_internal`) bygges af GitHub Actions ved hvert
  `v*`-tag (`.github/workflows/release.yml`) med PyInstaller `--onedir`, en selvkompileret bootloader, en
  sha256-fil og sit eget ikon (`bomtool/web/icon.ico`, tegnes af `tools/make_icon.py`).
- **Selvopdatering** fra GitHub Releases (`bomtool/updater.py`):
  - tjekker sha256;
  - pakker zip'en ud i `~/.kicad_bomtool/update`, og et lille `install.cmd` venter på, at programmet lukker,
    kopierer filerne over programmappen med robocopy `/E` (sletter aldrig noget) og starter den nye version;
  - gamle én-fils-versioner (≤ 1.5.0) blev opdateret ved at omdøbe den kørende exe til `.old`;
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
- **Printvisning** (`footprint.js` → `BoardView`):
  - printkant og rigtige pads;
  - fejl er rødtonede og advarsler orange;
  - den valgte komponent lyser blåt, og resten dæmpes;
  - zoom og pan; klik på printet vælger komponenten.

### Tests
- `python -m tests.test_units`: 59+ enhedstjek. Nogle bruger rigtige projekter og springes over uden KiCad installeret.
- `python -m tests.test_pipeline`: hele analysen med en falsk grosist.
- Kør med `PYTHONIOENCODING=utf-8` på Windows (cp1252 kan ikke skrive → og ↔).

---

## 3. Hvad der mangler / idéer

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
- **Mouser Search API-nøgle:** brugeren har ansøgt, men ingen bekræftelsesmail er kommet. Mouser er derfor kun
  testet med falske data og Mouser-BOM-filer.
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

---

## 4. Valg der er truffet (og hvorfor)

| Valg | Begrundelse |
|---|---|
| **Eget programvindue (pywebview)** frem for ren browser-app ("option A") | Føles som et rigtigt program; browseren er fallback. |
| Python standardbibliotek + valgfri pakker | Kører uden installation; exe'en indeholder pypdf, pypdfium2, pillow, openpyxl, pywebview og certifi. |
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

---

## 5. Hvad der tidligere ikke har fungeret (og hvordan det blev løst)

**Byg, release og opdatering**
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

**Pris og alternativer**
- **Pris på 78.908 kr.** fra tilbud, der kun fandtes som hel rulle: markeres nu som `impractical`.
- **Specs for passive forsvandt:** en dummy "1 50V" kunne ikke parses, så der bruges nu "1uF".
- **Alternativer til kontakter viste "Footprint: unknown":** sammenligning med KiCads footprint via `by_mpn` og
  fallback på `api_size`.

**Brugerflade**
- **Printvisningens streger blev for tykke ved zoom:** bruger nu non-scaling strokes.
- **Heredoc i bash ødelagde `\b` og `\d` i patch-scripts:** skriv scripts med en fil-editor, og tjek for `\x08` bagefter.

---

## 6. Praktisk

- **Kør fra kilde:**

  ```
  python -m bomtool
  ```

  Brug `--browser` for at køre i browseren. Port 8765, eller `PORT` fra miljøet.
- **Byg lokalt:** `build_exe.bat` (giver `dist\KiCadBOM\`, men med PyInstallers standard-bootloader).
- **Release:**

  ```
  git tag vX.Y.Z && git push origin vX.Y.Z
  ```

  CI bygger og udgiver, og programmet tilbyder derefter opdateringen.
- **Commit-beskeder** slutter med `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
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
