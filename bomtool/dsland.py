"""The datasheet's recommended footprint, read from its drawing.

Most datasheets draw the recommended land pattern ("Recommended Pad Layout", "Land Pattern",
"Example Board Layout" ...) as vector graphics. It is read the way a person reads it:

1. the pads are the rectangles of the drawing (filled, outlined, or drawn as four loose sides with
   rounded corners like TI does) - the biggest group of equally sized ones that keep a gap;
2. every dimension line is a pair of arrow heads, and its value is the number written nearest to it
   ("1.5 ± 0.05 (.059)" -> 1.5; TI's "6X (1.1)" -> 1.1);
3. the arrow tips land on pad edges or pad centre lines, so each measure ties two edges together,
   and pads drawn the same size are the same size. That fixes every edge in mm.

Drawings are often not to scale (Bourns draws its pads wider than they are), so the drawing's own
proportions are never used - only the numbers. A drawing that is a picture, or whose numbers don't
pin every edge down, gives nothing: better no footprint than a wrong one.
"""
import itertools
import math
import re

from . import datasheet, dsdata, dsimage

NUM = re.compile(r"(?<![\d.])(\d{1,2}(?:[.,]\d{1,3})?|[.,]\d{1,3})(?![\d.])")


def read(url, fp_pkg=None, own_geo=None):
    """{pads, label, page, rule, hits} for the recommended footprint drawn in the datasheet, or None.
    With `own_geo` the pads are turned and numbered like the user's footprint, and of several
    drawings (one per package style) the one most like the user's footprint is chosen."""
    if not dsimage.available():
        return None
    data = datasheet.fetch(url)
    text = datasheet.text_for(url)
    with dsimage._PDFIUM:
        found = _read(data, text, fp_pkg)
    if not found:
        return None
    best = None
    for f in found:
        pads = f["pads"]
        if own_geo and own_geo.get("pads"):
            pads, err = _orient(pads, own_geo)
        else:
            err = 0.0
        if best is None or err < best[0]:
            best = (err, dict(f, pads=pads))
    return best[1]


def _read(data, text, fp_pkg):
    import pypdfium2 as pdfium  # noqa: PLC0415

    doc = pdfium.PdfDocument(data)
    out = []
    try:
        order = dsdata.drawing_pages(text, fp_pkg)
        order += [p for p in range(1, len(doc) + 1) if p not in order]
        found = dsimage._find(doc, order, dsimage.LAND)
        try:
            seen = set()
            for _, (idx, x, y) in zip(range(10), found):
                key = (idx, round(y))
                if key in seen:
                    continue
                seen.add(key)
                res = _from_region(doc[idx], _region(doc, idx, x, y))
                if res:
                    res["page"] = idx + 1
                    res["label"] = f"Databladets tegning (s. {idx + 1}), aflæst"
                    out.append(res)
                if len(out) >= 4:
                    break
        finally:
            found.close()
    finally:
        doc.close()
    return out


# ---- reading one drawing ----------------------------------------------------------------

def _region(doc, idx, x, y):
    """Where to look for the drawing under the heading at (x, y): down to the next heading or section
    bar (a filled band across the page), at most half a page; from a bit left of the heading
    to the right edge. Shapes that are not part of it are sorted out later."""
    import pypdfium2.raw as R  # noqa: PLC0415
    page = doc[idx]
    pw, h = page.get_size()
    bottom = min(h, y + h * 0.45)
    for hy in dsimage._headings(doc, idx):
        if y + 25 < hy < bottom:
            bottom = hy - 2
    for o in page.get_objects(max_depth=2):
        if o.type != R.FPDF_PAGEOBJ_PATH:
            continue
        x0, y0, x1, y1 = (o.get_bounds() if hasattr(o, "get_bounds") else o.get_pos())[:4]
        top = h - y1
        if x1 - x0 > pw * 0.6 and 6 <= y1 - y0 < 30 and y + 25 < top < bottom:
            bottom = top - 1
    return (max(0.0, x - pw * 0.35), y - 4, pw, bottom)
# All coordinates here are points with y going down the page (like the picture, and like KiCad).

def _shapes(page, box):
    """The drawing's vector shapes inside box (l, t, r, b): rectangles (x0, y0, x1, y1, filled),
    arrow heads (tip x, tip y, axis "x"/"y", +1/-1 = which way it points)."""
    import ctypes  # noqa: PLC0415
    import pypdfium2.raw as R  # noqa: PLC0415
    l, t, r, b = box
    h = page.get_size()[1]
    rects, arrows, hs, vs = [], [], [], []
    for o in page.get_objects(max_depth=6):
        if o.type != R.FPDF_PAGEOBJ_PATH:
            continue
        bx0, by0, bx1, by1 = (o.get_bounds() if hasattr(o, "get_bounds") else o.get_pos())[:4]
        x0, x1, y0, y1 = bx0, bx1, h - by1, h - by0
        if x0 < l - 1 or x1 > r + 1 or y0 < t - 1 or y1 > b + 1:
            continue
        n = R.FPDFPath_CountSegments(o.raw)
        if n < 2 or n > 40:
            continue
        fill, stroke = ctypes.c_int(0), ctypes.c_int(0)
        R.FPDFPath_GetDrawMode(o.raw, fill, stroke)
        m = o.get_matrix() if hasattr(o, "get_matrix") else None
        pts, curved, closed = [], False, False
        for k in range(n):
            seg = R.FPDFPath_GetPathSegment(o.raw, k)
            closed = closed or bool(R.FPDFPathSegment_GetClose(seg))
            if R.FPDFPathSegment_GetType(seg) == R.FPDF_SEGMENT_BEZIERTO:
                curved = True
                continue
            px, py = ctypes.c_float(0), ctypes.c_float(0)
            R.FPDFPathSegment_GetPoint(seg, px, py)
            X, Y = (m.on_point(px.value, py.value) if m is not None else (px.value, py.value))
            pts.append((round(X, 2), round(h - Y, 2)))
        uniq = list(dict.fromkeys(pts))
        if len(uniq) == 2 and not curved and stroke.value:
            (ax, ay), (bx, by) = uniq
            if abs(ay - by) < 0.3 and abs(ax - bx) > 1.5:
                hs.append((ay, min(ax, bx), max(ax, bx)))
            elif abs(ax - bx) < 0.3 and abs(ay - by) > 1.5:
                vs.append((ax, min(ay, by), max(ay, by)))
            continue
        # Closed: flagged so, or the outline ends where it began.
        closed = closed or (len(pts) > 2 and abs(pts[0][0] - pts[-1][0]) < 0.3 and abs(pts[0][1] - pts[-1][1]) < 0.3)
        if not (fill.value or closed):
            continue
        if len(uniq) == 3 and not curved and max(x1 - x0, y1 - y0) < 15:
            a = _arrow(uniq)
            if a:
                arrows.append(a)
            continue
        if not fill.value and stroke.value:
            # An outline: its bounds include half the line width on every side.
            wd = ctypes.c_float(0)
            if R.FPDFPageObj_GetStrokeWidth(o.raw, wd) and 0 < wd.value < min(x1 - x0, y1 - y0) / 3:
                x0, y0, x1, y1 = x0 + wd.value / 2, y0 + wd.value / 2, x1 - wd.value / 2, y1 - wd.value / 2
        if x1 - x0 < 3 or y1 - y0 < 3 or not _boxy(uniq, (x0, y0, x1, y1)):
            continue
        rects.append((x0, y0, x1, y1, bool(fill.value)))
    rects += _line_rects(hs, vs)
    # A pad drawn twice (filled, then outlined): keep one.
    rects.sort(key=lambda q: not q[4])
    keep = []
    for q in rects:
        if not any(all(abs(q[i] - k[i]) < 2 for i in range(4)) for k in keep):
            keep.append(q)
    return keep, arrows


def _line_rects(hs, vs):
    """Rectangles drawn as four loose sides (TI draws every side, and every rounded corner, as its own
    path): two vertical lines over the same height, joined by a line along the top and the bottom
    (which may stop short of the corners by the corner radius)."""
    out = []
    vs = sorted(vs)
    for i, L in enumerate(vs):
        for R_ in vs[i + 1:]:
            w = R_[0] - L[0]
            if w < 3:
                continue
            if w > 80:
                break
            if abs(L[1] - R_[1]) > 1 or abs(L[2] - R_[2]) > 1:
                continue
            r = min(6.0, w / 2)
            top = [h for h in hs if L[1] - r - 0.5 <= h[0] <= L[1] + 0.5 and h[1] >= L[0] - 1 and h[2] <= R_[0] + 1
                   and h[2] - h[1] >= w * 0.4]
            bot = [h for h in hs if L[2] - 0.5 <= h[0] <= L[2] + r + 0.5 and h[1] >= L[0] - 1 and h[2] <= R_[0] + 1
                   and h[2] - h[1] >= w * 0.4]
            if top and bot:
                out.append((L[0], min(t[0] for t in top), R_[0], max(b[0] for b in bot), False))
                break
    return out


def _arrow(pts):
    """An arrow head (a small triangle): (tip x, tip y, axis, direction). The tip is the corner that
    is not on the base - the base is the side across the arrow's axis."""
    for i in range(3):
        tip, b1, b2 = pts[i], pts[(i + 1) % 3], pts[(i + 2) % 3]
        if abs(b1[0] - b2[0]) < 0.4 and abs(tip[0] - b1[0]) > 1:           # base vertical: points along x
            return tip[0], tip[1], "x", 1 if tip[0] > b1[0] else -1
        if abs(b1[1] - b2[1]) < 0.4 and abs(tip[1] - b1[1]) > 1:           # base horizontal: along y
            return tip[0], tip[1], "y", 1 if tip[1] > b1[1] else -1
    return None


def _boxy(pts, bounds):
    """Is the path a rectangle? Every corner lies on the bounding box and it touches all four sides
    (rounded corners: the curves are skipped, the straight ends still lie on the sides)."""
    x0, y0, x1, y1 = bounds
    tol = max(1.0, min(x1 - x0, y1 - y0) * 0.08)
    sides = [False] * 4
    for px, py in pts:
        on = [abs(px - x0) <= tol, abs(py - y0) <= tol, abs(px - x1) <= tol, abs(py - y1) <= tol]
        if not any(on):
            return False
        sides = [a or b for a, b in zip(sides, on)]
    return len(pts) >= 4 and all(sides)


def _texts(page, box):
    """Measures written in the box: [(value, cx, cy)]. The text is put together character by character
    into runs (rotated text too), then the first number of a run counts; numbers in brackets (inches
    after mm: "1.5 ± 0.05 (.059 ± .002)") and tolerances are left out."""
    import pypdfium2.raw as R  # noqa: PLC0415
    l, t, r, b = box
    h = page.get_size()[1]
    tp = page.get_textpage()
    chars = []
    try:
        for i in range(tp.count_chars()):
            c = chr(R.FPDFText_GetUnicode(tp.raw, i) or 32)
            try:
                x0, y0, x1, y1 = tp.get_charbox(i, loose=True)   # the font's full height, also for "."
            except TypeError:
                x0, y0, x1, y1 = tp.get_charbox(i)
            X0, X1, Y0, Y1 = x0, x1, h - y1, h - y0
            if X0 < l - 1 or X1 > r + 1 or Y0 < t - 1 or Y1 > b + 1 or (c.isspace() and X1 - X0 < 0.01):
                continue
            ang = R.FPDFText_GetCharAngle(tp.raw, i)
            vertical = 0.7 < abs(math.sin(ang)) if ang >= 0 else False
            chars.append((c, X0, Y0, X1, Y1, vertical))
    finally:
        tp.close()
    runs = []
    for c, x0, y0, x1, y1, vert in chars:
        size = (x1 - x0) if vert else (y1 - y0)
        size = max(size, 2.0)
        u0, u1, w = (y0, y1, (x0 + x1) / 2) if vert else (x0, x1, (y0 + y1) / 2)
        for run in runs:
            if run["vert"] == vert and abs(run["w"] - w) < size * 0.6 and -size * 0.3 < (u0 if not vert else u0) - run["u1"] < size * 1.2:
                run["text"] += c
                run["u1"] = max(run["u1"], u1)
                run["box"] = [min(run["box"][0], x0), min(run["box"][1], y0), max(run["box"][2], x1), max(run["box"][3], y1)]
                break
        else:
            runs.append({"text": c, "u1": u1, "w": w, "vert": vert, "box": [x0, y0, x1, y1]})
    img = page.render(scale=1).to_pil().convert("L")
    out, bracketed = [], []
    for run in runs:
        x0, y0, x1, y1 = run["box"]
        if not _inked(img, x0, y0, x1, y1):
            continue        # invisible text (PDFs carry hidden duplicates and leftovers)
        raw = re.sub(r"^\d+\s*[Xx]\s*", "", run["text"].strip())    # "6X (1.1)": six pads of 1.1
        if raw.startswith(("±", "+", "-", "–")):
            continue
        alone = raw.startswith("(")
        # "(1.1)" alone is the measure (TI writes reference measures so); "1.5 (.059)" is mm then inches.
        s = raw.strip("()") if alone else re.sub(r"\([^)]*\)?", " ", raw)
        s = re.sub(r"[±+\-–]\s*[\d.,]+", " ", s)
        if re.search(r"[A-Za-z]{3,}", s) or re.match(r"\s*[A-Za-z]", s):
            continue        # words, or "R0.05" (a corner radius)
        m = NUM.search(s)
        if m:
            v = float(m.group(1).replace(",", "."))
            if 0.05 <= v <= 60:
                (bracketed if alone else out).append((v, (x0 + x1) / 2, (y0 + y1) / 2, y1 - y0))
    # A bracketed line right under a plain number is the same measure in inches.
    for v, cx, cy, hh in bracketed:
        if not any(abs(cx - c2) < 15 and 0 < cy - c3 < hh * 1.8 for _, c2, c3, _ in out):
            out.append((v, cx, cy, hh))
    return [(v, cx, cy) for v, cx, cy, _ in out]


def _inked(img, x0, y0, x1, y1):
    px = img.load()
    for x in range(int(x0), int(x1) + 1):
        for y in range(int(y0), int(y1) + 1):
            if 0 <= x < img.width and 0 <= y < img.height and px[x, y] < 160:
                return True
    return False


def _pads(rects):
    """The pads among the rectangles: the biggest group of equally sized ones (at least two) that
    don't touch each other (table cells do), plus one bigger rectangle inside their area (an exposed
    pad). Frames around other shapes are not pads."""
    def area(a):
        return (a[2] - a[0]) * (a[3] - a[1])

    def contains(a, c):
        return (a != c and a[0] <= c[0] + 0.3 and a[1] <= c[1] + 0.3 and a[2] >= c[2] - 0.3 and a[3] >= c[3] - 0.3
                and area(a) > area(c) * 1.5)
    shapes = [q for q in rects if not any(contains(q, c) for c in rects)]
    groups = []
    for q in shapes:
        w, h = q[2] - q[0], q[3] - q[1]
        for g in groups:
            gw, gh = g[0][2] - g[0][0], g[0][3] - g[0][1]
            if abs(w - gw) <= max(0.4, gw * 0.04) and abs(h - gh) <= max(0.4, gh * 0.04):
                g.append(q)
                break
        else:
            groups.append([q])
    groups = [g for g in groups if 2 <= len(g) <= 120 and _apart(g)]
    if not groups:
        return []
    groups.sort(key=lambda g: (-len(g), -sum(q[4] for q in g)))
    pads = groups[0]
    x0, y0 = min(q[0] for q in pads), min(q[1] for q in pads)
    x1, y1 = max(q[2] for q in pads), max(q[3] for q in pads)
    big = [q for q in shapes if q not in pads and q[0] > x0 and q[2] < x1 and q[1] > y0 and q[3] < y1
           and area(q) > area(pads[0]) * 1.5]
    if len(big) == 1:
        pads = pads + big
    return pads


def _apart(g):
    """Pads keep a gap to their neighbours; the rows of a table touch."""
    small = min(min(q[2] - q[0], q[3] - q[1]) for q in g)
    for a, c in itertools.combinations(g, 2):
        gx = max(a[0], c[0]) - min(a[2], c[2])
        gy = max(a[1], c[1]) - min(a[3], c[3])
        if max(gx, gy) < small * 0.08:
            return False
    return True


def _dims(arrows, texts):
    """Dimension lines: two arrow heads on one line pointing away from or towards each other, and the
    number written nearest to them. [(axis, a, b, value)] with a < b where the arrow tips point."""
    dims = []
    for axis in ("x", "y"):
        al = [a for a in arrows if a[2] == axis]
        along = (lambda a: a[0]) if axis == "x" else (lambda a: a[1])
        across = (lambda a: a[1]) if axis == "x" else (lambda a: a[0])
        rows = []
        for a in sorted(al, key=across):
            for row in rows:
                if abs(across(row[0]) - across(a)) < 1.5:
                    row.append(a)
                    break
            else:
                rows.append([a])
        for row in rows:
            row.sort(key=along)
            i = 0
            while i + 1 < len(row):
                p, q = row[i], row[i + 1]
                if p[3] != q[3] and along(q) - along(p) > 1:
                    dims.append([axis, along(p), along(q), across(p)])
                    i += 2
                else:
                    i += 1
    # Each dimension gets the nearest number: beside the line, inside its span or just past an end.
    pairs = []
    for di, (axis, a, b, line) in enumerate(dims):
        for ti, (v, cx, cy) in enumerate(texts):
            u, w = (cx, cy) if axis == "x" else (cy, cx)
            off = abs(w - line)
            outside = max(0.0, a - u, u - b)
            if off <= 16 and outside <= 60:
                pairs.append((off + outside * 0.5, di, ti))
    pairs.sort()
    used_d, used_t, out = set(), set(), []
    for _, di, ti in pairs:
        if di in used_d or ti in used_t:
            continue
        used_d.add(di)
        used_t.add(ti)
        axis, a, b, _line = dims[di]
        out.append((axis, a, b, texts[ti][0]))
    return out


class _Offsets:
    """Union-find that also keeps every member's distance (in mm) from its root."""

    def __init__(self):
        self.parent, self.off = {}, {}

    def find(self, k):
        self.parent.setdefault(k, k)
        self.off.setdefault(k, 0.0)
        if self.parent[k] == k:
            return k, 0.0
        root, o = self.find(self.parent[k])
        self.parent[k] = root
        self.off[k] += o
        return root, self.off[k]

    def join(self, a, b, d):
        """position(b) - position(a) = d. Returns False when it contradicts what is known."""
        ra, oa = self.find(a)
        rb, ob = self.find(b)
        if ra == rb:
            return abs((ob - oa) - d) <= max(0.03, abs(d) * 0.03)
        self.parent[rb] = ra
        self.off[rb] = oa + d - ob
        return True

    def known(self, a, b):
        ra, oa = self.find(a)
        rb, ob = self.find(b)
        return ob - oa if ra == rb else None


def _solve(pads, dims, axis):
    """Positions in mm of every pad edge along one axis, from the dimensions; None when the numbers
    don't pin every edge down or contradict each other."""
    i0, i1 = (0, 2) if axis == "x" else (1, 3)
    # Edges at the same place in the drawing are the same edge (pads in a row).
    coords = sorted({round(q[i], 1) for q in pads for i in (i0, i1)})
    merged = []
    for c in coords:
        if merged and c - merged[-1][-1] < 0.8:
            merged[-1].append(c)
        else:
            merged.append([c])
    pos = [sum(g) / len(g) for g in merged]

    def node(v):
        k = min(range(len(pos)), key=lambda j: abs(pos[j] - v))
        return k if abs(pos[k] - v) < max(2.0, (pos[-1] - pos[0]) * 0.03) else None
    U = _Offsets()
    edges = [(node(q[i0]), node(q[i1])) for q in pads]
    centres = {}
    for k, (a, b) in enumerate(edges):
        centres.setdefault(round((pos[a] + pos[b]) / 2, 1), []).append(k)
    used = []
    for ax, a, b, v in dims:
        if ax != axis:
            continue
        na, nb = node(a), node(b)
        if na is not None and nb is not None and na != nb:
            if not U.join(na, nb, v):
                return None, used
            used.append(v)
            continue
        # Pitch: from centre line to centre line of two pads of the same size.
        ca = next((ks for c, ks in centres.items() if abs(c - a) < 1.5), None)
        cb = next((ks for c, ks in centres.items() if abs(c - b) < 1.5), None)
        if ca and cb:
            pa, pb = pads[ca[0]], pads[cb[0]]
            if abs((pa[i1] - pa[i0]) - (pb[i1] - pb[i0])) < 0.8:
                if not U.join(edges[ca[0]][0], edges[cb[0]][0], v):
                    return None, used
                used.append(v)
                # "4X (0.95)": the same pitch between every pair of neighbours drawn as far apart.
                d = b - a
                for j, pj in enumerate(pads):
                    for k, pk in enumerate(pads):
                        dc = (pk[i0] + pk[i1]) / 2 - (pj[i0] + pj[i1]) / 2
                        if abs(dc - d) < max(1.0, d * 0.02) and abs((pj[i1] - pj[i0]) - (pk[i1] - pk[i0])) < 0.8:
                            if not U.join(edges[j][0], edges[k][0], v):
                                return None, used
    if not used:
        return None, used
    # Pads drawn the same size are the same size.
    size = {}
    for q, (a, b) in zip(pads, edges):
        size.setdefault((round(q[2] - q[0]), round(q[3] - q[1])), []).append((a, b))
    for _ in range(4):
        for members in size.values():
            w = next((U.known(a, b) for a, b in members if U.known(a, b) is not None), None)
            if w is None:
                continue
            for a, b in members:
                if not U.join(a, b, w):
                    return None, used
    root = U.find(edges[0][0])[0]
    if any(U.find(k)[0] != root for e in edges for k in e):
        return None, used
    mm = {k: U.find(k)[1] for e in edges for k in e}
    return [(mm[a], mm[b]) for a, b in edges], used


def _from_region(page, box):
    rects, arrows = _shapes(page, box)
    pads = _pads(rects)
    if len(pads) < 2:
        return None
    texts = _texts(page, box)
    dims = _dims(arrows, texts)
    xs, ux = _solve(pads, dims, "x")
    ys, uy = _solve(pads, dims, "y")
    if not xs or not ys:
        return None
    cx = (min(a for a, _ in xs) + max(b for _, b in xs)) / 2
    cy = (min(a for a, _ in ys) + max(b for _, b in ys)) / 2
    out = []
    for (x0, x1), (y0, y1) in zip(xs, ys):
        w, h = x1 - x0, y1 - y0
        if not (0.08 <= w <= 20 and 0.08 <= h <= 20):
            return None
        out.append({"num": "", "type": "smd", "shape": "rect", "angle": 0,
                    "x": round((x0 + x1) / 2 - cx, 3), "y": round((y0 + y1) / 2 - cy, 3),
                    "w": round(w, 3), "h": round(h, 3)})
    out.sort(key=lambda p: (p["y"], p["x"]))
    hits = sorted(set(ux + uy))
    return {"pads": out, "hits": hits,
            "rule": "Aflæst fra databladets tegning (målene " + ", ".join(f"{v:g}" for v in hits) + " mm)."}


# ---- numbering ------------------------------------------------------------------------------

def _turn(pads, deg, mirror):
    c, s = round(math.cos(math.radians(deg))), round(math.sin(math.radians(deg)))
    out = []
    for p in pads:
        x = -p["x"] if mirror else p["x"]
        q = dict(p, x=round(x * c - p["y"] * s, 3), y=round(x * s + p["y"] * c, 3))
        if deg % 180:
            q["w"], q["h"] = p["h"], p["w"]
        out.append(q)
    return out


def _orient(pads, own_geo):
    """Turn the pads so they lie like the user's footprint, and give each the number of the user's pad
    it lands on. Returns (pads, mean distance in mm) - the distance says how alike they are."""
    own = [p for p in own_geo["pads"] if p.get("type") != "np_thru_hole"]
    if not own:
        return pads, 0.0
    ox = (min(p["x"] for p in own) + max(p["x"] for p in own)) / 2
    oy = (min(p["y"] for p in own) + max(p["y"] for p in own)) / 2
    best = None
    # Both drawings are seen from the top; only a part on the bottom side is mirrored in the file.
    for mirror in (False, True) if own_geo.get("bottom") else (False,):
        for deg in (0, 90, 180, 270):
            t = _turn(pads, deg, mirror)
            err = 0.0
            for p in t:
                q = min(own, key=lambda q: math.hypot(q["x"] - ox - p["x"], q["y"] - oy - p["y"]))
                err += math.hypot(q["x"] - ox - p["x"], q["y"] - oy - p["y"])
            err /= len(t)
            err += 0.02 * abs(len(t) - len(own)) + (0.001 if mirror else 0)
            if best is None or err < best[0] - 1e-9:
                best = (err, t)
    err, t = best
    # Numbers from the nearest user pad; the drawing is placed on the user's footprint's centre so it
    # can be laid on top of it.
    for p in t:
        q = min(own, key=lambda q: math.hypot(q["x"] - ox - p["x"], q["y"] - oy - p["y"]))
        p["num"] = q.get("num", "")
        p["x"] = round(p["x"] + ox, 3)
        p["y"] = round(p["y"] + oy, 3)
    return t, err


__all__ = ["read"]
