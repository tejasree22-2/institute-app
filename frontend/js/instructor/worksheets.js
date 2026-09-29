let allBatches = [];
let allWorksheets = [];

const subjectSlug = new URLSearchParams(window.location.search).get("subject");

document.addEventListener("DOMContentLoaded", async () => {
  const user = requireRole("instructor");
  if (!user) return;
  document.getElementById("user-avatar").textContent = initials(user.name);
  document.getElementById("user-name").textContent = user.name;

  allBatches = await api("/batches").catch(() => []);
  await loadWorksheets();

  // new files pushed to the repo show up here once an instructor clicks "Sync from GitHub"
  document.getElementById("ws-sync-btn").addEventListener("click", syncFromRepo);
  const status = await api("/worksheets/sync").catch(() => null);
  if (status) showSyncStatus(status);
});

async function syncFromRepo() {
  const btn = document.getElementById("ws-sync-btn");
  btn.disabled = true;
  btn.querySelector("i").className = "ti ti-loader-2 ws-spin";
  document.getElementById("ws-sync-text").textContent = "Checking the GitHub repo for new or changed worksheets…";
  try {
    const status = await api("/worksheets/sync", { method: "POST" });
    await loadWorksheets();
    showSyncStatus(status, true);
  } catch (err) {
    document.getElementById("ws-sync-text").textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.querySelector("i").className = "ti ti-refresh";
  }
}

function showSyncStatus(s, justRan = false) {
  const text = document.getElementById("ws-sync-text");
  text.classList.toggle("ws-sync-error", !!s.last_error);
  if (s.last_error) { text.textContent = s.last_error; return; }
  if (s.running) { text.textContent = "Another sync is running — refresh in a moment."; return; }
  if (!s.last_synced_at) { text.textContent = "Worksheets come from the GitHub repo. Click Sync to pull new files."; return; }
  const added = s.added.length ? ` · ${s.added.length} new` : " · nothing new";
  text.textContent = `Synced with the GitHub repo ${timeAgo(s.last_synced_at)}${added}`;
  showSyncReport(s.items, justRan);
}

const SYNC_ITEM_STATUS = {
  new: `<span class="pill pill-green"><i class="ti ti-sparkles"></i> New — added to the Library</span>`,
  existing: `<span class="pill pill-grey"><i class="ti ti-check"></i> Already in the Library</span>`,
  not_in_repo: `<span class="pill pill-amber"><i class="ti ti-alert-triangle"></i> No longer in the repo index</span>`,
};
const SYNC_FILE_STATE = {
  in_repo: { icon: "ti-circle-check", cls: "ok", title: "Found in the repo" },
  kept: { icon: "ti-alert-circle", cls: "kept", title: "Not in the repo any more — the saved copy is used" },
  missing: { icon: "ti-circle-x", cls: "missing", title: "Not in the repo and no saved copy — can't be opened" },
};

// every item the sync checked, per subject: new or already there, and whether each file exists in the repo
function showSyncReport(items, open) {
  const report = document.getElementById("ws-sync-report");
  const shown = subjectSlug ? items.filter((it) => allWorksheets.some((w) => w.id === it.worksheet_id && w.subject_slug === subjectSlug)) : items;
  report.hidden = shown.length === 0;
  if (!shown.length) return;
  const count = (status) => shown.filter((it) => it.status === status).length;
  const problems = shown.filter((it) => it.files.some((f) => f.state !== "in_repo")).length;
  document.getElementById("ws-sync-summary").innerHTML =
    `<strong>Sync check</strong> · ${shown.length} item${shown.length === 1 ? "" : "s"} checked · ${count("new")} new · ${count("existing")} already in the Library` +
    (problems ? ` · <span class="ws-sync-warn">${problems} with files not in the repo</span>` : "");

  const subjects = new Map();
  for (const it of shown) {
    if (!subjects.has(it.subject)) subjects.set(it.subject, []);
    subjects.get(it.subject).push(it);
  }
  document.getElementById("ws-sync-items").innerHTML = Array.from(subjects, ([subject, rows]) => `
    <div class="ws-sync-subject">${escapeHtml(subject)}</div>
    ${rows.map((it) => `
      <div class="ws-sync-row">
        <div class="ws-sync-title">${escapeHtml(it.title)} ${SYNC_ITEM_STATUS[it.status] || ""}</div>
        <div class="ws-sync-files">${it.files.map((f) => {
          const st = SYNC_FILE_STATE[f.state];
          return `<span class="ws-sync-file ${st.cls}" title="${st.title}"><i class="ti ${st.icon}"></i> ${escapeHtml(sheetLinkText(f.kind, f.kind === "topic" ? "Topic" : f.label))}</span>`;
        }).join("")}</div>
      </div>`).join("")}
  `).join("") + `
    <div class="ws-sync-legend small-muted">
      ${Object.values(SYNC_FILE_STATE).map((st) => `<span class="ws-sync-file ${st.cls}"><i class="ti ${st.icon}"></i> ${st.title}</span>`).join("")}
    </div>`;
  if (open) report.open = true;
}

function timeAgo(iso) {
  const minutes = Math.round((Date.now() - new Date(iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z")) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  return formatDateTime(iso);
}

async function loadWorksheets() {
  const list = document.getElementById("worksheet-list");
  const empty = document.getElementById("empty-state");
  try {
    allWorksheets = await api("/worksheets");
    if (subjectSlug) {
      renderSubjectPage(allWorksheets.filter((w) => w.subject_slug === subjectSlug));
      return;
    }

    renderSubjectGrid(allWorksheets.filter((w) => w.subject_slug));
    const uploaded = allWorksheets.filter((w) => !w.subject_slug);
    document.getElementById("uploaded-heading").style.display = uploaded.length ? "" : "none";
    list.innerHTML = uploaded.map(worksheetCardHtml).join("");
    empty.style.display = allWorksheets.length === 0 ? "block" : "none";
  } catch (err) {
    list.innerHTML = `<p style="color:var(--red);">${escapeHtml(err.message)}</p>`;
  }
}

function renderSubjectGrid(synced) {
  const subjects = new Map();
  for (const w of synced) {
    if (!subjects.has(w.subject_slug)) subjects.set(w.subject_slug, { name: w.subject, count: 0 });
    subjects.get(w.subject_slug).count += 1;
  }
  document.getElementById("subject-grid").innerHTML = Array.from(subjects, ([slug, s]) => `
    <div class="category-card" onclick="window.location.href='worksheets.html?subject=${encodeURIComponent(slug)}'">
      <div class="category-icon"><i class="ti ti-folder"></i></div>
      <div class="category-body">
        <div class="category-label">${escapeHtml(s.name)}</div>
        <div class="category-desc">Topic, questions and answers for each task.</div>
      </div>
      <div class="category-count">${s.count} topic${s.count === 1 ? "" : "s"}</div>
    </div>
  `).join("");
}

function renderSubjectPage(worksheets) {
  const name = worksheets.length ? worksheets[0].subject : subjectSlug;
  document.title = `${name} — Worksheets — Institute App`;
  document.getElementById("page-title").textContent = name;
  document.getElementById("page-subtitle").textContent =
    "Laid out like the worksheet repo. Choose, for each file, which batches can open it — students see only those files.";
  const back = document.getElementById("back-link");
  back.href = "worksheets.html";
  back.querySelector("span").textContent = "Worksheets";
  document.getElementById("new-worksheet-btn").style.display = "none";
  document.getElementById("subject-grid").style.display = "none";

  document.getElementById("worksheet-list").innerHTML = worksheets.length
    ? worksheetIndexHtml(
      name,
      worksheets.map((w) => ({
        ...w,
        sheets: w.files.map((f) => f.kind),
        labels: Object.fromEntries(w.files.filter((f) => f.label).map((f) => [f.kind, f.label])),
      })),
      (w, kind) => `worksheet-view.html?id=${w.id}&kind=${kind}`,
      fileBatchesHtml,
    )
    : `<p class="small-muted">No worksheets in this subject.</p>`;
}

// under each index line: which batches can open each of its files, and the button to change that
function fileBatchesHtml(w) {
  const names = Object.fromEntries(allBatches.map((b) => [b.id, b.name]));
  const parts = WORKSHEET_KINDS.filter((k) => w.sheets.includes(k.kind)).map((k) => {
    const batches = w.assignments.filter((a) => a.kinds.includes(k.kind)).map((a) => names[a.batch_id] || `Batch ${a.batch_id}`);
    return `<span><strong>${escapeHtml(sheetLinkText(k.kind, k.kind === "topic" ? "Topic" : w.labels[k.kind]))}</strong>
      ${batches.length ? escapeHtml(batches.join(", ")) : "no batch"}</span>`;
  }).join("");
  const button = w.verified_at
    ? `<button class="btn btn-secondary btn-sm" onclick="assignWorksheet(${w.id})"><i class="ti ti-users"></i> Batches</button>`
    : `<span class="pill pill-grey"><i class="ti ti-alert-circle"></i> Not verified</span>`;
  return `<div class="ws-index-batches"><i class="ti ti-users"></i> ${parts} ${button}</div>`;
}

function worksheetCardHtml(w) {
  const verified = !!w.verified_at;
  const viewHref = (kind) => `worksheet-view.html?id=${w.id}&kind=${kind}`;
  const assignBtn = verified
    ? `<button class="btn btn-primary btn-sm" onclick="assignWorksheet(${w.id})"><i class="ti ti-send"></i> Assign to batch</button>`
    : `<span class="tooltip-wrap" data-tooltip="Upload all 3 files and verify before assigning"><button class="btn btn-primary btn-sm" disabled><i class="ti ti-send"></i> Assign to batch</button></span>`;

  return `
    <div class="card topic-card">
      <div class="topic-card-main">
        <a class="topic-card-title" href="${viewHref("topic")}">${escapeHtml(w.title)}</a>
        ${worksheetPartButtonsHtml(viewHref, { present: w.files.map((f) => f.kind) })}
        <div class="topic-card-assigned small-muted">
          <i class="ti ti-users"></i> ${escapeHtml(assignmentSummaryText(w.assignments, allBatches))}
          ${verified ? "" : `<span class="pill pill-grey"><i class="ti ti-alert-circle"></i> Not verified</span>`}
        </div>
      </div>
      <div class="topic-card-corner">
        <a class="btn btn-secondary btn-sm" href="worksheet-editor.html?id=${w.id}" title="Edit"><i class="ti ti-edit"></i></a>
        ${assignBtn}
      </div>
    </div>
  `;
}

function assignWorksheet(worksheetId) {
  const w = allWorksheets.find((x) => x.id === worksheetId);
  openAssignSheetsModal(w, () => loadWorksheets());
}
