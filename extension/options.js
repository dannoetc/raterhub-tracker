// ============================================================
// DOM lookups and state helpers
// ============================================================

const statusEl = document.getElementById("status");
const modeRadios = document.querySelectorAll('input[name="auth-mode"]');
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const tokenInput = document.getElementById("api-token");
const refreshInput = document.getElementById("refresh-token");
const passwordFields = document.getElementById("password-fields");
const tokenField = document.getElementById("token-field");
const refreshField = document.getElementById("refresh-field");

function showStatus(text, tone = "info") {
  if (!statusEl) return;
  statusEl.style.display = "block";
  statusEl.textContent = text;
  statusEl.style.background = tone === "error" ? "#fee2e2" : tone === "success" ? "#dcfce7" : "#eef2ff";
  statusEl.style.color = tone === "error" ? "#991b1b" : tone === "success" ? "#166534" : "#312e81";
}

// ============================================================
// Form mode toggles and prefill
// ============================================================

function currentMode() {
  const checked = Array.from(modeRadios).find((r) => r.checked);
  return checked ? checked.value : "password";
}

function toggleFieldVisibility() {
  const mode = currentMode();
  passwordFields.style.display = mode === "password" ? "grid" : "none";
  tokenField.style.display = mode === "token" ? "grid" : "none";
  refreshField.style.display = mode === "refresh" ? "grid" : "none";
}

async function loadExistingConfig() {
  try {
    const res = await chrome.runtime.sendMessage({ type: "GET_AUTH_CONFIG" });
    if (!res?.ok) return;
    if (res.config?.mode === "token") {
      modeRadios.forEach((r) => (r.checked = r.value === "token"));
      tokenInput.value = res.config.apiToken || "";
    } else if (res.config?.mode === "refresh") {
      modeRadios.forEach((r) => (r.checked = r.value === "refresh"));
      refreshInput.value = res.config.refreshToken || "";
    } else if (res.config) {
      modeRadios.forEach((r) => (r.checked = r.value === "password"));
      emailInput.value = res.config.email || "";
      passwordInput.value = res.config.password || "";
    }
    toggleFieldVisibility();
  } catch (err) {
    console.warn("[Options] Failed to load config", err);
  }
}

// ============================================================
// Save and credential lifecycle actions
// ============================================================

async function save() {
  const mode = currentMode();
  if (mode === "password") {
    if (!emailInput.value || !passwordInput.value) {
      showStatus("Email and password are required", "error");
      return;
    }
  }
  if (mode === "token" && !tokenInput.value) {
    showStatus("Personal token is required", "error");
    return;
  }
  if (mode === "refresh" && !refreshInput.value) {
    showStatus("Refresh token is required", "error");
    return;
  }

  const config = { mode };
  if (mode === "password") {
    config.email = emailInput.value.trim();
    config.password = passwordInput.value;
  } else if (mode === "token") {
    config.apiToken = tokenInput.value.trim();
  } else if (mode === "refresh") {
    config.refreshToken = refreshInput.value.trim();
  }

  const res = await chrome.runtime.sendMessage({ type: "SAVE_AUTH_CONFIG", config });
  if (res?.ok) {
    showStatus("Saved. Background worker will use the new credentials.", "success");
  } else {
    showStatus("Failed to save credentials", "error");
  }
}

async function requestRefreshToken() {
  showStatus("Requesting refresh token…");
  const res = await chrome.runtime.sendMessage({ type: "REQUEST_REFRESH_TOKEN" });
  if (res?.ok && res.refreshToken) {
    modeRadios.forEach((r) => (r.checked = r.value === "refresh"));
    refreshInput.value = res.refreshToken;
    toggleFieldVisibility();
    showStatus("New refresh token saved.", "success");
  } else if (res?.error === "NO_CREDENTIALS") {
    showStatus("Provide email/password or token first.", "error");
  } else {
    showStatus("Unable to request refresh token.", "error");
  }
}

async function triggerLogin() {
  showStatus("Signing in…");
  const res = await chrome.runtime.sendMessage({ type: "LOGIN" });
  if (res?.ok) {
    showStatus("Logged in.", "success");
  } else if (res?.error === "NO_CREDENTIALS") {
    showStatus("Provide credentials first.", "error");
  } else {
    showStatus("Login failed.", "error");
  }
}

async function logout() {
  showStatus("Clearing stored data…");
  await chrome.runtime.sendMessage({ type: "LOGOUT_RESET" });
  emailInput.value = "";
  passwordInput.value = "";
  tokenInput.value = "";
  refreshInput.value = "";
  modeRadios.forEach((r) => (r.checked = r.value === "password"));
  toggleFieldVisibility();
  showStatus("Credentials and tokens cleared.", "success");
}

async function clearWidgetPosition() {
  showStatus("Resetting widget position…");
  const res = await chrome.runtime.sendMessage({ type: "RESET_WIDGET_POSITION" });
  if (res?.ok) {
    showStatus("Widget position cleared. It will return to default on next load.", "success");
  } else {
    showStatus("Unable to reset widget position.", "error");
  }
}

// ============================================================
// Wire up UI events
// ============================================================

modeRadios.forEach((radio) => radio.addEventListener("change", toggleFieldVisibility));
document.getElementById("save").addEventListener("click", save);
document.getElementById("request-refresh").addEventListener("click", requestRefreshToken);
document.getElementById("login").addEventListener("click", triggerLogin);
document.getElementById("logout").addEventListener("click", logout);
document.getElementById("reset-position").addEventListener("click", clearWidgetPosition);

document.addEventListener("DOMContentLoaded", () => {
  toggleFieldVisibility();
  loadExistingConfig();
});
