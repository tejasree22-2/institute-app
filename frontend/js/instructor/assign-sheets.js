// "Assign to batch" dialog: pick which of the worksheet's files (Topic / Questions / Answers / extras)
// each batch can open. Students only see the files assigned to their batch.

function ensureAssignSheetsModal() {
  let modal = document.getElementById("assign-sheets-modal");
  if (modal) return modal;
  document.body.insertAdjacentHTML("beforeend", `
    <div class="modal-overlay" id="assign-sheets-modal" hidden>
      <div class="modal" style="max-width:620px;">
        <div class="modal-header">
          <h3>Assign "<span id="as-title"></span>"</h3>
          <button class="modal-close" data-close>&times;</button>
        </div>
        <div class="modal-body">
          <p class="small-muted" style="margin-top:0;">Tick the files each batch can open. Students only see what is ticked for their batch.</p>
          <div id="as-body">Loading…</div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" data-close>Cancel</button>
          <button class="btn btn-primary" id="as-save"><i class="ti ti-send"></i> Save</button>
        </div>
      </div>
    </div>
  `);
  modal = document.getElementById("assign-sheets-modal");
  modal.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => { modal.hidden = true; }));
  return modal;
}

// worksheet: {id, title, files}; onSaved(assignments) runs after a successful save
async function openAssignSheetsModal(worksheet, onSaved) {
  const modal = ensureAssignSheetsModal();
  document.getElementById("as-title").textContent = worksheet.title;
  const body = document.getElementById("as-body");
  const saveBtn = document.getElementById("as-save");
  body.innerHTML = "Loading…";
  saveBtn.disabled = true;
  modal.hidden = false;

  const present = new Set(worksheet.files.map((f) => f.kind));
  const labels = Object.fromEntries(worksheet.files.map((f) => [f.kind, f.label]));
  // extra sheets only get a column when this worksheet has them
  const kinds = WORKSHEET_KINDS.filter((k) => !k.optional || present.has(k.kind));
  const colLabel = (k) => k.kind === "topic" || !labels[k.kind] ? k.label : sheetLinkText(k.kind, labels[k.kind]);
  try {
    const [batches, current] = await Promise.all([
      api("/batches"),
      api(`/worksheets/${worksheet.id}/assignments`),
    ]);
    if (batches.length === 0) {
      body.innerHTML = `<p class="small-muted">No batches yet. Create one from the Batches page first.</p>`;
      return;
    }
    const kindsByBatch = Object.fromEntries(current.assignments.map((a) => [a.batch_id, new Set(a.kinds)]));

    body.innerHTML = `
      <table class="data-table as-table">
        <thead><tr>
          <th>Batch</th>
          ${kinds.map((k) => `<th class="as-col"><i class="ti ${k.icon}"></i> ${escapeHtml(colLabel(k))}</th>`).join("")}
        </tr></thead>
        <tbody>
          ${batches.map((b) => `
            <tr>
              <td><strong>${escapeHtml(b.name)}</strong><div class="small-muted">${b.member_count} student${b.member_count === 1 ? "" : "s"}</div></td>
              ${kinds.map((k) => `
                <td class="as-col">
                  <input type="checkbox" data-batch="${b.id}" data-kind="${k.kind}"
                    ${kindsByBatch[b.id] && kindsByBatch[b.id].has(k.kind) ? "checked" : ""}
                    ${present.has(k.kind) ? "" : "disabled title=\"No sheet uploaded\""} />
                </td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
    saveBtn.disabled = false;
    saveBtn.onclick = async () => {
      const assignments = batches.map((b) => ({
        batch_id: b.id,
        kinds: Array.from(body.querySelectorAll(`input[data-batch="${b.id}"]:checked`)).map((el) => el.dataset.kind),
      })).filter((a) => a.kinds.length);
      saveBtn.disabled = true;
      try {
        const saved = await api(`/worksheets/${worksheet.id}/assignments`, { method: "PUT", body: { assignments } });
        modal.hidden = true;
        if (onSaved) onSaved(saved.assignments);
      } catch (err) {
        alert("Could not save: " + err.message);
      } finally {
        saveBtn.disabled = false;
      }
    };
  } catch (err) {
    body.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.message)}</p>`;
  }
}

// "Morning: Topic, Questions · Evening: all sheets"
function assignmentSummaryText(assignments, batches) {
  if (!assignments.length) return "Not assigned to any batch yet";
  const names = Object.fromEntries(batches.map((b) => [b.id, b.name]));
  return assignments.map((a) => {
    const sheets = a.kinds.length === WORKSHEET_KINDS.length ? "all sheets"
      : WORKSHEET_KINDS.filter((k) => a.kinds.includes(k.kind)).map((k) => k.label).join(", ");
    return `${names[a.batch_id] || "Batch " + a.batch_id}: ${sheets}`;
  }).join("  ·  ");
}
