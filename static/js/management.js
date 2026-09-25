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
  let me;
  try {
    me = await apiFetch("/api/me");
  } catch (err) {
    if (err.status === 401) {
      window.location.href = "/login";
    } else {
      accessDenied.hidden = false;
    }
    return;
  }
  if (me.role !== "management") {
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
  const data = await apiFetch(`/api/users${buildQuery()}`);
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
    if (state.editingId) {
      await apiFetch(`/api/users/${state.editingId}`, { method: "PUT", body: JSON.stringify(payload) });
    } else {
      payload.password = passwordInput.value;
      await apiFetch("/api/users", { method: "POST", body: JSON.stringify(payload) });
    }
    resetForm();
    await loadUsers();
  } catch (err) {
    formError.textContent = err.message;
    formError.hidden = false;
  } finally {
    saveButton.disabled = false;
  }
});

async function toggleActive(user) {
  const action = user.is_active ? "deactivate" : "reactivate";
  try {
    await apiFetch(`/api/users/${user.id}/${action}`, { method: "POST" });
    await loadUsers();
  } catch (err) {
    alert(err.message);
  }
}

async function deleteUser(user) {
  if (!confirm(`Delete ${user.full_name}? This cannot be undone.`)) return;
  try {
    await apiFetch(`/api/users/${user.id}`, { method: "DELETE" });
    await loadUsers();
  } catch (err) {
    alert(err.message);
  }
}

document.getElementById("logout-button").addEventListener("click", async () => {
  try {
    await apiFetch("/api/logout", { method: "POST" });
  } catch (err) {
    // Logging out best-effort even if the request failed — always send
    // the user back to the login page.
  }
  window.location.href = "/login";
});

init();
