"""Import a distributor BOM / cart export without any template, and match it
against the project BOM.
"""
import re

from . import fields as F
from . import packages as P
from .bom import norm_mpn
from .tables import read_table

COLS = {
    "mpn": ["mfrpartnumber", "manufacturerpartnumber", "mfrpartno", "mfrno", "mfr#", "mpn",
            "manufacturerpn", "mfgpartnumber", "mfgpn", "manufacturerpart", "manufacturerproductnumber",
            "mfrproductnumber", "herstellerteilenummer", "herstellerartikelnummer", "producentvarenummer",
            "producentnr", "producentvarenr", "mfrpart", "manufacturerpartno", "mfgpart", "partnumber",
            "partno", "pn", "manufacturerreference", "mfrpartnumbers"],
    "dist_pn": ["mouserno", "mouser#", "mouserpartnumber", "mouserpartno", "digikeypartnumber", "digikeypart#",
                "digikeyproductnumber", "digikeypartno", "digikey#", "dkpartnumber", "lcscpart#",
                "lcscpartnumber", "lcscpart", "lcsc", "jlcpcbpart#", "ordercode", "farnellordercode",
                "newarkpartnumber", "tmesymbol", "symbol", "rsstockno", "rsstocknumber", "rspartnumber",
                "varenummer", "varenr", "bestellnummer", "artikelnummer", "distributorpartnumber",
                "supplierpartnumber", "sku", "catalognumber", "stockno", "itemnumber"],
    "qty": ["quantity", "qty", "orderqty", "quantityordered", "orderquantity", "antal", "menge", "anzahl",
            "bestiltantal", "qtyordered", "quantity1", "customerquantity", "buyqty", "orderedqty",
            "qtyorderd", "requestedquantity", "amount"],
    "unit_price": ["unitprice", "price", "pris", "stykpris", "enhedspris", "einzelpreis", "preis",
                   "unitpriceusd", "unitpricedkk", "unitpriceeur", "priceeach", "unitcost", "cost"],
    "ext_price": ["extendedprice", "extprice", "ext", "total", "totalprice", "linetotal", "samletpris",
                  "beløb", "belob", "subtotal", "gesamtpreis", "totalcost", "extendedcost"],
    "desc": ["description", "beskrivelse", "productdescription", "desc", "bezeichnung", "detaileddescription",
             "name", "title"],
    "mfr": ["manufacturer", "mfr", "producent", "hersteller", "manufacturername", "mfrname", "brand"],
    "refs": ["customerreference", "customerref", "referencedesignator", "referencedesignators", "designator",
             "designators", "refdes", "reference", "references", "kundereference", "customerpartnumber",
             "customerno", "yourreference", "comment", "notes", "note"],
    "package": ["package", "packagecase", "case", "footprint", "pakke", "gehäuse", "gehause",
                "supplierdevicepackage"],
}
DIST_NAMES = {"mouser": "Mouser", "digikey": "DigiKey", "digi-key": "DigiKey", "lcsc": "LCSC",
              "jlcpcb": "LCSC", "farnell": "Farnell", "element14": "Farnell", "newark": "Farnell",
              "tme": "TME", "rs": "RS", "arrow": "Arrow", "conrad": "Conrad", "reichelt": "Reichelt"}


def _k(s):
    return re.sub(r"[^a-z0-9#ø]", "", (s or "").lower())


def _col_class(cell):
    """Best (class, score) for a header cell."""
    k = _k(cell)
    if not k:
        return None, 0
    best = (None, 0)
    for cls, syns in COLS.items():
        for i, syn in enumerate(syns):
            if k == syn:
                score = 3 - i / 100
            elif len(syn) >= 4 and (k.startswith(syn) or (k.endswith(syn) and len(syn) >= 6)):
                score = 2 - i / 100
            elif len(syn) >= 6 and syn in k:
                score = 1 - i / 100
            else:
                continue
            # "partnumber" alone means MPN, but "digikeypartnumber" is a distributor number
            if cls == "mpn" and any(d in k for d in ("mouser", "digikey", "lcsc", "farnell", "tme", "rs",
                                                      "supplier", "distributor", "customer")):
                continue
            if cls == "qty" and any(x in k for x in ("available", "stock", "lager", "min", "backorder", "mult")):
                continue
            if cls == "unit_price" and any(x in k for x in ("ext", "total")):
                continue
            if score > best[1]:
                best = (cls, score)
    return best


def detect_columns(rows, max_scan=40):
    best = None
    for idx, row in enumerate(rows[:max_scan]):
        classes = [_col_class(c) for c in row]
        found = {}
        for col, (cls, score) in enumerate(classes):
            if cls and (cls not in found or score > found[cls][1]):
                found[cls] = (col, score)
        score = sum(s for _, s in found.values()) + (2 if "qty" in found else 0) + \
            (2 if "mpn" in found or "dist_pn" in found else 0)
        if len(found) >= 2 and (best is None or score > best[0]):
            best = (score, idx, {c: v[0] for c, v in found.items()})
    if best:
        return best[1], best[2]
    return None, {}


def _content_columns(rows, project_mpns):
    """No usable header: guess columns from the data itself."""
    width = max((len(r) for r in rows), default=0)
    cols = {}
    stats = []
    for c in range(width):
        vals = [r[c] for r in rows if c < len(r) and r[c]]
        if not vals:
            stats.append((0, 0, 0))
            continue
        ints = sum(1 for v in vals if re.fullmatch(r"\d{1,6}", v.replace(".", "").replace(",", ""))) / len(vals)
        hits = sum(1 for v in vals if norm_mpn(v) in project_mpns) / len(vals)
        mpnish = sum(1 for v in vals if F.looks_like_mpn(v)) / len(vals)
        stats.append((ints, hits, mpnish))
    if stats:
        mpn_col = max(range(width), key=lambda c: (stats[c][1], stats[c][2]))
        if stats[mpn_col][1] > 0 or stats[mpn_col][2] > 0.5:
            cols["mpn"] = mpn_col
        qty_cands = [c for c in range(width) if c != mpn_col and stats[c][0] > 0.8]
        if qty_cands:
            cols["qty"] = qty_cands[0]
    return cols


def parse_price(s):
    """'1,23 kr.' / 'DKK 0,512' / '$0.10' / '€1.234,56' -> (float, currency) or (None, None)."""
    if s is None:
        return None, None
    s = str(s).strip()
    if not s:
        return None, None
    cur = None
    for sym, code in (("kr", "DKK"), ("dkk", "DKK"), ("$", "USD"), ("usd", "USD"), ("€", "EUR"),
                      ("eur", "EUR"), ("£", "GBP"), ("gbp", "GBP"), ("sek", "SEK"), ("nok", "NOK"),
                      ("chf", "CHF")):
        if sym in s.lower():
            cur = code
            break
    m = re.search(r"-?\d[\d.,\s]*", s)
    num = re.sub(r"\s", "", m.group(0)).strip(".,") if m else ""
    if not re.search(r"\d", num):
        return None, cur
    if "," in num and "." in num:
        if num.rfind(",") > num.rfind("."):
            num = num.replace(".", "").replace(",", ".")
        else:
            num = num.replace(",", "")
    elif "," in num:
        num = num.replace(",", ".") if num.count(",") == 1 else num.replace(",", "")
    try:
        return float(num), cur
    except ValueError:
        return None, cur


def parse_qty(s):
    s = str(s or "").strip()
    if not s:
        return None
    s = re.sub(r"\s", "", s)
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", s):
        s = re.sub(r"[.,]", "", s)
    m = re.search(r"\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    try:
        return int(round(float(m.group(0).replace(",", "."))))
    except ValueError:
        return None


def guess_distributor(name, header, lines):
    text = (name + " " + " ".join(header)).lower()
    for k, v in DIST_NAMES.items():
        if re.search(r"(?<![a-z])" + re.escape(k) + r"(?![a-z])", text):
            return v
    pns = [l["dist_pn"] for l in lines if l.get("dist_pn")]
    if pns:
        if sum(p.endswith("-ND") for p in pns) > len(pns) / 2:
            return "DigiKey"
        if sum(bool(re.match(r"^\d{2,3}-", p)) for p in pns) > len(pns) / 2:
            return "Mouser"
        if sum(bool(re.fullmatch(r"C\d{3,9}", p)) for p in pns) > len(pns) / 2:
            return "LCSC"
    return "Ukendt grosist"


def load(name, data, project_mpns=frozenset()):
    sheets = read_table(name, data)
    best = None
    for rows in sheets:
        rows = [r for r in rows if any(c.strip() for c in r)]
        if not rows:
            continue
        hidx, cols = detect_columns(rows)
        if hidx is None:
            cols = _content_columns(rows, project_mpns)
            hidx = -1
        body = rows[hidx + 1:]
        score = len(cols) * 10 + len(body)
        if cols and (best is None or score > best[0]):
            best = (score, rows, hidx, cols)
    if best is None:
        raise ValueError("Kunne ikke finde varenumre/antal i filen.")
    _, rows, hidx, cols = best
    header = rows[hidx] if hidx >= 0 else []
    lines = []
    for i, r in enumerate(rows[hidx + 1:]):
        def get(c):
            j = cols.get(c)
            return r[j].strip() if j is not None and j < len(r) else ""
        mpn, dpn = get("mpn"), get("dist_pn")
        if not mpn and not dpn:
            continue
        low = (mpn + dpn).lower()
        if any(x in low for x in ("subtotal", "total", "merchandise", "shipping", "fragt", "moms", "vat")):
            continue
        qty = parse_qty(get("qty"))
        up, cur = parse_price(get("unit_price"))
        ep, cur2 = parse_price(get("ext_price"))
        if up is None and ep is not None and qty:
            up = ep / qty
        desc = get("desc")
        lines.append({
            "row": hidx + 2 + i, "mpn": mpn, "dist_pn": dpn, "qty": qty, "unit_price": up,
            "ext_price": ep if ep is not None else (up * qty if up is not None and qty else None),
            "currency": cur or cur2, "desc": desc, "mfr": get("mfr"), "refs": get("refs"),
            "package": get("package") or "",
        })
    dist = guess_distributor(name, header, lines)
    currency = next((l["currency"] for l in lines if l["currency"]), None)
    found = {k: header[v] if header and v < len(header) else f"kolonne {v + 1}" for k, v in cols.items()}
    return {"name": name, "distributor": dist, "currency": currency, "lines": lines, "columns": found}


# ---- matching ------------------------------------------------------------------

def _refs(text):
    return {r.upper() for r in re.findall(r"[A-Za-z]{1,4}\d{1,5}", text or "")}


def match(bom_lines, dist):
    """Attach the best distributor line to each BOM line, report everything that doesn't fit."""
    dlines = dist["lines"]
    used = set()
    by_mpn, by_pn = {}, {}
    for i, d in enumerate(dlines):
        if d["mpn"]:
            by_mpn.setdefault(norm_mpn(d["mpn"]), []).append(i)
        if d["dist_pn"]:
            by_pn.setdefault(norm_mpn(d["dist_pn"]), []).append(i)
    results = []
    for line in bom_lines:
        how, idx = None, None
        mpn = norm_mpn(line["mpn"] or line.get("mpn_guess", ""))
        if mpn and mpn in by_mpn:
            idx, how = by_mpn[mpn][0], "MPN"
        if idx is None:
            for pn in line["dist"].values():
                hits = by_pn.get(norm_mpn(pn)) or by_mpn.get(norm_mpn(pn))
                if hits:
                    idx, how = hits[0], "grosist-varenr."
                    break
        if idx is None and mpn and len(mpn) >= 6:
            # Packaging suffixes: LM317T vs LM317TG, GRM188R61A226ME15D vs ...ME15J
            for k, hits in by_mpn.items():
                short, long_ = sorted((k, mpn), key=len)
                if len(short) >= 6 and long_.startswith(short) and len(long_) - len(short) <= 4:
                    idx, how = hits[0], "MPN (uden emballage-suffiks)"
                    break
        if idx is None:
            refs = set(line["refs"])
            for i, d in enumerate(dlines):
                if d["refs"] and refs & _refs(d["refs"]):
                    idx, how = i, "reference (R1, C3 …)"
                    break
        if idx is None and line["kind"] and line.get("parsed"):
            idx, how = _match_by_value(line, dlines, used)
        res = {"id": line["id"], "dist_index": idx, "how": how, "issues": []}
        if idx is None:
            res["status"] = "missing"
            res["issues"].append("Findes ikke i grosist-BOM'en.")
        else:
            used.add(idx)
            res["status"] = "ok"
            d = dlines[idx]
            res["dist_line"] = d
            if how and how.startswith("MPN (uden"):
                res["issues"].append(f"Varenummer afviger let: projekt '{line['mpn']}', grosist '{d['mpn']}' "
                                     "(emballage/variant – tjek at det er den rigtige).")
                res["status"] = "warn"
            if line["mpn"] and d["mpn"] and norm_mpn(d["mpn"]) != norm_mpn(line["mpn"]) and how != "MPN" \
                    and not how.startswith("MPN"):
                res["issues"].append(f"Matchet via {how}, men MPN er forskellig: projekt '{line['mpn']}', "
                                     f"grosist '{d['mpn']}'.")
                res["status"] = "mismatch"
            if how == "værdi + pakke":
                res["status"] = "warn"
                res["issues"].append("Projektet har intet MPN; matchet på værdi og pakke i beskrivelsen.")
        results.append(res)
    extras = [dict(d, index=i) for i, d in enumerate(dlines) if i not in used]
    return results, extras


def _match_by_value(line, dlines, used):
    want = line["parsed"]["value"]
    pkg = P.parse_package(line["footprint"])
    for i, d in enumerate(dlines):
        if i in used:
            continue
        text = " ".join(x for x in (d["desc"], d["mpn"], d["package"]) if x)
        got = F.parse_value(text, line["kind"])
        if not got or abs(got["value"] - want) > want * 0.001 + 1e-15:
            continue
        dpkg = P.parse_package(text)
        if pkg and dpkg and P.compare(pkg, dpkg)[0] == "mismatch":
            continue
        return i, "værdi + pakke"
    return None, None


def check_quantity(needed, spare_needed, ordered):
    if ordered is None:
        return "unknown", "Antal ikke angivet i grosist-BOM'en."
    if ordered < needed:
        return "mismatch", f"Bestilt {ordered}, men der skal bruges {needed}. Mangler {needed - ordered}."
    if ordered < spare_needed:
        return "warn", f"Bestilt {ordered} – dækker behovet ({needed}), men ingen reserve (anbefalet {spare_needed})."
    return "ok", f"Bestilt {ordered}, behov {needed}" + (f" + reserve = {spare_needed}." if spare_needed > needed else ".")
