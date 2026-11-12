/* Retention Schedule Determination - front end (vanilla JS, no build step) */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const LC = { I: "var(--l1)", II: "var(--l2)", III: "var(--l3)", IV: "var(--l4)", V: "var(--l5)", VI: "var(--l6)" };
const PERIOD = { I: "5 years", II: "10 years", III: "10 years", IV: "15 years", V: "20 years", VI: "Permanent" };
const TRIG = { creation: "after creation", event: "after end of relationship", permanent: "life of organization" };
const S = { schedule: null, health: null, current: null, regFilter: "", chips: [] };

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!r.ok) { let m = r.statusText; try { m = (await r.json()).detail || m } catch { } throw new Error(m) }
  return r.json();
}
function toast(msg) {
  const t = $("#toast");
  t.innerHTML = `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/></svg>${esc(msg)}`;
  t.classList.add("on"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), 2400);
}
const download = url => { const a = document.createElement("a"); a.href = url; a.download = ""; document.body.appendChild(a); a.click(); a.remove() };

/* ------------------------------------------------------------ navigation */
const TITLES = { assess: "Assess", register: "Register", schedule: "Schedule", insights: "Insights" };
function go(view) {
  $$(".tab").forEach(t => t.classList.toggle("on", t.dataset.view === view));
  $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + view));
  $("#smallTitle").textContent = TITLES[view];
  window.scrollTo({ top: 0 });
  if (view === "register") loadRegister();
  if (view === "schedule") renderSchedule();
  if (view === "insights") loadInsights();
}
$$(".tab").forEach(t => t.onclick = () => go(t.dataset.view));
addEventListener("scroll", () => $("#navbar").classList.toggle("scrolled", scrollY > 40), { passive: true });

/* ---------------------------------------------------------------- sheets */
function openSheet({ title, body, done, onDone, onOpen }) {
  $("#sheetTitle").textContent = title || "";
  $("#sheetBody").innerHTML = body;
  const d = $("#sheetDone"); d.textContent = done || ""; d.style.visibility = done ? "visible" : "hidden";
  d.onclick = async () => { if (onDone && (await onDone()) === false) return; closeSheet() };
  $("#sheet").classList.add("on"); $("#backdrop").classList.add("on");
  onOpen && onOpen($("#sheetBody"));
}
function closeSheet() { $("#sheet").classList.remove("on"); $("#backdrop").classList.remove("on") }
$("#sheetCancel").onclick = closeSheet;
$("#backdrop").onclick = () => { closeSheet(); closeAction() };
addEventListener("keydown", e => { if (e.key === "Escape") { closeSheet(); closeAction() } });

function actionSheet(header, actions) {
  const a = $("#actionSheet");
  a.innerHTML = `<div class="grp">${header ? `<div class="hd">${esc(header)}</div>` : ""}${actions.map((x, i) =>
    `<button data-i="${i}" class="${header ? "after-hd" : ""}" style="${x.destructive ? "color:var(--red)" : ""}">${esc(x.label)}</button>`).join("")}</div>
    <div class="grp"><button class="cancel">Cancel</button></div>`;
  $$("button[data-i]", a).forEach(b => b.onclick = () => { closeAction(); actions[+b.dataset.i].run() });
  $(".cancel", a).onclick = closeAction;
  a.classList.add("on"); $("#backdrop").classList.add("on");
}
function closeAction() { $("#actionSheet").classList.remove("on"); if (!$("#sheet").classList.contains("on")) $("#backdrop").classList.remove("on") }

/* ------------------------------------------------------------------ form */
$$(".segmented[data-name]").forEach(seg => $$("button", seg).forEach(b => b.onclick = () => {
  $$("button", seg).forEach(x => x.classList.toggle("on", x === b));
}));
function renderChips() {
  $("#chips").innerHTML = S.chips.map((c, i) => `<span class="chip"><span title="${esc(c)}">${esc(c)}</span><button type="button" data-i="${i}" aria-label="Remove">✕</button></span>`).join("");
  $$("#chips button").forEach(b => b.onclick = () => { S.chips.splice(+b.dataset.i, 1); renderChips() });
}
$("#chipInput").addEventListener("keydown", e => {
  const v = e.target.value.trim();
  if ((e.key === "Enter" || e.key === ",") && v) { e.preventDefault(); S.chips.push(v); e.target.value = ""; renderChips() }
  if (e.key === "Backspace" && !v && S.chips.length) { S.chips.pop(); renderChips() }
});

const EXAMPLES = [
  { label: "Client 360 data product (mixed)", d: { title: "Client 360 Data Product", asset_type: "Data Product", record_copy: "Copy / derived", business_unit: "Client Data Products", system: "Databricks", description: "A curated data product in the lakehouse that gives advisors and analysts a single view of each client. It combines account and household data with interaction history and supervisory review outcomes and is refreshed daily.", components: ["Client account master, registrations and beneficiaries", "Client call recordings and chat transcripts from the contact center", "Reg BI suitability and concentration review results", "Marketing campaign responses and seminar attendance"], client_data: 1, pii: 1 } },
  { label: "Advisor email archive", d: { title: "Financial Advisor Email Archive", asset_type: "Communication", description: "Journaled archive of all emails sent and received by financial advisors, including correspondence with clients and prospects.", client_data: 1, pii: 1 } },
  { label: "GenAI assistant prompt logs", d: { title: "GenAI Assistant Prompt Logs", asset_type: "Application / System", description: "Prompt and response logs from an internal generative AI assistant that associates use to summarize research and draft documents. Logged for model evaluation and abuse monitoring.", employee_data: 1 } },
  { label: "ESG emissions inventory (gap)", d: { title: "Greenhouse Gas Emissions Inventory", asset_type: "Dataset", description: "Annual scope 1 and scope 2 greenhouse gas emissions calculations for office facilities, used for sustainability disclosure." } },
  { label: "Commission payout dashboard", d: { title: "FA Commission Payout Dashboard", asset_type: "Report / Dashboard", description: "Monthly Power BI dashboard of financial advisor commission and payout calculations with reconciliation to the general ledger.", employee_data: 1 } },
  { label: "SEC exam response files", d: { title: "SEC Exam 2026 Production", asset_type: "Legal Matter", description: "Documents and data produced in response to an SEC examination request letter, with counsel correspondence.", legal_hold: 1 } },
];
$("#exampleBtn").onclick = () => actionSheet("Load an example scenario", EXAMPLES.map(x => ({ label: x.label, run: () => fillForm(x.d) })));
function fillForm(d) {
  const f = $("#assessForm"); f.reset();
  ["title", "description", "data_owner", "business_unit", "system"].forEach(k => f[k].value = d[k] || "");
  f.asset_type.value = d.asset_type || "Dataset";
  ["client_data", "employee_data", "pii", "legal_hold"].forEach(k => f[k].checked = !!d[k]);
  f.j_us.checked = true; f.use_llm.checked = !!S.health?.llm?.enabled;
  $$('[data-name="record_copy"] button').forEach(b => b.classList.toggle("on", b.dataset.v === (d.record_copy || "Official record")));
  S.chips = [...(d.components || [])]; renderChips();
  f.description.focus();
}

$("#assessForm").onsubmit = async e => {
  e.preventDefault();
  const f = e.target;
  const pending = $("#chipInput").value.trim(); if (pending) { S.chips.push(pending); $("#chipInput").value = ""; renderChips() }
  const body = {
    title: f.title.value, description: f.description.value, data_owner: f.data_owner.value, business_unit: f.business_unit.value,
    system: f.system.value, asset_type: f.asset_type.value, components: S.chips,
    record_copy: $('[data-name="record_copy"] .on').dataset.v,
    client_data: f.client_data.checked, employee_data: f.employee_data.checked, pii: f.pii.checked, legal_hold: f.legal_hold.checked,
    jurisdictions: [f.j_us.checked && "US", f.j_ca.checked && "CA"].filter(Boolean), use_llm: f.use_llm.checked,
  };
  if (!body.jurisdictions.length) body.jurisdictions = ["US"];
  const btn = $("#assessBtn"); btn.disabled = true; btn.innerHTML = `<div class="spinner"></div><span>Analyzing…</span>`;
  try {
    const det = await api("/api/assess", { method: "POST", body: JSON.stringify(body) });
    S.current = det; $("#emptyState").hidden = true;
    renderResult(det, $("#result"));
    if (innerWidth <= 920) $("#resultCol").scrollIntoView({ behavior: "smooth" });
    else { window.scrollTo({ top: 0, behavior: "smooth" }); $("#resultCol").scrollTo({ top: 0 }) }
    refreshBadge();
  } catch (err) { toast("Error: " + err.message) }
  finally { btn.disabled = false; btn.innerHTML = `<span>Determine Retention</span>` }
};

/* ---------------------------------------------------------- result view */
function statusClass(s) { s = (s || "").toLowerCase(); return s.startsWith("approved") ? "approved" : s === "rejected" ? "rejected" : "draft" }
function renderResult(d, el, inSheet = false) {
  const g = d.governing, lc = LC[d.final_level];
  const icon = { covered: "Covered", multi: "Multi-activity", inferred: "Inferred", gap: "Gap" }[d.coverage];
  const period = d.final_level === "VI" ? "Life of organization" : `${PERIOD[d.final_level]} ${TRIG[d.final_trigger]}`;
  const comps = (d.components || []);
  const regs = d.regulatory || [];
  el.innerHTML = `
  <div class="hero" style="--lc:${lc}">
    <div class="hero-top">
      <div>
        <span class="pill">${esc(icon)}</span> <span class="pill">${esc(d.status || "Preview")}</span>
        <div class="lvl">Level ${d.final_level}</div>
        <div class="period">${esc(period)}</div>
        <div class="stmt">${esc(d.retention_statement)}</div>
      </div>
      <div class="ring" style="--p:${d.confidence}"><div><div><b>${d.confidence}</b><small>CONFIDENCE</small></div></div></div>
    </div>
    <div class="meta">
      <span><b>Activity</b> ${esc(g.activity)}</span>
      <span><b>Category</b> ${esc(g.category)}</span>
      ${d.issuance_id ? `<span><b>ID</b> ${esc(d.issuance_id)}</span>` : ""}
    </div>
  </div>

  ${d.request?.legal_hold ? banner("red", "Legal hold in effect - disposition is suspended until Legal releases the hold.") : ""}
  ${d.regulatory_uplift ? banner("orange", `Regulatory uplift: the schedule level for this activity (Level ${g.level}) is below a matched regulatory minimum, so retention was raised to Level ${d.final_level}.`) : ""}
  ${d.review_required && !String(d.status).startsWith("Approved") ? banner("orange", "DRD review recommended before this schedule is issued.") : ""}
  ${String(d.status).startsWith("Approved") ? banner("green", `Approved${d.review?.reviewer ? " by " + esc(d.review.reviewer) : ""}${d.review?.at ? " on " + esc(d.review.at.slice(0, 10)) : ""}.`) : ""}

  <div class="action-bar">
    ${d.issuance_id && !String(d.status).startsWith("Approved") && d.status !== "Rejected" ? `
      <button class="btn-tinted green" data-act="approve"><svg viewBox="0 0 24 24" class="ic"><path d="M5 12l5 5 9-10"/></svg>Approve</button>
      <button class="btn-tinted" data-act="override"><svg viewBox="0 0 24 24" class="ic"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg>Override</button>
      <button class="btn-tinted red" data-act="reject">Reject</button>` : ""}
    ${d.issuance_id ? `
      <button class="btn-tinted gray" data-dl="pdf"><svg viewBox="0 0 24 24" class="ic"><path d="M12 4v12M7 11l5 5 5-5M4 20h16"/></svg>PDF</button>
      <button class="btn-tinted gray" data-dl="xlsx">Excel</button>
      <button class="btn-tinted gray" data-dl="json">JSON</button>` : ""}
  </div>

  <div class="cards">
    <div class="card"><h4>Why this schedule</h4><ul class="bullets">${d.rationale.map(r => `<li>${esc(r)}</li>`).join("")}</ul>
      ${d.notes?.length ? `<ul class="bullets warn" style="margin-top:10px">${d.notes.map(r => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}</div>

    ${d.proposal ? `<div class="card"><h4>Proposed new business activity</h4>
      <dl class="kv"><dt>Activity</dt><dd>${esc(d.proposal.proposed_activity)}</dd>
      <dt>Category</dt><dd>${esc(d.proposal.proposed_category)}</dd>
      <dt>Proposed level</dt><dd><span class="lv" style="--lc:${LC[d.proposal.proposed_level]}">${d.proposal.proposed_level}</span> ${esc(PERIOD[d.proposal.proposed_level])}</dd>
      <dt>Trigger</dt><dd>${esc(d.proposal.trigger_event)}</dd>
      <dt>Nearest existing</dt><dd>${esc(d.proposal.nearest_activity)} <span class="muted">(${d.proposal.nearest_score.toFixed(2)})</span></dd></dl>
      <div class="group-footer" style="margin:10px 0 0">Approving with "Add to schedule" creates a DRD-approved extension the engine uses for future requests.</div></div>` : ""}

    <div class="card"><h4>Determination</h4><dl class="kv">
      <dt>Coverage</dt><dd>${esc(d.coverage_label)}</dd>
      <dt>Business activity</dt><dd>${esc(g.activity)} ${g.activity_id ? `<span class="muted">${esc(g.activity_id)}</span>` : ""}</dd>
      <dt>Activity schedule</dt><dd>${esc(g.level_label)}</dd>
      <dt>Trigger event</dt><dd>${esc(d.trigger_event)}</dd>
      <dt>Disposition</dt><dd>${esc(d.disposition)}</dd>
      <dt>Schedule version</dt><dd>${esc(d.schedule_version)}</dd></dl></div>

    ${comps.length ? `<div class="card"><h4>Component breakdown <span class="count">${comps.length}</span></h4>
      ${comps.map(c => `<div class="comp"><div><div class="t">${esc(c.text)}</div>
        <div class="a">${c.matched ? esc(c.activity) + " · " + esc(c.category) : "No confident match - covered by the governing activity"}</div>
        ${c.matched_keywords?.length ? c.matched_keywords.slice(0, 4).map(k => `<span class="kw">${esc(k)}</span>`).join("") : ""}</div>
        <div>${c.matched ? `<span class="lv" style="--lc:${LC[c.level]}">${c.level}</span>` : `<span class="tag gray">-</span>`}</div></div>`).join("")}</div>` : ""}

    ${regs.length ? `<div class="card"><h4>Regulatory minimums <span class="count">${regs.length}</span></h4>
      ${regs.map(r => {
    const f = r.floor; const min = r.type === "ceiling" ? "Data minimization" : f.trigger === "permanent" ? "Permanent" : `${f.years} yrs after ${f.event || "creation"}`;
    const tag = r.type === "ceiling" ? `<span class="tag ceil">Ceiling</span>` : r.satisfied_by_schedule ? `<span class="tag ok">Met</span>` : `<span class="tag up">Needs Level ${r.minimum_level}</span>`;
    return `<div class="reg"><div class="h"><span>${esc(r.name)}</span>${tag}</div><div class="c">${esc(r.citation)} · ${esc(min)} · ${esc(r.jurisdiction)}</div></div>`
  }).join("")}
      <div class="group-footer" style="margin:10px 0 0">Decision support only - validate with Legal/Compliance.</div></div>` : ""}

    <div class="card"><h4>How the engine ranked activities</h4>
      ${d.alternatives.map(a => `<div class="alt"><div><div class="n">${esc(a.activity)} <span class="lv" style="--lc:${LC[a.level]};height:19px;min-width:28px;font-size:11px">${a.level}</span></div>
        <div class="c">keywords ${a.signals.keywords} · similarity ${a.signals.similarity} · learned examples ${a.signals.examples}</div>
        <div class="bar"><i style="width:${Math.round(a.score * 100)}%;background:${LC[a.level]}"></i></div></div><div class="s">${a.score.toFixed(2)}</div></div>`).join("")}</div>

    ${d.llm ? `<div class="card"><h4>AI second opinion <span class="count">${esc(d.llm.provider)} · ${esc(d.llm.model)}</span></h4>
      ${d.llm.error ? `<div class="muted">Unavailable: ${esc(d.llm.error)}</div>` :
        `<div>${esc(d.llm.reasoning || "")}</div><div style="margin-top:6px">${(d.llm.activity_ids || []).map(i => `<span class="kw">${esc(i)}</span>`).join("")}</div>
        ${(d.llm.regulatory_considerations || []).length ? `<ul class="bullets" style="margin-top:10px">${d.llm.regulatory_considerations.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}`}</div>` : ""}
  </div>`;

  $$("[data-dl]", el).forEach(b => b.onclick = () => download(`/api/issuances/${d.issuance_id}/export?fmt=${b.dataset.dl}`));
  const act = $("[data-act=approve]", el);
  if (act) {
    act.onclick = () => d.coverage === "gap" && d.proposal
      ? actionSheet("This asset is not covered by the current schedule", [
        { label: "Approve & add activity to schedule", run: () => review(d, { action: "approve", adopt_proposal: true }, el, inSheet) },
        { label: "Approve as a one-off", run: () => review(d, { action: "approve" }, el, inSheet) }])
      : reviewPrompt(d, "approve", el, inSheet);
    $("[data-act=override]", el).onclick = () => overrideSheet(d, el, inSheet);
    $("[data-act=reject]", el).onclick = () => actionSheet("Reject this determination?", [{ label: "Reject", destructive: true, run: () => review(d, { action: "reject" }, el, inSheet) }]);
  }
}
const banner = (kind, text) => `<div class="banner ${kind}"><svg viewBox="0 0 24 24">${kind === "green"
  ? '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>'
  : '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17.5v.01"/>'}</svg><div>${text}</div></div>`;

function reviewerFields(extra = "") {
  return `${extra}<div class="group-label">Reviewer</div><div class="group">
    <label class="row input-row"><span class="row-label">Name</span><input id="rvName" placeholder="Your name" value="${esc(localStorage.getItem("drs_reviewer") || "")}"></label>
    <div class="row textarea-row"><textarea id="rvNotes" class="textarea-plain" placeholder="Notes (optional)"></textarea></div></div>`;
}
function reviewPrompt(d, action, el, inSheet) {
  // approvals from inside the register sheet run directly to avoid stacking sheets
  if (inSheet) return review(d, { action, reviewer: localStorage.getItem("drs_reviewer") || "" }, el, inSheet);
  openSheet({
    title: "Approve schedule", done: "Approve", body: reviewerFields(),
    onDone: () => review(d, { action, reviewer: $("#rvName").value, notes: $("#rvNotes").value }, el, inSheet)
  });
}
function overrideSheet(d, el) {
  const cats = S.schedule.categories;
  const opts = cats.map(c => `<optgroup label="${esc(c.name)}">${c.activities.map(a =>
    `<option value="${a.activity_id}" ${a.activity_id === d.governing.activity_id ? "selected" : ""}>${esc(a.activity)} (Level ${a.level})</option>`).join("")}</optgroup>`).join("");
  openSheet({
    title: "Override", done: "Save",
    body: `<div class="group-label">Business activity</div><div class="group"><label class="row select-row"><select id="ovAct" class="picker">${opts}</select>
      <svg class="chev" viewBox="0 0 24 24"><path d="M8 10l4 4 4-4"/></svg></label></div>
      <div class="group-label">Retention level</div><div class="group"><div class="row" style="justify-content:center">
      <div class="segmented" id="ovLvl">${["I", "II", "III", "IV", "V", "VI"].map(l => `<button type="button" data-v="${l}" class="${l === d.final_level ? "on" : ""}">${l}</button>`).join("")}</div></div></div>
      <div class="group-footer" id="ovHint"></div>${reviewerFields()}`,
    onOpen: b => {
      const seg = $("#ovLvl", b), hint = () => { const l = $(".on", seg).dataset.v; $("#ovHint").textContent = S.schedule.levels[l].label };
      $$("button", seg).forEach(x => x.onclick = () => { $$("button", seg).forEach(y => y.classList.toggle("on", y === x)); hint() });
      $("#ovAct", b).onchange = e => {
        const a = cats.flatMap(c => c.activities).find(a => a.activity_id === e.target.value);
        $$("button", seg).forEach(y => y.classList.toggle("on", y.dataset.v === a.level)); hint();
      }; hint();
    },
    onDone: () => {
      if (!$("#rvNotes").value.trim()) { toast("Add a note explaining the override"); return false }
      return review(d, { action: "override", activity_id: $("#ovAct").value, level: $("#ovLvl .on").dataset.v, reviewer: $("#rvName").value, notes: $("#rvNotes").value }, el, false);
    }
  });
}
async function review(d, payload, el, inSheet) {
  if (payload.reviewer) localStorage.setItem("drs_reviewer", payload.reviewer);
  try {
    const nd = await api(`/api/issuances/${d.issuance_id}/review`, { method: "POST", body: JSON.stringify(payload) });
    if (S.current?.issuance_id === nd.issuance_id) S.current = nd;
    renderResult(nd, el, inSheet);
    if (!inSheet && $("#result") !== el) renderResult(nd, $("#result"));
    toast({ approve: "Approved - the engine learned from this decision", override: "Override saved - model retrained", reject: "Rejected" }[payload.action]);
    if (payload.adopt_proposal) { S.schedule = await api("/api/schedule") }
    refreshBadge();
    if ($("#view-register").classList.contains("active")) loadRegister();
  } catch (e) { toast("Error: " + e.message); return false }
}

/* -------------------------------------------------------------- register */
$$("#regFilter button").forEach(b => b.onclick = () => { $$("#regFilter button").forEach(x => x.classList.toggle("on", x === b)); S.regFilter = b.dataset.v; loadRegister() });
let regT; $("#regSearch").oninput = () => { clearTimeout(regT); regT = setTimeout(loadRegister, 200) };
async function loadRegister() {
  let rows = await api(`/api/issuances?q=${encodeURIComponent($("#regSearch").value)}`);
  if (S.regFilter === "review") rows = rows.filter(r => r.review_required && !r.status.startsWith("Approved") && r.status !== "Rejected");
  else if (S.regFilter) rows = rows.filter(r => r.status.startsWith(S.regFilter));
  $("#regList").innerHTML = rows.length ? rows.map(r => `
    <div class="item" data-id="${r.id}">
      <div class="lvl-tile" style="--lc:${LC[r.final_level]}">${r.final_level}</div>
      <div class="main"><div class="t1">${esc(r.title || "(untitled)")}</div>
        <div class="t2">${esc(r.activity)} · ${esc(r.id)}${r.data_owner ? " · " + esc(r.data_owner) : ""}</div></div>
      <div class="right"><span class="status ${r.review_required && !r.status.startsWith("Approved") && r.status !== "Rejected" ? "review" : statusClass(r.status)}">${esc(r.review_required && r.status === "Draft" ? "Needs review" : r.status)}</span>
        <span class="hide-sm">${esc(r.created_at.slice(0, 10))}</span><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg></div>
    </div>`).join("") : `<div class="none">No issuances yet. Run an assessment or upload a batch.</div>`;
  $$("#regList .item").forEach(i => i.onclick = () => openIssuance(i.dataset.id));
}
async function openIssuance(id) {
  const d = await api(`/api/issuances/${id}`);
  openSheet({ title: id, body: `<div id="sheetResult" style="padding-top:6px"></div>`, onOpen: b => renderResult(d, $("#sheetResult", b), true) });
}
$("#registerXlsx").onclick = () => download("/api/register.xlsx");
async function refreshBadge() {
  const rows = await api("/api/issuances");
  const n = rows.filter(r => r.review_required && r.status === "Draft").length;
  const b = $("#regBadge"); b.hidden = !n; b.textContent = n;
}

/* ----------------------------------------------------------------- batch */
$("#batchBtn").onclick = () => openSheet({
  title: "Batch upload", body: `
    <div class="group-label">Upload a CSV</div>
    <label class="drop" id="drop"><input type="file" id="batchFile" accept=".csv" hidden>
      <svg viewBox="0 0 24 24"><path d="M12 16V4M7 9l5-5 5 5M4 20h16"/></svg>
      <div style="font-weight:600;margin-top:6px">Choose or drop a CSV file</div>
      <div class="muted" style="font-size:13px">One data asset per row. Components separated by "|".</div></label>
    <div style="text-align:center;margin-top:10px"><button class="btn-plain" id="tpl">Download CSV template</button></div>
    <div id="batchOut"></div>`,
  onOpen: b => {
    $("#tpl", b).onclick = () => download("/api/batch/template.csv");
    const drop = $("#drop", b), inp = $("#batchFile", b);
    const run = async file => {
      const fd = new FormData(); fd.append("file", file);
      $("#batchOut").innerHTML = `<div class="group-footer center">Processing ${esc(file.name)}…</div>`;
      const r = await fetch("/api/batch", { method: "POST", body: fd }).then(x => x.json());
      $("#batchOut").innerHTML = `<div class="group-label">${r.count} determinations</div><div class="group list">${r.results.map(x => `
        <div class="item" data-id="${x.id}"><div class="lvl-tile" style="--lc:${LC[x.level]}">${x.level}</div>
        <div class="main"><div class="t1">${esc(x.title || x.id)}</div><div class="t2">${esc(x.activity)} · ${x.confidence}%</div></div></div>`).join("")}</div>
        <button class="btn-primary" id="batchXlsx">Download batch as Excel</button>`;
      $("#batchXlsx").onclick = () => download(`/api/register.xlsx?ids=${r.ids.join(",")}`);
      refreshBadge(); loadRegister();
    };
    inp.onchange = () => inp.files[0] && run(inp.files[0]);
    drop.ondragover = e => { e.preventDefault(); drop.classList.add("over") };
    drop.ondragleave = () => drop.classList.remove("over");
    drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); e.dataTransfer.files[0] && run(e.dataTransfer.files[0]) };
  }
});

/* -------------------------------------------------------------- schedule */
async function renderSchedule() {
  S.schedule = await api("/api/schedule");
  const L = S.schedule.levels;
  $("#levelsStrip").innerHTML = Object.entries(L).map(([k, v]) => `<div class="lvcard" style="--lc:${LC[k]}"><b>Level ${k}</b><span>${k === "VI" ? "Life of organization" : `${v.years} yrs ${TRIG[v.trigger]}`}</span></div>`).join("");
  const draw = () => {
    const q = $("#schedSearch").value.toLowerCase();
    $("#schedList").innerHTML = S.schedule.categories.map(c => {
      const acts = c.activities.filter(a => !q || [a.activity, a.definition, c.name, ...(a.keywords || [])].join(" ").toLowerCase().includes(q));
      if (!acts.length) return "";
      return `<div class="cat"><div class="group-label">${esc(c.id)} · ${esc(c.name)}</div><div class="group">${acts.map(a => `
        <div class="act"><div class="h"><div class="nm">${esc(a.activity)}<span class="id">${esc(a.activity_id)}</span>${a.custom ? `<span class="ext">DRD extension</span>` : ""}</div>
        <span class="lv" style="--lc:${LC[a.level]}">${a.level}</span></div>
        <div class="df">${esc(a.definition)}</div><div class="tr">${esc(a.level_label)} · Trigger: ${esc(a.trigger_event)}</div></div>`).join("")}</div></div>`;
    }).join("") || `<div class="group-footer center" style="margin-top:20px">No matching activities</div>`;
  };
  $("#schedSearch").oninput = draw; draw();
  const kb = await api("/api/knowledge");
  $("#kbNote").textContent = kb.disclaimer;
  $("#kbList").innerHTML = kb.rules.map(r => `<div class="item" style="cursor:default"><div class="lvl-tile" style="--lc:${r.type === "ceiling" ? "#8E8E93" : "var(--indigo)"};font-size:10.5px">${esc(r.jurisdiction)}</div>
    <div class="main"><div class="t1">${esc(r.name)}</div><div class="t2">${esc(r.citation)}</div></div>
    <div class="right">${r.type === "ceiling" ? "Ceiling" : r.floor.trigger === "permanent" ? "Permanent" : `${r.floor.years} yrs`}</div></div>`).join("");
}
$("#schedXlsx").onclick = () => download("/api/schedule.xlsx");

/* -------------------------------------------------------------- insights */
async function loadInsights() {
  const s = await api("/api/stats");
  const lv = ["I", "II", "III", "IV", "V", "VI"], maxL = Math.max(1, ...lv.map(l => s.by_level[l] || 0));
  const cov = { covered: "Covered", multi: "Multi-activity", inferred: "Inferred", gap: "Gap" };
  const covC = { covered: "var(--green)", multi: "var(--blue)", inferred: "var(--orange)", gap: "var(--red)" };
  const maxC = Math.max(1, ...Object.keys(cov).map(k => s.by_coverage[k] || 0));
  const approved = Object.entries(s.by_status).filter(([k]) => k.startsWith("Approved")).reduce((a, [, v]) => a + v, 0);
  $("#insights").innerHTML = `
    <div class="tiles">
      <div class="tile"><div class="l">Determinations</div><div class="v">${s.total}</div><div class="s">${approved} approved</div></div>
      <div class="tile"><div class="l">Avg. confidence</div><div class="v">${s.avg_confidence}<span style="font-size:18px">%</span></div><div class="s">across all issuances</div></div>
      <div class="tile"><div class="l">Schedule gaps</div><div class="v">${s.by_coverage.gap || 0}</div><div class="s">${s.custom_activities} activities added</div></div>
      <div class="tile"><div class="l">Learned decisions</div><div class="v">${s.feedback}</div><div class="s">${s.training_examples} training examples</div></div>
    </div>
    <div class="two">
      <div class="card"><h4>By retention level</h4>${lv.map(l => `<div class="hbar" style="--lc:${LC[l]}"><span>Level ${l}</span><div class="track"><i style="width:${(s.by_level[l] || 0) / maxL * 100}%"></i></div><span class="n">${s.by_level[l] || 0}</span></div>`).join("")}</div>
      <div class="card"><h4>By coverage</h4>${Object.entries(cov).map(([k, v]) => `<div class="hbar" style="--lc:${covC[k]}"><span>${v}</span><div class="track"><i style="width:${(s.by_coverage[k] || 0) / maxC * 100}%"></i></div><span class="n">${s.by_coverage[k] || 0}</span></div>`).join("")}</div>
    </div>
    <div class="group-label" style="margin-top:24px">Schedule gaps - proposed business activities</div>
    <div class="group list">${s.gaps.length ? s.gaps.map(g => `<div class="item" data-id="${g.id}"><div class="lvl-tile" style="--lc:${LC[g.proposed_level] || "var(--red)"}">${esc(g.proposed_level || "?")}</div>
      <div class="main"><div class="t1">${esc(g.proposed_activity || g.title)}</div><div class="t2">${esc(g.proposed_category || "")} · nearest: ${esc(g.nearest_activity || "-")}</div></div>
      <div class="right"><span class="status ${statusClass(g.status)}">${esc(g.status)}</span><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg></div></div>`).join("") : `<div class="none">No gaps found yet - every request has mapped to the schedule.</div>`}</div>
    <div class="group-label" style="margin-top:24px">DRD-approved schedule extensions</div>
    <div class="group list">${s.custom.length ? s.custom.map(c => `<div class="item" style="cursor:default"><div class="lvl-tile" style="--lc:${LC[c.level]}">${c.level}</div>
      <div class="main"><div class="t1">${esc(c.name)} <span class="muted">${esc(c.id)}</span></div><div class="t2">${esc(c.category)} · approved by ${esc(c.approved_by || "-")}</div></div></div>`).join("") : `<div class="none">None yet. Approve a gap with "Add to schedule" to extend the schedule.</div>`}</div>
    <div class="group-label" style="margin-top:24px">Engine</div>
    <div class="group">
      <div class="row toggle-row"><span>Statistical classifier</span><span class="muted">Keywords + TF-IDF + learned examples</span></div>
      <div class="row toggle-row"><span>AI second opinion</span><span class="muted">${s.llm.enabled ? esc(s.llm.provider + " · " + s.llm.model) : "Off - set DRS_LLM_PROVIDER"}</span></div>
      <div class="row toggle-row"><span>Regulatory knowledge base</span><span class="muted">data/regulatory_knowledge.json</span></div>
    </div>`;
  $$("#insights .item[data-id]").forEach(i => i.onclick = () => openIssuance(i.dataset.id));
}

/* ------------------------------------------------------------------ boot */
(async () => {
  S.health = await api("/api/health");
  S.schedule = await api("/api/schedule");
  const llmOn = S.health.llm.enabled, f = $("#assessForm");
  $("#llmSub").textContent = llmOn ? `${S.health.llm.provider} · ${S.health.llm.model}` : "Not configured - see README";
  f.use_llm.checked = llmOn; f.use_llm.disabled = !llmOn;
  refreshBadge();
})();
