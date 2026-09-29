let selectedBatchId = null;
let allBatches = [];

document.addEventListener("DOMContentLoaded", async () => {
  const user = requireRole("instructor");
  if (!user) return;
  document.getElementById("user-avatar").textContent = initials(user.name);
  document.getElementById("user-name").textContent = user.name;

  document.getElementById("new-batch-form").addEventListener("submit", handleCreateBatch);
  await loadBatches();
  await renderStudents();
});

async function loadBatches() {
  const listEl = document.getElementById("batch-list");
  try {
    const batches = await api("/batches");
    allBatches = batches;
    if (batches.length === 0) {
      listEl.innerHTML = `<p class="small-muted">No batches yet.</p>`;
      return;
    }
    listEl.innerHTML = batches.map((b) => `
      <div class="batch-list-item ${b.id === selectedBatchId ? "active" : ""}" onclick="selectBatch(${b.id})">
        <span>${escapeHtml(b.name)}</span>
        <span class="count">${b.member_count} student${b.member_count === 1 ? "" : "s"}</span>
      </div>
    `).join("");
  } catch (err) {
    listEl.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.message)}</p>`;
  }
}

async function handleCreateBatch(e) {
  e.preventDefault();
  const input = document.getElementById("batch-name-input");
  const name = input.value.trim();
  if (!name) return;
  try {
    const batch = await api("/batches", { method: "POST", body: { name } });
    input.value = "";
    await loadBatches();
    await selectBatch(batch.id);
    await renderStudents();
  } catch (err) {
    alert("Could not create batch: " + err.message);
  }
}

async function selectBatch(batchId) {
  selectedBatchId = batchId;
  await loadBatches();
  await renderBatchDetail();
}

// ---- Students: everyone who signed up, with the batches they're in ----
async function renderStudents() {
  const el = document.getElementById("student-list");
  try {
    const students = await api("/students");
    if (students.length === 0) {
      el.innerHTML = `<p class="small-muted">No students yet. They appear here as soon as they sign up.</p>`;
      return;
    }
    el.innerHTML = `
      <table class="data-table">
        <thead><tr><th>Name</th><th>Email</th><th>Signed up</th><th>Batches</th><th style="text-align:right;">Add to batch</th></tr></thead>
        <tbody>
          ${students.map((st) => {
            const inIds = st.batches.map((b) => b.id);
            const options = allBatches.filter((b) => !inIds.includes(b.id));
            return `
              <tr>
                <td>${escapeHtml(st.name)}</td>
                <td>${escapeHtml(st.email)}</td>
                <td class="small-muted">${formatDate(st.created_at)}</td>
                <td>${st.batches.length
                  ? st.batches.map((b) => `<span class="pill pill-grey">${escapeHtml(b.name)}</span>`).join(" ")
                  : `<span class="pill pill-amber">Waiting for a batch</span>`}</td>
                <td>
                  ${allBatches.length === 0
                    ? `<span class="small-muted">Create a batch first</span>`
                    : options.length === 0
                      ? `<span class="small-muted">In every batch</span>`
                      : `<div class="student-add">
                          <select id="add-to-${st.id}">
                            ${options.map((b) => `<option value="${b.id}" ${b.id === selectedBatchId ? "selected" : ""}>${escapeHtml(b.name)}</option>`).join("")}
                          </select>
                          <button class="btn btn-primary btn-sm" onclick="addStudentToBatch(${st.id})"><i class="ti ti-user-plus"></i> Add</button>
                        </div>`}
                </td>
              </tr>`;
          }).join("")}
        </tbody>
      </table>`;
  } catch (err) {
    el.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.message)}</p>`;
  }
}

async function addStudentToBatch(studentId) {
  const batchId = Number(document.getElementById(`add-to-${studentId}`).value);
  try {
    await api(`/batches/${batchId}/students`, { method: "POST", body: { student_id: studentId } });
    await loadBatches();
    if (selectedBatchId === batchId) await renderBatchDetail();
    await renderStudents();
  } catch (err) {
    alert("Could not add student: " + err.message);
  }
}

async function renderBatchDetail() {
  const detailEl = document.getElementById("batch-detail");
  detailEl.innerHTML = `<p class="small-muted">Loading…</p>`;
  try {
    const batch = await api(`/batches/${selectedBatchId}`);
    detailEl.innerHTML = `
      <div class="section-title"><i class="ti ti-users-group"></i> ${escapeHtml(batch.name)}</div>
      <p class="small-muted" style="margin-top:-8px;">Created ${formatDate(batch.created_at)} · ${batch.members.length} student${batch.members.length === 1 ? "" : "s"}</p>

      <table class="data-table" style="margin: 14px 0;">
        <thead><tr><th>Name</th><th>Email</th><th></th></tr></thead>
        <tbody id="member-tbody">
          ${batch.members.length === 0
            ? `<tr><td colspan="3" class="small-muted" style="text-align:center;padding:20px;">No students yet.</td></tr>`
            : batch.members.map((m) => `
              <tr>
                <td>${escapeHtml(m.name)}</td>
                <td>${escapeHtml(m.email)}</td>
                <td style="text-align:right;">
                  <button class="btn btn-danger btn-sm" onclick="removeStudent(${m.id})"><i class="ti ti-user-minus"></i> Remove</button>
                </td>
              </tr>
            `).join("")}
        </tbody>
      </table>

      <div style="border-top:1px solid var(--border); padding-top:16px; margin:8px 0 18px;">
        <div class="section-title" style="font-size:13px;"><i class="ti ti-file-text"></i> Assigned worksheets</div>
        <div id="batch-worksheets"><p class="small-muted">Loading…</p></div>
      </div>

      <div style="border-top:1px solid var(--border); padding-top:16px; margin-top:8px;">
        <div class="section-title" style="font-size:13px;"><i class="ti ti-user-plus"></i> Add a student to this batch</div>
        <form id="add-student-form">
          <div class="form-row">
            <div class="field"><label>Email</label><input type="email" id="as-email" required /></div>
            <div class="field"><label>Name</label><input type="text" id="as-name" /></div>
            <div class="field"><label>Initial password</label><input type="text" id="as-password" minlength="8" /></div>
          </div>
          <p class="small-muted" style="margin:-6px 0 12px;">A student who already has an account (e.g. signed up) needs only the email — or use <strong>Students</strong> below. For a new student, also enter a name and an initial password (at least 8 characters).</p>
          <button type="submit" class="btn btn-primary btn-sm">Add student</button>
        </form>
      </div>
    `;
    document.getElementById("add-student-form").addEventListener("submit", handleAddStudent);
    await renderBatchWorksheets();
  } catch (err) {
    detailEl.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.message)}</p>`;
  }
}

async function handleAddStudent(e) {
  e.preventDefault();
  const name = document.getElementById("as-name").value.trim();
  const email = document.getElementById("as-email").value.trim();
  const password = document.getElementById("as-password").value;
  try {
    await api(`/batches/${selectedBatchId}/students`, {
      method: "POST",
      body: { email, name: name || null, password: password || null },
    });
    await loadBatches();
    await renderBatchDetail();
    await renderStudents();
  } catch (err) {
    alert("Could not add student: " + err.message);
  }
}

async function removeStudent(studentId) {
  if (!confirm("Remove this student from the batch?")) return;
  try {
    await api(`/batches/${selectedBatchId}/students/${studentId}`, { method: "DELETE" });
    await loadBatches();
    await renderBatchDetail();
    await renderStudents();
  } catch (err) {
    alert("Could not remove student: " + err.message);
  }
}

async function renderBatchWorksheets() {
  const el = document.getElementById("batch-worksheets");
  try {
    const worksheets = await api(`/batches/${selectedBatchId}/worksheets`);
    batchWorksheets = worksheets;
    if (worksheets.length === 0) {
      el.innerHTML = `<p class="small-muted">No worksheets assigned yet. Assign one from <a href="worksheets.html">Library → Worksheets</a>.</p>`;
      return;
    }
    el.innerHTML = worksheets.map((w) => `
      <div class="batch-ws-row">
        <div class="batch-ws-main">
          <div class="batch-ws-title">
            ${w.subject ? `<span class="pill pill-grey">${escapeHtml(w.subject)}</span>` : ""}
            <a href="worksheet-view.html?id=${w.id}&kind=topic">${escapeHtml(w.title)}</a>
          </div>
          ${worksheetPartButtonsHtml((kind) => `worksheet-view.html?id=${w.id}&kind=${kind}`, { present: w.files.map((f) => f.kind) })}
          <div class="small-muted">Students see: <strong>${escapeHtml(WORKSHEET_KINDS.filter((k) => w.kinds.includes(k.kind)).map((k) => k.label).join(", "))}</strong></div>
        </div>
        <div class="batch-ws-side">
          <span class="small-muted">Assigned ${formatDate(w.assigned_at)}</span>
          <button class="btn btn-secondary btn-sm" onclick="changeSheets(${w.id})"><i class="ti ti-adjustments"></i> Change sheets</button>
          <button class="btn btn-secondary btn-sm" onclick="unassignWorksheet(${w.id})" title="Remove from this batch"><i class="ti ti-x"></i> Remove</button>
        </div>
      </div>
    `).join("");
  } catch (err) {
    el.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.message)}</p>`;
  }
}

let batchWorksheets = [];

function changeSheets(worksheetId) {
  const w = batchWorksheets.find((x) => x.id === worksheetId);
  openAssignSheetsModal(w, renderBatchWorksheets);
}

async function unassignWorksheet(worksheetId) {
  if (!confirm("Remove this worksheet from the batch? Students in it will no longer see it.")) return;
  try {
    await api(`/batches/${selectedBatchId}/worksheets/${worksheetId}`, { method: "DELETE" });
    await renderBatchWorksheets();
  } catch (err) {
    alert("Could not remove worksheet: " + err.message);
  }
}
