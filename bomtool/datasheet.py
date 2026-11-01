"""Datasheet check: download the PDF, pull out its text and look for package
names - preferably on the ordering-information line that names the MPN.

It reads text, not drawings: it can tell that the datasheet says "SOIC-8" for
this part, not that the land pattern drawing matches the footprint.
"""
import hashlib
import io
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from .net import urlopen
from . import packages as P
from .config import cache_dir

MAX_BYTES = 30 * 1024 * 1024
MAX_PAGES = 40
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kicad-bomtool/1.0"

# Package words as they appear in datasheets ("SOIC-8", "8-Pin SOIC", "SOIC (8)", "D (SOIC, 8)")
_FAMS = sorted(set(P.PINNED) | {"SOT-223", "SOT-89", "SOT-323", "SOT-353", "SOT-363", "SOT-563", "SC-88",
                                 "SC-59", "SOD-123", "SOD-323", "SOD-523", "TO-92", "TO-247", "TO-236",
                                 "SMA", "SMB", "SMC", "DPAK", "D2PAK", "MELF", "SOT-25", "SOT-26", "SOT-457",
                                 "SOT-753", "SC-74", "SC-74A", "SOT-416", "SOT-523", "SC-75", "SC-89"},
              key=len, reverse=True)
_FAM_RX = "|".join(re.escape(f).replace(r"\-", "-?") for f in _FAMS)
_PKG_RX = re.compile(
    r"(?<![A-Za-z0-9.+])(?:(\d{1,3})(?:\s*-\s*|\s*-?\s*(?:pin|lead|ld|ball)s?\s*-?\s*))?(" + _FAM_RX + r")"
    r"(?:\s*-\s*(\d{1,3})(?![\d.])|\s*\(\s*(\d{1,3})\s*\)|(\d{1,3})(?![\d.x]))?(?![A-Za-z])", re.I)
_TI_RX = re.compile(r"\(\s*(" + _FAM_RX + r")\s*,\s*(\d{1,3})\s*\)", re.I)   # D (SOIC, 8)


def _path(url, ext):
    d = os.path.join(cache_dir(), "datasheets")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, hashlib.sha1(("v2|" + url).encode()).hexdigest() + ext)


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,text/html;q=0.8,*/*;q=0.5"})
    with urlopen(req, timeout=30) as resp:
        data = resp.read(MAX_BYTES + 1)
        return data[:MAX_BYTES], resp.geturl()


def _datasheet_link(html, url, final):
    """A product page often links its datasheet PDF. Only follow a link that clearly is one:
    a redirect to the shop's front page, or a link to a certificate, must not count."""
    if urllib.parse.urlparse(final).path.strip("/") == "":
        return None
    ids = [t.lower() for t in re.findall(r"[A-Za-z0-9]{4,}", urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
           if re.search(r"\d", t) and t.lower() not in ("html", "product", "detail")]
    best = None
    for m in re.finditer(r"""(?:href|src|data-href)\s*=\s*["']([^"']+?\.pdf(?:[?#][^"']*)?)["']""", html, re.I):
        link = m.group(1).replace("&amp;", "&")
        low = link.lower()
        if re.search(r"certif|iso[-_ ]?\d|pci|policy|terms|catalog|brochure|conflict|rohs|reach", low):
            continue
        if any(i in low for i in ids):
            return urllib.parse.urljoin(final, link)
        if best is None and re.search(r"datasheet|data-sheet|/ds/|[_-]ds[_.-]", low):
            best = urllib.parse.urljoin(final, link)
    return best


def _readable(text):
    """Share of ordinary characters - garbled font encodings come out as noise."""
    sample = text[:20000]
    if not sample:
        return 0.0
    good = sum(1 for c in sample if c.isascii() and (c.isalnum() or c in " .,:;()-/%\n\t"))
    return good / len(sample)


def fetch(url):
    """Return the PDF bytes (cached on disk), or raise ValueError with a Danish reason."""
    if not re.match(r"https?://", url or "", re.I):
        raise ValueError("Ingen gyldig datablad-URL.")
    path = _path(url, ".pdf")
    if os.path.exists(path):
        with open(path, "rb") as fh:
            return fh.read()
    try:
        data, final = _get(url)
        if not data.lstrip()[:5] == b"%PDF-":
            link = _datasheet_link(data.decode("utf-8", "replace"), url, final)
            if not link:
                raise ValueError("Linket peger på en webside, ikke et PDF-datablad.")
            data, _ = _get(link)
            if not data.lstrip()[:5] == b"%PDF-":
                raise ValueError("Linket peger på en webside, ikke et PDF-datablad.")
    except urllib.error.HTTPError as e:
        raise ValueError(f"Kunne ikke hente databladet (HTTP {e.code}).")
    except (urllib.error.URLError, OSError) as e:
        raise ValueError(f"Kunne ikke hente databladet ({getattr(e, 'reason', e)}).")
    with open(path, "wb") as fh:
        fh.write(data)
    return data


def pdf_text(data):
    """Text of the first pages. Uses pypdf when installed, otherwise a simple built-in reader."""
    try:
        import logging
        import pypdf  # noqa: PLC0415 - optional dependency
        logging.getLogger("pypdf").setLevel(logging.ERROR)   # font warnings are noise here
        reader = pypdf.PdfReader(io.BytesIO(data))
        out, start = [], time.monotonic()
        for page in reader.pages[:MAX_PAGES]:
            if time.monotonic() - start > 20:   # huge drawing-heavy PDFs: the first pages are enough
                break
            try:
                out.append(page.extract_text() or "")
            except Exception:  # noqa: BLE001 - one broken page shouldn't stop the rest
                out.append("")  # keep page numbering
        text = "\f".join(out)   # form feed between pages, so a page can be found again
        if text.strip():
            return text
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - fall back to the simple reader
        pass
    return _simple_text(data)


_STR = rb"\((?:\\.|[^\\)])*\)"


def _unescape(s):
    s = s[1:-1]
    s = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 255]), s)
    s = re.sub(rb"\\(.)", lambda m: {b"n": b"\n", b"r": b"\r", b"t": b"\t"}.get(m.group(1), m.group(1)), s,
               flags=re.S)
    return s.decode("latin-1")


def _simple_text(data):
    """Good enough for PDFs with plain (non-CID) fonts: inflate the content
    streams and collect the strings drawn by Tj / TJ."""
    out, start = [], time.monotonic()
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        if time.monotonic() - start > 20:
            break
        raw = m.group(1)
        try:
            raw = zlib.decompress(raw)
        except zlib.error:
            pass
        if len(raw) > 2_000_000 or (b"Tj" not in raw and b"TJ" not in raw) or b"BT" not in raw:
            continue
        # One linear pass over the tokens; strings wait on a stack until their operator arrives.
        pending = []
        for tok in _TOK.finditer(raw):
            t = tok.group(0)
            c = t[:1]
            if c == b"(":
                pending.append(_unescape(t))
            elif c == b"[":
                pending = []
            elif c in b"-.0123456789":
                if pending and t not in (b"-", b".") and float(t) < -200:
                    pending.append(" ")
            elif t in (b"Tj", b"TJ", b"'", b'"'):
                out.append("".join(pending))
                pending = []
            elif t in (b"T*", b"Td", b"TD", b"ET"):
                out.append("\n")
                pending = []
            elif c.isalpha():
                pending = []
    return "".join(out)


_TOK = re.compile(rb"\((?:\\.|[^\\)])*\)|-?\d*\.?\d+|[A-Za-z]+\*?|['\"\[]", re.S)


def text_for(url):
    """Cached text of a datasheet."""
    path = _path(url, ".v3.txt")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    text = pdf_text(fetch(url))
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    return text


def packages_in(text):
    """Return [(parsed_package, line)] for every package name in the text."""
    found = []
    for line in text.splitlines():
        if len(line) > 400:
            line = line[:400]
        for m in _TI_RX.finditer(line):
            pkg = P.parse_package(f"{m.group(1)}-{m.group(2)}")
            if pkg:
                found.append((pkg, line))
        for m in _PKG_RX.finditer(line):
            fam = m.group(2)
            if re.search(r"\d$", fam):     # SOT-23-5, TO-220 (3): only an explicit suffix is a pin count
                pins = m.group(3) or m.group(4)
            else:
                pins = m.group(3) or m.group(4) or m.group(5) or m.group(1)
            pkg = P.parse_package(f"{fam}-{pins}" if pins else fam)
            if pkg and pkg["family"] != "CHIP":
                found.append((pkg, line))
    return found


def _key(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _mpn_lines(text, mpn):
    """Lines that name the MPN (or its base, with packaging/temperature suffixes cut off)."""
    full = _key(mpn)
    if len(full) < 4:
        return [], False
    lines = text.splitlines()
    hits = [l for l in lines if full in _key(l)]
    if hits:
        return hits, True
    # Ordering tables often list a base with the suffix in a separate column.
    for n in range(len(full) - 1, max(4, len(full) - 6) - 1, -1):
        base = full[:n]
        hits = [l for l in lines if base in _key(l)]
        if hits:
            return hits, False
    return [], False


def _label(pkg):
    return P.describe(pkg) or pkg["raw"]


def check(url, mpn, fp_pkg):
    """Compare the footprint's package with what the datasheet says.
    Returns a check dict {check, status, msg} (status ok/warn/mismatch/unknown)."""
    name = "Datablad"
    try:
        text = text_for(url)
    except ValueError as e:
        return {"check": name, "status": "unknown", "msg": str(e)}
    if len(text.strip()) < 200 or _readable(text) < 0.6:
        return {"check": name, "status": "unknown",
                "msg": "Databladets tekst kunne ikke læses (scannet eller specielle skrifttyper)."}
    if not fp_pkg:
        return {"check": name, "status": "unknown", "msg": "Footprintets pakke kunne ikke aflæses."}

    def fits(pkg):
        st, _ = P.compare(fp_pkg, pkg)
        return st in ("ok", "partial")

    # 1) The ordering line(s) for this MPN
    lines, exact = _mpn_lines(text, mpn) if mpn else ([], False)
    on_line = [pkg for line in lines for pkg, _ in packages_in(line)]
    if on_line:
        names = sorted({_label(p) for p in on_line})
        if any(fits(p) for p in on_line):
            return {"check": name, "status": "ok",
                    "msg": f"Databladet angiver {', '.join(names)} for {mpn} – passer med footprintet."}
        return {"check": name, "status": "mismatch" if exact else "warn",
                "msg": f"Databladet angiver {', '.join(names)} for {mpn}, men footprintet er "
                       f"{_label(fp_pkg)}." + ("" if exact else " (fundet ud fra grundnummeret – tjek bestillingstabellen)")}

    # 2) Packages mentioned anywhere in the datasheet
    allp = packages_in(text)
    if not allp:
        return {"check": name, "status": "unknown", "msg": "Ingen pakkenavne fundet i databladet."}
    counts = {}
    for pkg, _ in allp:
        counts[_label(pkg)] = counts.get(_label(pkg), 0) + 1
    names = [k for k, _ in sorted(counts.items(), key=lambda kv: -kv[1])][:6]
    if any(fits(p) for p, _ in allp):
        return {"check": name, "status": "ok",
                "msg": f"Footprintets pakke ({_label(fp_pkg)}) findes i databladet (nævner: {', '.join(names)})."}
    return {"check": name, "status": "warn",
            "msg": f"Databladet nævner {', '.join(names)} – ikke {_label(fp_pkg)}. Tjek at det er det rigtige datablad/pakke."}
