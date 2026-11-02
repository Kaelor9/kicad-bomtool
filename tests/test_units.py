"""Unit checks for the pieces the demo projects don't exercise.

Run:  python -m tests.test_units   (from the project folder)
"""
import copy
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bomtool import distbom, footprint, kicad, pricing  # noqa: E402
from bomtool.packages import parse_package  # noqa: E402

_dirs = kicad.kicad_install_footprint_dirs()
LIB = _dirs[0] if _dirs else None   # tests that need KiCad's own libraries are skipped without it


class Skip(Exception):
    pass


def load(lib, name):
    if LIB is None:
        raise Skip("KiCad er ikke installeret")
    with open(os.path.join(LIB, lib + ".pretty", name + ".kicad_mod"), encoding="utf-8") as fh:
        return kicad.load_kicad_mod(fh.read())[0]


def check(name, cond, info=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  [{info}]" if info else ""))
    if not cond:
        check.failed = True


check.failed = False


def test_reference_compare():
    soic = load("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm")
    same = footprint.compare_geometry(soic, copy.deepcopy(soic))
    check("identical footprint = ok", same["status"] == "ok", same["msg"])
    # Rotated 90° reference must still align perfectly
    rot = copy.deepcopy(soic)
    for p in rot["pads"]:
        p["x"], p["y"], p["angle"] = p["y"], -p["x"], (p["angle"] + 90) % 360
    r = footprint.compare_geometry(soic, rot)
    check("rotated reference aligns", r["status"] == "ok", r["msg"])
    # Wide-body SOIC (7.5 mm) vs narrow: rows too far apart
    wide = load("Package_SO", "SOIC-8_7.5x5.85mm_P1.27mm")
    r = footprint.compare_geometry(soic, wide)
    check("narrow vs wide SOIC = mismatch", r["status"] == "mismatch", r["msg"])
    # Pin 1 swapped with pin 8 (mirrored pinout)
    mir = copy.deepcopy(soic)
    for p in mir["pads"]:
        p["x"] = -p["x"]
    r = footprint.compare_geometry(soic, mir)
    check("mirrored pinout flagged", r["status"] in ("warn", "mismatch") and "spejl" in r["msg"], r["msg"])
    # One pad 0.3 mm off
    bad = copy.deepcopy(soic)
    bad["pads"][2]["y"] += 0.3
    r = footprint.compare_geometry(soic, bad)
    check("single shifted pad found", r["status"] != "ok" and any(d["pad"] == bad["pads"][2]["num"] for d in r["details"]),
          r["msg"])


def test_chip_fit():
    for size, met in (("0402", "1005"), ("0603", "1608"), ("0805", "2012"), ("1206", "3216")):
        geo = load("Resistor_SMD", f"R_{size}_{met}Metric")
        fit = footprint.chip_fit(geo, size)
        check(f"KiCad R_{size} fits {size}", fit["status"] == "ok", fit["msg"])
    geo = load("Resistor_SMD", "R_0402_1005Metric")
    fit = footprint.chip_fit(geo, "0805")
    check("0402 pads for an 0805 part = mismatch", fit["status"] == "mismatch", fit["msg"])
    geo = load("Resistor_SMD", "R_1206_3216Metric")
    fit = footprint.chip_fit(geo, "0402")
    check("1206 pads for an 0402 part = mismatch", fit["status"] == "mismatch", fit["msg"])


def test_pins_vs_pads():
    soic = load("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm")
    r = footprint.pins_vs_pads([str(i) for i in range(1, 9)], soic)
    check("8 pins on SOIC-8 = ok", r["status"] == "ok", r["msg"])
    r = footprint.pins_vs_pads(["1", "2", "3"], load("Diode_SMD", "D_SOD-123"))
    check("3-pin symbol on 2-pad footprint = mismatch", r["status"] == "mismatch", r["msg"])
    r = footprint.pins_vs_pads(["A", "K"], load("Diode_SMD", "D_SOD-123"))
    check("A/K symbol on 1/2 pads = mismatch", r["status"] == "mismatch", r["msg"])


def test_package_compare():
    from bomtool.packages import compare
    cases = [("SOT-23-5", "SC-74A, SOT-753", "ok"), ("SOT-23", "TO-236-3, SC-59, SOT-23-3", "ok"),
             ("QFN-32-1EP_5x5mm_P0.5mm", "32-VFQFN Exposed Pad", "ok"), ("TSSOP-20", "20-SSOP", "mismatch"),
             ("LQFP-48_7x7mm_P0.5mm", "48-LQFP (7x7)", "ok"), ("D_SMA", "DO-214AC, SMA", "ok"),
             ("D_SMA", "DO-214AA, SMB", "mismatch"), ("SOIC-8_3.9x4.9mm", "8-SOIC (0.209\", 5.30mm Width)", "mismatch")]
    for a, b, want in cases:
        st, msg = compare(parse_package(a), parse_package(b))
        check(f"{a} vs {b} -> {want}", st == want, f"{st}: {msg}")


def test_dist_xlsx_header_offset():
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["DigiKey order 1234"]); ws.append([]); ws.append(["Kunde: test"]); ws.append([])
    ws.append(["Index", "Quantity", "DigiKey Part #", "Manufacturer Part Number", "Description", "Customer Reference",
               "Available", "Unit Price", "Extended Price"])
    ws.append([1, 20, "311-10.0KHRCT-ND", "RC0603FR-0710KL", "RES 10K OHM 1% 1/10W 0603", "R1,R2", 100000, 0.74, 14.8])
    ws.append([2, 10, "1276-1000-1-ND", "CL10B104KB8NNNC", "CAP CER 0.1UF 50V X7R 0603", "", 50000, 0.6, 6])
    buf = io.BytesIO(); wb.save(buf)
    d = distbom.load("digikey.xlsx", buf.getvalue())
    check("xlsx: header found below title rows", d["columns"].get("mpn") == "Manufacturer Part Number", str(d["columns"]))
    check("xlsx: qty column is Quantity, not Available", d["columns"].get("qty") == "Quantity", str(d["columns"]))
    check("xlsx: distributor = DigiKey", d["distributor"] == "DigiKey", d["distributor"])
    check("xlsx: 2 lines, price parsed", len(d["lines"]) == 2 and abs(d["lines"][0]["unit_price"] - 0.74) < 1e-9)
    # Match: line without MPN matched by value+package; line with MPN in refs column
    lines = [{"id": "R1", "refs": ["R1", "R2"], "mpn": "", "dist": {}, "kind": "R", "parsed": {"value": 10000.0},
              "footprint": "Resistor_SMD:R_0603_1608Metric"},
             {"id": "C1", "refs": ["C1"], "mpn": "", "dist": {}, "kind": "C", "parsed": {"value": 1e-7},
              "footprint": "Capacitor_SMD:C_0603_1608Metric"},
             {"id": "C9", "refs": ["C9"], "mpn": "", "dist": {}, "kind": "C", "parsed": {"value": 1e-7},
              "footprint": "Capacitor_SMD:C_0805_2012Metric"}]
    res, extras = distbom.match(lines, d)
    by = {r["id"]: r for r in res}
    check("match by customer reference", by["R1"]["how"].startswith("reference"), by["R1"]["how"])
    check("match by value + package", by["C1"]["how"] == "værdi + pakke", by["C1"]["how"])
    check("0805 cap not matched to 0603 line", by["C9"]["status"] == "missing", by["C9"]["status"])


def test_mouser_html_xls():
    html = ("<html><body><table><tr><th>Mouser #:</th><th>Mfr. #:</th><th>Desc.:</th><th>Order Qty.</th>"
            "<th>Price (DKK)</th></tr><tr><td>595-NE555DR</td><td>NE555DR</td><td>Timer SOIC-8</td><td>1.000</td>"
            "<td>1,23 kr.</td></tr></table></body></html>").encode()
    d = distbom.load("cart.xls", html)
    l = d["lines"][0]
    check("html-xls parsed", l["mpn"] == "NE555DR" and l["qty"] == 1000 and abs(l["unit_price"] - 1.23) < 1e-9,
          str(l))
    check("html-xls distributor = Mouser", d["distributor"] == "Mouser", d["distributor"])


def test_pricing():
    offer = {"seller": "X", "breaks": [[1, 1.20], [10, 0.62], [100, 0.18]], "moq": 1, "mult": 1, "stock": 1e6}
    b = pricing.best_buy(offer, 60)
    check("60 needed -> buy 100 (cheaper)", b["qty"] == 100 and abs(b["total"] - 18) < 1e-9, str(b["suggestions"]))
    b = pricing.best_buy(offer, 3, 5, 10)
    check("3 needed -> buy 10 (6.20 vs 3.60? no: keep 3)", b["qty"] == 3, f"{b['qty']} {b['total']}")
    check("3 needed -> suggests 10 for small extra", any(s["kind"] == "consider" and s["qty"] == 10
                                                         for s in b["suggestions"]), str(b["suggestions"]))
    offer = {"seller": "Y", "breaks": [[2500, 0.01]], "moq": 2500, "mult": 2500, "stock": 1e6}
    b = pricing.best_buy(offer, 30)
    check("reel MOQ respected", b["qty"] == 2500, str(b["qty"]))


def test_datasheet():
    import zlib
    from bomtool import datasheet as D
    from bomtool import packages as PK
    content = b"BT 72 700 Td (ORDERING INFORMATION) Tj T* [(NE555)-300(DR)] TJ ( SOIC-8 Tape) Tj ET"
    comp = zlib.compress(content)
    pdf = b"%PDF-1.4\n2 0 obj<</Length 1/Filter/FlateDecode>>stream\n" + comp + b"\nendstream\nendobj\n%%EOF"
    txt = D._simple_text(pdf)
    check("built-in PDF reader finds text", "NE555 DR SOIC-8" in txt, repr(txt))
    found = {PK.describe(p) for p, _ in D.packages_in("D (SOIC, 8) and 8-pin MSOP, SOT-23-5, SC70-6, TO-220 (3)")}
    check("datasheet package names", {"SOIC-8", "MSOP-8", "SOT-23-5", "SC-70-6", "TO-220-3"} <= found, str(found))
    orig = D.text_for
    D.text_for = lambda url: "x" * 300 + "\nNE555DR  SOIC-8  2500\nNE555P  PDIP-8  50\n"
    try:
        fp = PK.parse_package("SOIC-8_3.9x4.9mm_P1.27mm")
        check("datasheet: ordering line matches footprint", D.check("http://x", "NE555DR", fp)["status"] == "ok")
        check("datasheet: DIP part on SOIC footprint = mismatch", D.check("http://x", "NE555P", fp)["status"] == "mismatch")
    finally:
        D.text_for = orig


# Text as pypdf gives it for a Diodes and a TI datasheet (shortened).
DIODES = ("Pin Descriptions\nPin Name Pin Number I/O Function\nIN 1 6 I Input\nGND 2 5 — Ground\n"
          "EN 3 4 I Enable\nFAULT 4 3 O Fault\nILIM 5 2 O Limit\nOUT 6 1 O Output\n\f"
          "Package Outline Dimensions\n(1) Package Type: SOT26\nSOT26\nDim Min Max Typ\nA1 0.013 0.10 0.05\n"
          "b 0.35 0.50 0.38\nD 2.90 3.10 3.00\ne - - 0.95\nE 2.70 3.00 2.80\nE1 1.50 1.70 1.60\n"
          "L 0.35 0.55 0.40\nAll Dimensions in mm\n\fSuggested Pad Layout\n(1) Package Type: SOT26\n"
          "Dimensions Value (in mm)\nC 2.40\nC1 0.95\nX 0.55\nY 0.80\nY1 3.20\n")
TI = ("7.1 Q5A Package Dimensions\nMILLIMETERS INCHES\nDIM\nMIN NOM MAX MIN NOM MAX\nA 0.90 1.00 1.10 0.035 0.039 0.043\n"
      "b 0.33 0.41 0.51 0.013 0.016 0.020\nD1 4.80 4.90 5.00 0.189 0.193 0.197\nE 5.90 6.00 6.10 0.232 0.236 0.240\n"
      "e 1.17 1.27 1.37 0.046 0.050 0.054\nL 0.51 0.61 0.71 0.020 0.024 0.028\n")


def test_dsdata():
    from bomtool import dsdata as X
    t = X.dim_tables(DIODES)
    check("Diodes table: SOT26 found on page 2", len(t) == 1 and t[0]["page"] == 2 and t[0]["name"].startswith("SOT-23-6"),
          str([(x["page"], x["name"]) for x in t]))
    d = t[0]["dims"]
    check("Min/Max/Typ column order", d["D"] == {"min": 2.9, "nom": 3.0, "max": 3.1} and d["e"]["nom"] == 0.95, str(d["D"]))
    t = X.dim_tables(TI)
    check("TI table: mm columns of a mm+inch table", t and t[0]["dims"]["E"] == {"min": 5.9, "nom": 6.0, "max": 6.1},
          str(t and t[0]["dims"].get("E")))
    lands = X.pad_layouts(DIODES)
    check("suggested pad layout", lands and lands[0]["values"] == {"C": 2.4, "C1": 0.95, "X": 0.55, "Y": 0.8, "Y1": 3.2},
          str(lands))
    pins = X.pin_tables(DIODES)
    best = X.best_pin_map({"1": "IN", "2": "GND", "3": "EN", "4": "~{FAULT}", "5": "ILIM", "6": "OUT"}, pins)
    check("pin table column for SOT26 chosen", best and best["pins"]["1"] == "IN" and best["pins"]["6"] == "OUT", str(best))
    m, s, diff, miss = X.compare_pins({"1": "IN", "2": "VCC", "3": "OUT"}, {"1": "IN", "2": "VDD", "3": "EN"})
    check("pin compare: same / same type / different", (m, s, len(diff)) == (1, 1, 1), str((m, s, diff)))


def test_fpcompare():
    from bomtool import dsdata as X, fpcompare as C
    geo = load("Package_TO_SOT_SMD", "SOT-23-6")
    f = C.features(geo)
    check("SOT-23-6 measures", f["pitch"] == 0.95 and len(f["rows"]) == 1, str(f))
    rows = C.compare_dims(f, X.dim_tables(DIODES)[0]["dims"], "SOT-23-6")
    check("SOT-23-6 footprint fits SOT26 table", rows and all(r["status"] == "ok" for r in rows),
          str([(r["what"], r["status"]) for r in rows]))
    narrow = dict(geo, pads=[dict(p, y=p["y"] * 0.5) for p in geo["pads"]])   # wrong pitch
    rows = C.compare_dims(C.features(narrow), X.dim_tables(DIODES)[0]["dims"], "SOT-23-6")
    check("wrong pitch is caught", any(r["what"].startswith("Pitch") and r["status"] == "mismatch" for r in rows))


def _pads(nums, pitch=1.27):
    return {"pads": [{"num": n, "x": 0, "y": i * pitch, "w": 1.5, "h": 0.6, "angle": 0, "type": "smd", "shape": "rect"}
                     for i, n in enumerate(nums)], "graphics": []}


def test_real_projects():
    """Cases found in real KiCad 8 projects."""
    from bomtool import datasheet as D, fields as F, footprint as FP, kicad as K, packages as P
    # MOSFET with drain pins 5-8 on one pad, USB-C with doubled VBUS/GND
    names = {"1": "S", "2": "S", "3": "S", "4": "G", "5": "D", "6": "D", "7": "D", "8": "D"}
    r = FP.pins_vs_pads(list(names), _pads(["1", "2", "3", "4", "5"]), names)
    check("merged drain pins are OK", r["status"] == "ok", r["msg"])
    r = FP.pins_vs_pads(["1", "2", "3"], _pads(["1", "2"]), {"1": "A", "2": "B", "3": "C"})
    check("a really missing pad is still caught", r["status"] == "mismatch", r["msg"])
    # SO6 optocoupler with pin 2 left out
    comp = {"ref": "IC3", "footprint": "Lib:SOIC-6", "package_field": "", "pins": ["1", "3", "4", "5", "6"],
            "geometry": _pads(["1", "3", "4", "5", "6"]), "lib_id": ""}
    rep = FP.report(comp)
    own = next(c for c in rep["checks"] if c["check"] == "Navn ↔ egen geometri")
    check("SOIC-6 with pin 2 missing is OK", own["status"] == "ok", own["msg"])
    # IPC name for an HTSSOP with PowerPAD
    a = P.parse_package("SOP65P640X120-17N")
    check("SOP65P640X120-17N = TSSOP-16 + EP", (a["family"], a["pins"], a["ep"]) == ("TSSOP", 16, True), str(a))
    check("... and fits 16-HTSSOP", P.compare(a, P.parse_package("16-HTSSOP"))[0] == "ok")
    # Generic KiCad names are not part numbers
    check("Screw_Terminal_01x07 is not an MPN", not F.looks_like_mpn("Screw_Terminal_01x07"))
    check("TLP2361_TPL,E is an MPN", F.looks_like_mpn("TLP2361_TPL,E"))
    # MPN and manufacturer typed into each other's fields
    c = K._new_component("SW1", {"Value": "~", "Mfr. No:": "C&K", "Mfr.": "PTS810SJM250SMTR LFS"}, "", "/", "x")
    check("swapped MPN/manufacturer fields fixed", c["mpn"] == "PTS810SJM250SMTR LFS" and c["mfr"] == "C&K", str(c["mpn"]))
    # A datasheet for another part
    orig = D.text_for
    D.text_for = lambda url: "x" * 300 + "\nLT1963A regulator SOT-223\nMF-MSMF075/30 fuse 1812\n"
    try:
        check("wrong datasheet detected", "forkert datablad" in D.check("http://x", "AP7365-33YG-13", None)["msg"])
        check("suffixes don't trigger it", "forkert" not in D.check("http://x", "MF-MSMF075/30-2", None)["msg"])
    finally:
        D.text_for = orig


def test_dsland():
    """Reading the recommended footprint from a datasheet drawing (synthetic shapes, no PDF needed)."""
    from bomtool import dsland
    # Bourns MF-MSMF style 2: pads drawn 23 x 40 pt, NOT to scale, with the measures 1.68, 2.95 and 3.1.
    pads = [(382.8, 325.2, 406.1, 365.6, True), (447.0, 325.2, 469.7, 365.6, True)]
    arrows = [(383.4, 379.3, "x", -1), (406.3, 379.3, "x", 1), (406.9, 379.4, "x", -1), (446.0, 379.4, "x", 1),
              (487.8, 325.3, "y", -1), (487.8, 365.3, "y", 1)]
    texts = [(1.68, 361.2, 375.4), (3.1, 470.6, 375.5), (2.95, 488.1, 340.2)]
    dims = dsland._dims(arrows, texts)
    check("dimension lines get their numbers", sorted(d[3] for d in dims) == [1.68, 2.95, 3.1], str(dims))
    xs, _ = dsland._solve(pads, dims, "x")
    ys, _ = dsland._solve(pads, dims, "y")
    w = [round(b - a, 2) for a, b in xs]
    gap = round(xs[1][0] - xs[0][1], 2)
    check("pads from the measures, not the drawing's scale", w == [1.68, 1.68] and gap == 3.1 and
          round(ys[0][1] - ys[0][0], 2) == 2.95, f"{xs} {ys}")
    # Arrow heads point at the tip; a rectangle needs four corners on its box (a triangle has three).
    check("arrow head tip", dsland._arrow([(10, 5), (14, 3), (14, 7)])[:4] == (10, 5, "x", -1))
    check("triangle is not a pad", not dsland._boxy([(10, 5), (14, 3), (14, 7)], (10, 3, 14, 7)))
    check("table rows (touching) are not pads", not dsland._apart([(0, 0, 50, 10, False), (0, 10, 50, 20, False)]))
    # "4X (0.95)": one pitch measure holds for every pair of neighbours drawn as far apart.
    col = [(0, y, 20, y + 10, False) for y in (0, 30, 60)]
    d2 = [("y", 5.0, 35.0, 0.95), ("y", 0.0, 10.0, 0.6), ("x", 0.0, 20.0, 1.1)]
    ys2, _ = dsland._solve(col, d2, "y")
    check("repeated pitch", ys2 and round(ys2[2][0] - ys2[0][0], 2) == 1.9, str(ys2))


def test_recognise_kind():
    from bomtool import fplib
    check("a fuse is not shown as a diode", not fplib._kind_ok("Diode_SMD:D_MELF", "F1"))
    check("a fuse may match a fuse", fplib._kind_ok("Fuse:Fuse_1812_4532Metric", "F1"))
    check("package libraries fit anything", fplib._kind_ok("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "F1"))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
            except Skip as e:
                print(f"SKIP {name}: {e}")
    print("ALL PASSED" if not check.failed else "SOME FAILED")
    sys.exit(1 if check.failed else 0)
