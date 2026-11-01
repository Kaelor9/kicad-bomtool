"""Footprint verification: geometry measurements, comparison against a
reference footprint (manufacturer CAD file, KiCad library or IPC chip land
pattern), symbol-pin vs pad checks and package-name checks.
"""
import math
import re
import statistics

from . import packages as P
from .fields import passive_kind


def _numbered(pads):
    return [p for p in pads if p["num"] and p["type"] != "np_thru_hole"]


def _extent(p):
    """Half extents of a pad's bounding box in footprint coordinates."""
    a = math.radians(p.get("angle", 0) % 180)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    return (p["w"] * c + p["h"] * s) / 2, (p["w"] * s + p["h"] * c) / 2


def measure(geo):
    pads = _numbered(geo["pads"])
    nums = {p["num"] for p in pads}
    out = {"pads": len(pads), "pins": len(nums), "pitch": None, "ep": False, "bbox": None}
    if not pads:
        return out
    xs = [p["x"] for p in pads]
    ys = [p["y"] for p in pads]
    out["bbox"] = (round(max(xs) - min(xs), 3), round(max(ys) - min(ys), 3))
    areas = [p["w"] * p["h"] for p in pads]
    med = statistics.median(areas)
    big = [p for p, a in zip(pads, areas) if a > 4 * med]
    if len(pads) > 4 and len(big) == 1:
        out["ep"] = True
    regular = [p for p, a in zip(pads, areas) if a <= 4 * med]
    # Pitch: most common nearest-neighbour distance between regular pads.
    dists = []
    for i, p in enumerate(regular):
        best = None
        for j, q in enumerate(regular):
            if i != j:
                d = math.hypot(p["x"] - q["x"], p["y"] - q["y"])
                if d > 0.01 and (best is None or d < best):
                    best = d
        if best:
            dists.append(round(best, 2))
    if dists and len(regular) > 2:
        out["pitch"] = statistics.mode(dists)
    return out


# ---- reference geometry --------------------------------------------------------

def chip_reference(chip, kind):
    table = P.CHIP_LAND.get(kind) or P.CHIP_LAND["R"]
    land = table.get(chip) or P.CHIP_LAND["R"].get(chip)
    if not land:
        return None
    w, h, c = land
    pads = [{"num": "1", "type": "smd", "shape": "roundrect", "x": -c / 2, "y": 0, "w": w, "h": h, "angle": 0},
            {"num": "2", "type": "smd", "shape": "roundrect", "x": c / 2, "y": 0, "w": w, "h": h, "angle": 0}]
    return {"pads": pads, "graphics": []}


def chip_fit(geo, chip):
    """Does a 2-pad land pattern physically fit a chip of this size?

    Checks that each pad overlaps the part's metal terminal, that the pads reach
    past the part ends (toe fillet) without being absurdly long, and that the
    pad width suits the part width. Robust against IPC density variants.
    """
    body = P.CHIP_BODY.get(chip)
    pads = _numbered(geo["pads"])
    if not body or len(pads) != 2:
        return None
    L, W, T = body
    a, b = pads
    horizontal = abs(a["x"] - b["x"]) >= abs(a["y"] - b["y"])
    c = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
    ea, eb = _extent(a), _extent(b)
    along = (ea[0] + eb[0]) if horizontal else (ea[1] + eb[1])        # = pad length
    across = min(ea[1], eb[1]) * 2 if horizontal else min(ea[0], eb[0]) * 2
    inner, outer = (c - along) / 2, (c + along) / 2                    # from centre
    overlap = min(L / 2, outer) - max(L / 2 - T, inner)
    problems, warns = [], []
    if inner * 2 < 0.15:
        problems.append(f"afstanden mellem pads er kun {inner * 2:.2f} mm (kortslutningsrisiko)")
    if overlap < 0.2 * T:
        problems.append(f"pads rammer ikke komponentens terminaler ordentligt "
                        f"(overlap {max(overlap, 0):.2f} mm af {T} mm)")
    elif overlap < 0.5 * T:
        warns.append(f"lille overlap med terminalerne ({overlap:.2f} mm af {T} mm)")
    if outer * 2 < L - 0.05:
        problems.append(f"pad-mønstret ({outer * 2:.2f} mm) er kortere end komponenten ({L} mm)")
    elif outer * 2 > L + 2.0:
        warns.append(f"pads går {outer - L / 2:.2f} mm ud over komponenten (risiko for tombstoning)")
    if across < 0.6 * W:
        problems.append(f"pads er {across:.2f} mm brede, komponenten er {W} mm")
    elif across < 0.7 * W:
        warns.append(f"pads er smalle ({across:.2f} mm mod komponentbredde {W} mm)")
    status = "mismatch" if problems else ("warn" if warns else "ok")
    detail = "; ".join(problems + warns)
    msg = (f"Pads passer fysisk til en {chip} ({L}x{W} mm)." if status == "ok" else
           f"Som {chip} ({L}x{W} mm): {detail}.")
    return {"status": status, "msg": msg}


def _transform(p, rot, mirror):
    x, y = (-p["x"] if mirror else p["x"]), p["y"]
    r = math.radians(rot)
    nx, ny = x * math.cos(r) - y * math.sin(r), x * math.sin(r) + y * math.cos(r)
    q = dict(p)
    q["x"], q["y"] = nx, ny
    q["angle"] = ((-p.get("angle", 0) if mirror else p.get("angle", 0)) + rot) % 360
    return q


def compare_geometry(geo, ref):
    """Align `ref` onto `geo` (rotation/mirror/translation) and compare pad by pad.

    Returns dict(status, max_offset, size_diff, details, aligned_ref_pads).
    """
    a = _numbered(geo["pads"])
    b = _numbered(ref["pads"])
    if not a or not b:
        return {"status": "unknown", "msg": "Ingen pads at sammenligne."}
    best = None
    for mirror in (False, True):
        for rot in (0, 90, 180, 270):
            tb = [_transform(p, rot, mirror) for p in b]
            pairs = _pair(a, tb)
            if not pairs:
                continue
            dx = statistics.mean(pa["x"] - pb["x"] for pa, pb in pairs)
            dy = statistics.mean(pa["y"] - pb["y"] for pa, pb in pairs)
            err = [math.hypot(pa["x"] - pb["x"] - dx, pa["y"] - pb["y"] - dy) for pa, pb in pairs]
            score = (len(pairs), -max(err))
            if best is None or score > best[0]:
                best = (score, rot, mirror, dx, dy, pairs, err, tb)
    if best is None:
        return {"status": "unknown", "msg": "Pads kunne ikke parres."}
    _, rot, mirror, dx, dy, pairs, err, tb = best
    for p in tb:
        p["x"] += dx
        p["y"] += dy
    size_diffs = []
    details = []
    for (pa, pb), e in zip(pairs, err):
        ea, eb = _extent(pa), _extent(pb)
        sd = max(abs(ea[0] - eb[0]), abs(ea[1] - eb[1])) * 2
        size_diffs.append(sd)
        if e > 0.05 or sd > 0.1:
            details.append({"pad": pa["num"], "offset": round(e, 3), "size_diff": round(sd, 3),
                            "a": [round(pa["w"], 3), round(pa["h"], 3)], "b": [round(pb["w"], 3), round(pb["h"], 3)]})
    max_off, max_sd = max(err), max(size_diffs)
    nums_a = {p["num"] for p in a}
    nums_b = {p["num"] for p in b}
    missing = sorted(nums_b - nums_a, key=_nk)
    extra = sorted(nums_a - nums_b, key=_nk)
    if len(a) != len(b) or missing or extra:
        status = "mismatch"
    elif max_off <= 0.1 and max_sd <= 0.2:
        status = "ok"
    elif max_off <= 0.25 and max_sd <= 0.45:
        status = "warn"
    else:
        status = "mismatch"
    msg = (f"{len(pairs)} af {len(b)} pads parret; største placeringsfejl {max_off:.2f} mm, "
           f"største størrelsesforskel {max_sd:.2f} mm")
    if rot or mirror:
        msg += f" (reference drejet {rot}°" + (", spejlet" if mirror else "") + ")"
    if len(a) != len(b):
        msg += f". Antal pads: dit footprint {len(a)}, reference {len(b)}"
    if missing:
        msg += f". Pads i reference men ikke hos dig: {', '.join(missing[:8])}"
    if extra:
        msg += f". Ekstra pads hos dig: {', '.join(extra[:8])}"
    if mirror and geo.get("bottom"):
        msg = msg.replace(", spejlet)", ", spejlet – normalt for bundside)")
    if mirror and status != "mismatch" and not geo.get("bottom"):
        status = "warn"
        msg += ". OBS: passer kun spejlvendt – tjek at pin 1 og pinout ikke er byttet om"
    return {"status": status, "msg": msg + ".", "max_offset": round(max_off, 3), "size_diff": round(max_sd, 3),
            "details": details[:20], "ref_pads": tb}


def _pair(a, b):
    """Pair pads by number; for pads sharing a number, nearest first."""
    by_num = {}
    for p in b:
        by_num.setdefault(p["num"], []).append(p)
    pairs = []
    # Reference centroid offset for nearest matching
    for num in {p["num"] for p in a}:
        la = [p for p in a if p["num"] == num]
        lb = list(by_num.get(num, []))
        for pa in la:
            if not lb:
                break
            pb = min(lb, key=lambda q: abs(q["w"] * q["h"] - pa["w"] * pa["h"]))
            lb.remove(pb)
            pairs.append((pa, pb))
    return pairs


def _nk(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


# ---- symbol pins vs pads --------------------------------------------------------

def pins_vs_pads(pins, geo, names=None):
    if not pins:
        return None
    pads = {p["num"] for p in _numbered(geo["pads"])}
    pins = set(pins)
    missing = sorted(pins - pads, key=_nk)
    extra = sorted(pads - pins, key=_nk)
    names = names or {}
    # Pins with the same name as a pin that has a pad (MOSFET drain 5-8 on one pad, USB-C VBUS/GND pairs)
    # are one connection - the footprint simply merges them.
    present = {names[p].upper() for p in pins & pads if names.get(p)}
    merged = [m for m in missing if names.get(m) and names[m].upper() in present]
    if missing and len(merged) == len(missing):
        groups = sorted({names[m] for m in merged})
        return {"check": "Symbol-ben ↔ pads", "status": "ok",
                "msg": f"Ben {', '.join(merged[:10])} ({', '.join(groups)}) har ingen egen pad, men deler navn med et ben "
                       "der har – footprintet har slået dem sammen til én pad (samme forbindelse)."}
    missing = [m for m in missing if m not in merged]
    if missing:
        return {"check": "Symbol-ben ↔ pads", "status": "mismatch",
                "msg": f"Symbolet har ben {', '.join(missing[:10])} som ikke findes som pad i footprintet – "
                       "de bliver ikke forbundet."}
    if extra:
        mech = [e for e in extra if not e.isdigit() or e.upper() in ("EP", "MP", "SH", "PAD")]
        # An exposed/thermal pad: one extra pad that is much bigger than the rest.
        numbered = _numbered(geo["pads"])
        areas = sorted(p["w"] * p["h"] for p in numbered)
        median = areas[len(areas) // 2] if areas else 0
        big = {p["num"] for p in numbered if median and p["w"] * p["h"] > 3 * median}
        if len(extra) == 1 and extra[0] in big:
            return {"check": "Symbol-ben ↔ pads", "status": "ok",
                    "msg": f"Alle {len(pins)} ben har en pad. Pad {extra[0]} er en exposed/thermal pad uden ben "
                           "i symbolet – tjek i databladet om den skal forbindes (typisk GND)."}
        if len(mech) == len(extra):
            return {"check": "Symbol-ben ↔ pads", "status": "ok",
                    "msg": f"Alle {len(pins)} ben har en pad. Ekstra mekaniske pads: {', '.join(extra[:6])}."}
        return {"check": "Symbol-ben ↔ pads", "status": "warn",
                "msg": f"Footprintet har pads {', '.join(extra[:10])} uden tilsvarende ben i symbolet "
                       "(ofte OK for exposed pad/tab, men tjek det)."}
    return {"check": "Symbol-ben ↔ pads", "status": "ok", "msg": f"Alle {len(pins)} ben matcher en pad."}


# ---- full report ------------------------------------------------------------------

def report(comp, part_pkg_text=None, part_pkg_source="", reference=None, reference_name=""):
    """Run every check that has data available. Returns a dict for the UI."""
    checks = []
    geo = comp.get("geometry")
    fp_name = comp.get("footprint", "")
    fp_pkg = P.parse_package(fp_name)
    if fp_pkg is None and comp.get("package_field"):
        fp_pkg = P.parse_package(comp["package_field"])
    meas = measure(geo) if geo else None
    kind = passive_kind(comp["ref"], comp.get("lib_id", ""))
    overlay = None

    if not fp_name and not geo:
        checks.append({"check": "Footprint", "status": "mismatch", "msg": "Komponenten har intet footprint."})

    # 1. Name vs the part's real package (from distributor data / BOM description)
    part_pkg = P.parse_package(part_pkg_text) if part_pkg_text else None
    if part_pkg_text:
        status, msg = P.compare(fp_pkg, part_pkg)
        if status == "unknown" and meas and part_pkg and part_pkg["pins"]:
            # Footprint name says nothing useful: compare pad count instead.
            pc = meas["pins"]
            if pc == part_pkg["pins"] or (part_pkg.get("ep") or meas["ep"]) and abs(pc - part_pkg["pins"]) == 1:
                status, msg = "partial", f"Navnet siger ikke pakken, men antal pads ({pc}) passer med {P.describe(part_pkg)}."
            else:
                status, msg = "mismatch", f"Footprintet har {pc} pads, men komponenten er {P.describe(part_pkg)}."
        checks.append({"check": "Navn ↔ komponentens pakke", "status": status,
                       "msg": msg + (f" (Pakke fra {part_pkg_source}: '{part_pkg_text}')" if part_pkg_source else "")})

    # 2. Footprint name vs its own geometry (catches renamed / edited footprints)
    if fp_pkg and meas and meas["pads"]:
        problems = []
        if fp_pkg["pins"] and fp_pkg["family"] != "CHIP":
            pc = meas["pins"]
            # +1 is nearly always an exposed pad or tab that the name doesn't count.
            nums = [int(n) for n in {p["num"] for p in _numbered(geo["pads"])} if n.isdigit()]
            # Packages that leave a lead out (optocouplers in "SO6" with pin 2 missing) number up to the full count.
            skipped = pc < fp_pkg["pins"] and nums and max(nums) == fp_pkg["pins"]
            if pc != fp_pkg["pins"] and pc != fp_pkg["pins"] + 1 and fp_pkg["family"] != "SOT-223" and not skipped:
                problems.append(f"navnet siger {fp_pkg['pins']} ben men der er {pc} pads")
        # SOT/SC/TO packages leave lead positions empty, so the nearest-neighbour pitch isn't the nominal one.
        irregular = re.match(r"(SOT|SC-|TO-|SOD|DO-|SM[ABCF]|MELF|MiniMELF)", fp_pkg["family"] or "")
        if fp_pkg.get("pitch") and meas["pitch"] and abs(fp_pkg["pitch"] - meas["pitch"]) > 0.03 \
                and fp_pkg["family"] != "CHIP" and not irregular:
            problems.append(f"navnet siger pitch {fp_pkg['pitch']} mm men målt er {meas['pitch']} mm")
        checks.append({"check": "Navn ↔ egen geometri", "status": "warn" if problems else "ok",
                       "msg": ("; ".join(problems).capitalize() + ".") if problems else
                       f"Geometrien passer med navnet ({meas['pins']} pads"
                       + (f", pitch {meas['pitch']} mm" if meas["pitch"] else "") + ")."})

    # 3. Geometry vs a reference: uploaded manufacturer file > IPC chip > KiCad library
    ref_geo, ref_label = None, ""
    if reference:
        ref_geo, ref_label = reference, f"producent/CAD-fil ({reference_name})"
    elif geo and (fp_pkg and fp_pkg["family"] == "CHIP" or part_pkg and part_pkg["family"] == "CHIP"):
        chip = (part_pkg or {}).get("chip") or fp_pkg["chip"]
        ref_geo = chip_reference(chip, kind or "R")
        ref_label = f"IPC-7351 nominel {chip} ({P.CHIP_IMP_TO_MET.get(chip, '')} metrisk)"
    elif geo and comp.get("lib_geometry") and comp.get("geometry_source") == "PCB":
        ref_geo, ref_label = comp["lib_geometry"], f"{comp.get('lib_geometry_source', 'bibliotek')}: {fp_name}"
    if geo and ref_geo:
        res = compare_geometry(geo, ref_geo)
        if "IPC" in ref_label:
            # IPC density variants differ legitimately, so judge by physical fit instead.
            fit = chip_fit(geo, chip)
            if fit:
                checks.append({"check": "Pads ↔ komponentens fysiske mål", "status": fit["status"],
                               "msg": fit["msg"]})
        elif res["status"] != "unknown":
            status, msg = res["status"], res["msg"]
            if not reference and status == "mismatch":
                # The library is not the truth, only the starting point: flag the edit, don't fail it.
                status = "warn"
                msg = "Footprintet på PCB'en afviger fra biblioteket (redigeret lokalt?): " + msg
            checks.append({"check": "Geometri ↔ " + ref_label.split(" (")[0].split(":")[0],
                           "status": status, "msg": msg})
        if res["status"] != "unknown":
            overlay = {"ref_pads": res.get("ref_pads"), "ref_label": ref_label, "details": res.get("details")}

    # 4. Symbol pins vs pads
    if geo:
        pv = pins_vs_pads(comp.get("pins"), geo, comp.get("pin_names"))
        if pv:
            checks.append(pv)

    order = {"mismatch": 3, "warn": 2, "partial": 1, "unknown": 1, "ok": 0}
    worst = max((c["status"] for c in checks), key=lambda s: order[s], default="unknown")
    if not checks:
        worst = "unknown"
    oks = sum(1 for c in checks if c["status"] == "ok")
    if worst == "ok" and oks < 2:
        worst = "partial"  # only one independent confirmation
    return {"status": worst, "checks": checks, "footprint_pkg": P.describe(fp_pkg) if fp_pkg else "",
            "part_pkg": P.describe(part_pkg) if part_pkg else "", "measure": meas, "overlay": overlay}
