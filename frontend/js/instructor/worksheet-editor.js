const user = requireRole("instructor");
document.getElementById("user-avatar").textContent = initials(user.name);
document.getElementById("user-name").textContent = user.name;

const params = new URLSearchParams(window.location.search);
let worksheetId = params.get("id") ? parseInt(params.get("id"), 10) : null;

const FILE_KINDS = [
  { kind: "topic", label: "Topic", desc: "The reading material students learn from first." },
  { kind: "questions", label: "Questions", desc: "The questions students attempt after reading the topic." },
  { kind: "answers", label: "Answers", desc: "Students see it only when you assign the Answers sheet to their batch." },
];

let currentFiles = {}; // kind -> { original_filename, uploaded_at }

async function uploadFile(kind, file) {
  const form = new FormData();
  form.append("kind", kind);
  form.append("file", file);

  const res = await fetch(`${API_BASE}/worksheets/${worksheetId}/files`, {
    method: "POST",
    headers: { Authorization: `Bearer ${authToken()}` },
    body: form,
  });
  const text = await res.text();
  const data = text ? JSON.parse(text) : null;
  if (!res.ok) throw new Error((data && data.detail) || "Upload failed");
  return data;
}

function renderFileSlots() {
  const host = document.getElementById("file-slots");
  host.innerHTML = FILE_KINDS.map(({ kind, label, desc }) => {
    const f = currentFiles[kind];
    const statusHtml = f
      ? `<span class="pill pill-green"><i class="ti ti-circle-check"></i> ${escapeHtml(f.original_filename)}</span>`
      : `<span class="pill pill-grey"><i class="ti ti-file-off"></i> No file yet</span>`;
    return `
      <div class="field" style="border:1px solid var(--border); border-radius:8px; padding:14px; margin-bottom:12px;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
          <div>
            <strong>${escapeHtml(label)}</strong>
            <div class="small-muted">${escapeHtml(desc)}</div>
          </div>
          ${statusHtml}
        </div>
        <input type="file" class="file-input" data-kind="${kind}" />
      </div>
    `;
  }).join("");

  host.querySelectorAll(".file-input").forEach((input) => {
    input.addEventListener("change", async (e) => {
      const kind = e.target.dataset.kind;
      const file = e.target.files[0];
      if (!file) return;
      try {
        const record = await uploadFile(kind, file);
        currentFiles[kind] = record;
        renderFileSlots();
        resetVerifyBanner();
      } catch (err) {
        alert("Upload failed: " + err.message);
      }
    });
  });
}

function resetVerifyBanner() {
  document.getElementById("verify-banner-success").classList.remove("show-success");
  document.getElementById("verify-banner-fail").classList.remove("show-fail");
}

function showFilesSection() {
  document.getElementById("files-hint").hidden = true;
  document.getElementById("file-slots").hidden = false;
  document.getElementById("verify-section").hidden = false;
  renderFileSlots();
}

async function handleSaveDetails() {
  const title = document.getElementById("f-title").value.trim();
  const description = document.getElementById("f-description").value;
  if (!title) { alert("Please give the worksheet a title."); return; }

  const btn = document.getElementById("save-details-btn");
  btn.disabled = true;
  try {
    if (!worksheetId) {
      const created = await api("/worksheets", { method: "POST", body: { title, description } });
      worksheetId = created.id;
      currentFiles = {};
      const url = new URL(window.location.href);
      url.searchParams.set("id", worksheetId);
      window.history.replaceState({}, "", url);
      document.getElementById("page-title").textContent = "Edit Worksheet";
      showFilesSection();
    } else {
      await api(`/worksheets/${worksheetId}`, { method: "PUT", body: { title, description } });
    }
    btn.innerHTML = `<i class="ti ti-circle-check"></i> Saved`;
    setTimeout(() => { btn.innerHTML = `<i class="ti ti-device-floppy"></i> Save details`; }, 1200);
  } catch (err) {
    alert("Could not save: " + err.message);
  } finally {
    btn.disabled = false;
  }
}

async function handleVerify() {
  const btn = document.getElementById("verify-btn");
  btn.disabled = true;
  btn.innerHTML = `<i class="ti ti-loader-2"></i> Verifying…`;
  resetVerifyBanner();
  try {
    await api(`/worksheets/${worksheetId}/verify`, { method: "POST" });
    document.getElementById("verify-banner-success").classList.add("show-success");
  } catch (err) {
    document.getElementById("verify-fail-text").textContent = err.message;
    document.getElementById("verify-banner-fail").classList.add("show-fail");
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="ti ti-player-play"></i> Verify worksheet`;
  }
}

async function loadExisting() {
  const w = await api(`/worksheets/${worksheetId}`);
  document.getElementById("page-title").textContent = "Edit Worksheet";
  document.getElementById("f-title").value = w.title;
  document.getElementById("f-description").value = w.description;
  currentFiles = {};
  for (const f of w.files) currentFiles[f.kind] = f;
  showFilesSection();
  if (w.verified_at) document.getElementById("verify-banner-success").classList.add("show-success");
}

(async function init() {
  document.getElementById("save-details-btn").addEventListener("click", handleSaveDetails);
  document.getElementById("verify-btn").addEventListener("click", handleVerify);

  if (worksheetId) {
    await loadExisting();
  }
})();
