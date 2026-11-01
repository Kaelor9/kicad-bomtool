"""Group placed components into BOM lines."""
import re

from . import fields as F
from . import packages as P
from .kicad import natkey


def norm_mpn(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


GENERIC_MFR = {"generic", "any", "diverse", "various", "standard", "tbd", "-", "n/a"}


def build(components):
    lines = {}
    excluded = []
    for c in components:
        if c.get("virtual"):
            excluded.append({"ref": c["ref"], "value": c.get("value", ""), "why": "mekanisk/grafik (købes ikke)", "footprint": c["footprint"]})
            continue
        if not c["in_bom"]:
            excluded.append({"ref": c["ref"], "value": c.get("value", ""), "why": "'Exclude from BOM' er sat", "footprint": c["footprint"]})
            continue
        if c["dnp"] or c["value"].strip().lower() in F.DNP_VALUES:
            excluded.append({"ref": c["ref"], "value": c.get("value", ""), "why": "DNP (monteres ikke)", "footprint": c["footprint"]})
            continue
        generic = c["mfr"].strip().lower() in GENERIC_MFR
        mpn = c["mpn"] if not generic else ""
        fp_name = c["footprint"].split(":")[-1]
        if mpn:
            key = ("mpn", norm_mpn(mpn), fp_name)
        else:
            key = ("val", c["value"].strip().lower(), fp_name, c["lib_id"].split(":")[-1].lower())
        line = lines.get(key)
        if line is None:
            kind = F.passive_kind(c["ref"], c["lib_id"])
            line = lines[key] = {
                "refs": [], "qty": 0, "value": c["value"], "footprint": c["footprint"],
                "mpn": mpn, "mpn_field": c["mpn_field"] if mpn else "",
                "generic_spec": c["mpn"] if generic else "",
                "mfr": c["mfr"] if not generic else "", "datasheet": c["datasheet"],
                "dist": dict(c["dist"]), "kind": kind, "lib_id": c["lib_id"],
                "parsed": F.parse_value(c["value"] + " " + " ".join(
                    v for k, v in c["fields"].items() if F.key(k) in ("voltage", "tolerance", "dielectric",
                                                                       "power", "rating", "current")), kind)
                if kind else None,
                "package_field": c["package_field"], "warnings": [], "components": [],
            }
            if line["parsed"] is None and kind and c["mpn"] and generic:
                line["parsed"] = F.parse_value(c["mpn"], kind)
        line["refs"].append(c["ref"])
        line["qty"] += 1
        line["components"].append(c["ref"])
        for k in ("datasheet", "mfr"):
            if not line[k] and c[k]:
                line[k] = c[k]
        for k, v in c["dist"].items():
            line["dist"].setdefault(k, v)
    out = []
    for line in lines.values():
        line["refs"].sort(key=natkey)
        line["id"] = line["refs"][0]
        line["mpn_hint_pkg"] = P.mpn_chip_hint(line["mpn"]) if line["mpn"] else None
        if not line["mpn"] and not line["generic_spec"] and line["kind"] is None:
            if F.looks_like_mpn(line["value"]):
                line["mpn_guess"] = line["value"]
                line["warnings"].append(f"Ingen MPN-felt – prøver værdien '{line['value']}' som varenummer.")
        out.append(line)
    # Same MPN placed with different footprints is almost always a mistake.
    by_mpn = {}
    for line in out:
        if line["mpn"]:
            by_mpn.setdefault(norm_mpn(line["mpn"]), []).append(line)
    for group in by_mpn.values():
        if len(group) > 1:
            fps = ", ".join(sorted({g["footprint"] for g in group}))
            for g in group:
                g["warnings"].append(f"Samme MPN bruges med forskellige footprints: {fps}")
    out.sort(key=lambda l: natkey(l["id"]))
    return out, sorted(excluded, key=lambda e: natkey(e["ref"]))
