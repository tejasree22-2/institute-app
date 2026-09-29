const CATEGORIES = [
  { type: "coding", icon: "ti-code", label: "Coding", desc: "Solve problems and run test cases" },
  { type: "video", icon: "ti-video", label: "Video", desc: "Watch assigned lecture videos" },
  { type: "worksheet", icon: "ti-file-text", label: "Worksheet", desc: "Practice worksheets and exercises" },
  { type: "interactive", icon: "ti-messages", label: "Interactive", desc: "Interactive activities and quizzes" },
  { type: "daily_task", icon: "ti-checklist", label: "Daily Task", desc: "Your day-to-day assignments" },
  { type: "reading", icon: "ti-book", label: "Reading", desc: "Reading material and articles" },
];

document.addEventListener("DOMContentLoaded", async () => {
  const user = requireRole("student");
  if (!user) return;

  document.getElementById("user-avatar").textContent = initials(user.name);
  document.getElementById("user-name").textContent = user.name;

  try {
    const [batches, tasks] = await Promise.all([
      api("/me/batches"),
      api("/me/tasks"),
    ]);

    const batchNames = batches.map((b) => b.name).join(", ") || "No batch assigned";
    document.getElementById("batch-name-label").textContent = batchNames;
    document.getElementById("batch-subtitle").textContent = batches.length
      ? batchNames
      : "You're not in a batch yet — your instructor will add you, and your tasks will appear here.";

    renderCategories(tasks);
  } catch (err) {
    document.getElementById("batch-subtitle").textContent = "Could not load dashboard: " + err.message;
  }
});

function renderCategories(tasks) {
  const counts = {};
  for (const t of tasks) {
    counts[t.type] = (counts[t.type] || 0) + 1;
  }

  const grid = document.getElementById("category-grid");
  grid.innerHTML = CATEGORIES.map((c) => {
    const count = counts[c.type] || 0;
    return `
      <div class="category-card" onclick="openCategory('${c.type}')">
        <div class="category-icon"><i class="ti ${c.icon}"></i></div>
        <div class="category-body">
          <div class="category-label">${escapeHtml(c.label)}</div>
          <div class="category-desc">${escapeHtml(c.desc)}</div>
        </div>
        <div class="category-count">${count} task${count === 1 ? "" : "s"}</div>
      </div>
    `;
  }).join("");
}

function openCategory(type) {
  window.location.href = `tasks.html?type=${encodeURIComponent(type)}`;
}
