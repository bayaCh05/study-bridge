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
    const data = await apiFetch("/api/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    window.location.href = ROLE_PAGES[data.role] || "/";
  } catch (err) {
    errorBox.textContent = err.message;
    errorBox.hidden = false;
  } finally {
    submitButton.disabled = false;
  }
});
