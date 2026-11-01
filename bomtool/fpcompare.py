"""The compare window: the footprint's real measures next to the datasheet's
package dimensions, recommended land pattern and pin table. Built on demand
when the user opens it - it reads the datasheet, which takes a moment.
"""
import statistics

from . import datasheet, dsdata
from . import packages as P
from .footprint import _extent, _numbered

NO_LEAD = {"QFN", "DFN", "LGA", "BGA", "CHIP", "LFCSP", "WLCSP", "CSP"}


def _r(v):
    return round(v, 3) if v is not None else None


def features(geo):
    """Measures of a footprint in mm: pitch, pad size, row spans, exposed pad, body (Fab layer)."""
    pads = _numbered(geo.get("pads") or [])
    out = {"pads": len(pads), "pitch": None, "pad_w": None, "pad_l": None, "rows": {}, "ep": None, "body": None}
    if not pads:
        return out
    ext = [(_extent(p), p) for p in pads]
    areas = [e[0] * e[1] * 4 for e, _ in ext]
    med = statistics.median(areas)
    reg = [(e, p) for (e, p), a in zip(ext, areas) if a <= 3 * med]
    big = [(e, p) for (e, p), a in zip(ext, areas) if a > 3 * med]
    if len(big) == 1 and len(reg) >= 2:
        (ex, ey), _ = big[0]
        out["ep"] = (_r(ex * 2), _r(ey * 2))
    # Pads stretched along x sit in left/right rows (they point at the body), along y in top/bottom rows.
    groups = {"x": [], "y": []}
    for (ex, ey), p in reg:
        if ex > ey * 1.1:
            groups["x"].append(((ex, ey), p))
        elif ey > ex * 1.1:
            groups["y"].append(((ex, ey), p))
        else:
            groups["x" if abs(p["x"]) >= abs(p["y"]) else "y"].append(((ex, ey), p))
    widths, lengths, pitches = [], [], []
    for axis, items in groups.items():
        if len(items) < 2:
            continue
        a, b = ("x", "y") if axis == "x" else ("y", "x")
        ia, ib = (0, 1) if axis == "x" else (1, 0)
        neg = [(e, p) for e, p in items if p[a] < -0.01]
        pos = [(e, p) for e, p in items if p[a] > 0.01]
        row = {"count": len(items)}
        outer = max(p[a] + e[ia] for e, p in items) - min(p[a] - e[ia] for e, p in items)
        row["outer"] = _r(outer)
        if neg and pos:
            row["inner"] = _r(min(p[a] - e[ia] for e, p in pos) - max(p[a] + e[ia] for e, p in neg))
            row["centers"] = _r(statistics.median([p[a] for _, p in pos]) - statistics.median([p[a] for _, p in neg]))
        out["rows"][axis] = row
        widths += [e[ib] * 2 for e, _ in items]
        lengths += [e[ia] * 2 for e, _ in items]
        # pitch: nearest neighbour along the row
        for e, p in items:
            same = [q for _, q in items if q is not p and abs(q[a] - p[a]) < 0.05]
            if same:
                pitches.append(round(min(abs(q[b] - p[b]) for q in same), 3))
    if widths:
        out["pad_w"] = _r(statistics.median(widths))
        out["pad_l"] = _r(statistics.median(lengths))
    if pitches:
        out["pitch"] = statistics.mode(pitches)
    xs, ys = [], []
    for g in geo.get("graphics") or []:
        if g.get("l") != "fab":
            continue
        if g["k"] == "poly":
            xs += [x for x, _ in g["pts"]]
            ys += [y for _, y in g["pts"]]
        elif g["k"] in ("line", "rect"):
            xs += [g["x1"], g["x2"]]
            ys += [g["y1"], g["y2"]]
    if xs and ys:
        out["body"] = (_r(max(xs) - min(xs)), _r(max(ys) - min(ys)))
    return out


def _v(d, *keys):
    for k in keys:
        if k in d:
            return d[k]
    return None


def _fmt(d):
    if d is None:
        return "–"
    if d["min"] is not None and d["max"] is not None:
        return f"{d['min']:g}–{d['max']:g}" + (f" (typ {d['nom']:g})" if d["nom"] is not None else "")
    return f"{d['nom']:g}" if d["nom"] is not None else f"{(d['min'] or d['max']):g}"


def _lo(d):
    return d["min"] if d["min"] is not None else d["nom"] if d["nom"] is not None else d["max"]


def _hi(d):
    return d["max"] if d["max"] is not None else d["nom"] if d["nom"] is not None else d["min"]


def _nom(d):
    if d["nom"] is not None:
        return d["nom"]
    if d["min"] is not None and d["max"] is not None:
        return (d["min"] + d["max"]) / 2
    return d["min"] if d["min"] is not None else d["max"]


def compare_dims(feat, dims, family):
    """Rows {what, ds, fp, status, note} comparing the footprint with the package table."""
    rows = []
    no_lead = P.family_group(family) in NO_LEAD or (family or "").upper() in NO_LEAD or "SON" in (family or "").upper()

    def add(what, ds, fp, status, note):
        rows.append({"what": what, "ds": ds, "fp": fp, "status": status, "note": note})

    e = _v(dims, "e")
    if e and feat["pitch"]:
        diff = abs(_nom(e) - feat["pitch"])
        add("Pitch (e)", _fmt(e), f"{feat['pitch']:g}", "ok" if diff <= 0.03 else "mismatch",
            "Samme pitch." if diff <= 0.03 else "Pitch passer ikke – benene rammer ikke padsene.")
    b = _v(dims, "b")
    if b and feat["pad_w"]:
        w = feat["pad_w"]
        if w >= _hi(b):
            st, note = "ok", "Padden er mindst lige så bred som benet."
        elif w >= _nom(b) - 0.01:
            st, note = "warn", "Padden er smallere end benets max-bredde."
        else:
            st, note = "mismatch", "Padden er smallere end benet."
        if feat["pitch"] and w > feat["pitch"] - 0.1:
            st, note = "warn", "Padsene er så brede at der næsten ikke er luft imellem (risiko for kortslutning)."
        add("Benbredde (b) ↔ padbredde", _fmt(b), f"{w:g}", st, note)

    # Row span: the axis with the most pads in two opposite rows.
    rows_fp = feat["rows"]
    axis = max(rows_fp, key=lambda k: (("inner" in rows_fp[k]), rows_fp[k]["count"])) if rows_fp else None
    span = _v(dims, "E", "HE", "H") if not no_lead else _v(dims, "E", "D")
    L = _v(dims, "L")
    if axis and span and "inner" in rows_fp[axis]:
        r = rows_fp[axis]
        if no_lead:
            ok_out = r["outer"] >= _lo(span) - 0.05
            add("Kropsbredde ↔ padsenes yderkant", _fmt(span), f"{r['outer']:g}", "ok" if ok_out else "warn",
                "Padsene går ud til kroppens kant." if ok_out else "Padsene stopper inden kroppens kant.")
            if L:
                need = _hi(span) - 2 * _hi(L)
                st = "ok" if r["inner"] <= need + 0.05 else "warn"
                add("Terminal (L) ↔ padsenes inderkant", f"{_fmt(L)} → ≤ {need:.2f}", f"{r['inner']:g}", st,
                    "Padsene dækker terminalerne." if st == "ok" else "Padsene dækker ikke hele terminalens længde.")
        else:
            st = "ok" if r["outer"] >= _hi(span) else "warn" if r["outer"] >= _nom(span) else "mismatch"
            add("Benspænd (E) ↔ padsenes yderkant", _fmt(span), f"{r['outer']:g}", st,
                {"ok": "Benenes spidser ligger inden for padsene.",
                 "warn": "Benenes spidser kan nå ud over padsene ved max-mål.",
                 "mismatch": "Benene stikker ud over padsene."}[st])
            if L:
                heel = _lo(span) - 2 * _hi(L)
                st = "ok" if r["inner"] <= heel + 0.05 else "warn" if r["inner"] <= _nom(span) - 2 * _nom(L) else "mismatch"
                add("Benets fod (L) ↔ padsenes inderkant", f"{_fmt(L)} → ≤ {heel:.2f}", f"{r['inner']:g}", st,
                    {"ok": "Hele foden ligger på padden.", "warn": "Hælen ligger tæt på padsenes inderkant.",
                     "mismatch": "Benets fod rammer kun delvist padden."}[st])
    d2, e2 = _v(dims, "D2"), _v(dims, "E2")
    if (d2 or e2) and feat["ep"]:
        want = sorted(x for x in (_nom(d2) if d2 else None, _nom(e2) if e2 else None) if x)
        have = sorted(feat["ep"])
        ok = all(have[-1 - i] <= want[-1 - i] + 0.15 and have[-1 - i] >= want[-1 - i] - 0.6 for i in range(len(want)))
        add("Eksponeret pad (D2×E2)", " × ".join(_fmt(x) for x in (d2, e2) if x), f"{have[1]:g} × {have[0]:g}",
            "ok" if ok else "warn", "Termisk pad passer." if ok else "Termisk pad afviger fra pakkens.")
    elif (d2 or e2) and not feat["ep"]:
        add("Eksponeret pad (D2×E2)", " × ".join(_fmt(x) for x in (d2, e2) if x), "ingen", "mismatch",
            "Pakken har en termisk pad, footprintet har ikke.")
    D = _v(dims, "D", "D1")
    W = _v(dims, "E1") if not no_lead else _v(dims, "E")
    if D and W and feat["body"]:
        want = sorted((_nom(D), _nom(W)))
        have = sorted(feat["body"])
        ok = all(abs(x - y) <= 0.3 for x, y in zip(want, have))
        add("Krop (D × E1)", f"{_fmt(D)} × {_fmt(W)}", f"{feat['body'][0]:g} × {feat['body'][1]:g} (Fab-lag)",
            "ok" if ok else "warn", "Kroppens omrids på Fab-laget passer." if ok else "Fab-lagets omrids afviger.")
    return rows


def land_rows(feat, values):
    """Match each recommended land-pattern value with the footprint measure it equals (if any)."""
    names = {"pitch": "pitch", "pad_w": "padbredde", "pad_l": "padlængde"}
    cands = [(names[k], feat[k]) for k in names if feat.get(k)]
    for axis, r in feat["rows"].items():
        cands += [("yderkant", r.get("outer")), ("inderkant (gap)", r.get("inner")), ("centerafstand", r.get("centers"))]
    if feat["ep"]:
        cands += [("termisk pad", feat["ep"][0]), ("termisk pad", feat["ep"][1])]
    rows = []
    for k, v in values.items():
        close = [(abs(v - fv), name, fv) for name, fv in cands if fv and abs(v - fv) <= 0.03]
        if close:
            fv = min(close)[2]
            names = " / ".join(dict.fromkeys(n for d, n, x in close if abs(x - fv) < 1e-6))
            rows.append({"what": k, "ds": f"{v:g}", "fp": f"{fv:g} ({names})", "status": "ok", "note": ""})
        else:
            rows.append({"what": k, "ds": f"{v:g}", "fp": "–", "status": "unknown",
                         "note": "Intet mål i footprintet svarer til denne værdi – se tegningen."})
    return rows


def build(line):
    """Everything the compare window shows for one BOM line."""
    fp = line.get("fp") or {}
    geo = fp.get("geometry") or {}
    feat = features(geo)
    fp_name = line["footprint"].split(":")[-1]
    fp_pkg = P.parse_package(fp_name)
    out = {"footprint": line["footprint"], "features": feat, "fp_pkg": P.describe(fp_pkg) if fp_pkg else "",
           "datasheet": line.get("datasheet") or "", "pages": [], "dims": None, "land": None, "pins": None,
           "notes": []}
    url = out["datasheet"]
    if not url.startswith("http"):
        out["notes"].append("Ingen datablad-link på komponenten – kun footprintets egne mål kan vises.")
        return out
    try:
        text = datasheet.text_for(url)
    except ValueError as e:
        out["notes"].append(str(e))
        return out
    if len(text.strip()) < 200:
        out["notes"].append("Databladets tekst kunne ikke læses (scannet eller specielle skrifttyper) – se tegningen selv.")
    out["pages"] = dsdata.drawing_pages(text, fp_pkg)

    tables = dsdata.dim_tables(text)
    if tables:
        fits = [t for t in tables if t["pkg"] and fp_pkg and P.compare(fp_pkg, t["pkg"])[0] in ("ok", "partial")]
        table = fits[0] if fits else (tables[0] if len(tables) == 1 else None)
        if table:
            fam = (table["pkg"] or fp_pkg or {}).get("family") if (table["pkg"] or fp_pkg) else None
            out["dims"] = {"name": table["name"], "page": table["page"], "sure": bool(fits),
                           "table": {k: _fmt(v) for k, v in table["dims"].items()},
                           "rows": compare_dims(feat, table["dims"], fam)}
            if table["page"] not in out["pages"]:
                out["pages"].insert(0, table["page"])
        else:
            out["notes"].append("Databladet har mål-tabeller for " + ", ".join(t["name"] for t in tables) +
                                f", men ingen for {out['fp_pkg'] or fp_name}.")
    else:
        out["notes"].append("Ingen mål-tabel fundet som tekst – målene står kun på tegningen (se siden herunder).")

    lands = dsdata.pad_layouts(text)
    if lands:
        fits = [t for t in lands if t["pkg"] and fp_pkg and P.compare(fp_pkg, t["pkg"])[0] in ("ok", "partial")]
        land = fits[0] if fits else (lands[0] if len(lands) == 1 else None)
        if land:
            out["land"] = {"label": land["label"], "page": land["page"], "rows": land_rows(feat, land["values"])}

    want = line.get("pin_names") or {}
    tables = dsdata.pin_tables(text)
    if want and tables:
        best = dsdata.best_pin_map(want, tables)
        m, s, diff, miss = dsdata.compare_pins(want, best["pins"])
        rows = []
        for num in sorted(set(want) | set(best["pins"]), key=_natkey):
            a, b = want.get(num), best["pins"].get(num)
            st = "ok"
            if a and b:
                if any(d[0] == num for d in diff):
                    st = "mismatch"
                elif dsdata.norm_pin(a) != dsdata.norm_pin(b) and not (dsdata.norm_pin(a) in dsdata.norm_pin(b) or
                                                                       dsdata.norm_pin(b) in dsdata.norm_pin(a)):
                    st = "warn"
            else:
                st = "unknown"
            rows.append({"num": num, "symbol": a or "–", "datasheet": b or "–", "status": st})
        status = "mismatch" if diff else "ok" if m + s >= len(want) * 0.8 else "warn"
        out["pins"] = {"page": best["page"], "rows": rows, "status": status,
                       "summary": f"{m} ens, {s} samme type, {len(diff)} forskellige, {len(miss)} ikke i tabellen."}
    elif want:
        out["notes"].append("Ingen pin-tabel fundet i databladet.")
    return out


def _natkey(s):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
