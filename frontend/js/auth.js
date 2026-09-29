document.addEventListener("DOMContentLoaded", () => {
  if (isLoggedIn()) {
    const user = currentUser();
    if (user) {
      window.location.href = user.role === "instructor" ? "instructor/library.html" : "student/dashboard.html";
      return;
    }
  }

  if (["localhost", "127.0.0.1"].includes(window.location.hostname)) {
    document.getElementById("demo-hint").hidden = false;
  }

  const form = document.getElementById("login-form");
  const errorBox = document.getElementById("login-error");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.style.display = "none";
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Logging in…";

    try {
      const data = await api("/auth/login", { method: "POST", body: { email, password }, auth: false });
      if (!data || !data.token) {
        // an empty reply means the request didn't reach the backend (API_BASE in js/config.js)
        throw new Error("Can't reach the server — check the API address in js/config.js");
      }
      localStorage.setItem("token", data.token);
      localStorage.setItem("user", JSON.stringify(data.user));
      window.location.href = data.user.role === "instructor" ? "instructor/library.html" : "student/dashboard.html";
    } catch (err) {
      errorBox.textContent = err.message || "Login failed";
      errorBox.style.display = "block";
      submitBtn.disabled = false;
      submitBtn.textContent = "Log in";
    }
  });
});
