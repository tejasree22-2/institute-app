const CATEGORIES = [
  { type: "coding", icon: "ti-code", label: "Coding", desc: "Solve-and-test coding questions", href: "coding-library.html", enabled: true },
  { type: "worksheet", icon: "ti-file-text", label: "Worksheet", desc: "Topic + questions + answers file sets", href: "worksheets.html", enabled: true },
  { type: "video", icon: "ti-video", label: "Video", desc: "Lecture videos", href: null, enabled: false },
  { type: "interactive", icon: "ti-messages", label: "Interactive", desc: "Interactive activities and quizzes", href: null, enabled: false },
  { type: "daily_task", icon: "ti-checklist", label: "Daily Task", desc: "Day-to-day assignments", href: null, enabled: false },
  { type: "reading", icon: "ti-book", label: "Reading", desc: "Reading material and articles", href: null, enabled: false },
];

document.addEventListener("DOMContentLoaded", async () => {
  const user = requireRole("instructor");
  if (!user) return;

  document.getElementById("user-avatar").textContent = initials(user.name);
  document.getElementById("user-name").textContent = user.name;

  let counts = {};
  try {
    const [questions, worksheets] = await Promise.all([
      api("/questions"),
      api("/worksheets"),
    ]);
    counts = { coding: questions.length, worksheet: worksheets.length };
  } catch (err) {
    console.error("Failed to load library counts", err);
  }

  renderCategories(counts);
});

function renderCategories(counts) {
  const grid = document.getElementById("category-grid");
  grid.innerHTML = CATEGORIES.map((c) => {
    const count = counts[c.type] || 0;
    const disabledAttrs = c.enabled ? `onclick="window.location.href='${c.href}'"` : `style="opacity:.55; cursor:default;"`;
    const countLabel = c.enabled ? `${count} item${count === 1 ? "" : "s"}` : "Coming soon";
    return `
      <div class="category-card" ${disabledAttrs}>
        <div class="category-icon"><i class="ti ${c.icon}"></i></div>
        <div class="category-body">
          <div class="category-label">${escapeHtml(c.label)}</div>
          <div class="category-desc">${escapeHtml(c.desc)}</div>
        </div>
        <div class="category-count">${countLabel}</div>
      </div>
    `;
  }).join("");
}
