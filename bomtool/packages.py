"""Package names: normalise the many spellings used by KiCad libraries,
distributors and manufacturers ("0603 (1608 Metric)", "R_0603_1608Metric",
"8-SOIC (0.154", 3.90mm Width)", "TO-236-3, SC-59, SOT-23-3" ...) into a
comparable form, and compare two of them.
"""
import re

# Imperial <-> metric chip sizes
CHIP_IMP_TO_MET = {"01005": "0402", "0201": "0603", "0402": "1005", "0603": "1608", "0805": "2012",
                   "1008": "2520", "1206": "3216", "1210": "3225", "1806": "4516", "1812": "4532",
                   "2010": "5025", "2220": "5750", "2512": "6332", "2920": "7451"}
CHIP_MET_TO_IMP = {v: k for k, v in CHIP_IMP_TO_MET.items()}

# Aliases -> canonical family. Pin count is handled separately.
ALIASES = [
    (r"\bTO-?236(AB)?\b|\bSC-?59\b|\bSOT-?346\b", "SOT-23"),
    (r"\bSOT-?25\b|\bSOT-?753\b|\bSC-?74A\b", "SOT-23-5"),
    (r"\bSOT-?26\b|\bSOT-?457\b|\bSC-?74\b(?!A)", "SOT-23-6"),
    (r"\bSOT-?323\b|\bSC-?70-?3\b", "SC-70-3"),
    (r"\bSOT-?353\b|\bSC-?70-?5\b|\bSC-?88A\b", "SC-70-5"),
    (r"\bSOT-?363\b|\bSC-?70-?6\b|\bSC-?88\b(?!A)", "SC-70-6"),
    (r"\bSOT-?416\b|\bSC-?75\b", "SC-75"),
    (r"\bSOT-?523\b|\bSC-?89\b", "SOT-523"),
    (r"\bTO-?261(AA)?\b|\bSOT-?223\b", "SOT-223"),
    (r"\bTO-?243(AA)?\b|\bSOT-?89\b|\bSC-?62\b", "SOT-89"),
    (r"\bDO-?214AC\b|\bSMA\b(?![-_]?(?:J|connector))", "SMA"),
    (r"\bDO-?214AA\b|\bSMB\b(?![-_]?(?:J|connector))", "SMB"),
    (r"\bDO-?214AB\b|\bSMC\b", "SMC"),
    (r"\bDO-?219AB\b|\bSMF\b", "SMF"),
    (r"\bSOD-?323F?\b|\bSC-?76\b", "SOD-323"),
    (r"\bSOD-?523\b|\bSC-?79\b", "SOD-523"),
    (r"\bSOD-?123F?\b", "SOD-123"),
    (r"\bSOD-?923\b", "SOD-923"),
    (r"\bTO-?252\b|\bD-?PAK\b(?!2)", "TO-252"),
    (r"\bTO-?263\b|\bD2-?PAK\b", "TO-263"),
    (r"\bTO-?220\b", "TO-220"),
    (r"\bTO-?92\b", "TO-92"),
    (r"\bTO-?247\b", "TO-247"),
    (r"\bDO-?41\b|\bSOD-?81\b", "DO-41"),
    (r"\bDO-?35\b|\bSOD-?27\b", "DO-35"),
    (r"\bMINI-?MELF\b|\bSOD-?80\b|\bLL-?34\b", "MiniMELF"),
    (r"\bMELF\b|\bDO-?213AB\b", "MELF"),
]

# Families where the leading "8-" / trailing "-8" is the pin count.
PINNED = ["SOIC", "SO", "SOP", "SSOP", "TSSOP", "MSOP", "VSSOP", "HTSSOP", "HSOP", "HSSOP", "HVSSOP", "QSOP", "TSOP",
          "QFN", "VQFN", "WQFN", "UQFN", "VFQFN", "DFN", "WDFN", "UDFN", "VDFN", "TDFN", "SON",
          "WSON", "VSON", "USON", "X2SON", "LQFP", "TQFP", "QFP", "PQFP", "LFCSP", "BGA", "FBGA",
          "LGA", "WLCSP", "CSP", "DIP", "PDIP", "SIP", "PLCC", "SOT-23", "SC-70", "TO-220", "TO-252",
          "TO-263", "HSOP", "PowerPAK", "PSOP", "DIP"]

# Groups that are physically interchangeable names for the same thing.
FAMILY_GROUPS = {
    "SOIC": "SOIC", "SO": "SOIC", "SOP": "SOIC",
    "MSOP": "MSOP", "VSSOP": "MSOP", "uMAX": "MSOP", "TSSOP": "TSSOP", "SSOP": "SSOP", "QSOP": "SSOP",
    "HTSSOP": "TSSOP", "HSOP": "SOIC", "HSSOP": "SSOP", "HVSSOP": "MSOP", "HMSOP": "MSOP",
    "QFN": "QFN", "VQFN": "QFN", "WQFN": "QFN", "UQFN": "QFN", "VFQFN": "QFN", "LFCSP": "QFN",
    "DFN": "DFN", "WDFN": "DFN", "UDFN": "DFN", "VDFN": "DFN", "TDFN": "DFN", "SON": "DFN",
    "WSON": "DFN", "VSON": "DFN", "USON": "DFN", "X2SON": "DFN",
    "LQFP": "QFP", "TQFP": "QFP", "QFP": "QFP", "PQFP": "QFP",
    "BGA": "BGA", "FBGA": "BGA", "DIP": "DIP", "PDIP": "DIP",
}


def _chip(text):
    """Find a chip size (0402, 0603 ...) and return the imperial code."""
    t = text
    m = re.search(r"(\d{4,5})\s*\(?\s*(\d{4})\s*(?:metric|met)\b", t, re.I)
    if m and m.group(1) in CHIP_IMP_TO_MET:
        return m.group(1)
    m = re.search(r"(?<!\d)(\d{4})\s*(?:metric|met|m)\b", t, re.I)
    if m and m.group(1) in CHIP_MET_TO_IMP:
        return CHIP_MET_TO_IMP[m.group(1)]
    m = re.search(r"(?:^|[^\d.x])(\d{4,5})(?:_|\s|$|[^\dxX.])", t)
    if m and m.group(1) in CHIP_IMP_TO_MET:
        return m.group(1)
    # IPC-7351 names: RESC1608X55N, CAPC3216X140N, INDC2012X100N, LEDC..., DIOC...
    m = re.search(r"(?:RES|CAP|IND|LED|DIO|FUS)[CM](\d{4})X", t, re.I)
    if m and m.group(1) in CHIP_MET_TO_IMP:
        return CHIP_MET_TO_IMP[m.group(1)]
    # A bare metric-only code such as R_1005 (1005 has no imperial meaning)
    m = re.search(r"(?:^|[^\d.x])(\d{4})(?:_|\s|$|[^\dxX.])", t)
    if m and m.group(1) in CHIP_MET_TO_IMP and m.group(1) not in CHIP_IMP_TO_MET:
        return CHIP_MET_TO_IMP[m.group(1)]
    # "1608Metric" in KiCad names without the imperial code first
    m = re.search(r"(\d{4})Metric", t)
    if m and m.group(1) in CHIP_MET_TO_IMP:
        return CHIP_MET_TO_IMP[m.group(1)]
    return None


def parse_package(text):
    """Return dict(family, pins, chip, body, pitch, ep, raw) or None if nothing recognisable."""
    if not text:
        return None
    raw = text
    t = text.replace("_", " ").replace(" ", " ")
    out = {"raw": raw, "family": None, "pins": None, "chip": None, "body": None, "pitch": None, "ep": False}

    # Dimensions as KiCad writes them: 3.9x4.9mm, P1.27mm, EP2.1x2.1mm
    m = re.search(r"P(\d+(?:\.\d+)?)\s*mm", text)
    if m:
        out["pitch"] = float(m.group(1))
    m = re.search(r"(?:pitch|Pitch)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*mm", text)
    if m and not out["pitch"]:
        out["pitch"] = float(m.group(1))
    m = re.search(r"(?<![EP\d.])(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(?:x\d+(?:\.\d+)?)?\s*mm", text)
    if m:
        out["body"] = tuple(sorted((float(m.group(1)), float(m.group(2)))))
    m = re.search(r"(\d+(?:\.\d+)?)\s*mm\s*(?:Width|bredde)", text, re.I)
    if m and not out["body"]:
        out["width"] = float(m.group(1))
    if re.search(r"\b\d?-?EP\b|Exposed\s*Pad|EP\d|Thermal\s*Pad|PowerPad", text, re.I):
        out["ep"] = True

    # IPC-7351 names: SOIC127P600X175-8N, QFN50P500X500X100-33N, SOP65P640X120-16N
    m = re.search(r"(?<![A-Za-z])(SOIC|SOP|SSOP|TSSOP|MSOP|QFN|DFN|SON|QFP|LQFP|TQFP|SOT|BGA)(\d{2,3})P"
                  r"(\d{3,4})X(\d{2,4})(?:X\d+)?-(\d{1,3})", t, re.I)
    if m:
        fam = m.group(1).upper()
        out["pitch"] = int(m.group(2)) / 100
        out["pins"] = int(m.group(5))
        if fam in ("QFN", "DFN", "SON", "SOP", "SSOP", "TSSOP", "MSOP", "SOIC") and out["pins"] % 2 == 1:
            out["pins"] -= 1  # IPC counts the thermal pad
            out["ep"] = True
        span = int(m.group(3)) / 100
        out["ipc"] = True
        if fam == "SOT":
            # SOT95P... = SOT-23 family, SOT65P... = SC-70 family
            base = "SOT-23" if out["pitch"] >= 0.9 else "SC-70"
            fam = base if (base == "SOT-23" and out["pins"] == 3) else f"{base}-{out['pins']}"
        elif fam == "SOP":
            # IPC calls them all SOP; pitch and lead span tell the JEDEC family.
            if out["pitch"] >= 1.27:
                fam = "SOIC"
            elif span < 5.5:
                fam = "MSOP"
            elif span <= 6.6:
                fam = "TSSOP"
            else:
                fam = "SSOP"
        out["family"] = fam
        return out

    # Alias families (SOT-23, SMA ...) checked first; they can carry pin counts.
    for rx, fam in ALIASES:
        if re.search(rx, t, re.I):
            out["family"] = fam
            break
    if out["family"] in ("SOT-23",):
        m = re.search(r"SOT-?23-?(\d)\b", t, re.I)
        pins = int(m.group(1)) if m else 3
        out["family"], out["pins"] = ("SOT-23", 3) if pins == 3 else (f"SOT-23-{pins}", pins)
    elif out["family"] in ("SOT-23-5", "SOT-23-6", "SC-70-3", "SC-70-5", "SC-70-6"):
        out["pins"] = int(out["family"][-1])
    elif out["family"] == "SOT-223":
        out["pins"] = 4  # 3 leads + tab
    elif out["family"] in ("SMA", "SMB", "SMC", "SMF", "SOD-323", "SOD-523", "SOD-123", "SOD-923",
                           "MiniMELF", "MELF", "DO-41", "DO-35"):
        out["pins"] = 2
    else:
        m = re.search(r"SOT-?23-?(\d)\b", t, re.I)
        if m:
            n = int(m.group(1))
            out["family"], out["pins"] = ("SOT-23" if n == 3 else f"SOT-23-{n}"), n

    if not out["family"]:
        fams = "|".join(sorted(set(PINNED), key=len, reverse=True))
        # "8-SOIC", "SOIC-8", "SOIC8", "16-TSSOP", "QFN-32-1EP"
        m = re.search(r"(?<![A-Za-z])(\d{1,3})\s*-\s*(?:Lead\s*)?(" + fams + r")(?![A-Za-z])", t, re.I)
        if m:
            out["family"], out["pins"] = m.group(2).upper(), int(m.group(1))
        else:
            m = re.search(r"(?<![A-Za-z])(" + fams + r")\s*-?\s*(\d{1,3})(?![\d.x])", t, re.I)
            if m:
                out["family"], out["pins"] = m.group(1).upper(), int(m.group(2))
            else:
                m = re.search(r"(?<![A-Za-z])(" + fams + r")(?![A-Za-z])", t, re.I)
                if m:
                    out["family"] = m.group(1).upper()
        if out["family"] in ("SO",) and not out["pins"]:
            out["family"] = None  # too ambiguous on its own

    if not out["family"]:
        chip = _chip(text)
        if chip:
            out["chip"], out["family"], out["pins"] = chip, "CHIP", 2
    if out["family"] and out["family"].startswith("TO-"):
        m = re.search(out["family"] + r"-(\d)", t)
        if m:
            out["pins"] = int(m.group(1))
    return out if out["family"] else None


def family_group(fam):
    if not fam:
        return None
    return FAMILY_GROUPS.get(fam, fam)


def compare(a, b):
    """Compare two parsed packages. Returns (status, reason), status in ok/mismatch/partial/unknown."""
    if not a or not b:
        return "unknown", "Pakken kunne ikke aflæses fra begge sider."
    if a["family"] == "CHIP" or b["family"] == "CHIP":
        if a["chip"] and b["chip"]:
            if a["chip"] == b["chip"]:
                return "ok", f"Begge er {a['chip']} ({CHIP_IMP_TO_MET[a['chip']]} metrisk)."
            return "mismatch", (f"Footprint er {a['chip']} men komponenten er {b['chip']} "
                                f"({CHIP_IMP_TO_MET[b['chip']]} metrisk).")
        return "mismatch", f"{a['raw']} og {b['raw']} er forskellige pakketyper."
    ga, gb = family_group(a["family"]), family_group(b["family"])
    thin = {"MSOP", "TSSOP", "SSOP"}
    if (a.get("ipc") or b.get("ipc")) and ga in thin and gb in thin:
        gb = ga   # IPC names only say "SOP": the shrink family is a guess, so let pins and pitch decide
    if ga != gb:
        # SOT-23 vs SOT-23-3 etc are handled by parse; QFN vs DFN is a real difference.
        return "mismatch", f"Pakketype {a['family']} passer ikke med {b['family']}."
    if a["pins"] and b["pins"] and a["pins"] != b["pins"]:
        # An exposed pad is often counted as an extra pin by one side only.
        if abs(a["pins"] - b["pins"]) == 1 and (a["ep"] or b["ep"]):
            pass
        else:
            return "mismatch", f"Antal ben: footprint {a['pins']}, komponent {b['pins']}."
    if a.get("pitch") and b.get("pitch") and abs(a["pitch"] - b["pitch"]) > 0.02:
        return "mismatch", f"Pitch: footprint {a['pitch']} mm, komponent {b['pitch']} mm."
    if a.get("body") and b.get("body"):
        if max(abs(x - y) for x, y in zip(a["body"], b["body"])) > 0.25:
            return "mismatch", (f"Kropsstørrelse: footprint {a['body'][0]}x{a['body'][1]} mm, "
                                f"komponent {b['body'][0]}x{b['body'][1]} mm.")
    wa = a.get("width") or (a["body"][0] if a.get("body") else None)
    wb = b.get("width") or (b["body"][0] if b.get("body") else None)
    if wa and wb and abs(wa - wb) > 0.3 and ga in ("SOIC", "SSOP", "TSSOP", "MSOP"):
        return "mismatch", f"Kropsbredde: footprint {wa} mm, komponent {wb} mm (smal/bred variant?)."
    if not (a["pins"] and b["pins"]) and ga not in ("SOT-23", "SOT-223", "SMA", "SMB", "SMC"):
        return "partial", f"Samme pakketype ({ga}), men antal ben kunne ikke bekræftes."
    return "ok", f"Samme pakke ({a['family']}" + (f", {a['pins']} ben" if a["pins"] else "") + ")."


def describe(pkg):
    if not pkg:
        return "?"
    if pkg["family"] == "CHIP":
        return f"{pkg['chip']} ({CHIP_IMP_TO_MET[pkg['chip']]} metrisk)"
    s = pkg["family"]
    if pkg["pins"] and not s.endswith(f"-{pkg['pins']}"):
        s += f"-{pkg['pins']}"
    if pkg.get("pitch"):
        s += f", pitch {pkg['pitch']} mm"
    if pkg.get("body"):
        s += f", {pkg['body'][0]}x{pkg['body'][1]} mm"
    return s


# ---- IPC-7351 nominal land patterns for chip parts (as used by the KiCad libraries)
# size: (pad width along axis, pad height across, centre-to-centre distance)
CHIP_LAND = {
    "R": {"01005": (0.4, 0.3, 0.5), "0201": (0.46, 0.4, 0.64), "0402": (0.54, 0.64, 1.02),
          "0603": (0.8, 0.95, 1.65), "0805": (1.025, 1.4, 1.825), "1206": (1.125, 1.75, 2.925),
          "1210": (1.125, 2.65, 2.925), "1812": (1.125, 3.4, 4.275), "2010": (1.225, 2.65, 4.625),
          "2512": (1.225, 3.35, 5.925)},
    "C": {"01005": (0.4, 0.3, 0.5), "0201": (0.46, 0.4, 0.64), "0402": (0.56, 0.62, 0.96),
          "0603": (0.9, 0.95, 1.55), "0805": (1.0, 1.45, 1.9), "1206": (1.15, 1.8, 2.95),
          "1210": (1.15, 2.7, 2.95), "1812": (1.4, 3.4, 4.1), "2220": (1.8, 5.4, 5.1)},
    "L": {"01005": (0.4, 0.3, 0.5), "0201": (0.46, 0.4, 0.64), "0402": (0.59, 0.64, 0.97),
          "0603": (0.875, 0.95, 1.575), "0805": (0.875, 1.2, 2.125), "1008": (1.25, 2.2, 2.15),
          "1206": (1.05, 1.9, 3.15), "1210": (1.25, 2.65, 2.8), "1806": (1.275, 1.9, 4.225),
          "1812": (1.125, 3.4, 4.275), "2010": (1.35, 2.65, 4.5), "2512": (1.35, 3.35, 5.8)},
}


# Nominal EIA chip bodies: (length L, width W, terminal length T) in mm
CHIP_BODY = {"01005": (0.4, 0.2, 0.1), "0201": (0.6, 0.3, 0.15), "0402": (1.0, 0.5, 0.25),
             "0603": (1.6, 0.8, 0.3), "0805": (2.0, 1.25, 0.4), "1008": (2.5, 2.0, 0.5),
             "1206": (3.2, 1.6, 0.5), "1210": (3.2, 2.5, 0.5), "1806": (4.5, 1.6, 0.5),
             "1812": (4.5, 3.2, 0.6), "2010": (5.0, 2.5, 0.6), "2220": (5.7, 5.0, 0.6),
             "2512": (6.35, 3.2, 0.6)}

# Manufacturer part-number patterns that reveal the chip size.
_MPN_SIZE = [
    (r"^GRM(15|18|21|31|32|43|55)", {"15": "0402", "18": "0603", "21": "0805", "31": "1206", "32": "1210",
                                     "43": "1812", "55": "2220"}),
    (r"^GCM(15|18|21|31|32)", {"15": "0402", "18": "0603", "21": "0805", "31": "1206", "32": "1210"}),
    (r"^CL(03|05|10|21|31|32)", {"03": "0201", "05": "0402", "10": "0603", "21": "0805", "31": "1206",
                                 "32": "1210"}),
    (r"^ERJ-?(1G|2|3|6|8|14|12|1T)", {"1G": "0201", "2": "0402", "3": "0603", "6": "0805", "8": "1206",
                                      "14": "1210", "12": "1812", "1T": "2512"}),
    (r"^BLM(03|15|18|21|31)", {"03": "0201", "15": "0402", "18": "0603", "21": "0805", "31": "1206"}),
    (r"^LQ[GMWH](03|15|18|21|31)", {"03": "0201", "15": "0402", "18": "0603", "21": "0805", "31": "1206"}),
    (r"^(?:C|CGA|CGJ)(0603|1005|1608|2012|3216|3225|4532|5750)[A-Z]", "metric"),
    (r"^(?:RC|CC|AC|AF|RT|RL|PE)(0201|0402|0603|0805|1206|1210|2010|2512)", "imperial"),
    (r"^(?:CRCW|CRGP?|RMCF|RNCP|ERA|TNPW|MCR|ESR|KTR|CR|RCS|MCT|CRG|CPF|WR|RK73)(0201|0402|0603|0805|1206|"
     r"1210|2010|2512)", "imperial"),
    (r"^(0201|0402|0603|0805|1206|1210|2010|2512)[A-Z]", "imperial"),
    (r"^(?:C|T|VJ|GJM|EMK|JMK|LMK|TMK|UMK|GMK|HMK)(0201|0402|0603|0805|1206|1210|1812)", "imperial"),
    (r"^(?:NM|LQM|MLZ|MLF|NR|VLS|CIG|CIH|BK)(0201|0402|0603|0805|1206|1210|1812)", "imperial"),
]


def mpn_chip_hint(mpn):
    """Chip size implied by a well-known MPN pattern, e.g. GRM188R61A226ME15D -> '0603'."""
    if not mpn:
        return None
    m_up = mpn.upper().replace(" ", "")
    for rx, mapping in _MPN_SIZE:
        m = re.match(rx, m_up)
        if not m:
            continue
        code = m.group(1)
        if mapping == "metric":
            return CHIP_MET_TO_IMP.get(code)
        if mapping == "imperial":
            return code if code in CHIP_IMP_TO_MET else None
        return mapping.get(code)
    return None
