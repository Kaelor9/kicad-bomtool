"""Reads a KiCad 6-10 project: schematic hierarchy, PCB footprints and
footprint libraries. Produces a flat list of placed components.
"""
import glob
import math
import os
import posixpath
import re

from . import fields as F
from .sexpr import parse, head, children, child, value, num, flag, properties, walk


# ---- footprint geometry -------------------------------------------------------

GRAPHIC_LAYERS = ("F.Fab", "B.Fab", "F.SilkS", "B.SilkS", "F.Silkscreen", "B.Silkscreen",
                  "F.CrtYd", "B.CrtYd", "F.Courtyard", "B.Courtyard")


def _rot(x, y, deg):
    if not deg:
        return x, y
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    # KiCad: positive angle = counter-clockwise with y pointing down
    return x * c + y * s, -x * s + y * c


def footprint_geometry(fp_node):
    """Pads and outline in footprint-local coordinates (rotation removed)."""
    at = child(fp_node, "at")
    fp_rot = num(at[3]) if at is not None and len(at) > 3 else 0.0
    layer = value(fp_node, "layer", "F.Cu")
    pads = []
    for p in children(fp_node, "pad"):
        if len(p) < 4:
            continue
        number = str(p[1])
        ptype, shape = str(p[2]), str(p[3])
        pat = child(p, "at")
        size = child(p, "size")
        layers = child(p, "layers")
        drill = child(p, "drill")
        pad = {
            "num": number,
            "type": ptype,                 # smd / thru_hole / np_thru_hole / connect
            "shape": shape,                # rect / roundrect / circle / oval / trapezoid / custom
            "x": num(pat[1]) if pat is not None and len(pat) > 1 else 0.0,
            "y": num(pat[2]) if pat is not None and len(pat) > 2 else 0.0,
            "angle": (num(pat[3]) if pat is not None and len(pat) > 3 else 0.0) - fp_rot,
            "w": num(size[1]) if size is not None and len(size) > 1 else 0.0,
            "h": num(size[2]) if size is not None and len(size) > 2 else 0.0,
            "drill": num(drill[1]) if drill is not None and len(drill) > 1 and not isinstance(drill[1], list)
            and drill[1] != "oval" else (num(drill[2]) if drill is not None and len(drill) > 2 else 0.0),
            "layers": [str(x) for x in layers[1:]] if layers is not None else [],
            "rratio": num(value(p, "roundrect_rratio", 0)),
        }
        pad["angle"] = round(pad["angle"] % 360, 3)
        pads.append(pad)

    lines = []
    for kind in ("fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly"):
        for g in children(fp_node, kind):
            glayer = str(value(g, "layer", ""))
            if glayer not in GRAPHIC_LAYERS:
                continue
            lay = glayer.split(".")[1][:4].lower()  # fab / silk / crty
            if kind in ("fp_line", "fp_rect", "fp_circle", "fp_arc"):
                s, e = child(g, "start") or child(g, "center"), child(g, "end")
                if s is None or e is None:
                    continue
                item = {"k": kind[3:], "l": lay,
                        "x1": num(s[1]), "y1": num(s[2]), "x2": num(e[1]), "y2": num(e[2])}
                if kind == "fp_arc":
                    mid = child(g, "mid")
                    if mid is not None:
                        item["xm"], item["ym"] = num(mid[1]), num(mid[2])
                    else:
                        continue
                if kind == "fp_circle":
                    item["k"] = "circle"
                lines.append(item)
            else:
                pts = child(g, "pts")
                if pts is None:
                    continue
                xy = [(num(c[1]), num(c[2])) for c in children(pts, "xy")]
                if xy:
                    lines.append({"k": "poly", "l": lay, "pts": xy})
    return {"pads": pads, "graphics": lines, "bottom": str(layer).startswith("B."), "rot": fp_rot}


def _fp_fields(fp_node):
    """Reference/value/properties of a PCB footprint (KiCad 6 fp_text or 8+ property)."""
    props = properties(fp_node)
    for t in children(fp_node, "fp_text"):
        if len(t) >= 3 and str(t[1]) in ("reference", "value"):
            props.setdefault(str(t[1]).capitalize(), str(t[2]))
    return props


# ---- library lookup -----------------------------------------------------------

def kicad_install_footprint_dirs():
    dirs = []
    for var in ("KICAD10_FOOTPRINT_DIR", "KICAD9_FOOTPRINT_DIR", "KICAD8_FOOTPRINT_DIR",
                "KICAD7_FOOTPRINT_DIR", "KICAD_FOOTPRINT_DIR"):
        if os.environ.get(var):
            dirs.append(os.environ[var])
    pats = [r"C:\Program Files\KiCad\*\share\kicad\footprints",
            "/usr/share/kicad/footprints", "/usr/local/share/kicad/footprints",
            "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints",
            os.path.expanduser("~/.local/share/kicad/*/footprints")]
    for pat in pats:
        dirs.extend(sorted(glob.glob(pat), reverse=True))  # newest version first
    return [d for d in dirs if os.path.isdir(d)]


class FootprintLibrary:
    def __init__(self, files):
        self.files = files
        self.install_dirs = kicad_install_footprint_dirs()
        self.cache = {}

    def lookup(self, lib_id):
        """Return (geometry, source) for 'Lib:Name', or (None, None)."""
        if not lib_id or ":" not in lib_id:
            return None, None
        if lib_id in self.cache:
            return self.cache[lib_id]
        lib, name = lib_id.split(":", 1)
        target = f"{lib}.pretty/{name}.kicad_mod".lower()
        result = (None, None)
        for path in self.files.files:
            if path.lower().endswith(target):
                result = self._load(self.files.text(path), "projekt")
                break
        if result[0] is None:
            for d in self.install_dirs:
                fp = os.path.join(d, f"{lib}.pretty", f"{name}.kicad_mod")
                if os.path.isfile(fp):
                    with open(fp, encoding="utf-8", errors="replace") as fh:
                        result = self._load(fh.read(), "KiCad-bibliotek")
                    break
        self.cache[lib_id] = result
        return result

    @staticmethod
    def _load(text, source):
        node = parse(text or "")
        if head(node) not in ("footprint", "module"):
            return None, None
        return footprint_geometry(node), source


def load_kicad_mod(text):
    node = parse(text or "")
    if head(node) not in ("footprint", "module"):
        return None, ""
    return footprint_geometry(node), str(node[1]) if len(node) > 1 else ""


# ---- schematic ------------------------------------------------------------------

def _lib_symbol_info(sch):
    """{lib_id: {"pins": set, "power": bool}} from a sheet's lib_symbols."""
    out = {}
    libs = child(sch, "lib_symbols")
    if libs is None:
        return out
    raw = {}
    for sym in children(libs, "symbol"):
        name = str(sym[1])
        pins, names = set(), {}
        for pin in walk(sym, "pin"):
            n = child(pin, "number")
            if n is not None and len(n) > 1:
                pins.add(str(n[1]))
                nm = child(pin, "name")
                if nm is not None and len(nm) > 1 and str(nm[1]) not in ("~", ""):
                    names[str(n[1])] = str(nm[1])
        raw[name] = {"pins": pins, "names": names, "power": child(sym, "power") is not None,
                     "extends": value(sym, "extends")}
    for name, info in raw.items():
        if not info["pins"] and info["extends"]:
            parent = raw.get(info["extends"]) or raw.get(name.split(":")[0] + ":" + str(info["extends"]))
            if parent:
                info["pins"] = parent["pins"]
                info["names"] = parent["names"]
                info["power"] = info["power"] or parent["power"]
        out[name] = info
    return out


class Component(dict):
    """Placed component; a dict so it serialises straight to JSON."""


def _new_component(ref, props, lib_id, sheet_name, src):
    fields = {k: v for k, v in props.items()}
    mpn_field, mpn = F.pick(fields, F.MPN_KEYS)
    mfr_field, mfr = F.pick(fields, F.MFR_KEYS)
    _, datasheet = F.pick(fields, F.DATASHEET_KEYS)
    _, package = F.pick(fields, F.PACKAGE_KEYS)
    comp = Component(
        ref=ref, value=props.get("Value", ""), footprint=props.get("Footprint", ""),
        lib_id=lib_id, fields=fields, mpn=mpn, mpn_field=mpn_field or "", mfr=mfr,
        datasheet=datasheet if datasheet.lower().startswith("http") else
        ("https://" + datasheet if datasheet.lower().startswith("www.") else ""),
        package_field=package, dist=F.distributor_numbers(fields), sheet=sheet_name,
        source=src, dnp=False, in_bom=True, on_board=True, pins=[], warnings=[],
    )
    # MPN and manufacturer typed into each other's fields ("Mfr. No: C&K", "Mfr.: PTS810SJM250SMTR LFS")
    if mpn and mfr and not re.search(r"\d", mpn) and F.looks_like_mpn(mfr):
        comp["mpn"], comp["mfr"] = mfr, mpn
        comp["warnings"].append(f"MPN- og producent-felterne ser ud til at være byttet om ('{mpn_field}' = '{mpn}', "
                                f"'{mfr_field}' = '{mfr}') – bruger {mfr} som MPN.")
    return comp


class Project:
    def __init__(self, files):
        self.files = files
        self.name = ""
        self.version = {}
        self.components = []
        self.warnings = []
        self.pcb_footprints = {}
        self.pcb_by_path = {}     # symbol path ("/sheet uuid/.../symbol uuid") -> footprint
        self.fplib = FootprintLibrary(files)

    # -- loading
    def load(self):
        pro = self.files.find(".kicad_pro")
        schs = self.files.find(".kicad_sch")
        pcbs = self.files.find(".kicad_pcb")
        root = None
        if pro:
            pro.sort(key=lambda p: p.count("/"))
            self.name = posixpath.splitext(posixpath.basename(pro[0]))[0]
            stem = posixpath.splitext(pro[0])[0]
            if stem + ".kicad_sch" in self.files.files:
                root = stem + ".kicad_sch"
            pcb = stem + ".kicad_pcb"
            pcbs = [pcb] if pcb in self.files.files else pcbs
        if root is None and schs:
            root = self._guess_root(schs)
            self.name = self.name or posixpath.splitext(posixpath.basename(root))[0]
        if not schs and not pcbs:
            if self.files.find(".sch"):
                raise ValueError("Projektet bruger det gamle KiCad 5-format (.sch). Åbn det i KiCad 8/10 "
                                 "og gem det, så filerne bliver opdateret.")
            raise ValueError("Fandt ingen .kicad_sch eller .kicad_pcb i det uploadede.")

        if pcbs:
            self._load_pcb(pcbs[0])
        if root:
            self._load_schematic(root)
        else:
            self.warnings.append("Ingen skematisk fil – BOM er lavet ud fra PCB'en alene.")
            self._components_from_pcb()
        self._link_pcb()
        return self

    def _guess_root(self, schs):
        referenced = set()
        for s in schs:
            for m in re.finditer(r'\(property\s+"Sheet ?[Ff]ile"\s+"([^"]+)"', self.files.text(s) or ""):
                referenced.add(posixpath.basename(m.group(1)).lower())
        roots = [s for s in schs if posixpath.basename(s).lower() not in referenced]
        roots.sort(key=lambda p: (p.count("/"), len(p)))
        return (roots or schs)[0]

    def _load_pcb(self, path):
        pcb = parse(self.files.text(path))
        self.version["pcb"] = value(pcb, "version", "")
        self.version["pcb_generator"] = value(pcb, "generator_version", "")
        for fp in children(pcb, "footprint") + children(pcb, "module"):
            props = _fp_fields(fp)
            ref = props.get("Reference", "")
            if not ref or ref.startswith("#"):
                continue
            attr = child(fp, "attr")
            attrs = [str(a) for a in attr[1:]] if attr is not None else []
            entry = self.pcb_footprints.setdefault(ref, {
                "ref": ref, "path": str(value(fp, "path", "")),
                "lib_id": str(fp[1]) if len(fp) > 1 else "",
                "props": props,
                "geometry": footprint_geometry(fp),
                "exclude_from_bom": "exclude_from_bom" in attrs,
                "dnp": "dnp" in attrs,
                "board_only": "board_only" in attrs,
            })
            if entry["path"]:
                self.pcb_by_path.setdefault(entry["path"], entry)

    def _load_schematic(self, root):
        self.sheet_cache = {}
        root_node = self._sheet(root)
        self.version["sch"] = value(root_node, "version", "")
        self.version["sch_generator"] = value(root_node, "generator_version", "")
        root_uuid = str(value(root_node, "uuid", ""))
        # KiCad 6 stores instance data centrally in the root sheet.
        legacy = {}
        for si in children(root_node, "symbol_instances"):
            for p in children(si, "path"):
                legacy[str(p[1])] = {"reference": value(p, "reference", ""),
                                     "unit": value(p, "unit", "1"),
                                     "value": value(p, "value", None),
                                     "footprint": value(p, "footprint", None)}
        self.legacy = legacy
        self.by_ref = {}
        self._walk(root, "/" + root_uuid if root_uuid else "", "", "/", 0, set())
        self.components = list(self.by_ref.values())

    def _sheet(self, path):
        if path not in self.sheet_cache:
            node = parse(self.files.text(path) or "")
            self.sheet_cache[path] = (node, _lib_symbol_info(node))
        return self.sheet_cache[path][0]

    def _walk(self, path, inst_path, legacy_path, sheet_name, depth, stack):
        if depth > 32 or path in stack:
            self.warnings.append(f"Rekursiv/for dyb hierarki ved {path} – sprunget over.")
            return
        sch = self._sheet(path)
        libinfo = self.sheet_cache[path][1]
        base = posixpath.dirname(path)
        for sym in children(sch, "symbol"):
            self._add_symbol(sym, libinfo, inst_path, legacy_path, sheet_name, path)
        for sh in children(sch, "sheet"):
            props = properties(sh)
            fname = props.get("Sheetfile") or props.get("Sheet file") or ""
            sname = props.get("Sheetname") or props.get("Sheet name") or fname
            uuid = str(value(sh, "uuid", ""))
            sub = self.files.resolve(base, fname) if fname else None
            if sub is None:
                self.warnings.append(f"Under-ark '{fname}' mangler i det uploadede – komponenter derfra er ikke med.")
                continue
            if flag(sh, "dnp"):
                continue
            self._walk(sub, f"{inst_path}/{uuid}", f"{legacy_path}/{uuid}".replace("//", "/"),
                       f"{sheet_name}{sname}/", depth + 1, stack | {path})

    def _add_symbol(self, sym, libinfo, inst_path, legacy_path, sheet_name, src):
        lib_id = str(value(sym, "lib_id", ""))
        info = libinfo.get(lib_id) or libinfo.get(str(value(sym, "lib_name", ""))) or {"pins": set(), "power": False}
        props = properties(sym)
        uuid = str(value(sym, "uuid", ""))
        ref = props.get("Reference", "")
        # Instance reference for exactly this position in the hierarchy.
        found = False
        for inst in children(sym, "instances"):
            for proj in children(inst, "project"):
                for p in children(proj, "path"):
                    if str(p[1]) == inst_path:
                        ref = str(value(p, "reference", ref))
                        found = True
        if not found and self.legacy:
            key = f"{legacy_path}/{uuid}".replace("//", "/")
            if key in self.legacy:
                ref = self.legacy[key]["reference"] or ref
                if self.legacy[key].get("value"):
                    props["Value"] = self.legacy[key]["value"]
                if self.legacy[key].get("footprint"):
                    props["Footprint"] = self.legacy[key]["footprint"]
        if info["power"] or not ref or ref.startswith("#") or lib_id.lower().startswith("power:"):
            return
        in_bom = flag(sym, "in_bom", True)
        on_board = flag(sym, "on_board", True)
        dnp = flag(sym, "dnp", False)
        # The PCB links footprints to symbols by this path, not by reference.
        pcb_path = f"{legacy_path}/{uuid}".replace("//", "/")
        comp = self.by_ref.get(ref)
        if comp is None:
            comp = _new_component(ref, props, lib_id, sheet_name, posixpath.basename(src))
            comp["in_bom"], comp["on_board"], comp["dnp"] = in_bom, on_board, dnp
            comp["pins"] = sorted(info["pins"], key=_natkey)
            comp["pin_names"] = dict(info.get("names") or {})
            comp["pcb_paths"] = [pcb_path]
            if ref.endswith("?"):
                comp["warnings"].append("Ikke annoteret (reference ender på '?').")
            self.by_ref[ref] = comp
        else:
            # Another unit of a multi-unit symbol: fill in blanks only.
            extra = _new_component(ref, props, lib_id, sheet_name, src)
            for k in ("mpn", "mfr", "datasheet", "footprint", "package_field"):
                if not comp[k] and extra[k]:
                    comp[k] = extra[k]
            comp["dist"] = {**extra["dist"], **comp["dist"]}
            comp["pins"] = sorted(set(comp["pins"]) | info["pins"], key=_natkey)
            comp["pin_names"] = {**(info.get("names") or {}), **comp.get("pin_names", {})}
            comp.setdefault("pcb_paths", []).append(pcb_path)
            comp["dnp"] = comp["dnp"] or dnp

    def _components_from_pcb(self):
        for ref, fp in sorted(self.pcb_footprints.items(), key=lambda kv: _natkey(kv[0])):
            props = dict(fp["props"])
            props.setdefault("Footprint", fp["lib_id"])
            comp = _new_component(ref, props, "", "/", "pcb")
            comp["dnp"] = fp["dnp"]
            comp["in_bom"] = not fp["exclude_from_bom"]
            comp["pins"] = sorted({p["num"] for p in fp["geometry"]["pads"] if p["num"]}, key=_natkey)
            self.components.append(comp)

    def _link_pcb(self):
        used, renamed = set(), []
        for comp in self.components:
            ref = comp["ref"]
            fp = next((self.pcb_by_path[p] for p in comp.get("pcb_paths", []) if p in self.pcb_by_path), None)
            if fp is None:
                fp = self.pcb_footprints.get(ref)
            if fp:
                used.add(id(fp))
                if fp["ref"] != ref and comp["source"] != "pcb":
                    renamed.append(f"{ref} → '{fp['ref']}'")
                comp["geometry"] = fp["geometry"]
                comp["geometry_source"] = "PCB"
                comp["pcb_footprint"] = fp["lib_id"]
                if (comp["footprint"] and fp["lib_id"] and comp["source"] != "pcb"
                        and comp["footprint"].split(":")[-1] != fp["lib_id"].split(":")[-1]):
                    comp["warnings"].append(
                        f"Skematik siger footprint '{comp['footprint']}', men PCB'en har '{fp['lib_id']}'. "
                        "Kør 'Update PCB from Schematic'.")
                if not comp["footprint"]:
                    comp["footprint"] = fp["lib_id"]
                # Fill MPN etc. from PCB fields if the schematic had none.
                if not comp["mpn"]:
                    name, mpn = F.pick(fp["props"], F.MPN_KEYS)
                    if mpn:
                        comp["mpn"], comp["mpn_field"] = mpn, name + " (PCB)"
            elif self.pcb_footprints and comp["on_board"] and not comp["dnp"] and comp["source"] != "pcb":
                comp["warnings"].append("Findes i skematik men ikke på PCB'en.")
            lib_geo, lib_src = self.fplib.lookup(comp["footprint"])
            if lib_geo is None and fp:
                # Archived into a project library: try the original library name too.
                lib_geo, lib_src = self.fplib.lookup(fp["lib_id"])
            if lib_geo is not None:
                comp["lib_geometry"] = lib_geo
                comp["lib_geometry_source"] = lib_src
                if "geometry" not in comp:
                    comp["geometry"] = lib_geo
                    comp["geometry_source"] = lib_src
        for comp in self.components:
            comp["virtual"] = is_virtual(comp)
        if self.components and self.components[0]["source"] != "pcb":
            for ref, fp in self.pcb_footprints.items():
                lib = fp["lib_id"].lower()
                if (id(fp) in used or fp["board_only"] or "**" in ref
                        or any(v in lib for v in _VIRTUAL_FP + ("heatsink", "mounting"))):
                    continue   # unannotated board items (REF**, heatsinks, holes) are PCB-only on purpose
                self.warnings.append(f"{ref} ({fp['lib_id']}) er på PCB'en men ikke i skematikken.")
            if renamed:
                self.warnings.append(
                    f"{len(renamed)} footprint(s) har en anden reference på PCB'en end i skematikken "
                    f"({', '.join(renamed[:6])}{' …' if len(renamed) > 6 else ''}). De er koblet via symbolets ID, "
                    "så kontrollen er korrekt – kør 'Update PCB from Schematic', hvis det ikke er meningen.")


_VIRTUAL_PREFIX = ("H", "MH", "LOGO", "FID", "REF", "G", "KIBUZZARD", "NT", "JP_SOLDER")
_VIRTUAL_FP = ("mountinghole", "fiducial", "logo", "symbol:", "testpoint_pad", "nettie", "solderjumper",
               "kibuzzard", "oshw", "creative_commons")


def is_virtual(comp):
    """Mechanical/graphic items nobody buys: mounting holes, logos, fiducials, net ties."""
    if comp["mpn"]:
        return False
    prefix = re.match(r"[A-Za-z_]+", comp["ref"])
    prefix = prefix.group(0).upper() if prefix else ""
    fp = comp["footprint"].lower()
    if any(v in fp for v in _VIRTUAL_FP):
        return True
    if not comp["pins"] and not comp["footprint"]:
        return True
    return prefix in _VIRTUAL_PREFIX and not comp["pins"]


def _natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


natkey = _natkey
