/**
 * Shared fetch wrapper used by every page: timeout, one automatic retry for
 * GET requests, normalized error messages, and an offline/server-down
 * banner that polls /health while the server is unreachable.
 */

const API_TIMEOUT_MS = 8000;
const HEALTH_POLL_MS = 10000;

class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status || null;
    this.data = data || {};
  }
}

function withTimeout(path, options) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  return fetch(path, { ...options, signal: controller.signal }).finally(() => clearTimeout(timeoutId));
}

/**
 * Call a JSON API endpoint. Resolves with the parsed JSON body on 2xx;
 * throws ApiError (with .status and .data) on any 4xx/5xx or network
 * failure. GET requests get one automatic retry on a network error, a
 * timeout, or a 5xx response, since GETs are safe to repeat.
 */
async function apiFetch(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const isGet = method === "GET";
  const headers = { ...(options.headers || {}) };
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const fetchOptions = { ...options, method, headers };

  let response = await attemptWithOneRetry(path, fetchOptions, isGet);

  let data = {};
  try {
    data = await response.json();
  } catch (err) {
    data = {};
  }

  if (response.status >= 500) {
    throw new ApiError(data.error || "Server error, please try again", response.status, data);
  }
  if (!response.ok) {
    throw new ApiError(data.error || "Request failed", response.status, data);
  }

  return data;
}

async function attemptWithOneRetry(path, fetchOptions, isGet) {
  let response;
  try {
    response = await withTimeout(path, fetchOptions);
  } catch (err) {
    if (!isGet) {
      throw new ApiError("Server unreachable — check your network or try again later");
    }
    try {
      return await withTimeout(path, fetchOptions);
    } catch (err2) {
      throw new ApiError("Server unreachable — check your network or try again later");
    }
  }

  if (isGet && response.status >= 500) {
    try {
      const retryResponse = await withTimeout(path, fetchOptions);
      return retryResponse;
    } catch (err) {
      return response;
    }
  }

  return response;
}

// --- Offline / server-down banner, shared across every page --------------

let healthPollTimer = null;

function getOrCreateBanner() {
  let banner = document.getElementById("offline-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "offline-banner";
    banner.textContent = "Server unreachable — check your network or try again later";
    banner.hidden = true;
    document.body.prepend(banner);
  }
  return banner;
}

function showOfflineBanner() {
  getOrCreateBanner().hidden = false;
  if (healthPollTimer === null) {
    healthPollTimer = setInterval(checkHealth, HEALTH_POLL_MS);
  }
}

function hideOfflineBanner() {
  const banner = document.getElementById("offline-banner");
  if (banner) banner.hidden = true;
  if (healthPollTimer !== null) {
    clearInterval(healthPollTimer);
    healthPollTimer = null;
  }
}

async function checkHealth() {
  try {
    const response = await fetch("/health", { cache: "no-store" });
    if (response.ok) {
      hideOfflineBanner();
    } else {
      showOfflineBanner();
    }
  } catch (err) {
    showOfflineBanner();
  }
}

window.addEventListener("offline", showOfflineBanner);
window.addEventListener("online", checkHealth);
checkHealth();
