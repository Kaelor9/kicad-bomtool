"""Read any tabular file into a list of rows (lists of strings).

Handles CSV/TSV/semicolon files in any common encoding, .xlsx (openpyxl if
installed, otherwise a small built-in reader), "xls" files that are really
HTML tables (Mouser does this), and real .xls when xlrd is installed.
"""
import csv
import html
import io
import re
import zipfile
import xml.etree.ElementTree as ET


def read_table(name, data):
    """Return list of sheets; each sheet is a list of rows (lists of str)."""
    low = name.lower()
    head = data[:8]
    if head[:4] == b"PK\x03\x04":
        return _xlsx(data)
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return _xls(data)
    text = _decode(data)
    if re.search(r"<\s*(table|html)", text[:5000], re.I):
        return _html(text)
    if low.endswith((".xlsx", ".xlsm")):
        raise ValueError("Filen ligner ikke en gyldig Excel-fil.")
    return [_csv(text)]


def _decode(data):
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8-sig"), (b"\xff\xfe", "utf-16"), (b"\xfe\xff", "utf-16")):
        if data.startswith(bom):
            return data.decode(enc, errors="replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _csv(text):
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in ",;\t|"}
        delim = max(counts, key=counts.get)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    return [[c.strip() for c in r] for r in rows]


def _xlsx(data):
    try:
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheets = []
        for ws in wb.worksheets:
            rows = []
            for row in ws.iter_rows(values_only=True):
                rows.append(["" if v is None else _cell(v) for v in row])
            sheets.append(rows)
        return sheets
    except ImportError:
        return _xlsx_builtin(data)


def _cell(v):
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _xlsx_builtin(data):
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", ns):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % ns["m"])))
        sheets = []
        for name in sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml", n)):
            root = ET.fromstring(z.read(name))
            rows = []
            for r in root.iter("{%s}row" % ns["m"]):
                row = {}
                for c in r.findall("m:c", ns):
                    ref = c.get("r", "")
                    col = _col_index(re.sub(r"\d", "", ref)) if ref else len(row)
                    t = c.get("t")
                    v = c.find("m:v", ns)
                    if t == "s" and v is not None:
                        val = shared[int(v.text)]
                    elif t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter("{%s}t" % ns["m"]))
                    else:
                        val = v.text if v is not None else ""
                        try:
                            f = float(val)
                            val = str(int(f)) if f.is_integer() else val
                        except (TypeError, ValueError):
                            pass
                    row[col] = (val or "").strip()
                if row:
                    rows.append([row.get(i, "") for i in range(max(row) + 1)])
            sheets.append(rows)
        return sheets


def _col_index(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n - 1


def _xls(data):
    try:
        import xlrd
    except ImportError:
        raise ValueError("Gammelt .xls-format kræver pakken 'xlrd' (pip install xlrd). "
                         "Alternativt: gem filen som .xlsx eller .csv.")
    book = xlrd.open_workbook(file_contents=data)
    return [[[_cell(c) for c in sh.row_values(r)] for r in range(sh.nrows)] for sh in book.sheets()]


def _html(text):
    sheets = []
    for table in re.findall(r"<table.*?</table>", text, re.S | re.I):
        rows = []
        for tr in re.findall(r"<tr.*?</tr>", table, re.S | re.I):
            cells = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, re.S | re.I)
            rows.append([html.unescape(re.sub(r"<[^>]+>", " ", c)).strip() for c in cells])
        if rows:
            sheets.append(rows)
    return sheets
