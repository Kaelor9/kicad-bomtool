"""Heuristics for finding MPN / manufacturer / distributor numbers in symbol
fields, plus parsing of passive component values ("4k7", "100nF 50V X7R" ...).
"""
import re


def key(name):
    return re.sub(r"[^a-z0-9#]", "", name.lower())


# Normalised field names. Order matters: earlier = more trusted.
MPN_KEYS = [
    "mpn", "mfrpn", "mfrno", "mfrpartno", "mfrpartnumber", "mfrpart", "mfr#",
    "manufacturerpartnumber", "manufacturerpn", "manufacturerpart", "manufacturerno",
    "manufacturerpartno", "mfgpn", "mfgpartno", "mfgpartnumber", "mfg#", "manfpn",
    "manf#", "manfpartno", "mpn1", "manufacturerpartnumber1", "mfrpn1", "mfrnumber",
    "producentnr", "producentvarenr", "herstellerteilenummer", "herstellernummer",
    "partnumber", "partno", "pn", "part#", "articlenumber",
]
MFR_KEYS = [
    "manufacturer", "mfr", "mfg", "manufacturername", "manufacturer1", "manf",
    "mfrname", "producent", "hersteller", "brand", "vendor",
]
DIST_KEYS = {
    "digikey": ["digikey", "digikeypn", "digikeypartnumber", "digikeypart", "digikey#",
                "digikeyno", "dkpn", "digikeypartno", "digikey1"],
    "mouser": ["mouser", "mouserpn", "mouserpartnumber", "mouserno", "mouser#",
               "mouserpartno", "mouserpart", "mouser1"],
    "lcsc": ["lcsc", "lcscpart", "lcscpn", "lcscpartnumber", "lcsc#", "jlcpcb", "jlcpcbpart",
             "jlcpart", "lcscpartno"],
    "farnell": ["farnell", "farnellpn", "farnellno", "farnellpartnumber", "element14",
                "newark", "ordercode"],
    "tme": ["tme", "tmepn", "tmesymbol", "tmepartnumber"],
    "rs": ["rs", "rspn", "rsstockno", "rscomponents", "rspartnumber"],
}
DATASHEET_KEYS = ["datasheet", "datasheeturl", "datablad", "ds"]
PACKAGE_KEYS = ["package", "case", "packagecase", "pakke", "size", "footprintsize"]
DNP_VALUES = {"dnp", "dnf", "nc", "nf", "nofit", "notfitted", "donotplace", "donotpopulate",
              "dnm", "np", "nopop"}


def pick(fields, keys):
    """Return (field name, value) for the first non-empty field matching keys."""
    norm = {}
    for name, val in fields.items():
        val = (val or "").strip()
        if val and val not in ("~", "-", "?", "N/A", "n/a", "NA", "TBD", "tbd"):
            norm.setdefault(key(name), (name, val))
    for k in keys:
        if k in norm:
            return norm[k]
    return None, ""


def distributor_numbers(fields):
    out = {}
    for dist, keys in DIST_KEYS.items():
        name, val = pick(fields, keys)
        if val:
            out[dist] = val
    return out


# ---- passive values ----------------------------------------------------------

_MULT = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "μ": 1e-6, "m": 1e-3,
         "k": 1e3, "K": 1e3, "M": 1e6, "G": 1e9, "R": 1.0, "r": 1.0, "": 1.0}

KIND_UNIT = {"R": "Ω", "C": "F", "L": "H"}


def passive_kind(ref, lib_id="", footprint=""):
    prefix = re.match(r"[A-Za-z]+", ref or "")
    prefix = prefix.group(0).upper() if prefix else ""
    lib = (lib_id or "").split(":")[-1].upper()
    if prefix in ("R", "RN") or lib in ("R", "R_SMALL", "R_US", "R_SMALL_US"):
        return "R"
    if prefix == "C" or lib in ("C", "C_SMALL", "C_POLARIZED", "CP", "CP_SMALL", "C_POL"):
        return "C"
    if prefix in ("L", "FB") or lib in ("L", "L_SMALL", "FERRITEBEAD", "FERRITEBEAD_SMALL"):
        return "L"
    return None


def parse_value(text, kind):
    """Parse '4k7', '10K 1%', '100nF/50V X7R', 'CC1206_100NF_50V' -> dict, or None."""
    if not text:
        return None
    t = _clean(text, kind)
    extras = _extras(t, kind)
    core = _strip_extras(t)
    value = _value(core, kind)
    if value is None:
        # Value buried in a longer string: try each token, preferring ones with a unit.
        tokens = [x for x in re.split(r"[_\s/]+", core) if x]
        ranked = sorted(tokens, key=lambda x: 0 if re.search(r"\d[pnumkKMRrG]|[FH]$", x, re.I) else 1)
        for tok in ranked:
            if re.fullmatch(r"\d{4}", tok):
                continue  # 0603, 1206 ... are package sizes
            value = _value(tok, kind)
            if value is not None:
                break
    if value is None:
        return None
    return {"value": value, **extras}


def _clean(text, kind):
    t = text.replace(",", ".").replace("Ω", "").replace("µ", "u").replace("μ", "u")
    t = re.sub(r"(?i)ohms?", "", t).strip()
    if kind in ("C", "L"):
        t = re.sub(r"(\d)\s*([NUP])", lambda m: m.group(1) + m.group(2).lower(), t)
    return t


_EXTRA_RES = {
    "power": r"(\d+/\d+|\d+(?:\.\d+)?)\s*W(?![A-Za-z0-9])",
    "voltage": r"(\d+(?:\.\d+)?)\s*([kK]?)[Vv](?:DC|dc|olts?)?(?![A-Za-z0-9])",
    "tolerance": r"[±+-]?(\d+(?:\.\d+)?)\s*%",
    "dielectric": r"(?<![A-Za-z0-9])(C0G|NP0|NPO|X5R|X7R|X7S|X6S|X8R|Y5V|Z5U)(?![A-Za-z0-9])",
    "current": r"(\d+(?:\.\d+)?)\s*(m?)A(?![A-Za-z0-9])",
}


def _extras(t, kind):
    out = {}
    for name, rx in _EXTRA_RES.items():
        m = re.search(rx, t, re.I if name == "dielectric" else 0)
        if not m:
            continue
        if name == "power" and kind == "R":
            s = m.group(1)
            out["power"] = float(s.split("/")[0]) / float(s.split("/")[1]) if "/" in s else float(s)
        elif name == "voltage":
            out["voltage"] = float(m.group(1)) * (1000 if m.group(2) else 1)
        elif name == "tolerance":
            out["tolerance"] = float(m.group(1))
        elif name == "dielectric" and kind == "C":
            out["dielectric"] = m.group(1).upper().replace("NPO", "C0G").replace("NP0", "C0G")
        elif name == "current" and kind == "L":
            out["current"] = float(m.group(1)) / (1000 if m.group(2) else 1)
    return out


def _strip_extras(t):
    for rx in _EXTRA_RES.values():
        t = re.sub(rx, " ", t, flags=re.I)
    return t.strip(" /_-")


def _value(t, kind):
    t = t.strip()
    # Embedded multiplier notation: 4k7, 2R2, 4n7, 1M5
    m = re.fullmatch(r"(\d+)([pnumkKMRrG])(\d+)\s*[FH]?", t)
    if m:
        return float(f"{m.group(1)}.{m.group(3)}") * _MULT[m.group(2)]
    unit = {"R": "", "C": "[fF]?", "L": "[hH]?"}[kind]
    mults = "pnumkKMGRr" if kind == "R" else "pnumkKMG"
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([" + mults + r"]?)\s*(" + unit + r")", t)
    if not m:
        return None
    mult = m.group(2)
    if kind == "C" and not mult and not m.group(3):
        # Old habit: "0.1" on a capacitor means 0.1 µF. Whole numbers are ambiguous.
        if float(m.group(1)) >= 1:
            return None
        mult = "u"
    return float(m.group(1)) * _MULT.get(mult, 1.0)


def format_value(v, kind):
    unit = KIND_UNIT[kind]
    for mult, sym in ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ"),
                      (1e-9, "n"), (1e-12, "p")):
        if v >= mult * 0.9999:
            n = v / mult
            s = f"{n:.3g}"
            return f"{s}{sym}{unit}"
    return f"{v:g}{unit}"


def looks_like_mpn(text):
    """True for strings like 'NE555DR', 'LM317T', 'STM32F103C8T6', not '10k', '100nF'."""
    t = (text or "").strip()
    if len(t) < 4 or " " in t.strip() and len(t.split()) > 2:
        return False
    if not re.search(r"[A-Za-z]", t) or not re.search(r"\d", t):
        return False
    if re.fullmatch(r"\d+(\.\d+)?\s*[pnuµμmkKMGRNUP]?\d{0,2}\s*(?i:F|H|Ω|ohm|V|W|A|Hz)?(/.*)?", t):
        return False
    return len(re.sub(r"[^A-Za-z0-9]", "", t)) >= 5
