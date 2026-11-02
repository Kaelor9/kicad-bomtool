// Renders a KiCad footprint as a small technical drawing: hatched copper pads, the
// component outline, an optional reference land pattern (datasheet / library, dashed)
// and dimension lines for pad size, pitch and row spacing.
(function () {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const r3 = v => String(Math.round(v * 1000) / 1000);
  let uid = 0;

  function padBox(p) {
    const a = ((p.angle || 0) % 180) * Math.PI / 180;
    const c = Math.abs(Math.cos(a)), s = Math.abs(Math.sin(a));
    return [(p.w * c + p.h * s) / 2, (p.w * s + p.h * c) / 2];
  }

  function padShape(p, cls, fill) {
    const t = `rotate(${-(p.angle || 0)} ${p.x} ${p.y})`;
    const f = fill ? ` fill="${fill}"` : "";
    if (p.shape === "circle") return `<circle class="${cls}"${f} cx="${p.x}" cy="${p.y}" r="${p.w / 2}"/>`;
    let rx = 0;
    if (p.shape === "oval") rx = Math.min(p.w, p.h) / 2;
    else if (p.shape === "roundrect") rx = Math.min(p.w, p.h) * (p.rratio || 0.25);
    return `<rect class="${cls}"${f} x="${p.x - p.w / 2}" y="${p.y - p.h / 2}" width="${p.w}" height="${p.h}" rx="${rx}" transform="${t}"/>`;
  }

  function arcPath(g) {
    const [ax, ay, bx, by, cx, cy] = [g.x1, g.y1, g.xm, g.ym, g.x2, g.y2];
    const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
    if (Math.abs(d) < 1e-9) return `M${ax} ${ay}L${cx} ${cy}`;
    const ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d;
    const uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d;
    const r = Math.hypot(ax - ux, ay - uy);
    const cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
    const sweep = cross > 0 ? 1 : 0;
    const a1 = Math.atan2(ay - uy, ax - ux), a3 = Math.atan2(cy - uy, cx - ux);
    const norm = x => (x + 4 * Math.PI) % (2 * Math.PI);
    const span = sweep ? norm(a3 - a1) : norm(a1 - a3);
    return `M${ax} ${ay}A${r} ${r} 0 ${span > Math.PI ? 1 : 0} ${sweep} ${cx} ${cy}`;
  }

  function graphic(g) {
    if (g.l !== "fab" && g.l !== "silk") return "";
    const cls = g.l === "fab" ? "g-fab" : "g-silk";
    if (g.k === "line") return `<line class="${cls}" x1="${g.x1}" y1="${g.y1}" x2="${g.x2}" y2="${g.y2}"/>`;
    if (g.k === "rect") return `<rect class="${cls}" x="${Math.min(g.x1, g.x2)}" y="${Math.min(g.y1, g.y2)}" width="${Math.abs(g.x2 - g.x1)}" height="${Math.abs(g.y2 - g.y1)}" fill="none"/>`;
    if (g.k === "circle") return `<circle class="${cls}" cx="${g.x1}" cy="${g.y1}" r="${Math.hypot(g.x2 - g.x1, g.y2 - g.y1)}" fill="none"/>`;
    if (g.k === "arc") return `<path class="${cls}" d="${arcPath(g)}" fill="none"/>`;
    if (g.k === "poly") return `<polygon class="${cls}" points="${g.pts.map(p => p.join(",")).join(" ")}" fill="none"/>`;
    return "";
  }

  function bounds(pads, graphics, body) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    const add = (x, y) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); };
    for (const p of pads) { const [ex, ey] = padBox(p); add(p.x - ex, p.y - ey); add(p.x + ex, p.y + ey); }
    for (const g of graphics) {
      if (g.l !== "fab") continue;
      if (g.pts) g.pts.forEach(p => add(p[0], p[1]));
      else if (g.k !== "circle") { add(g.x1, g.y1); add(g.x2, g.y2); }
    }
    if (body) { add(-body.w / 2, -body.h / 2); add(body.w / 2, body.h / 2); }
    if (!isFinite(x0)) return [-1, -1, 2, 2];
    return [x0, y0, x1 - x0, y1 - y0];
  }

  // ---- dimensions ------------------------------------------------------------------
  // A dimension: two feature points (on the copper), the direction it measures ("h"/"v"),
  // which side of the drawing it goes on, and how many steps out from the copper.
  function autoDims(pads) {
    const reg0 = pads.filter(p => p.num !== "" && p.type !== "np_thru_hole");
    if (reg0.length < 2 || reg0.length > 60) return [];
    const area = p => { const [ex, ey] = padBox(p); return ex * ey; };
    const med = reg0.map(area).sort((a, b) => a - b)[Math.floor(reg0.length / 2)];
    const reg = reg0.filter(p => area(p) <= 3 * med);
    const ep = reg0.filter(p => area(p) > 3 * med);
    // Which way do the pad rows face? Pads stretched along x sit in left/right columns.
    let col = 0, row = 0;
    for (const p of reg) { const [ex, ey] = padBox(p); if (ex > ey * 1.1) col++; else if (ey > ex * 1.1) row++; else if (Math.abs(p.x) >= Math.abs(p.y)) col++; else row++; }
    const X = col >= row;                       // true: columns at left/right, measure across in x
    const A = p => X ? p.x : p.y, O = p => X ? p.y : p.x;          // across / along
    const eA = p => padBox(p)[X ? 0 : 1], eO = p => padBox(p)[X ? 1 : 0];
    const pt = (a, o) => X ? [a, o] : [o, a];
    const dir = X ? "h" : "v", odir = X ? "v" : "h";
    const sides = X ? ["below", "above", "left", "right"] : ["right", "left", "above", "below"];
    const out = [];
    const neg = reg.filter(p => A(p) < -0.01), pos = reg.filter(p => A(p) > 0.01);
    const lo = Math.min(...reg.map(p => A(p) - eA(p))), hi = Math.max(...reg.map(p => A(p) + eA(p)));
    const oMax = Math.max(...reg.map(p => O(p) + eO(p))), oMin = Math.min(...reg.map(p => O(p) - eO(p)));
    const p1 = reg.find(p => p.num === "1" || p.num === "A1") || reg[0];
    // 1. outer span
    out.push({ a: pt(lo, oMax), b: pt(hi, oMax), d: dir, side: sides[0], level: 1, text: r3(hi - lo) });
    if (neg.length && pos.length) {
      // 2. gap between the rows
      const g1 = Math.max(...neg.map(p => A(p) + eA(p))), g2 = Math.min(...pos.map(p => A(p) - eA(p)));
      if (g2 - g1 > 0.05) out.push({ a: pt(g1, oMin), b: pt(g2, oMin), d: dir, side: sides[1], level: 1, text: r3(g2 - g1) });
    }
    // 3. pad length (across) on pin 1
    out.push({ a: pt(A(p1) - eA(p1), O(p1) - eO(p1)), b: pt(A(p1) + eA(p1), O(p1) - eO(p1)), d: dir, side: sides[1], level: 2, text: r3(2 * eA(p1)) });
    // 4. pitch from pin 1 to its neighbour in the same row
    const nb = reg.filter(q => q !== p1 && Math.abs(A(q) - A(p1)) < 0.05).sort((q1, q2) => Math.abs(O(q1) - O(p1)) - Math.abs(O(q2) - O(p1)))[0];
    const edgeSide = A(p1) <= 0 ? sides[2] : sides[3];
    // (extension lines start at the outer pad edge, on the pad centre line)
    const outer = p => A(p) <= 0 ? A(p) - eA(p) : A(p) + eA(p);
    if (nb) out.push({ a: pt(outer(p1), O(p1)), b: pt(outer(nb), O(nb)), d: odir, side: edgeSide, level: 1, text: r3(Math.abs(O(nb) - O(p1))) });
    // 5. pad width (along) on pin 1
    out.push({ a: pt(A(p1), O(p1) - eO(p1)), b: pt(A(p1), O(p1) + eO(p1)), d: odir, side: edgeSide, level: nb ? 2 : 1, text: r3(2 * eO(p1)) });
    // 6. exposed pad
    if (ep.length === 1) {
      const e = ep[0], [ex, ey] = padBox(e);
      out.push({ a: [e.x - ex, e.y + ey], b: [e.x + ex, e.y + ey], d: "h", side: "below", level: 2, text: r3(2 * ex) });
      out.push({ a: [e.x + ex, e.y - ey], b: [e.x + ex, e.y + ey], d: "v", side: "right", level: 2, text: r3(2 * ey) });
    }
    return out;
  }

  function drawDims(dims, box, unit, font) {
    const [bx, by, bw, bh] = box;
    const step = font * 2.3, gap = unit * 0.8, over = unit * 1.2, ah = font * 0.55, aw = font * 0.22;
    const parts = [];
    for (const d of dims) {
      const lvl = d.level * step;
      let line, ext, label;
      if (d.d === "h") {
        const y = d.side === "above" ? by - lvl : by + bh + lvl;
        const [x1, x2] = [Math.min(d.a[0], d.b[0]), Math.max(d.a[0], d.b[0])];
        line = [x1, y, x2, y];
        ext = [[d.a[0], d.a[1], d.a[0], y], [d.b[0], d.b[1], d.b[0], y]];
        label = [(x1 + x2) / 2, y - font * 0.55];
      } else {
        const x = d.side === "left" ? bx - lvl : bx + bw + lvl;
        const [y1, y2] = [Math.min(d.a[1], d.b[1]), Math.max(d.a[1], d.b[1])];
        line = [x, y1, x, y2];
        ext = [[d.a[0], d.a[1], x, d.a[1]], [d.b[0], d.b[1], x, d.b[1]]];
        label = [x, (y1 + y2) / 2];
      }
      for (const [x1, y1, x2, y2] of ext) {
        // extension line: from just off the copper to just past the dimension line
        const len = Math.hypot(x2 - x1, y2 - y1) || 1, ux = (x2 - x1) / len, uy = (y2 - y1) / len;
        parts.push(`<line class="ext" x1="${x1 + ux * gap}" y1="${y1 + uy * gap}" x2="${x2 + ux * over}" y2="${y2 + uy * over}"/>`);
      }
      const [x1, y1, x2, y2] = line;
      const len = Math.hypot(x2 - x1, y2 - y1);
      parts.push(`<line class="dim" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>`);
      const ux = (x2 - x1) / (len || 1), uy = (y2 - y1) / (len || 1), inside = len > ah * 2.6 ? 1 : -1;
      for (const [px, py, s] of [[x1, y1, 1], [x2, y2, -1]]) {
        const tx = px + ux * ah * s * inside, ty = py + uy * ah * s * inside;
        parts.push(`<polygon class="arrow" points="${px},${py} ${tx - uy * aw},${ty + ux * aw} ${tx + uy * aw},${ty - ux * aw}"/>`);
      }
      const t = esc(d.text);
      if (d.d === "h") parts.push(`<text class="dimt" x="${label[0]}" y="${label[1]}">${t}</text>`);
      else parts.push(`<text class="dimt" x="${label[0] - font * 0.55}" y="${label[1]}" transform="rotate(-90 ${label[0] - font * 0.55} ${label[1]})">${t}</text>`);
    }
    return parts.join("");
  }

  window.renderFootprint = function (geo, refPads, opts = {}) {
    if (!geo || !geo.pads) return `<div class="empty">Ingen footprint-geometri</div>`;
    const id = "fp" + (++uid);
    const pads = geo.pads.filter(p => p.type !== "np_thru_hole" || p.w > 0);
    const graphics = geo.graphics || [];
    const box = bounds(pads.concat(refPads || []), graphics, opts.refBody);
    let [x, y, w, h] = box;
    const size = Math.max(w, h, 1);
    const unit = size / 100;
    const font = Math.max(size * 0.042, 0.1);
    const dims = opts.dims ? autoDims(pads) : [];
    const levels = { above: 0, below: 0, left: 0, right: 0 };
    dims.forEach(d => { levels[d.side] = Math.max(levels[d.side], d.level); });
    const step = font * 2.3, pad = font * 1.2;
    x -= levels.left * step + pad + (levels.left ? font : 0);
    y -= levels.above * step + pad + (levels.above ? font : 0);
    w += (levels.left + levels.right) * step + 2 * pad + (levels.left ? font : 0) + (levels.right ? font : 0);
    h += (levels.above + levels.below) * step + 2 * pad + (levels.above ? font : 0) + (levels.below ? font : 0) + font * 1.6;
    const parts = [];
    parts.push(`<defs><pattern id="${id}h" patternUnits="userSpaceOnUse" width="${unit * 2.2}" height="${unit * 2.2}" patternTransform="rotate(45)">
        <rect width="${unit * 2.2}" height="${unit * 2.2}" fill="var(--pad-bg)"/><line x1="0" y1="0" x2="0" y2="${unit * 2.2}" stroke="var(--pad)" stroke-width="${unit * 0.55}"/></pattern></defs>
      <style>
      #${id} .g-fab{stroke:var(--fab);stroke-width:${unit * 0.45};fill:none}
      #${id} .g-silk{stroke:var(--silk);stroke-width:${unit * 0.35};fill:none;opacity:.55}
      #${id} .pad{stroke:var(--pad);stroke-width:${unit * 0.5}}
      #${id} .ref{fill:var(--ref-bg);stroke:var(--ref);stroke-width:${unit * 0.55};stroke-dasharray:${unit * 1.6} ${unit * 0.9}}
      #${id} .refbody{fill:none;stroke:var(--ref);stroke-width:${unit * 0.35};stroke-dasharray:${unit * 0.6} ${unit * 0.8}}
      #${id} .bad{fill:none;stroke:var(--bad);stroke-width:${unit * 0.8}}
      #${id} .drill{fill:var(--surface2);stroke:var(--pad);stroke-width:${unit * 0.3}}
      #${id} .pn{fill:var(--text);font:600 ${font}px system-ui,sans-serif;text-anchor:middle;dominant-baseline:central;paint-order:stroke;stroke:var(--surface2);stroke-width:${unit * 0.9}}
      #${id} .dim,#${id} .ext{stroke:var(--dim);stroke-width:${unit * 0.28}}
      #${id} .ext{opacity:.7}
      #${id} .arrow{fill:var(--dim)}
      #${id} .dimt{fill:var(--dim);font:500 ${font}px ui-monospace,Consolas,monospace;text-anchor:middle;dominant-baseline:auto}
      #${id} .scale{fill:var(--muted);font:${font * 0.85}px system-ui,sans-serif;text-anchor:middle}
    </style>`);
    graphics.forEach(g => parts.push(graphic(g)));
    if (opts.refBody) parts.push(`<rect class="refbody" x="${-opts.refBody.w / 2}" y="${-opts.refBody.h / 2}" width="${opts.refBody.w}" height="${opts.refBody.h}"/>`);
    const badPads = new Set((opts.details || []).map(d => d.pad));
    pads.forEach(p => {
      parts.push(padShape(p, "pad", `url(#${id}h)`));
      if (p.drill) parts.push(`<circle class="drill" cx="${p.x}" cy="${p.y}" r="${p.drill / 2}"/>`);
    });
    (refPads || []).forEach(p => parts.push(padShape(p, "ref")));
    pads.forEach(p => { if (badPads.has(p.num)) parts.push(padShape(Object.assign({}, p, { w: p.w + unit * 2, h: p.h + unit * 2 }), "bad")); });
    if (pads.length <= 120) {
      pads.forEach(p => {
        if (!p.num) return;
        const fs = Math.min(font, Math.min(p.w, p.h) * 0.75);
        parts.push(`<text class="pn" x="${p.x}" y="${p.y}" style="font-size:${fs}px">${esc(p.num)}</text>`);
      });
    }
    const p1 = pads.find(p => p.num === "1" || p.num === "A1");
    if (p1) {
      const [ex, ey] = padBox(p1);
      parts.push(`<circle cx="${p1.x - ex - unit * 2}" cy="${p1.y - ey - unit * 2}" r="${unit * 1.1}" fill="var(--bad)"/>`);
    }
    parts.push(drawDims(dims, box, unit, font));
    if (opts.scaleBar !== false) {
      const len = [0.5, 1, 2, 5, 10, 20, 50].find(v => v >= size / 5) || 1;
      const sx = x + pad, sy = y + h - font * 0.6;
      parts.push(`<line x1="${sx}" y1="${sy}" x2="${sx + len}" y2="${sy}" stroke="var(--muted)" stroke-width="${unit * 0.5}"/>`);
      parts.push(`<text class="scale" x="${sx + len / 2}" y="${sy - font * 0.35}">${len} mm</text>`);
    }
    return `<svg id="${id}" viewBox="${x} ${y} ${w} ${h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Footprint">${parts.join("")}</svg>`;
  };
})();
