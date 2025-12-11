(() => {
  const POS_KEY = "raterhubTrackerPos_v2";
  const STATE_KEY = "raterhubTrackerState_v2";

  const MESSAGE_TYPES = {
    CONTROL_EVENT: "SEND_EVENT",
    FIND_ACTIVE_SESSION: "FIND_ACTIVE_SESSION",
    LOGIN: "LOGIN",
    SESSION_SUMMARY: "SESSION_SUMMARY",
    SESSION_SUMMARY_RELAY: "SESSION_SUMMARY_RELAY",
    RESET_WIDGET_STATE: "RESET_WIDGET_STATE",
  };

  // --- UI + session state ---
  let questionIndex = 0;
  let currentSessionId = null;
  let questionStartTime = null;
  let accumulatedActiveMs = 0;
  let timerIntervalId = null;
  let isPaused = false;
  let isCollapsed = false;
  let lastSummary = null;

  // --- Widget elements ---
  let widget,
    statusEl,
    userEl,
    questionEl,
    timerEl,
    lastEventEl,
    bodyContainer,
    toggleBtn,
    sessionStatsEl;

  // --- Drag state ---
  let isDragging = false;
  let dragStartMouseX = 0;
  let dragStartMouseY = 0;
  let dragStartLeft = 0;
  let dragStartTop = 0;

  function storageGet(key) {
    return chrome.storage.local.get([key]).then((res) => res[key]);
  }

  function storageSet(key, value) {
    return chrome.storage.local.set({ [key]: value });
  }

  // -----------------------------------------
  // Persistence helpers
  // -----------------------------------------

  async function saveWidgetPosition() {
    if (!widget) return;
    try {
      const rect = widget.getBoundingClientRect();
      await storageSet(POS_KEY, { left: rect.left, top: rect.top });
    } catch (e) {
      console.warn("[RaterHubTracker] Failed to save widget position:", e);
    }
  }

  async function loadWidgetPosition() {
    if (!widget) return;
    try {
      const pos = await storageGet(POS_KEY);
      if (pos && typeof pos.left === "number" && typeof pos.top === "number") {
        widget.style.left = `${pos.left}px`;
        widget.style.top = `${pos.top}px`;
        widget.style.right = "auto";
        widget.style.bottom = "auto";
      }
    } catch (e) {
      console.warn("[RaterHubTracker] Failed to load widget position:", e);
    }
  }

  async function saveState() {
    try {
      const state = {
        questionIndex,
        currentSessionId,
        isCollapsed,
        accumulatedActiveMs,
        questionStartTime,
        isPaused,
        lastSummary,
      };
      await storageSet(STATE_KEY, state);
    } catch (e) {
      console.warn("[RaterHubTracker] Failed to save state:", e);
    }
  }

  async function loadState() {
    try {
      const state = await storageGet(STATE_KEY);
      if (!state) return;
      if (typeof state.questionIndex === "number") {
        questionIndex = state.questionIndex;
      }
      if (typeof state.currentSessionId === "string") {
        currentSessionId = state.currentSessionId;
      }
      if (typeof state.isCollapsed === "boolean") {
        isCollapsed = state.isCollapsed;
      }
      if (typeof state.accumulatedActiveMs === "number") {
        accumulatedActiveMs = state.accumulatedActiveMs;
      }
      if (typeof state.questionStartTime === "number") {
        questionStartTime = state.questionStartTime;
      }
      if (typeof state.isPaused === "boolean") {
        isPaused = state.isPaused;
      }
      if (typeof state.lastSummary === "object" && state.lastSummary !== null) {
        lastSummary = state.lastSummary;
      }
    } catch (e) {
      console.warn("[RaterHubTracker] Failed to load state:", e);
    }
  }

  // -----------------------------------------
  // Widget creation & helpers
  // -----------------------------------------

  function applyCollapsedState() {
    if (!bodyContainer || !toggleBtn) return;
    if (isCollapsed) {
      bodyContainer.style.display = "none";
      toggleBtn.textContent = "▴";
    } else {
      bodyContainer.style.display = "block";
      toggleBtn.textContent = "▾";
    }
  }

  function createWidget() {
    widget = document.createElement("div");
    widget.id = "raterhub-tracker-widget";
    widget.style.position = "fixed";
    widget.style.bottom = "16px";
    widget.style.right = "16px";
    widget.style.zIndex = "999999";
    widget.style.background = "#ffffff";
    widget.style.borderRadius = "10px";
    widget.style.boxShadow = "0 6px 18px rgba(0, 0, 0, 0.15)";
    widget.style.padding = "8px 10px";
    widget.style.fontFamily = 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
    widget.style.fontSize = "12px";
    widget.style.color = "#1f2933";
    widget.style.minWidth = "240px";
    widget.style.border = "2px solid #8b5cf6";
    widget.style.backgroundImage = "linear-gradient(to bottom, #f9f5ff, #ffffff)";
    widget.style.cursor = "default";

    const header = document.createElement("div");
    header.style.display = "flex";
    header.style.alignItems = "center";
    header.style.justifyContent = "space-between";
    header.style.marginBottom = "4px";
    header.style.cursor = "move";
    header.style.userSelect = "none";
    header.style.touchAction = "none";

    const title = document.createElement("div");
    title.textContent = "RaterHub Tracker";
    title.style.fontWeight = "700";
    title.style.fontSize = "13px";
    title.style.color = "#6d28d9";

    toggleBtn = document.createElement("button");
    toggleBtn.textContent = "▾";
    toggleBtn.style.border = "none";
    toggleBtn.style.background = "transparent";
    toggleBtn.style.color = "#4b5563";
    toggleBtn.style.cursor = "pointer";
    toggleBtn.style.fontSize = "14px";
    toggleBtn.style.padding = "0 0 0 8px";
    toggleBtn.style.lineHeight = "1";

    header.appendChild(title);
    header.appendChild(toggleBtn);

    bodyContainer = document.createElement("div");

    statusEl = document.createElement("div");
    statusEl.textContent = "Loaded – logging in…";
    statusEl.style.fontSize = "11px";
    statusEl.style.marginBottom = "6px";
    statusEl.style.color = "#4b5563";

    userEl = document.createElement("div");
    userEl.textContent = "User: (not logged in)";
    userEl.style.marginBottom = "2px";

    questionEl = document.createElement("div");
    questionEl.textContent = "Question: –";
    questionEl.style.marginBottom = "2px";

    timerEl = document.createElement("div");
    timerEl.textContent = "Timer: 00:00";
    timerEl.style.marginBottom = "6px";
    timerEl.style.fontFeatureSettings = '"tnum" 1';
    timerEl.style.fontVariantNumeric = "tabular-nums";
    timerEl.style.color = "#4c1d95";

    sessionStatsEl = document.createElement("div");
    sessionStatsEl.textContent = "Session: –";
    sessionStatsEl.style.fontSize = "11px";
    sessionStatsEl.style.marginBottom = "6px";
    sessionStatsEl.style.color = "#4b5563";

    lastEventEl = document.createElement("div");
    lastEventEl.textContent = "Last event: –";
    lastEventEl.style.fontSize = "11px";
    lastEventEl.style.marginBottom = "6px";
    lastEventEl.style.color = "#6b7280";

    const hotkeys = document.createElement("div");
    hotkeys.style.fontSize = "10px";
    hotkeys.style.color = "#6b7280";
    hotkeys.innerHTML = `
            <strong>Keys:</strong>
            Ctrl+Q = Next,
            Ctrl+Shift+P = Pause,
            Ctrl+Shift+X = Exit,
            Ctrl+Shift+Q = Undo
        `;

    bodyContainer.appendChild(statusEl);
    bodyContainer.appendChild(userEl);
    bodyContainer.appendChild(questionEl);
    bodyContainer.appendChild(timerEl);
    bodyContainer.appendChild(sessionStatsEl);
    bodyContainer.appendChild(lastEventEl);
    bodyContainer.appendChild(hotkeys);

    widget.appendChild(header);
    widget.appendChild(bodyContainer);
    document.body.appendChild(widget);

    loadWidgetPosition();

    header.addEventListener("pointerdown", onHeaderPointerDown);
    document.addEventListener("pointermove", onDocumentPointerMove);
    document.addEventListener("pointerup", onDocumentPointerUp);
    document.addEventListener("pointercancel", onDocumentPointerUp);

    toggleBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      isCollapsed = !isCollapsed;
      applyCollapsedState();
      saveState();
    });

    applyCollapsedState();
  }

  function onHeaderPointerDown(e) {
    if (e.target === toggleBtn) return;

    widget.setPointerCapture(e.pointerId);
    isDragging = true;
    dragStartMouseX = e.clientX;
    dragStartMouseY = e.clientY;

    const rect = widget.getBoundingClientRect();
    dragStartLeft = rect.left;
    dragStartTop = rect.top;

    widget.style.left = `${dragStartLeft}px`;
    widget.style.top = `${dragStartTop}px`;
    widget.style.right = "auto";
    widget.style.bottom = "auto";

    e.preventDefault();
  }

  function onDocumentPointerMove(e) {
    if (!isDragging) return;
    const dx = e.clientX - dragStartMouseX;
    const dy = e.clientY - dragStartMouseY;
    widget.style.left = `${dragStartLeft + dx}px`;
    widget.style.top = `${dragStartTop + dy}px`;
  }

  function onDocumentPointerUp(e) {
    if (!isDragging) return;
    isDragging = false;
    try {
      widget.releasePointerCapture(e.pointerId);
    } catch (_) {}
    saveWidgetPosition();
  }

  function setStatus(msg, color) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.style.color = color || "#4b5563";
  }

  function flashWidget(color) {
    if (!widget) return;
    const original = widget.style.borderColor;
    widget.style.borderColor = color;
    setTimeout(() => {
      widget.style.borderColor = original;
    }, 250);
  }

  function updateUserDisplay(isLoggedIn) {
    if (!userEl) return;
    userEl.textContent = isLoggedIn ? "User: logged in" : "User: (not logged in)";
  }

  function updateQuestionDisplay() {
    if (!questionEl) return;
    questionEl.textContent = `Question: ${questionIndex > 0 ? questionIndex : "–"}`;
  }

  function formatMs(ms) {
    const totalSeconds = Math.max(0, Math.floor(ms / 1000));
    const minutes = Math.floor(totalSeconds / 60)
      .toString()
      .padStart(2, "0");
    const seconds = (totalSeconds % 60).toString().padStart(2, "0");
    return `${minutes}:${seconds}`;
  }

  function updateTimerDisplay() {
    if (!timerEl) return;
    let elapsedMs = accumulatedActiveMs;
    if (!isPaused && questionStartTime) {
      elapsedMs += Date.now() - questionStartTime;
    }
    timerEl.textContent = `Timer: ${formatMs(elapsedMs)}`;
  }

  function startTimerLoop() {
    if (timerIntervalId) return;
    timerIntervalId = setInterval(updateTimerDisplay, 500);
  }

  function stopTimerLoop() {
    if (!timerIntervalId) return;
    clearInterval(timerIntervalId);
    timerIntervalId = null;
  }

  function startNewQuestionTimer() {
    accumulatedActiveMs = 0;
    questionStartTime = Date.now();
    isPaused = false;
    updateTimerDisplay();
    startTimerLoop();
  }

  function togglePauseTimer() {
    if (isPaused) {
      questionStartTime = Date.now();
      isPaused = false;
      startTimerLoop();
      return;
    }

    if (questionStartTime) {
      accumulatedActiveMs += Date.now() - questionStartTime;
    }
    questionStartTime = null;
    isPaused = true;
    updateTimerDisplay();
    stopTimerLoop();
  }

  function exitTimer() {
    accumulatedActiveMs = 0;
    questionStartTime = null;
    isPaused = false;
    updateTimerDisplay();
    stopTimerLoop();
  }

  function resetTimerForUndo() {
    accumulatedActiveMs = 0;
    questionStartTime = Date.now();
    isPaused = false;
    updateQuestionDisplay();
    updateTimerDisplay();
    startTimerLoop();
  }

  function restoreTimerFromState() {
    if (isPaused) {
      questionStartTime = null;
      stopTimerLoop();
      updateTimerDisplay();
      return;
    }

    if (questionStartTime) {
      accumulatedActiveMs += Math.max(0, Date.now() - questionStartTime);
      questionStartTime = Date.now();
      startTimerLoop();
    } else if (accumulatedActiveMs > 0) {
      startTimerLoop();
    }

    updateTimerDisplay();
  }

  function updateSessionStatsText(text) {
    if (!sessionStatsEl) return;
    sessionStatsEl.textContent = text;
  }

  function applySessionSummary(summary) {
    if (!summary) return;
    lastSummary = summary;
    if (summary.is_active === false) {
      hardResetSessionUI("Session: ended");
      return;
    }
    const totalQ = summary.total_questions ?? 0;
    const avg = summary.avg_active_mmss || "00:00";
    const emoji = summary.pace_emoji || "";
    const label = summary.pace_label || "";
    updateSessionStatsText(`Session: ${totalQ} q, AHT ${avg} ${emoji} ${label}`);
    saveState();
  }

  function hardResetSessionUI(reasonText) {
    currentSessionId = null;
    questionIndex = 0;
    accumulatedActiveMs = 0;
    questionStartTime = null;
    isPaused = false;
    lastSummary = null;
    stopTimerLoop();
    updateQuestionDisplay();
    updateTimerDisplay();
    updateSessionStatsText(reasonText || "Session: –");
    saveState();
  }

  // -----------------------------------------
  // Messaging helpers
  // -----------------------------------------

  function sendRuntimeMessage(type, payload = {}) {
    const message = { type, timestamp: Date.now(), ...payload };
    return chrome.runtime.sendMessage(message).catch((err) => {
      console.warn("[RaterHubTracker] Message failed", message, err);
      return { ok: false, error: "MESSAGE_FAILED" };
    });
  }

  async function refreshSessionSummary() {
    if (!currentSessionId) {
      hardResetSessionUI("Session: –");
      return;
    }

    const res = await sendRuntimeMessage(MESSAGE_TYPES.SESSION_SUMMARY, {
      sessionId: currentSessionId,
    });

    if (!res?.ok) {
      if (res?.error === "UNAUTHORIZED") {
        updateUserDisplay(false);
      }
      updateSessionStatsText("Session: summary error");
      return;
    }

    applySessionSummary(res.summary || {});
  }

  async function syncFromBackend() {
    if (currentSessionId) {
      await refreshSessionSummary();
      return;
    }

    const res = await sendRuntimeMessage(MESSAGE_TYPES.FIND_ACTIVE_SESSION);
    if (!res?.ok || !res.activeSession) {
      updateSessionStatsText("Session: –");
      return;
    }

    const active = res.activeSession;
    currentSessionId = active.session_id;
    if (typeof active.current_question_index === "number") {
      questionIndex = active.current_question_index;
      updateQuestionDisplay();
    }
    await refreshSessionSummary();
    saveState();
  }

  async function login() {
    setStatus("Logging in…", "#4b5563");
    const res = await sendRuntimeMessage(MESSAGE_TYPES.LOGIN);

    if (!res?.ok) {
      setStatus("Login failed", "#b91c1c");
      flashWidget("#ef4444");
      updateUserDisplay(false);
      return;
    }

    updateUserDisplay(true);
    setStatus("Logged in ✔", "#15803d");
    flashWidget("#22c55e");
    await syncFromBackend();
  }

  async function sendEvent(eventType) {
    const res = await sendRuntimeMessage(MESSAGE_TYPES.CONTROL_EVENT, {
      eventType,
      sessionId: currentSessionId,
      questionIndex,
    });

    if (!res?.ok) {
      if (res?.error === "THROTTLED") {
        setStatus(`Event ${eventType} throttled`, "#b45309");
      } else if (res?.error === "UNAUTHORIZED") {
        setStatus("Re-authenticating…", "#b45309");
        updateUserDisplay(false);
        await login();
      } else {
        setStatus(`Event ${eventType} failed`, "#b91c1c");
      }
      lastEventEl.textContent = `Last event: ${eventType} (error)`;
      flashWidget("#ef4444");
      return;
    }

    const data = res.data || {};
    const sessionIdFromResponse = res.sessionId || data.session_id || null;
    const backendTotal =
      typeof res.totalQuestions === "number"
        ? res.totalQuestions
        : typeof data.total_questions === "number"
          ? data.total_questions
          : null;

    setStatus(`Event ${eventType} recorded ✔`, "#15803d");
    lastEventEl.textContent = `Last event: ${eventType} @ ${new Date().toLocaleTimeString()}`;
    flashWidget("#22c55e");

    if (sessionIdFromResponse) {
      currentSessionId = sessionIdFromResponse;
    }

    if (eventType === "NEXT") {
      if (backendTotal !== null) {
        questionIndex = backendTotal;
      } else {
        questionIndex += 1;
      }
      saveState();
      startNewQuestionTimer();
    } else if (eventType === "PAUSE") {
      togglePauseTimer();
      saveState();
    } else if (eventType === "EXIT") {
      if (backendTotal !== null) {
        questionIndex = backendTotal;
      }
      saveState();
      exitTimer();
    } else if (eventType === "UNDO") {
      if (backendTotal !== null) {
        questionIndex = backendTotal;
      } else if (questionIndex > 0) {
        questionIndex -= 1;
      }
      saveState();
      resetTimerForUndo();
    }

    updateQuestionDisplay();
    if (res.summary) {
      applySessionSummary(res.summary);
    } else {
      await refreshSessionSummary();
    }
    saveState();
  }

  // -----------------------------------------
  // Keyboard handling
  // -----------------------------------------

  function handleKeydown(e) {
    const tag = e.target && e.target.tagName ? e.target.tagName.toLowerCase() : "";
    if (tag === "input" || tag === "textarea" || tag === "select" || e.isComposing) {
      return;
    }

    if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "q") {
      e.preventDefault();
      sendEvent("NEXT");
      return;
    }

    if (e.ctrlKey && e.shiftKey && !e.altKey && e.key.toLowerCase() === "p") {
      e.preventDefault();
      sendEvent("PAUSE");
      return;
    }

    if (e.ctrlKey && e.shiftKey && !e.altKey && e.key.toLowerCase() === "x") {
      e.preventDefault();
      sendEvent("EXIT");
      return;
    }

    if (e.ctrlKey && e.shiftKey && !e.altKey && e.key.toLowerCase() === "q") {
      e.preventDefault();
      sendEvent("UNDO");
    }
  }

  // -----------------------------------------
  // Init
  // -----------------------------------------

  async function init() {
    createWidget();
    await loadState();
    updateQuestionDisplay();
    restoreTimerFromState();
    applyCollapsedState();
    updateUserDisplay(false);
    setStatus("Loaded – logging in…", "#4b5563");
    if (lastSummary) {
      applySessionSummary(lastSummary);
    } else {
      updateSessionStatsText("Session: –");
    }

    window.addEventListener("keydown", handleKeydown, true);
    chrome.runtime.onMessage.addListener((message) => {
      if (message?.type === MESSAGE_TYPES.RESET_WIDGET_STATE) {
        hardResetSessionUI("Session: –");
        updateUserDisplay(false);
        setStatus("Logged out", "#6b7280");
        return;
      }
      if (message?.type === MESSAGE_TYPES.SESSION_SUMMARY_RELAY && message.summary) {
        if (typeof message.totalQuestions === "number") {
          questionIndex = message.totalQuestions;
          updateQuestionDisplay();
        }
        if (typeof message.sessionId === "string") {
          currentSessionId = message.sessionId;
        }
        applySessionSummary(message.summary);
      }
    });

    await login();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
