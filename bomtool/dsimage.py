"""Pictures from the datasheet: the recommended land pattern and the package outline, cut out
of the PDF page so they can be shown right under the footprint drawing.

Uses pypdfium2 (PDFium) when installed; without it the page itself is shown in the PDF viewer.
"""
import io

from . import datasheet, dsdata
from . import packages as P

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


def _find(doc, pages, words):
    """(page index, x, y from top in points) of the most specific heading found: every page is tried
    for the first word before the next, more general word is tried."""
    pages = [p for p in pages if 1 <= p <= len(doc)]
    tps = {}
    try:
        for w in words:
            for pno in pages:
                if pno not in tps:
                    tps[pno] = doc[pno - 1].get_textpage()
                found = tps[pno].search(w, match_case=False).get_next()
                if found:
                    left, _, _, top = tps[pno].get_charbox(found[0])
                    return pno - 1, left, doc[pno - 1].get_size()[1] - top
    finally:
        for tp in tps.values():
            tp.close()
    return None, None, None


def image(url, kind, fp_pkg=None):
    """PNG bytes of the land pattern ("land") or package outline ("outline") region, or None."""
    import pypdfium2 as pdfium  # noqa: PLC0415

    text = datasheet.text_for(url)
    data = datasheet.fetch(url)
    doc = pdfium.PdfDocument(data)
    try:
        order = dsdata.drawing_pages(text, fp_pkg)
        # Pages naming the footprint's package first, then the rest of the drawing pages, then everything.
        order += [p for p in range(1, len(doc) + 1) if p not in order]
        words = LAND if kind == "land" else OUTLINE
        idx, _, y = _find(doc, order, words)
        if idx is None:
            if not order:
                return None
            idx, y = order[0] - 1, 0
        page = doc[idx]
        h = page.get_size()[1]
        scale = 2.2
        img = page.render(scale=scale).to_pil()
        top = max(0, (y - 14) * scale)
        bottom = min(img.height, top + h * 0.5 * scale)
        crop = img.crop((0, int(top), img.width, int(bottom)))
        crop = _trim(crop)
        buf = io.BytesIO()
        crop.save(buf, "PNG", optimize=True)
        return buf.getvalue(), idx + 1
    finally:
        doc.close()


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
