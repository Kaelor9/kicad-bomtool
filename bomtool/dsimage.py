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

LAND = ("example board layout", "recommended land", "recommended pcb", "recommended footprint", "suggested pad",
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
    """(page index, x, y from top in points) of the most specific *visible* heading: every page is
    tried for the first word before the next, more general word is tried."""
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
                    box = tp.get_charbox(found[0])
                    h = doc[pno - 1].get_size()[1]
                    if pno not in imgs:
                        imgs[pno] = doc[pno - 1].render(scale=1).to_pil()
                    if _visible(imgs[pno], box, h):
                        return pno - 1, box[0], h - box[3]
    finally:
        for tp in tps.values():
            tp.close()
    return None, None, None


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
        idx, x, y = _find(doc, order, words)
        if idx is None:
            if not order:
                return None
            idx, x, y = order[0] - 1, 0, 0
        page = doc[idx]
        h = page.get_size()[1]
        scale = 2.2
        img = page.render(scale=scale).to_pil()
        top = int(max(0, (y - 6) * scale))
        # Stop at the next heading below this one, or at the first wide blank band, or after 60 % of a page.
        nxt = [hy for hy in _headings(doc, idx) if hy > y + 25]
        limit = int(((min(nxt) - 4) * scale if nxt else img.height) - top)
        limit = max(40, min(limit, int(h * 0.6 * scale)))
        skip = int(18 * scale)          # the heading itself
        bottom = _block_end(img, top + skip, max(20, limit - skip), int(h * 0.035 * scale))
        crop = img.crop((0, top, img.width, max(bottom, top + 40)))
        # Heading in the right-hand column with an empty gutter to its left: keep only that column.
        if x and x > page.get_size()[0] * 0.4:
            left = _gutter(crop, int(page.get_size()[0] * 0.25 * scale), int(x * scale) - 10, int(page.get_size()[0] * 0.02 * scale))
            if left:
                crop = crop.crop((left, 0, crop.width, crop.height))
        crop = _trim(crop)
        buf = io.BytesIO()
        crop.save(buf, "PNG", optimize=True)
        return buf.getvalue(), idx + 1
    finally:
        doc.close()


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


__all__ = ["available", "image", "fp_package"]
