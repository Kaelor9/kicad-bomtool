"""Structured data from a datasheet's text: package dimension tables
("Dim Min Max Typ / D 2.90 3.10 3.00 / e 0.95 BSC"), suggested pad layouts
and pin tables. Also finds the pages with the package drawing so the user can
look at the drawing itself.
"""
import re

from . import packages as P
from .datasheet import packages_in

# JEDEC-style dimension symbols
_SYM = r"(A[123]?|b[12]?|c[12]?|D[123]?|E[123]?|e[12]?|H[DE]?|L[123]?|K|N|Z[DE]?|θ|q|a1?|ccc|aaa|bbb|ddd)"
_NUM = r"(?:\d+(?:[.,]\d+)?|[.,]\d+)"
_PIN_SECTION = re.compile(r"pin\s*(?:descriptions?|functions?|configurations?|assignments?|definitions?)|"
                          r"terminal\s+functions|pin\s+out", re.I)
_PIN_NAME = r"[A-Za-z~/][A-Za-z0-9_+\-#/~]{0,15}"
_NOTPIN = {"PIN", "NAME", "NUMBER", "NO", "TYPE", "FUNCTION", "DESCRIPTION", "I", "O", "IO", "I/O", "THE", "AND",
           "FOR", "TO", "OF", "SEE", "NOTE", "FIGURE", "TABLE", "PAGE", "MIN", "MAX", "TYP"}


def pages(text):
    return text.split("\f")


def _f(s):
    return float(s.replace(",", "."))


def _pkg_near(lines, i, back=8):
    for j in range(i - 1, max(-1, i - back - 1), -1):
        found = packages_in(lines[j])
        if found:
            return found[0][0], lines[j].strip()
    return None, ""


# ---- dimension tables ---------------------------------------------------------------

def _header(lines, i):
    """Column layout if line i is a table header such as "Dim Min Max Typ" or "MIN NOM MAX"
    (TI puts DIM / MILLIMETERS on the lines above). Returns (order, (from, to), inches) or None."""
    line = lines[i]
    words = [w.lower()[:3] for w in re.findall(r"\b(min|nom|typ|max)\b", line, re.I)]
    if len(words) < 2:
        return None
    rest = re.sub(r"\b(min|nom|typ|max)\b|\b(dim\w*|symbols?|ref|values?)\b|millimet\w*|inch\w*|\(?mm\)?|[.()]",
                  "", line, flags=re.I)
    if len(rest.strip()) > 6:
        return None
    context = " ".join(lines[max(0, i - 3):i + 1]).lower()
    if not re.search(r"\bdim|symbol|millimet|inch|\bmm\b", context):
        return None
    words = ["nom" if w == "typ" else w for w in words]
    mm_pos, in_pos = context.find("millimet"), context.find("inch")
    if mm_pos < 0 and re.search(r"\bmm\b", context):
        mm_pos = context.find("mm")
    if in_pos >= 0 and mm_pos >= 0 and len(words) % 2 == 0 and len(words) >= 4:
        half = len(words) // 2
        if mm_pos < in_pos:
            return words[:half], (0, half), False
        return words[half:], (half, None), False
    return words, (0, None), in_pos >= 0 and mm_pos < 0


def _rows(lines, j, order, cols, sym_rx):
    """Read table rows from line j on. Returns ({sym: {min, nom, max}}, next line, inches-note)."""
    dims, inches = {}, None
    start = j
    while j < len(lines) and j < start + 45:
        row = lines[j].strip()
        rm = re.match(sym_rx + r"\s+(.*)$", row)
        if not rm:
            if re.search(r"all dimensions|dimensions in", row, re.I):
                inches = bool(re.search(r"inch", row, re.I))
            if dims and row and not re.search(r"all dimensions|dimensions in|^note", row, re.I):
                break
            j += 1
            continue
        sym, rest = rm.group(1), rm.group(2)
        vals = re.findall(_NUM + r"|[-–—]|�+", rest)
        nums = [(_f(v) if re.match(_NUM + "$", v) else None) for v in vals]
        real_all = [n for n in nums if n is not None]
        row_order = order
        half = len(real_all) // 2
        if cols == (0, None) and len(real_all) >= 4 and len(real_all) % 2 == 0 and real_all[0] and \
                abs(real_all[0] / 25.4 - real_all[half]) < 0.002 + real_all[half] * 0.03:
            # mm and inch columns side by side without a header saying so: the second half is the first / 25.4
            nums, row_order = real_all[:half], (["min", "max"] if half == 2 else ["min", "nom", "max"][:half])
        elif cols != (0, None) and len(real_all) % 2 == 0 and 0 < len(real_all) < 2 * len(order):
            # Header says Min/Typ/Max for both units, but this row leaves Typ empty: split the row itself.
            nums = real_all[:half] if cols[0] == 0 else real_all[half:]
            row_order = ["min", "max"] if half == 2 else ["nom"]
        else:
            nums = nums[cols[0]:cols[1]]
        real = [n for n in nums if n is not None]
        if re.search(r"BSC|REF|TYP\b", rest) or len(real) == 1:
            if real:
                dims[sym] = {"min": None, "nom": real[0], "max": None}
        elif real:
            d = {"min": None, "nom": None, "max": None}
            for k, v in zip(row_order, nums):
                d[k] = v
            dims[sym] = d
        j += 1
    return dims, j, inches


def _to_mm(dims):
    return {k: {kk: (round(vv * 25.4, 3) if vv is not None else None) for kk, vv in v.items()}
            for k, v in dims.items()}


def _label_tables(out):
    """Tables without their own label take the "(n) Package Type: X" names of their page, in order."""
    for pno in {t["page"] for t in out}:
        same = [t for t in out if t["page"] == pno]
        for n, t in enumerate(same):
            if not t["pkg"] and n < len(t["types"]):
                t["label"] = t["types"][n]
                t["pkg"] = P.parse_package(t["label"])
    for t in out:
        t.pop("types", None)
        t["name"] = P.describe(t["pkg"]) if t["pkg"] else (t["label"] or "ukendt pakke")
    return out


def _types(page):
    return [m.group(1).strip() for m in re.finditer(r"Package\s+Type:\s*([^\n]+)", page)]


def dim_tables(text):
    """[{page, label, pkg, name, dims: {sym: {min, nom, max}}}] - package dimension tables, in mm."""
    out = []
    for pno, page in enumerate(pages(text), 1):
        lines = page.splitlines()
        types = _types(page)
        i = 0
        while i < len(lines):
            h = _header(lines, i)
            if not h:
                i += 1
                continue
            order, cols, inches = h
            dims, j, note = _rows(lines, i + 1, order, cols, _SYM)
            if note is not None:
                inches = note
            if (len(dims) >= 3 and dims.get("e")) or len(dims) >= 4:
                if inches:
                    dims = _to_mm(dims)
                pkg, label = _pkg_near(lines, i)
                out.append({"page": pno, "pkg": pkg, "label": label, "dims": dims, "types": types})
            i = max(j, i + 1)
    return _label_tables(out)


def pad_layouts(text):
    """Suggested/recommended land patterns given as a value table ("C 0.95 / X 0.55 / Y 0.80",
    or TI's "F1 6.205 6.305"). Shown to the user as they are - the letters differ between makers."""
    out = []
    for pno, page in enumerate(pages(text), 1):
        if not re.search(r"(suggested|recommended)\s+(pad|land|footprint|solder|pcb)|land\s+pattern|"
                         r"pcb\s+(layout|pattern)", page, re.I):
            continue
        lines = page.splitlines()
        types = _types(page)
        tables = []
        i = 0
        while i < len(lines):
            if re.search(r"dimensions?\s+value", lines[i], re.I):
                dims, j, _ = _rows(lines, i + 1, ["nom"], (0, None), r"([A-Z][0-9]?)")
            else:
                h = _header(lines, i)
                if not h:
                    i += 1
                    continue
                dims, j, note = _rows(lines, i + 1, h[0], h[1], r"([A-Z][A-Z]?\d{0,2})")
                if note or h[2]:
                    dims = _to_mm(dims)
                if set(dims) & {"D", "E", "e", "b", "A1"}:   # a package table, not a land pattern
                    i = max(j, i + 1)
                    continue
            if len(dims) >= 2:
                vals = {}
                for k, d in dims.items():
                    if d["nom"] is not None:
                        v = d["nom"]
                    elif d["min"] is not None and d["max"] is not None:
                        v = (d["min"] + d["max"]) / 2
                    else:
                        v = d["min"] if d["min"] is not None else d["max"]
                    vals[k] = round(v, 3)
                tables.append(vals)
            i = max(j, i + 1)
        for n, vals in enumerate(tables):
            label = types[n] if n < len(types) else ""
            out.append({"page": pno, "label": label, "pkg": P.parse_package(label) if label else None,
                        "values": vals})
    return out


def drawing_pages(text, fp_pkg=None):
    """Pages with the package outline and the land pattern - best match for the footprint first."""
    hits = []
    for pno, page in enumerate(pages(text), 1):
        low = page.lower()
        score = 0
        if re.search(r"package\s+(outline|drawing|dimensions|information)|mechanical\s+(data|drawing|dimensions)|"
                     r"outline\s+dimensions", low):
            score += 3
        if re.search(r"(suggested|recommended)\s+(pad|land|footprint|pcb)|land\s+pattern|solder\s+pad", low):
            score += 2
        if score and fp_pkg:
            if any(P.compare(fp_pkg, pkg)[0] in ("ok", "partial") for pkg, _ in packages_in(page)):
                score += 3
        if score:
            hits.append((score, pno))
    hits.sort(key=lambda h: (-h[0], h[1]))
    return [p for _, p in hits[:4]]


# ---- pins ---------------------------------------------------------------------------

def _pinname_ok(name):
    return name.upper() not in _NOTPIN and not re.search(r"[a-z]{4,}", name)


def pin_tables(text):
    """Pin number -> name maps found in the datasheet's pin tables.
    Tables with several package columns ("IN 1 1 6 6") give one map per column."""
    maps = []
    for pno, page in enumerate(pages(text), 1):
        for sec in _PIN_SECTION.finditer(page):
            chunk = page[sec.end():sec.end() + 4000].splitlines()
            by_num, by_name = {}, {}
            for row in chunk[:120]:
                row = row.strip()
                m = re.match(r"(\d{1,3})\s+(" + _PIN_NAME + r")(?:\s|$)", row)
                if m and _pinname_ok(m.group(2)):
                    by_num.setdefault(m.group(1), m.group(2))
                    continue
                m = re.match(r"(" + _PIN_NAME + r")\s+((?:(?:\d{1,3}|[-–—]|Pad)\s+){1,8})", row + " ")
                if m and _pinname_ok(m.group(1)):
                    cols = re.findall(r"\d{1,3}|[-–—]|Pad", m.group(2))
                    by_name.setdefault(m.group(1), cols)
            if len(by_num) >= 3:
                maps.append({"page": pno, "pins": by_num})
            if len(by_name) >= 3:
                ncol = max(len(c) for c in by_name.values())
                for k in range(ncol):
                    pins = {}
                    for name, cols in by_name.items():
                        if k < len(cols) and re.fullmatch(r"\d{1,3}", cols[k]):
                            pins.setdefault(cols[k], name)
                    if len(pins) >= 3:
                        maps.append({"page": pno, "pins": pins, "column": k + 1})
    seen, out = set(), []
    for m in maps:
        key = tuple(sorted(m["pins"].items()))
        if key not in seen:
            seen.add(key)
            out.append(m)
    return out


_CLASSES = [
    ("GND", r"^(A|D|P|S|E)?GND\d*$|^VSS\w*$|^V-$|^COM$|^EP$|^PAD$|^THERMAL\w*$"),
    ("SUPPLY", r"^V(CC|DD|IN|S|BAT|SUP|\+)\w*$|^IN$|^PVIN$"),
    ("NC", r"^N\.?C\.?$|^DNC$|^NIC$"),
]


def norm_pin(name):
    n = re.sub(r"[^A-Z0-9+\-]", "", (name or "").upper())
    if len(n) > 3:
        n = re.sub(r"(_?N|B)$", "", n)
    return n


def pin_class(name):
    n = re.sub(r"[^A-Z0-9+\-]", "", (name or "").upper())
    for cls, rx in _CLASSES:
        if re.search(rx, n):
            return cls
    return None


def compare_pins(want, have):
    """want/have: {num: name}. Returns (matched, similar, differ[(num, want, have)], missing[num])."""
    matched, similar, differ, missing = 0, 0, [], []
    for num, name in want.items():
        other = have.get(num)
        if other is None:
            missing.append(num)
            continue
        a, b = norm_pin(name), norm_pin(other)
        if a == b or (len(a) >= 2 and len(b) >= 2 and (a in b or b in a)):
            matched += 1
        elif pin_class(name) and pin_class(name) == pin_class(other):
            similar += 1
        else:
            differ.append((num, name, other))
    return matched, similar, differ, missing


def best_pin_map(want, tables):
    """The pin table (column) from the datasheet that best fits `want`."""
    best, best_score = None, None
    for t in tables:
        m, s, d, miss = compare_pins(want, t["pins"])
        score = m * 2 + s - len(d) * 2 - len(miss) * 0.5
        if best_score is None or score > best_score:
            best, best_score = t, score
    return best
