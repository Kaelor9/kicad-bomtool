"""End-to-end test against the KiCad demo projects, with a fake distributor API.

Run:  python -m tests.test_pipeline   (from the project folder)
"""
import io
import json
import os
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bomtool import analyze, kicad  # noqa: E402
from bomtool import fields as F  # noqa: E402

DEMOS = None
for base in kicad.kicad_install_footprint_dirs():
    cand = os.path.join(os.path.dirname(base), "demos")
    if os.path.isdir(cand):
        DEMOS = cand
        break


def zip_dir(path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for root, _, files in os.walk(path):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.relpath(p, os.path.dirname(path)))
    return buf.getvalue()


class FakeProvider:
    """Behaves like DigiKey: knows every MPN, returns price breaks and a package."""
    name = "DigiKey"

    def _part(self, mpn, desc="", package="", value=None, kind=None):
        breaks = [[1, 1.20], [10, 0.62], [100, 0.18], [1000, 0.07]]
        params = {"Package / Case": package}
        if value:
            params[{"R": "Resistance", "C": "Capacitance", "L": "Inductance"}[kind]] = value
        return {"source": self.name, "mpn": mpn, "mfr": "TestCo", "desc": desc or f"Part {mpn}",
                "package": package, "datasheet": f"https://example.com/{mpn}.pdf", "url": "",
                "stock": 5000, "category": "", "lifecycle": "Active", "params": params, "dist_pn": mpn + "-ND",
                "offers": [{"seller": self.name, "sku": mpn + "-ND", "packaging": "Cut Tape", "moq": 1, "mult": 1,
                            "stock": 5000, "currency": "DKK", "breaks": breaks, "url": "", "reel_fee": False}]}

    def lookup(self, pn):
        pn = pn.replace("-ND", "")
        hint = None
        from bomtool.packages import mpn_chip_hint, CHIP_IMP_TO_MET
        hint = mpn_chip_hint(pn)
        pkg = f"{hint} ({CHIP_IMP_TO_MET[hint]} Metric)" if hint else ""
        if pn == "0402WGF1003TCE":
            return [self._part(pn, "RES 100K OHM 1% 1/16W 0402", pkg, "100 kOhms", "R")]
        return [self._part(pn, package=pkg)]

    def search(self, keywords, limit=10, exact_first=None):
        # Return a few candidates: one matching, one wrong value, one wrong package
        words = keywords.split()
        if words[0] not in ("resistor", "capacitor", "inductor"):
            # Similar-function search for ICs: one in another package, one in a common one
            return [self._part("SIMILAR-SOT23", "similar part", "SOT-23-5"),
                    self._part("SIMILAR-SOIC8", "similar part", "8-SOIC (0.154\", 3.90mm Width)")]
        kind = {"resistor": "R", "capacitor": "C", "inductor": "L"}[words[0]]
        val, chip = words[1], words[-1]
        from bomtool.packages import CHIP_IMP_TO_MET
        mk = lambda mpn, v, c: self._part(mpn, f"{words[0]} {v} {c}", f"{c} ({CHIP_IMP_TO_MET.get(c, '')} Metric)",
                                          v, kind)
        good = mk("GOOD-" + val + "-" + chip, val, chip)
        good["offers"][0]["breaks"] = [[1, 0.5], [10, 0.1], [100, 0.02]]
        return [mk("WRONGVAL", "999k" if kind == "R" else "999u", chip), mk("WRONGPKG", val, "1206"), good]

    def substitutes(self, pn):
        return [{"mpn": pn + "-ALT", "mfr": "OtherCo", "desc": "drop-in?", "type": "Direct", "source": self.name}]


def main():
    assert DEMOS, "KiCad demos not found"
    analyze.make_providers = lambda cfg: [FakeProvider()]
    proj = zip_dir(os.path.join(DEMOS, "stickhub"))
    dist_csv = (
        "Mouser No:;Mfr. No:;Description;Order Qty.;Price (DKK);Ext.: (DKK)\n"
        "603-RC0402FR-0710KL;0402WGF1003TCE;RES 100K 0402;5;0,62 kr.;3,10 kr.\n"
        "81-GRM188R61A226ME5D;GRM188R61A226ME15D;MLCC 22uF 10V X5R 0603;1;1,20 kr.;1,20 kr.\n"
        "999-EXTRA;NOT-IN-PROJECT;Something extra;3;2,00 kr.;6,00 kr.\n"
    ).encode("cp1252")
    settings = {"boards": 2, "spare_passive_pct": 10, "spare_passive_min": 2, "use_api": True,
                "check_datasheets": False}  # no network in tests
    msgs = []
    a = analyze.Analysis([("stickhub.zip", proj)], [("mouser_cart.csv", dist_csv)], [], settings, {},
                         lambda m, p: msgs.append((p, m)))
    res = a.run()
    print("progress steps:", len(msgs), msgs[-1])
    print("project:", res["project"]["name"], res["project"]["components"], "comps,", len(res["lines"]), "lines")
    print("summary:", json.dumps(res["summary"], ensure_ascii=False))
    print("totals:", res["totals"])
    print("errors:", res["errors"])
    d = res["dist_boms"][0]
    print("dist:", d["distributor"], d["currency"], d["columns"], "extras:", [e["mpn"] for e in d["extras"]])
    for r in list(d["results"].values()):
        if r["status"] != "missing":
            print("  match", r["id"], r["status"], r["how"], r.get("qty_msg"), r["issues"])
    by = {l["id"]: l for l in res["lines"]}
    for lid in list(by)[:3] + ["C11"]:
        l = by.get(lid)
        if not l:
            continue
        p = l["plan"]["best"] if l.get("plan") else None
        print(f"line {lid}: qty={l['qty']} need={l['need']}/{l['need_spare']} mpn={l['mpn']} status={l['status']}")
        print("   fp:", l["fp"]["status"], [(c["check"], c["status"]) for c in l["fp"]["checks"]])
        print("   buy:", p and (p["qty"], p["unit"], p["total"], [s["text"] for s in p["suggestions"]]))
        print("   warn:", l["warnings"])
    # alternatives
    cap = next(l for l in res["lines"] if l["kind"] == "C" and l.get("parsed"))
    alt = analyze.run_alternatives(res, cap["id"], {}, settings)
    print("alt", cap["id"], cap["value"], alt["note"], [(i["mpn"], i["price"]) for i in alt["items"]])
    for l in res["lines"]:
        if not l["mpn"] or l.get("suggested"):
            print("no-mpn line", l["id"], l["value"], l["footprint"], "suggested:",
                  [s["mpn"] for s in l.get("suggested", [])], l.get("suggested_note"))
    line = next(l for l in res["lines"] if l["kind"] is None and l["mpn"])
    alt = analyze.run_alternatives(res, line["id"], {}, settings)
    print("alt", line["id"], alt["note"], [(i["mpn"], i.get("relation"), i.get("fit"), i.get("group")) for i in alt["items"]])
    # history: save, change a part, diff
    import copy
    import tempfile
    os.environ["BOMTOOL_HOME"] = tempfile.mkdtemp()
    from bomtool import history
    meta = history.save(res)
    newer = copy.deepcopy(res)
    newer["lines"][0]["mpn"] = "CHANGED-123"
    newer["lines"][1]["refs"] = newer["lines"][1]["refs"][1:]
    d = history.diff(history.load(meta["id"])["result"], newer)
    print("history:", [e["id"] for e in history.entries()], "changed:", d["changed"][:1], "removed:",
          [x["ref"] for x in d["removed"]])
    assert d["changed"] and d["changed"][0]["new"] == "CHANGED-123"
    json.dumps(res, default=list)  # must be serialisable
    # no-MPN passive gets a suggestion
    print("value parse sanity:", F.parse_value("4k7 1%", "R"))
    print("OK")


if __name__ == "__main__":
    main()
