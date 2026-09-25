const accessDenied = document.getElementById("access-denied");
const app = document.getElementById("app");
const tbody = document.getElementById("requests-tbody");
const letterStudentSelect = document.getElementById("letter-student-id");
const letterForm = document.getElementById("letter-form");
const letterError = document.getElementById("letter-error");
const letterSaveButton = document.getElementById("letter-save-button");
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
  if (!response.ok || me.role !== "advisor") {
    accessDenied.hidden = false;
    return;
  }
  app.hidden = false;
  await Promise.all([loadRequests(), loadStudentsForLetters(), loadLetters()]);
}

async function loadRequests() {
  const response = await fetch("/api/office-hours");
  const data = await response.json();
  tbody.textContent = "";
  for (const request of data.requests) {
    tbody.appendChild(renderRow(request));
  }
}

function renderRow(request) {
  const row = document.createElement("tr");

  const studentCell = document.createElement("td");
  studentCell.textContent = request.student_name;
  row.appendChild(studentCell);

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

  const actionsCell = document.createElement("td");
  if (request.status === "pending") {
    const acceptButton = document.createElement("button");
    acceptButton.type = "button";
    acceptButton.textContent = "Accept";
    acceptButton.addEventListener("click", () => respond(request.id, "accept"));
    actionsCell.appendChild(acceptButton);

    const rejectButton = document.createElement("button");
    rejectButton.type = "button";
    rejectButton.textContent = "Reject";
    rejectButton.addEventListener("click", () => respond(request.id, "reject"));
    actionsCell.appendChild(rejectButton);
  }
  row.appendChild(actionsCell);

  return row;
}

async function respond(requestId, action) {
  const comment = prompt("Optional comment:") || "";
  const response = await fetch(`/api/office-hours/${requestId}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ comment }),
  });
  if (!response.ok) {
    const data = await response.json();
    alert(data.error || "Could not update this request");
    return;
  }
  await loadRequests();
}

async function loadStudentsForLetters() {
  const response = await fetch("/api/students");
  const data = await response.json();
  letterStudentSelect.textContent = "";
  for (const student of data.students) {
    const option = document.createElement("option");
    option.value = student.id;
    option.textContent = `${student.full_name} (${student.email})`;
    letterStudentSelect.appendChild(option);
  }
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      resolve(result.substring(result.indexOf(",") + 1));
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

letterForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  letterError.hidden = true;
  letterSaveButton.disabled = true;

  const fileInput = document.getElementById("letter-file");
  const file = fileInput.files[0];

  try {
    if (!file) {
      letterError.textContent = "Please choose a PDF file";
      letterError.hidden = false;
      return;
    }

    const contentBase64 = await readFileAsBase64(file);
    const response = await fetch("/api/letters", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        student_id: letterStudentSelect.value,
        title: document.getElementById("letter-title").value,
        filename: file.name,
        content_base64: contentBase64,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      letterError.textContent = data.error || "Could not upload this letter";
      letterError.hidden = false;
      return;
    }
    letterForm.reset();
    await loadLetters();
  } catch (err) {
    letterError.textContent = "Server unreachable — check your network or try again later";
    letterError.hidden = false;
  } finally {
    letterSaveButton.disabled = false;
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

  const studentCell = document.createElement("td");
  studentCell.textContent = letter.student_name;
  row.appendChild(studentCell);

  const titleCell = document.createElement("td");
  titleCell.textContent = letter.title;
  row.appendChild(titleCell);

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
