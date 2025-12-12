# 💜 RaterHub Tracker

RaterHub Tracker is a lightweight, privacy-conscious time tracker designed specifically for Raters working on [RaterHub.com](https://www.raterhub.com). It helps track question timing and session activity using a browser widget and a FastAPI backend — no browser extensions or third-party logins required.

---

## 🚀 What It Does

- ⏱️ Tracks NEXT / PAUSE / EXIT / UNDO events using hotkeys or clicks
- 📊 Computes active and raw question time, session pace, and day totals
- 🔐 Authenticates with JWT tokens, password auth, and CSRF protection
- 📈 Offers dashboards for each session and day, with visual pacing feedback
- 🌐 Works via a self-hosted API + TamperMonkey (or local) widget

---

## 🧰 Tech Stack

- **Backend**: FastAPI + SQLAlchemy + PostgreSQL (or SQLite)
- **Auth**: JWT Bearer tokens, CSRF, optional rate limiting (SlowAPI)
- **Frontend**: TamperMonkey widget + Jinja2 HTML templates
- **Packaging**: Docker, `.env` support, Makefile for quick builds

---

## ⚙️ Quickstart (Local)

```bash
cd app
python -m venv .venv
source .venv/bin/activate
pip install -r ../requirements.txt
uvicorn main:app --reload
```

### Or with Docker:

```bash
docker build -t raterhub-tracker .
docker run --rm -p 8000:8000 --env-file .env raterhub-tracker
```

### Docker Compose (with optional nginx reverse proxy)

```bash
docker compose up --build           # FastAPI available on :8000
docker compose --profile nginx up   # Adds nginx reverse proxy on :80
```

nginx proxies requests to the `web` container and forwards headers for correct
client IP reporting. Its configuration lives in `nginx/default.conf` and is
mounted read-only when the profile is enabled.

### Manual setup (no Docker)

If you prefer to run everything directly on your host:

```bash
bash scripts/manual_setup.sh
```

The script creates a virtual environment under `app/.venv`, installs
dependencies, and writes a baseline `.env` if one is missing. Afterwards, run
the server from the `app/` directory with:

```bash
source app/.venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 🔐 Environment Configuration (`.env`)

```env
SECRET_KEY=your-super-secret-key
DATABASE_URL=postgresql+psycopg2://raterhub:super-secret@localhost:5432/raterhub
ACCESS_TOKEN_EXPIRE_MINUTES=1440
ALLOWED_ORIGINS=https://raterhub.com,https://api.raterhub.com
DEBUG=false
```

---

## 🔁 Event Lifecycle

Each key press (or button) sends an event:

- `NEXT`: Starts a session and progresses the question counter
- `PAUSE`: Toggles pause/resume state
- `UNDO`: Removes the last question
- `EXIT`: Closes the current session

The backend computes timing stats per question and persists each session.

---

## 📺 Dashboards

- `/dashboard/today` — View today’s sessions, timing, pace emojis, and scores
- `/dashboard/sessions/<id>` — Inspect each question inside a session
- `/profile` — Manage personal details, timezone, and password

---

## 🔑 Authentication

- `/login` and `/register`: HTML-based login
- `/auth/login` and `/auth/register`: API-style login (used by the widget)
- `GET /me`: Verify session/token
- JWT token stored in secure cookie + optional Authorization header

---

## 🔒 Security Posture

- Rate limits for login, registration, and event ingestion
- CSRF tokens for login/registration flows
- Passwords hashed with bcrypt
- Sessions cannot be created by non-NEXT events

---

## 🗄️ Database migration for name fields

If you're upgrading an existing deployment, run the helper script to add the
`first_name` and `last_name` columns to the `users` table (safe to re-run):

```bash
SECRET_KEY=your-secret DATABASE_URL=postgresql+psycopg2://... \\
    python scripts/add_user_name_columns.py
```

---

## 🛠️ Admin Tools

- `/admin/debug/user-sessions`: View session metadata
- `/admin/debug/user-events/<id>`: View raw event timeline

---

## 🧪 Still To Do

- [ ] Email verification & stronger password policy
- [ ] Optional email/password login toggle
- [ ] Widget UI toggle between compact and expanded states
- [ ] Timezone auto-detection (fallback)
- [ ] Export session data to CSV
- [ ] Multitenancy / team support
- [ ] More robust test coverage

---

## 📄 License

MIT License. Open source, self-hostable, and free to use. See `LICENSE`.

---
Made with 💜 by [Melissa Steigenga](https://raterhub.steigenga.com)
