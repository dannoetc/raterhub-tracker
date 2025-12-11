# RaterHub Tracker Documentation

## Overview
RaterHub Tracker is a FastAPI application for session-based productivity tracking, originally aimed at RaterHub workflows. It records timing events from a JavaScript widget, aggregates the data into per-session and per-day dashboards, and secures access with JWT authentication.

## Quickstart
1. **Create environment file**
   ```bash
   cp .env.example .env  # if available; otherwise export variables directly
   ```
2. **Install dependencies and run locally**
   ```bash
   cd app
   python -m venv .venv
   source .venv/bin/activate
   pip install -r ../requirements.txt
   uvicorn main:app --reload
   ```
3. **Docker Compose**
   ```bash
   docker-compose up --build
   ```

## Configuration
Key environment variables are read in `app/config.py`:

- `SECRET_KEY` (**required**): used for signing JWTs and CSRF HMACs; the app will raise at startup if missing.
- `ACCESS_TOKEN_EXPIRE_MINUTES` (default `1440`): JWT lifetime.
- `DATABASE_URL` (default `sqlite:///./app.db`): SQLAlchemy connection string.
- `SESSION_COOKIE_SECURE` (default `True` unless `DEBUG=true`): controls the `Secure` flag on cookies.
- `ALLOWED_ORIGINS`: comma-separated CORS whitelist; defaults include `raterhub.com` and the hosted API domains.

Templates live in `app/templates/`. Static assets are served directly from templates (no build step).

## Architecture
- **App entrypoint:** `app/main.py` wires the FastAPI app, middleware, rate limiting, CSRF helpers, and route handlers.
- **Authentication:** JWT bearer tokens created in `app/auth.py` and accepted via `Authorization: Bearer` headers or the `access_token` cookie. CSRF tokens are required for login and registration requests.
- **Persistence:** SQLAlchemy models in `app/db_models.py` store users, sessions, events, questions, password history, and login throttling records. The engine and session factory are configured in `app/database.py`.
- **Pydantic schemas:** `app/models.py` defines request/response shapes for events, summaries, tokens, and user forms.

## Data Model
- **User:** email-based identity with `password_hash`, `is_active`, and `timezone` fields. Related to sessions and password history.
- **Session:** per-user timer run, with pause tracking (`pause_accumulated_seconds`, `is_paused`, `pause_started_at`), current question pointer, and a per-question target pace.
- **Event:** raw timeline of `NEXT`, `PAUSE`, `UNDO`, `EXIT` actions.
- **Question:** derived durations per question with both raw and active seconds (raw minus pauses).
- **PasswordHistory:** keeps historical password hashes to block recent reuse.
- **LoginAttempt:** tracks per-account and per-IP failures for lockout/backoff logic.

## Authentication & Security
- **Password policy:** minimum 12 characters with mixed case, digits, and symbols; optional Have I Been Pwned range checks; offline weak-password blocklist; prevents reuse of recent hashes.
- **CSRF:** `GET /auth/csrf` issues an HMAC-protected token stored as an HTTP-only cookie and echoed in the `x-csrf-token` header/form fields for login/registration.
- **Rate limiting:** SlowAPI enforces limits on authentication and event ingestion (e.g., `/auth/login` is `5/minute`, `/events` is `15/minute`).
- **Login throttling:** per-account and per-IP backoff with lockouts after repeated failures (threshold 5, 15-minute lockout, escalating cooldowns after three failures).
- **JWT storage:** accepted from either bearer header or `access_token` cookie. Auth-required routes reject missing/invalid/disabled users.

## Event Flow (widget → backend)
Events are posted to `POST /events` with shape:
```json
{
  "type": "NEXT" | "PAUSE" | "UNDO" | "EXIT",
  "timestamp": "2024-01-01T12:00:00Z"
}
```
Behavior highlights:
- **Session creation:** only `NEXT` can start a new session. Other event types require an active session and return `400` otherwise.
- **PAUSE:** toggles paused state; when resuming, paused duration is accumulated.
- **NEXT/EXIT:** closes the current question, storing raw and active seconds; `EXIT` also ends the session, while `NEXT` advances the question index and resets pause counters.
- **UNDO:** removes the most recent question, rewinds current question pointer, and restores pause counters based on the removed record.
- Responses include the session public ID, total questions, and last question timing in both seconds and `MM:SS` format.

## Key API Endpoints
- `GET /health` — simple liveness probe.
- `GET /auth/csrf` — issues CSRF token + cookie.
- `POST /auth/register` — create user, enforcing password policy and saving password history.
- `POST /auth/login` — login with CSRF + rate limiting + throttling; returns JWT.
- `GET /me` — current-user profile (requires auth).
- `GET /sessions/recent` — last N sessions for the user.
- `POST /events` — ingest tracker events (auth + rate limited).
- `GET /summary/{session_id}` — JSON summary for a session, excluding ghost placeholder questions.
- `DELETE /sessions/{session_id}` — delete a session (API and HTML form variants).
- `DELETE /sessions/{session_id}/questions/{question_id}` — delete an individual question.
- `GET /dashboard/today` — HTML dashboard for a day (defaults to today in user timezone).
- `GET /dashboard/today/json` — JSON summary for the selected day (hourly buckets, pace scores).
- `GET /profile` / `POST /profile` — view/update timezone.
- Admin/debug helpers: `GET /admin/debug/user-sessions`, `GET /admin/debug/user-events/{session_id}`, `GET /admin/dashboard` (all scoped to the authenticated user).

## Dashboards & Summaries
- **Session summary:** `GET /summary/{session_id}` aggregates per-question pacing, totals, averages, and renders HH:MM/MM:SS strings. Ghost zero-length placeholder questions are filtered out.
- **Daily summary:** `GET /dashboard/today` and `/dashboard/today/json` compute per-session stats, weighted daily pace, and hourly activity buckets (24 hours). Target pace per question defaults to 5.5 minutes but uses the session’s stored target when present.

## Running Notes
- Tables are created automatically at startup via `Base.metadata.create_all` in `app/main.py`; no separate migrations are shipped.
- Default database is SQLite for quick local runs; supply a PostgreSQL URL for production.
- CORS allows the configured origins for the browser widget. Cookies set by the HTML flows use `SameSite=None` to support cross-site TamperMonkey scripts.
- HTML templates include login/register forms, a simple dashboard, and a profile page; `/docs` exposes FastAPI’s OpenAPI UI for ad-hoc inspection.

## Operational Tips
- Rotate `SECRET_KEY` cautiously—existing JWT cookies will become invalid immediately.
- If running behind HTTPS, keep `SESSION_COOKIE_SECURE=true` to prevent cookie leakage; set `ALLOWED_ORIGINS` to match the public domains hosting the widget and API.
- For Docker deployments, ensure the database volume is persisted and set the timezone on user profiles to align reports with local midnight boundaries.
