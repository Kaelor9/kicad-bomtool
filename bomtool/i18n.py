"""English translations of the program's messages.

The checks write their messages in Danish (the source language). When the chosen language is
English, every message is translated on its way to the screen or the Excel file by matching it against
the templates below: "{}" is a value inside the message, and the English text may reorder them with
{0}, {1} ... Nothing in the checks themselves depends on the language.
"""
import re

T = [
    # program / server
    ("Kunne ikke åbne programvinduet ({}) – bruger browseren i stedet.", "Could not open the program window ({}) – using the browser instead."),
    ("Kunne ikke finde en ledig port.", "Could not find a free port."),
    ("Filen er for stor.", "The file is too large."),
    ("En uploadet fil er udløbet – upload den igen.", "An uploaded file has expired – upload it again."),
    ("Kunne ikke gemme i historikken: {}", "Could not save to history: {}"),
    ("Ingen nøgler indtastet.", "No keys entered."),
    ("Analysen findes ikke længere – kør den igen.", "The analysis no longer exists – run it again."),
    ("Analysen findes ikke længere.", "The analysis no longer exists."),
    ("Analysen blev stoppet.", "The analysis was stopped."),
    ("Ingen linjer har et Mouser-varenummer.", "No lines have a Mouser part number."),
    ("OK – fandt {} resultat(er).", "OK – found {} result(s)."),
    ("Stopper …", "Stopping …"),
    ("Filen ligner ikke en gyldig Excel-fil.", "The file does not look like a valid Excel file."),
    ("Gammelt .xls-format kræver pakken 'xlrd' (pip install xlrd). Alternativt: gem filen som .xlsx eller .csv.",
     "The old .xls format needs the 'xlrd' package (pip install xlrd). Or save the file as .xlsx or .csv."),
    ("Opdateret til {} – starter igen.", "Updated to {} – restarting."),
    ("Kunne ikke tjekke for opdateringer ({}).", "Could not check for updates ({})."),
    ("Programmet kører fra kildekoden – opdatér med 'git pull'.", "Running from source – update with 'git pull'."),
    ("Udgivelsen mangler programfilen – hent den manuelt fra GitHub.", "The release has no program file – download it from GitHub."),
    ("Den hentede fil er beskadiget (checksum passer ikke) – intet er ændret.", "The downloaded file is damaged (checksum mismatch) – nothing was changed."),
    ("Ingen udgivelser fundet endnu.", "No releases found yet."),
    ("Du har allerede den nyeste version.", "You already have the latest version."),
    ("GitHub svarede {}.", "GitHub answered {}."),
    # providers
    ("Ingen Mouser-nøgle – indtast en under Indstillinger.", "No Mouser key – enter one in Settings."),
    ("Mouser svarede ikke på kurv-forespørgslen.", "Mouser did not answer the cart request."),
    ("Ingen forbindelse: {}", "No connection: {}"),
    ("Ugyldigt svar fra serveren.", "Invalid answer from the server."),
    ("For mange forespørgsler (rate limit) – prøv igen om lidt.", "Too many requests (rate limit) – try again shortly."),
    ("Adgang nægtet ({}) – tjek API-nøglen. {}", "Access denied ({}) – check the API key. {}"),
    ("DigiKey login fejlede – tjek Client ID/Secret.", "DigiKey login failed – check Client ID/Secret."),
    ("Nexar login fejlede – tjek Client ID/Secret.", "Nexar login failed – check Client ID/Secret."),
    # progress
    ("Læser KiCad-projektet …", "Reading the KiCad project …"),
    ("Fandt {} komponenter i {} BOM-linjer.", "Found {} components in {} BOM lines."),
    ("Læser grosist-BOM {} …", "Reading distributor BOM {} …"),
    ("Ingen API-nøgler sat op – springer pris/lager-opslag over.", "No API keys set up – skipping price/stock lookups."),
    ("Henter priser og data ({}/{}) …", "Fetching prices and data ({}/{}) …"),
    ("Finder forslag til komponenter uden MPN ({}/{}) …", "Finding suggestions for parts without an MPN ({}/{}) …"),
    ("Kontrollerer footprints …", "Checking footprints …"),
    ("Læser datablade ({}/{}) …", "Reading datasheets ({}/{}) …"),
    ("Beregner antal og priser …", "Working out quantities and prices …"),
    ("Færdig.", "Done."),
    ("Starter …", "Starting …"),
    # project / BOM
    ("Ingen KiCad-filer fundet i det uploadede.", "No KiCad files found in the upload."),
    ("Fandt ingen .kicad_sch eller .kicad_pcb i det uploadede.", "No .kicad_sch or .kicad_pcb found in the upload."),
    ("Ingen skematisk fil – BOM er lavet ud fra PCB'en alene.", "No schematic – the BOM is built from the PCB alone."),
    ("Projektet bruger det gamle KiCad 5-format (.sch). Åbn det i KiCad 8/10 og gem det, så filerne bliver opdateret.",
     "The project uses the old KiCad 5 format (.sch). Open it in KiCad 8/10 and save it to update the files."),
    ("Under-ark '{}' mangler i det uploadede – komponenter derfra er ikke med.", "Sub-sheet '{}' is missing from the upload – its parts are not included."),
    ("Ikke annoteret (reference ender på '?').", "Not annotated (reference ends in '?')."),
    ("{} ({}) er på PCB'en men ikke i skematikken.", "{} ({}) is on the PCB but not in the schematic."),
    ("{} footprint(s) har en anden reference på PCB'en end i skematikken ({}{}). De er koblet via symbolets ID, så kontrollen er korrekt – kør 'Update PCB from Schematic', hvis det ikke er meningen.",
     "{} footprint(s) have a different reference on the PCB than in the schematic ({}{}). They are linked by the symbol ID, so the check is correct – run 'Update PCB from Schematic' if this is not intended."),
    ("Skematik siger footprint '{}', men PCB'en har '{}'. Kør 'Update PCB from Schematic'.", "The schematic says footprint '{}' but the PCB has '{}'. Run 'Update PCB from Schematic'."),
    ("Findes i skematik men ikke på PCB'en.", "In the schematic but not on the PCB."),
    ("MPN-feltet ('{}') indeholder '{}', som er et producentnavn – komponenten mangler et rigtigt varenummer.",
     "The MPN field ('{}') contains '{}', which is a manufacturer name – the part has no real part number."),
    ("MPN- og producent-felterne ser ud til at være byttet om ('{}' = '{}', '{}' = '{}') – bruger {} som MPN.",
     "The MPN and manufacturer fields look swapped ('{}' = '{}', '{}' = '{}') – using {} as the MPN."),
    ("mekanisk/grafik (købes ikke)", "mechanical/graphic (not purchased)"),
    ("'Exclude from BOM' er sat", "'Exclude from BOM' is set"),
    ("DNP (monteres ikke)", "DNP (not fitted)"),
    ("Ingen MPN-felt – prøver værdien '{}' som varenummer.", "No MPN field – trying the value '{}' as part number."),
    ("Samme MPN bruges med forskellige footprints: {}", "The same MPN is used with different footprints: {}"),
    # lookups
    ("Varenummeret blev ikke fundet hos de tilsluttede grosister.", "The part number was not found at the connected distributors."),
    ("Ikke på lager hos nogen af de tilsluttede grosister.", "Not in stock at any connected distributor."),
    ("Livscyklus: {} – overvej et alternativ.", "Lifecycle: {} – consider an alternative."),
    ("udgået/NRND", "obsolete/NRND"),
    ("{} er en {}, men symbolet ({}) er en {}: {}.", "{} is a {}, but the symbol ({}) is a {}: {}."),
    ("Værdi passer ikke: skematik siger {}, men {} er {}.", "Value mismatch: the schematic says {}, but {} is {}."),
    ("Intet MPN i projektet – billigste der opfylder {} {}: {} {}", "No MPN in the project – cheapest part meeting {} {}: {} {}"),
    ("Databladet kunne ikke læses: {}", "The datasheet could not be read: {}"),
    ("Databladet er mærket 'Not recommended for new design' (NRND).", "The datasheet is marked 'Not recommended for new design' (NRND)."),
    (" (fra BOM-fil)", " (from BOM file)"),
    ("fundet via {}", "found via {}"),
    ("grosist-API", "distributor API"),
    ("MPN-mønster ({})", "MPN pattern ({})"),
    ("symbolets Package-felt", "the symbol's Package field"),
    ("modstand", "resistor"), ("kondensator", "capacitor"), ("spole/ferrit", "inductor/ferrite"),
    # footprint checks
    ("Symbol-ben ↔ pads", "Symbol pins ↔ pads"),
    ("Navn ↔ komponentens pakke", "Name ↔ part package"),
    ("Navn ↔ egen geometri", "Name ↔ own geometry"),
    ("Pads ↔ komponentens fysiske mål", "Pads ↔ part's physical size"),
    ("Geometri ↔ {}", "Geometry ↔ {}"),
    ("Ens footprints", "Identical footprints"),
    ("Genkendt geometri", "Recognised geometry"),
    ("Datablad", "Datasheet"),
    ("Footprint", "Footprint"),
    ("Alle {} ben matcher en pad.", "All {} pins match a pad."),
    ("Ben {} ({}) har ingen egen pad, men deler navn med et ben der har – footprintet har slået dem sammen til én pad (samme forbindelse).",
     "Pins {} ({}) have no pad of their own but share a name with a pin that does – the footprint merges them into one pad (same connection)."),
    ("Symbolet har ben {} som ikke findes som pad i footprintet – de bliver ikke forbundet.", "The symbol has pins {} with no pad in the footprint – they will not be connected."),
    ("Footprintet har pads {} uden tilsvarende ben i symbolet (ofte OK for exposed pad/tab, men tjek det).", "The footprint has pads {} without a matching symbol pin (often OK for an exposed pad/tab, but check)."),
    ("Alle {} ben har en pad. Pad {} er en exposed/thermal pad uden ben i symbolet – tjek i databladet om den skal forbindes (typisk GND).",
     "All {} pins have a pad. Pad {} is an exposed/thermal pad without a symbol pin – check the datasheet whether it must be connected (usually GND)."),
    ("Alle {} ben har en pad. Ekstra mekaniske pads: {}.", "All {} pins have a pad. Extra mechanical pads: {}."),
    ("Komponenten har intet footprint.", "The part has no footprint."),
    ("Navnet siger ikke pakken, men antal pads ({}) passer med {}.", "The name doesn't give the package, but the pad count ({}) matches {}."),
    ("Footprintet har {} pads, men komponenten er {}.", "The footprint has {} pads, but the part is {}."),
    ("navnet siger {} ben men der er {} pads", "the name says {} pins but there are {} pads"),
    ("navnet siger pitch {} mm men målt er {} mm", "the name says pitch {} mm but it measures {} mm"),
    ("Geometrien passer med navnet ({} pads", "The geometry matches the name ({} pads"),
    (", pitch {} mm", ", pitch {} mm"),
    (" (Pakke fra {}: '{}')", " (Package from {}: '{}')"),
    ("Footprintet på PCB'en afviger fra biblioteket (redigeret lokalt?): ", "The footprint on the PCB differs from the library (edited locally?): "),
    ("{} af {} pads parret; største placeringsfejl {} mm, største størrelsesforskel {} mm", "{} of {} pads paired; largest position error {} mm, largest size difference {} mm"),
    (" (reference drejet {}°", " (reference rotated {}°"),
    (", spejlet – normalt for bundside)", ", mirrored – normal for the bottom side)"),
    (", spejlet)", ", mirrored)"),
    (". Antal pads: dit footprint {}, reference {}", ". Pad count: your footprint {}, reference {}"),
    (". Pads i reference men ikke hos dig: {}", ". Pads in the reference but not in yours: {}"),
    (". Ekstra pads hos dig: {}", ". Extra pads in yours: {}"),
    (". OBS: passer kun spejlvendt – tjek at pin 1 og pinout ikke er byttet om", ". NOTE: only fits mirrored – check that pin 1 and the pinout are not swapped"),
    ("Ingen pads at sammenligne.", "No pads to compare."),
    ("Pads kunne ikke parres.", "Pads could not be paired."),
    ("Pads passer fysisk til en {} ({}x{} mm).", "Pads physically fit a {} ({}x{} mm)."),
    ("pads rammer ikke komponentens terminaler ordentligt (overlap {} mm af {} mm)", "pads don't land properly on the part's terminals (overlap {} mm of {} mm)"),
    ("pad-mønstret ({} mm) er kortere end komponenten ({} mm)", "the pad pattern ({} mm) is shorter than the part ({} mm)"),
    ("pads er {} mm brede, komponenten er {} mm", "pads are {} mm wide, the part is {} mm"),
    ("afstanden mellem pads er kun {} mm (kortslutningsrisiko)", "the gap between pads is only {} mm (risk of shorts)"),
    ("lille overlap med terminalerne ({} mm af {} mm)", "small overlap with the terminals ({} mm of {} mm)"),
    ("pads går {} mm ud over komponenten (risiko for tombstoning)", "pads extend {} mm beyond the part (tombstoning risk)"),
    ("pads er smalle ({} mm mod komponentbredde {} mm)", "pads are narrow ({} mm vs part width {} mm)"),
    ("Komponenterne i denne linje har ikke helt ens pads på PCB'en (et footprint er redigeret lokalt?).", "The parts in this line don't have identical pads on the PCB (a footprint edited locally?)."),
    ("Samme geometri som KiCad-bibliotekets {} ({} % ens).", "Same geometry as the KiCad library's {} ({} % alike)."),
    (" Men navnet siger {} – navnet passer ikke med geometrien.", " But the name says {} – the name doesn't match the geometry."),
    (" Komponenten er {}: {}", " The part is {}: {}"),
    (" Passer med komponentens pakke ({}).", " Matches the part's package ({})."),
    ("KiCad-bibliotek: {}", "KiCad library: {}"),
    ("IPC-7351 nominel {} ({} metrisk)", "IPC-7351 nominal {} ({} metric)"),
    ("producent/CAD-fil ({})", "manufacturer CAD file ({})"),
    # packages
    ("Pakken kunne ikke aflæses fra begge sider.", "The package could not be read from both sides."),
    ("{} og {} er forskellige pakketyper.", "{} and {} are different package types."),
    ("Pakketype {} passer ikke med {}.", "Package type {} doesn't match {}."),
    ("Samme pakketype ({}), men antal ben kunne ikke bekræftes.", "Same package type ({}), but the pin count could not be confirmed."),
    ("Footprint er {} men komponenten er {} ({} metrisk).", "The footprint is {} but the part is {} ({} metric)."),
    ("Antal ben: footprint {}, komponent {}.", "Pin count: footprint {}, part {}."),
    ("Pitch: footprint {} mm, komponent {} mm.", "Pitch: footprint {} mm, part {} mm."),
    ("Kropsstørrelse: footprint {}x{} mm, komponent {}x{} mm.", "Body size: footprint {}x{} mm, part {}x{} mm."),
    ("Kropsbredde: footprint {} mm, komponent {} mm (smal/bred variant?).", "Body width: footprint {} mm, part {} mm (narrow/wide variant?)."),
    ("Begge er {} ({} metrisk).", "Both are {} ({} metric)."),
    ("Samme pakke ({}", "Same package ({}"),
    (", {} ben)", ", {} pins)"),
    ("{} ({} metrisk)", "{} ({} metric)"),
    # datasheet
    ("Databladet nævner {} – ikke {}. Tjek at det er det rigtige datablad/pakke.", "The datasheet mentions {} – not {}. Check that it is the right datasheet/package."),
    ("Ingen gyldig datablad-URL.", "No valid datasheet URL."),
    ("Databladets tekst kunne ikke læses (scannet eller specielle skrifttyper) – se tegningen selv.", "The datasheet text could not be read (scanned or special fonts) – look at the drawing yourself."),
    ("Databladets tekst kunne ikke læses (scannet eller specielle skrifttyper).", "The datasheet text could not be read (scanned or special fonts)."),
    ("Footprintets pakke kunne ikke aflæses.", "The footprint's package could not be read."),
    ("Ingen pakkenavne fundet i databladet.", "No package names found in the datasheet."),
    ("Footprintets pakke ({}) findes i databladet (nævner: {}).", "The footprint's package ({}) is in the datasheet (mentions: {})."),
    ("Kunne ikke hente databladet (HTTP {}).", "Could not download the datasheet (HTTP {})."),
    ("Kunne ikke hente databladet ({}).", "Could not download the datasheet ({})."),
    ("Databladet nævner slet ikke {} – linket peger sandsynligvis på et forkert datablad.", "The datasheet doesn't mention {} at all – the link probably points to the wrong datasheet."),
    ("Databladet angiver {} for {} – passer med footprintet.", "The datasheet gives {} for {} – matches the footprint."),
    ("Databladet angiver {} for {}, men footprintet er {}.", "The datasheet gives {} for {}, but the footprint is {}."),
    ("Linket peger på en webside, ikke et PDF-datablad.", "The link points to a web page, not a PDF datasheet."),
    (" (fundet ud fra grundnummeret – tjek bestillingstabellen)", " (found from the base number – check the ordering table)"),
    # compare window
    ("Ingen datablad-link på komponenten – kun footprintets egne mål kan vises.", "No datasheet link on the part – only the footprint's own measures can be shown."),
    ("Ingen mål-tabel fundet som tekst – målene står kun på tegningen (se siden herunder).", "No dimension table found as text – the dimensions are only on the drawing."),
    ("Ingen pin-tabel fundet i databladet.", "No pin table found in the datasheet."),
    ("{} ens, {} samme type, {} forskellige, {} ikke i tabellen.", "{} identical, {} same type, {} different, {} not in the table."),
    ("Databladet har mål-tabeller for {}, men ingen for {}.", "The datasheet has dimension tables for {}, but none for {}."),
    ("tabel s. {}, valgt ud fra pitch", "table p. {}, chosen by pitch"),
    ("Databladet (s. {}) → IPC-7351", "Datasheet (p. {}) → IPC-7351"),
    ("Pin-tabellen i databladet kunne ikke læses sikkert – tjek benene på tegningen.", "The datasheet's pin table could not be read reliably – check the pins on the drawing."),
    ("Komponentens størrelse: {} (IPC, KiCad-biblioteket)", "The part's real size: {} (IPC, KiCad library)"),
    ("KiCad-bibliotekets footprint til {} (efter producentens tegning)", "KiCad library footprint for {} (made from the maker's drawing)"),
    ("Pakken fra grosisten: {} (KiCad-biblioteket)", "Package given by the distributor: {} (KiCad library)"),
    ("IPC-7351 (nominel): tå {} mm, hæl {} mm, side {} mm", "IPC-7351 (nominal): toe {} mm, heel {} mm, side {} mm"),
    ("Pitch (e)", "Pitch (e)"),
    ("Samme pitch.", "Same pitch."),
    ("Pitch passer ikke – benene rammer ikke padsene.", "Pitch doesn't match – the leads miss the pads."),
    ("Benbredde (b) ↔ padbredde", "Lead width (b) ↔ pad width"),
    ("Padden er mindst lige så bred som benet.", "The pad is at least as wide as the lead."),
    ("Padden er smallere end benets max-bredde.", "The pad is narrower than the lead's max width."),
    ("Padden er smallere end benet.", "The pad is narrower than the lead."),
    ("Padsene er så brede at der næsten ikke er luft imellem (risiko for kortslutning).", "The pads are so wide there is hardly any gap (risk of shorts)."),
    ("Kropsbredde ↔ padsenes yderkant", "Body width ↔ outer pad edge"),
    ("Padsene går ud til kroppens kant.", "The pads reach the body edge."),
    ("Padsene stopper inden kroppens kant.", "The pads stop before the body edge."),
    ("Terminal (L) ↔ padsenes inderkant", "Terminal (L) ↔ inner pad edge"),
    ("Padsene dækker terminalerne.", "The pads cover the terminals."),
    ("Padsene dækker ikke hele terminalens længde.", "The pads don't cover the whole terminal length."),
    ("Benspænd (E) ↔ padsenes yderkant", "Lead span (E) ↔ outer pad edge"),
    ("Benenes spidser ligger inden for padsene.", "The lead tips are inside the pads."),
    ("Benenes spidser kan nå ud over padsene ved max-mål.", "The lead tips may reach past the pads at max dimensions."),
    ("Benene stikker ud over padsene.", "The leads stick out past the pads."),
    ("Benets fod (L) ↔ padsenes inderkant", "Lead foot (L) ↔ inner pad edge"),
    ("Hele foden ligger på padden.", "The whole foot is on the pad."),
    ("Hælen ligger tæt på padsenes inderkant.", "The heel is close to the inner pad edge."),
    ("Benets fod rammer kun delvist padden.", "The lead foot only partly lands on the pad."),
    ("Eksponeret pad (D2×E2)", "Exposed pad (D2×E2)"),
    ("Termisk pad passer.", "The thermal pad fits."),
    ("Termisk pad afviger fra pakkens.", "The thermal pad differs from the package's."),
    ("Pakken har en termisk pad, footprintet har ikke.", "The package has a thermal pad, the footprint doesn't."),
    ("Krop (D × E1)", "Body (D × E1)"),
    ("Kroppens omrids på Fab-laget passer.", "The body outline on the Fab layer matches."),
    ("Fab-lagets omrids afviger.", "The Fab layer outline differs."),
    ("{} × {} (Fab-lag)", "{} × {} (Fab layer)"),
    ("Intet mål i footprintet svarer til denne værdi – se tegningen.", "No measure in the footprint equals this value – see the drawing."),
    ("inderkant (gap)", "inner edge (gap)"), ("centerafstand", "centre distance"), ("termisk pad", "thermal pad"),
    ("padlængde", "pad length"), ("padbredde", "pad width"), ("yderkant", "outer edge"),
    ("ukendt pakke", "unknown package"),
    # distributor BOM
    ("Ukendt grosist", "Unknown distributor"),
    ("BOM-fil", "BOM file"),
    ("Kunne ikke finde varenumre/antal i filen.", "Could not find part numbers/quantities in the file."),
    ("værdi + pakke", "value + package"),
    ("grosist-varenr.", "distributor P/N"),
    ("reference (R1, C3 …)", "reference (R1, C3 …)"),
    ("Antal ikke angivet i grosist-BOM'en.", "Quantity not given in the distributor BOM."),
    ("Bestilt {}, men der skal bruges {}. Mangler {}.", "Ordered {}, but {} are needed. {} short."),
    ("Bestilt {} – dækker behovet ({}). Overvej {} ekstra som reserve.", "Ordered {} – covers the need ({}). Consider {} extra as spares."),
    ("Bestilt {}, behov {}", "Ordered {}, needed {}"),
    (" + reserve = {}.", " + spares = {}."),
    ("Findes ikke i grosist-BOM'en.", "Not in the distributor BOM."),
    ("Varenummer afviger let: projekt '{}', grosist '{}' (emballage/variant – tjek at det er den rigtige).", "Part number differs slightly: project '{}', distributor '{}' (packaging/variant – check it is the right one)."),
    ("Matchet via {}, men MPN er forskellig: projekt '{}', grosist '{}'.", "Matched via {}, but the MPN differs: project '{}', distributor '{}'."),
    ("Projektet har intet MPN; matchet på værdi og pakke i beskrivelsen.", "The project has no MPN; matched on value and package in the description."),
    # pricing
    ("Minimumskøb er {} stk.", "Minimum order is {} pcs."),
    ("Køb {} i stedet for {}: det koster {} mindre ({} → {}) og du får {} ekstra.", "Buy {} instead of {}: it costs {} less ({} → {}) and you get {} extra."),
    ("For kun {} mere får du {} stk. ({} ekstra, {}/stk.).", "For only {} more you get {} pcs ({} extra, {}/pc)."),
    (" Kun {} på lager.", " Only {} in stock."),
    ("Kun hel rulle/pakning: mindst {} stk. ({} {}).", "Full reel/pack only: at least {} pcs ({} {})."),
    ("Købes hos {} i stedet for {}: lidt dyrere her, men det sparer fragt.", "Bought from {} instead of {}: a little more here, but it saves freight."),
    # alternatives
    ("Erstatninger fra grosisterne og søgning på \"{}\".", "Substitutes from the distributors and a search for \"{}\"."),
    ("Erstatninger fra grosisterne.", "Substitutes from the distributors."),
    ("Passer IKKE på dit footprint: {} (dit footprint er {}).", "Does NOT fit your footprint: {} (your footprint is {})."),
    ("Passer IKKE på dit footprint: {}", "Does NOT fit your footprint: {}"),
    ("Pakken kunne ikke sammenlignes – kontrollér footprint, pinout og elektriske data.", "The package could not be compared – check footprint, pinout and electrical data."),
    ("Passer på dit footprint ({}). Kontrollér stadig pinout og elektriske data.", "Fits your footprint ({}). Still check pinout and electrical data."),
    ("Samme pakketype ({}), men antal ben kunne ikke bekræftes. Kontrollér pinout.", "Same package type ({}), but the pin count could not be confirmed. Check the pinout."),
    ("Samme størrelse som dit footprint ({} × {} mm). Kontrollér padplacering og pinout i databladet.", "Same size as your footprint ({} × {} mm). Check pad positions and pinout in the datasheet."),
    ("Anden størrelse: {} × {} mm, dit footprint er {} × {} mm.", "Different size: {} × {} mm, your footprint is {} × {} mm."),
    ("Kunne ikke bestemme chip-størrelsen ud fra footprintet.", "Could not tell the chip size from the footprint."),
    ("Den valgte komponent er {}, men footprintet er {} – der søges {} med samme værdi og mindst lige gode specs.", "The chosen part is {}, but the footprint is {} – searching {} with the same value and at least as good specs."),
    ("Krav: {}.", "Requirements: {}."),
    ("Intet MPN at søge alternativer ud fra.", "No MPN to search alternatives from."),
    ("Erstatning ifølge {} ({})", "Substitute according to {} ({})"),
    ("Erstatning ifølge {}", "Substitute according to {}"),
    ("Ingen alternativer fundet hos de tilsluttede grosister.", "No alternatives found at the connected distributors."),
    ("Lignende funktion (søgning)", "Similar function (search)"),
    ("Samme pinout ifølge databladet ({} af {} ben).", "Same pinout according to the datasheet ({} of {} pins)."),
    ("Pinout kun delvist bekræftet ({} af {} ben fundet i databladet).", "Pinout only partly confirmed ({} of {} pins found in the datasheet)."),
    ("Anden pinout: {}", "Different pinout: {}"),
    ("ben {} er {} (din: {})", "pin {} is {} (yours: {})"),
    ("Ikke verificeret ud fra grosistens data: {}.", "Not verified from the distributor's data: {}."),
    ("spænding", "voltage"), ("strøm", "current"), ("effekt", "power"), ("dielektrikum", "dielectric"),
    ("KiCad-bibliotekets {} er magen til dit footprint.", "The KiCad library's {} is the same as your footprint."),
    ("KiCad-bibliotekets {} ligner dit footprint: {}", "The KiCad library's {} is similar to your footprint: {}"),
    ("Passer IKKE på dit footprint: KiCad-bibliotekets {} er anderledes ({})", "Does NOT fit your footprint: the KiCad library's {} is different ({})"),
    ("Alternativer kræver mindst én grosist-API-nøgle (Indstillinger).", "Alternatives need at least one distributor API key (Settings)."),
    # export
    ("Erstatter {} i indkøbet (KiCad-projektet er uændret).", "Replaces {} in the purchase (the KiCad project is unchanged)."),
    ("Alternativ valgt: {}", "Alternative chosen: {}"),
    ("Matcher kurven", "Matches the cart"), ("Mangler i kurven", "Missing from the cart"), ("Afviger fra kurven", "Differs from the cart"),
    ("Kun hel rulle ({} stk.)", "Full reel only ({} pcs)"), ("Kun {} på lager", "Only {} in stock"),
    ("Ikke på lager", "Out of stock"), ("Ingen indkøbsdata", "No purchase data"),
    ("I alt (valgt indkøb)", "Total (chosen purchase)"),
]

# Words that are also translated inside longer texts (lists of unverified specs).
SUBWORDS = {"spænding", "strøm", "effekt", "dielektrikum", "grosist-API", ", spejlet)", " (fra BOM-fil)",
            ", spejlet – normalt for bundside)", "symbolets Package-felt", "udgået/NRND"}

# Excel and status words: whole-string only
WORDS = {
    "OK": "OK", "Advarsel": "Warning", "Delvis": "Partial", "Fejl": "Error", "Mangler": "Missing", "Ukendt": "Unknown",
    "Pos": "Pos", "Antal pr. print": "Qty per board", "Behov": "Need", "Referencer": "References", "Værdi": "Value",
    "Beskrivelse": "Description", "Producent": "Manufacturer", "Pakke": "Package", "Grosist": "Distributor",
    "Varenr.": "Distributor P/N", "Køb (stk.)": "Buy (pcs)", "Stykpris": "Unit price", "Linjepris": "Line total",
    "Valuta": "Currency", "Lager": "Stock", "Livscyklus": "Lifecycle", "1 Footprint": "1 Footprint",
    "2 Datablad": "2 Datasheet", "3 Indkøb": "3 Purchase", "Bemærkninger": "Notes", "Indkøb": "Purchase",
    "Antal": "Qty", "I alt": "Total", "Udeladt": "Excluded", "Reference": "Reference", "Hvorfor": "Why",
    "Projekt": "Project", "Komponenter": "Components", "BOM-linjer": "BOM lines", "Print": "Boards",
    "KiCad skematik": "KiCad schematic", "Grosist-BOM": "Distributor BOM",
}


def _compile():
    pats = []
    for da, en in T:
        holes = da.count("{}")
        if holes == 0 and len(da) < 25 and da not in SUBWORDS:
            continue          # short fixed words: whole-string match only (see EXACT)
        rx = re.escape(da).replace(r"\{\}", "(.+?)")
        if da.endswith("{}"):
            rx = rx[:-len("(.+?)")] + "(.+)"
        if da in SUBWORDS:
            rx = (r"\b" if da[0].isalnum() else "") + rx + (r"\b" if da[-1].isalnum() else "")
        rep = en
        n = 0
        while "{}" in rep:
            rep = rep.replace("{}", f"\\g<{n + 1}>", 1)
            n += 1
        for i in range(holes):
            rep = rep.replace("{" + str(i) + "}", f"\\g<{i + 1}>")
        pats.append((len(da), re.compile(rx), rep))
    pats.sort(key=lambda p: -p[0])
    return [(rx, rep) for _, rx, rep in pats]


_PATS = _compile()
EXACT = {da: en for da, en in T if da.count("{}") == 0}
EXACT.update(WORDS)
# Strings that contain one of these are worth running the patterns on (most data strings aren't).
_HINT = re.compile(r"[æøåÆØÅ↔]|\b(?:ikke|er|og|men|til|fra|med|kan|ben|pads?|stk|mm|af|på|som|Bestilt|Pakke|Krav|Erstatning|"
                   r"Datablad|Køb|For kun|Kun|Samme|Ingen|Kunne|Footprintet|Navnet|Symbolet|Alle|Geometri|Pitch|Padden|"
                   r"Padsene|Benene|Benets|Hælen|Hele|Fandt|Henter|Finder|Læser|Kontrollerer|Beregner|Starter|Stopper)\b")

SKIP_KEYS = {"mpn", "mfr", "footprint", "lib_id", "refs", "ref", "sku", "url", "datasheet", "id", "photo", "dist_pn",
             "seller", "source", "value", "history_id", "lifecycle", "category", "file", "name", "label_raw", "path"}


def tr(s):
    if not isinstance(s, str) or not s:
        return s
    if s in EXACT:
        return EXACT[s]
    if not _HINT.search(s):
        return s
    for rx, rep in _PATS:
        if rx.search(s):
            s = rx.sub(rep, s)
    return s


def translate(obj, lang="en", key=None):
    """Translate every message in a result (dicts/lists/strings). Danish is returned unchanged."""
    if lang != "en":
        return obj
    if isinstance(obj, str):
        return obj if key in SKIP_KEYS else tr(obj)
    if isinstance(obj, list):
        return [translate(v, lang, key) for v in obj]
    if isinstance(obj, tuple):
        return [translate(v, lang, key) for v in obj]
    if isinstance(obj, dict):
        return {k: translate(v, lang, k) for k, v in obj.items()}
    return obj
