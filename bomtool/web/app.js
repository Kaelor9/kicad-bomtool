(function () {
  const $ = s => document.querySelector(s);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const post = (url, body) => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const STATUS = () => ({ ok: t("OK"), warn: t("Check"), partial: t("Partial"), mismatch: t("Error"), missing: t("Missing"), unknown: t("Unknown"), none: "–" });
  const pill = (st, txt) => `<span class="pill ${esc(st)}">${esc(txt || STATUS()[st] || st)}</span>`;
  const dot = (st, tip) => `<span class="dot ${esc(st)}" title="${esc(tip || STATUS()[st] || "")}"></span>`;
  const money = (v, cur) => v == null ? "–" : Number(v).toLocaleString(LANG === "da" ? "da-DK" : "en-GB", { minimumFractionDigits: 2, maximumFractionDigits: v < 1 ? 4 : 2 }) + (cur ? " " + cur : "");
  const intl = v => v == null ? "–" : Number(v).toLocaleString(LANG === "da" ? "da-DK" : "en-GB");
  const KEEP_EXT = /\.(kicad_sch|kicad_pcb|kicad_pro|kicad_mod|kicad_sym)$|(^|\/)(fp-lib-table|sym-lib-table)$/i;
  const stored = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const store = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* private window */ } };

  const files = { project: [], dist: [], refs: [] };
  const state = { job: null, result: null, tab: "bom", alts: {}, cmp: {}, choice: {}, sel: null, filter: null,
    ptab: null, refView: null, libfp: {}, altSort: stored("altSort") || "stock", altMin: +(stored("altMin") || 0) };

  // ---------- language ----------
  function applyStatic() {
    document.documentElement.lang = LANG;
    document.querySelectorAll("[data-t]").forEach(el => {
      if (!el.dataset.src) el.dataset.src = el.textContent.trim();
      el.textContent = t(el.dataset.src);
    });
  }

  // ---------- settings ----------
  async function loadSettings() {
    const cfg = await (await fetch("/api/settings")).json();
    window.LANG = cfg.language || "en";
    applyStatic();
    const form = $("#settingsForm");
    for (const [k, v] of Object.entries(cfg)) if (form.elements[k]) form.elements[k].value = v || "";
    $("#chkUpdates").checked = cfg.check_updates !== "0";
    const names = [];
    if (cfg.digikey_client_id && cfg.digikey_client_secret) names.push("DigiKey");
    if (cfg.mouser_key) names.push("Mouser");
    if (cfg.nexar_client_id && cfg.nexar_client_secret) names.push("Nexar");
    const b = $("#providerBadge");
    b.textContent = names.length ? "API: " + names.join(", ") : t("No distributor API");
    b.className = "badge" + (names.length ? "" : " muted");
    return cfg;
  }
  function formData() {
    const out = {};
    for (const el of $("#settingsForm").elements) if (el.name) out[el.name] = el.value;
    out.check_updates = $("#chkUpdates").checked ? "1" : "0";
    return out;
  }
  $("#btnSettings").onclick = () => { $("#testResult").textContent = ""; $("#settings").showModal(); checkUpdates(false); };
  $("#btnCancel").onclick = () => $("#settings").close();
  $("#btnSave").onclick = async () => {
    const before = LANG;
    await post("/api/settings", formData());
    await loadSettings();
    $("#settings").close();
    if (before !== LANG) location.reload();      // everything is re-rendered in the new language
  };
  $("#btnTest").onclick = async () => {
    await post("/api/settings", formData());
    await loadSettings();
    $("#testResult").textContent = t("Testing …");
    const res = await (await post("/api/test-keys")).json();
    $("#testResult").innerHTML = Object.entries(res).map(([k, v]) =>
      `<div class="${v.ok ? "ok-text" : "bad-text"}"><b>${esc(k)}</b>: ${esc(v.msg)}</div>`).join("");
  };

  // ---------- links & updates ----------
  function openExternal(url) {
    if (window.pywebview && window.pywebview.api) window.pywebview.api.open_url(url);
    else window.open(url, "_blank", "noopener");
  }
  document.addEventListener("click", e => {
    const a = e.target.closest && e.target.closest('a[target="_blank"]');
    if (a && window.pywebview && window.pywebview.api && /^https?:/.test(a.href) && !a.href.startsWith(location.origin)) {
      e.preventDefault(); openExternal(a.href);
    }
  }, true);

  let lastVersion = null;
  async function checkUpdates(force) {
    let v;
    try { v = await (await fetch("/api/version" + (force ? "?force=1" : ""))).json(); } catch (e) { return; }
    lastVersion = v;
    $("#verLabel").textContent = v.current ? "v" + v.current : "";
    $("#verInfo").textContent = t("You have version {v}.", { v: v.current }) + (v.latest ? " " + t("Latest: {v}.", { v: v.latest }) : "")
      + (v.error ? " " + v.error : (force && !v.newer ? " " + t("You have the latest.") : ""));
    $("#btnUpdNow").classList.toggle("hidden", !v.newer);
    const b = $("#updBanner");
    if (!v.newer) { b.classList.add("hidden"); return; }
    b.innerHTML = `<b>${esc(t("Version {v} is ready", { v: v.latest }))}</b> <span class="sub">(${esc(t("you have {v}", { v: v.current }))})</span>
      <button class="btn small primary" data-update>${esc(v.can_install ? t("Update now") : t("Download on GitHub"))}</button>
      <button class="btn small ghost" data-updlater>${esc(t("Later"))}</button>
      ${v.notes ? `<details><summary>${esc(t("What's new"))}</summary>${esc(v.notes)}</details>` : ""}`;
    b.classList.remove("hidden");
  }
  async function updateNow() {
    const v = lastVersion || {};
    if (!v.can_install) { if (v.page) openExternal(v.page); return; }
    const msg = t("Downloading and installing the update … the program restarts in a moment.");
    $("#updBanner").textContent = msg;
    $("#updBanner").classList.remove("hidden");
    $("#verInfo").textContent = msg;
    const r = await (await post("/api/update")).json();
    const txt = r.error ? t("Update failed: {e}", { e: r.error }) : r.msg;
    $("#updBanner").textContent = txt;
    $("#verInfo").textContent = txt;
  }
  document.addEventListener("click", e => {
    if (e.target.closest("[data-update]")) updateNow();
    if (e.target.closest("[data-updlater]")) $("#updBanner").classList.add("hidden");
  });
  $("#btnCheckUpd").onclick = () => checkUpdates(true);
  $("#btnUpdNow").onclick = updateNow;

  // ---------- uploads ----------
  async function upload(kind, file, relPath) {
    const name = relPath || file.webkitRelativePath || file.name;
    const entry = { name, size: file.size, id: null, status: t("uploading …") };
    files[kind].push(entry);
    renderFiles(kind);
    try {
      const r = await fetch("/api/upload", { method: "POST", headers: { "X-Filename": encodeURIComponent(name) }, body: file });
      const j = await r.json();
      if (j.error) throw new Error(j.error);
      entry.id = j.id; entry.status = "";
    } catch (e) { entry.status = t("error: {e}", { e: e.message }); }
    renderFiles(kind);
  }
  function addFiles(kind, list) {
    for (const f of list) {
      const rel = f._rel || f.webkitRelativePath || f.name;
      if (kind === "project" && !/\.zip$/i.test(f.name) && !KEEP_EXT.test(rel)) continue;
      upload(kind, f, rel);
    }
  }
  function renderFiles(kind) {
    const ul = $({ project: "#lProject", dist: "#lDist", refs: "#lRefs" }[kind]);
    const list = files[kind];
    const shown = list.length > 8 ? list.slice(0, 6) : list;
    ul.innerHTML = shown.map((f, i) =>
      `<li><span>${esc(f.name)} <span class="sub">${(f.size / 1024).toFixed(0)} kB ${esc(f.status)}</span></span><button data-k="${kind}" data-i="${i}" title="${esc(t("Remove"))}">×</button></li>`).join("")
      + (list.length > shown.length ? `<li><span class="sub">${esc(t("… and {n} more files", { n: list.length - shown.length }))}</span><button data-k="${kind}" data-i="all">×</button></li>` : "");
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
      shipping: +$("#oShip").value || 0,
      use_api: $("#oApi").checked, suggest_mpn: $("#oSuggest").checked,
      check_datasheets: $("#oDs").checked, save_history: $("#oHist").checked,
    };
  }
  $("#btnRun").onclick = async () => {
    const body = { settings: settings() };
    for (const k of ["project", "dist", "refs"]) body[k] = files[k].filter(f => f.id).map(f => f.id);
    $("#btnRun").disabled = true;
    $("#progress").classList.remove("hidden");
    $("#btnStop").disabled = false;
    const { job, error } = await (await post("/api/analyze", body)).json();
    if (error) return fail(error);
    state.job = job;
    poll();
  };
  $("#btnStop").onclick = async () => {
    $("#btnStop").disabled = true;
    await post("/api/cancel", { job: state.job });
  };
  function fail(msg) {
    $("#progMsg").innerHTML = `<span class="bad-text">${esc(msg)}</span>`;
    $("#btnRun").disabled = false;
    $("#btnStop").disabled = true;
  }
  async function poll() {
    const j = await (await fetch("/api/job/" + state.job)).json();
    $("#progBar").style.width = (j.progress || 0) + "%";
    $("#progMsg").textContent = j.msg || "";
    if (j.state === "running") return setTimeout(poll, 500);
    if (j.state === "error" || j.state === "cancelled") return fail(j.error);
    openResult(j.result);
    $("#btnRun").disabled = false;
  }
  function openResult(result) {
    state.result = result;
    Object.assign(state, { alts: {}, cmp: {}, choice: {}, sel: null, filter: null, diff: null, cart: null });
    showResult();
  }
  $("#btnBack").onclick = () => {
    document.querySelector("main").classList.remove("wide");
    $("#resultView").classList.add("hidden"); $("#inputView").classList.remove("hidden"); $("#progress").classList.add("hidden");
    loadHistory();
  };

  // ---------- history ----------
  let historyList = [];
  async function loadHistory() {
    try { historyList = await (await fetch("/api/history")).json(); } catch (e) { historyList = []; }
    $("#histCard").classList.toggle("hidden", !historyList.length);
    $("#histBody").innerHTML = historyList.slice(0, 30).map(h => {
      const st = Object.entries(h.status || {}).filter(([k]) => k !== "ok");
      return `<tr><td>${esc(h.time)}</td><td>${esc(h.project)}</td><td class="num">${h.parts ?? ""}</td>
        <td>${st.length ? st.map(([k, v]) => `${dot(k)} ${v}`).join(" &nbsp;") : pill("ok")}</td><td class="num">${h.total ? money(h.total) : "–"}</td>
        <td class="num"><button class="btn small" data-hopen="${esc(h.id)}">${esc(t("Open"))}</button> <button class="btn small ghost" data-hdel="${esc(h.id)}" title="${esc(t("Delete"))}">×</button></td></tr>`;
    }).join("");
  }
  document.addEventListener("click", async e => {
    const o = e.target.closest("[data-hopen]"), d = e.target.closest("[data-hdel]");
    if (o) {
      const res = await (await post("/api/history/open", { id: o.dataset.hopen })).json();
      if (res.error) return alert(res.error);
      state.job = res.job;
      openResult(res.result);
    } else if (d) {
      if (!confirm(t("Delete this analysis from history?"))) return;
      await post("/api/history/delete", { id: d.dataset.hdel });
      loadHistory();
    }
  });

  // ---------- the three checks ----------
  const ORDER = { ok: 0, none: 0, unknown: 1, partial: 1, warn: 2, missing: 3, mismatch: 4 };
  const worst = list => list.reduce((a, b) => (ORDER[b] ?? 1) > (ORDER[a] ?? 1) ? b : a, "ok");
  const isDsCheck = c => c.check === "Datablad" || c.check === "Datasheet";
  function fpStat(l) {
    const cs = ((l.fp || {}).checks || []).filter(c => !isDsCheck(c));
    return cs.length ? worst(cs.map(c => c.status)) : ((l.fp || {}).status || "unknown");
  }
  function dsStat(l) {
    const c = ((l.fp || {}).checks || []).find(isDsCheck);
    if (c) return [c.status, c.msg];
    if (l.kind) return ["none", t("Passives are checked against MPN patterns and IPC sizes, not the datasheet.")];
    return l.datasheet ? ["unknown", t("The datasheet was not read.")] : ["none", t("No datasheet link.")];
  }
  function buyStat(l) {
    const r = state.result, ch = state.choice[l.id];
    if (ch) return ["ok", t("Alternative chosen: {m}", { m: ch.mpn })];
    const ds = r.dist_boms.map(d => d.results[l.id]).filter(Boolean);
    if (ds.length) {
      const st = worst(ds.map(m => m.status));
      return [st, { ok: t("Matches the cart"), missing: t("Missing from the cart") }[st] || t("Differs from the cart")];
    }
    if (l.plan) {
      if (l.plan.best.impractical) return ["mismatch", t("Full reel only ({n} pcs)", { n: l.plan.best.qty })];
      const s = l.plan.best.stock;
      if (s != null && s < l.need_spare) return [s ? "warn" : "mismatch", s ? t("Only {n} in stock", { n: s }) : t("Out of stock")];
      if (l.warnings.some(w => /Livscyklus|Lifecycle|NRND|udgået|obsolete/i.test(w))) return ["warn", t("Obsolete / NRND")];
      return ["ok", `${l.plan.best.seller} · ${money(l.plan.best.total)}`];
    }
    if (r.providers.length && (l.mpn || l.mpn_guess)) return ["mismatch", t("Not found at the distributors")];
    return ["unknown", r.providers.length ? t("No MPN to buy by") : t("No purchase data (API key or distributor BOM)")];
  }
  const CHECKS = {
    fp: { n: 1, label: "Footprint", stat: l => fpStat(l) },
    ds: { n: 2, label: "Datasheet", stat: l => dsStat(l)[0] },
    buy: { n: 3, label: "Purchase", stat: l => buyStat(l)[0] },
  };
  const isBad = st => ORDER[st] >= 3;
  const isWarn = st => st === "warn" || st === "partial";

  // ---------- results ----------
  const curOf = r => (r.lines.find(l => l.plan) || {}).plan?.best.currency || "";
  function showResult() {
    const r = state.result;
    $("#inputView").classList.add("hidden");
    $("#resultView").classList.remove("hidden");
    document.querySelector("main").classList.add("wide");
    $("#rTitle").textContent = r.project.name || t("Project");
    const v = r.project.version;
    $("#rSub").textContent = `KiCad ${v.sch_generator || v.pcb_generator || "?"} · ${r.project.components} ${t("parts")} · ${r.lines.length} ${t("BOM lines")} · ${r.settings.boards} ${t(r.settings.boards === 1 ? "board" : "boards")}`;
    renderTiles();
    const notes = [];
    if (!r.providers.length && r.settings.use_api)
      notes.push(["info", t("No distributor API set up – prices, stock and alternatives need at least one key (Settings). Everything else works without.")]);
    r.errors.forEach(e => notes.push(["bad", e]));
    r.project.warnings.forEach(w => notes.push(["warn", w]));
    const html = notes.map(([c, x]) => `<div class="notice ${c}">${esc(x)}</div>`).join("");
    $("#notices").innerHTML = notes.length > 2 ? `<details class="notices"><summary>${esc(t("{n} project notes", { n: notes.length }))}</summary>${html}</details>` : html;
    $("#tabs [data-tab=dist]").classList.toggle("hidden", !r.dist_boms.length);
    renderTab();
    renderBoardView();
    const first = r.lines.find(l => ["fp", "ds", "buy"].some(k => isBad(CHECKS[k].stat(l)))) || r.lines.find(l => l.status !== "ok") || r.lines[0];
    if (first) select(first.id, true); else renderSide();
  }

  function renderTiles() {
    const r = state.result, cur = curOf(r);
    const tiles = Object.entries(CHECKS).map(([k, c]) => {
      const sts = r.lines.map(c.stat);
      const nb = sts.filter(isBad).length, nw = sts.filter(isWarn).length, nok = sts.filter(st => st === "ok").length;
      const cls = nb ? "bad" : nw ? "warn" : "ok";
      return `<button class="tile ctrl-tile ${cls} ${state.filter === k ? "on" : ""}" data-filter="${k}">
        <div class="k">${c.n} ${esc(t(c.label))}</div>
        <div class="v">${nb ? esc(t("{n} errors", { n: nb })) : nw ? esc(t("{n} to check", { n: nw })) : esc(t("All OK"))}</div>
        <div class="s">${nok} OK${nb && nw ? ` · ${esc(t("{n} to check", { n: nw }))}` : ""}${state.filter === k ? " · " + esc(t("filtering")) : ""}</div></button>`;
    });
    const tot = r.totals || {};
    if (tot.lines_priced) {
      const sh = tot.shipping;
      tiles.push(`<div class="tile"><div class="k">${esc(sh ? t("Cheapest incl. freight") : t("Total"))}</div>
        <div class="v">${money(sh ? sh.total_with_shipping : tot.mix, cur)}</div>
        <div class="s">${esc(t("{a} of {b} lines priced", { a: tot.lines_priced, b: r.lines.length }))}${tot.lines_unbuyable ? " · " + esc(t("{n} full reel only", { n: tot.lines_unbuyable })) : ""}</div></div>`);
    }
    $("#tiles").innerHTML = tiles.join("");
  }
  document.addEventListener("click", e => {
    const tl = e.target.closest("[data-filter]");
    if (!tl) return;
    state.filter = state.filter === tl.dataset.filter ? null : tl.dataset.filter;
    renderTiles();
    renderTab();
  });

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
    const f = state.filter && CHECKS[state.filter];
    return state.result.lines.filter(l => (!only || l.status !== "ok") && (!f || isBad(f.stat(l)) || isWarn(f.stat(l))));
  }
  function renderTab() {
    const f = { bom: tabBom, buy: tabBuy, dist: tabDist, excl: tabExcl, diff: tabDiff }[state.tab];
    $("#tabBody").innerHTML = f();
    if (state.sel) document.querySelectorAll(`#tabBody [data-line="${CSS.escape(state.sel)}"]`).forEach(e => e.classList.add("sel"));
  }
  function mpnCell(l) {
    if (l.mpn) return `<span class="mono">${esc(l.mpn)}</span>`;
    if (l.suggested) return `<span class="sub">${esc(t("suggestion:"))}</span> <span class="mono">${esc(l.suggested[0].mpn)}</span>`;
    if (l.mpn_guess) return `<span class="mono">${esc(l.mpn_guess)}</span> <span class="sub">(${esc(t("from value"))})</span>`;
    return `<span class="sub">– ${esc(t("no MPN"))} –</span>`;
  }

  function tabBom() {
    const rows = visibleLines().map(l => {
      const [ds, dsMsg] = dsStat(l), [bs, bsMsg] = buyStat(l), fs = fpStat(l);
      const fpMsg = ((l.fp || {}).checks || []).filter(c => c.status !== "ok" && !isDsCheck(c)).map(c => c.msg)[0] || STATUS()[fs];
      return `<tr data-line="${esc(l.id)}">
        <td class="num">${l.qty}</td>
        <td class="refs">${esc(l.refs.join(", "))}</td>
        <td title="${esc(l.desc || "")}">${esc(l.value && l.value !== "~" ? l.value : (l.desc || "").slice(0, 28))}</td>
        <td class="clip">${mpnCell(l)}${l.mfr ? `<div class="sub">${esc(l.mfr)}</div>` : ""}</td>
        <td class="mono clip" title="${esc(l.footprint)}">${esc(l.footprint.split(":").pop())}</td>
        <td class="ctrl">${dot(fs, fpMsg)}</td><td class="ctrl">${dot(ds, dsMsg)}</td>
        <td class="ctrl">${dot(bs, bsMsg)}${state.choice[l.id] ? ` <span class="sub">${esc(t("alt."))}</span>` : ""}</td>
      </tr>`;
    }).join("");
    return `<div class="tbl-wrap"><table class="bom"><thead><tr><th class="num">${esc(t("Qty"))}</th><th>${esc(t("References"))}</th><th>${esc(t("Value"))}</th><th>MPN</th><th>Footprint</th>
      <th class="ctrl" title="${esc(t("Do the symbol and footprint fit together?"))}">1 FP</th><th class="ctrl" title="${esc(t("Does the footprint match the datasheet?"))}">2 DS</th><th class="ctrl" title="${esc(t("Can it be bought as chosen?"))}">3 ${esc(t("Buy"))}</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="8" class="empty">${esc(t("No lines"))}</td></tr>`}</tbody></table></div>`;
  }

  function tabBuy() {
    const r = state.result, cur = curOf(r), tot = r.totals || {};
    const lines = visibleLines();
    if (!lines.some(l => l.plan)) return `<div class="empty">${esc(t("No prices. Add an API key in Settings, or upload a distributor BOM with prices."))}</div>`;
    const sellers = [...new Set(lines.flatMap(l => l.plan ? Object.keys(l.plan.per_seller) : []))];
    const total = lines.reduce((s, l) => { const b = buyFor(l, "*"); return s + (b && b.total ? b.total : 0); }, 0);
    const rows = lines.map(l => {
      const p = l.plan, ch = state.choice[l.id];
      if (!p && !ch) return `<tr data-line="${esc(l.id)}"><td class="refs">${esc(l.refs.join(", "))}</td><td class="mono">${esc(l.mpn || l.value)}</td><td class="num">${l.need_spare}</td><td colspan="5" class="sub">${esc(t("No price found"))}</td></tr>`;
      const b = ch ? { qty: ch.qty, seller: ch.seller, sku: ch.sku, unit: ch.unit, total: ch.price, stock: ch.stock, suggestions: [] } : p.best;
      const tips = (b.suggestions || []).map(s => `<span class="tip ${s.kind}" title="${esc(s.text)}">${s.kind === "save" ? "−" + money(b.saved || 0) : "+"}</span>`).join("");
      const stockBad = b.stock != null && b.stock < l.need_spare;
      return `<tr data-line="${esc(l.id)}">
        <td class="refs">${esc(l.refs.join(", "))}</td>
        <td><span class="mono">${esc(ch ? ch.mpn : (l.mpn || (l.suggested ? l.suggested[0].mpn : l.value)))}</span>${ch ? ` <span class="pill ok">${esc(t("alt."))}</span>` : ""}</td>
        <td class="num">${l.need}${l.need_spare > l.need ? `<span class="sub">+${l.need_spare - l.need}</span>` : ""}</td>
        <td class="num"><b>${b.qty}</b></td>
        <td>${esc(b.seller)} <span class="sub mono">${esc(b.sku)}</span>${b.impractical ? ` <span class="pill mismatch">${esc(t("full reel"))}</span>` : ""}</td>
        <td class="num">${money(b.unit)}</td>
        <td class="num"><b>${money(b.total)}</b>${tips}</td>
        <td class="num ${stockBad ? "bad-text" : ""}">${intl(b.stock)}</td>
      </tr>`;
    }).join("");
    const exp = sellers.map(s => `<button data-export="${esc(s)}">${esc(t("Order list: {s} (CSV)", { s }))}</button>`).join("")
      + `<button data-export="*">${esc(t("Cheapest mix (CSV)"))}</button>`;
    const carts = sellers.filter(s => /^digi-?key$/i.test(s)).map(s => `<button class="btn small primary" data-dkcart="${esc(s)}">${esc(t("Add to DigiKey cart"))}</button>`).join("")
      + sellers.filter(s => /^mouser$/i.test(s)).map(s => `<button class="btn small primary" data-mocart="${esc(s)}">${esc(t("Add to Mouser cart"))}</button>`).join("");
    return `<div class="buy-sum">
        <div><div class="k">${esc(t("Total"))}</div><div class="big">${money(tot.shipping ? tot.shipping.total_with_shipping : total, cur)}</div></div>
        <div><div class="k">${esc(t("Lines priced"))}</div><b>${tot.lines_priced || 0} / ${r.lines.length}</b></div>
        ${tot.saved_breaks ? `<div><div class="k">${esc(t("Saved by price breaks"))}</div><b class="ok-text">${money(tot.saved_breaks, cur)}</b></div>` : ""}
        ${tot.lines_unbuyable ? `<div><div class="k">${esc(t("Full reel only"))}</div><b class="bad-text">${tot.lines_unbuyable}</b></div>` : ""}
        ${tot.shipping ? `<div><div class="k">${esc(t("Distributors"))}</div><b>${esc(tot.shipping.sellers.join(", "))}</b></div>` : ""}
        <div class="grow"></div>
        <div class="row">${carts}<span class="menu"><button class="btn small" data-menu>${esc(t("Export"))} ▾</button><div class="hidden">${exp}</div></span></div>
      </div>${cartBox()}
      <div class="tbl-wrap"><table><thead><tr><th>${esc(t("References"))}</th><th>${esc(t("Part"))}</th><th class="num">${esc(t("Need"))}</th><th class="num">${esc(t("Buy"))}</th><th>${esc(t("From"))}</th><th class="num">${esc(t("Unit"))}</th><th class="num">${esc(t("Line"))}</th><th class="num">${esc(t("Stock"))}</th></tr></thead>
      <tbody>${rows}</tbody><tfoot><tr><th colspan="6">${esc(t("Total"))}</th><th class="num">${money(total, cur)}</th><th></th></tr></tfoot></table></div>
      <p class="hint" style="margin-top:8px">${esc(t("Need = quantity × {n} boards (+ spares). \"Buy\" is the cheapest quantity after price breaks, MOQ and packaging. Green badges: money saved by buying more; blue: much more for a little extra (hover).", { n: r.settings.boards }))}</p>`;
  }
  document.addEventListener("click", e => {
    const m = e.target.closest("[data-menu]");
    document.querySelectorAll(".menu > div").forEach(d => { if (!m || d !== m.nextElementSibling) d.classList.add("hidden"); });
    if (m) m.nextElementSibling.classList.toggle("hidden");
  });

  function tabDist() {
    const r = state.result;
    if (!r.dist_boms.length) return `<div class="empty">${esc(t("No distributor BOM uploaded."))}</div>`;
    return r.dist_boms.map(d => {
      const rows = visibleLines().map(l => {
        const m = d.results[l.id] || {};
        const dl = m.dist_line;
        const issues = (m.issues || []).concat(m.qty_msg ? [m.qty_msg] : []);
        return `<tr data-line="${esc(l.id)}"><td>${dot(m.status || "missing")}</td><td class="refs">${esc(l.refs.join(", "))}</td>
          <td class="mono">${esc(l.mpn || l.value)}</td><td class="mono">${dl ? esc(dl.mpn) : ""}<div class="sub">${dl ? esc(dl.dist_pn) : ""}</div></td>
          <td class="num">${l.need}</td><td class="num">${dl ? (dl.qty ?? "?") : "–"}</td>
          <td class="sub">${esc([m.how ? t("matched via {h}", { h: m.how }) : "", ...issues].filter(Boolean).join(" · "))}</td></tr>`;
      }).join("");
      const extras = d.extras.length ? `<h3 style="margin-top:14px">${esc(t("In the cart but not in the project ({n})", { n: d.extras.length }))}</h3><div class="tbl-wrap"><table class="tight"><tbody>${d.extras.map(e => `<tr><td class="mono">${esc(e.mpn)}</td><td class="mono">${esc(e.dist_pn)}</td><td class="num">${e.qty ?? ""}</td><td>${esc(e.desc)}</td></tr>`).join("")}</tbody></table></div>` : "";
      return `<h3>${esc(d.distributor)} – ${esc(d.name)}</h3><div class="tbl-wrap"><table class="tight"><thead><tr><th></th><th>${esc(t("References"))}</th><th>${esc(t("Project"))}</th><th>${esc(t("File"))}</th><th class="num">${esc(t("Need"))}</th><th class="num">${esc(t("Ordered"))}</th><th>${esc(t("Notes"))}</th></tr></thead><tbody>${rows}</tbody></table></div>${extras}`;
    }).join("");
  }
  function tabExcl() {
    const ex = state.result.excluded;
    if (!ex.length) return `<div class="empty">${esc(t("Nothing excluded."))}</div>`;
    return `<div class="tbl-wrap"><table class="tight"><thead><tr><th>${esc(t("Reference"))}</th><th>${esc(t("Why"))}</th><th>Footprint</th></tr></thead><tbody>${ex.map(e => `<tr><td>${esc(e.ref)}</td><td>${esc(e.why)}</td><td class="mono">${esc(e.footprint)}</td></tr>`).join("")}</tbody></table></div>`;
  }
  function tabDiff() {
    const r = state.result;
    const older = historyList.filter(h => h.id !== r.history_id && h.project === r.project.name);
    if (!older.length) return `<div class="empty">${esc(t("No earlier analyses of \"{p}\" to compare with.", { p: r.project.name }))}</div>`;
    const sel = `<label class="inline" style="margin-bottom:10px">${esc(t("Compare with"))} <select id="diffSel">${older.map(h => `<option value="${esc(h.id)}" ${state.diff && state.diff.id === h.id ? "selected" : ""}>${esc(h.time)} – ${h.parts}</option>`).join("")}</select></label>`;
    if (!state.diff) { setTimeout(() => loadDiff(older[0].id), 0); return sel + `<p class="hint">${esc(t("Comparing …"))}</p>`; }
    const d = state.diff.data;
    const tbl = (title, rows, head) => rows.length ? `<h3 style="margin-top:12px">${esc(title)} (${rows.length})</h3><div class="tbl-wrap"><table class="tight"><thead><tr>${head.map(h => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>` : "";
    const row = x => `<tr><td>${esc(x.ref)}</td><td>${esc(x.value)}</td><td class="mono">${esc((x.footprint || "").split(":").pop())}</td><td class="mono">${esc(x.mpn)}</td></tr>`;
    return sel + (d.added.length + d.removed.length + d.changed.length === 0 ? `<div class="empty">${esc(t("No changes to the parts."))}</div>` : "")
      + tbl(t("Added"), d.added.map(row), [t("Ref"), t("Value"), "Footprint", "MPN"])
      + tbl(t("Removed"), d.removed.map(row), [t("Ref"), t("Value"), "Footprint", "MPN"])
      + tbl(t("Changed"), d.changed.map(x => `<tr><td>${esc(x.ref)}</td><td>${esc(x.field)}</td><td class="mono">${esc(x.old)}</td><td class="mono">${esc(x.new)}</td></tr>`), [t("Ref"), t("Field"), t("Before"), t("Now")]);
  }
  async function loadDiff(id) {
    const res = await (await post("/api/compare", { job: state.job, id })).json();
    if (res.error) { $("#tabBody").innerHTML = `<div class="notice bad">${esc(res.error)}</div>`; return; }
    state.diff = { id, data: res };
    if (state.tab === "diff") renderTab();
  }
  document.addEventListener("change", e => { if (e.target.id === "diffSel") loadDiff(e.target.value); });

  // ---------- purchase: what is bought, carts, exports ----------
  function buyFor(l, seller) {
    const ch = state.choice[l.id];
    if (ch) return seller === "*" || ch.seller === seller ? { sku: ch.sku, qty: ch.qty, seller: ch.seller, mpn: ch.mpn, total: ch.price } : null;
    if (!l.plan || l.plan.best.impractical) return null;
    const b = seller === "*" ? l.plan.best : l.plan.per_seller[seller];
    return b ? { sku: b.sku, qty: b.qty, seller: b.seller, mpn: l.mpn || (l.suggested ? l.suggested[0].mpn : ""), total: b.total } : null;
  }
  function cartItems(seller) { return state.result.lines.map(l => ({ l, b: buyFor(l, seller) })).filter(x => x.b && x.b.sku); }
  function digikeyCart(seller) {
    const items = cartItems(seller);
    if (window.pywebview && window.pywebview.api) {
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
    state.cart = await (await post("/api/cart/mouser", { job: state.job, seller })).json();
    renderTab();
  }
  function cartBox() {
    const c = state.cart;
    if (!c) return "";
    if (c.busy) return `<div class="notice info">${esc(t("Adding to the Mouser cart …"))}</div>`;
    if (c.error) return `<div class="notice bad">Mouser: ${esc(c.error)}</div>`;
    const bad = c.lines.filter(x => x.errors.length);
    return `<div class="notice info">${esc(t("Mouser cart created: {n} lines, {total} (Mouser's own price). Cart key: {k}. Log in on mouser.com with the account the API key belongs to.", { n: c.lines.length, total: money(c.total, c.currency), k: c.cart_key }))}
      ${bad.length ? `<ul class="warnlist">${bad.map(x => `<li>${esc(x.sku)}: ${esc(x.errors.join(" "))}</li>`).join("")}</ul>` : ""}</div>`;
  }
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
  $("#btnExportXlsx").onclick = async () => {
    const r = state.result;
    const res = await post("/api/export/xlsx", { job: state.job, choices: state.choice });
    if (!res.ok) { alert((await res.json()).error || "Export failed"); return; }
    const a = document.createElement("a");
    a.href = URL.createObjectURL(await res.blob());
    a.download = `${r.project.name || "bom"}_BOM.xlsx`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };
  $("#btnExportBom").onclick = () => {
    const r = state.result;
    const rows = [[t("References"), t("Qty"), t("Value"), "Footprint", "MPN", t("Manufacturer"), t("Datasheet"), "1 Footprint", "2 " + t("Datasheet"), "3 " + t("Purchase"), t("Notes")]];
    r.lines.forEach(l => rows.push([l.refs.join(","), l.qty, l.value, l.footprint, (state.choice[l.id] || {}).mpn || l.mpn, l.mfr, l.datasheet,
      STATUS()[fpStat(l)], STATUS()[dsStat(l)[0]], STATUS()[buyStat(l)[0]], l.warnings.join(" | ")]));
    download(`${r.project.name || "bom"}_BOM.csv`, csv(rows));
  };
  function exportOrder(seller) {
    const r = state.result;
    const rows = [["Manufacturer Part Number", "Distributor Part Number", "Quantity", "Customer Reference", "Seller"]];
    for (const l of r.lines) { const b = buyFor(l, seller); if (b) rows.push([b.mpn, b.sku, b.qty, l.refs.join(","), b.seller]); }
    download(`${r.project.name || "bom"}_order_${seller === "*" ? "mix" : seller.replace(/\W+/g, "_")}.csv`, csv(rows));
  }

  // ---------- board ----------
  let board = null;
  const lineOfRef = ref => state.result.lines.find(l => l.refs.includes(ref));
  function renderBoardView() {
    const r = state.result;
    const has = r.board && Object.keys(r.board.parts || {}).length;
    $("#boardBox").classList.toggle("hidden", !has);
    if (!has) { board = null; return; }
    board = new BoardView($("#boardHost"), r.board, ref => {
      const l = lineOfRef(ref);
      if (!l) return "";
      const sts = ["fp", "ds", "buy"].map(k => CHECKS[k].stat(l));
      return sts.some(isBad) ? "mismatch" : sts.some(isWarn) ? "warn" : "ok";
    }, ref => { const l = lineOfRef(ref); if (l) select(l.id, true, false); });
  }

  // ---------- control panel ----------
  function select(id, scroll, zoomBoard = true) {
    const changed = state.sel !== id;
    state.sel = id;
    document.querySelectorAll("[data-line].sel").forEach(e => e.classList.remove("sel"));
    document.querySelectorAll(`#tabBody [data-line="${CSS.escape(id)}"]`).forEach(e => { e.classList.add("sel"); if (scroll) e.scrollIntoView({ block: "nearest" }); });
    const l = state.result.lines.find(x => x.id === id);
    if (board && l) board.select(l.refs, zoomBoard);
    if (changed && l) {
      // open the panel on the first check with a problem; a part that can't be bought opens on its alternatives
      const order = [["fp", fpStat(l)], ["ds", dsStat(l)[0]], ["buy", buyStat(l)[0]]];
      const bad = order.find(([, st]) => isBad(st)) || order.find(([, st]) => isWarn(st));
      state.ptab = bad ? (bad[0] === "buy" && isBad(bad[1]) && state.result.providers.length ? "alt" : bad[0]) : "fp";
    }
    renderSide();
  }

  function renderSide() {
    const side = $("#side");
    const l = state.result && state.result.lines.find(x => x.id === state.sel);
    if (!l) { side.innerHTML = `<div class="empty">${esc(t("Select a part in the table."))}<div class="sub">${esc(t("Up/down arrows change part."))}</div></div>`; return; }
    if (!(l.id in state.cmp)) loadCompare(l.id);
    if (state.result.providers.length && !state.alts[l.id]) loadAlternatives(l.id);
    const [ds, dsMsg] = dsStat(l), [bs, bsMsg] = buyStat(l), fs = fpStat(l);
    const altRes = state.alts[l.id];
    const altSt = altRes && altRes.items ? (altRes.items.length ? "ok" : "none") : "unknown";
    const tabs = [["fp", "Footprint", fs, ""], ["ds", "Datasheet", ds, dsMsg], ["buy", "Purchase", bs, bsMsg], ["alt", "Alternatives", altSt, ""]];
    const body = { fp: pFootprint, ds: pDatasheet, buy: pBuy, alt: pAlts }[state.ptab || "fp"](l);
    side.innerHTML = `<div class="side-head">
        <h2>${esc(l.refs.join(", "))}</h2>
        <div>${l.value && l.value !== "~" && l.value !== l.mpn ? `<b>${esc(l.value)}</b> · ` : ""}${mpnCell(l)} ${l.mfr ? `<span class="sub">${esc(l.mfr)}</span>` : ""}</div>
        <div class="sub mono">${esc(l.footprint)}</div>
        ${l.warnings.length ? `<ul class="warnlist">${l.warnings.slice(0, 3).map(w => `<li>${esc(w)}</li>`).join("")}${l.warnings.length > 3 ? `<li>${esc(t("… {n} more", { n: l.warnings.length - 3 }))}</li>` : ""}</ul>` : ""}
        <div class="ptabs">${tabs.map(([k, label, st, tip]) => `<button class="${(state.ptab || "fp") === k ? "on" : ""}" data-ptab="${k}" title="${esc(tip)}">${dot(st)}${esc(t(label))}${k === "alt" && altRes && altRes.items ? ` <span class="sub">${altRes.items.length}</span>` : ""}</button>`).join("")}</div>
      </div><div class="pbody">${body}</div>`;
    hydrateThumbs();
  }

  const mm = v => v == null ? "–" : `${v} mm`;
  function pFootprint(l) {
    const fp = l.fp || {}, cmp = state.cmp[l.id], f = cmp && cmp.features;
    const dsFp = cmp && cmp.ds_footprint;
    const refs = [];
    if (dsFp) refs.push({ key: "ds", name: t("Datasheet"), label: dsFp.label, pads: dsFp.pads, body: dsFp.body });
    if (fp.overlay && fp.overlay.ref_pads) refs.push({ key: "lib", name: /producent|manufacturer/i.test(fp.overlay.ref_label) ? t("Manufacturer CAD") : /IPC/.test(fp.overlay.ref_label) ? "IPC" : t("KiCad library"), label: fp.overlay.ref_label, pads: fp.overlay.ref_pads });
    refs.push({ key: "none", name: t("None"), label: "", pads: null });
    const cur = refs.find(r => r.key === state.refView) || refs[0];
    const checks = (fp.checks || []).filter(c => !isDsCheck(c));
    const rec = (fp.recognised || [])[0];
    return `${refs.length > 1 ? `<div class="row"><span class="sub">${esc(t("Overlay:"))}</span><span class="seg">${refs.map(r => `<button class="${r === cur ? "on" : ""}" data-refview="${r.key}">${esc(r.name)}</button>`).join("")}</span></div>` : ""}
      <div class="fp-svg">${renderFootprint(fp.geometry, cur.pads, { details: cur.key === "lib" ? fp.overlay.details : null, dims: true, refBody: cur.body })}</div>
      <div class="legend"><span><i class="hatch"></i>${esc(t("Your footprint"))}</span>${cur.label ? `<span><i class="dash"></i>${esc(cur.label)}</span>` : ""}<span><i style="background:var(--bad);border-radius:50%"></i>${esc(t("Pin 1"))}</span><span style="color:var(--dim)">${esc(t("Dimensions in mm"))}</span></div>
      ${f ? `<div class="meas"><div><span>${esc(t("Pads"))}</span>${f.pads}</div><div><span>Pitch</span>${mm(f.pitch)}</div><div><span>${esc(t("Pad (w × l)"))}</span>${f.pad_w ? `${f.pad_w} × ${f.pad_l}` : "–"}</div>
        ${Object.values(f.rows).slice(0, 1).map(r => `<div><span>${esc(t("Outer / gap"))}</span>${r.outer} / ${r.inner ?? "–"}</div>`).join("")}
        ${f.ep ? `<div><span>${esc(t("Thermal pad"))}</span>${f.ep[0]} × ${f.ep[1]}</div>` : ""}${f.body ? `<div><span>${esc(t("Body (Fab)"))}</span>${f.body[0]} × ${f.body[1]}</div>` : ""}</div>` : ""}
      ${rec ? `<div class="recog">${esc(t("Recognised as"))} <b class="mono">${esc(rec.id)}</b> <span class="sub">(${rec.similarity} % ${esc(t("alike"))})</span>${(fp.recognised || []).slice(1).map(x => `<div class="sub mono">${esc(x.id)} · ${x.similarity} %</div>`).join("")}</div>` : ""}
      ${!dsFp && cmp && !cmp.error && !l.kind ? `<p class="sub">${esc(cmp.dims ? t("The datasheet footprint can't be drawn: the dimension table lacks b, L or e.") : t("The datasheet has no dimension table as text – see the drawing under Datasheet."))}</p>` : ""}
      <h4>${esc(t("Checks"))}</h4>
      <ul class="checks">${checks.map(c => `<li>${dot(c.status)}<span><b>${esc(c.check)}</b><br><span class="sub">${esc(c.msg)}</span></span></li>`).join("")}</ul>`;
  }

  function cmpTable(rows) {
    return `<div class="tbl-wrap"><table class="tight"><thead><tr><th>${esc(t("Measure"))}</th><th class="num">${esc(t("Datasheet"))}</th><th class="num">Footprint</th><th></th></tr></thead><tbody>${rows.map(r => `<tr title="${esc(r.note)}"><td>${esc(r.what)}${r.note ? `<div class="sub">${esc(r.note)}</div>` : ""}</td><td class="num">${esc(r.ds)}</td><td class="num">${esc(r.fp)}</td><td>${dot(r.status)}</td></tr>`).join("")}</tbody></table></div>`;
  }
  function pDatasheet(l) {
    const [ds, dsMsg] = dsStat(l), cmp = state.cmp[l.id];
    let h = `<p class="hint">${dot(ds)} ${esc(dsMsg)}</p>`;
    if (!l.datasheet || !l.datasheet.startsWith("http")) return h + `<div class="empty">${esc(t("No datasheet link on this part."))}</div>`;
    const pic = k => `<div class="ds-pic"><div class="cap">${esc(k === "land" ? t("Recommended footprint (from the datasheet)") : t("Package drawing (from the datasheet)"))}</div>
      <img alt="" loading="lazy" data-dspic="${k}" title="${esc(t("Click to open the page"))}" src="/api/dsimage/${encodeURIComponent(state.job)}/${encodeURIComponent(l.id)}?kind=${k}" onerror="this.parentNode.classList.add('hidden')"></div>`;
    h += `<div class="ds-pics">${pic("land")}${pic("outline")}</div>`;
    if (!cmp) return h + `<p class="hint">${esc(t("Reading the datasheet …"))}</p>`;
    if (cmp.error) return h + `<div class="notice bad">${esc(cmp.error)}</div>`;
    if (cmp.dims) {
      h += `<h4>${esc(t("Package dimensions"))}: ${esc(cmp.dims.name)} <span class="sub">${esc(t("p. {p}", { p: cmp.dims.page }))}</span></h4>
        ${cmp.dims.sure ? "" : `<p class="hint warn-text">${esc(t("The table could not be tied to the footprint's package with certainty."))}</p>`}${cmpTable(cmp.dims.rows)}`;
    }
    if (cmp.land) h += `<h4>${esc(t("Recommended land pattern"))} ${esc(cmp.land.label)}</h4><p class="hint">${esc(t("Letters mean different things at each maker – values that exist in your footprint are marked."))}</p>${cmpTable(cmp.land.rows)}`;
    if (cmp.pins) {
      h += `<h4>${esc(t("Pinout: symbol ↔ datasheet"))} ${dot(cmp.pins.status)}</h4><p class="hint">${esc(cmp.pins.summary)}</p>
        <div class="tbl-wrap"><table class="tight"><thead><tr><th class="num">${esc(t("Pin"))}</th><th>${esc(t("Symbol"))}</th><th>${esc(t("Datasheet"))}</th><th></th></tr></thead><tbody>
        ${cmp.pins.rows.map(r => `<tr><td class="num">${esc(r.num)}</td><td class="mono">${esc(r.symbol)}</td><td class="mono">${esc(r.datasheet)}</td><td>${dot(r.status)}</td></tr>`).join("")}</tbody></table></div>`;
    }
    h += cmp.notes.map(n => `<div class="notice info">${esc(n)}</div>`).join("");
    const pages = cmp.pages || [];
    h += `<div class="row" style="margin-top:10px"><span class="sub">${esc(t("Datasheet pages:"))}</span>${(pages.length ? pages : [1]).map(p => `<button class="btn small" data-page="${p}">${esc(t("p. {p}", { p }))}</button>`).join("")}
      <a class="btn small ghost" href="${esc(l.datasheet)}" target="_blank" rel="noopener">${esc(t("Open PDF"))}</a></div><div id="sidePdfWrap" class="hidden"><iframe id="sidePdf" title="PDF"></iframe></div>`;
    return h;
  }

  function pBuy(l) {
    const r = state.result, p = l.plan, ch = state.choice[l.id];
    const [bs, bsMsg] = buyStat(l);
    let h = `<p class="hint">${dot(bs)} ${esc(bsMsg)} · ${esc(t("need {n} pcs", { n: l.need }))}${l.need_spare > l.need ? ` + ${l.need_spare - l.need} ${esc(t("spare"))}` : ""}</p>`;
    if (ch) h += `<div class="notice info">${esc(t("You chose {m} ({f}) from {s}: {q} pcs for {p}. This changes the order list and carts – not the KiCad project.", { m: ch.mpn, f: ch.mfr, s: ch.seller, q: ch.qty, p: money(ch.price, ch.currency) }))} <button class="btn small" data-unchoose="${esc(l.id)}">${esc(t("Undo"))}</button></div>`;
    const dists = r.dist_boms.map(d => {
      const m = d.results[l.id];
      return m ? `<li>${dot(m.status)}<span><b>${esc(d.distributor)}</b> <span class="sub">${esc([m.how ? t("matched via {h}", { h: m.how }) : "", ...(m.issues || []), m.qty_msg || ""].filter(Boolean).join(" · ") || t("not in the file"))}</span></span></li>` : "";
    }).join("");
    if (dists) h += `<h4>${esc(t("Distributor BOM"))}</h4><ul class="checks">${dists}</ul>`;
    if (p) {
      h += `<h4>${esc(t("Offers"))}</h4><div class="tbl-wrap"><table class="tight"><thead><tr><th>${esc(t("Seller"))}</th><th class="num">${esc(t("Buy"))}</th><th class="num">${esc(t("Price"))}</th><th class="num">${esc(t("Stock"))}</th></tr></thead><tbody>
        ${Object.values(p.per_seller).sort((a, b) => a.total - b.total).map(b => `<tr><td>${esc(b.seller)}<div class="sub mono">${b.url ? `<a href="${esc(b.url)}" target="_blank" rel="noopener">${esc(b.sku)}</a>` : esc(b.sku)} · ${esc(b.packaging || "")}</div>${b.impractical ? `<span class="pill mismatch">${esc(t("full reel"))}</span>` : ""}</td>
        <td class="num">${b.qty}</td><td class="num">${money(b.total, b.currency)}<div class="sub">${money(b.unit)}/${esc(t("pc"))}</div></td>
        <td class="num ${b.stock != null && b.stock < l.need_spare ? "bad-text" : ""}">${intl(b.stock)}</td></tr>`).join("")}</tbody></table></div>
        ${(p.best.suggestions || []).map(s => `<div class="sugg ${s.kind}">${esc(s.text)}</div>`).join("")}`;
    } else if (!dists) {
      h += `<p class="hint">${esc(r.providers.length ? t("No offers found.") : t("Add an API key in Settings, or upload a distributor BOM, to see prices and stock."))}</p>`;
    }
    const lc = (l.api || []).filter(a => a.lifecycle);
    if (lc.length) h += `<p class="sub">${esc(t("Lifecycle"))}: ${lc.map(a => `${esc(a.source)}: ${esc(a.lifecycle)}`).join(" · ")}</p>`;
    return h;
  }

  // ---------- alternatives ----------
  const GROUPS = () => ({ "drop-in": t("Fits directly – same footprint and pinout"), "same-package": t("Same package – check the pinout"),
    "check": t("Package could not be compared – check yourself"), "redesign": t("Similar function – needs a new footprint or other pinout") });
  function altCard(l, it, i, ch) {
    const chosen = ch && ch.mpn === it.mpn;
    const fitTxt = { ok: t("Fits footprint"), partial: t("Footprint: maybe"), mismatch: t("Other footprint"), unknown: t("Footprint: unknown") };
    return `<div class="alt ${chosen ? "chosen" : ""}">
      <div>
        <div><span class="mono mpn">${it.url ? `<a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.mpn)}</a>` : esc(it.mpn)}</span> <span class="sub">${esc(it.mfr)}</span></div>
        <div class="desc">${esc((it.desc || "").slice(0, 130))}</div>
        <div class="facts">
          ${it.fit ? pill({ ok: "ok", partial: "partial", mismatch: "mismatch" }[it.fit] || "unknown", fitTxt[it.fit]) : ""}
          ${it.pinout ? pill(it.pinout.status, { ok: t("Same pinout"), warn: t("Pinout partly"), mismatch: t("Other pinout") }[it.pinout.status]) : ""}
          <span class="sub">${esc(it.seller || it.source || "")}${it.package ? ` · ${esc(it.package)}` : ""}</span>
          ${it.datasheet ? `<a class="sub" href="${esc(it.datasheet)}" target="_blank" rel="noopener">${esc(t("datasheet"))}</a>` : ""}
        </div>
        ${it.check && it.fit !== "ok" ? `<div class="note">${esc(it.check)}</div>` : ""}
        ${it.pinout && it.pinout.status !== "ok" ? `<div class="note">${esc(it.pinout.msg)}</div>` : ""}
      </div>
      <div class="alt-side">
        <div class="alt-stock ${it.stock ? "" : "bad-text"}">${it.stock != null ? esc(t("{n} in stock", { n: intl(it.stock) })) : esc(t("stock unknown"))}</div>
        ${it.price != null ? `<div class="alt-price">${it.qty} ${esc(t("pcs"))} · ${money(it.price, it.currency)}</div>` : ""}
        ${it.sku && it.price != null ? `<button class="btn small ${chosen ? "primary" : ""}" data-choose="${esc(l.id)}" data-i="${i}">${esc(chosen ? t("Chosen") : t("Choose"))}</button>` : ""}
        <div class="alt-thumb">${it.photo ? `<div><img src="${esc(it.photo)}" alt="" loading="lazy" onerror="this.parentNode.remove()"></div>` : ""}
          <div class="fp-mini" data-pkg="${esc(it.package || "")}" data-kind="${esc(l.kind || "")}"></div></div>
      </div></div>`;
  }
  function pAlts(l) {
    const res = state.alts[l.id];
    if (!state.result.providers.length) return `<p class="hint">${esc(t("Alternatives need at least one distributor API key (Settings)."))}</p>`;
    if (!res || res === "loading") return `<p class="hint">${esc(t("Finding alternatives … (the distributors' rate limits can make this take a little while)"))}</p>`;
    if (res.error) return `<div class="notice bad">${esc(res.error)}</div>`;
    if (!res.items.length) return `<p class="hint">${esc(res.note)}</p>`;
    const ch = state.choice[l.id], min = state.altMin || 0;
    const shown = res.items.map((it, i) => ({ it, i })).filter(({ it }) => (it.stock || 0) >= min);
    // Cheapest first still puts what can't be bought (no price, nothing in stock) last.
    const key = state.altSort === "price" ? (({ it }) => [it.price == null || !it.stock ? 1 : 0, it.price || 0]) : (({ it }) => [0, -(it.stock || 0)]);
    shown.sort((a, b) => { const ka = key(a), kb = key(b); return ka[0] - kb[0] || ka[1] - kb[1]; });
    let body = "";
    for (const [g, title] of Object.entries(GROUPS())) {
      const inG = shown.filter(({ it }) => (it.group || "drop-in") === g);
      if (!inG.length) continue;
      if (res.kind !== "passive") body += `<h4>${esc(title)} (${inG.length})</h4>`;
      body += inG.slice(0, 15).map(({ it, i }) => altCard(l, it, i, ch)).join("");
    }
    if (!shown.length) body = `<p class="hint">${esc(t("No alternatives with at least {n} in stock.", { n: intl(min) }))}</p>`;
    return `<p class="hint">${esc(res.note)}</p>
      <div class="row alt-ctl"><label class="inline">${esc(t("Sort"))} <select id="altSort"><option value="stock" ${state.altSort === "stock" ? "selected" : ""}>${esc(t("Most stock first"))}</option><option value="price" ${state.altSort === "price" ? "selected" : ""}>${esc(t("Cheapest first"))}</option></select></label>
      <label class="inline">${esc(t("Minimum stock"))} <input id="altMin" type="number" min="0" step="1000" value="${min || ""}" placeholder="50000"></label>
      <span class="sub">${esc(t("{a} of {b} shown", { a: shown.length, b: res.items.length }))}</span></div>${body}`;
  }
  async function hydrateThumbs() {
    for (const el of document.querySelectorAll("#side .fp-mini[data-pkg]")) {
      if (!el.dataset.pkg) { el.remove(); continue; }
      const key = el.dataset.pkg + "|" + el.dataset.kind;
      if (!(key in state.libfp)) {
        state.libfp[key] = "loading";
        try { state.libfp[key] = await (await fetch(`/api/libfp?pkg=${encodeURIComponent(el.dataset.pkg)}&kind=${encodeURIComponent(el.dataset.kind)}`)).json(); }
        catch (e) { state.libfp[key] = {}; }
      }
      const fp = state.libfp[key];
      if (fp === "loading") continue;
      if (fp && fp.geometry) { el.innerHTML = renderFootprint(fp.geometry, null, { scaleBar: false }); el.title = fp.id; }
      else el.remove();
    }
  }
  document.addEventListener("change", e => {
    if (e.target.id === "altSort") { state.altSort = e.target.value; store("altSort", state.altSort); renderSide(); }
    if (e.target.id === "altMin") { state.altMin = Math.max(0, +e.target.value || 0); store("altMin", String(state.altMin)); renderSide(); }
  });

  async function loadCompare(id) {
    state.cmp[id] = null;
    let res;
    try { res = await (await post("/api/fpcompare", { job: state.job, line: id })).json(); } catch (e) { res = { error: e.message }; }
    state.cmp[id] = res;
    if (state.sel === id) renderSide();
  }
  async function loadAlternatives(id) {
    state.alts[id] = "loading";
    let res;
    try { res = await (await post("/api/alternatives", { job: state.job, line: id })).json(); } catch (e) { res = { error: e.message }; }
    state.alts[id] = res;
    if (state.sel === id) renderSide();
  }
  function showPage(p) {
    const wrap = $("#sidePdfWrap");
    if (!wrap) return;
    wrap.classList.remove("hidden");
    $("#sidePdf").src = `/api/datasheet/${encodeURIComponent(state.job)}/${encodeURIComponent(state.sel)}?p=${p}#page=${p}`;
    document.querySelectorAll("#side [data-page]").forEach(b => b.classList.toggle("primary", b.dataset.page === String(p)));
    wrap.scrollIntoView({ block: "nearest" });
  }
  function refresh(id) { renderTiles(); renderTab(); renderBoardView(); select(id, false, false); }

  document.addEventListener("click", e => {
    const exp = e.target.closest("[data-export]");
    if (exp) { exportOrder(exp.dataset.export); return; }
    const dk = e.target.closest("[data-dkcart]");
    if (dk) { digikeyCart(dk.dataset.dkcart); return; }
    const mo = e.target.closest("[data-mocart]");
    if (mo) { mouserCart(mo.dataset.mocart); return; }
    const pt = e.target.closest("[data-ptab]");
    if (pt) { state.ptab = pt.dataset.ptab; renderSide(); return; }
    const pg = e.target.closest("#side [data-page]");
    if (pg) { showPage(pg.dataset.page); return; }
    const pic = e.target.closest("[data-dspic]");
    if (pic) { const c = state.cmp[state.sel]; showPage(((c && c.pages) || [1])[0]); return; }
    const rv = e.target.closest("[data-refview]");
    if (rv) { state.refView = rv.dataset.refview; renderSide(); return; }
    const choose = e.target.closest("[data-choose]");
    if (choose) { state.choice[choose.dataset.choose] = state.alts[choose.dataset.choose].items[+choose.dataset.i]; refresh(choose.dataset.choose); return; }
    const un = e.target.closest("[data-unchoose]");
    if (un) { delete state.choice[un.dataset.unchoose]; refresh(un.dataset.unchoose); return; }
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

  loadSettings().then(() => { loadHistory(); checkUpdates(false); });
})();
