// Tabbed Topic / Questions / Answers viewer, shared by the instructor preview and the student workspace.
// Pages synced from the worksheet repo are shown inline in an iframe; uploaded files get a download button.

// extra_* sheets only exist for some repo tasks, so they are hidden wherever a worksheet lacks them
const WORKSHEET_KINDS = [
  { kind: "topic", label: "Topic", icon: "ti-book" },
  { kind: "questions", label: "Questions", icon: "ti-help-circle" },
  { kind: "answers", label: "Answers", icon: "ti-key" },
  { kind: "extra_questions", label: "Extra Questions", icon: "ti-help-circle", optional: true },
  { kind: "extra_answers", label: "Extra Answers", icon: "ti-key", optional: true },
];

// the link text used on the repo's subject index ("[Questions]", "[ans]", ...) for one sheet
function sheetLinkText(kind, label) {
  const k = WORKSHEET_KINDS.find((x) => x.kind === kind);
  return kind === "topic" ? (label || k.label) : `[${label || (k ? k.label : kind)}]`;
}

async function downloadAuthed(path, filename) {
  const res = await fetch(`${API_BASE}${path}`, { headers: { Authorization: `Bearer ${authToken()}` } });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error((data && data.detail) || "Could not download file");
  }
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// opts: basePath ("/worksheets/3" or "/me/worksheets/3"), numbered (show tabs as steps 1-2-3),
// newTabLink (offer "Open in new tab"), onlyPresent (hide tabs of sheets that weren't given),
// lockedHint + lockedAction ({label, onClick}) for the locked screen, barFor(kind) -> HTML shown
// above the sheet (or ""), onChange(kind)
function createWorksheetViewer(root, { basePath, numbered = false, newTabLink = true, onlyPresent = false, lockedHint = "", lockedAction, barFor, onChange } = {}) {
  root.innerHTML = `
    <div class="ws-tabs" role="tablist">
      ${WORKSHEET_KINDS.map((k, i) => `
        <button class="ws-tab" role="tab" data-kind="${k.kind}">
          ${numbered ? `<span class="ws-step">${i + 1}</span>` : `<i class="ti ${k.icon}"></i>`} ${k.label}
        </button>
      `).join("")}
      <div class="ws-bar" hidden></div>
      <a class="ws-tool ws-newtab" target="_blank" rel="noopener" hidden><i class="ti ti-external-link"></i> Open in new tab</a>
    </div>
    <div class="ws-pane card"></div>
  `;
  const pane = root.querySelector(".ws-pane");
  const newTab = root.querySelector(".ws-newtab");
  const bar = root.querySelector(".ws-bar");
  let files = {};
  let locked = new Set();
  let current = null;
  let showSeq = 0;

  root.querySelectorAll(".ws-tab").forEach((btn) => btn.addEventListener("click", () => show(btn.dataset.kind)));

  function message(icon, text, action) {
    pane.innerHTML = `
      <div class="ws-message">
        <i class="ti ${icon}"></i><p>${escapeHtml(text)}</p>
        ${action ? `<button class="btn btn-primary">${escapeHtml(action.label)}</button>` : ""}
      </div>`;
    if (action) pane.querySelector("button").addEventListener("click", action.onClick);
  }

  function renderBar(kind) {
    const html = barFor ? barFor(kind) : "";
    bar.innerHTML = html;
    bar.hidden = !html;
  }

  async function show(kind) {
    const seq = ++showSeq;
    current = kind;
    root.querySelectorAll(".ws-tab").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.kind === kind);
      btn.setAttribute("aria-selected", btn.dataset.kind === kind);
    });
    newTab.hidden = true;
    renderBar(kind);
    if (onChange) onChange(kind);

    const file = files[kind];
    if (locked.has(kind)) return message("ti-lock", lockedHint, lockedAction);
    if (!file) return message("ti-file-off", "Not uploaded yet.");

    if (!file.viewable) {
      pane.innerHTML = `
        <div class="ws-message">
          <i class="ti ti-file-download"></i>
          <button class="btn btn-secondary btn-sm"><i class="ti ti-download"></i> ${escapeHtml(file.original_filename)}</button>
        </div>`;
      const btn = pane.querySelector("button");
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          await downloadAuthed(`${basePath}/files/${kind}/download`, file.original_filename);
        } catch (err) {
          alert(err.message);
        } finally {
          btn.disabled = false;
        }
      });
      return;
    }

    message("ti-loader", "Loading…");
    try {
      const { url } = await api(`${basePath}/files/${kind}/view-link`, { method: "POST" });
      if (seq !== showSeq) return; // another tab was clicked meanwhile
      pane.innerHTML = `<iframe class="ws-frame" title="${escapeHtml(kind)}" src="${API_BASE + url}?embed=1"></iframe>`;
      newTab.href = API_BASE + url;
      newTab.hidden = !newTabLink;
    } catch (err) {
      if (seq === showSeq) message("ti-alert-triangle", err.message);
    }
  }

  return {
    // fileList: [{kind, original_filename, viewable}], lockedKinds: shown as locked, doneKinds: ticked
    setFiles(fileList, lockedKinds = [], doneKinds = []) {
      files = Object.fromEntries(fileList.filter(Boolean).map((f) => [f.kind, f]));
      locked = new Set(lockedKinds);
      root.querySelectorAll(".ws-tab").forEach((btn) => {
        btn.classList.toggle("locked", locked.has(btn.dataset.kind));
        btn.classList.toggle("done", doneKinds.includes(btn.dataset.kind));
        const optional = WORKSHEET_KINDS.find((k) => k.kind === btn.dataset.kind).optional;
        btn.hidden = (onlyPresent || optional) && !files[btn.dataset.kind];
      });
      if (current) renderBar(current);
    },
    show,
    get current() { return current; },
  };
}

// Topic / Questions / Answers buttons for a worksheet row. hrefFor(kind) gives each button's link;
// sheets not in `present` are greyed out, or left out entirely with hideMissing.
function worksheetPartButtonsHtml(hrefFor, { present = ["topic", "questions", "answers"], locked = [], hideMissing = false } = {}) {
  return `<div class="ws-parts">${WORKSHEET_KINDS.map((k) => {
    if (!present.includes(k.kind)) {
      if (hideMissing || k.optional) return "";
      return `<span class="btn btn-secondary btn-sm" aria-disabled="true" style="opacity:.45;" title="Not uploaded yet"><i class="ti ${k.icon}"></i> ${k.label}</span>`;
    }
    const lock = locked.includes(k.kind) ? ` <i class="ti ti-lock"></i>` : "";
    return `<a class="btn btn-secondary btn-sm" href="${hrefFor(k.kind)}" onclick="event.stopPropagation()"><i class="ti ${k.icon}"></i> ${k.label}${lock}</a>`;
  }).join("")}</div>`;
}

// One subject laid out like the repo's subject index (aikaryashala.com/first-steps/ganitham/):
// "Practice <Subject>", then a line per item: its title (the topic link) followed by [Questions] [ans] ...
// items: [{id, title, sheets: [kind], labels: {kind: link text}}] in index order; only `sheets` get links.
// hrefFor(item, kind) -> link; sideFor(item) -> HTML shown under / beside the line (optional);
// footer -> HTML after the list (the site's "← Back to Practice").
function worksheetIndexHtml(subject, items, hrefFor, sideFor, footer = "") {
  const rows = items.map((it) => {
    const labels = it.labels || {};
    const title = it.sheets.includes("topic")
      ? `<a href="${hrefFor(it, "topic")}">${escapeHtml(sheetLinkText("topic", it.title))}</a>`
      : `<span>${escapeHtml(it.title)}</span>`;
    const links = WORKSHEET_KINDS
      .filter((k) => k.kind !== "topic" && it.sheets.includes(k.kind))
      .map((k) => `<a class="q" href="${hrefFor(it, k.kind)}">${escapeHtml(sheetLinkText(k.kind, labels[k.kind]))}</a>`)
      .join(" ");
    return `<li><div class="ws-index-line">${title} ${links}</div>${sideFor ? sideFor(it) : ""}</li>`;
  }).join("");
  return `
    <div class="ws-index">
      <h1>Practice ${escapeHtml(subject)}</h1>
      <ul>${rows}</ul>
      ${footer}
    </div>`;
}
