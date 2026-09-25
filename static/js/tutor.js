const accessDenied = document.getElementById("access-denied");
const app = document.getElementById("app");
const tbody = document.getElementById("slots-tbody");
const form = document.getElementById("slot-form");
const formError = document.getElementById("form-error");
const saveButton = document.getElementById("save-button");

function formatDateTime(iso) {
  return new Date(iso).toLocaleString();
}

async function init() {
  const response = await fetch("/api/me");
  if (response.status === 401) {
    window.location.href = "/login";
    return;
  }
  const me = await response.json();
  if (!response.ok || me.role !== "tutor") {
    accessDenied.hidden = false;
    return;
  }
  app.hidden = false;
  await loadSlots();
}

async function loadSlots() {
  const response = await fetch("/api/availability");
  const data = await response.json();
  tbody.textContent = "";
  for (const slot of data.slots) {
    tbody.appendChild(renderRow(slot));
  }
}

function renderRow(slot) {
  const row = document.createElement("tr");

  const startCell = document.createElement("td");
  startCell.textContent = formatDateTime(slot.start_at);
  row.appendChild(startCell);

  const endCell = document.createElement("td");
  endCell.textContent = formatDateTime(slot.end_at);
  row.appendChild(endCell);

  const actionsCell = document.createElement("td");
  const deleteButton = document.createElement("button");
  deleteButton.type = "button";
  deleteButton.textContent = "Delete";
  deleteButton.addEventListener("click", () => deleteSlot(slot));
  actionsCell.appendChild(deleteButton);
  row.appendChild(actionsCell);

  return row;
}

async function deleteSlot(slot) {
  if (!confirm("Delete this slot?")) return;
  const response = await fetch(`/api/availability/${slot.id}`, { method: "DELETE" });
  if (!response.ok) {
    const data = await response.json();
    alert(data.error || "Could not delete this slot");
    return;
  }
  await loadSlots();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.hidden = true;
  saveButton.disabled = true;

  const payload = {
    start_at: document.getElementById("start_at").value,
    end_at: document.getElementById("end_at").value,
  };

  try {
    const response = await fetch("/api/availability", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      formError.textContent = data.error || "Could not add this slot";
      formError.hidden = false;
      return;
    }
    form.reset();
    await loadSlots();
  } catch (err) {
    formError.textContent = "Server unreachable — check your network or try again later";
    formError.hidden = false;
  } finally {
    saveButton.disabled = false;
  }
});

document.getElementById("logout-button").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

init();
