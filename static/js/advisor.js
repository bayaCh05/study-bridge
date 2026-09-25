const accessDenied = document.getElementById("access-denied");
const app = document.getElementById("app");
const tbody = document.getElementById("requests-tbody");

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
  await loadRequests();
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

document.getElementById("logout-button").addEventListener("click", async () => {
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/login";
});

init();
