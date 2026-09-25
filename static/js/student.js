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
  if (me.role !== "student") {
    accessDenied.hidden = false;
    return;
  }
  app.hidden = false;
  await Promise.all([loadTutors(), loadBookings(), loadAdvisors(), loadOfficeHourRequests(), loadLetters()]);
}

async function loadTutors() {
  const data = await apiFetch("/api/tutors");
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
  try {
    await apiFetch("/api/bookings", {
      method: "POST",
      body: JSON.stringify({ availability_id: availabilityId, subject }),
    });
    await Promise.all([loadTutors(), loadBookings()]);
  } catch (err) {
    alert(err.message);
  }
}

async function loadBookings() {
  const data = await apiFetch("/api/bookings");
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
  try {
    await apiFetch(`/api/bookings/${bookingId}/cancel`, { method: "POST" });
    await Promise.all([loadTutors(), loadBookings()]);
  } catch (err) {
    alert(err.message);
  }
}

async function loadAdvisors() {
  const data = await apiFetch("/api/advisors");
  advisorSelect.textContent = "";
  for (const advisor of data.advisors) {
    const option = document.createElement("option");
    option.value = advisor.id;
    option.textContent = `${advisor.full_name} (${advisor.email})`;
    advisorSelect.appendChild(option);
  }
}

async function loadOfficeHourRequests() {
  const data = await apiFetch("/api/office-hours");
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
    await apiFetch("/api/office-hours", { method: "POST", body: JSON.stringify(payload) });
    officeHoursForm.reset();
    await loadOfficeHourRequests();
  } catch (err) {
    officeHoursError.textContent = err.message;
    officeHoursError.hidden = false;
  } finally {
    officeHoursSaveButton.disabled = false;
  }
});

async function loadLetters() {
  const data = await apiFetch("/api/letters");
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
  try {
    await apiFetch("/api/logout", { method: "POST" });
  } catch (err) {
    // Best-effort: send the user back to login regardless.
  }
  window.location.href = "/login";
});

init();
