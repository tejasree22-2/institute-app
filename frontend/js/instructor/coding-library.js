let allBatches = [];
let currentAssignQuestion = null;

document.addEventListener("DOMContentLoaded", async () => {
  const user = requireRole("instructor");
  if (!user) return;
  document.getElementById("user-avatar").textContent = initials(user.name);
  document.getElementById("user-name").textContent = user.name;

  await Promise.all([loadQuestions(), loadBatchesCache()]);

  document.getElementById("assign-confirm-btn").addEventListener("click", confirmAssign);
});

async function loadBatchesCache() {
  allBatches = await api("/batches");
}

async function loadQuestions() {
  const tbody = document.getElementById("library-tbody");
  try {
    const questions = await api("/questions");
    if (questions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--text-muted);padding:30px;">No questions yet. Click "New question" to create one.</td></tr>`;
      return;
    }
    tbody.innerHTML = questions.map((q) => {
      const verified = !!q.verified_at;
      const statusHtml = verified
        ? `<span class="pill pill-green"><i class="ti ti-circle-check"></i> Verified</span>`
        : `<span class="pill pill-grey"><i class="ti ti-alert-circle"></i> Not verified</span>`;
      const assignBtn = verified
        ? `<button class="btn btn-secondary btn-sm" onclick="openAssignModal(${q.id}, '${escapeHtml(q.title).replace(/'/g, "\\'")}')"><i class="ti ti-send"></i> Assign to batch</button>`
        : `<span class="tooltip-wrap" data-tooltip="Verify the reference solution before assigning"><button class="btn btn-secondary btn-sm" disabled><i class="ti ti-send"></i> Assign to batch</button></span>`;

      return `
        <tr>
          <td><strong>${escapeHtml(q.title)}</strong></td>
          <td>${difficultyPillHtml(q.difficulty)}</td>
          <td>${q.test_case_count}</td>
          <td>${q.assignment_count} batch${q.assignment_count === 1 ? "" : "es"}</td>
          <td>${statusHtml}</td>
          <td style="text-align:right; white-space:nowrap;">
            <a class="btn btn-secondary btn-sm" href="question-editor.html?id=${q.id}"><i class="ti ti-edit"></i> Edit</a>
            ${assignBtn}
          </td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;color:var(--red);padding:30px;">${escapeHtml(err.message)}</td></tr>`;
  }
}

async function openAssignModal(questionId, title) {
  currentAssignQuestion = questionId;
  document.getElementById("assign-question-title").textContent = title;
  const listEl = document.getElementById("assign-batch-list");
  listEl.innerHTML = "Loading…";
  document.getElementById("assign-modal").hidden = false;

  try {
    const [assignedData] = await Promise.all([
      api(`/questions/${questionId}/assignments`),
    ]);
    const assignedIds = new Set(assignedData.batch_ids);

    if (allBatches.length === 0) {
      listEl.innerHTML = `<p class="small-muted">No batches yet. Create one from the Batches page first.</p>`;
      return;
    }

    listEl.innerHTML = allBatches.map((b) => `
      <label class="batch-check-row">
        <input type="checkbox" value="${b.id}" ${assignedIds.has(b.id) ? "checked" : ""} />
        ${escapeHtml(b.name)}
        <span class="member-count">${b.member_count} student${b.member_count === 1 ? "" : "s"}</span>
      </label>
    `).join("");
  } catch (err) {
    listEl.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.message)}</p>`;
  }
}

function closeAssignModal() {
  document.getElementById("assign-modal").hidden = true;
  currentAssignQuestion = null;
}

async function confirmAssign() {
  const checked = Array.from(document.querySelectorAll("#assign-batch-list input[type=checkbox]:checked"))
    .map((el) => parseInt(el.value, 10));
  const btn = document.getElementById("assign-confirm-btn");
  btn.disabled = true;
  try {
    await api("/assignments", { method: "POST", body: { question_id: currentAssignQuestion, batch_ids: checked } });
    closeAssignModal();
    await loadQuestions();
  } catch (err) {
    alert("Failed to update assignment: " + err.message);
  } finally {
    btn.disabled = false;
  }
}
