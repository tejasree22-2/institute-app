document.addEventListener("DOMContentLoaded", () => {
  if (isLoggedIn() && currentUser()) {
    window.location.href = currentUser().role === "instructor" ? "instructor/library.html" : "student/dashboard.html";
    return;
  }

  const form = document.getElementById("signup-form");
  const errorBox = document.getElementById("signup-error");
  const showError = (msg) => {
    errorBox.textContent = msg;
    errorBox.style.display = "block";
  };

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    errorBox.style.display = "none";
    const name = document.getElementById("name").value.trim();
    const email = document.getElementById("email").value.trim();
    const password = document.getElementById("password").value;
    if (password !== document.getElementById("password2").value) {
      showError("The passwords don't match");
      return;
    }
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Creating account…";

    try {
      await api("/auth/signup", { method: "POST", body: { name, email, password }, auth: false });
      // no automatic login: the login page confirms the account and asks them to log in
      window.location.href = `index.html?signed_up=${encodeURIComponent(email)}`;
    } catch (err) {
      showError(err.message || "Sign-up failed");
      submitBtn.disabled = false;
      submitBtn.textContent = "Create account";
    }
  });
});
