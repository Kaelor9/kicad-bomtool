"""Pictures from the datasheet: the recommended land pattern and the package outline, cut out
of the PDF page so they can be shown right under the footprint drawing.

Uses pypdfium2 (PDFium) when installed; without it the page itself is shown in the PDF viewer.
"""
import io
import threading

from . import datasheet, dsdata
from . import packages as P

# PDFium is not thread-safe: two pictures rendered at once crash the whole process.
_PDFIUM = threading.Lock()

LAND = ("example board layout", "recommended land", "recommended pad", "recommended pcb", "recommended footprint",
        "suggested pad",
        "suggested footprint", "footprint recommendation", "land pattern", "pcb layout", "recommended solder", "footprint")
OUTLINE = ("package outline", "outline dimensions", "package dimensions", "package drawing", "mechanical data",
           "mechanical drawing", "dimensions")


def available():
    try:
        import pypdfium2  # noqa: F401, PLC0415
        import PIL  # noqa: F401, PLC0415
        return True
    except ImportError:
        return False


def _visible(img, box, h):
    """Is there ink where the text is? PDFs often carry invisible duplicates of their text."""
    l, bottom, r, top = box
    px = img.convert("L").load()
    for x in range(int(l), int(r) + 1):
        for y in range(int(h - top), int(h - bottom) + 1):
            if 0 <= x < img.width and 0 <= y < img.height and px[x, y] < 150:
                return True
    return False


def _find(doc, pages, words):
    """(page index, x, y from top in points) of every *visible* heading, most specific first: every page
    is tried for the first word before the next, more general word is tried."""
    pages = [p for p in pages if 1 <= p <= len(doc)]
    tps, imgs = {}, {}
    try:
        for w in words:
            for pno in pages:
                if pno not in tps:
                    tps[pno] = doc[pno - 1].get_textpage()
                tp = tps[pno]
                search = tp.search(w, match_case=False)
                while True:
                    found = search.get_next()
                    if not found:
                        break
                    if not _heading_line(tp, found, w, w == words[-1]):
                        continue
                    box = tp.get_charbox(found[0])
                    h = doc[pno - 1].get_size()[1]
                    if pno not in imgs:
                        imgs[pno] = doc[pno - 1].render(scale=1).to_pil()
                    if _visible(imgs[pno], box, h):
                        yield pno - 1, box[0], h - box[3]
    finally:
        for tp in tps.values():
            tp.close()


def _heading_line(tp, found, word, generic):
    """Is the match a heading? Not a line in the table of contents ("Outline Dimensions ..... 27"),
    not a sentence ("... mounted on an FR4 board, standard footprint."). The most general words
    ("footprint", "dimensions") must also start their line."""
    import re  # noqa: PLC0415
    i, n = found
    start = max(0, i - 80)
    text = tp.get_text_range(start, min(i + n + 80, tp.count_chars()) - start)
    k = i - start
    line = text[text.rfind("\n", 0, k) + 1:]
    nl = line.find("\n", k - (text.rfind("\n", 0, k) + 1))
    line = (line[:nl] if nl >= 0 else line).strip()
    if "...." in line or "…" in line or ". . ." in line or len(line) > 60:
        return False
    if re.search(r"[A-Za-z]\s+\d{1,3}$", line):     # "PCB Layout Recommendations 45": contents
        return False
    if generic:
        head = re.sub(r"^[\d.\s•·\-–]+", "", line).lower()
        return head.startswith(word) and len(line) <= 32
    return True


def _wordy(page, box):
    """Is this region of the page running text rather than a drawing? Drawings carry numbers and a
    few labels; a paragraph about solder fillets carries dozens of real words."""
    import re  # noqa: PLC0415
    l, t, r, b = box
    h = page.get_size()[1]
    tp = page.get_textpage()
    try:
        text = tp.get_text_bounded(left=l, bottom=h - b, right=r, top=h - t)
    finally:
        tp.close()
    words = len(re.findall(r"[A-Za-z]{4,}", text or ""))
    numbers = len(re.findall(r"\d+\.\d+|\d+", text or ""))
    return words > 40 and numbers < words


def _headings(doc, idx):
    """y (points from the top) of every land-pattern/outline heading on a page - where a drawing ends."""
    ys = []
    page = doc[idx]
    h = page.get_size()[1]
    tp = page.get_textpage()
    img = page.render(scale=1).to_pil()
    try:
        for w in LAND[:-1] + OUTLINE[:-1] + ("schematic", "ordering information", "tape and reel", "packaging",
                                            "marking", "notes"):
            search = tp.search(w, match_case=False)
            while True:
                found = search.get_next()
                if not found:
                    break
                box = tp.get_charbox(found[0])
                if _visible(img, box, h):
                    ys.append(h - box[3])
    finally:
        tp.close()
    return sorted(set(round(y, 1) for y in ys))


def _block_end(img, start, max_px, gap_px):
    """First row after `start` where a band of `gap_px` blank rows begins (after some content)."""
    gray = img.convert("L")
    w = gray.width
    px = gray.load()
    seen, blank = 0, 0
    for y in range(start, min(gray.height, start + max_px)):
        dark = any(px[x, y] < 200 for x in range(0, w, 3))
        if dark:
            seen += 1
            blank = 0
        else:
            blank += 1
            if seen > gap_px and blank >= gap_px:
                return y - blank
    return min(gray.height, start + max_px)


def _first_ink(img, start, max_px):
    """First row with ink at or below `start` (within max_px), or None."""
    gray = img.convert("L")
    px = gray.load()
    for y in range(start, min(gray.height, start + max_px)):
        if any(px[x, y] < 200 for x in range(0, gray.width, 3)):
            return y
    return None


def _block_start(img, end, max_px, gap_px):
    """Going up from `end`: the top of the block of content, where a band of `gap_px` blank rows begins."""
    gray = img.convert("L")
    w = gray.width
    px = gray.load()
    seen, blank = 0, 0
    for y in range(end, max(-1, end - max_px), -1):
        if any(px[x, y] < 200 for x in range(0, w, 3)):
            seen += 1
            blank = 0
        else:
            blank += 1
            if seen > gap_px and blank >= gap_px:
                return y + blank
    return max(0, end - max_px)


def image(url, kind, fp_pkg=None):
    """PNG bytes of the land pattern ("land") or package outline ("outline") drawing, or None."""
    text = datasheet.text_for(url)
    data = datasheet.fetch(url)
    with _PDFIUM:
        return _image(data, text, kind, fp_pkg)


def _image(data, text, kind, fp_pkg):
    import pypdfium2 as pdfium  # noqa: PLC0415

    doc = pdfium.PdfDocument(data)
    try:
        order = dsdata.drawing_pages(text, fp_pkg)
        # Pages naming the footprint's package first, then the rest of the drawing pages, then everything.
        order += [p for p in range(1, len(doc) + 1) if p not in order]
        words = LAND if kind == "land" else OUTLINE
        crop = None
        found = _find(doc, order, words)
        try:
            # The first few headings in turn: skip a "footprint" that only starts a paragraph of text.
            for _, (idx, x, y) in zip(range(8), found):
                crop = _cut(doc, idx, x, y, 2.2)
                if crop:
                    break
        finally:
            found.close()       # its text pages must close before the document does
        if not crop:
            return None
        buf = io.BytesIO()
        crop.save(buf, "PNG", optimize=True)
        return buf.getvalue(), idx + 1
    finally:
        doc.close()


def _cut(doc, idx, x, y, scale):
    """The drawing under the heading at (x, y), or None when that region is running text."""
    r = cut_region(doc, idx, x, y, scale)
    return r[0] if r else None


def cut_region(doc, idx, x, y, scale=2.2):
    """(picture, (left, top, right, bottom) in points from the page's top-left) of the drawing under
    the heading at (x, y), or None when that region is running text."""
    page = doc[idx]
    pw, h = page.get_size()
    img = page.render(scale=scale).to_pil()
    top = int(max(0, (y - 6) * scale))
    # Stop at the next heading below this one, or at the first wide blank band, or after 60 % of a page.
    nxt = [hy for hy in _headings(doc, idx) if hy > y + 25]
    limit = int(((min(nxt) - 4) * scale if nxt else img.height) - top)
    limit = max(40, min(limit, int(h * 0.6 * scale)))
    skip = int(18 * scale)          # the heading itself
    gap = int(h * 0.035 * scale)
    if _first_ink(img, top + skip, int(30 * scale)) is None and y > h * 0.25:
        # Nothing right under it: a caption below its figure ("Figure 11: ... Land Pattern").
        bottom = int((y + 14) * scale)
        top = _block_start(img, int((y - 4) * scale), int(h * 0.6 * scale), gap)
    else:
        bottom = _block_end(img, top + skip, max(20, limit - skip), gap)
    bottom = max(bottom, top + 40)
    left = 0
    # Heading in the right-hand column with an empty gutter to its left: keep only that column.
    if x and x > pw * 0.4:
        left = _gutter(img.crop((0, top, img.width, bottom)), int(pw * 0.25 * scale), int(x * scale) - 10, int(pw * 0.02 * scale)) or 0
    if _wordy(page, (left / scale, top / scale, pw, bottom / scale)):
        return None
    crop = _trim(img.crop((left, top, img.width, bottom)))
    # A heading with hardly anything under it (a table cell, a caption) is not the drawing.
    if crop.height < 50 * scale:
        return None
    return crop, (left / scale, top / scale, pw, bottom / scale)


def _gutter(img, x0, x1, min_w):
    """Right end of the right-most blank vertical band between x0 and x1, or None."""
    gray = img.convert("L")
    px = gray.load()
    blank = [all(px[x, y] >= 200 for y in range(0, gray.height, 2)) for x in range(max(0, x0), min(gray.width, x1))]
    run, best = 0, None
    for i, b in enumerate(blank):
        run = run + 1 if b else 0
        if run >= min_w:
            best = x0 + i
    return best


def _trim(img):
    """Cut away white margins."""
    from PIL import ImageChops, Image  # noqa: PLC0415
    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, (255, 255, 255))
    box = ImageChops.difference(rgb, bg).point(lambda v: 255 if v > 18 else 0).getbbox()
    if not box:
        return rgb
    l, t, r, b = box
    pad = 12
    return rgb.crop((max(0, l - pad), max(0, t - pad), min(rgb.width, r + pad), min(rgb.height, b + pad)))


def fp_package(footprint):
    return P.parse_package((footprint or "").split(":")[-1])


__all__ = ["available", "image", "fp_package", "cut_region", "LAND"]
