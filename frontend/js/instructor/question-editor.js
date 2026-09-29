import { EditorView, basicSetup } from "https://esm.sh/codemirror@6.0.1";
import { python } from "https://esm.sh/@codemirror/lang-python@6.1.6";

const user = requireRole("instructor");
document.getElementById("user-avatar").textContent = initials(user.name);
document.getElementById("user-name").textContent = user.name;

const params = new URLSearchParams(window.location.search);
let questionId = params.get("id") ? parseInt(params.get("id"), 10) : null;

let testCases = []; // { id: number|null, stdin, expected_stdout, is_hidden }
let deletedTestCaseIds = [];
let initialized = false;
let verified = false;

let starterEditor, referenceEditor;

function makeEditor(host, doc) {
  return new EditorView({
    doc,
    extensions: [basicSetup, python(), EditorView.updateListener.of((u) => {
      if (u.docChanged) markDirty();
    })],
    parent: host,
  });
}

function markDirty() {
  if (!initialized) return;
  verified = false;
  document.getElementById("verify-banner-success").classList.remove("show-success");
  document.getElementById("verify-banner-fail").classList.remove("show-fail");
  document.getElementById("verify-results").innerHTML = "";
  updateSaveButton();
}

function updateSaveButton() {
  const btn = document.getElementById("save-btn");
  btn.disabled = !verified;
  btn.title = verified ? "" : "Run all tests and pass every case before saving";
}

function renderTestCaseRows() {
  const tbody = document.getElementById("tc-tbody");
  if (testCases.length === 0) {
    tbody.innerHTML = `<tr><td colspan="4" class="small-muted" style="padding:14px 8px;">No test cases yet. Add at least one before verifying.</td></tr>`;
    return;
  }
  tbody.innerHTML = testCases.map((tc, i) => `
    <tr data-idx="${i}">
      <td><textarea class="tc-stdin" rows="2">${escapeHtml(tc.stdin)}</textarea></td>
      <td><textarea class="tc-expected" rows="2">${escapeHtml(tc.expected_stdout)}</textarea></td>
      <td class="col-hidden"><input type="checkbox" class="tc-hidden" ${tc.is_hidden ? "checked" : ""} /></td>
      <td class="col-actions"><button class="tc-icon-btn" title="Delete test case" data-action="delete"><i class="ti ti-trash"></i></button></td>
    </tr>
  `).join("");

  tbody.querySelectorAll("tr").forEach((row) => {
    const idx = parseInt(row.dataset.idx, 10);
    row.querySelector(".tc-stdin").addEventListener("input", (e) => { testCases[idx].stdin = e.target.value; markDirty(); });
    row.querySelector(".tc-expected").addEventListener("input", (e) => { testCases[idx].expected_stdout = e.target.value; markDirty(); });
    row.querySelector(".tc-hidden").addEventListener("change", (e) => { testCases[idx].is_hidden = e.target.checked; markDirty(); });
    row.querySelector('[data-action="delete"]').addEventListener("click", () => {
      const removed = testCases.splice(idx, 1)[0];
      if (removed.id) deletedTestCaseIds.push(removed.id);
      renderTestCaseRows();
      markDirty();
    });
  });
}

function currentFormValues() {
  return {
    title: document.getElementById("f-title").value.trim(),
    difficulty: document.getElementById("f-difficulty").value,
    description: document.getElementById("f-description").value,
    starter_code: starterEditor.state.doc.toString(),
    reference_solution: referenceEditor.state.doc.toString(),
  };
}

async function syncToServer() {
  const values = currentFormValues();
  if (!values.title) throw new Error("Please give the question a title.");
  if (testCases.length === 0) throw new Error("Add at least one test case before verifying.");

  if (!questionId) {
    const created = await api("/questions", {
      method: "POST",
      body: { ...values, test_cases: testCases.map(({ stdin, expected_stdout, is_hidden }) => ({ stdin, expected_stdout, is_hidden })) },
    });
    questionId = created.id;
    testCases = created.test_cases.map((tc) => ({ id: tc.id, stdin: tc.stdin, expected_stdout: tc.expected_stdout, is_hidden: tc.is_hidden }));
    renderTestCaseRows();
    return;
  }

  await api(`/questions/${questionId}`, { method: "PUT", body: values });

  for (const id of deletedTestCaseIds) {
    await api(`/test-cases/${id}`, { method: "DELETE" });
  }
  deletedTestCaseIds = [];

  for (const tc of testCases) {
    const payload = { stdin: tc.stdin, expected_stdout: tc.expected_stdout, is_hidden: tc.is_hidden };
    if (tc.id) {
      await api(`/test-cases/${tc.id}`, { method: "PUT", body: payload });
    } else {
      const created = await api(`/questions/${questionId}/test-cases`, { method: "POST", body: payload });
      tc.id = created.id;
    }
  }
}

async function handleVerify() {
  const btn = document.getElementById("verify-btn");
  btn.disabled = true;
  btn.innerHTML = `<i class="ti ti-loader-2"></i> Running…`;
  document.getElementById("verify-banner-success").classList.remove("show-success");
  document.getElementById("verify-banner-fail").classList.remove("show-fail");

  try {
    await syncToServer();
    const data = await api(`/questions/${questionId}/verify`, { method: "POST" });

    const resultsHtml = data.results.map((r, i) => `
      <div class="verify-result-row ${r.passed ? "pass" : "fail"}">
        <span><i class="ti ${r.passed ? "ti-circle-check" : "ti-circle-x"}"></i> Test ${i + 1}${r.hidden ? " (hidden)" : ""}</span>
        <span>${r.passed ? "Passed" : (r.error ? escapeHtml(r.error) : "Failed")} · ${r.runtime_ms} ms</span>
      </div>
    `).join("");
    document.getElementById("verify-results").innerHTML = resultsHtml;

    verified = data.summary.passed === data.summary.total;
    initialized = true; // allow future edits to mark dirty
    document.getElementById(verified ? "verify-banner-success" : "verify-banner-fail")
      .classList.add(verified ? "show-success" : "show-fail");
    updateSaveButton();

    if (questionId && !new URLSearchParams(window.location.search).get("id")) {
      const url = new URL(window.location.href);
      url.searchParams.set("id", questionId);
      window.history.replaceState({}, "", url);
      document.getElementById("page-title").textContent = "Edit Question";
    }
  } catch (err) {
    alert("Could not verify: " + err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = `<i class="ti ti-player-play"></i> Run all tests`;
  }
}

function handleSave() {
  window.location.href = "coding-library.html";
}

async function loadExisting() {
  const q = await api(`/questions/${questionId}`);
  document.getElementById("page-title").textContent = "Edit Question";
  document.getElementById("f-title").value = q.title;
  document.getElementById("f-difficulty").value = q.difficulty;
  document.getElementById("f-description").value = q.description;
  testCases = q.test_cases.map((tc) => ({ id: tc.id, stdin: tc.stdin, expected_stdout: tc.expected_stdout, is_hidden: tc.is_hidden }));
  renderTestCaseRows();

  starterEditor = makeEditor(document.getElementById("starter-code-host"), q.starter_code || "");
  referenceEditor = makeEditor(document.getElementById("reference-code-host"), q.reference_solution || "");

  verified = !!q.verified_at;
  updateSaveButton();
  if (verified) document.getElementById("verify-banner-success").classList.add("show-success");
}

function loadBlank() {
  testCases = [{ id: null, stdin: "", expected_stdout: "", is_hidden: false }];
  renderTestCaseRows();
  starterEditor = makeEditor(document.getElementById("starter-code-host"), "# starter code shown to students\n");
  referenceEditor = makeEditor(document.getElementById("reference-code-host"), "# write a correct reference solution\n");
  updateSaveButton();
}

(async function init() {
  document.getElementById("add-tc-btn").addEventListener("click", () => {
    testCases.push({ id: null, stdin: "", expected_stdout: "", is_hidden: false });
    renderTestCaseRows();
    markDirty();
  });
  document.getElementById("verify-btn").addEventListener("click", handleVerify);
  document.getElementById("save-btn").addEventListener("click", handleSave);
  ["f-title", "f-difficulty", "f-description"].forEach((id) => {
    document.getElementById(id).addEventListener("input", markDirty);
    document.getElementById(id).addEventListener("change", markDirty);
  });

  try {
    if (questionId) {
      await loadExisting();
    } else {
      loadBlank();
    }
  } finally {
    initialized = true;
  }
})();
