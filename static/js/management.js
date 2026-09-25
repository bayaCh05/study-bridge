const state = { editingId: null };

const accessDenied = document.getElementById("access-denied");
const app = document.getElementById("app");
const tbody = document.getElementById("users-tbody");
const form = document.getElementById("user-form");
const formTitle = document.getElementById("form-title");
const formError = document.getElementById("form-error");
const saveButton = document.getElementById("save-button");
const cancelEditButton = document.getElementById("cancel-edit");
const passwordLabel = document.getElementById("password-label");
const passwordInput = document.getElementById("password");

async function init() {
  const response = await fetch("/api/me");
  if (response.status === 401) {
    window.location.href = "/login";
    return;
  }
  const me = await response.json();
  if (!response.ok || me.role !== "management") {
    accessDenied.hidden = false;
    return;
  }
  app.hidden = false;
  await loadUsers();
}

function buildQuery() {
  const role = document.getElementById("filter-role").value;
  const search = document.getElementById("filter-search").value;
  const params = new URLSearchParams();
  if (role) params.set("role", role);
  if (search) params.set("search", search);
  const query = params.toString();
  return query ? `?${query}` : "";
}

async function loadUsers() {
  const response = await fetch(`/api/users${buildQuery()}`);
  const data = await response.json();
  tbody.textContent = "";
  for (const user of data.users) {
    tbody.appendChild(renderRow(user));
  }
}

function renderRow(user) {
  const row = document.createElement("tr");

  const nameCell = document.createElement("td");
  nameCell.textContent = user.full_name;
  row.appendChild(nameCell);

  const emailCell = document.createElement("td");
  emailCell.textContent = user.email;
  row.appendChild(emailCell);

  const roleCell = document.createElement("td");
  roleCell.textContent = user.role;
  row.appendChild(roleCell);

  const statusCell = document.createElement("td");
  statusCell.textContent = user.is_active ? "active" : "inactive";
  row.appendChild(statusCell);

  const actionsCell = document.createElement("td");

  const editButton = document.createElement("button");
  editButton.type = "button";
  editButton.textContent = "Edit";
  editButton.addEventListener("click", () => startEdit(user));
  actionsCell.appendChild(editButton);

  const toggleButton = document.createElement("button");
  toggleButton.type = "button";
  toggleButton.textContent = user.is_active ? "Deactivate" : "Reactivate";
  toggleButton.addEventListener("click", () => toggleActive(user));
  actionsCell.appendChild(toggleButton);

  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.textContent = "Delete";
  deleteButton.addEventListener("click", () => deleteUser(user));
  actionsCell.appendChild(deleteButton);

  row.appendChild(actionsCell);
  return row;
}

function startEdit(user) {
  state.editingId = user.id;
  document.getElementById("user-id").value = user.id;
  document.getElementById("full_name").value = user.full_name;
  document.getElementById("email").value = user.email;
  document.getElementById("role").value = user.role;
  passwordInput.value = "";
  passwordLabel.hidden = true;
  formTitle.textContent = `Edit ${user.full_name}`;
  saveButton.textContent = "Save";
  cancelEditButton.hidden = false;
}

function resetForm() {
  state.editingId = null;
  form.reset();
  passwordLabel.hidden = false;
  formTitle.textContent = "Add a user";
  saveButton.textContent = "Create";
  cancelEditButton.hidden = true;
}

cancelEditButton.addEventListener("click", resetForm);

document.getElementById("filter-form").addEventListener("submit", (event) => {
  event.preventDefault();
  loadUsers();
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.hidden = true;
  saveButton.disabled = true;

  const payload = {
    full_name: document.getElementById("full_name").value,
    email: document.getElementById("email").value,
    role: document.getElementById("role").value,
  };

  try {
    let response;
    if (state.editingId) {
      response = await fetch(`/api/users/${state.editingId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    } else {
      payload.password = passwordInput.value;
      response = await fetch("/api/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    }
    const data = await response.json();
    if (!response.ok) {
      formError.textContent = data.error || "Could not save this user";
      formError.hidden = false;
      return;
    }
    resetForm();
    await loadUsers();
  } catch (err) {
    formError.textContent = "Server unreachable — check your network or try again later";
    formError.hidden = false;
  } finally {
    saveButton.disabled = false;
  }
});

async function toggleActive(user) {
  const action = user.is_active ? "deactivate" : "reactivate";
  const response = await fetch(`/api/users/${user.id}/${action}`, { method: "POST" });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || "Could not update this user");
    return;
  }
  await loadUsers();
}

async function deleteUser(user) {
  if (!confirm(`Delete ${user.full_name}? This cannot be undone.`)) return;
  const response = await fetch(`/api/users/${user.id}`, { method: "DELETE" });
  if (!response.ok) {
    const data = await response.json();
    alert(data.error || "Could not delete this user");
    return;
  }
  await loadUsers();
}

document.getElementById("logout-button").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

init();
