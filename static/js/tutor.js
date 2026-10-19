const accessDenied = document.getElementById("access-denied");
const app = document.getElementById("app");
const tbody = document.getElementById("slots-tbody");
const form = document.getElementById("slot-form");
const formError = document.getElementById("form-error");
const saveButton = document.getElementById("save-button");
const bookingsTbody = document.getElementById("bookings-tbody");
const slotsCount = document.getElementById("slots-count");
const bookingsCount = document.getElementById("bookings-count");

function formatDateTime(iso) {
  return new Date(iso).toLocaleString();
}

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
  if (me.role !== "tutor") {
    accessDenied.hidden = false;
    return;
  }
  app.hidden = false;
  await Promise.all([loadSlots(), loadBookings()]);
}

async function loadSlots() {
  const data = await apiFetch("/api/availability");
  tbody.textContent = "";
  slotsCount.textContent = `${data.slots.length} upcoming slot(s)`;
  if (data.slots.length === 0) {
    tbody.appendChild(emptyRow(3, "No upcoming slots yet."));
    return;
  }
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
  try {
    await apiFetch(`/api/availability/${slot.id}`, { method: "DELETE" });
    await loadSlots();
    showToast("Slot deleted");
  } catch (err) {
    showToast(err.message, true);
  }
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
    await apiFetch("/api/availability", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    await loadSlots();
    showToast("Slot added");
  } catch (err) {
    formError.textContent = err.message;
    formError.hidden = false;
  } finally {
    saveButton.disabled = false;
  }
});

async function loadBookings() {
  const data = await apiFetch("/api/bookings");
  bookingsTbody.textContent = "";
  bookingsCount.textContent = `${data.bookings.length} booking(s)`;
  if (data.bookings.length === 0) {
    bookingsTbody.appendChild(emptyRow(6, "No bookings yet."));
    return;
  }
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

const BOOKING_ACTION_TOAST = { accept: "Booking accepted", decline: "Booking declined", cancel: "Booking cancelled" };

async function respondToBooking(bookingId, action) {
  try {
    await apiFetch(`/api/bookings/${bookingId}/${action}`, { method: "POST" });
    await Promise.all([loadSlots(), loadBookings()]);
    showToast(BOOKING_ACTION_TOAST[action] || "Booking updated");
  } catch (err) {
    showToast(err.message, true);
  }
}

async function completeBooking(bookingId) {
  const attended = confirm("Did the student attend? OK = yes, Cancel = no");
  const notes = prompt("Session notes:");
  if (notes === null || notes.trim() === "") return;

  try {
    await apiFetch(`/api/bookings/${bookingId}/complete`, {
      method: "POST",
      body: JSON.stringify({ attended, notes: notes.trim() }),
    });
    await Promise.all([loadSlots(), loadBookings()]);
    showToast("Session report saved");
  } catch (err) {
    showToast(err.message, true);
  }
}

document.getElementById("logout-button").addEventListener("click", async () => {
  try {
    await apiFetch("/api/logout", { method: "POST" });
  } catch (err) {
    // Best-effort: send the user back to login regardless.
  }
  window.location.href = "/login";
});

init();
