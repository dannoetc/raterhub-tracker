// ============================================================
// Constants and in-memory state
// ============================================================

const API_BASE = "https://api.raterhub.steigenga.com";
const AUTH_KEY = "raterhubAuth_v1";
const STATUS_KEY = "raterhubLastStatus_v1";
const CREDENTIALS_KEY = "raterhubCredentials_v1";
const CRYPTO_KEY = "raterhubCredentialsKey_v1";
const POSITION_KEY = "raterhubTrackerPos_v2";
const throttleMap = {};
let promptedForLogin = false;

const MESSAGE_TYPES = {
  CONTROL_EVENT: "SEND_EVENT",
  FIND_ACTIVE_SESSION: "FIND_ACTIVE_SESSION",
  LOGIN: "LOGIN",
  SESSION_SUMMARY: "SESSION_SUMMARY",
  RESET_WIDGET_STATE: "RESET_WIDGET_STATE",
  SESSION_SUMMARY_RELAY: "SESSION_SUMMARY_RELAY",
  RESET_WIDGET_POSITION: "RESET_WIDGET_POSITION",
};

let authState = {
  accessToken: null,
  csrfToken: null,
};

let cachedCredentials = null;

// ============================================================
// Auth state persistence (local)
// ============================================================

async function loadAuthFromStorage() {
  // Load cached access + CSRF tokens so background can resume quickly.
  try {
    const stored = await chrome.storage.local.get([AUTH_KEY]);
    if (stored && stored[AUTH_KEY]) {
      authState = { ...authState, ...stored[AUTH_KEY] };
    }
  } catch (err) {
    console.warn("[RaterHubTracker] Failed to load auth from storage", err);
  }
}

async function persistAuthState() {
  // Persist short-lived auth artifacts to avoid extra CSRF/login requests.
  try {
    await chrome.storage.local.set({ [AUTH_KEY]: authState });
  } catch (err) {
    console.warn("[RaterHubTracker] Failed to persist auth", err);
  }
}

// ============================================================
// Credential resolution and storage (sync)
// ============================================================

async function resolveLoginPayload() {
  const creds = await loadStoredCredentials();
  if (!creds) {
    return { ok: false, error: "NO_CREDENTIALS" };
  }

  if (creds.refreshToken) {
    return { ok: true, body: { refresh_token: creds.refreshToken }, mode: "refresh" };
  }

  if (creds.mode === "token" && creds.apiToken) {
    return { ok: true, body: { token: creds.apiToken }, mode: "token" };
  }

  if (creds.email && creds.password) {
    return { ok: true, body: { email: creds.email, password: creds.password }, mode: "password" };
  }

  return { ok: false, error: "NO_CREDENTIALS" };
}

async function loadStoredCredentials() {
  // Retrieve and decrypt credentials from sync storage; cache in memory.
  if (cachedCredentials) return cachedCredentials;
  try {
    const stored = await chrome.storage.sync.get([CREDENTIALS_KEY]);
    if (stored && stored[CREDENTIALS_KEY]) {
      cachedCredentials = await decryptFromStorage(stored[CREDENTIALS_KEY]);
    }
  } catch (err) {
    console.warn("[RaterHubTracker] Failed to load credentials", err);
  }
  return cachedCredentials;
}

async function persistCredentials(creds) {
  // Encrypt credentials for sync storage or clear them entirely.
  cachedCredentials = creds;
  if (!creds) {
    await chrome.storage.sync.remove([CREDENTIALS_KEY]);
    return;
  }
  const encrypted = await encryptForStorage(creds);
  await chrome.storage.sync.set({ [CREDENTIALS_KEY]: encrypted });
}

function setLastStatus(message) {
  chrome.storage.local.set({ [STATUS_KEY]: message }).catch(() => {});
}

function throttle(key, windowMs = 750) {
  // Simple per-key throttle to avoid hammering APIs from rapid UI events.
  const now = Date.now();
  const last = throttleMap[key] || 0;
  if (now - last < windowMs) {
    return { throttled: true, retryIn: windowMs - (now - last) };
  }
  throttleMap[key] = now;
  return { throttled: false };
}

async function promptInteractiveLogin(reason = "LOGIN_REQUIRED") {
  if (promptedForLogin) return;
  promptedForLogin = true;
  setLastStatus(reason === "NO_CREDENTIALS" ? "Sign in to continue" : "Login required");
  try {
    await chrome.runtime.openOptionsPage();
  } catch (err) {
    console.warn("[RaterHubTracker] Failed to open options page", err);
  }
}

function isInternalPage(sender) {
  const base = chrome.runtime.getURL("");
  return Boolean(sender?.url && sender.url.startsWith(base));
}

function buildMessage(type, payload = {}) {
  return { type, timestamp: Date.now(), ...payload };
}

// ============================================================
// Encryption helpers for stored credentials
// ============================================================

function bufferToBase64(buffer) {
  return btoa(String.fromCharCode(...new Uint8Array(buffer)));
}

function base64ToBuffer(b64) {
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
}

async function getCryptoKey() {
  const existing = await chrome.storage.local.get([CRYPTO_KEY]);
  let rawKey = existing[CRYPTO_KEY];
  if (!rawKey) {
    const keyBytes = crypto.getRandomValues(new Uint8Array(32));
    rawKey = bufferToBase64(keyBytes.buffer);
    await chrome.storage.local.set({ [CRYPTO_KEY]: rawKey });
  }

  const keyBuffer = base64ToBuffer(rawKey);
  return crypto.subtle.importKey("raw", keyBuffer, "AES-GCM", false, ["encrypt", "decrypt"]);
}

async function encryptForStorage(obj) {
  const encoder = new TextEncoder();
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await getCryptoKey();
  const data = encoder.encode(JSON.stringify(obj));
  const cipher = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, data);
  return { iv: bufferToBase64(iv.buffer), cipher: bufferToBase64(cipher) };
}

async function decryptFromStorage(record) {
  if (!record?.iv || !record?.cipher) return null;
  const key = await getCryptoKey();
  const iv = new Uint8Array(base64ToBuffer(record.iv));
  const cipher = base64ToBuffer(record.cipher);
  try {
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, cipher);
    const decoded = new TextDecoder().decode(plain);
    return JSON.parse(decoded);
  } catch (err) {
    console.warn("[RaterHubTracker] Failed to decrypt credentials", err);
    return null;
  }
}

// ============================================================
// Auth: CSRF issuance and login/token caching
// ============================================================

async function fetchCsrfToken() {
  const { throttled } = throttle("csrf", 500);
  if (throttled) {
    return { ok: false, error: "THROTTLED" };
  }

  try {
    const res = await fetch(`${API_BASE}/auth/csrf`, {
      method: "GET",
      credentials: "include",
    });

    if (!res.ok) {
      return { ok: false, status: res.status, error: "CSRF_FAILED" };
    }

    const data = await res.json();
    if (data && typeof data.csrf_token === "string") {
      authState.csrfToken = data.csrf_token;
      await persistAuthState();
      return { ok: true, csrf: authState.csrfToken };
    }
  } catch (err) {
    console.error("[RaterHubTracker] CSRF fetch error", err);
    return { ok: false, error: "NETWORK" };
  }

  return { ok: false, error: "INVALID_RESPONSE" };
}

async function login(options = {}) {
  // Perform login using stored credentials or refresh token; captures new tokens.
  const { throttled } = throttle("login", 1000);
  if (throttled) {
    return { ok: false, error: "THROTTLED" };
  }

  const payload = await resolveLoginPayload();
  if (!payload.ok) {
    return payload;
  }

  if (!authState.csrfToken) {
    const csrfRes = await fetchCsrfToken();
    if (!csrfRes.ok) {
      return csrfRes;
    }
  }

  try {
    let res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": authState.csrfToken || "",
      },
      credentials: "include",
      body: JSON.stringify(payload.body),
    });

    if (res.status === 400) {
      authState.csrfToken = null;
      await persistAuthState();
      const refreshed = await fetchCsrfToken();
      if (!refreshed.ok) {
        return refreshed;
      }

      res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": authState.csrfToken || "",
        },
        credentials: "include",
        body: JSON.stringify(payload.body),
      });
    }

    if (!res.ok) {
      const text = await res.text();
      console.warn("[RaterHubTracker] Login failed", res.status, text);
      if (!options.silent) setLastStatus(`Login failed (${res.status})`);
      return { ok: false, status: res.status, error: "LOGIN_FAILED" };
    }

    const data = (await res.json().catch(() => ({}))) || {};
    authState.accessToken = data.access_token || null;
    await persistAuthState();

    if (data.refresh_token) {
      const existing = (await loadStoredCredentials()) || {};
      await persistCredentials({ ...existing, refreshToken: data.refresh_token, mode: "refresh" });
    }

    if (!options.silent) setLastStatus("Logged in");
    return { ok: true };
  } catch (err) {
    console.error("[RaterHubTracker] Login error", err);
    if (!options.silent) setLastStatus("Login error");
    return { ok: false, error: "NETWORK" };
  }
}

async function ensureAccessToken() {
  // Guarantee an access token exists, re-running login if necessary.
  if (authState.accessToken) {
    return { ok: true };
  }
  const res = await login();
  if (!res.ok) return res;
  return authState.accessToken ? { ok: true } : { ok: false, error: "NO_TOKEN" };
}

async function logoutAndReset() {
  // Clear all stored secrets and inform active tabs to reset UI state.
  authState = { accessToken: null, csrfToken: null };
  cachedCredentials = null;
  await chrome.storage.local.remove([AUTH_KEY, CRYPTO_KEY]);
  await chrome.storage.sync.remove([CREDENTIALS_KEY]);
  setLastStatus("Logged out");
  try {
    const tabs = await chrome.tabs.query({ url: "https://*.raterhub.com/*" });
    for (const tab of tabs) {
      chrome.tabs
        .sendMessage(tab.id, buildMessage(MESSAGE_TYPES.RESET_WIDGET_STATE))
        .catch(() => {});
    }
  } catch (err) {
    console.warn("[RaterHubTracker] Failed to broadcast reset", err);
  }
}

// ============================================================
// API callers for session data and event recording
// ============================================================

async function fetchSessionSummary(sessionId) {
  // Fetch summary for a specific session, refreshing tokens on 401s.
  const gate = await ensureAccessToken();
  if (!gate.ok) return gate;

  const { throttled } = throttle(`summary-${sessionId}`, 500);
  if (throttled) {
    return { ok: false, error: "THROTTLED" };
  }

  try {
    const makeRequest = () =>
      fetch(`${API_BASE}/sessions/${sessionId}/summary`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${authState.accessToken}`,
        },
      });

    let res = await makeRequest();

    if (res.status === 401) {
      authState.accessToken = null;
      await persistAuthState();
      const relog = await login({ silent: true });
      if (!relog.ok) {
        return { ok: false, status: 401, error: "UNAUTHORIZED" };
      }
      res = await makeRequest();
    }

    if (!res.ok) {
      const text = await res.text();
      console.warn("[RaterHubTracker] Summary failed", res.status, text);
      return { ok: false, status: res.status, error: "SUMMARY_FAILED" };
    }

    const data = await res.json();
    setLastStatus("Summary refreshed");
    return { ok: true, summary: data };
  } catch (err) {
    console.error("[RaterHubTracker] Summary error", err);
    return { ok: false, error: "NETWORK" };
  }
}

async function findActiveSession() {
  // Look up most recent active session to keep UI aligned with backend state.
  const gate = await ensureAccessToken();
  if (!gate.ok) return gate;

  const { throttled } = throttle("recent-sessions", 750);
  if (throttled) {
    return { ok: false, error: "THROTTLED" };
  }

  try {
    const makeRequest = () =>
      fetch(`${API_BASE}/sessions/recent?limit=5`, {
        method: "GET",
        headers: {
          Authorization: `Bearer ${authState.accessToken}`,
        },
      });

    let res = await makeRequest();

    if (res.status === 401) {
      authState.accessToken = null;
      await persistAuthState();
      const relog = await login({ silent: true });
      if (!relog.ok) {
        return { ok: false, status: 401, error: "UNAUTHORIZED" };
      }
      res = await makeRequest();
    }

    if (!res.ok) {
      const text = await res.text();
      console.warn("[RaterHubTracker] Recent sessions failed", res.status, text);
      return { ok: false, status: res.status, error: "RECENT_FAILED" };
    }

    const sessions = await res.json();
    const active = Array.isArray(sessions) ? sessions.find((s) => s.is_active) : null;
    return { ok: true, activeSession: active || null };
  } catch (err) {
    console.error("[RaterHubTracker] Recent sessions error", err);
    return { ok: false, error: "NETWORK" };
  }
}

async function sendEvent(eventType, options = {}) {
  // Record a timestamped event and retry authentication on 401s.
  const gate = await ensureAccessToken();
  if (!gate.ok) return gate;

  const { throttled } = throttle(`event-${eventType}`, 400);
  if (throttled) {
    return { ok: false, error: "THROTTLED" };
  }

  const payload = {
    type: eventType,
    timestamp: options.clientTimestamp
      ? new Date(options.clientTimestamp).toISOString()
      : new Date().toISOString(),
  };

  if (options.sessionId) {
    payload.session_id = options.sessionId;
  }
  if (typeof options.questionIndex === "number") {
    payload.current_question_index = options.questionIndex;
  }

  try {
    const makeRequest = () =>
      fetch(`${API_BASE}/events`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${authState.accessToken}`,
        },
        body: JSON.stringify(payload),
      });

    let res = await makeRequest();

    if (res.status === 401) {
      authState.accessToken = null;
      await persistAuthState();
      const relog = await login({ silent: true });
      if (!relog.ok) {
        return { ok: false, status: 401, error: "UNAUTHORIZED" };
      }
      res = await makeRequest();
    }

    if (!res.ok) {
      const text = await res.text();
      console.warn("[RaterHubTracker] Event failed", res.status, text);
      setLastStatus(`Event ${eventType} failed (${res.status})`);
      return { ok: false, status: res.status, error: "EVENT_FAILED" };
    }

    const data = await res.json();
    setLastStatus(`Event ${eventType} recorded`);

    const sessionId = data.session_id || options.sessionId || null;
    let summary = null;
    if (sessionId) {
      const summaryRes = await fetchSessionSummary(sessionId);
      if (summaryRes.ok) {
        summary = summaryRes.summary || null;
      }
    }

    const totalQuestions =
      typeof data.total_questions === "number"
        ? data.total_questions
        : summary?.total_questions ?? null;

    return {
      ok: true,
      data,
      sessionId,
      totalQuestions,
      summary,
    };
  } catch (err) {
    console.error("[RaterHubTracker] Event error", err);
    setLastStatus(`Event ${eventType} network error`);
    return { ok: false, error: "NETWORK" };
  }
}

async function pushLatestSummaryToTab(tabId) {
  try {
    const activeRes = await findActiveSession();
    if (!activeRes?.ok || !activeRes.activeSession?.session_id) return;
    const sessionId = activeRes.activeSession.session_id;
    const summaryRes = await fetchSessionSummary(sessionId);
    if (!summaryRes?.ok || !summaryRes.summary) return;
    const message = buildMessage(MESSAGE_TYPES.SESSION_SUMMARY_RELAY, {
      sessionId,
      summary: summaryRes.summary,
      totalQuestions: summaryRes.summary?.total_questions ?? null,
    });
    chrome.tabs.sendMessage(tabId, message).catch(() => {});
  } catch (err) {
    console.warn("[RaterHubTracker] Failed to push summary", err);
  }
}

// ============================================================
// Message router: internal actions only expose non-secret data
// ============================================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    switch (message?.type) {
      case MESSAGE_TYPES.LOGIN: {
        const res = await login({ silent: Boolean(message?.silent) });
        sendResponse(buildMessage(MESSAGE_TYPES.LOGIN, res));
        return;
      }
      case MESSAGE_TYPES.CONTROL_EVENT: {
        const res = await sendEvent(message.eventType, {
          sessionId: message.sessionId,
          questionIndex: message.questionIndex,
          clientTimestamp: message.timestamp,
        });
        sendResponse(buildMessage(MESSAGE_TYPES.CONTROL_EVENT, res));
        return;
      }
      case MESSAGE_TYPES.SESSION_SUMMARY: {
        const res = await fetchSessionSummary(message.sessionId);
        sendResponse(buildMessage(MESSAGE_TYPES.SESSION_SUMMARY, res));
        return;
      }
      case MESSAGE_TYPES.FIND_ACTIVE_SESSION: {
        const res = await findActiveSession();
        sendResponse(buildMessage(MESSAGE_TYPES.FIND_ACTIVE_SESSION, res));
        return;
      }
      case "GET_STATUS": {
        const storedCreds = await loadStoredCredentials();
        sendResponse({
          ok: true,
          authenticated: Boolean(authState.accessToken),
          hasCredentials: Boolean(storedCreds),
          lastStatus: message.includeLastStatus ? (await chrome.storage.local.get([STATUS_KEY]))[STATUS_KEY] : undefined,
        });
        return;
      }
      case "GET_AUTH_CONFIG": {
        if (!isInternalPage(sender)) {
          sendResponse({ ok: false, error: "FORBIDDEN" });
          return;
        }
        const creds = (await loadStoredCredentials()) || null;
        sendResponse({ ok: true, config: creds });
        return;
      }
      case "SAVE_AUTH_CONFIG": {
        if (!isInternalPage(sender)) {
          sendResponse({ ok: false, error: "FORBIDDEN" });
          return;
        }
        const config = message.config || {};
        if (config.mode === "password" && config.email && config.password) {
          await persistCredentials({ mode: "password", email: config.email, password: config.password });
          authState.accessToken = null;
          await persistAuthState();
          sendResponse({ ok: true });
        } else if (config.mode === "token" && config.apiToken) {
          await persistCredentials({ mode: "token", apiToken: config.apiToken });
          authState.accessToken = null;
          await persistAuthState();
          sendResponse({ ok: true });
        } else if (config.mode === "refresh" && config.refreshToken) {
          await persistCredentials({ mode: "refresh", refreshToken: config.refreshToken });
          authState.accessToken = null;
          await persistAuthState();
          sendResponse({ ok: true });
        } else {
          sendResponse({ ok: false, error: "INVALID_CONFIG" });
        }
        return;
      }
      case "REQUEST_REFRESH_TOKEN": {
        if (!isInternalPage(sender)) {
          sendResponse({ ok: false, error: "FORBIDDEN" });
          return;
        }
        const payload = await resolveLoginPayload();
        if (!payload.ok) {
          sendResponse({ ok: false, error: payload.error });
          return;
        }
        const res = await login({ silent: true });
        const creds = await loadStoredCredentials();
        sendResponse({ ok: res.ok, refreshToken: creds?.refreshToken });
        return;
      }
      case "LOGOUT_RESET": {
        if (!isInternalPage(sender) && sender?.url) {
          sendResponse({ ok: false, error: "FORBIDDEN" });
          return;
        }
        await logoutAndReset();
        sendResponse({ ok: true });
        return;
      }
      case MESSAGE_TYPES.RESET_WIDGET_POSITION: {
        if (!isInternalPage(sender) && sender?.url) {
          sendResponse({ ok: false, error: "FORBIDDEN" });
          return;
        }
        await chrome.storage.local.remove([POSITION_KEY]);
        try {
          const tabs = await chrome.tabs.query({ url: "https://*.raterhub.com/*" });
          for (const tab of tabs) {
            chrome.tabs
              .sendMessage(tab.id, buildMessage(MESSAGE_TYPES.RESET_WIDGET_POSITION))
              .catch(() => {});
          }
        } catch (err) {
          console.warn("[RaterHubTracker] Failed to broadcast position reset", err);
        }
        sendResponse(buildMessage(MESSAGE_TYPES.RESET_WIDGET_POSITION, { ok: true }));
        return;
      }
      default:
        sendResponse({ ok: false, error: "UNKNOWN_MESSAGE" });
        return;
    }
  })();
  return true;
});

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab?.url?.includes("raterhub.com")) {
    pushLatestSummaryToTab(tabId);
  }
});

(async () => {
  await loadAuthFromStorage();
  const creds = await loadStoredCredentials();
  if (!creds) {
    await promptInteractiveLogin("NO_CREDENTIALS");
    return;
  }

  if (!authState.accessToken) {
    const res = await login({ silent: true });
    if (!res.ok) {
      await promptInteractiveLogin(res.error || "LOGIN_FAILED");
    }
  }
})();
