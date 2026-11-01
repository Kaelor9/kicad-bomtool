// Renders a KiCad footprint (pads + fab/silk outline) as SVG, optionally with a
// reference footprint drawn on top as a dashed outline.
(function () {
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function padBox(p) {
    const a = ((p.angle || 0) % 180) * Math.PI / 180;
    const c = Math.abs(Math.cos(a)), s = Math.abs(Math.sin(a));
    return [(p.w * c + p.h * s) / 2, (p.w * s + p.h * c) / 2];
  }

  function padShape(p, cls) {
    const t = `rotate(${-(p.angle || 0)} ${p.x} ${p.y})`;
    if (p.shape === "circle") return `<circle class="${cls}" cx="${p.x}" cy="${p.y}" r="${p.w / 2}"/>`;
    let rx = 0;
    if (p.shape === "oval") rx = Math.min(p.w, p.h) / 2;
    else if (p.shape === "roundrect") rx = Math.min(p.w, p.h) * (p.rratio || 0.25);
    return `<rect class="${cls}" x="${p.x - p.w / 2}" y="${p.y - p.h / 2}" width="${p.w}" height="${p.h}" rx="${rx}" transform="${t}"/>`;
  }

  function arcPath(g) {
    // Circle through start, mid, end
    const [ax, ay, bx, by, cx, cy] = [g.x1, g.y1, g.xm, g.ym, g.x2, g.y2];
    const d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by));
    if (Math.abs(d) < 1e-9) return `M${ax} ${ay}L${cx} ${cy}`;
    const ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d;
    const uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d;
    const r = Math.hypot(ax - ux, ay - uy);
    const cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax);
    const sweep = cross > 0 ? 1 : 0;
    const a1 = Math.atan2(ay - uy, ax - ux), a2 = Math.atan2(by - uy, bx - ux), a3 = Math.atan2(cy - uy, cx - ux);
    const norm = x => (x + 4 * Math.PI) % (2 * Math.PI);
    const span = sweep ? norm(a3 - a1) : norm(a1 - a3);
    const large = span > Math.PI ? 1 : 0;
    return `M${ax} ${ay}A${r} ${r} 0 ${large} ${sweep} ${cx} ${cy}`;
  }

  function graphic(g) {
    const cls = g.l === "fab" ? "g-fab" : g.l === "silk" ? "g-silk" : "g-crty";
    if (g.k === "line") return `<line class="${cls}" x1="${g.x1}" y1="${g.y1}" x2="${g.x2}" y2="${g.y2}"/>`;
    if (g.k === "rect") return `<rect class="${cls}" x="${Math.min(g.x1, g.x2)}" y="${Math.min(g.y1, g.y2)}" width="${Math.abs(g.x2 - g.x1)}" height="${Math.abs(g.y2 - g.y1)}" fill="none"/>`;
    if (g.k === "circle") return `<circle class="${cls}" cx="${g.x1}" cy="${g.y1}" r="${Math.hypot(g.x2 - g.x1, g.y2 - g.y1)}" fill="none"/>`;
    if (g.k === "arc") return `<path class="${cls}" d="${arcPath(g)}" fill="none"/>`;
    if (g.k === "poly") return `<polygon class="${cls}" points="${g.pts.map(p => p.join(",")).join(" ")}" fill="none"/>`;
    return "";
  }

  function bounds(pads, graphics) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    const add = (x, y) => { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); };
    for (const p of pads) { const [ex, ey] = padBox(p); add(p.x - ex, p.y - ey); add(p.x + ex, p.y + ey); }
    for (const g of graphics) {
      if (g.l === "crty") continue;
      if (g.pts) g.pts.forEach(p => add(p[0], p[1]));
      else if (g.k === "circle") { const r = Math.hypot(g.x2 - g.x1, g.y2 - g.y1); add(g.x1 - r, g.y1 - r); add(g.x1 + r, g.y1 + r); }
      else { add(g.x1, g.y1); add(g.x2, g.y2); if (g.xm != null) add(g.xm, g.ym); }
    }
    if (!isFinite(x0)) return [-1, -1, 2, 2];
    return [x0, y0, x1 - x0, y1 - y0];
  }

  window.renderFootprint = function (geo, refPads, opts = {}) {
    if (!geo || !geo.pads) return `<div class="empty">Ingen footprint-geometri</div>`;
    const pads = geo.pads.filter(p => p.type !== "np_thru_hole" || p.w > 0);
    const graphics = (geo.graphics || []).filter(g => g.l !== "crty");
    let [x, y, w, h] = bounds(pads.concat(refPads || []), graphics);
    const m = Math.max(w, h) * (opts.dims ? 0.3 : 0.12) + 0.3;
    x -= m; y -= m; w += 2 * m; h += 2 * m;
    const unit = Math.max(w, h) / 100;
    const font = Math.max(unit * 3.2, 0.12);
    const parts = [];
    parts.push(`<style>
      .g-fab{stroke:var(--fab);stroke-width:${unit * 0.5};}
      .g-silk{stroke:var(--silk);stroke-width:${unit * 0.6};}
      .g-crty{stroke:var(--fab);stroke-width:${unit * 0.3};stroke-dasharray:${unit} ${unit};}
      .pad{fill:var(--pad-fill);stroke:var(--pad);stroke-width:${unit * 0.4};}
      .ref{fill:none;stroke:var(--ref);stroke-width:${unit * 0.7};stroke-dasharray:${unit * 1.6} ${unit};}
      .bad{fill:none;stroke:var(--bad);stroke-width:${unit * 0.9};}
      .drill{fill:var(--surface2);}
      .dim{stroke:var(--accent);stroke-width:${unit * 0.45};}
      .dimt{fill:var(--accent);font:600 ${font * 0.95}px system-ui,sans-serif;text-anchor:middle;dominant-baseline:central;paint-order:stroke;stroke:var(--surface);stroke-width:${unit * 0.8};}
      .pn{fill:var(--text);font:${font}px system-ui,sans-serif;text-anchor:middle;dominant-baseline:central;pointer-events:none;}
    </style>`);
    graphics.forEach(g => parts.push(graphic(g)));
    const badPads = new Set((opts.details || []).map(d => d.pad));
    pads.forEach(p => {
      parts.push(padShape(p, "pad"));
      if (p.drill) parts.push(`<circle class="drill" cx="${p.x}" cy="${p.y}" r="${p.drill / 2}"/>`);
    });
    (refPads || []).forEach(p => parts.push(padShape(p, "ref")));
    pads.forEach(p => { if (badPads.has(p.num)) parts.push(padShape(Object.assign({}, p, { w: p.w + unit * 2, h: p.h + unit * 2 }), "bad")); });
    if (pads.length <= 120) {
      pads.forEach(p => {
        if (!p.num) return;
        const fs = Math.min(font, Math.min(p.w, p.h) * 0.7);
        parts.push(`<text class="pn" x="${p.x}" y="${p.y}" style="font-size:${fs}px">${esc(p.num)}</text>`);
      });
    }
    // Pin 1 marker
    const p1 = pads.find(p => p.num === "1" || p.num === "A1");
    if (p1) {
      const [ex, ey] = padBox(p1);
      parts.push(`<circle cx="${p1.x - ex - unit * 2.2}" cy="${p1.y - ey - unit * 2.2}" r="${unit * 1.4}" fill="var(--bad)"/>`);
    }
    // Dimension lines: {x1, y1, x2, y2, text, side: "above"|"below"|"left"|"right"}
    (opts.dims || []).forEach(d => {
      const t = unit * 1.2;
      const vertical = Math.abs(d.x2 - d.x1) < Math.abs(d.y2 - d.y1);
      parts.push(`<line class="dim" x1="${d.x1}" y1="${d.y1}" x2="${d.x2}" y2="${d.y2}"/>`);
      for (const [px, py] of [[d.x1, d.y1], [d.x2, d.y2]])
        parts.push(vertical ? `<line class="dim" x1="${px - t}" y1="${py}" x2="${px + t}" y2="${py}"/>`
                            : `<line class="dim" x1="${px}" y1="${py - t}" x2="${px}" y2="${py + t}"/>`);
      const tx = (d.x1 + d.x2) / 2 + (vertical ? (d.side === "right" ? 1 : -1) * unit * 4.5 : 0);
      const ty = (d.y1 + d.y2) / 2 + (vertical ? 0 : (d.side === "above" ? -1 : 1) * unit * 2.6);
      parts.push(`<text class="dimt" x="${tx}" y="${ty}">${esc(d.text)}</text>`);
    });
    const scale = opts.scaleBar !== false;
    if (scale) {
      const len = [0.5, 1, 2, 5, 10, 20, 50].find(v => v >= w / 6) || 1;
      const sx = x + m * 0.4, sy = y + h - m * 0.35;
      parts.push(`<line x1="${sx}" y1="${sy}" x2="${sx + len}" y2="${sy}" stroke="var(--muted)" stroke-width="${unit * 0.6}"/>`);
      parts.push(`<text x="${sx + len / 2}" y="${sy - unit * 2.2}" fill="var(--muted)" style="font:${font * 0.9}px system-ui;text-anchor:middle">${len} mm</text>`);
    }
    return `<svg viewBox="${x} ${y} ${w} ${h}" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Footprint">${parts.join("")}</svg>`;
  };
})();
