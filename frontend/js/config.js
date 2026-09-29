// Where the backend API lives. On the deployed site it's the Render backend; when the frontend is
// opened from this computer (localhost), api.js falls back to the local backend on :8010 instead.
// If the backend's URL changes, update it here and push.
if (!["localhost", "127.0.0.1"].includes(window.location.hostname)) {
  window.API_BASE = "https://institute-app-api.onrender.com";
}
