# RaterHub Tracker extension

## Message schema

Content and background scripts exchange timestamped envelopes shaped as:

```json
{
  "type": "<MESSAGE_TYPES value>",
  "timestamp": 1700000000000,
  "eventType": "NEXT",
  "sessionId": "abc123",
  "questionIndex": 4,
  "summary": { /* optional session summary */ },
  "totalQuestions": 4
}
```

Key message types:

- `SEND_EVENT`: content → background control events (`NEXT`, `PAUSE`, `EXIT`, `UNDO`). Responses include the updated `sessionId`, optional `totalQuestions`, and a `summary` when available.
- `SESSION_SUMMARY`: content → background explicit summary fetch for a given `sessionId`; response mirrors the envelope with the summary payload.
- `SESSION_SUMMARY_RELAY`: background → content push used after tab reload/navigation or scheduled refreshes. Carries `summary`, `sessionId`, and `totalQuestions` to hydrate the overlay.
- `FIND_ACTIVE_SESSION`: content → background lookup of the most recent active session so the overlay can reattach.
- `LOGIN`/`RESET_WIDGET_STATE`: auth plumbing; logout broadcasts a reset envelope to all tracker tabs.

Every envelope is timestamped so the receiver can ignore stale updates if needed.

## State fields

The content script owns transient UI/session state and persists the following keys via `chrome.storage.local`:

- `questionIndex`: zero-based index for the current question.
- `currentSessionId`: session identifier used for future API calls.
- `isCollapsed`: overlay collapsed/expanded toggle.
- `accumulatedActiveMs`: milliseconds of active time before the current timer leg.
- `questionStartTime`: epoch milliseconds when the timer last resumed (used to restore after reload).
- `isPaused`: whether the timer is paused.
- `lastSummary`: cached session summary from the background for quick restoration.
- Position is separately tracked by `raterhubTrackerPos_v2` to keep the widget anchored between navigations.

When a tab reloads, the content script restores timer/session state from storage, rehydrates the timer, and requests the latest session summary from the background so the overlay remains in sync.
