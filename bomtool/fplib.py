"""An index of every footprint in the installed KiCad libraries, so a footprint can be recognised from
its geometry alone ("your 'MyChip_v2' is Package_SO:SOIC-8_3.9x4.9mm_P1.27mm"), and so a package name
can be drawn as a small footprint.

Reading ~15 000 .kicad_mod files takes about a minute, so it happens once in the background and the
result is cached on disk.
"""
import glob
import gzip
import hashlib
import json
import os
import threading

from . import packages as P
from .config import cache_dir
from .footprint import _extent, _numbered, compare_geometry
from .kicad import kicad_install_footprint_dirs, load_kicad_mod

_state = {"entries": None, "progress": 0, "total": 0, "building": False, "error": ""}
_lock = threading.Lock()
_pkg_cache = {}


def _sig(pads):
    """Rotation-free signature: pad count, sorted span of the pad centres, total copper area."""
    if not pads:
        return None
    xs = [p["x"] for p in pads]
    ys = [p["y"] for p in pads]
    span = sorted((max(xs) - min(xs), max(ys) - min(ys)))
    area = sum(4 * _extent(p)[0] * _extent(p)[1] for p in pads)
    return len(pads), round(span[0], 3), round(span[1], 3), round(area, 3)


def _index_file(dirs, files):
    key = hashlib.sha1(("|".join(dirs) + str(len(files)) + str(max((os.path.getmtime(d) for d in dirs), default=0)))
                       .encode()).hexdigest()[:12]
    return os.path.join(cache_dir(), f"fpindex-{key}.json.gz")


def _build():
    dirs = kicad_install_footprint_dirs()
    files = sorted(f for d in dirs for f in glob.glob(os.path.join(d, "*.pretty", "*.kicad_mod")))
    path = _index_file(dirs, files)
    if os.path.exists(path):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    _state["total"] = len(files)
    entries = []
    for i, f in enumerate(files):
        _state["progress"] = i
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                geo, _ = load_kicad_mod(fh.read())
        except OSError:
            continue
        if not geo:
            continue
        pads = [p for p in _numbered(geo["pads"]) if p.get("type") != "np_thru_hole"]
        sig = _sig(pads)
        if not sig:
            continue
        lib = os.path.basename(os.path.dirname(f))[:-len(".pretty")]
        name = os.path.basename(f)[:-len(".kicad_mod")]
        body = None
        xs = [v for g in geo["graphics"] if g["l"] == "fab" and g["k"] in ("line", "rect") for v in (g["x1"], g["x2"])]
        ys = [v for g in geo["graphics"] if g["l"] == "fab" and g["k"] in ("line", "rect") for v in (g["y1"], g["y2"])]
        if xs:
            body = [round(min(xs), 3), round(min(ys), 3), round(max(xs), 3), round(max(ys), 3)]
        entries.append({"id": f"{lib}:{name}", "sig": sig, "body": body,
                        "pads": [[p["num"], round(p["x"], 4), round(p["y"], 4), round(p["w"], 4), round(p["h"], 4),
                                  round(p.get("angle", 0), 2), p["shape"], p["type"], round(p.get("rratio", 0), 3)]
                                 for p in pads]})
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(entries, fh)
    return entries


def ensure(background=True):
    """Start building/loading the index. Returns True when it is ready."""
    with _lock:
        if _state["entries"] is not None:
            return True
        if _state["building"]:
            return False
        _state["building"] = True

    def run():
        try:
            entries = _build()
            _state["entries"] = entries
        except Exception as e:  # noqa: BLE001 - recognition is optional
            _state["error"] = str(e)
            _state["entries"] = []
        finally:
            _state["building"] = False

    if background:
        threading.Thread(target=run, daemon=True).start()
        return False
    run()
    return True


def status():
    e = _state["entries"]
    return {"ready": e is not None, "count": len(e) if e else 0, "progress": _state["progress"],
            "total": _state["total"], "error": _state["error"]}


def _geo(entry):
    return {"pads": [{"num": n, "x": x, "y": y, "w": w, "h": h, "angle": a, "shape": s, "type": t, "rratio": r}
                     for n, x, y, w, h, a, s, t, r in entry["pads"]], "graphics": []}


def geometry(entry):
    g = _geo(entry)
    if entry.get("body"):
        x0, y0, x1, y1 = entry["body"]
        g["graphics"] = [{"k": "rect", "l": "fab", "x1": x0, "y1": y0, "x2": x1, "y2": y1}]
    return g


# Libraries that only hold one kind of part. A footprint is not "recognised" as one of these when the
# reference says it is another kind (a fuse F1 is not a D_MELF diode even if the pads look alike).
# Libraries not listed here (Package_*, ...) fit any part.
TYPED_LIBS = {"Resistor_": "R", "Capacitor_": "C", "Inductor_": "L", "Diode_": "D", "LED_": "D", "Fuse": "F",
              "Crystal": "Y", "Oscillator": "Y", "Connector": "J", "Button_Switch": "SW", "Relay": "K",
              "Buzzer_Beeper": "BZ", "Transformer": "T", "Varistor": "RV", "Potentiometer": "RV"}
# Reference prefix -> the kinds it may be (KiCad and common habits).
REF_KINDS = {"R": {"R"}, "RN": {"R"}, "C": {"C"}, "L": {"L"}, "FB": {"L", "R"}, "FL": {"L", "C"},
             "D": {"D"}, "LED": {"D"}, "TVS": {"D"}, "F": {"F", "R"}, "PTC": {"F", "R"}, "Y": {"Y"}, "X": {"Y"},
             "J": {"J"}, "P": {"J"}, "CN": {"J"}, "CON": {"J"}, "SW": {"SW"}, "S": {"SW"}, "BOOT": {"SW"},
             "RESET": {"SW"}, "BTN": {"SW"}, "K": {"K"}, "BZ": {"BZ"}, "LS": {"BZ"}, "T": {"T", "L"},
             "RV": {"RV", "R"}, "VR": {"RV", "R"}}
MIN_SIMILARITY = 90   # below this the "match" is only a vague likeness (an 0201 for an 0402) and confuses more than it helps


def _kind_ok(eid, ref):
    """May library footprint `eid` be shown as what part `ref` is?"""
    import re as _re  # noqa: PLC0415
    prefix = _re.match(r"[A-Za-z]+", ref or "")
    kinds = REF_KINDS.get(prefix.group(0).upper()) if prefix else None
    lib = eid.split(":", 1)[0]
    lib_kind = next((k for name, k in TYPED_LIBS.items() if lib.startswith(name)), None)
    return kinds is None or lib_kind is None or lib_kind in kinds


def recognise(geo, top=3, ref=None):
    """Library footprints with the same geometry as `geo`, best first: [{id, status, max_offset, size_diff}].
    `ref` (e.g. "F1") leaves out libraries for other kinds of parts."""
    entries = _state["entries"]
    if not entries or not geo or not geo.get("pads"):
        return []
    pads = [p for p in _numbered(geo["pads"]) if p.get("type") != "np_thru_hole"]
    sig = _sig(pads)
    if not sig:
        return []
    n, s0, s1, area = sig
    cands = [e for e in entries if e["sig"][0] == n and abs(e["sig"][1] - s0) <= 0.2 and abs(e["sig"][2] - s1) <= 0.2
             and abs(e["sig"][3] - area) <= max(0.3, area * 0.35)]
    scored = []
    cands = [e for e in cands if _kind_ok(e["id"], ref)]
    for e in cands[:400]:
        r = compare_geometry({"pads": pads, "bottom": geo.get("bottom")}, _geo(e))
        if r.get("status") in ("ok", "warn") and r.get("max_offset", 9) <= 0.2:
            scored.append((r["max_offset"] + r["size_diff"] * 0.5, e["id"], r))
    scored.sort(key=lambda t: (t[0], len(t[1])))
    out = []
    for score, eid, r in scored[:top]:
        if round(100 - score * 200) < MIN_SIMILARITY:
            continue
        out.append({"id": eid, "status": r["status"], "max_offset": r["max_offset"], "size_diff": r["size_diff"],
                    "similarity": max(0, round(100 - score * 200)), "package": _describe(eid)})
    return out


def _describe(eid):
    pkg = P.parse_package(eid.split(":", 1)[1])
    return P.describe(pkg) if pkg else ""


_parsed = []
_tokens = {}


def by_mpn(mpn):
    """Library footprints named after this part number: KiCad has SW_SPST_TL3315NF, SW_SPST_PTS810 ...
    A name token of 5+ characters that the MPN starts with counts."""
    entries = _state["entries"]
    if not entries or not mpn:
        return []
    if not _tokens:
        import re  # noqa: PLC0415
        for e in entries:
            for tok in re.split(r"[_\-.]", e["id"].split(":", 1)[1]):
                tok = re.sub(r"[^A-Za-z0-9]", "", tok).upper()
                if len(tok) >= 5 and any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
                    _tokens.setdefault(tok, []).append(e)
    key = "".join(c for c in mpn.upper() if c.isalnum())
    # Longest shared start: TL3315NF250Q finds SW_SPST_TL3315NF160Q (same body, other actuator force).
    for n in range(len(key), 4, -1):
        hits = [e for tok, es in _tokens.items() if tok.startswith(key[:n]) for e in es]
        if hits:
            return hits
    return []


def for_package(text, kind=None):
    """A library footprint for a package description ('1206 (3216 Metric)', '8-SOIC', 'SOT-23-5') - for drawing."""
    entries = _state["entries"]
    pkg = P.parse_package(text or "")
    if not entries or not pkg:
        return None
    key = (P.describe(pkg), kind)
    if key in _pkg_cache:
        return _pkg_cache[key]
    if not _parsed:
        for e in entries:
            name = e["id"].split(":", 1)[1]
            if "handsolder" in name.lower() or "_pad" in name.lower():
                continue
            cand = P.parse_package(name)
            if cand:
                _parsed.append((e, cand))
    prefer = {"R": "Resistor_SMD:R_", "C": "Capacitor_SMD:C_", "L": "Inductor_SMD:L_"}.get(kind, "")
    best = None
    for e, cand in _parsed:
        if pkg.get("chip") and prefer and not e["id"].startswith(prefer):
            continue
        if P.compare(cand, pkg)[0] != "ok":
            continue
        name = e["id"].split(":", 1)[1]
        penalty = (0 if e["id"].startswith(("Package_", "Resistor_SMD", "Capacitor_SMD", "Inductor_SMD")) else 50)             + (0 if bool(cand.get("ep")) == bool(pkg.get("ep")) else 100)             + (0 if cand.get("family") == pkg.get("family") else 30)             + (0 if name.upper().startswith((pkg.get("family") or "").upper()) else 20)             + (60 if e["id"].startswith(("Connector", "Button", "RF_", "Module")) else 0)
        rank = (penalty, len(name), name)
        if best is None or rank < best[0]:
            best = (rank, e)
    result = {"id": best[1]["id"], "geometry": geometry(best[1])} if best else None
    _pkg_cache[key] = result
    return result


__all__ = ["ensure", "status", "recognise", "for_package", "geometry"]

