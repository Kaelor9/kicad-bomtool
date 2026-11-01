"""Earlier analyses, saved as JSON in the user's folder, and a diff between two of them."""
import gzip
import json
import os
import re
import time

from .config import app_dir

KEEP = 200


def _dir():
    d = os.path.join(app_dir(), "history")
    os.makedirs(d, exist_ok=True)
    return d


def save(result):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    name = re.sub(r"[^\w.-]+", "_", result["project"].get("name") or "projekt")[:60]
    hid = f"{stamp}_{name}"
    meta = {"id": hid, "time": time.strftime("%Y-%m-%d %H:%M"), "project": result["project"].get("name") or "",
            "lines": result["summary"]["lines"], "parts": result["summary"]["parts"],
            "status": result["summary"]["status"], "total": result["totals"].get("mix"),
            "boards": result["settings"].get("boards", 1)}
    with gzip.open(os.path.join(_dir(), hid + ".json.gz"), "wt", encoding="utf-8") as fh:
        json.dump({"meta": meta, "result": result}, fh, ensure_ascii=False,
                  default=lambda o: list(o) if isinstance(o, (set, tuple)) else str(o))
    _prune()
    return meta


def _prune():
    files = sorted(f for f in os.listdir(_dir()) if f.endswith(".json.gz"))
    for f in files[:-KEEP]:
        try:
            os.remove(os.path.join(_dir(), f))
        except OSError:
            pass


def _safe(hid):
    if not re.fullmatch(r"[\w.-]+", hid or ""):
        raise ValueError("Ugyldigt id.")
    path = os.path.join(_dir(), hid + ".json.gz")
    if not os.path.exists(path):
        raise ValueError("Analysen findes ikke længere.")
    return path


def entries():
    out = []
    for f in sorted(os.listdir(_dir()), reverse=True):
        if not f.endswith(".json.gz"):
            continue
        try:
            with gzip.open(os.path.join(_dir(), f), "rt", encoding="utf-8") as fh:
                # The meta block is written first, so a short read is enough.
                head = fh.read(4096)
            m = re.search(r'"meta":\s*(\{.*?\})\s*,\s*"result"', head, re.S)
            out.append(json.loads(m.group(1)) if m else {"id": f[:-8], "project": f[16:-8], "time": ""})
        except (OSError, ValueError, EOFError):
            continue
    return out


def load(hid):
    with gzip.open(_safe(hid), "rt", encoding="utf-8") as fh:
        return json.load(fh)


def delete(hid):
    os.remove(_safe(hid))


def _per_ref(result):
    out = {}
    for l in result["lines"]:
        for r in l["refs"]:
            out[r] = {"value": l["value"], "footprint": l["footprint"], "mpn": l.get("mpn") or "",
                      "mfr": l.get("mfr") or ""}
    for e in result.get("excluded", []):
        out.setdefault(e["ref"], {"value": e.get("value", ""), "footprint": e.get("footprint", ""),
                                  "mpn": "", "mfr": "", "excluded": e.get("why", "udeladt")})
    return out


def diff(old, new):
    """What changed from `old` to `new` (both analysis results), per reference."""
    a, b = _per_ref(old), _per_ref(new)
    names = {"value": "Værdi", "footprint": "Footprint", "mpn": "MPN", "mfr": "Producent"}
    added, removed, changed = [], [], []
    for ref in sorted(set(a) | set(b), key=_natkey):
        if ref not in a:
            if not b[ref].get("excluded"):
                added.append({"ref": ref, **b[ref]})
        elif ref not in b:
            if not a[ref].get("excluded"):
                removed.append({"ref": ref, **a[ref]})
        else:
            if bool(a[ref].get("excluded")) != bool(b[ref].get("excluded")):
                changed.append({"ref": ref, "field": "BOM",
                                "old": a[ref].get("excluded") or "med", "new": b[ref].get("excluded") or "med"})
            for k, label in names.items():
                if (a[ref].get(k) or "") != (b[ref].get(k) or ""):
                    changed.append({"ref": ref, "field": label, "old": a[ref].get(k) or "–", "new": b[ref].get(k) or "–"})
    return {"added": added, "removed": removed, "changed": changed,
            "total_old": old["totals"].get("mix"), "total_new": new["totals"].get("mix"),
            "parts_old": old["summary"]["parts"], "parts_new": new["summary"]["parts"]}


def _natkey(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]
