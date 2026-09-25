const ROLE_PAGES = {
  student: "/student",
  tutor: "/tutor",
  advisor: "/advisor",
  management: "/management",
};

const form = document.getElementById("login-form");
const errorBox = document.getElementById("error");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  errorBox.hidden = true;

  const email = document.getElementById("email").value;
  const password = document.getElementById("password").value;
  const submitButton = form.querySelector("button[type=submit]");
  submitButton.disabled = true;

  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await response.json();

    if (!response.ok) {
      errorBox.textContent = data.error || "Login failed";
      errorBox.hidden = false;
      return;
    }

    window.location.href = ROLE_PAGES[data.role] || "/";
  } catch (err) {
    errorBox.textContent = "Server unreachable — check your network or try again later";
    errorBox.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
});
