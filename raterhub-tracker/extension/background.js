const API_BASE = "https://api.raterhub.steigenga.com";
const LOGIN_EMAIL = "melissa517.freelancer@gmail.com";
const LOGIN_PASSWORD = "super-secret";
const AUTH_KEY = "raterhubAuth_v1";
const STATUS_KEY = "raterhubLastStatus_v1";
const throttleMap = {};

let authState = {
  accessToken: null,
  csrfToken: null,
};

async function loadAuthFromStorage() {
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
  try {
    await chrome.storage.local.set({ [AUTH_KEY]: authState });
  } catch (err) {
    console.warn("[RaterHubTracker] Failed to persist auth", err);
  }
}

function setLastStatus(message) {
  chrome.storage.local.set({ [STATUS_KEY]: message }).catch(() => {});
}

function throttle(key, windowMs = 750) {
  const now = Date.now();
  const last = throttleMap[key] || 0;
  if (now - last < windowMs) {
    return { throttled: true, retryIn: windowMs - (now - last) };
  }
  throttleMap[key] = now;
  return { throttled: false };
}

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

async function login() {
  const { throttled } = throttle("login", 1000);
  if (throttled) {
    return { ok: false, error: "THROTTLED" };
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
      body: JSON.stringify({
        email: LOGIN_EMAIL,
        password: LOGIN_PASSWORD,
      }),
    });

    if (res.status === 400) {
      // Likely bad CSRF token; refresh once.
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
        body: JSON.stringify({
          email: LOGIN_EMAIL,
          password: LOGIN_PASSWORD,
        }),
      });
    }

    if (!res.ok) {
      const text = await res.text();
      console.warn("[RaterHubTracker] Login failed", res.status, text);
      setLastStatus(`Login failed (${res.status})`);
      return { ok: false, status: res.status, error: "LOGIN_FAILED" };
    }

    const data = await res.json();
    authState.accessToken = data.access_token;
    await persistAuthState();
    setLastStatus("Logged in");
    return { ok: true, token: authState.accessToken };
  } catch (err) {
    console.error("[RaterHubTracker] Login error", err);
    setLastStatus("Login error");
    return { ok: false, error: "NETWORK" };
  }
}

async function ensureAccessToken() {
  if (authState.accessToken) {
    return { ok: true, token: authState.accessToken };
  }
  return login();
}

async function fetchSessionSummary(sessionId) {
  const gate = await ensureAccessToken();
  if (!gate.ok) return gate;

  const { throttled } = throttle(`summary-${sessionId}`, 500);
  if (throttled) {
    return { ok: false, error: "THROTTLED" };
  }

  try {
    const res = await fetch(`${API_BASE}/sessions/${sessionId}/summary`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${authState.accessToken}`,
      },
    });

    if (res.status === 401) {
      authState.accessToken = null;
      await persistAuthState();
      return { ok: false, status: 401, error: "UNAUTHORIZED" };
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
  const gate = await ensureAccessToken();
  if (!gate.ok) return gate;

  const { throttled } = throttle("recent-sessions", 750);
  if (throttled) {
    return { ok: false, error: "THROTTLED" };
  }

  try {
    const res = await fetch(`${API_BASE}/sessions/recent?limit=5`, {
      method: "GET",
      headers: {
        Authorization: `Bearer ${authState.accessToken}`,
      },
    });

    if (res.status === 401) {
      authState.accessToken = null;
      await persistAuthState();
      return { ok: false, status: 401, error: "UNAUTHORIZED" };
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

async function sendEvent(eventType) {
  const gate = await ensureAccessToken();
  if (!gate.ok) return gate;

  const { throttled } = throttle(`event-${eventType}`, 400);
  if (throttled) {
    return { ok: false, error: "THROTTLED" };
  }

  const payload = {
    type: eventType,
    timestamp: new Date().toISOString(),
  };

  try {
    const res = await fetch(`${API_BASE}/events`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${authState.accessToken}`,
      },
      body: JSON.stringify(payload),
    });

    if (res.status === 401) {
      authState.accessToken = null;
      await persistAuthState();
      return { ok: false, status: 401, error: "UNAUTHORIZED" };
    }

    if (!res.ok) {
      const text = await res.text();
      console.warn("[RaterHubTracker] Event failed", res.status, text);
      setLastStatus(`Event ${eventType} failed (${res.status})`);
      return { ok: false, status: res.status, error: "EVENT_FAILED" };
    }

    const data = await res.json();
    setLastStatus(`Event ${eventType} recorded`);
    return { ok: true, data };
  } catch (err) {
    console.error("[RaterHubTracker] Event error", err);
    setLastStatus(`Event ${eventType} network error`);
    return { ok: false, error: "NETWORK" };
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    switch (message?.type) {
      case "LOGIN": {
        const res = await login();
        sendResponse(res);
        return;
      }
      case "SEND_EVENT": {
        const res = await sendEvent(message.eventType);
        sendResponse(res);
        return;
      }
      case "SESSION_SUMMARY": {
        const res = await fetchSessionSummary(message.sessionId);
        sendResponse(res);
        return;
      }
      case "FIND_ACTIVE_SESSION": {
        const res = await findActiveSession();
        sendResponse(res);
        return;
      }
      case "GET_STATUS": {
        sendResponse({
          ok: true,
          authenticated: Boolean(authState.accessToken),
          lastStatus: message.includeLastStatus ? (await chrome.storage.local.get([STATUS_KEY]))[STATUS_KEY] : undefined,
        });
        return;
      }
      default:
        sendResponse({ ok: false, error: "UNKNOWN_MESSAGE" });
        return;
    }
  })();
  return true;
});

loadAuthFromStorage();
