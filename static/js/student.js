const accessDenied = document.getElementById("access-denied");
const app = document.getElementById("app");
const tutorsList = document.getElementById("tutors-list");
const bookingsTbody = document.getElementById("bookings-tbody");
const advisorSelect = document.getElementById("advisor-id");
const officeHoursForm = document.getElementById("office-hours-form");
const officeHoursError = document.getElementById("office-hours-error");
const officeHoursSaveButton = document.getElementById("office-hours-save-button");
const officeHoursTbody = document.getElementById("office-hours-tbody");
const lettersTbody = document.getElementById("letters-tbody");

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
  await Promise.all([loadTutors(), loadBookings(), loadAdvisors(), loadOfficeHourRequests(), loadLetters()]);
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

  const reportCell = document.createElement("td");
  if (booking.report) {
    reportCell.textContent = `${booking.report.attended ? "Attended" : "No-show"} — ${booking.report.notes}`;
  }
  row.appendChild(reportCell);

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

async function loadAdvisors() {
  const response = await fetch("/api/advisors");
  const data = await response.json();
  advisorSelect.textContent = "";
  for (const advisor of data.advisors) {
    const option = document.createElement("option");
    option.value = advisor.id;
    option.textContent = `${advisor.full_name} (${advisor.email})`;
    advisorSelect.appendChild(option);
  }
}

async function loadOfficeHourRequests() {
  const response = await fetch("/api/office-hours");
  const data = await response.json();
  officeHoursTbody.textContent = "";
  for (const request of data.requests) {
    officeHoursTbody.appendChild(renderOfficeHourRow(request));
  }
}

function renderOfficeHourRow(request) {
  const row = document.createElement("tr");

  const advisorCell = document.createElement("td");
  advisorCell.textContent = request.advisor_name;
  row.appendChild(advisorCell);

  const whenCell = document.createElement("td");
  whenCell.textContent = formatDateTime(request.requested_at);
  row.appendChild(whenCell);

  const reasonCell = document.createElement("td");
  reasonCell.textContent = request.reason;
  row.appendChild(reasonCell);

  const statusCell = document.createElement("td");
  statusCell.textContent = request.status;
  row.appendChild(statusCell);

  const commentCell = document.createElement("td");
  commentCell.textContent = request.advisor_comment || "";
  row.appendChild(commentCell);

  return row;
}

officeHoursForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  officeHoursError.hidden = true;
  officeHoursSaveButton.disabled = true;

  const payload = {
    advisor_id: advisorSelect.value,
    requested_at: document.getElementById("requested_at").value,
    reason: document.getElementById("reason").value,
  };

  try {
    const response = await fetch("/api/office-hours", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      officeHoursError.textContent = data.error || "Could not send this request";
      officeHoursError.hidden = false;
      return;
    }
    officeHoursForm.reset();
    await loadOfficeHourRequests();
  } catch (err) {
    officeHoursError.textContent = "Server unreachable — check your network or try again later";
    officeHoursError.hidden = false;
  } finally {
    officeHoursSaveButton.disabled = false;
  }
});

async function loadLetters() {
  const response = await fetch("/api/letters");
  const data = await response.json();
  lettersTbody.textContent = "";
  for (const letter of data.letters) {
    lettersTbody.appendChild(renderLetterRow(letter));
  }
}

function renderLetterRow(letter) {
  const row = document.createElement("tr");

  const titleCell = document.createElement("td");
  titleCell.textContent = letter.title;
  row.appendChild(titleCell);

  const fromCell = document.createElement("td");
  fromCell.textContent = letter.advisor_name;
  row.appendChild(fromCell);

  const uploadedCell = document.createElement("td");
  uploadedCell.textContent = formatDateTime(letter.uploaded_at);
  row.appendChild(uploadedCell);

  const downloadCell = document.createElement("td");
  const downloadLink = document.createElement("a");
  downloadLink.href = `/api/letters/${letter.id}/download`;
  downloadLink.textContent = "Download";
  downloadCell.appendChild(downloadLink);
  row.appendChild(downloadCell);

  return row;
}

document.getElementById("logout-button").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

init();
