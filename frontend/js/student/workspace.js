import { EditorView, basicSetup } from "https://esm.sh/codemirror@6.0.1";
import { python } from "https://esm.sh/@codemirror/lang-python@6.1.6";

const user = requireRole("student");
const params = new URLSearchParams(window.location.search);
const questionId = params.get("id");

let editorView = null;

document.getElementById("user-avatar").textContent = initials(user.name);
document.getElementById("user-name").textContent = user.name;

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      document.querySelectorAll(".tab-content").forEach((c) => (c.hidden = true));
      document.getElementById(`tab-${btn.dataset.tab}`).hidden = false;
    });
  });
}

function renderProblem(q) {
  document.getElementById("q-title-text").textContent = q.title;
  document.getElementById("q-difficulty-pill").innerHTML = difficultyPillHtml(q.difficulty);

  const html = window.marked ? window.marked.parse(q.description || "") : `<p>${escapeHtml(q.description)}</p>`;
  const samplesHtml = q.visible_test_cases.map((tc, i) => `
    <div style="margin-bottom:14px;">
      <div class="small-muted" style="margin-bottom:4px;"><strong>Sample ${i + 1}</strong></div>
      <div class="form-row">
        <div>
          <div class="small-muted">Input</div>
          <pre style="background:#f5f6fa;padding:8px 10px;border-radius:6px;">${escapeHtml(tc.stdin)}</pre>
        </div>
        <div>
          <div class="small-muted">Expected output</div>
          <pre style="background:#f5f6fa;padding:8px 10px;border-radius:6px;">${escapeHtml(tc.expected_stdout)}</pre>
        </div>
      </div>
    </div>
  `).join("");

  document.getElementById("problem-pane").innerHTML = `
    <div class="desc-preview">${html}</div>
    <hr style="border:none;border-top:1px solid var(--border);margin:20px 0;" />
    <h3 style="font-size:14px;">Sample Input / Output</h3>
    ${samplesHtml || '<p class="small-muted">No visible sample test cases.</p>'}
  `;
}

function initEditor(code) {
  const host = document.getElementById("editor-host");
  editorView = new EditorView({
    doc: code,
    extensions: [basicSetup, python()],
    parent: host,
  });
}

function getCode() {
  return editorView.state.doc.toString();
}

function renderResults(data, containerId, { hiddenNote } = {}) {
  const container = document.getElementById(containerId);
  const summary = data.summary;
  const cls = summary.passed === summary.total ? "all" : summary.passed === 0 ? "none" : "some";
  let html = `<div class="summary-bar ${cls}">${summary.passed} of ${summary.total} test cases passed</div>`;

  data.results.forEach((r, i) => {
    const label = r.hidden ? `Hidden test ${i + 1}` : `Test ${i + 1}`;
    html += `
      <div class="result-row ${r.passed ? "pass" : "fail"}">
        <div class="rr-left"><i class="ti ${r.passed ? "ti-circle-check" : "ti-circle-x"}"></i> ${label}</div>
        <div class="rr-time">${r.runtime_ms} ms</div>
      </div>`;
    if (!r.hidden && !r.passed) {
      html += `<div class="result-detail">${escapeHtml(r.error || `Got: ${r.actual_output ?? ""}`)}</div>`;
    }
  });

  if (hiddenNote) {
    html += `<p class="small-muted" style="margin-top:10px;"><i class="ti ti-lock"></i> Hidden test cases show pass/fail only.</p>`;
  }

  container.innerHTML = html;
}

function appendTerminal(text) {
  const box = document.getElementById("terminal-box");
  box.textContent += "\n" + text;
  box.scrollTop = box.scrollHeight;
}

async function loadQuestion() {
  const q = await api(`/me/questions/${questionId}`);
  renderProblem(q);
  initEditor(q.student_code || q.starter_code || "");

  const notes = await api(`/me/questions/${questionId}/notes`);
  document.getElementById("notes-area").value = notes.content || "";
}

async function handleRun() {
  const btn = document.getElementById("run-btn");
  btn.disabled = true;
  btn.innerHTML = `<i class="ti ti-loader-2"></i> Running…`;
  appendTerminal("$ running against visible test cases…");
  document.querySelector('[data-tab="results"]').click();
  try {
    const data = await api(`/me/questions/${questionId}/run`, { method: "POST", body: { code: getCode() } });
    renderResults(data, "tab-results");
    appendTerminal(`Run complete: ${data.summary.passed}/${data.summary.total} passed.`);
  } catch (err) {
    appendTerminal("Error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="ti ti-player-play"></i> Run`;
  }
}

async function handleSubmit() {
  const btn = document.getElementById("submit-btn");
  btn.disabled = true;
  btn.innerHTML = `<i class="ti ti-loader-2"></i> Submitting…`;
  appendTerminal("$ submitting against all test cases…");
  document.querySelector('[data-tab="results"]').click();
  try {
    const data = await api(`/me/questions/${questionId}/submit`, { method: "POST", body: { code: getCode() } });
    renderResults(data, "tab-results", { hiddenNote: true });
    appendTerminal(`Submission #${data.submission_id}: ${data.summary.passed}/${data.summary.total} passed.`);
  } catch (err) {
    appendTerminal("Error: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="ti ti-send"></i> Submit`;
  }
}

function setupNotes() {
  const area = document.getElementById("notes-area");
  const hint = document.getElementById("notes-saved-hint");
  area.addEventListener("blur", async () => {
    try {
      await api(`/me/questions/${questionId}/notes`, { method: "PUT", body: { content: area.value } });
      hint.classList.add("show");
      setTimeout(() => hint.classList.remove("show"), 1500);
    } catch (err) {
      console.error("Failed to save notes", err);
    }
  });
}

(async function init() {
  setupTabs();
  setupNotes();
  document.getElementById("run-btn").addEventListener("click", handleRun);
  document.getElementById("submit-btn").addEventListener("click", handleSubmit);
  try {
    await loadQuestion();
  } catch (err) {
    document.getElementById("problem-pane").innerHTML = `<p style="color:var(--red);">Failed to load task: ${escapeHtml(err.message)}</p>`;
  }
})();
