const accessDenied = document.getElementById("access-denied");
const app = document.getElementById("app");
const tbody = document.getElementById("slots-tbody");
const form = document.getElementById("slot-form");
const formError = document.getElementById("form-error");
const saveButton = document.getElementById("save-button");
const bookingsTbody = document.getElementById("bookings-tbody");

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
  await Promise.all([loadSlots(), loadBookings()]);
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

async function loadBookings() {
  const response = await fetch("/api/bookings");
  const data = await response.json();
  bookingsTbody.textContent = "";
  for (const booking of data.bookings) {
    bookingsTbody.appendChild(renderBookingRow(booking));
  }
}

function renderBookingRow(booking) {
  const row = document.createElement("tr");

  const studentCell = document.createElement("td");
  studentCell.textContent = booking.student_name;
  row.appendChild(studentCell);

  const subjectCell = document.createElement("td");
  subjectCell.textContent = booking.subject;
  row.appendChild(subjectCell);

  const whenCell = document.createElement("td");
  whenCell.textContent = `${formatDateTime(booking.start_at)} - ${formatDateTime(booking.end_at)}`;
  row.appendChild(whenCell);

  const statusCell = document.createElement("td");
  statusCell.textContent = booking.status;
  row.appendChild(statusCell);

  const reportCell = document.createElement("td");
  if (booking.report) {
    reportCell.textContent = `${booking.report.attended ? "Attended" : "No-show"} — ${booking.report.notes}`;
  }
  row.appendChild(reportCell);

  const actionsCell = document.createElement("td");
  if (booking.status === "pending") {
    actionsCell.appendChild(makeBookingActionButton("Accept", () => respondToBooking(booking.id, "accept")));
    actionsCell.appendChild(makeBookingActionButton("Decline", () => respondToBooking(booking.id, "decline")));
  } else if (booking.status === "confirmed") {
    actionsCell.appendChild(
      makeBookingActionButton("Cancel", () => respondToBooking(booking.id, "cancel"), "Cancel this booking?")
    );
    if (new Date(booking.end_at) <= new Date()) {
      actionsCell.appendChild(makeBookingActionButton("Complete", () => completeBooking(booking.id)));
    }
  }
  row.appendChild(actionsCell);

  return row;
}

function makeBookingActionButton(label, onClick, confirmMessage) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", () => {
    if (confirmMessage && !confirm(confirmMessage)) return;
    onClick();
  });
  return button;
}

async function respondToBooking(bookingId, action) {
  const response = await fetch(`/api/bookings/${bookingId}/${action}`, { method: "POST" });
  if (!response.ok) {
    const data = await response.json();
    alert(data.error || "Could not update this booking");
    return;
  }
  await Promise.all([loadSlots(), loadBookings()]);
}

async function completeBooking(bookingId) {
  const attended = confirm("Did the student attend? OK = yes, Cancel = no");
  const notes = prompt("Session notes:");
  if (notes === null || notes.trim() === "") return;

  const response = await fetch(`/api/bookings/${bookingId}/complete`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ attended, notes: notes.trim() }),
  });
  if (!response.ok) {
    const data = await response.json();
    alert(data.error || "Could not complete this booking");
    return;
  }
  await Promise.all([loadSlots(), loadBookings()]);
}

document.getElementById("logout-button").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

init();
