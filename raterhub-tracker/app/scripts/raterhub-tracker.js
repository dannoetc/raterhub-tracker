// ==UserScript==
// @name         RaterHub Time Tracker
// @namespace    https://raterhub.steigenga.com
// @version      0.8
// @description  Track RaterHub question timing via FastAPI backend with JWT auth and on-page widget
// @author       Melissa Steigenga
// @match        *://*.raterhub.com/*
// @run-at       document-end
// @grant        none
// ==/UserScript==

window.addEventListener('load', function () {
    'use strict';

    const API_BASE = "https://api.raterhub.steigenga.com";
    const LOGIN_EMAIL = "melissa517.freelancer@gmail.com";
    const LOGIN_PASSWORD = "super-secret"; // personal use only

    // LocalStorage keys
    const POS_KEY = "raterhubTrackerPos_v1";
    const STATE_KEY = "raterhubTrackerState_v1";

    let accessToken = null;
    let csrfToken = null;

    // --- UI+session state ---
    let questionIndex = 0;           // what we display as "Question"
    let currentSessionId = null;     // public_id from backend
    let questionStartTime = null;    // ms timestamp when current question started
    let accumulatedActiveMs = 0;     // ms of active time before current run
    let timerIntervalId = null;
    let isPaused = false;

    // --- Widget elements ---
    let widget, statusEl, userEl, questionEl, timerEl, lastEventEl, bodyContainer,
        toggleBtn, sessionStatsEl;

    // --- Drag state ---
    let isDragging = false;
    let dragStartMouseX = 0;
    let dragStartMouseY = 0;
    let dragStartLeft = 0;
    let dragStartTop = 0;

    // -----------------------------------------
    // Persistence helpers
    // -----------------------------------------

    function saveWidgetPosition() {
        if (!widget) return;
        try {
            const rect = widget.getBoundingClientRect();
            const pos = { left: rect.left, top: rect.top };
            localStorage.setItem(POS_KEY, JSON.stringify(pos));
        } catch (e) {
            console.warn("[RaterHubTracker] Failed to save widget position:", e);
        }
    }

    function loadWidgetPosition() {
        if (!widget) return;
        try {
            const raw = localStorage.getItem(POS_KEY);
            if (!raw) return;
            const pos = JSON.parse(raw);
            if (typeof pos.left === "number" && typeof pos.top === "number") {
                widget.style.left = pos.left + "px";
                widget.style.top = pos.top + "px";
                widget.style.right = "auto";
                widget.style.bottom = "auto";
            }
        } catch (e) {
            console.warn("[RaterHubTracker] Failed to load widget position:", e);
        }
    }

    function saveState() {
        try {
            const state = {
                questionIndex: questionIndex,
                currentSessionId: currentSessionId,
            };
            localStorage.setItem(STATE_KEY, JSON.stringify(state));
        } catch (e) {
            console.warn("[RaterHubTracker] Failed to save state:", e);
        }
    }

    function loadState() {
        try {
            const raw = localStorage.getItem(STATE_KEY);
            if (!raw) return;
            const state = JSON.parse(raw);
            if (typeof state.questionIndex === "number") {
                questionIndex = state.questionIndex;
            }
            if (typeof state.currentSessionId === "string") {
                currentSessionId = state.currentSessionId;
            }
        } catch (e) {
            console.warn("[RaterHubTracker] Failed to load state:", e);
        }
    }

    // -----------------------------------------
    // Widget creation & helpers
    // -----------------------------------------

    function createWidget() {
        widget = document.createElement('div');
        widget.id = 'raterhub-tracker-widget';
        widget.style.position = 'fixed';
        widget.style.bottom = '16px';
        widget.style.right = '16px';
        widget.style.zIndex = '999999';
        widget.style.background = '#ffffff';
        widget.style.borderRadius = '10px';
        widget.style.boxShadow = '0 6px 18px rgba(0, 0, 0, 0.15)';
        widget.style.padding = '8px 10px';
        widget.style.fontFamily = 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        widget.style.fontSize = '12px';
        widget.style.color = '#1f2933';
        widget.style.minWidth = '240px';
        widget.style.border = '2px solid #8b5cf6'; // purple
        widget.style.backgroundImage = 'linear-gradient(to bottom, #f9f5ff, #ffffff)';
        widget.style.cursor = 'default';

        // Header (drag handle + toggle)
        const header = document.createElement('div');
        header.style.display = 'flex';
        header.style.alignItems = 'center';
        header.style.justifyContent = 'space-between';
        header.style.marginBottom = '4px';
        header.style.cursor = 'move';  // drag handle

        const title = document.createElement('div');
        title.textContent = 'RaterHub Tracker';
        title.style.fontWeight = '700';
        title.style.fontSize = '13px';
        title.style.color = '#6d28d9';

        toggleBtn = document.createElement('button');
        toggleBtn.textContent = '▾'; // down arrow = expanded
        toggleBtn.style.border = 'none';
        toggleBtn.style.background = 'transparent';
        toggleBtn.style.color = '#4b5563';
        toggleBtn.style.cursor = 'pointer';
        toggleBtn.style.fontSize = '14px';
        toggleBtn.style.padding = '0 0 0 8px';
        toggleBtn.style.lineHeight = '1';

        header.appendChild(title);
        header.appendChild(toggleBtn);

        // Body container (everything except header)
        bodyContainer = document.createElement('div');

        statusEl = document.createElement('div');
        statusEl.textContent = 'Loaded – logging in…';
        statusEl.style.fontSize = '11px';
        statusEl.style.marginBottom = '6px';
        statusEl.style.color = '#4b5563';

        userEl = document.createElement('div');
        userEl.textContent = `User: (not logged in)`;
        userEl.style.marginBottom = '2px';

        questionEl = document.createElement('div');
        questionEl.textContent = 'Question: –';
        questionEl.style.marginBottom = '2px';

        timerEl = document.createElement('div');
        timerEl.textContent = 'Timer: 00:00';
        timerEl.style.marginBottom = '6px';
        timerEl.style.fontFeatureSettings = '"tnum" 1';
        timerEl.style.fontVariantNumeric = 'tabular-nums';
        timerEl.style.color = '#4c1d95';

        sessionStatsEl = document.createElement('div');
        sessionStatsEl.textContent = 'Session: –';
        sessionStatsEl.style.fontSize = '11px';
        sessionStatsEl.style.marginBottom = '6px';
        sessionStatsEl.style.color = '#4b5563';

        lastEventEl = document.createElement('div');
        lastEventEl.textContent = 'Last event: –';
        lastEventEl.style.fontSize = '11px';
        lastEventEl.style.marginBottom = '6px';
        lastEventEl.style.color = '#6b7280';

        const hotkeys = document.createElement('div');
        hotkeys.style.fontSize = '10px';
        hotkeys.style.color = '#6b7280';
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

        // Try to restore last position
        loadWidgetPosition();

        // --- Dragging events (on header only) ---
        header.addEventListener('mousedown', onHeaderMouseDown);
        document.addEventListener('mousemove', onDocumentMouseMove);
        document.addEventListener('mouseup', onDocumentMouseUp);

        // --- Collapse/expand ---
        toggleBtn.addEventListener('click', function (e) {
            e.stopPropagation();
            if (bodyContainer.style.display === 'none') {
                bodyContainer.style.display = 'block';
                toggleBtn.textContent = '▾';
            } else {
                bodyContainer.style.display = 'none';
                toggleBtn.textContent = '▴';
            }
        });
    }

    function onHeaderMouseDown(e) {
        // Avoid starting drag when clicking directly on the toggle button
        if (e.target === toggleBtn) return;

        isDragging = true;
        dragStartMouseX = e.clientX;
        dragStartMouseY = e.clientY;

        const rect = widget.getBoundingClientRect();
        dragStartLeft = rect.left;
        dragStartTop = rect.top;

        // Switch to top/left positioning for dragging
        widget.style.left = `${dragStartLeft}px`;
        widget.style.top = `${dragStartTop}px`;
        widget.style.right = 'auto';
        widget.style.bottom = 'auto';

        // Prevent text selection
        e.preventDefault();
    }

    function onDocumentMouseMove(e) {
        if (!isDragging) return;
        const dx = e.clientX - dragStartMouseX;
        const dy = e.clientY - dragStartMouseY;
        widget.style.left = `${dragStartLeft + dx}px`;
        widget.style.top = `${dragStartTop + dy}px`;
    }

    function onDocumentMouseUp() {
        if (!isDragging) return;
        isDragging = false;
        saveWidgetPosition();
    }

    function setStatus(msg, color) {
        if (!statusEl) return;
        statusEl.textContent = msg;
        statusEl.style.color = color || '#4b5563';
    }

    function flashWidget(color) {
        if (!widget) return;
        const original = widget.style.borderColor;
        widget.style.borderColor = color;
        setTimeout(() => {
            widget.style.borderColor = original;
        }, 250);
    }

    function updateUserDisplay() {
        if (!userEl) return;
        if (accessToken) {
            userEl.textContent = `User: ${LOGIN_EMAIL}`;
        } else {
            userEl.textContent = 'User: (not logged in)';
        }
    }

    function updateQuestionDisplay() {
        if (!questionEl) return;
        questionEl.textContent = `Question: ${questionIndex > 0 ? questionIndex : '–'}`;
    }

    function formatMmSs(ms) {
        const totalSec = Math.floor(ms / 1000);
        const m = Math.floor(totalSec / 60);
        const s = totalSec % 60;
        return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }

    function updateTimerDisplay() {
        if (!timerEl) return;
        let totalMs = accumulatedActiveMs;
        if (!isPaused && questionStartTime != null) {
            totalMs += (Date.now() - questionStartTime);
        }
        timerEl.textContent = `Timer: ${formatMmSs(totalMs)}`;
        timerEl.style.opacity = isPaused ? '0.6' : '1.0';
    }

    function startTimerLoop() {
        if (timerIntervalId) clearInterval(timerIntervalId);
        timerIntervalId = setInterval(updateTimerDisplay, 500);
    }

    function stopTimerLoop() {
        if (timerIntervalId) {
            clearInterval(timerIntervalId);
            timerIntervalId = null;
        }
    }

    // Called when starting a *new* question (questionIndex handled elsewhere)
    function startNewQuestionTimer() {
        accumulatedActiveMs = 0;
        questionStartTime = Date.now();
        isPaused = false;
        updateQuestionDisplay();
        updateTimerDisplay();
        startTimerLoop();
    }

    // Pause/resume toggle
    function togglePauseTimer() {
        if (questionIndex === 0) {
            // No active question yet; ignore
            return;
        }
        if (!isPaused) {
            // Pausing
            if (questionStartTime != null) {
                accumulatedActiveMs += (Date.now() - questionStartTime);
            }
            questionStartTime = null;
            isPaused = true;
            updateTimerDisplay();
        } else {
            // Resuming
            questionStartTime = Date.now();
            isPaused = false;
            updateTimerDisplay();
        }
    }

    // Exit: stop timer, keep last shown value
    function exitTimer() {
        if (questionIndex === 0) return;
        if (questionStartTime != null) {
            accumulatedActiveMs += (Date.now() - questionStartTime);
        }
        questionStartTime = null;
        isPaused = true;
        updateTimerDisplay();
        stopTimerLoop();
    }

    // Undo: timer resets fresh for the (new) current questionIndex
    function resetTimerForUndo() {
        accumulatedActiveMs = 0;
        questionStartTime = Date.now();
        isPaused = false;
        updateQuestionDisplay();
        updateTimerDisplay();
        startTimerLoop();
    }

    function updateSessionStatsText(text) {
        if (!sessionStatsEl) return;
        sessionStatsEl.textContent = text;
    }

    function hardResetSessionUI(reasonText) {
        currentSessionId = null;
        questionIndex = 0;
        accumulatedActiveMs = 0;
        questionStartTime = null;
        isPaused = false;
        stopTimerLoop();
        updateQuestionDisplay();
        updateTimerDisplay();
        updateSessionStatsText(reasonText || 'Session: –');
        saveState();
    }

    // -----------------------------------------
    // Backend sync: session summary (AHT, pace)
    // -----------------------------------------

    async function refreshSessionSummary() {
        if (!accessToken || !currentSessionId) {
            hardResetSessionUI('Session: –');
            return;
        }

        try {
            const res = await fetch(`${API_BASE}/sessions/${currentSessionId}/summary`, {
                method: "GET",
                headers: {
                    "Authorization": `Bearer ${accessToken}`,
                },
            });
            if (!res.ok) {
                const text = await res.text();
                console.error("[RaterHubTracker] Summary fetch failed:", res.status, text);
                // On error we don't blow away the current session, just show an error
                updateSessionStatsText('Session: summary error');
                return;
            }
            const summary = await res.json();

            // If the session is not active anymore, clear UI + state
            if (summary.is_active === false) {
                hardResetSessionUI('Session: ended');
                return;
            }

            // summary fields: total_questions, avg_active_mmss, pace_label, pace_emoji, etc.
            const totalQ = summary.total_questions ?? 0;
            const avg = summary.avg_active_mmss || "00:00";
            const emoji = summary.pace_emoji || "";
            const label = summary.pace_label || "";

            updateSessionStatsText(
                `Session: ${totalQ} q, AHT ${avg} ${emoji} ${label}`
            );
        } catch (e) {
            console.error("[RaterHubTracker] Summary fetch error:", e);
            updateSessionStatsText('Session: summary error');
        }
    }

    // Can be used after login if we have a remembered sessionId
    async function syncFromBackendOnLogin() {
        if (!accessToken) return;

        // If we have a remembered sessionId, check if it's still active
        if (currentSessionId) {
            await refreshSessionSummary();
            // refreshSessionSummary will clear state if ended
            if (!currentSessionId) {
                return;
            }
            return;
        }

        // Optional: if you want to guess the current session from recent sessions:
        try {
            const res = await fetch(`${API_BASE}/sessions/recent?limit=5`, {
                method: "GET",
                headers: {
                    "Authorization": `Bearer ${accessToken}`,
                },
            });
            if (!res.ok) {
                console.warn("[RaterHubTracker] /sessions/recent failed:", res.status);
                return;
            }
            const sessions = await res.json();
            if (!Array.isArray(sessions) || sessions.length === 0) {
                return;
            }

            // Prefer an active session; if none are active, don't pick any
            let active = sessions.find(s => s.is_active);
            if (!active) {
                // no active session; show "no session"
                hardResetSessionUI('Session: –');
                return;
            }

            currentSessionId = active.session_id;

            if (typeof active.current_question_index === "number") {
                questionIndex = active.current_question_index;
                saveState();
                updateQuestionDisplay();
            }

            await refreshSessionSummary();
        } catch (e) {
            console.warn("[RaterHubTracker] Failed to sync from backend:", e);
        }
    }

    // -----------------------------------------
    // Auth & event sending
    // -----------------------------------------

    async function fetchCsrfToken() {
        try {
            const res = await fetch(`${API_BASE}/auth/csrf`, {
                method: "GET",
                credentials: "include",
            });
            if (!res.ok) {
                console.error("[RaterHubTracker] Failed to fetch CSRF token:", res.status);
                return null;
            }
            const data = await res.json();
            if (data && typeof data.csrf_token === "string") {
                csrfToken = data.csrf_token;
                return csrfToken;
            }
        } catch (e) {
            console.error("[RaterHubTracker] Error fetching CSRF token:", e);
        }
        return null;
    }

    async function login() {
        try {
            setStatus('Logging in…', '#4b5563');
            let attempt = 0;
            let res;
            while (attempt < 2) {
                if (!csrfToken) {
                    await fetchCsrfToken();
                }
                res = await fetch(`${API_BASE}/auth/login`, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRF-Token": csrfToken || "",
                    },
                    credentials: "include",
                    body: JSON.stringify({
                        email: LOGIN_EMAIL,
                        password: LOGIN_PASSWORD,
                    }),
                });

                if (res.status === 400 && attempt === 0) {
                    console.warn("[RaterHubTracker] CSRF token rejected, refreshing and retrying...");
                    csrfToken = null;
                    attempt += 1;
                    continue;
                }
                break;
            }

            if (!res || !res.ok) {
                const text = res ? await res.text() : 'no response';
                console.error("[RaterHubTracker] Login failed:", res ? res.status : 'n/a', text);
                setStatus(`Login failed (${res ? res.status : 'n/a'})`, '#b91c1c');
                flashWidget('#ef4444');
                return;
            }

            const data = await res.json();
            accessToken = data.access_token;
            updateUserDisplay();
            setStatus('Logged in ✔', '#15803d');
            flashWidget('#22c55e');
            console.log("[RaterHubTracker] Logged in, token acquired.");

            // Now that we have a token, try to sync session summary
            await syncFromBackendOnLogin();
        } catch (err) {
            console.error("[RaterHubTracker] Login error:", err);
            setStatus('Login error', '#b91c1c');
            flashWidget('#ef4444');
        }
    }

    async function sendEvent(type) {
        if (!accessToken) {
            console.warn("[RaterHubTracker] No token yet, attempting login...");
            setStatus('No token – logging in…', '#b45309');
            await login();
            if (!accessToken) {
                console.error("[RaterHubTracker] Still no token, aborting event.");
                setStatus('Event aborted – no token', '#b91c1c');
                return;
            }
        }

        const payload = {
            type: type,
            timestamp: new Date().toISOString(),
        };

        console.log(`[RaterHubTracker] Sending ${type}`, payload);
        setStatus(`Sending ${type}…`, '#4b5563');

        try {
            const res = await fetch(`${API_BASE}/events`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": `Bearer ${accessToken}`,
                },
                body: JSON.stringify(payload),
            });

            if (!res.ok) {
                const text = await res.text();
                console.error("[RaterHubTracker] Event error:", res.status, text);
                setStatus(`Event ${type} failed (${res.status})`, '#b91c1c');
                lastEventEl.textContent = `Last event: ${type} (error ${res.status})`;
                flashWidget('#ef4444');
                if (res.status === 401) {
                    accessToken = null;
                    updateUserDisplay();
                }
                return;
            }

            const data = await res.json();
            console.log("[RaterHubTracker] Event recorded:", data);
            setStatus(`Event ${type} recorded ✔`, '#15803d');
            lastEventEl.textContent = `Last event: ${type} @ ${new Date().toLocaleTimeString()}`;
            flashWidget('#22c55e');

            // Keep a handle on the session from the backend
            if (data && typeof data.session_id === "string") {
                currentSessionId = data.session_id;
            }

            const backendTotal = (data && typeof data.total_questions === "number")
                ? data.total_questions
                : null;

            // Update client-side state based on event type
            if (type === "NEXT") {
                if (backendTotal !== null) {
                    questionIndex = backendTotal;  // number of completed questions
                } else {
                    questionIndex += 1;
                }
                saveState();
                startNewQuestionTimer();
            } else if (type === "PAUSE") {
                togglePauseTimer();
                saveState();
            } else if (type === "EXIT") {
                if (backendTotal !== null) {
                    questionIndex = backendTotal;
                }
                saveState();
                exitTimer();
            } else if (type === "UNDO") {
                if (backendTotal !== null) {
                    questionIndex = backendTotal;
                } else if (questionIndex > 0) {
                    questionIndex -= 1;
                }
                saveState();
                resetTimerForUndo();
            }

            updateQuestionDisplay();

            // After every successful event, refresh session summary (AHT, pace)
            await refreshSessionSummary();
            saveState();
        } catch (err) {
            console.error("[RaterHubTracker] Network error:", err);
            setStatus(`Event ${type} network error`, '#b91c1c');
            lastEventEl.textContent = `Last event: ${type} (network error)`;
            flashWidget('#ef4444');
        }
    }

    // -----------------------------------------
    // Keyboard handling
    // -----------------------------------------

    function handleKeydown(e) {
        const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : "";
        if (tag === "input" || tag === "textarea" || tag === "select" || e.isComposing) {
            return;
        }

        // Ctrl+Q => NEXT
        if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key.toLowerCase() === "q") {
            e.preventDefault();
            sendEvent("NEXT");
            return;
        }

        // Ctrl+Shift+P => PAUSE/RESUME
        if (e.ctrlKey && e.shiftKey && !e.altKey && e.key.toLowerCase() === "p") {
            e.preventDefault();
            sendEvent("PAUSE");
            return;
        }

        // Ctrl+Shift+X => EXIT
        if (e.ctrlKey && e.shiftKey && !e.altKey && e.key.toLowerCase() === "x") {
            e.preventDefault();
            sendEvent("EXIT");
            return;
        }

        // Ctrl+Shift+Q => UNDO
        if (e.ctrlKey && e.shiftKey && !e.altKey && e.key.toLowerCase() === "q") {
            e.preventDefault();
            sendEvent("UNDO");
            return;
        }
    }

    // -----------------------------------------
    // Init
    // -----------------------------------------

    createWidget();
    loadState();
    updateQuestionDisplay();
    updateTimerDisplay();
    updateUserDisplay();
    setStatus('Loaded – logging in…', '#4b5563');
    updateSessionStatsText('Session: –');

    window.addEventListener("keydown", handleKeydown, true);
    console.log("[RaterHubTracker] Userscript loaded. Will log in as", LOGIN_EMAIL);

    // Kick off login immediately
    login();
}, false);
