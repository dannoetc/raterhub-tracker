# RaterHub Tracker

RaterHub Tracker is a FastAPI application for session-based productivity tracking. It records event streams from a JavaScript widget (NEXT, PAUSE, UNDO, EXIT), aggregates timing per question and per day, and secures access with JWT authentication and CSRF protection.

## What you get
- FastAPI backend with JWT auth, CSRF, and rate limits
- Event-driven model that enforces valid session/question flows
- Per-session and per-day dashboards (HTML + JSON) with pacing scores
- Simple Jinja2 HTML flows plus a TamperMonkey-friendly widget
- SQLite by default, PostgreSQL recommended for production

## Quickstart
```bash
cd app
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
# Supply environment variables (see below), then run:
uvicorn main:app --reload
```

Or run everything via Docker Compose:
```bash
docker-compose up --build
```

## Configuration highlights
Set these environment variables (or add them to `.env`):
- `SECRET_KEY` (required): signs JWTs and CSRF HMACs; app exits if missing.
- `ACCESS_TOKEN_EXPIRE_MINUTES` (default `1440`): token lifetime.
- `DATABASE_URL` (default `sqlite:///./app.db`): SQLAlchemy connection string.
- `SESSION_COOKIE_SECURE` (default `True` unless `DEBUG=true`): `Secure` flag on cookies.
- `ALLOWED_ORIGINS`: comma-separated CORS whitelist for the widget and HTML flows.

## Architecture at a glance
- **Entrypoint:** `app/main.py` wires FastAPI, middleware, rate limiting, CSRF helpers, and routes.
- **Auth:** JWT bearer tokens issued in `app/auth.py`, accepted via header or `access_token` cookie.
- **Persistence:** SQLAlchemy models in `app/db_models.py`; session factory in `app/database.py`.
- **Schemas:** Request/response shapes live in `app/models.py`.

## Event flow (widget → backend)
- Events POST to `/events` with `NEXT`, `PAUSE`, `UNDO`, or `EXIT` plus a timestamp.
- `NEXT` starts sessions and advances questions; `EXIT` ends the session.
- `PAUSE` toggles paused state and accumulates paused time; `UNDO` rewinds the last question.

## Key endpoints
- Health: `GET /health`
- Auth: `GET /auth/csrf`, `POST /auth/register`, `POST /auth/login`, `GET /me`
- Sessions & events: `POST /events`, `GET /summary/{session_id}`, `DELETE /sessions/{session_id}`, `DELETE /sessions/{session_id}/questions/{question_id}`
- Dashboards: `GET /dashboard/today` (HTML) and `/dashboard/today/json`
- Profile: `GET/POST /profile`

## Dashboards & pacing
Session summaries show per-question durations (raw vs. active) and pacing feedback. Daily dashboards bucket activity by hour and compute weighted pacing across sessions; target pace defaults to 5.5 minutes per question unless overridden per session.

## Security & operations
- Passwords must meet a 12-character mixed-case/digit/symbol policy and avoid recent reuse.
- CSRF tokens are required for login/registration and are issued via `GET /auth/csrf` (cookie + header/form echo).
- SlowAPI rate limits protect auth and event ingestion; login throttling tracks per-account and per-IP failures.
- Tables auto-create on startup via SQLAlchemy metadata; persist volumes in Docker deployments.

## More documentation
See `documentation.md` for the full guide covering architecture, security posture, dashboards, and operational tips. OpenAPI docs are available at `/docs` when the server is running.

## License

MIT License. See `LICENSE` for details.

