(function () {
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const STATUS_TXT = { ok: "OK", warn: "Advarsel", partial: "Delvis", mismatch: "Fejl", missing: "Mangler i kurv", unknown: "Ukendt" };
  const pill = (st, txt) => `<span class="pill ${esc(st)}">${esc(txt || STATUS_TXT[st] || st)}</span>`;
  const KEEP_EXT = /\.(kicad_sch|kicad_pcb|kicad_pro|kicad_mod|kicad_sym)$|(^|\/)(fp-lib-table|sym-lib-table)$/i;

  const files = { project: [], dist: [], refs: [] };
  let state = { job: null, result: null, tab: "bom", alts: {}, cmp: {}, choice: {}, sel: null };

  // ---------- settings ----------
  async function loadSettings() {
    const cfg = await (await fetch("/api/settings")).json();
    const form = $("#settingsForm");
    for (const [k, v] of Object.entries(cfg)) if (form.elements[k]) form.elements[k].value = v || "";
    $("#chkUpdates").checked = cfg.check_updates !== "0";
    const names = [];
    if (cfg.digikey_client_id && cfg.digikey_client_secret) names.push("DigiKey");
    if (cfg.mouser_key) names.push("Mouser");
    if (cfg.nexar_client_id && cfg.nexar_client_secret) names.push("Nexar");
    const b = $("#providerBadge");
    b.textContent = names.length ? "API: " + names.join(", ") : "Ingen grosist-API";
    b.className = "badge" + (names.length ? "" : " muted");
    return cfg;
  }
  function formData() {
    const out = {};
    for (const el of $("#settingsForm").elements) if (el.name) out[el.name] = el.value;
    out.check_updates = $("#chkUpdates").checked ? "1" : "0";
    return out;
  }
  $("#btnSettings").onclick = () => { $("#testResult").textContent = ""; $("#settings").showModal(); };
  $("#btnCancel").onclick = () => $("#settings").close();
  $("#btnSave").onclick = async () => {
    await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(formData()) });
    await loadSettings();
    $("#settings").close();
  };
  $("#btnTest").onclick = async () => {
    await fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(formData()) });
    await loadSettings();
    $("#testResult").textContent = "Tester …";
    const res = await (await fetch("/api/test-keys", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
    $("#testResult").innerHTML = Object.entries(res).map(([k, v]) =>
      `<div class="${v.ok ? "ok-text" : "bad-text"}"><b>${esc(k)}</b>: ${esc(v.msg)}</div>`).join("");
  };

  // ---------- links & updates ----------
  // In the app window, external pages open in the normal browser.
  function openExternal(url) {
    if (window.pywebview && window.pywebview.api) window.pywebview.api.open_url(url);
    else window.open(url, "_blank", "noopener");
  }
  document.addEventListener("click", e => {
    const a = e.target.closest('a[target="_blank"]');
    if (a && window.pywebview && window.pywebview.api && /^https?:/.test(a.href) && !a.href.startsWith(location.origin)) {
      e.preventDefault(); openExternal(a.href);
    }
  }, true);

  async function checkUpdates(force) {
    let v;
    try { v = await (await fetch("/api/version" + (force ? "?force=1" : ""))).json(); } catch (e) { return; }
    $("#verInfo").textContent = `Du har version ${v.current}.` + (v.latest ? ` Nyeste: ${v.latest}.` : "") + (v.error ? " " + v.error : "");
    const b = $("#updBanner");
    if (!v.newer) { b.classList.add("hidden"); if (force) $("#verInfo").textContent += v.error ? "" : " Du har den nyeste."; return; }
    b.innerHTML = `<b>Version ${esc(v.latest)} er klar</b> <span>(du har ${esc(v.current)})</span>
      <button class="btn small" id="updNow">${v.can_install ? "Opdatér nu" : "Hent på GitHub"}</button>
      <button class="btn small ghost" id="updLater">Senere</button>
      ${v.notes ? `<details><summary>Hvad er nyt</summary>${esc(v.notes)}</details>` : ""}`;
    b.classList.remove("hidden");
    $("#updLater").onclick = () => b.classList.add("hidden");
    $("#updNow").onclick = async () => {
      if (!v.can_install) return openExternal(v.page);
      b.innerHTML = "Henter og installerer opdateringen … programmet genstarter om lidt.";
      const r = await (await fetch("/api/update", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })).json();
      b.innerHTML = r.error ? `Opdatering fejlede: ${esc(r.error)}` : esc(r.msg);
    };
  }
  $("#btnCheckUpd").onclick = () => checkUpdates(true);

  // ---------- uploads ----------
  async function upload(kind, file, relPath) {
    const name = relPath || file.webkitRelativePath || file.name;
    const entry = { name, size: file.size, id: null, status: "uploader …" };
    files[kind].push(entry);
    renderFiles(kind);
    try {
      const r = await fetch("/api/upload", { method: "POST", headers: { "X-Filename": encodeURIComponent(name) }, body: file });
      const j = await r.json();
      if (j.error) throw new Error(j.error);
      entry.id = j.id; entry.status = "";
    } catch (e) { entry.status = "fejl: " + e.message; }
    renderFiles(kind);
  }
  function addFiles(kind, list) {
    for (const f of list) {
      const rel = f._rel || f.webkitRelativePath || f.name;
      if (kind === "project" && !/\.zip$/i.test(f.name) && !KEEP_EXT.test(rel)) continue; // skip 3D models etc.
      upload(kind, f, rel);
    }
  }
  function renderFiles(kind) {
    const ul = $({ project: "#lProject", dist: "#lDist", refs: "#lRefs" }[kind]);
    const list = files[kind];
    const shown = list.length > 8 ? list.slice(0, 6) : list;
    ul.innerHTML = shown.map((f, i) =>
      `<li><span>${esc(f.name)} <span class="sub">${(f.size / 1024).toFixed(0)} kB ${esc(f.status)}</span></span><button data-k="${kind}" data-i="${i}" title="Fjern">×</button></li>`).join("")
      + (list.length > shown.length ? `<li><span class="sub">… og ${list.length - shown.length} filer mere</span><button data-k="${kind}" data-i="all" title="Fjern alle">×</button></li>` : "");
    $("#btnRun").disabled = !files.project.some(f => f.id);
  }
  document.addEventListener("click", e => {
    const b = e.target.closest(".files button");
    if (!b) return;
    if (b.dataset.i === "all") files[b.dataset.k] = []; else files[b.dataset.k].splice(+b.dataset.i, 1);
    renderFiles(b.dataset.k);
  });
  $("#fProject").onchange = e => { addFiles("project", e.target.files); e.target.value = ""; };
  $("#fProjectDir").onchange = e => { addFiles("project", e.target.files); e.target.value = ""; };
  $("#fDist").onchange = e => { addFiles("dist", e.target.files); e.target.value = ""; };
  $("#fRefs").onchange = e => { addFiles("refs", e.target.files); e.target.value = ""; };

  async function readEntry(entry, path, out) {
    if (entry.isFile) {
      const f = await new Promise((res, rej) => entry.file(res, rej));
      f._rel = path + f.name;
      out.push(f);
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      let batch;
      do {
        batch = await new Promise((res, rej) => reader.readEntries(res, rej));
        for (const ch of batch) await readEntry(ch, path + entry.name + "/", out);
      } while (batch.length);
    }
  }
  for (const [dz, kind] of [["#dzProject", "project"], ["#dzDist", "dist"], ["#dzRefs", "refs"]]) {
    const el = $(dz);
    el.addEventListener("dragover", e => { e.preventDefault(); el.classList.add("over"); });
    el.addEventListener("dragleave", () => el.classList.remove("over"));
    el.addEventListener("drop", async e => {
      e.preventDefault(); el.classList.remove("over");
      const items = [...(e.dataTransfer.items || [])].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
      if (items.some(i => i.isDirectory)) {
        const out = [];
        for (const it of items) await readEntry(it, "", out);
        addFiles(kind, out);
      } else addFiles(kind, e.dataTransfer.files);
    });
  }

  // ---------- run ----------
  function settings() {
    return {
      boards: +$("#oBoards").value || 1, spare_passive_pct: +$("#oSpareP").value || 0,
      spare_passive_min: +$("#oSpareMin").value || 0, spare_pct: +$("#oSpare").value || 0,
      extra_budget_abs: +$("#oExtraAbs").value || 0, extra_budget_pct: +$("#oExtraPct").value || 0,
      use_api: $("#oApi").checked, suggest_mpn: $("#oSuggest").checked,
      check_datasheets: $("#oDs").checked, save_history: $("#oHist").checked,
    };
  }
  $("#btnRun").onclick = async () => {
    const body = { settings: settings() };
    for (const k of ["project", "dist", "refs"]) body[k] = files[k].filter(f => f.id).map(f => f.id);
    $("#btnRun").disabled = true;
    $("#progress").classList.remove("hidden");
    const { job, error } = await (await fetch("/api/analyze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })).json();
    if (error) return fail(error);
    state.job = job;
    poll();
  };
  function fail(msg) {
    $("#progMsg").innerHTML = `<span class="bad-text">${esc(msg)}</span>`;
    $("#btnRun").disabled = false;
  }
  async function poll() {
    const j = await (await fetch("/api/job/" + state.job)).json();
    $("#progBar").style.width = (j.progress || 0) + "%";
    $("#progMsg").textContent = j.msg || "";
    if (j.state === "running") return setTimeout(poll, 600);
    if (j.state === "error") return fail(j.error);
    state.result = j.result; state.alts = {}; state.cmp = {}; state.choice = {}; state.sel = null; state.diff = null; state.cart = null;
    $("#btnRun").disabled = false;
    showResult();
  }
  $("#btnBack").onclick = () => { document.querySelector("main").classList.remove("wide"); $("#resultView").classList.add("hidden"); $("#inputView").classList.remove("hidden"); $("#progress").classList.add("hidden"); loadHistory(); };

  // ---------- history ----------
  let historyList = [];
  async function loadHistory() {
    try { historyList = await (await fetch("/api/history")).json(); } catch (e) { historyList = []; }
    $("#histCard").classList.toggle("hidden", !historyList.length);
    $("#histBody").innerHTML = historyList.map(h => {
      const st = Object.entries(h.status || {}).filter(([k]) => k !== "ok").map(([k, v]) => `${v} ${STATUS_TXT[k] || k}`).join(", ");
      return `<tr><td>${esc(h.time)}</td><td>${esc(h.project)}</td><td class="num">${h.parts ?? ""}</td><td class="num">${h.lines ?? ""}</td>
        <td>${st ? `<span class="sub">${esc(st)}</span>` : pill("ok")}</td><td class="num">${h.total ? money(h.total) : "–"}</td>
        <td><button class="btn small" data-hopen="${esc(h.id)}">Åbn</button> <button class="btn small ghost" data-hdel="${esc(h.id)}" title="Slet">×</button></td></tr>`;
    }).join("");
  }
  document.addEventListener("click", async e => {
    const o = e.target.closest("[data-hopen]"), d = e.target.closest("[data-hdel]");
    if (o) {
      const res = await (await fetch("/api/history/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: o.dataset.hopen }) })).json();
      if (res.error) return alert(res.error);
      state.job = res.job; state.result = res.result; state.alts = {}; state.cmp = {}; state.choice = {}; state.sel = null; state.diff = null; state.cart = null;
      showResult();
    } else if (d) {
      if (!confirm("Slet denne analyse fra historikken?")) return;
      await fetch("/api/history/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id: d.dataset.hdel }) });
      loadHistory();
    }
  });

  // ---------- results ----------
  const money = (v, cur) => v == null ? "–" : v.toLocaleString("da-DK", { minimumFractionDigits: 2, maximumFractionDigits: v < 1 ? 4 : 2 }) + (cur ? " " + cur : "");
  const curOf = r => (r.lines.find(l => l.plan) || {}).plan?.best.currency || "";

  function showResult() {
    const r = state.result;
    $("#inputView").classList.add("hidden");
    $("#resultView").classList.remove("hidden");
    document.querySelector("main").classList.add("wide");
    $("#rTitle").textContent = r.project.name || "Projekt";
    const v = r.project.version;
    $("#rSub").textContent = `KiCad-filversion: skematik ${v.sch || "–"} (${v.sch_generator || "?"}), PCB ${v.pcb || "–"} (${v.pcb_generator || "?"}) · ${r.settings.boards} print`;
    const s = r.summary, cur = curOf(r);
    const fpBad = (s.fp.mismatch || 0), fpWarn = (s.fp.warn || 0) + (s.fp.partial || 0) + (s.fp.unknown || 0);
    const tiles = [
      ["Komponenter", s.parts, `${s.lines} BOM-linjer · ${s.excluded} udeladt`],
      ["Uden MPN", s.no_mpn, s.no_mpn ? "se BOM-fanen" : "alle har varenummer"],
      ["Footprints OK", s.fp.ok || 0, `${fpWarn} at tjekke · ${fpBad} fejl`],
    ];
    for (const d of s.dist) tiles.push([`${d.distributor}-BOM`, `${d.ok}/${d.ok + d.problems}`, `${d.problems} afvigelser · ${d.extras} ekstra i kurven`]);
    if (r.totals.lines_priced) {
      tiles.push(["Billigste mix", money(r.totals.mix, cur), `${r.totals.lines_priced} af ${s.lines} linjer prissat`]);
      for (const [seller, t] of Object.entries(r.totals.per_seller))
        tiles.push([seller, money(t.total, cur), `har ${t.lines} af ${s.lines} linjer`]);
    }
    $("#tiles").innerHTML = tiles.map(([k, v, sub]) => `<div class="tile"><div class="k">${esc(k)}</div><div class="v">${esc(v)}</div><div class="s">${esc(sub)}</div></div>`).join("");
    const notes = [];
    if (!r.providers.length && r.settings.use_api)
      notes.push(["info", "Ingen grosist-API sat op – priser, lager, datablade og alternativer kræver mindst én nøgle (Indstillinger). Alt andet virker uden."]);
    r.errors.forEach(e => notes.push(["bad", e]));
    r.project.warnings.forEach(w => notes.push(["warn", w]));
    $("#notices").innerHTML = notes.map(([c, t]) => `<div class="notice ${c}">${esc(t)}</div>`).join("");
    renderTab();
    const first = r.lines.find(l => l.status !== "ok") || r.lines[0];
    if (first) select(first.id, true); else renderSide();
  }

  $("#tabs").addEventListener("click", e => {
    const b = e.target.closest("button[data-tab]");
    if (!b) return;
    state.tab = b.dataset.tab;
    document.querySelectorAll("#tabs button").forEach(x => x.classList.toggle("active", x === b));
    renderTab();
  });
  $("#onlyProblems").onchange = renderTab;

  function visibleLines() {
    const only = $("#onlyProblems").checked;
    return state.result.lines.filter(l => !only || l.status !== "ok");
  }

  function renderTab() {
    const f = { bom: tabBom, fp: tabFp, dist: tabDist, buy: tabBuy, excl: tabExcl, diff: tabDiff }[state.tab];
    $("#tabBody").innerHTML = f();
    if (state.sel) document.querySelectorAll(`#tabBody [data-line="${CSS.escape(state.sel)}"]`).forEach(e => e.classList.add("sel"));
  }

  function mpnCell(l) {
    if (l.mpn) return `<span class="mono">${esc(l.mpn)}</span>${l.mpn_field && !/^(MPN|Mfr|Manufacturer)/i.test(l.mpn_field) ? `<div class="sub">${esc(l.mpn_field)}</div>` : ""}`;
    if (l.suggested) return `<span class="sub">forslag:</span> <span class="mono">${esc(l.suggested[0].mpn)}</span>`;
    if (l.mpn_guess) return `<span class="mono">${esc(l.mpn_guess)}</span> <span class="sub">(fra værdi)</span>`;
    if (l.generic_spec) return `<span class="sub">generisk: ${esc(l.generic_spec)}</span>`;
    return `<span class="sub">– intet MPN –</span>`;
  }

  function tabBom() {
    const rows = visibleLines().map(l => {
      const [ds, dsMsg] = dsStat(l), [bs, bsMsg] = buyStat(l), fs = fpStat(l);
      return `<tr data-line="${esc(l.id)}">
      <td class="num">${l.qty}</td>
      <td class="refs">${esc(l.refs.join(", "))}</td>
      <td>${esc(l.value)}${l.desc ? `<div class="sub">${esc(l.desc).slice(0, 60)}</div>` : ""}</td>
      <td>${mpnCell(l)}${l.mfr ? `<div class="sub">${esc(l.mfr)}</div>` : ""}</td>
      <td class="mono">${esc(l.footprint.split(":").pop())}</td>
      <td class="ctrl">${ctrlPill(fs, STATUS_TXT[fs] || fs, "Symbol ↔ footprint")}</td>
      <td class="ctrl">${ds === "none" ? `<span class="sub">–</span>` : ctrlPill(ds, STATUS_TXT[ds] || ds, dsMsg)}</td>
      <td class="ctrl">${ctrlPill(bs, bs === "ok" ? "OK" : STATUS_TXT[bs] || bs, bsMsg)}${state.choice[l.id] ? `<div class="sub">alternativ</div>` : ""}</td>
    </tr>`;
    }).join("");
    return `<div class="tbl-wrap"><table class="bom"><thead><tr><th class="num">Antal</th><th>Referencer</th><th>Værdi</th><th>MPN</th><th>Footprint</th>
      <th title="Passer symbolet og footprintet sammen?">1 Footprint</th><th title="Passer footprintet med databladet?">2 Datablad</th><th title="Kan den købes som valgt?">3 Indkøb</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="8" class="empty">Ingen linjer</td></tr>`}</tbody></table></div>`;
  }

  function fpLegend(fp) {
    return `<div class="legend"><span><i style="background:var(--pad-fill);border:1px solid var(--pad)"></i>Dit footprint (${esc(fp.geometry_source || "")})</span>${fp.overlay ? `<span><i style="border:2px dashed var(--ref)"></i>${esc(fp.overlay.ref_label)}</span>` : ""}<span><i style="background:var(--bad);border-radius:50%"></i>Pin 1</span></div>`;
  }
  function checksList(fp) {
    return `<ul class="checks">${(fp.checks || []).map(c => `<li>${pill(c.status)}<span><b>${esc(c.check)}</b><br>${esc(c.msg)}</span></li>`).join("")}</ul>`;
  }

  function tabFp() {
    const cards = visibleLines().filter(l => l.fp).map(l => {
      const fp = l.fp;
      return `<div class="fp-card" data-line="${esc(l.id)}">
        <h3><span>${esc(l.refs.slice(0, 4).join(", "))}${l.refs.length > 4 ? " …" : ""}</span>${pill(fp.status)}</h3>
        <div class="sub mono">${esc(l.footprint)}</div>
        <div class="sub">${esc(l.mpn || l.value)}${fp.part_pkg ? " · pakke: " + esc(fp.part_pkg) : ""}</div>
        <div class="fp-svg">${renderFootprint(fp.geometry, fp.overlay && fp.overlay.ref_pads, { details: fp.overlay && fp.overlay.details })}</div>
        ${checksList(fp)}
      </div>`;
    }).join("");
    return `<p class="hint">Orange = dine pads (fra PCB'en eller biblioteket). Blå stiplet = reference: producentens CAD-fil, IPC-7351-mønster eller KiCad-biblioteket. Klik på et kort for at se det i kontrolpanelet.</p><div class="fp-grid">${cards || `<div class="empty">Ingen footprints</div>`}</div>`;
  }

  function tabDist() {
    const r = state.result;
    if (!r.dist_boms.length) return `<div class="empty">Ingen grosist-BOM uploadet. Upload en kurv/BOM-fil fra fx Mouser eller DigiKey for at sammenligne.</div>`;
    return r.dist_boms.map(d => {
      const cols = Object.entries(d.columns).map(([k, v]) => `${({ mpn: "MPN", dist_pn: "Varenr.", qty: "Antal", unit_price: "Stykpris", ext_price: "Total", desc: "Beskrivelse", mfr: "Producent", refs: "Referencer", package: "Pakke" })[k] || k} = "${v}"`).join(" · ");
      const rows = visibleLines().map(l => {
        const m = d.results[l.id] || {};
        const dl = m.dist_line;
        const issues = (m.issues || []).concat(m.qty_msg && m.qty_status !== "ok" ? [m.qty_msg] : []);
        return `<tr data-line="${esc(l.id)}">
          <td>${pill(m.status || "missing", m.status === "missing" ? "Mangler" : null)}</td>
          <td class="refs">${esc(l.refs.join(", "))}</td>
          <td class="mono">${esc(l.mpn || l.value)}</td>
          <td class="mono">${dl ? esc(dl.mpn) : ""}<div class="sub">${dl ? esc(dl.dist_pn) : ""}</div></td>
          <td class="num">${l.need}${l.need_spare > l.need ? ` <span class="sub">(+${l.need_spare - l.need})</span>` : ""}</td>
          <td class="num">${dl ? (dl.qty ?? "?") : "–"}</td>
          <td class="num">${dl && dl.unit_price != null ? money(dl.unit_price, dl.currency || d.currency) : ""}</td>
          <td>${esc(m.how || "")}${issues.length ? `<ul class="warnlist">${issues.map(i => `<li>${esc(i)}</li>`).join("")}</ul>` : ""}</td>
        </tr>`;
      }).join("");
      const extras = d.extras.length ? `<div class="section"><h3>I kurven, men ikke i projektet (${d.extras.length})</h3><div class="tbl-wrap"><table><thead><tr><th>Række</th><th>MPN</th><th>Varenr.</th><th class="num">Antal</th><th>Beskrivelse</th></tr></thead><tbody>${d.extras.map(e => `<tr><td>${e.row}</td><td class="mono">${esc(e.mpn)}</td><td class="mono">${esc(e.dist_pn)}</td><td class="num">${e.qty ?? ""}</td><td>${esc(e.desc)}</td></tr>`).join("")}</tbody></table></div></div>` : "";
      return `<div class="section"><h3>${esc(d.distributor)} – ${esc(d.name)}</h3><p class="hint">Fundne kolonner: ${esc(cols)}</p>
        <div class="tbl-wrap"><table><thead><tr><th>Status</th><th>Referencer</th><th>Projekt</th><th>Grosist</th><th class="num">Behov</th><th class="num">Bestilt</th><th class="num">Stykpris</th><th>Match / afvigelser</th></tr></thead><tbody>${rows}</tbody></table></div>${extras}</div>`;
    }).join("");
  }

  function tabBuy() {
    const r = state.result, cur = curOf(r);
    const lines = visibleLines();
    if (!lines.some(l => l.plan)) return `<div class="empty">Ingen priser. Tilføj en API-nøgle under Indstillinger, eller upload en grosist-BOM med priser.</div>`;
    const sellers = [...new Set(lines.flatMap(l => l.plan ? Object.keys(l.plan.per_seller) : []))];
    const rows = lines.map(l => {
      const p = l.plan;
      if (!p) return `<tr data-line="${esc(l.id)}"><td class="refs">${esc(l.refs.join(", "))}</td><td class="mono">${esc(l.mpn || l.value)}</td><td class="num">${l.need_spare}</td><td colspan="${4 + sellers.length}" class="sub">Ingen pris fundet</td></tr>`;
      const b = p.best;
      const sugg = b.suggestions.map(s => `<div class="sugg ${s.kind}">${esc(s.text)}</div>`).join("") + (b.note ? `<div class="sub">${esc(b.note)}</div>` : "");
      return `<tr data-line="${esc(l.id)}">
        <td class="refs">${esc(l.refs.join(", "))}</td>
        <td class="mono">${esc(l.mpn || (l.suggested ? l.suggested[0].mpn : l.value))}</td>
        <td class="num">${l.need}${l.need_spare > l.need ? ` <span class="sub">+${l.need_spare - l.need}</span>` : ""}</td>
        <td class="num"><b>${b.qty}</b></td>
        <td>${esc(b.seller)}<div class="sub mono">${esc(b.sku)}</div></td>
        <td class="num">${money(b.unit)}</td>
        <td class="num"><b>${money(b.total)}</b>${sugg}</td>
        ${sellers.map(s => `<td class="num">${p.per_seller[s] ? money(p.per_seller[s].total) + `<div class="sub">${p.per_seller[s].qty} stk.</div>` : "–"}</td>`).join("")}
      </tr>`;
    }).join("");
    return `<p class="hint">Behov = antal × ${r.settings.boards} print (+ reserve). "Køb" er den billigste mængde ved prisknæk, MOQ og pakning – nogle gange er flere stk. billigere end færre. Valuta: ${esc(cur)}.</p>
      <div class="row" style="margin-bottom:10px">${sellers.map(s => `<button class="btn small" data-export="${esc(s)}">Indkøbsliste: ${esc(s)} (CSV)</button>`).join("")}<button class="btn small" data-export="*">Billigste mix (CSV)</button>
        ${sellers.filter(s => /^digi-?key$/i.test(s)).map(s => `<button class="btn small primary" data-dkcart="${esc(s)}" title="Åbner DigiKey med varerne i kurven (DigiKey FastAdd)">Læg i DigiKey-kurv</button>`).join("")}
        ${sellers.filter(s => /^mouser$/i.test(s)).map(s => `<button class="btn small primary" data-mocart="${esc(s)}" title="Opretter en kurv via Mousers Cart API">Læg i Mouser-kurv</button>`).join("")}</div>
      ${cartBox()}
      <div class="tbl-wrap"><table><thead><tr><th>Referencer</th><th>MPN</th><th class="num">Behov</th><th class="num">Køb</th><th>Billigst hos</th><th class="num">Stykpris</th><th class="num">Linjepris</th>${sellers.map(s => `<th class="num">${esc(s)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody>
      <tfoot><tr><th colspan="6">I alt (billigste mix)</th><th class="num">${money(r.totals.mix, cur)}</th>${sellers.map(s => `<th class="num">${r.totals.per_seller[s] ? money(r.totals.per_seller[s].total) + `<div class="sub">${r.totals.per_seller[s].lines}/${r.summary.lines} linjer</div>` : "–"}</th>`).join("")}</tr></tfoot></table></div>`;
  }

  function tabExcl() {
    const ex = state.result.excluded;
    if (!ex.length) return `<div class="empty">Intet udeladt.</div>`;
    return `<p class="hint">Disse er ikke med i BOM'en og indkøbet.</p><div class="tbl-wrap"><table><thead><tr><th>Reference</th><th>Hvorfor</th><th>Footprint</th></tr></thead><tbody>${ex.map(e => `<tr><td>${esc(e.ref)}</td><td>${esc(e.why)}</td><td class="mono">${esc(e.footprint)}</td></tr>`).join("")}</tbody></table></div>`;
  }

  function tabDiff() {
    const r = state.result;
    const older = historyList.filter(h => h.id !== r.history_id && h.project === r.project.name);
    if (!older.length) return `<div class="empty">Ingen tidligere analyser af "${esc(r.project.name)}" at sammenligne med. Analyser gemmes automatisk, så næste gang kan du se hvad der er ændret.</div>`;
    const sel = `<label class="row" style="margin-bottom:10px">Sammenlign med <select id="diffSel">${older.map(h => `<option value="${esc(h.id)}" ${state.diff && state.diff.id === h.id ? "selected" : ""}>${esc(h.time)} – ${h.parts} komp.</option>`).join("")}</select></label>`;
    if (!state.diff) { setTimeout(() => loadDiff(older[0].id), 0); return sel + `<p class="hint">Sammenligner …</p>`; }
    const d = state.diff.data;
    const tbl = (title, rows, head) => rows.length ? `<div class="section"><h3>${title} (${rows.length})</h3><div class="tbl-wrap"><table><thead><tr>${head.map(h => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div></div>` : "";
    const price = d.total_old && d.total_new ? ` · pris (mix) ${money(d.total_old)} → ${money(d.total_new)}` : "";
    const row = x => `<tr><td>${esc(x.ref)}</td><td>${esc(x.value)}</td><td class="mono">${esc((x.footprint || "").split(":").pop())}</td><td class="mono">${esc(x.mpn)}</td></tr>`;
    return sel + `<p class="hint">Fra ${esc(d.old_meta.time)} til denne analyse: ${d.parts_old} → ${d.parts_new} komponenter${price}.</p>`
      + (d.added.length + d.removed.length + d.changed.length === 0 ? `<div class="empty">Ingen ændringer i komponenterne.</div>` : "")
      + tbl("Tilføjet", d.added.map(row), ["Ref", "Værdi", "Footprint", "MPN"])
      + tbl("Fjernet", d.removed.map(row), ["Ref", "Værdi", "Footprint", "MPN"])
      + tbl("Ændret", d.changed.map(x => `<tr><td>${esc(x.ref)}</td><td>${esc(x.field)}</td><td class="mono">${esc(x.old)}</td><td class="mono">${esc(x.new)}</td></tr>`), ["Ref", "Felt", "Før", "Nu"]);
  }
  async function loadDiff(id) {
    const res = await (await fetch("/api/compare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job: state.job, id }) })).json();
    if (res.error) { $("#tabBody").innerHTML = `<div class="notice bad">${esc(res.error)}</div>`; return; }
    state.diff = { id, data: res };
    if (state.tab === "diff") renderTab();
  }
  document.addEventListener("change", e => { if (e.target.id === "diffSel") loadDiff(e.target.value); });

  // ---------- carts ----------
  // What will actually be bought for a line at a seller: a chosen alternative overrides the plan.
  function buyFor(l, seller) {
    const ch = state.choice[l.id];
    if (ch) return seller === "*" || ch.seller === seller ? { sku: ch.sku, qty: ch.qty, seller: ch.seller, mpn: ch.mpn } : null;
    if (!l.plan) return null;
    const b = seller === "*" ? l.plan.best : l.plan.per_seller[seller];
    return b ? { sku: b.sku, qty: b.qty, seller: b.seller, mpn: l.mpn || (l.suggested ? l.suggested[0].mpn : "") } : null;
  }
  function cartItems(seller) {
    return state.result.lines.map(l => ({ l, b: buyFor(l, seller) })).filter(x => x.b && x.b.sku);
  }
  function digikeyCart(seller) {
    // DigiKey FastAdd: a form POST opens their site with the parts in your cart (max ~400 per post).
    const items = cartItems(seller);
    if (window.pywebview && window.pywebview.api) {
      // In the app window the cart opens in the normal browser: GET links of max ~1700 characters.
      const base = "https://www.digikey.com/classic/ordering/fastadd.aspx?";
      let parts = [], n = 0, first = true;
      const flush = () => { if (parts.length) openExternal(base + (first ? "newcart=true&" : "") + parts.join("&")); parts = []; n = 0; first = false; };
      for (const { l, b } of items) {
        const item = k => `part${k}=${encodeURIComponent(b.sku)}&qty${k}=${b.qty}&cref${k}=${encodeURIComponent(l.refs.join(",").slice(0, 30))}`;
        if ((base + parts.join("&") + "&" + item(n + 1)).length > 1650) flush();
        parts.push(item(n + 1)); n++;
      }
      flush();
      return;
    }
    for (let i = 0; i < items.length; i += 400) {
      const f = document.createElement("form");
      f.method = "post"; f.target = "_blank";
      f.action = "https://www.digikey.com/classic/ordering/fastadd.aspx" + (i === 0 ? "?newcart=true" : "");
      items.slice(i, i + 400).forEach(({ l, b }, j) => {
        for (const [k, v] of [["part", b.sku], ["qty", b.qty], ["cref", l.refs.join(",").slice(0, 48)]]) {
          const inp = document.createElement("input");
          inp.type = "hidden"; inp.name = k + (j + 1); inp.value = v;
          f.appendChild(inp);
        }
      });
      document.body.appendChild(f); f.submit(); f.remove();
    }
  }
  async function mouserCart(seller) {
    state.cart = { busy: true };
    renderTab();
    const res = await (await fetch("/api/cart/mouser", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job: state.job, seller }) })).json();
    state.cart = res;
    renderTab();
  }
  function cartBox() {
    const c = state.cart;
    if (!c) return "";
    if (c.busy) return `<div class="notice info">Lægger varer i Mouser-kurven …</div>`;
    if (c.error) return `<div class="notice bad">Mouser-kurv: ${esc(c.error)}</div>`;
    const bad = c.lines.filter(x => x.errors.length);
    return `<div class="notice info">Mouser-kurv oprettet: ${c.lines.length} linjer, i alt ${money(c.total, c.currency)} (Mousers egen pris). Kurv-nøgle: <span class="mono">${esc(c.cart_key)}</span>.
      Log ind på <a href="https://www.mouser.dk/Cart/" target="_blank" rel="noopener">mouser.dk/Cart</a> med den konto API-nøglen hører til for at se og bestille.
      ${bad.length ? `<ul class="warnlist">${bad.map(x => `<li>${esc(x.sku)}: ${esc(x.errors.join(" "))}</li>`).join("")}</ul>` : ""}</div>`;
  }

  // ---------- control panel (right side) ----------
  // Three checks per BOM line: symbol <-> footprint, footprint <-> datasheet, and what you will buy.
  const ORDER = { ok: 0, none: 0, unknown: 1, partial: 1, warn: 2, missing: 3, mismatch: 4 };
  const worst = list => list.reduce((a, b) => (ORDER[b] ?? 1) > (ORDER[a] ?? 1) ? b : a, "ok");

  function fpStat(l) {
    const cs = ((l.fp || {}).checks || []).filter(c => c.check !== "Datablad");
    return cs.length ? worst(cs.map(c => c.status)) : ((l.fp || {}).status || "unknown");
  }
  function dsStat(l) {
    const c = ((l.fp || {}).checks || []).find(c => c.check === "Datablad");
    if (c) return [c.status, c.msg];
    if (l.kind) return ["none", "Passive komponenter kontrolleres mod MPN-mønstre og IPC-mål i trin 1, ikke mod databladet."];
    return l.datasheet ? ["unknown", "Databladet er ikke læst."] : ["none", "Intet datablad-link."];
  }
  function buyStat(l) {
    const r = state.result, ch = state.choice[l.id];
    if (ch) return ["ok", `Alternativ valgt: ${ch.mpn}`];
    const ds = r.dist_boms.map(d => d.results[l.id]).filter(Boolean);
    if (ds.length) {
      const st = worst(ds.map(m => m.status));
      return [st, { ok: "Matcher kurven", missing: "Mangler i kurven" }[st] || "Afviger fra kurven"];
    }
    if (l.plan) {
      const s = l.plan.best.stock;
      if (s != null && s < l.need_spare) return [s ? "warn" : "mismatch", s ? `Kun ${s} på lager` : "Ikke på lager"];
      if (l.warnings.some(w => /Livscyklus|NRND|udgået/i.test(w))) return ["warn", "Udgået / NRND"];
      return ["ok", `${l.plan.best.seller} · ${money(l.plan.best.total)}`];
    }
    if (r.providers.length && (l.mpn || l.mpn_guess)) return ["mismatch", "Ikke fundet hos grosisterne"];
    return ["unknown", r.providers.length ? "Intet MPN at købe efter" : "Ingen indkøbsdata (API-nøgle eller grosist-BOM)"];
  }
  const needsAlt = l => state.result.providers.length && !state.choice[l.id] && ["warn", "mismatch", "missing"].includes(buyStat(l)[0]);
  const ctrlPill = (st, label, tip) => `<span class="pill ${st === "none" ? "unknown" : esc(st)}" title="${esc(tip || "")}">${esc(label)}</span>`;

  function select(id, scroll) {
    state.sel = id;
    document.querySelectorAll("[data-line].sel").forEach(e => e.classList.remove("sel"));
    document.querySelectorAll(`[data-line="${CSS.escape(id)}"]`).forEach(e => {
      e.classList.add("sel");
      if (scroll) e.scrollIntoView({ block: "nearest" });
    });
    renderSide();
  }

  function padBox(p) {
    const a = ((p.angle || 0) % 180) * Math.PI / 180, c = Math.abs(Math.cos(a)), s = Math.abs(Math.sin(a));
    return [(p.w * c + p.h * s) / 2, (p.w * s + p.h * c) / 2];
  }
  // Dimension lines for the drawing: row span, gap between rows and pitch.
  function dimLines(geo, f) {
    if (!geo || !geo.pads || !f || !f.rows) return [];
    const out = [];
    const pads = geo.pads.filter(p => p.num);
    const area = p => { const [ex, ey] = padBox(p); return ex * ey; };
    const med = pads.map(area).sort((a, b) => a - b)[Math.floor(pads.length / 2)] || 0;
    const reg = pads.filter(p => area(p) <= 3 * med);
    for (const axis of Object.keys(f.rows)) {
      const r = f.rows[axis];
      const X = axis === "x";
      const inRow = reg.filter(p => { const [ex, ey] = padBox(p); return X ? ex > ey * 1.1 || (Math.abs(ex - ey) < 1e-6 && Math.abs(p.x) >= Math.abs(p.y)) : ey > ex * 1.1 || (Math.abs(ex - ey) < 1e-6 && Math.abs(p.y) > Math.abs(p.x)); });
      if (inRow.length < 2) continue;
      const lo = Math.min(...inRow.map(p => (X ? p.x : p.y) - padBox(p)[X ? 0 : 1]));
      const hi = Math.max(...inRow.map(p => (X ? p.x : p.y) + padBox(p)[X ? 0 : 1]));
      const aMax = Math.max(...inRow.map(p => (X ? p.y + padBox(p)[1] : p.x + padBox(p)[0])));
      const aMin = Math.min(...inRow.map(p => (X ? p.y - padBox(p)[1] : p.x - padBox(p)[0])));
      const off = (hi - lo) * 0.12 + 0.3;
      if (X) out.push({ x1: lo, y1: aMax + off, x2: hi, y2: aMax + off, text: `${r.outer} mm`, side: "below" });
      else out.push({ x1: aMax + off, y1: lo, x2: aMax + off, y2: hi, text: `${r.outer} mm`, side: "right" });
      if (r.inner != null && r.inner > 0) {
        const neg = inRow.filter(p => (X ? p.x : p.y) < 0), pos = inRow.filter(p => (X ? p.x : p.y) > 0);
        const a = Math.max(...neg.map(p => (X ? p.x : p.y) + padBox(p)[X ? 0 : 1]));
        const b = Math.min(...pos.map(p => (X ? p.x : p.y) - padBox(p)[X ? 0 : 1]));
        if (X) out.push({ x1: a, y1: aMin - off, x2: b, y2: aMin - off, text: `${r.inner} mm`, side: "above" });
        else out.push({ x1: aMin - off, y1: a, x2: aMin - off, y2: b, text: `${r.inner} mm`, side: "left" });
      }
      const p1 = inRow.find(p => p.num === "1") || inRow[0];
      const nb = inRow.filter(q => q !== p1 && Math.abs((X ? q.x : q.y) - (X ? p1.x : p1.y)) < 0.05)
        .sort((q1, q2) => Math.abs((X ? q1.y : q1.x) - (X ? p1.y : p1.x)) - Math.abs((X ? q2.y : q2.x) - (X ? p1.y : p1.x)))[0];
      if (nb && f.pitch) {
        const edge = (X ? p1.x : p1.y) - padBox(p1)[X ? 0 : 1] - off * 0.6;
        if (X) out.push({ x1: edge, y1: p1.y, x2: edge, y2: nb.y, text: `${f.pitch}`, side: "left" });
        else out.push({ x1: p1.x, y1: edge, x2: nb.x, y2: edge, text: `${f.pitch}`, side: "above" });
      }
      break;
    }
    return out;
  }

  const mm = v => v == null ? "–" : `${v} mm`;
  const cmpTable = rows => `<div class="tbl-wrap"><table class="tight"><thead><tr><th>Mål</th><th class="num">Datablad</th><th class="num">Footprint</th><th></th></tr></thead><tbody>${rows.map(r => `<tr title="${esc(r.note)}"><td>${esc(r.what)}${r.note ? `<div class="sub">${esc(r.note)}</div>` : ""}</td><td class="num">${esc(r.ds)}</td><td class="num">${esc(r.fp)}</td><td>${pill(r.status)}</td></tr>`).join("")}</tbody></table></div>`;
  const pageBtn = (p, label) => `<button class="btn small" data-page="${p}">${esc(label || "side " + p)}</button>`;

  function sideCompare(l) {
    const res = state.cmp[l.id];
    if (!res) return `<p class="hint">Læser databladet og måler footprintet …</p>`;
    if (res.error) return `<div class="notice bad">${esc(res.error)}</div>`;
    let h = "";
    if (res.dims) {
      h += `<h4>Pakkemål: ${esc(res.dims.name)} ${pageBtn(res.dims.page)}</h4>
        ${res.dims.sure ? "" : `<p class="hint" style="color:var(--warn)">Tabellen kunne ikke knyttes sikkert til footprintets pakke.</p>`}
        ${cmpTable(res.dims.rows)}
        <details><summary class="hint">Hele mål-tabellen</summary><p class="mono hint">${Object.entries(res.dims.table).map(([k, v]) => `${esc(k)}: ${esc(v)}`).join(" · ")}</p></details>`;
    }
    if (res.land) {
      h += `<h4>Anbefalet land pattern ${esc(res.land.label)} ${pageBtn(res.land.page)}</h4>
        <p class="hint">Bogstaverne betyder forskelligt hos hver producent – værdier der findes i dit footprint er markeret.</p>${cmpTable(res.land.rows)}`;
    }
    if (res.pins) {
      h += `<h4>Pinout: symbol ↔ datablad ${pill(res.pins.status)} ${pageBtn(res.pins.page)}</h4><p class="hint">${esc(res.pins.summary)}</p>
        <div class="tbl-wrap"><table class="tight"><thead><tr><th class="num">Ben</th><th>Symbol</th><th>Datablad</th><th></th></tr></thead><tbody>
        ${res.pins.rows.map(r => `<tr><td class="num">${esc(r.num)}</td><td class="mono">${esc(r.symbol)}</td><td class="mono">${esc(r.datasheet)}</td><td>${pill(r.status, r.status === "unknown" ? "Ikke fundet" : null)}</td></tr>`).join("")}</tbody></table></div>`;
    }
    h += res.notes.map(n => `<div class="notice info">${esc(n)}</div>`).join("");
    const pages = res.pages || [];
    if (res.datasheet && res.datasheet.startsWith("http") && !res.notes.some(n => /webside|hente/.test(n))) {
      h += `<div class="row" style="margin-top:10px"><span class="sub">Tegningen i databladet:</span>${pages.map(p => pageBtn(p)).join("")}
        ${pages.length ? "" : pageBtn(1, "side 1")}<a class="btn small ghost" href="${esc(res.datasheet)}" target="_blank" rel="noopener">Åbn PDF</a></div>
        <div id="sidePdfWrap" class="hidden"><iframe id="sidePdf" title="Datablad"></iframe></div>`;
    }
    return h;
  }

  function sideBuy(l) {
    const r = state.result, p = l.plan, ch = state.choice[l.id];
    let h = `<p class="hint">Behov ${l.need} stk.${l.need_spare > l.need ? ` + ${l.need_spare - l.need} reserve` : ""} (${l.qty} pr. print × ${r.settings.boards} print).</p>`;
    if (ch) h += `<div class="notice info">Du har valgt <b class="mono">${esc(ch.mpn)}</b> (${esc(ch.mfr)}) hos ${esc(ch.seller)}: ${ch.qty} stk. for ${money(ch.price, ch.currency)}.
      Det ændrer indkøbslisten og kurven – ikke KiCad-projektet. <button class="btn small" data-unchoose="${esc(l.id)}">Fortryd</button></div>`;
    const dists = r.dist_boms.map(d => {
      const m = d.results[l.id];
      return m ? `<li>${pill(m.status, m.status === "missing" ? "Mangler" : null)} <span><b>${esc(d.distributor)}-kurv</b>: ${esc([m.how ? "fundet via " + m.how : "", ...(m.issues || []), m.qty_msg || ""].filter(Boolean).join(" · ") || "ikke i kurven")}</span></li>` : "";
    }).join("");
    if (dists) h += `<ul class="checks">${dists}</ul>`;
    if (p) {
      h += `<div class="tbl-wrap" style="margin-top:8px"><table class="tight"><thead><tr><th>Sælger</th><th class="num">Køb</th><th class="num">Pris</th><th class="num">Lager</th></tr></thead><tbody>
        ${Object.values(p.per_seller).sort((a, b) => a.total - b.total).map(b => `<tr><td>${esc(b.seller)}<div class="sub mono">${b.url ? `<a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.sku)}</a>` : esc(b.sku)} ${esc(b.packaging || "")}</div></td>
        <td class="num">${b.qty}</td><td class="num">${money(b.total, b.currency)}<div class="sub">${money(b.unit)}/stk.</div></td>
        <td class="num ${b.stock != null && b.stock < l.need_spare ? "bad-text" : ""}">${b.stock ?? "–"}</td></tr>`).join("")}</tbody></table></div>
        ${p.best.suggestions.map(s => `<div class="sugg ${s.kind}">${esc(s.text)}</div>`).join("")}`;
    } else if (!dists) {
      h += `<p class="hint">${r.providers.length ? "Ingen tilbud fundet." : "Tilføj en API-nøgle under Indstillinger, eller upload en grosist-BOM, for at se priser og lager."}</p>`;
    }
    const apiRows = (l.api || []).filter(a => a.lifecycle);
    if (apiRows.length) h += `<p class="hint">Livscyklus: ${apiRows.map(a => `${esc(a.source)}: ${esc(a.lifecycle)}`).join(" · ")}</p>`;
    return h;
  }

  function sideAlts(l) {
    const res = state.alts[l.id];
    if (res === "loading") return `<p class="hint">Søger alternativer … (grosisternes rate limits kan gøre det lidt langsomt)</p>`;
    if (res && res.error) return `<div class="notice bad">${esc(res.error)}</div>`;
    if (!res) {
      if (!state.result.providers.length) return `<p class="hint">Alternativer kræver mindst én grosist-API-nøgle (Indstillinger).</p>`;
      return `<button class="btn small" data-alt="${esc(l.id)}">Find alternativer</button> <span class="sub">${l.kind ? "Samme værdi og pakke, mindst lige gode specs." : "Grosisternes egne erstatninger, tjekket for pakke og pinout."}</span>`;
    }
    if (!res.items.length) return `<p class="hint">${esc(res.note)}</p>`;
    const ch = state.choice[l.id];
    return `<p class="hint">${esc(res.note)}</p>` + res.items.map((it, i) => `<div class="alt ${ch && ch.mpn === it.mpn ? "chosen" : ""}">
      <div class="alt-head"><span class="mono"><b>${it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.mpn)}</a>` : esc(it.mpn)}</b></span> <span class="sub">${esc(it.mfr)}</span>
        ${it.sku && it.price != null ? `<button class="btn small ${ch && ch.mpn === it.mpn ? "primary" : ""}" data-choose="${esc(l.id)}" data-i="${i}">${ch && ch.mpn === it.mpn ? "Valgt" : "Vælg"}</button>` : ""}</div>
      <div class="sub">${esc((it.desc || "").slice(0, 110))}</div>
      <div class="row" style="margin-top:4px">
        ${it.fit ? pill({ ok: "ok", partial: "partial", mismatch: "mismatch" }[it.fit] || "unknown", { ok: "Passer på footprint", partial: "Footprint: måske", mismatch: "Passer ikke på footprint", unknown: "Footprint: ukendt" }[it.fit]) : ""}
        ${it.pinout ? pill(it.pinout.status, { ok: "Samme pinout", warn: "Pinout delvist", mismatch: "Anden pinout" }[it.pinout.status]) : ""}
        ${it.same_seller ? `<span class="pill ok">samme grosist</span>` : ""}
        <span class="sub">${esc(it.seller || it.source || "")}${it.price != null ? ` · ${it.qty} stk. ${money(it.price, it.currency)}` : ""}${it.stock != null ? ` · lager ${it.stock}` : ""}</span>
        ${it.datasheet ? `<a class="sub" href="${esc(it.datasheet)}" target="_blank" rel="noopener">datablad</a>` : ""}</div>
      ${it.check ? `<div class="sub" style="color:var(--warn)">${esc(it.check)}</div>` : ""}
      ${it.pinout && it.pinout.status !== "ok" ? `<div class="sub" style="color:var(--warn)">${esc(it.pinout.msg)}</div>` : ""}</div>`).join("");
  }

  function renderSide() {
    const side = $("#side");
    const l = state.result && state.result.lines.find(x => x.id === state.sel);
    if (!l) { side.innerHTML = `<div class="empty">Vælg en komponent i tabellen for at kontrollere den.<div class="sub">Pil op/ned skifter komponent.</div></div>`; return; }
    const fp = l.fp || {};
    const [ds, dsMsg] = dsStat(l), [bs, bsMsg] = buyStat(l);
    if (!(l.id in state.cmp)) loadCompare(l.id);
    if (needsAlt(l) && !state.alts[l.id]) loadAlternatives(l.id);
    const cmp = state.cmp[l.id];
    const dims = cmp && cmp.features ? dimLines(fp.geometry, cmp.features) : undefined;
    const f = cmp && cmp.features;
    side.innerHTML = `
      <div class="side-head">
        <h2>${esc(l.refs.join(", "))}</h2>
        <div>${l.value && l.value !== "~" && l.value !== l.mpn ? `<b>${esc(l.value)}</b> · ` : ""}${mpnCell(l)} ${l.mfr ? `<span class="sub">${esc(l.mfr)}</span>` : ""}</div>
        <div class="sub mono">${esc(l.footprint)}</div>
        <div class="row" style="margin-top:6px">${ctrlPill(fpStat(l), "1 Footprint", "Symbol ↔ footprint")}${ctrlPill(ds, "2 Datablad", dsMsg)}${ctrlPill(bs, "3 Indkøb", bsMsg)}</div>
        ${l.warnings.length ? `<ul class="warnlist">${l.warnings.map(w => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
        ${l.suggested_note ? `<div class="notice info">${esc(l.suggested_note)}</div>` : ""}
      </div>
      <section class="step"><h3><span class="n">1</span>Komponent ↔ footprint ${pill(fpStat(l))}</h3>
        <div class="fp-svg big">${renderFootprint(fp.geometry, fp.overlay && fp.overlay.ref_pads, { details: fp.overlay && fp.overlay.details, dims })}</div>
        ${fpLegend(fp)}
        ${f ? `<p class="sub">Pitch ${mm(f.pitch)} · pad ${f.pad_w ? `${f.pad_w} × ${f.pad_l} mm` : "–"}${Object.values(f.rows).map(r => ` · yder/inder ${r.outer}/${r.inner ?? "–"} mm`).join("")}${f.ep ? ` · termisk pad ${f.ep[0]} × ${f.ep[1]} mm` : ""}${f.body ? ` · krop ${f.body[0]} × ${f.body[1]} mm` : ""}</p>` : ""}
        <ul class="checks">${(fp.checks || []).filter(c => c.check !== "Datablad").map(c => `<li>${pill(c.status)}<span><b>${esc(c.check)}</b><br>${esc(c.msg)}</span></li>`).join("")}</ul>
      </section>
      <section class="step"><h3><span class="n">2</span>Footprint ↔ datablad ${ctrlPill(ds, STATUS_TXT[ds] || "–", dsMsg)}</h3>
        <p class="hint">${esc(dsMsg)}</p>${sideCompare(l)}</section>
      <section class="step"><h3><span class="n">3</span>Indkøb ${ctrlPill(bs, bsMsg)}</h3>${sideBuy(l)}</section>
      <section class="step"><h3><span class="n">4</span>Alternativer</h3>${sideAlts(l)}</section>`;
  }

  async function loadCompare(id) {
    state.cmp[id] = null;
    let res;
    try {
      res = await (await fetch("/api/fpcompare", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job: state.job, line: id }) })).json();
    } catch (e) { res = { error: e.message }; }
    state.cmp[id] = res;
    if (state.sel === id) renderSide();
  }
  async function loadAlternatives(id) {
    state.alts[id] = "loading";
    if (state.sel === id) renderSide();
    let res;
    try {
      res = await (await fetch("/api/alternatives", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ job: state.job, line: id }) })).json();
    } catch (e) { res = { error: e.message }; }
    state.alts[id] = res;
    if (state.sel === id) renderSide();
  }
  function showPage(p) {
    const wrap = $("#sidePdfWrap");
    if (!wrap) return;
    wrap.classList.remove("hidden");
    $("#sidePdf").src = `/api/datasheet/${encodeURIComponent(state.job)}/${encodeURIComponent(state.sel)}?p=${p}#page=${p}`;
    document.querySelectorAll("#side [data-page]").forEach(b => b.classList.toggle("primary", b.dataset.page === String(p)));
  }
  function refreshRow(id) {
    // Re-render the table so the control columns follow a new choice.
    renderTab();
    select(id);
  }

  document.addEventListener("click", e => {
    const exp = e.target.closest("[data-export]");
    if (exp) { exportOrder(exp.dataset.export); return; }
    const dk = e.target.closest("[data-dkcart]");
    if (dk) { digikeyCart(dk.dataset.dkcart); return; }
    const mo = e.target.closest("[data-mocart]");
    if (mo) { mouserCart(mo.dataset.mocart); return; }
    const pg = e.target.closest("#side [data-page]");
    if (pg) { showPage(pg.dataset.page); return; }
    const altBtn = e.target.closest("[data-alt]");
    if (altBtn) { loadAlternatives(altBtn.dataset.alt); return; }
    const choose = e.target.closest("[data-choose]");
    if (choose) {
      const id = choose.dataset.choose, it = state.alts[id].items[+choose.dataset.i];
      state.choice[id] = it;
      refreshRow(id);
      return;
    }
    const un = e.target.closest("[data-unchoose]");
    if (un) { delete state.choice[un.dataset.unchoose]; refreshRow(un.dataset.unchoose); return; }
    const row = e.target.closest("[data-line]");
    if (row && !e.target.closest("a") && !row.closest("#side")) select(row.dataset.line);
  });
  document.addEventListener("keydown", e => {
    if (!state.result || $("#resultView").classList.contains("hidden")) return;
    if (!["ArrowDown", "ArrowUp"].includes(e.key) || (e.target.closest && e.target.closest("input, select, textarea, dialog"))) return;
    const ids = [...new Set([...document.querySelectorAll("#tabBody [data-line]")].map(x => x.dataset.line))];
    if (!ids.length) return;
    e.preventDefault();
    const i = ids.indexOf(state.sel);
    select(ids[Math.max(0, Math.min(ids.length - 1, i < 0 ? 0 : i + (e.key === "ArrowDown" ? 1 : -1)))], true);
  });

  // ---------- export ----------
  function csv(rows) {
    return "﻿" + rows.map(r => r.map(v => {
      v = v == null ? "" : String(v);
      return /[";,\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
    }).join(";")).join("\r\n");
  }
  function download(name, text) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }));
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }
  $("#btnExportBom").onclick = () => {
    const r = state.result;
    const rows = [["Referencer", "Antal pr. print", "Værdi", "Footprint", "MPN", "Producent", "Datablad", "Status", "Footprint-status", "Bemærkninger"]];
    r.lines.forEach(l => rows.push([l.refs.join(","), l.qty, l.value, l.footprint, l.mpn || (l.suggested ? l.suggested[0].mpn + " (forslag)" : ""), l.mfr, l.datasheet, STATUS_TXT[l.status], STATUS_TXT[(l.fp || {}).status] || "", l.warnings.join(" | ")]));
    download(`${r.project.name || "bom"}_BOM.csv`, csv(rows));
  };
  function exportOrder(seller) {
    const r = state.result;
    // Column names that Mouser's and DigiKey's BOM upload tools recognise.
    const rows = [["Manufacturer Part Number", "Distributor Part Number", "Quantity", "Customer Reference", "Seller"]];
    for (const l of r.lines) {
      const b = buyFor(l, seller);
      if (b) rows.push([b.mpn, b.sku, b.qty, l.refs.join(","), b.seller]);
    }
    download(`${r.project.name || "bom"}_indkob_${seller === "*" ? "mix" : seller.replace(/\W+/g, "_")}.csv`, csv(rows));
  }

  loadSettings();
  loadHistory();
  checkUpdates(false);
})();
