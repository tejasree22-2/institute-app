const user = requireRole("student");
const params = new URLSearchParams(window.location.search);
const worksheetId = params.get("id");

document.getElementById("user-avatar").textContent = initials(user.name);
document.getElementById("user-name").textContent = user.name;

// only the sheets the instructor assigned to the student's batch come back from the API
const viewer = createWorksheetViewer(document.getElementById("viewer"), {
  basePath: `/me/worksheets/${encodeURIComponent(worksheetId)}`,
  newTabLink: false,
  onlyPresent: true,
  onChange: (kind) => {
    params.set("kind", kind);
    history.replaceState(null, "", `?${params}`);
  },
});

(async function init() {
  try {
    const [batches, w] = await Promise.all([
      api("/me/batches"),
      api(`/me/worksheets/${worksheetId}`),
    ]);
    document.getElementById("batch-name-label").textContent = batches.map((b) => b.name).join(", ") || "No batch assigned";
    document.title = `${w.title} — Institute App`;
    document.getElementById("w-title").textContent = w.title;
    document.getElementById("w-description").textContent = w.description || "";
    if (w.subject_slug) {
      const back = document.querySelector(".back-link");
      back.href = `tasks.html?type=worksheet&subject=${encodeURIComponent(w.subject_slug)}`;
      back.innerHTML = `<i class="ti ti-arrow-left"></i> Practice ${escapeHtml(w.subject)}`;
    }
    document.getElementById("w-pills").innerHTML = w.subject ? `<span class="pill pill-grey">${escapeHtml(w.subject)}</span>` : "";

    if (w.kinds.length === 0) {
      document.getElementById("viewer").innerHTML =
        `<div class="card ws-message"><i class="ti ti-file-off"></i><p>No sheets have been shared with your batch yet.</p></div>`;
      return;
    }
    viewer.setFiles(w.files);
    const kind = params.get("kind");
    viewer.show(w.kinds.includes(kind) ? kind : w.kinds[0]);
  } catch (err) {
    document.getElementById("w-title").textContent = "Could not load worksheet";
    document.getElementById("w-description").textContent = err.message;
  }
})();
