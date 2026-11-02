"""A tidy Excel BOM: one row per line with everything known about it, the three checks in colour,
a purchase list per seller and the parts left out."""
import io

STATUS_TXT = {"ok": "OK", "warn": "Advarsel", "partial": "Delvis", "mismatch": "Fejl", "missing": "Mangler",
              "unknown": "Ukendt", "none": "–"}
ORDER = {"ok": 0, "none": 0, "unknown": 1, "partial": 1, "warn": 2, "missing": 3, "mismatch": 4}
FILL = {"ok": "E7F6EC", "warn": "FDF3E2", "partial": "FDF3E2", "mismatch": "FDEAEA", "missing": "FDEAEA",
        "unknown": "EEF1F5"}


def _worst(sts):
    return max(sts, key=lambda s: ORDER.get(s, 1)) if sts else "ok"


def checks(line, result, choice=None):
    """The three control statuses, worked out like the screen does."""
    cs = [c for c in (line.get("fp") or {}).get("checks", []) if c["check"] != "Datablad"]
    fp = _worst([c["status"] for c in cs]) if cs else (line.get("fp") or {}).get("status", "unknown")
    dc = next((c for c in (line.get("fp") or {}).get("checks", []) if c["check"] == "Datablad"), None)
    ds = dc["status"] if dc else ("none" if line.get("kind") or not line.get("datasheet") else "unknown")
    if choice:
        buy, why = "ok", f"Alternativ valgt: {choice.get('mpn')}"
    else:
        dists = [d["results"].get(line["id"]) for d in result.get("dist_boms", [])]
        dists = [m for m in dists if m]
        plan = line.get("plan")
        if dists:
            buy = _worst([m["status"] for m in dists])
            why = {"ok": "Matcher kurven", "missing": "Mangler i kurven"}.get(buy, "Afviger fra kurven")
        elif plan and plan["best"].get("impractical"):
            buy, why = "mismatch", f"Kun hel rulle ({plan['best']['qty']} stk.)"
        elif plan:
            s = plan["best"].get("stock")
            if s is not None and s < line.get("need_spare", line["qty"]):
                buy, why = ("warn", f"Kun {s} på lager") if s else ("mismatch", "Ikke på lager")
            else:
                buy, why = "ok", ""
        else:
            buy, why = "unknown", "Ingen indkøbsdata"
    return fp, ds, buy, why


def build_xlsx(result, choices=None):
    from openpyxl import Workbook  # noqa: PLC0415
    from openpyxl.styles import Alignment, Font, PatternFill  # noqa: PLC0415
    from openpyxl.utils import get_column_letter  # noqa: PLC0415

    choices = choices or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "BOM"
    head = ["Pos", "Antal pr. print", "Behov", "Referencer", "Værdi", "Beskrivelse", "Producent", "MPN", "Footprint",
            "Pakke", "Datablad", "Grosist", "Varenr.", "Køb (stk.)", "Stykpris", "Linjepris", "Valuta", "Lager",
            "Livscyklus", "1 Footprint", "2 Datablad", "3 Indkøb", "Bemærkninger"]
    ws.append(head)
    bold = Font(bold=True, color="FFFFFF")
    for c in ws[1]:
        c.font = bold
        c.fill = PatternFill("solid", fgColor="1F2937")
        c.alignment = Alignment(vertical="center", wrap_text=True)
    total = 0.0
    for pos, l in enumerate(result["lines"], 1):
        ch = choices.get(l["id"])
        plan = l.get("plan") or {}
        best = plan.get("best") or {}
        if ch:
            seller, sku, qty, unit, line_total, cur, stock = (ch.get("seller"), ch.get("sku"), ch.get("qty"),
                                                              ch.get("unit"), ch.get("price"), ch.get("currency"),
                                                              ch.get("stock"))
        elif best and not best.get("impractical"):
            seller, sku, qty, unit, line_total, cur, stock = (best.get("seller"), best.get("sku"), best.get("qty"),
                                                              best.get("unit"), best.get("total"), best.get("currency"),
                                                              best.get("stock"))
        else:
            seller = sku = qty = unit = line_total = cur = stock = None
        if line_total:
            total += line_total
        fp, ds, buy, why = checks(l, result, ch)
        notes = list(l.get("warnings") or [])
        notes += [f"{c['check']}: {c['msg']}" for c in (l.get("fp") or {}).get("checks", [])
                  if c["status"] in ("warn", "mismatch")]
        if why and buy != "ok":
            notes.append(why)
        if ch:
            notes.append(f"Erstatter {l.get('mpn') or l['value']} i indkøbet (KiCad-projektet er uændret).")
        lifecycle = ", ".join(sorted({a.get("lifecycle") for a in l.get("api") or [] if a.get("lifecycle")}))
        ws.append([pos, l["qty"], l.get("need_spare") or l.get("need") or l["qty"], ", ".join(l["refs"]),
                   l["value"] if l["value"] not in ("~", "") else "",
                   l.get("desc") or "", (ch or {}).get("mfr") or l.get("mfr") or "",
                   (ch or {}).get("mpn") or l.get("mpn") or "", l["footprint"].split(":")[-1],
                   (l.get("fp") or {}).get("part_pkg") or (l.get("fp") or {}).get("footprint_pkg") or "",
                   l.get("datasheet") or "", seller or "", sku or "", qty, unit, line_total, cur or "", stock, lifecycle,
                   STATUS_TXT.get(fp, fp), STATUS_TXT.get(ds, ds), STATUS_TXT.get(buy, buy), "\n".join(notes)])
        row = ws.max_row
        if l.get("datasheet", "").startswith("http"):
            cell = ws.cell(row=row, column=11)
            cell.hyperlink, cell.value, cell.font = l["datasheet"], "PDF", Font(color="2563EB", underline="single")
        for col, st in ((20, fp), (21, ds), (22, buy)):
            if st in FILL:
                ws.cell(row=row, column=col).fill = PatternFill("solid", fgColor=FILL[st])
        for col in (15, 16):
            ws.cell(row=row, column=col).number_format = "#,##0.00##"
        for c in ws[row]:
            c.alignment = Alignment(vertical="top", wrap_text=c.column in (4, 6, 23))
    ws.append([])
    ws.append(["", "", "", "", "", "", "", "", "", "", "", "", "", "", "I alt", round(total, 2)])
    ws.cell(row=ws.max_row, column=15).font = Font(bold=True)
    ws.cell(row=ws.max_row, column=16).font = Font(bold=True)
    widths = [5, 8, 7, 22, 12, 40, 18, 22, 26, 16, 9, 12, 24, 9, 10, 11, 7, 9, 12, 11, 11, 11, 60]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(head))}{len(result['lines']) + 1}"

    # Purchase list per seller - what to put in the cart
    buy = wb.create_sheet("Indkøb")
    buy.append(["Grosist", "Varenr.", "MPN", "Producent", "Antal", "Stykpris", "Linjepris", "Valuta", "Referencer"])
    for c in buy[1]:
        c.font = bold
        c.fill = PatternFill("solid", fgColor="1F2937")
    rows = []
    for l in result["lines"]:
        ch = choices.get(l["id"])
        b = ch or ((l.get("plan") or {}).get("best") or {})
        if not b or b.get("impractical") or not b.get("sku"):
            continue
        rows.append([b.get("seller"), b.get("sku"), (ch or {}).get("mpn") or l.get("mpn") or "",
                     (ch or {}).get("mfr") or l.get("mfr") or "", b.get("qty"), b.get("unit"),
                     b.get("price") if ch else b.get("total"), b.get("currency"), ", ".join(l["refs"])])
    for r in sorted(rows, key=lambda r: (r[0] or "", r[2])):
        buy.append(r)
    for i, w in enumerate([12, 28, 24, 20, 8, 10, 11, 7, 40], 1):
        buy.column_dimensions[get_column_letter(i)].width = w
    buy.freeze_panes = "A2"

    if result.get("excluded"):
        ex = wb.create_sheet("Udeladt")
        ex.append(["Reference", "Værdi", "Footprint", "Hvorfor"])
        for c in ex[1]:
            c.font = bold
            c.fill = PatternFill("solid", fgColor="1F2937")
        for e in result["excluded"]:
            ex.append([e["ref"], e.get("value", ""), e.get("footprint", ""), e.get("why", "")])
        for i, w in enumerate([12, 16, 40, 30], 1):
            ex.column_dimensions[get_column_letter(i)].width = w

    info = wb.create_sheet("Projekt")
    p = result["project"]
    for k, v in (("Projekt", p.get("name")), ("Komponenter", p.get("components")), ("BOM-linjer", len(result["lines"])),
                 ("Print", result["settings"].get("boards", 1)), ("I alt (valgt indkøb)", round(total, 2)),
                 ("KiCad skematik", f"{p['version'].get('sch')} ({p['version'].get('sch_generator')})"),
                 ("KiCad PCB", f"{p['version'].get('pcb')} ({p['version'].get('pcb_generator')})")):
        info.append([k, v])
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 40
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
