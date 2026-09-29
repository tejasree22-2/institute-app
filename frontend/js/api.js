// set by js/config.js on deployed builds; locally the static server on :8080/:8888 talks to the API
// on :8010, and a frontend served by the backend itself uses the same origin
const API_BASE = window.API_BASE ?? (["8080", "8888"].includes(window.location.port) ? "http://localhost:8010" : "");

function authToken() {
  return localStorage.getItem("token");
}

function currentUser() {
  const raw = localStorage.getItem("user");
  return raw ? JSON.parse(raw) : null;
}

function isLoggedIn() {
  return !!authToken();
}

function logout() {
  localStorage.removeItem("token");
  localStorage.removeItem("user");
  window.location.href = rootPath() + "index.html";
}

function rootPath() {
  const depth = window.location.pathname.split("/").filter(Boolean);
  const inSubdir = depth.some((p) => p === "student" || p === "instructor");
  return inSubdir ? "../" : "";
}

async function api(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth) {
    const token = authToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401) {
    logout();
    throw new Error("Session expired");
  }

  let data = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }

  if (!res.ok) {
    let detail = (data && data.detail) || res.statusText || "Request failed";
    if (Array.isArray(detail)) {
      // FastAPI validation errors: [{loc: ["body", "password"], msg: "..."}]
      detail = detail.map((d) => {
        const field = String(d.loc?.at(-1) ?? "");
        const msg = /should match pattern/.test(d.msg) ? "is not valid" : d.msg;
        return field ? `${field}: ${msg}` : msg;
      }).join("; ");
    }
    throw new Error(detail);
  }
  return data;
}

function requireRole(role) {
  const user = currentUser();
  if (!isLoggedIn() || !user) {
    window.location.href = rootPath() + "index.html";
    return null;
  }
  if (user.role !== role) {
    window.location.href = rootPath() + (user.role === "instructor" ? "instructor/library.html" : "student/dashboard.html");
    return null;
  }
  return user;
}

function initials(name) {
  return name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
}

function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function statusPillHtml(status, detail) {
  const cls = status === "all_passed" ? "pill-green" : status === "partial" || status === "failed" ? "pill-amber" : "pill-grey";
  const label = status === "failed" ? detail || "0 of N passed" : detail;
  return `<span class="pill ${cls}">${escapeHtml(label)}</span>`;
}

const TYPE_BADGES = {
  coding: { icon: "ti-code", cls: "type-coding", label: "Coding" },
  video: { icon: "ti-video", cls: "type-video", label: "Video" },
  worksheet: { icon: "ti-file-text", cls: "type-worksheet", label: "Worksheet" },
  interactive: { icon: "ti-messages", cls: "type-interactive", label: "Interactive" },
  daily_task: { icon: "ti-checklist", cls: "type-daily-task", label: "Daily task" },
  reading: { icon: "ti-book", cls: "type-reading", label: "Reading" },
};

function typeBadgeHtml(type) {
  const t = TYPE_BADGES[type] || TYPE_BADGES.coding;
  return `<span class="type-badge ${t.cls}"><i class="ti ${t.icon}"></i>${t.label}</span>`;
}

function difficultyPillHtml(difficulty) {
  const d = (difficulty || "easy").toLowerCase();
  const label = d.charAt(0).toUpperCase() + d.slice(1);
  return `<span class="pill difficulty-${d}">${label}</span>`;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
