let currentBatchId = null;
let currentType = "coding";
let currentItemId = null; // question id (coding) or worksheet id (worksheet)
let batchWorksheets = [];

document.addEventListener("DOMContentLoaded", async () => {
  const user = requireRole("instructor");
  if (!user) return;
  document.getElementById("user-avatar").textContent = initials(user.name);
  document.getElementById("user-name").textContent = user.name;

  document.getElementById("filter-batch").addEventListener("change", onBatchChange);
  document.getElementById("filter-type").addEventListener("change", onTypeChange);
  document.getElementById("filter-item").addEventListener("change", onItemChange);
  document.getElementById("filter-sheet").addEventListener("change", loadPerformance);

  await loadBatchOptions();
});

async function loadBatchOptions() {
  const sel = document.getElementById("filter-batch");
  try {
    const batches = await api("/batches");
    sel.innerHTML = `<option value="">Select a batch…</option>` +
      batches.map((b) => `<option value="${b.id}">${escapeHtml(b.name)}</option>`).join("");
  } catch (err) {
    sel.innerHTML = `<option value="">Failed to load batches</option>`;
  }
}

function showEmpty(text) {
  document.getElementById("perf-table-card").style.display = "none";
  document.getElementById("perf-empty").style.display = "block";
  document.getElementById("perf-empty-text").textContent =
    text || "Choose a batch and a task above to see student performance.";
}

async function onBatchChange(e) {
  currentBatchId = e.target.value ? parseInt(e.target.value, 10) : null;
  document.getElementById("filter-type").disabled = !currentBatchId;
  await loadItems();
}

async function onTypeChange(e) {
  currentType = e.target.value;
  await loadItems();
}

// fills the Question / Topic dropdown for the chosen batch and task type
async function loadItems() {
  currentItemId = null;
  const sel = document.getElementById("filter-item");
  const isWorksheet = currentType === "worksheet";
  document.getElementById("filter-item-label").textContent = isWorksheet ? "Topic" : "Question";
  document.getElementById("filter-sheet-field").hidden = true;
  showEmpty();

  if (!currentBatchId) {
    sel.disabled = true;
    sel.innerHTML = `<option value="">Select a batch first…</option>`;
    return;
  }
  sel.disabled = false;
  sel.innerHTML = `<option value="">Loading…</option>`;
  try {
    const items = isWorksheet
      ? (batchWorksheets = await api(`/batches/${currentBatchId}/worksheets`))
      : await api(`/batches/${currentBatchId}/assignments`);
    if (items.length === 0) {
      sel.innerHTML = `<option value="">No ${isWorksheet ? "worksheets" : "questions"} assigned to this batch yet</option>`;
      return;
    }
    sel.innerHTML = `<option value="">Select a ${isWorksheet ? "topic" : "question"}…</option>` +
      items.map((it) => `<option value="${it.id}">${escapeHtml(it.subject ? `${it.subject} — ${it.title}` : it.title)}</option>`).join("");
  } catch (err) {
    sel.innerHTML = `<option value="">Failed to load</option>`;
  }
}

async function onItemChange(e) {
  currentItemId = e.target.value ? parseInt(e.target.value, 10) : null;
  const sheetField = document.getElementById("filter-sheet-field");
  if (!currentItemId) {
    sheetField.hidden = true;
    showEmpty();
    return;
  }
  if (currentType === "worksheet") {
    const w = batchWorksheets.find((x) => x.id === currentItemId);
    document.getElementById("filter-sheet").innerHTML = `<option value="">All sheets</option>` +
      WORKSHEET_KINDS.filter((k) => w.kinds.includes(k.kind))
        .map((k) => `<option value="${k.kind}">${k.label}</option>`).join("");
    sheetField.hidden = false;
  }
  await loadPerformance();
}

async function loadPerformance() {
  if (!currentItemId) return;
  document.getElementById("perf-empty").style.display = "none";
  document.getElementById("perf-table-card").style.display = "block";
  document.getElementById("perf-summary").innerHTML = "";
  const tbody = document.getElementById("perf-tbody");
  tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted);">Loading…</td></tr>`;
  try {
    if (currentType === "worksheet") await loadWorksheetPerformance();
    else await loadCodingPerformance();
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--red);">${escapeHtml(err.message)}</td></tr>`;
  }
}

function studentCell(r) {
  return `<td><strong>${escapeHtml(r.name)}</strong><div class="small-muted">${escapeHtml(r.email)}</div></td>`;
}

async function loadCodingPerformance() {
  document.getElementById("perf-thead").innerHTML =
    `<tr><th>Student</th><th>Status</th><th>Attempts</th><th>Last try</th><th></th></tr>`;
  const tbody = document.getElementById("perf-tbody");
  const rows = await api(`/batches/${currentBatchId}/questions/${currentItemId}/performance`);
  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text-muted);">No students in this batch yet.</td></tr>`;
    return;
  }
  const solved = rows.filter((r) => r.status === "all_passed").length;
  document.getElementById("perf-summary").innerHTML =
    `<span><strong>${solved} of ${rows.length}</strong> students passed all test cases</span>`;
  tbody.innerHTML = rows.map((r) => `
    <tr class="clickable" onclick="openHistory(${r.student_id}, '${escapeHtml(r.name).replace(/'/g, "\\'")}')">
      ${studentCell(r)}
      <td>${statusPillHtml(r.status, r.status_detail)}</td>
      <td>${r.attempt_count}</td>
      <td>${r.last_try_at ? formatDateTime(r.last_try_at) : "—"}</td>
      <td style="text-align:right;"><span class="link-btn">View history →</span></td>
    </tr>
  `).join("");
}

function openedPill(v) {
  return v.view_count
    ? `<span class="pill pill-green"><i class="ti ti-eye-check"></i> Opened</span>`
    : `<span class="pill pill-grey">Not opened</span>`;
}

async function loadWorksheetPerformance() {
  const sheet = document.getElementById("filter-sheet").value;
  const tbody = document.getElementById("perf-tbody");
  const data = await api(`/batches/${currentBatchId}/worksheets/${currentItemId}/performance`);
  const kinds = WORKSHEET_KINDS.filter((k) => data.kinds.includes(k.kind));
  const empty = (cols) => `<tr><td colspan="${cols}" style="text-align:center;padding:24px;color:var(--text-muted);">No students in this batch yet.</td></tr>`;

  if (sheet) {
    // one sheet: who opened it, how often, when
    const label = kinds.find((k) => k.kind === sheet).label;
    document.getElementById("perf-thead").innerHTML =
      `<tr><th>Student</th><th>${label} sheet</th><th>Times opened</th><th>First opened</th><th>Last opened</th></tr>`;
    if (data.rows.length === 0) { tbody.innerHTML = empty(5); return; }
    const opened = data.rows.filter((r) => r.sheets[sheet].view_count).length;
    document.getElementById("perf-summary").innerHTML =
      `<span><strong>${opened} of ${data.rows.length}</strong> students opened the ${label} sheet</span>`;
    tbody.innerHTML = data.rows.map((r) => {
      const v = r.sheets[sheet];
      return `<tr>
        ${studentCell(r)}
        <td>${openedPill(v)}</td>
        <td>${v.view_count}</td>
        <td>${v.first_viewed_at ? formatDateTime(v.first_viewed_at) : "—"}</td>
        <td>${v.last_viewed_at ? formatDateTime(v.last_viewed_at) : "—"}</td>
      </tr>`;
    }).join("");
    return;
  }

  // all sheets: one column per assigned sheet
  document.getElementById("perf-thead").innerHTML =
    `<tr><th>Student</th>${kinds.map((k) => `<th><i class="ti ${k.icon}"></i> ${k.label}</th>`).join("")}</tr>`;
  if (data.rows.length === 0) { tbody.innerHTML = empty(kinds.length + 1); return; }
  document.getElementById("perf-summary").innerHTML = kinds.map((k) => {
    const n = data.rows.filter((r) => r.sheets[k.kind].view_count).length;
    return `<span>${k.label}: <strong>${n} of ${data.rows.length}</strong> opened</span>`;
  }).join(`<span class="dotsep"></span>`);
  tbody.innerHTML = data.rows.map((r) => `<tr>
    ${studentCell(r)}
    ${kinds.map((k) => {
      const v = r.sheets[k.kind];
      return `<td>${openedPill(v)}${v.last_viewed_at ? `<div class="small-muted" style="margin-top:4px;">Last ${formatDateTime(v.last_viewed_at)} · ${v.view_count}×</div>` : ""}</td>`;
    }).join("")}
  </tr>`).join("");
}

async function openHistory(studentId, studentName) {
  document.getElementById("history-title").textContent = `${studentName} — submission history`;
  document.getElementById("history-modal").hidden = false;
  const body = document.getElementById("history-body");
  body.innerHTML = "Loading…";

  try {
    const data = await api(`/students/${studentId}/questions/${currentItemId}/submissions`);
    if (data.submissions.length === 0) {
      body.innerHTML = `<p class="small-muted">No submissions yet.</p>`;
      return;
    }
    const historyHtml = data.submissions.map((s) => `
      <div class="verify-result-row ${s.status === "all_passed" ? "pass" : "fail"}">
        <span>${formatDateTime(s.submitted_at)}</span>
        <span>${s.passed_count} / ${s.total_count} passed</span>
      </div>
    `).join("");

    body.innerHTML = `
      <div style="margin-bottom:16px;">${historyHtml}</div>
      <div class="section-title" style="font-size:13px;">Latest submitted code</div>
      <pre style="background:#0f1117;color:#d8dee9;padding:14px;border-radius:8px;overflow-x:auto;font-size:12.5px;">${escapeHtml(data.latest_code || "")}</pre>
    `;
  } catch (err) {
    body.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.message)}</p>`;
  }
}

function closeHistoryModal() {
  document.getElementById("history-modal").hidden = true;
}
