const STATE_KEY = "raterhubTrackerState_v2";
const STATUS_KEY = "raterhubLastStatus_v1";

async function loadPopupData() {
  const authStatusEl = document.getElementById("auth-status");
  const lastStatusEl = document.getElementById("last-status");
  const sessionInfoEl = document.getElementById("session-info");

  const statusResp = await chrome.runtime.sendMessage({
    type: "GET_STATUS",
    includeLastStatus: true,
  });

  if (statusResp?.authenticated) {
    authStatusEl.textContent = "Logged in";
    authStatusEl.style.color = "#15803d";
  } else {
    authStatusEl.textContent = "Not logged in";
    authStatusEl.style.color = "#b91c1c";
  }

  if (statusResp?.lastStatus) {
    lastStatusEl.textContent = statusResp.lastStatus;
  } else {
    lastStatusEl.textContent = "No recent activity";
  }

  const stored = await chrome.storage.local.get([STATE_KEY, STATUS_KEY]);
  const state = stored[STATE_KEY];

  if (!state) {
    sessionInfoEl.textContent = "No active session in this browser.";
    sessionInfoEl.style.color = "#6b7280";
    return;
  }

  const questionText = typeof state.questionIndex === "number" && state.questionIndex > 0
    ? `Question: ${state.questionIndex}`
    : "Question: –";

  const collapsed = state.isCollapsed ? "Widget collapsed" : "Widget expanded";
  sessionInfoEl.textContent = `${questionText} • ${collapsed}`;
}

document.addEventListener("DOMContentLoaded", loadPopupData);
