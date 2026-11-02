"""Find alternative parts.

Passives (R/C/L): parametric search on value + package (+ voltage, tolerance,
dielectric) - candidates must meet or beat every known spec.
Everything else: the distributors' own substitute / similar-part data. These
are suggestions; pinout and behaviour must be checked by a human.
"""
import re
from concurrent.futures import ThreadPoolExecutor

from . import datasheet, dsdata
from . import fields as F
from . import packages as P
from .pricing import plan_line
from .providers import ProviderError

DIELECTRIC_RANK = {"C0G": 4, "X8R": 3, "X7R": 3, "X7S": 3, "X6S": 2, "X5R": 2, "Y5V": 0, "Z5U": 0}
VALUE_PARAMS = {"R": ("Resistance",), "C": ("Capacitance",), "L": ("Inductance",)}


def _keywords(kind, want, chip, short=False):
    val = F.format_value(want["value"], kind).replace("µ", "u").replace("Ω", "")
    if kind == "R":
        return f"resistor {val} {chip}"
    if kind == "C":
        extra = "" if short else " ".join(x for x in (want.get("dielectric", ""),
                                                      f"{want['voltage']:g}V" if want.get("voltage") else "") if x)
        return f"capacitor {val} {extra} {chip}".replace("  ", " ")
    return f"inductor {val} {chip}"


_UNIT = {"R": "1R", "C": "1uF", "L": "1uH"}
_SPEC_TOKENS = re.compile(r"\d+(?:[.,]\d+)?\s*k?V(?:DC|dc)?\b|±\s*\d+(?:[.,]\d+)?\s*%|\b(?:C0G|NP0|X[5-8][RSTP]|Y5V|Z5U)\b|"
                          r"\d+(?:[.,]\d+)?\s*m?W\b|\d+(?:[.,]\d+)?\s*m?A\b|\d+/\d+\s*W\b")


def _specs_from(text, kind):
    """Ratings in a free text ("4.7 µF ±20% 50V Ceramic Capacitor X7R 1210") - parsed behind a dummy value,
    so words like 'Ceramic' don't stop the parser."""
    toks = _SPEC_TOKENS.findall(text or "")
    if not toks:
        return {}
    got = F.parse_value(_UNIT[kind] + " " + " ".join(toks), kind) or {}
    got.pop("value", None)
    return got


def candidate_specs(part, kind):
    params = part.get("params") or {}
    val = None
    for name in VALUE_PARAMS[kind]:
        if params.get(name):
            got = F.parse_value(params[name], kind)
            if got:
                val = got["value"]
    if val is None:
        got = F.parse_value(part.get("desc", ""), kind) or {}
        val = got.get("value")
        if val is None:
            m = re.search(r"\d+(?:[.,]\d+)?\s*(?:[pnuµmkKM]?\s*(?:F|H|Ω|Ohm|ohm)s?)\b", part.get("desc") or "")
            got = F.parse_value(m.group(0), kind) if m else {}
            val = (got or {}).get("value")
    specs = {"value": val}
    specs.update(_specs_from(part.get("desc", ""), kind))
    for k, v in params.items():
        kl = k.lower()
        if kl.startswith("voltage") or kl == "tolerance" or kl.startswith("temperature coefficient")                 or kl.startswith("power") or kl.startswith("current"):
            specs.update(_specs_from(v, kind))      # the parameter table beats the description
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


def _search(providers, query, limit, errors):
    out = []
    for prov in providers:
        try:
            out.extend(prov.search(query, limit=limit))
        except ProviderError as e:
            errors.append(f"{prov.name}: {e}")
    return out


def find(line, providers, need, settings, preferred=None, limit=4):
    """Return dict(kind, items, note). items carry price at `need`.

    The footprint is what the board was made with, so it decides the package; the part that was
    chosen (even when it doesn't fit) tells which ratings to keep."""
    if line.get("kind") and line.get("parsed"):
        return _passives(line, providers, need, settings, preferred)
    return _actives(line, providers, need, settings, preferred)


def _passives(line, providers, need, settings, preferred):
    kind = line["kind"]
    fp_pkg = P.parse_package(line["footprint"].split(":")[-1]) or P.parse_package(line.get("package_field") or "")
    part_pkg = P.parse_package(line.get("api_package") or "")
    chip = (fp_pkg or {}).get("chip") or (part_pkg or {}).get("chip")
    if not chip:
        return {"kind": "passive", "items": [], "note": "Kunne ikke bestemme chip-størrelsen ud fra footprintet."}
    want = dict(line["parsed"])
    for k, v in (line.get("api_specs") or {}).items():
        want.setdefault(k, v)
    notes = []
    if part_pkg and part_pkg.get("chip") and part_pkg["chip"] != chip:
        notes.append(f"Den valgte komponent er {part_pkg['chip']}, men footprintet er {chip} – "
                     f"der søges {chip} med samme værdi og mindst lige gode specs.")
    errors, items, seen = [], [], set()
    queries = [_keywords(kind, want, chip), _keywords(kind, want, chip, short=True)]
    for q in dict.fromkeys(queries):
        for part in _search(providers, q, 50, errors):
            if F.key(part["mpn"]) in seen:
                continue
            seen.add(F.key(part["mpn"]))
            specs = candidate_specs(part, kind)
            ok, unverified = meets(want, specs, chip)
            if not ok or not part.get("offers"):
                continue
            plan = plan_line(part["offers"], need, settings)
            if not plan or plan["best"].get("impractical"):
                continue
            item = _item(part, plan, specs)
            item["fit"] = "ok"
            item["group"] = "drop-in"
            if unverified:
                item["check"] = "Ikke verificeret ud fra grosistens data: " + ", ".join(unverified) + "."
            items.append(item)
        if len(items) >= 15:
            break
    items = _rank(items, preferred, line)
    items.sort(key=lambda it: (bool(it.get("check")), -(it.get("stock") or 0)))
    spec = ", ".join(x for x in (F.format_value(want["value"], kind), chip,
                                f"≥{want['voltage']:g} V" if want.get("voltage") else "",
                                want.get("dielectric", ""),
                                f"≤{want['tolerance']:g} %" if want.get("tolerance") else "") if x)
    notes.append(f"Krav: {spec}." + (f" Fejl: {'; '.join(errors)}" if errors else ""))
    return {"kind": "passive", "items": items[:30], "note": " ".join(notes)}


_PKG_WORDS = (r"\b(\d+-?(SOIC|SOP|SSOP|TSSOP|MSOP|QFN|DFN|SON|WSON|VSON|LQFP|TQFP|BGA|SOT|SC70|SC-70|TO|DIP)[\w-]*"
              r"|SOT-?\d+[\w-]*|SC-?70[\w-]*|TO-\d+[\w-]*|\d+(SOIC|TSSOP|SSOP|QFN|DFN|SOT)\w*)")


def _similar_query(line):
    """Words that describe what the part does, without its package:
    "IC TRANSCEIVER FULL 1/1 16SOIC" -> "IC TRANSCEIVER FULL 1/1"."""
    desc = line.get("desc") or ""
    q = re.sub(_PKG_WORDS, " ", desc, flags=re.I)
    q = re.sub(r"\s+", " ", q).strip()
    if len(q) < 6:
        q = ((line.get("api_category") or "") + " " + q).strip()
    return q


def _price(part, need, settings):
    if not part.get("offers"):
        return None
    plan = plan_line(part["offers"], need, settings)
    if not plan:
        return None
    item = _item(part, plan, {})
    item["pkg_text"] = part.get("package") or part.get("desc") or ""
    return item


def _actives(line, providers, need, settings, preferred):
    mpn = line.get("mpn") or line.get("mpn_guess")
    if not mpn:
        return {"kind": "other", "items": [], "note": "Intet MPN at søge alternativer ud fra."}
    own_pkg = P.parse_package(line["footprint"].split(":")[-1]) or P.parse_package(line.get("api_package") or "")
    errors, items, seen = [], [], {F.key(mpn)}
    # 1. The distributors' own substitutes (same function, often drop-in)
    subs = []
    for prov in providers:
        try:
            subs.extend(prov.substitutes(mpn))
        except ProviderError as e:
            errors.append(f"{prov.name}: {e}")
    for s in subs[:12]:
        if not s.get("mpn") or F.key(s["mpn"]) in seen:
            continue
        seen.add(F.key(s["mpn"]))
        priced = None
        for prov in providers:
            try:
                part = next((p for p in prov.lookup(s["mpn"]) if F.key(p["mpn"]) == F.key(s["mpn"])), None)
            except ProviderError:
                continue
            if part:
                priced = _price(part, need, settings)
                if priced:
                    break
        if priced is None:
            priced = {"mpn": s["mpn"], "mfr": s.get("mfr", ""), "desc": s.get("desc", ""), "url": s.get("url", ""),
                      "source": s.get("source", ""), "price": None, "stock": s.get("stock")}
        priced["relation"] = f"Erstatning ifølge {s.get('source') or 'grosisten'}" + (f" ({s['type']})" if s.get("type") else "")
        items.append(priced)
    # 2. Parts that do the same job, found by searching the description (may need a new footprint/pinout)
    q = _similar_query(line)
    if q:
        for part in _search(providers, q, 40, errors):
            if F.key(part["mpn"]) in seen or not part.get("offers"):
                continue
            seen.add(F.key(part["mpn"]))
            priced = _price(part, need, settings)
            if priced:
                priced["relation"] = "Lignende funktion (søgning)"
                items.append(priced)
    for it in items:
        _fit(it, own_pkg)
    # Pinout only for those that fit the footprint, best stocked first (datasheets take time to read).
    order = {"ok": 0, "partial": 1, "unknown": 2, "warn": 2, "mismatch": 3}
    items.sort(key=lambda it: (order[it["fit"]], -(it.get("stock") or 0)))
    _pinouts([it for it in items if it["fit"] in ("ok", "partial")][:10], line.get("pin_names") or {})
    for it in items:
        pin = (it.get("pinout") or {}).get("status")
        if it["fit"] == "ok" and pin == "ok":
            it["group"] = "drop-in"
        elif it["fit"] in ("ok", "partial") and pin != "mismatch":
            it["group"] = "same-package"
        elif it["fit"] == "unknown" and pin != "mismatch":
            it["group"] = "check"
        else:
            it["group"] = "redesign"
    items = _rank(items, preferred, line)
    grp = {"drop-in": 0, "same-package": 1, "check": 2, "redesign": 3}
    items.sort(key=lambda it: (grp[it["group"]], it.get("price") is None, -(it.get("stock") or 0)))
    note = f"Erstatninger fra grosisterne og søgning på \"{q}\"." if q else "Erstatninger fra grosisterne."
    if errors:
        note += f" Fejl: {'; '.join(errors)}"
    if not items:
        note = "Ingen alternativer fundet hos de tilsluttede grosister." + (f" {'; '.join(errors)}" if errors else "")
    return {"kind": "other", "items": items[:40], "note": note}


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
