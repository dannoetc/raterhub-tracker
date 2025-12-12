# 💜 RaterHub Tracker

RaterHub Tracker is a lightweight, privacy-conscious time tracker designed specifically for Raters working on [RaterHub.com](https://www.raterhub.com). It helps track question timing and session activity using a browser widget and a FastAPI backend, with a lightweight browser extension working things in the frontend! 

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
- **Frontend**: Browser Extension (code in /extension) + Jinja2 HTML templates
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

### CSV export smoke test (manual)

You can quickly verify the CSV endpoints by running a short local smoke test:

1. In one terminal, start the API with temporary settings:

   ```bash
   cd /workspace/personal
   SECRET_KEY=devkey DEBUG=true uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. In a second terminal, seed a throwaway user and get a JWT token:

   ```bash
   SECRET_KEY=devkey python - <<'PY'
from datetime import datetime
from app.auth import create_access_token, get_password_hash
from app.database import SessionLocal
from app.db_models import PasswordHistory, User

db = SessionLocal()
email = "smoke@example.com"
user = db.query(User).filter_by(email=email).first()
if not user:
    now = datetime.utcnow()
    user = User(
        external_id=email,
        email=email,
        first_name="Smoke",
        last_name="Test",
        created_at=now,
        last_login_at=now,
        password_hash=get_password_hash("password123!"),
        auth_provider="local",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.add(PasswordHistory(user_id=user.id, password_hash=user.password_hash))
    db.commit()

print("JWT=" + create_access_token(user=user))
db.close()
PY
   ```

   Copy the printed `JWT` value for the next steps.

3. Post a few events for today using that token (this example records a two-question session):

   ```bash
   python - <<'PY'
import requests, time
from datetime import datetime

TOKEN = "<paste JWT here>"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def send(event_type: str):
    resp = requests.post(
        "http://127.0.0.1:8000/events",
        json={"type": event_type, "timestamp": datetime.utcnow().isoformat() + "Z"},
        headers=HEADERS,
    )
    print(event_type, resp.status_code, resp.text)
    resp.raise_for_status()

send("NEXT")
time.sleep(1)
send("NEXT")
time.sleep(1)
send("EXIT")
PY
   ```

4. Download CSV exports to verify responses (replace the dates if you run on a different day):

   ```bash
   TOKEN="<paste JWT here>"
   curl -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:8000/reports/daily.csv?date=$(date -I)"
   curl -H "Authorization: Bearer ${TOKEN}" "http://127.0.0.1:8000/reports/weekly.csv?week_start=$(date -I -d 'monday this week')"
   ```

5. Stop the uvicorn process with `Ctrl+C` when finished.

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

### Database migrations for email features

If you are upgrading an existing deployment, run the lightweight migration to
add the email-related audit table and user preference columns:

```bash
SECRET_KEY=... DATABASE_URL=... python scripts/add_report_email_tables.py
```

The script is idempotent and can be re-run safely; it only creates the
`report_audit_logs` table and missing `users.timezone`/`users.wants_report_emails`
columns when they are absent.

### PDF rendering options

PDF exports prefer WeasyPrint for full HTML rendering. If you see raw HTML or CSS
in the generated PDF, install WeasyPrint's system dependencies so the renderer
can load fonts and CSS correctly (Debian/Ubuntu example):

```bash
apt-get update && apt-get install -y libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 shared-mime-info
```

When those libraries are unavailable, the service falls back to a text-only PDF
that strips tags and styling. If you need pixel-perfect HTML output in a
minimal environment, you can also replace the `_weasyprint_render` helper in
`app/services/report_exports.py` with a `wkhtmltopdf` or headless-Chromium
command that writes PDF bytes to stdout—the rest of the code simply expects the
rendered bytes.

---

## 🔐 Environment Configuration (`.env`)

```env
SECRET_KEY=your-super-secret-key
DATABASE_URL=postgresql+psycopg2://raterhub:super-secret@localhost:5432/raterhub
ACCESS_TOKEN_EXPIRE_MINUTES=1440
ALLOWED_ORIGINS=https://raterhub.com,https://api.raterhub.com
DEBUG=false
EMAIL_SENDING_ENABLED=false
EMAIL_SMTP_HOST=smtp.yourmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=mailer
EMAIL_SMTP_PASSWORD=super-secret
EMAIL_FROM_ADDRESS=reports@example.com
```

To deliver daily report emails at the start of each user's local day, schedule
the cron-friendly task to run hourly:

```bash
python -m app.scripts.deliver_reports
```

When `EMAIL_SENDING_ENABLED` is `true`, active users who opt in from their
profile will receive the previous day's PDF and CSV exports. Audit entries are
recorded for each delivery attempt.

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
