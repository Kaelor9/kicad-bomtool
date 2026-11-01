"""Find alternative parts.

Passives (R/C/L): parametric search on value + package (+ voltage, tolerance,
dielectric) - candidates must meet or beat every known spec.
Everything else: the distributors' own substitute / similar-part data. These
are suggestions; pinout and behaviour must be checked by a human.
"""
from concurrent.futures import ThreadPoolExecutor

from . import datasheet, dsdata
from . import fields as F
from . import packages as P
from .pricing import plan_line
from .providers import ProviderError

DIELECTRIC_RANK = {"C0G": 4, "X8R": 3, "X7R": 3, "X7S": 3, "X6S": 2, "X5R": 2, "Y5V": 0, "Z5U": 0}
VALUE_PARAMS = {"R": ("Resistance",), "C": ("Capacitance",), "L": ("Inductance",)}


def _keywords(line, chip):
    p = line["parsed"]
    val = F.format_value(p["value"], line["kind"]).replace("µ", "u").replace("Ω", "")
    if line["kind"] == "R":
        return f"resistor {val} {chip}"
    if line["kind"] == "C":
        extra = " ".join(x for x in (p.get("dielectric", ""), f"{p['voltage']:g}V" if p.get("voltage") else "") if x)
        return f"capacitor {val} {extra} {chip}".replace("  ", " ")
    return f"inductor {val} {chip}"


def candidate_specs(part, kind):
    params = part.get("params") or {}
    text = " ".join([part.get("desc", "")] + [f"{v}" for k, v in params.items()
                                              if k in VALUE_PARAMS[kind]])
    val = None
    for name in VALUE_PARAMS[kind]:
        if params.get(name):
            got = F.parse_value(params[name], kind)
            if got:
                val = got["value"]
    got = F.parse_value(text, kind) or {}
    if val is None:
        val = got.get("value")
    specs = {"value": val}
    for k in ("voltage", "tolerance", "dielectric", "power", "current"):
        if k in got:
            specs[k] = got[k]
    for k, v in params.items():
        kl = k.lower()
        if kl.startswith("voltage") and "voltage" not in specs:
            g = F.parse_value("1 " + v, "C") or {}
            if "voltage" in g:
                specs["voltage"] = g["voltage"]
        if kl == "tolerance":
            g = F.parse_value("1 " + v, kind) or {}
            if "tolerance" in g:
                specs["tolerance"] = g["tolerance"]
        if kl.startswith("temperature coefficient") and kind == "C":
            g = F.parse_value("1 " + v, "C") or {}
            if "dielectric" in g:
                specs["dielectric"] = g["dielectric"]
    pkg = P.parse_package(part.get("package") or "") or P.parse_package(part.get("desc") or "")
    specs["chip"] = pkg["chip"] if pkg else None
    return specs


def meets(want, have, chip):
    """Return (ok, unverified): value and package must match; any other spec the
    candidate states must be at least as good. Specs it doesn't state are listed
    as unverified rather than rejected (distributor data is often incomplete)."""
    if have.get("value") is None or abs(have["value"] - want["value"]) > abs(want["value"]) * 0.001 + 1e-15:
        return False, []
    if chip and have.get("chip") != chip:
        return False, []
    unverified = []
    checks = (("voltage", "spænding", lambda w, h: h >= w), ("tolerance", "tolerance", lambda w, h: h <= w),
              ("power", "effekt", lambda w, h: h >= w), ("current", "strøm", lambda w, h: h >= w))
    for key, label, good in checks:
        if want.get(key):
            if have.get(key) is None:
                unverified.append(label)
            elif not good(want[key], have[key]):
                return False, []
    if want.get("dielectric"):
        if have.get("dielectric") is None:
            unverified.append("dielektrikum")
        elif DIELECTRIC_RANK.get(have["dielectric"], -1) < DIELECTRIC_RANK.get(want["dielectric"], 0):
            return False, []
    return True, unverified


def find(line, providers, need, settings, preferred=None, limit=4):
    """Return dict(kind, items, note). items carry price at `need`."""
    if line.get("kind") and line.get("parsed"):
        chip = None
        for src in (line.get("api_package"), line["footprint"], line.get("package_field")):
            pkg = P.parse_package(src or "")
            if pkg and pkg.get("chip"):
                chip = pkg["chip"]
                break
        if not chip:
            return {"kind": "passive", "items": [], "note": "Kunne ikke bestemme chip-størrelsen ud fra footprintet."}
        kw = _keywords(line, chip)
        items, errors = [], []
        for prov in providers:
            try:
                parts = prov.search(kw, limit=25)
            except ProviderError as e:
                errors.append(f"{prov.name}: {e}")
                continue
            for part in parts:
                specs = candidate_specs(part, line["kind"])
                ok, unverified = meets(line["parsed"], specs, chip)
                if not ok or not part.get("offers"):
                    continue
                plan = plan_line(part["offers"], need, settings)
                if not plan:
                    continue
                item = _item(part, plan, specs)
                if unverified:
                    item["check"] = "Ikke verificeret ud fra grosistens data: " + ", ".join(unverified) + "."
                items.append(item)
        # Fully verified candidates first, then by price.
        items = _rank(items, preferred, line)
        items.sort(key=lambda it: bool(it.get("check")))
        note = f"Søgt efter: {kw}" + (f" · Fejl: {'; '.join(errors)}" if errors else "")
        return {"kind": "passive", "items": items[:limit * 3], "note": note}

    # Active / other parts
    mpn = line.get("mpn") or line.get("mpn_guess")
    if not mpn:
        return {"kind": "other", "items": [], "note": "Intet MPN at søge alternativer ud fra."}
    own_pkg = P.parse_package(line.get("api_package") or "") or P.parse_package(line["footprint"].split(":")[-1])
    subs, errors = [], []
    for prov in providers:
        try:
            subs.extend(prov.substitutes(mpn))
        except ProviderError as e:
            errors.append(f"{prov.name}: {e}")
    items, seen = [], {F.key(mpn)}
    for s in subs:
        if not s.get("mpn") or F.key(s["mpn"]) in seen:
            continue
        seen.add(F.key(s["mpn"]))
        priced = None
        for prov in providers:
            try:
                parts = prov.lookup(s["mpn"])
            except ProviderError:
                continue
            part = next((p for p in parts if F.key(p["mpn"]) == F.key(s["mpn"])), None)
            if part and part.get("offers"):
                plan = plan_line(part["offers"], need, settings)
                if plan:
                    priced = _item(part, plan, {})
                    priced["pkg_text"] = part.get("package") or part.get("desc") or ""
                    break
        if priced is None:
            priced = {"mpn": s["mpn"], "mfr": s.get("mfr", ""), "desc": s.get("desc", ""), "url": s.get("url", ""),
                      "source": s.get("source", ""), "price": None}
        priced["relation"] = s.get("type", "")
        _fit(priced, own_pkg)
        items.append(priced)
        if len(items) >= 8:
            break
    _pinouts(items, line.get("pin_names") or {})
    items = _rank(items, preferred, line)
    # Drop-ins first: same package, then same pinout.
    order = {"ok": 0, "partial": 1, "unknown": 2, "warn": 2, "mismatch": 3}
    items.sort(key=lambda it: (order[it["fit"]], order[(it.get("pinout") or {}).get("status", "unknown")]))
    note = "Erstatninger fra grosisternes egne data." + (f" Fejl: {'; '.join(errors)}" if errors else "")
    if not items:
        note = "Ingen erstatninger fundet hos de tilsluttede grosister." + (f" {'; '.join(errors)}" if errors else "")
    return {"kind": "other", "items": items, "note": note}


def _pinouts(items, want):
    """Read each candidate's datasheet pin table and compare it with the symbol's pins."""
    if not want:
        return

    def one(it):
        url = it.get("datasheet") or ""
        if url.startswith("//"):
            url = "https:" + url
        if not url.startswith("http"):
            return
        try:
            tables = dsdata.pin_tables(datasheet.text_for(url))
        except Exception:  # noqa: BLE001 - an unreadable datasheet just means "unknown"
            return
        if not tables:
            return
        best = dsdata.best_pin_map(want, tables)
        m, s, diff, miss = dsdata.compare_pins(want, best["pins"])
        if diff:
            status = "mismatch"
            msg = "Anden pinout: " + ", ".join(f"ben {n} er {b} (din: {a})" for n, a, b in diff[:4])
        elif m + s >= len(want) * 0.8:
            status, msg = "ok", f"Samme pinout ifølge databladet ({m + s} af {len(want)} ben)."
        else:
            status, msg = "warn", f"Pinout kun delvist bekræftet ({m + s} af {len(want)} ben fundet i databladet)."
        it["pinout"] = {"status": status, "msg": msg}

    with ThreadPoolExecutor(max_workers=4) as ex:
        list(ex.map(one, items))


def _fit(item, own_pkg):
    """Does the candidate fit the existing footprint? Judged from package name and pin count."""
    text = item.pop("pkg_text", "") or item.get("package") or item.get("desc") or ""
    cand = P.parse_package(text)
    if not own_pkg or not cand:
        item["fit"] = "unknown"
        item["check"] = "Pakken kunne ikke sammenlignes – kontrollér footprint, pinout og elektriske data."
        return
    status, msg = P.compare(own_pkg, cand)
    item["fit"] = status
    if status == "ok":
        item["check"] = f"Passer på dit footprint ({P.describe(cand)}). Kontrollér stadig pinout og elektriske data."
    elif status == "partial":
        item["check"] = f"Samme pakketype ({P.describe(cand)}), men antal ben kunne ikke bekræftes. Kontrollér pinout."
    else:
        item["check"] = f"Passer IKKE på dit footprint: {msg}"


def _item(part, plan, specs):
    best = plan["best"]
    pkg = P.parse_package(part.get("package") or part.get("desc") or "")
    return {"mpn": part["mpn"], "mfr": part["mfr"], "desc": part.get("desc", ""), "url": best.get("url") or part.get("url"),
            "datasheet": part.get("datasheet", ""), "source": part["source"], "seller": best["seller"],
            "sku": best.get("sku", ""), "price": best["total"], "unit": best["unit"], "qty": best["qty"],
            "currency": best.get("currency", ""), "stock": best.get("stock"),
            "package": P.describe(pkg) if pkg else (part.get("package") or ""),
            "specs": {k: v for k, v in specs.items() if v is not None},
            "lifecycle": part.get("lifecycle", ""), "per_seller": {s: b["total"] for s, b in plan["per_seller"].items()}}


def _rank(items, preferred, line):
    current = F.key(line.get("mpn") or "")
    dedup = {}
    for it in items:
        k = F.key(it["mpn"])
        if k == current:
            continue
        if k not in dedup or (it["price"] or 9e9) < (dedup[k]["price"] or 9e9):
            dedup[k] = it
    items = list(dedup.values())

    def score(it):
        same = 0 if preferred and it.get("seller") == preferred else 1
        return (it["price"] is None, same if preferred else 0, it["price"] or 9e9)
    items.sort(key=score)
    for it in items:
        it["same_seller"] = bool(preferred and it.get("seller") == preferred)
    return items
