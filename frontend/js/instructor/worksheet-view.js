const user = requireRole("instructor");
const params = new URLSearchParams(window.location.search);
const worksheetId = params.get("id");

document.getElementById("user-avatar").textContent = initials(user.name);
document.getElementById("user-name").textContent = user.name;
document.getElementById("edit-link").href = `worksheet-editor.html?id=${encodeURIComponent(worksheetId)}`;

const viewer = createWorksheetViewer(document.getElementById("viewer"), {
  basePath: `/worksheets/${encodeURIComponent(worksheetId)}`,
  numbered: true,
  // keep the open tab in the URL so reload / back keeps it
  onChange: (kind) => {
    params.set("kind", kind);
    history.replaceState(null, "", `?${params}`);
  },
});

let batches = [];

async function showAssigned() {
  const { assignments } = await api(`/worksheets/${encodeURIComponent(worksheetId)}/assignments`);
  document.getElementById("w-assigned").innerHTML =
    `<i class="ti ti-users"></i> ${escapeHtml(assignmentSummaryText(assignments, batches))}`;
}

(async function init() {
  try {
    const [w, allBatches] = await Promise.all([
      api(`/worksheets/${encodeURIComponent(worksheetId)}`),
      api("/batches"),
    ]);
    batches = allBatches;
    document.title = `${w.title} — Institute App`;
    document.getElementById("w-title").textContent = w.title;
    const assignBtn = document.getElementById("assign-btn");
    if (w.verified_at) {
      assignBtn.disabled = false;
      assignBtn.addEventListener("click", () => openAssignSheetsModal(w, showAssigned));
    } else {
      assignBtn.title = "Upload all 3 files and verify before assigning";
    }
    await showAssigned();
    if (w.subject_slug) {
      const back = document.getElementById("back-link");
      back.href = `worksheets.html?subject=${encodeURIComponent(w.subject_slug)}`;
      back.querySelector("span").textContent = w.subject;
    }
    viewer.setFiles(w.files);
    const kind = params.get("kind");
    viewer.show(WORKSHEET_KINDS.some((k) => k.kind === kind) ? kind : "topic");
  } catch (err) {
    document.getElementById("w-title").textContent = "Could not load worksheet";
    document.getElementById("w-assigned").textContent = err.message;
  }
})();
