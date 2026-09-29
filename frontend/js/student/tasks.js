document.addEventListener("DOMContentLoaded", async () => {
  const user = requireRole("student");
  if (!user) return;

  document.getElementById("user-avatar").textContent = initials(user.name);
  document.getElementById("user-name").textContent = user.name;

  const typeFilter = new URLSearchParams(window.location.search).get("type");
  applyCategoryHeader(typeFilter);

  try {
    const [batches, allTasks] = await Promise.all([
      api("/me/batches"),
      api("/me/tasks"),
    ]);

    const tasks = typeFilter ? allTasks.filter((t) => t.type === typeFilter) : allTasks;

    const batchNames = batches.map((b) => b.name).join(", ") || "No batch assigned";
    document.getElementById("batch-name-label").textContent = batchNames;
    document.getElementById("batch-subtitle").textContent = batchNames;
    document.getElementById("task-count").textContent =
      tasks.length === 0 ? "" : `${tasks.length} task${tasks.length === 1 ? "" : "s"}`;

    renderTasks(tasks, typeFilter);
  } catch (err) {
    document.getElementById("batch-subtitle").textContent = "Could not load tasks: " + err.message;
  }
});

function applyCategoryHeader(type) {
  const footer = document.getElementById("footer-note");
  if (!type) {
    document.getElementById("page-title").textContent = "My Tasks";
    return;
  }
  const t = TYPE_BADGES[type] || TYPE_BADGES.coding;
  document.getElementById("page-title").innerHTML = `<i class="ti ${t.icon}"></i> ${escapeHtml(t.label)} Tasks`;
  footer.style.display = "none";
}

function renderTasks(tasks, typeFilter) {
  const list = document.getElementById("task-list");
  const empty = document.getElementById("empty-state");

  if (tasks.length === 0) {
    list.innerHTML = "";
    if (typeFilter) {
      const t = TYPE_BADGES[typeFilter] || TYPE_BADGES.coding;
      empty.querySelector("strong").textContent = `No ${t.label.toLowerCase()} tasks assigned yet.`;
      empty.querySelector(".small-muted").textContent =
        `Once your instructor assigns ${t.label.toLowerCase()} tasks to your batch, they will show up here.`;
    }
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  if (typeFilter === "worksheet") {
    list.innerHTML = worksheetPracticeHtml(tasks, new URLSearchParams(window.location.search).get("subject"));
    return;
  }

  list.innerHTML = tasks.map((t) => {
    const metaParts = [];
    if (t.metadata.difficulty) metaParts.push(t.metadata.difficulty.charAt(0).toUpperCase() + t.metadata.difficulty.slice(1));
    if (t.metadata.test_case_count !== undefined && t.metadata.test_case_count !== null) {
      metaParts.push(`${t.metadata.test_case_count} test case${t.metadata.test_case_count === 1 ? "" : "s"}`);
    }
    metaParts.push(`Assigned ${formatDate(t.assigned_at)}`);

    return `
      <div class="card task-row" onclick="openTask('${t.type}', ${t.id})">
        <div class="task-main">
          <div class="task-title">${escapeHtml(t.title)}</div>
          <div class="task-meta">${metaParts.map((p) => escapeHtml(p)).join(' <span class="dotsep"></span> ')}</div>
          ${t.type === "worksheet" ? worksheetPartButtonsHtml(
            (kind) => `worksheet-workspace.html?id=${t.id}&kind=${kind}`,
            { present: t.metadata.sheets || [], hideMissing: true },
          ) : ""}
        </div>
        <div class="task-side">
          ${typeBadgeHtml(t.type)}
          ${t.type === "worksheet" ? "" : statusPillHtml(t.status, t.status_detail)}
        </div>
      </div>
    `;
  }).join("");
}

// Worksheets are browsed like the repo site (aikaryashala.com/first-steps/): a "Practice" list of
// subjects, and each subject's page like ganitham/index.html — showing only the files the instructor
// opened to the student's batch
function worksheetPracticeHtml(tasks, subjectSlug) {
  const subjects = new Map();
  for (const t of [...tasks].sort((a, b) => a.id - b.id)) { // synced in repo order
    const slug = t.metadata.subject_slug || "uploaded";
    if (!subjects.has(slug)) subjects.set(slug, { name: t.metadata.subject || "Worksheets", items: [] });
    subjects.get(slug).items.push({ id: t.id, title: t.title, sheets: t.metadata.sheets || [], labels: t.metadata.labels || {}, position: t.metadata.position || 0 });
  }

  const subject = subjectSlug && subjects.get(subjectSlug);
  if (!subject) {
    document.getElementById("footer-note").style.display = "none";
    return `
      <div class="ws-index">
        <h1>Practice</h1>
        <ul>${Array.from(subjects, ([slug, s]) =>
          `<li><a href="tasks.html?type=worksheet&subject=${encodeURIComponent(slug)}">${escapeHtml(s.name)}</a></li>`).join("")}</ul>
      </div>`;
  }
  document.title = `Practice ${subject.name} — Institute App`;
  return worksheetIndexHtml(
    subject.name,
    subject.items.sort((a, b) => a.position - b.position),
    (it, kind) => `worksheet-workspace.html?id=${it.id}&kind=${kind}`,
    null,
    `<p><a href="tasks.html?type=worksheet">&larr; Back to Practice</a></p>`,
  );
}

function openTask(type, id) {
  if (type === "coding") {
    window.location.href = `coding-workspace.html?id=${id}`;
  } else if (type === "worksheet") {
    window.location.href = `worksheet-workspace.html?id=${id}`;
  }
  // future task types would route to their own workspace pages here
}
