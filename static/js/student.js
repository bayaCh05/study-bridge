const accessDenied = document.getElementById("access-denied");
const app = document.getElementById("app");
const tutorsList = document.getElementById("tutors-list");
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
  if (!response.ok || me.role !== "student") {
    accessDenied.hidden = false;
    return;
  }
  app.hidden = false;
  await Promise.all([loadTutors(), loadBookings()]);
}

async function loadTutors() {
  const response = await fetch("/api/tutors");
  const data = await response.json();
  tutorsList.textContent = "";

  for (const tutor of data.tutors) {
    const card = document.createElement("div");

    const heading = document.createElement("h3");
    heading.textContent = `${tutor.full_name} (${tutor.email})`;
    card.appendChild(heading);

    if (tutor.slots.length === 0) {
      const empty = document.createElement("p");
      empty.textContent = "No free slots.";
      card.appendChild(empty);
    } else {
      const list = document.createElement("ul");
      for (const slot of tutor.slots) {
        list.appendChild(renderSlotItem(slot));
      }
      card.appendChild(list);
    }

    tutorsList.appendChild(card);
  }
}

function renderSlotItem(slot) {
  const item = document.createElement("li");

  const label = document.createElement("span");
  label.textContent = `${formatDateTime(slot.start_at)} - ${formatDateTime(slot.end_at)} `;
  item.appendChild(label);

  const subjectInput = document.createElement("input");
  subjectInput.type = "text";
  subjectInput.placeholder = "Subject";
  item.appendChild(subjectInput);

  const bookButton = document.createElement("button");
  bookButton.type = "button";
  bookButton.textContent = "Book";
  bookButton.addEventListener("click", () => bookSlot(slot.id, subjectInput));
  item.appendChild(bookButton);

  return item;
}

async function bookSlot(availabilityId, subjectInput) {
  const subject = subjectInput.value.trim();
  if (!subject) {
    alert("Please enter a subject");
    return;
  }
  const response = await fetch("/api/bookings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ availability_id: availabilityId, subject }),
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || "Could not book this slot");
    return;
  }
  await Promise.all([loadTutors(), loadBookings()]);
}

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

  const tutorCell = document.createElement("td");
  tutorCell.textContent = booking.tutor_name;
  row.appendChild(tutorCell);

  const subjectCell = document.createElement("td");
  subjectCell.textContent = booking.subject;
  row.appendChild(subjectCell);

  const whenCell = document.createElement("td");
  whenCell.textContent = `${formatDateTime(booking.start_at)} - ${formatDateTime(booking.end_at)}`;
  row.appendChild(whenCell);

  const statusCell = document.createElement("td");
  statusCell.textContent = booking.status;
  row.appendChild(statusCell);

  const actionsCell = document.createElement("td");
  if (booking.status === "pending" || booking.status === "confirmed") {
    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.textContent = "Cancel";
    cancelButton.addEventListener("click", () => cancelBooking(booking.id));
    actionsCell.appendChild(cancelButton);
  }
  row.appendChild(actionsCell);

  return row;
}

async function cancelBooking(bookingId) {
  if (!confirm("Cancel this booking?")) return;
  const response = await fetch(`/api/bookings/${bookingId}/cancel`, { method: "POST" });
  if (!response.ok) {
    const data = await response.json();
    alert(data.error || "Could not cancel this booking");
    return;
  }
  await Promise.all([loadTutors(), loadBookings()]);
}

document.getElementById("logout-button").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

init();
