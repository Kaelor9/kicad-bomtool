"""Price-break optimisation: how many to buy, and from whom."""
import math


def need_for(line, settings):
    boards = max(1, int(settings.get("boards", 1) or 1))
    base = line["qty"] * boards
    pct = settings.get("spare_passive_pct", 10) if line.get("kind") else settings.get("spare_pct", 0)
    pct = float(pct or 0)
    spare = math.ceil(base * pct / 100) if pct > 0 else 0
    if pct > 0 and line.get("kind"):
        spare = max(spare, int(settings.get("spare_passive_min", 2) or 0))
    return base, base + spare


def unit_price(breaks, q):
    price = None
    for bq, bp in sorted(breaks):
        if q >= bq:
            price = bp
    return price


def _round_up(q, moq, mult):
    q = max(q, moq or 1)
    mult = max(1, mult or 1)
    if (q - (moq or 0)) % mult:
        q += mult - (q - (moq or 0)) % mult
    return q


def best_buy(offer, need, extra_budget_abs=5.0, extra_budget_pct=10.0):
    """Cheapest quantity >= need for one offer, plus 'buy more' suggestions."""
    breaks = [b for b in offer["breaks"] if b[1] is not None]
    if not breaks or need <= 0:
        return None
    moq, mult = offer.get("moq") or 1, offer.get("mult") or 1
    cands = {_round_up(need, moq, mult)}
    for bq, _ in breaks:
        if bq >= need:
            cands.add(_round_up(bq, moq, mult))
    priced = []
    for q in sorted(cands):
        up = unit_price(breaks, q)
        if up is None:
            continue
        priced.append((round(q * up, 4), q, up))
    if not priced:
        return None
    base_q = min(cands)
    base = next((p for p in priced if p[1] == base_q), None)
    cheapest = min(priced, key=lambda p: (p[0], -p[1]))
    out = {"qty": cheapest[1], "unit": cheapest[2], "total": cheapest[0], "seller": offer["seller"],
           "sku": offer.get("sku", ""), "packaging": offer.get("packaging", ""), "url": offer.get("url", ""),
           "currency": offer.get("currency", ""), "stock": offer.get("stock"), "moq": moq,
           "reel_fee": offer.get("reel_fee", False), "suggestions": []}
    if base and cheapest[1] > base[1]:
        out["suggestions"].append({
            "kind": "save", "qty": cheapest[1], "total": cheapest[0],
            "text": f"Køb {cheapest[1]} i stedet for {base[1]}: det koster {base[0] - cheapest[0]:.2f} mindre "
                    f"({base[0]:.2f} → {cheapest[0]:.2f}) og du får {cheapest[1] - base[1]} ekstra."})
    # Worth considering: much more for a little extra money.
    limit = max(extra_budget_abs, cheapest[0] * extra_budget_pct / 100)
    for total, q, up in priced:
        if q > cheapest[1] and q >= cheapest[1] * 2 and total - cheapest[0] <= limit:
            out["suggestions"].append({
                "kind": "consider", "qty": q, "total": total,
                "text": f"For kun {total - cheapest[0]:.2f} mere får du {q} stk. ({q - cheapest[1]} ekstra, "
                        f"{up:.4g}/stk.)."})
    if moq > need:
        out["note"] = f"Minimumskøb er {moq} stk."
    if out["stock"] is not None and isinstance(out["stock"], (int, float)) and out["stock"] < out["qty"]:
        out["note"] = (out.get("note", "") + f" Kun {int(out['stock'])} på lager.").strip()
    return out


def plan_line(offers, need, settings):
    """Evaluate every offer; return best overall and best per seller."""
    eb_abs = float(settings.get("extra_budget_abs", 5) or 0)
    eb_pct = float(settings.get("extra_budget_pct", 10) or 0)
    per_seller = {}
    for off in offers:
        b = best_buy(off, need, eb_abs, eb_pct)
        if not b:
            continue
        in_stock = not isinstance(b["stock"], (int, float)) or b["stock"] >= b["qty"]
        # A full reel of 2000 when you need 1 is not a real option, unless it costs next to nothing.
        if b["qty"] > max(need * 10, 100) and b["total"] > 50:
            b["impractical"] = True
            b["note"] = f"Kun hel rulle/pakning: mindst {b['moq']} stk. ({b['total']:.0f} {b['currency']})."
        # Digi-Reel has a reeling fee; only use it when nothing else exists.
        key = (1 if b.get("impractical") else 0, 0 if in_stock else 1, 1 if b["reel_fee"] else 0, b["total"])
        cur = per_seller.get(off["seller"])
        if cur is None or key < cur[0]:
            per_seller[off["seller"]] = (key, b)
    if not per_seller:
        return None
    ranked = sorted(per_seller.values(), key=lambda kb: kb[0])
    return {"best": ranked[0][1], "per_seller": {s: kb[1] for s, kb in per_seller.items()}}


def consolidate(lines, shipping):
    """Fewer sellers when the freight saved is worth more than the extra part cost.
    Moves every line of a seller to the other sellers in use, if that is cheaper in total,
    and repeats until nothing improves. Changes plan["best"] in place; returns a summary."""
    if not shipping or shipping <= 0:
        return None
    priced = [l for l in lines if l.get("plan") and not l["plan"]["best"].get("impractical")]

    def usable(l, s):
        b = l["plan"]["per_seller"].get(s)
        return b if b and not b.get("impractical") else None

    def cost(assign):
        return sum(usable(l, assign[l["id"]])["total"] for l in priced) + shipping * len(set(assign.values()))

    assign = {l["id"]: l["plan"]["best"]["seller"] for l in priced}
    start = cost(assign)
    improved = True
    while improved:
        improved = False
        for s in sorted(set(assign.values()), key=lambda s: sum(1 for v in assign.values() if v == s)):
            others = set(assign.values()) - {s}
            trial = dict(assign)
            ok = True
            for l in priced:
                if assign[l["id"]] != s:
                    continue
                alts = [(usable(l, o)["total"], o) for o in others if usable(l, o)]
                if not alts:
                    ok = False
                    break
                trial[l["id"]] = min(alts)[1]
            if ok and others and cost(trial) < cost(assign) - 0.005:
                assign, improved = trial, True
                break
    moved = 0
    for l in priced:
        s = assign[l["id"]]
        if s != l["plan"]["best"]["seller"]:
            moved += 1
            b = dict(usable(l, s))
            b["suggestions"] = list(b.get("suggestions") or []) + [{
                "kind": "consider", "qty": b["qty"], "total": b["total"],
                "text": f"Købes hos {s} i stedet for {l['plan']['best']['seller']}: lidt dyrere her, men det sparer fragt."}]
            l["plan"]["best"] = b
    end = cost(assign)
    return {"sellers": sorted(set(assign.values())), "shipping": shipping, "moved": moved,
            "saved": round(start - end, 2), "total_with_shipping": round(end, 2)}


def totals(lines):
    """Cart totals: cheapest mix, and each seller alone (where it has everything)."""
    mix, per_seller, covered = 0.0, {}, {}
    count = unbuyable = 0
    for line in lines:
        plan = line.get("plan")
        if not plan:
            continue
        if plan["best"].get("impractical"):
            unbuyable += 1     # only full reels: kept out of the totals, it needs an alternative
            continue
        count += 1
        mix += plan["best"]["total"]
        for s, b in plan["per_seller"].items():
            if b.get("impractical"):
                continue
            per_seller[s] = per_seller.get(s, 0) + b["total"]
            covered[s] = covered.get(s, 0) + 1
    return {"mix": round(mix, 2), "lines_priced": count, "lines_unbuyable": unbuyable,
            "per_seller": {s: {"total": round(v, 2), "lines": covered[s]} for s, v in per_seller.items()}}
