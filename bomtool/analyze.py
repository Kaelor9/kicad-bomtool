"""The full analysis pipeline. Runs in a background thread and reports progress."""
import io
import posixpath
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor

from . import alternatives, bom, datasheet, distbom, footprint, fplib, packages as P, pricing
from . import fields as F
from .kicad import Project, load_kicad_mod
from .providers import ProviderError, make_providers
from .vfs import ProjectFiles


def _load_references(files):
    """Manufacturer footprints (.kicad_mod, .pretty folders or zips of them)."""
    refs = []
    for name, data in files:
        if data[:4] == b"PK\x03\x04":
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                for info in zf.infolist():
                    if info.filename.lower().endswith(".kicad_mod") and info.file_size < 5_000_000:
                        geo, fpname = load_kicad_mod(zf.read(info).decode("utf-8", "replace"))
                        if geo:
                            refs.append({"file": posixpath.basename(info.filename), "name": fpname, "geo": geo})
        elif name.lower().endswith(".kicad_mod"):
            geo, fpname = load_kicad_mod(data.decode("utf-8", "replace"))
            if geo:
                refs.append({"file": name, "name": fpname, "geo": geo})
    return refs


def _ref_for_line(line, refs):
    mpn = bom.norm_mpn(line.get("mpn") or "")
    fpname = line["footprint"].split(":")[-1].lower()
    for r in refs:
        key = bom.norm_mpn(r["file"].rsplit(".", 1)[0]) + " " + bom.norm_mpn(r["name"])
        if mpn and len(mpn) >= 4 and mpn in key:
            return r
    for r in refs:
        if r["name"].split(":")[-1].lower() == fpname or r["file"].lower() == fpname + ".kicad_mod":
            return r
    return None


def part_kind(part):
    """R/C/L judged from a distributor's data, or None if it's something else / unclear."""
    params = part.get("params") or {}
    if params.get("Resistance"):
        return "R"
    if params.get("Capacitance"):
        return "C"
    if params.get("Inductance") or params.get("Impedance @ Frequency"):
        return "L"
    text = (part.get("category", "") + " " + part.get("desc", "")).upper()
    if re.search(r"\bRES\b|RESISTOR", text):
        return "R"
    if re.search(r"\bCAP\b|CAPACITOR|MLCC", text):
        return "C"
    if re.search(r"\bIND\b|INDUCTOR|FERRITE|CHOKE", text):
        return "L"
    return None


def _best_part(parts, wanted):
    w = F.key(wanted)
    for p in parts:
        if F.key(p["mpn"]) == w:
            return p
    for p in parts:
        if F.key(p.get("dist_pn", "")) == w:
            return p
    for p in parts:
        k = F.key(p["mpn"])
        if len(w) >= 6 and (k.startswith(w) or w.startswith(k)) and abs(len(k) - len(w)) <= 4:
            return p
    return None


class Cancelled(Exception):
    """Raised from the progress callback when the user stops the analysis."""


class Analysis:
    def __init__(self, project_files, dist_files, ref_files, settings, cfg, progress):
        self.project_files = project_files
        self.dist_files = dist_files
        self.ref_files = ref_files
        self.settings = settings
        self.cfg = cfg
        self.progress = progress
        self.providers = make_providers(cfg) if settings.get("use_api", True) else []
        self.errors = []

    def run(self):
        self.progress("Læser KiCad-projektet …", 2)
        vfs = None
        for name, data in self.project_files:
            part = ProjectFiles.from_upload(name, data)
            if vfs is None:
                vfs = part
            else:
                vfs.merge(part)
        if vfs is None or not vfs.files:
            raise ValueError("Ingen KiCad-filer fundet i det uploadede.")
        project = Project(vfs).load()
        comps = {c["ref"]: c for c in project.components}
        lines, excluded = bom.build(project.components)
        self.progress(f"Fandt {len(project.components)} komponenter i {len(lines)} BOM-linjer.", 10)

        refs = _load_references(self.ref_files)

        # Distributor BOMs
        project_mpns = {bom.norm_mpn(l["mpn"]) for l in lines if l["mpn"]}
        dist_boms = []
        for name, data in self.dist_files:
            self.progress(f"Læser grosist-BOM {name} …", 12)
            try:
                d = distbom.load(name, data, project_mpns)
            except Exception as e:  # noqa: BLE001 - report any parse failure to the user
                self.errors.append(f"{name}: {e}")
                continue
            results, extras = distbom.match(lines, d)
            d["results"] = {r["id"]: r for r in results}
            d["extras"] = extras
            dist_boms.append(d)

        # API lookups
        if self.providers:
            self._lookup_all(lines)
        elif self.settings.get("use_api", True):
            self.progress("Ingen API-nøgler sat op – springer pris/lager-opslag over.", 60)

        self.progress("Kontrollerer footprints …", 75)
        for line in lines:
            self._footprint(line, comps, refs, dist_boms)
        if self.settings.get("check_datasheets", True):
            self._datasheets(lines)

        self.progress("Beregner antal og priser …", 88)
        for line in lines:
            need, need_spare = pricing.need_for(line, self.settings)
            line["need"], line["need_spare"] = need, need_spare
            offers = list(line.get("offers") or [])
            for d in dist_boms:
                r = d["results"].get(line["id"])
                if r and r.get("dist_line"):
                    dl = r["dist_line"]
                    r["qty_status"], r["qty_msg"] = distbom.check_quantity(need, need_spare, dl["qty"])
                    if r["qty_status"] in ("mismatch", "warn") and r["status"] == "ok":
                        r["status"] = r["qty_status"]
                    # Prices from the uploaded BOM count when the API has nothing for that seller
                    if dl.get("unit_price") and not any(o["seller"] == d["distributor"] for o in offers):
                        offers.append({"seller": d["distributor"] + " (fra BOM-fil)", "sku": dl["dist_pn"],
                                       "packaging": "", "moq": 1, "mult": 1, "stock": None,
                                       "currency": dl.get("currency") or d.get("currency") or "",
                                       "breaks": [[1, dl["unit_price"]]], "url": "", "reel_fee": False})
            line["plan"] = pricing.plan_line(offers, need_spare, self.settings) if offers else None
            line.pop("offers", None)
            line["status"] = self._line_status(line, dist_boms)

        rules = pricing.order_rules(self.cfg, self.settings.get("shipping", 0))
        consolidated = pricing.consolidate(lines, rules)
        summary = self._summary(lines, excluded, dist_boms, project)
        self.progress("Færdig.", 100)
        for line in lines:
            line.pop("api_parts", None)
        return {
            "project": {"name": project.name, "version": project.version, "warnings": project.warnings,
                        "components": len(project.components)},
            "lines": lines, "excluded": excluded,
            "dist_boms": [{k: v for k, v in d.items()} for d in dist_boms],
            "references": [{"file": r["file"], "name": r["name"]} for r in refs],
            "totals": dict(pricing.totals(lines), shipping=consolidated, order=pricing.order(lines, rules)),
            "order_rules": rules, "summary": summary, "errors": self.errors,
            "providers": [p.name for p in self.providers], "settings": self.settings,
            # For the board view: outline + each placed part [x, y, rot, bottom, cx, cy, half w, half h]
            "board": {"outline": project.board_outline,
                      "parts": {c["ref"]: c["pcb_pos"] for c in project.components if c.get("pcb_pos")},
                      "pads": {c["ref"]: c["pcb_pads"] for c in project.components if c.get("pcb_pads")}},
        }

    # -- API ---------------------------------------------------------------------
    def _lookup_all(self, lines):
        todo = [l for l in lines if l["mpn"] or l.get("mpn_guess") or l["dist"]]
        done = [0]

        def work(line):
            try:
                self._lookup(line)
            finally:
                done[0] += 1
                self.progress(f"Henter priser og data ({done[0]}/{len(todo)}) …", 15 + 55 * done[0] / max(1, len(todo)))

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(work, todo))
        # Passives without an MPN: propose the cheapest part that meets the spec.
        nompn = [l for l in lines if not l["mpn"] and l["kind"] and l.get("parsed")]
        for i, line in enumerate(nompn):
            if not self.settings.get("suggest_mpn", True):
                break
            self.progress(f"Finder forslag til komponenter uden MPN ({i + 1}/{len(nompn)}) …",
                          70 + 5 * (i + 1) / max(1, len(nompn)))
            need = pricing.need_for(line, self.settings)[1]
            res = alternatives.find(line, self.providers, need, self.settings, limit=3)
            if res["items"]:
                line["suggested"] = res["items"][:3]
                best = res["items"][0]
                line["offers"] = []
                # Price the suggestion so the cart total is complete.
                line["suggested_note"] = (f"Intet MPN i projektet – billigste der opfylder "
                                          f"{F.format_value(line['parsed']['value'], line['kind'])} "
                                          f"{line['footprint'].split(':')[-1]}: {best['mfr']} {best['mpn']}")
                for prov in self.providers:
                    try:
                        part = _best_part(prov.lookup(best["mpn"]), best["mpn"])
                    except ProviderError:
                        continue
                    if part:
                        line["offers"].extend(part["offers"])

    def _lookup(self, line):
        wanted = line["mpn"] or line.get("mpn_guess") or ""
        found = []
        line["offers"] = []
        for prov in self.providers:
            keys = [wanted] if wanted else []
            dist_key = {"DigiKey": "digikey", "Mouser": "mouser"}.get(prov.name)
            if dist_key and line["dist"].get(dist_key):
                keys.insert(0, line["dist"][dist_key])
            part = None
            for k in keys:
                try:
                    part = _best_part(prov.lookup(k), k)
                except ProviderError as e:
                    msg = f"{prov.name}: {e}"
                    if msg not in self.errors:
                        self.errors.append(msg)
                    break
                if part:
                    break
            if part:
                found.append(part)
                line["offers"].extend(part["offers"])
        line["api"] = [{"source": p["source"], "mpn": p["mpn"], "mfr": p["mfr"], "desc": p["desc"],
                        "package": p["package"], "url": p["url"], "stock": p["stock"],
                        "lifecycle": p["lifecycle"], "category": p.get("category", "")} for p in found]
        if not found:
            if wanted:
                line["warnings"].append("Varenummeret blev ikke fundet hos de tilsluttede grosister.")
            return
        first = found[0]
        if not line["mpn"] and first["mpn"]:
            line["mpn"], line["mpn_field"] = first["mpn"], f"fundet via {first['source']}"
            line.pop("mpn_guess", None)
        if not line["mfr"]:
            line["mfr"] = first["mfr"]
        if not line["datasheet"]:
            line["datasheet"] = next((p["datasheet"] for p in found if p.get("datasheet")), "")
            if line["datasheet"].startswith("//"):
                line["datasheet"] = "https:" + line["datasheet"]
        line["desc"] = first["desc"]
        line["api_category"] = first.get("category", "")
        # Body size and mounting of the chosen part - what its footprint was made for
        line["api_size"] = alternatives._size(first.get("params"))
        line["api_mounting"] = next((v for k, v in (first.get("params") or {}).items()
                                     if k.lower().startswith("mounting")), "")
        line["api_package"] = next((p["package"] for p in found if p.get("package")), "") or \
            next((p["desc"] for p in found if P.parse_package(p["desc"] or "")), "")
        lc = " ".join(p.get("lifecycle", "") for p in found).lower()
        if any(x in lc for x in ("obsolete", "discontinued", "not recommended", "nrnd", "end of life", "eol")):
            line["warnings"].append(f"Livscyklus: {found[0].get('lifecycle') or 'udgået/NRND'} – overvej et alternativ.")
        if sum(p.get("stock") or 0 for p in found) == 0:
            line["warnings"].append("Ikke på lager hos nogen af de tilsluttede grosister.")
        # Does the part's real value / type match the schematic?
        if line["kind"] and line.get("parsed"):
            actual = part_kind(first)
            names = {"R": "modstand", "C": "kondensator", "L": "spole/ferrit"}
            if actual and actual != line["kind"]:
                line["warnings"].append(
                    f"{line['mpn']} er en {names[actual]}, men symbolet ({line['refs'][0]}) er en "
                    f"{names[line['kind']]}: {first.get('desc') or first.get('category')}.")
            else:
                specs = alternatives.candidate_specs(first, line["kind"])
                # The chosen part's ratings, so alternatives can match them (voltage, dielectric, tolerance ...)
                line["api_specs"] = {k: v for k, v in specs.items() if k not in ("value", "chip") and v is not None}
                if specs.get("value") is not None and abs(specs["value"] - line["parsed"]["value"]) > \
                        abs(line["parsed"]["value"]) * 0.001 + 1e-15:
                    line["warnings"].append(
                        f"Værdi passer ikke: skematik siger {F.format_value(line['parsed']['value'], line['kind'])}, "
                        f"men {line['mpn']} er {F.format_value(specs['value'], line['kind'])}.")

    # -- footprint -----------------------------------------------------------------
    def _footprint(self, line, comps, refs, dist_boms):
        comp = comps.get(line["refs"][0])
        if comp is None:
            return
        # Where do we learn the part's real package? Best source first.
        pkg_text, pkg_src = "", ""
        if line.get("api_package") and P.parse_package(line["api_package"]):
            pkg_text, pkg_src = line["api_package"], "grosist-API"
        if not pkg_text:
            for d in dist_boms:
                r = d["results"].get(line["id"])
                if r and r.get("dist_line"):
                    dl = r["dist_line"]
                    for txt in (dl.get("package"), dl.get("desc")):
                        if txt and P.parse_package(txt):
                            pkg_text, pkg_src = txt, f"{d['distributor']}-BOM"
                            break
                if pkg_text:
                    break
        if not pkg_text and line.get("mpn_hint_pkg"):
            pkg_text, pkg_src = line["mpn_hint_pkg"], f"MPN-mønster ({line['mpn']})"
        if not pkg_text and line.get("package_field") and P.parse_package(line["package_field"]):
            pkg_text, pkg_src = line["package_field"], "symbolets Package-felt"
        ref = _ref_for_line(line, refs)
        rep = footprint.report(comp, pkg_text or None, pkg_src, ref["geo"] if ref else None,
                               ref["file"] if ref else "")
        # Different geometry across components of the same line?
        geos = {self._geo_sig(comps[r].get("geometry")) for r in line["refs"] if r in comps}
        if len(geos) > 1:
            rep["checks"].append({"check": "Ens footprints", "status": "warn",
                                  "msg": "Komponenterne i denne linje har ikke helt ens pads på PCB'en "
                                         "(et footprint er redigeret lokalt?)."})
            if rep["status"] == "ok":
                rep["status"] = "warn"
        rep["geometry"] = comp.get("geometry")
        line["pin_names"] = comp.get("pin_names") or {}
        self._recognise(rep, pkg_text)
        rep["geometry_source"] = comp.get("geometry_source", "")
        line["fp"] = rep
        for w in comp.get("warnings", []):
            if w not in line["warnings"]:
                line["warnings"].append(w)

    @staticmethod
    def _recognise(rep, part_pkg_text):
        """Which KiCad library footprint has the same geometry? Catches footprints with meaningless or
        wrong names: the geometry tells what package it really is."""
        if not fplib.status()["ready"] or not (rep.get("geometry") or {}).get("pads"):
            return
        found = fplib.recognise(rep["geometry"])
        if not found:
            return
        rep["recognised"] = found
        best = found[0]
        rec_pkg = P.parse_package(best["id"].split(":", 1)[1])
        name_pkg = P.parse_package(rep.get("footprint_pkg") or "") if rep.get("footprint_pkg") else None
        part_pkg = P.parse_package(part_pkg_text) if part_pkg_text else None
        check = {"check": "Genkendt geometri", "status": "ok",
                 "msg": f"Samme geometri som KiCad-bibliotekets {best['id']} ({best['similarity']} % ens)."}
        if rec_pkg and name_pkg and P.compare(rec_pkg, name_pkg)[0] == "mismatch":
            check["status"] = "warn"
            check["msg"] += f" Men navnet siger {rep['footprint_pkg']} – navnet passer ikke med geometrien."
        if rec_pkg and part_pkg and not name_pkg:
            st, msg = P.compare(rec_pkg, part_pkg)
            if st == "mismatch":
                check["status"] = "mismatch"
                check["msg"] += f" Komponenten er {P.describe(part_pkg)}: {msg}"
            elif st == "ok":
                check["msg"] += f" Passer med komponentens pakke ({P.describe(part_pkg)})."
        rep["checks"].append(check)
        order = {"ok": 0, "unknown": 1, "partial": 1, "warn": 2, "mismatch": 3}
        if order[check["status"]] > order.get(rep["status"], 0):
            rep["status"] = check["status"]

    def _datasheets(self, lines):
        """Read the package names in each IC's datasheet and compare with the footprint."""
        todo = [l for l in lines if l.get("fp") and not l["kind"] and l.get("datasheet", "").startswith("http")]
        done = [0]

        def work(line):
            fp_pkg = P.parse_package(line["footprint"].split(":")[-1])
            try:
                # Without an MPN the value is often the part number (AP22653W6, NE555 ...).
                mpn = line["mpn"] or (line["value"] if F.looks_like_mpn(line["value"]) else "")
                chk = datasheet.check(line["datasheet"], mpn, fp_pkg)
            except Exception as e:  # noqa: BLE001 - a broken PDF must not stop the analysis
                chk = {"check": "Datablad", "status": "unknown", "msg": f"Databladet kunne ikke læses: {e}"}
            line["fp"]["checks"].append(chk)
            try:
                # Only the explicit marking - "obsolete" etc. also appear in legal notices.
                if re.search(r"not\s+recommended\s+for\s+new\s+designs?", datasheet.text_for(line["datasheet"]), re.I):
                    line["warnings"].append("Databladet er mærket 'Not recommended for new design' (NRND).")
            except ValueError:
                pass
            order = {"ok": 0, "unknown": 1, "partial": 1, "warn": 2, "mismatch": 3}
            if chk["status"] in ("warn", "mismatch") and order[chk["status"]] > order.get(line["fp"]["status"], 0):
                line["fp"]["status"] = chk["status"]
            done[0] += 1
            self.progress(f"Læser datablade ({done[0]}/{len(todo)}) …", 80 + 7 * done[0] / max(1, len(todo)))

        with ThreadPoolExecutor(max_workers=4) as ex:
            list(ex.map(work, todo))

    @staticmethod
    def _geo_sig(geo):
        if not geo:
            return None
        return tuple(sorted((p["num"], round(p["x"], 2), round(p["y"], 2), round(p["w"], 2), round(p["h"], 2))
                            for p in geo["pads"]))

    # -- status ------------------------------------------------------------------------
    @staticmethod
    def _line_status(line, dist_boms):
        order = {"ok": 0, "partial": 1, "unknown": 1, "warn": 2, "missing": 3, "mismatch": 4}
        worst = "ok"

        def bump(s):
            nonlocal worst
            if order.get(s, 0) > order[worst]:
                worst = s
        bump((line.get("fp") or {}).get("status", "unknown"))
        for d in dist_boms:
            r = d["results"].get(line["id"])
            if r:
                bump(r["status"])
        if line["warnings"]:
            bump("warn")
        if not line["mpn"] and not line.get("suggested"):
            bump("warn")
        return worst

    @staticmethod
    def _summary(lines, excluded, dist_boms, project):
        s = {"lines": len(lines), "parts": sum(l["qty"] for l in lines), "excluded": len(excluded),
             "no_mpn": sum(1 for l in lines if not l["mpn"]),
             "fp": {}, "status": {}}
        for l in lines:
            st = (l.get("fp") or {}).get("status", "unknown")
            s["fp"][st] = s["fp"].get(st, 0) + 1
            s["status"][l["status"]] = s["status"].get(l["status"], 0) + 1
        s["dist"] = []
        for d in dist_boms:
            res = d["results"].values()
            s["dist"].append({"name": d["name"], "distributor": d["distributor"],
                              "ok": sum(1 for r in res if r["status"] == "ok"),
                              "problems": sum(1 for r in res if r["status"] != "ok"),
                              "extras": len(d["extras"])})
        return s


def run_alternatives(result, line_id, cfg, settings):
    line = next((l for l in result["lines"] if l["id"] == line_id), None)
    if line is None:
        raise ValueError("Ukendt linje.")
    providers = make_providers(cfg)
    if not providers:
        return {"items": [], "note": "Alternativer kræver mindst én grosist-API-nøgle (Indstillinger)."}
    preferred = None
    for d in result.get("dist_boms", []):
        r = d["results"].get(line_id)
        if r and r.get("dist_line"):
            preferred = d["distributor"]
            break
    if not preferred and line.get("plan"):
        preferred = line["plan"]["best"]["seller"]
    need = line.get("need_spare") or line["qty"]
    res = alternatives.find(line, providers, need, settings, preferred=preferred)
    res["preferred"] = preferred
    return res
