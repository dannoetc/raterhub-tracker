# RaterHub Tracker

RaterHub Tracker is a self-hosted, open-source productivity monitoring tool built to help users track session-based task completion time. Originally designed for workers using the RaterHub platform, it allows for detailed timing analysis of tasks and offers a JS powered overlay while you rate. 

## ✨ Features

- FastAPI-powered web backend
- Intuitive JavaScript-based widget for tracking your progress as you rate
- User authentication and session management
- Event-driven model with NEXT / PAUSE / EXIT / UNDO
- Per-session and per-day dashboards with visual summaries
- Intelligent pacing feedback with emoji-based scoring
- Lightweight HTML UI using Jinja2 templates
- PostgreSQL or SQLite database support
- Timezone-aware reporting and filtering
- Rate limiting and registration hardening

## 🚀 Goals

- Offer a private, transparent alternative to proprietary productivity tracking tools
- Enable RaterHub users and similar contractors to maintain their own logs
- Provide accurate time tracking for sessions and questions/tasks
- Facilitate self-assessment and pacing improvements
- Allow open-source contributions and customization for local or cloud hosting

## ⚙️ Tech Stack

- **Backend:** Python 3.10+, FastAPI, SQLAlchemy
- **Frontend:** Jinja2 templating (simple HTML forms and dashboards)
- **Auth:** JWT with secure cookie fallback
- **Rate limiting:** SlowAPI (Redis optional)
- **Database:** PostgreSQL (production) or SQLite (dev/testing)

## 🔧 Installation

### Prerequisites:

#### Backend 
- Python 3.10+
- PostgreSQL database (or use SQLite for quick testing)
#### Frontend 
- Chromium based browser (Edge/Chrome) 
- TamperMonkey browser addon
- **Developer mode** turned on

### Setup (local/dev):

```bash
git clone https://github.com/dannoetc/personal/raterhub-tracker/raterhub-tracker.git
cd raterhub-tracker/app
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit your .env with DB creds and secret keys
uvicorn main:app --reload
```

### Docker Compose (production or quick deploy):

A `docker-compose.yml` file is provided for containerized deployments. It includes:
- FastAPI backend
- PostgreSQL database
- Optional Redis for advanced rate limiting

```bash
docker-compose up --build
```

## 📄 .env Configuration

Your `.env` file should define values like:

```env
SECRET_KEY=your-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=1440
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/raterhub
ALLOWED_ORIGINS=https://raterhub.com,https://www.raterhub.com
```

## ⚖️ Security Notes

- Passwords are hashed with bcrypt
- JWT access tokens are short-lived and stored via secure HTTP-only cookies
- Session creation is restricted to valid "NEXT" events only
- Rate limits are enforced on `/login`, `/register`, and `/events`
- Sensitive routes require authentication and user ownership checks

## 📃 Documentation

You can visit `/docs` when running locally to access the FastAPI auto-generated API docs.

## 📃 TODO: Production Hardening & Cleanup

The following items remain before the application is considered production-ready and stable for self-hosting or open-source distribution:

### ✅ Completed
- [x] Environment-based config externalized via `config.py` and `.env`
- [x] Secure password hashing (bcrypt via `passlib`)
- [x] JWT-based auth with configurable expiry
- [x] UI widget (TamperMonkey) with backend session sync and active timers
- [x] Rate limiting via `slowapi`
- [x] Dockerfile and Docker Compose for self-contained deployment
- [x] Per-user timezone support
- [x] Session and question deletion
- [x] Session locking to prevent invalid sequences
- [x] RESTful API and HTML dashboard views
- [x] Complete pinned `requirements.txt`

### 🔒 Security & Access Control
- [ ] Add email verification for registration flow
- [ ] Prevent reuse of known weak passwords
- [ ] Add optional admin-only registration or invite-only flag
- [ ] Implement brute-force protection beyond rate limiting (e.g. exponential backoff)
- [ ] Sanitize and validate user input more rigorously

### 📈 Observability
- [ ] Add logging (file + console, configurable level via env)
- [ ] Add healthcheck endpoint for container orchestrators
- [ ] Add metrics or Prometheus-compatible exporter for event tracking

### 🧪 Testing & QA
- [ ] Add unit tests for auth, event handling, and DB logic
- [ ] Add a minimal integration test script (pytest + HTTPX)
- [ ] Add a test harness for widget → backend interaction

### 💅 UX Polish
- [ ] Add password reset flow (via email or temporary token)
- [ ] Add profile settings for AHT customization per user
- [ ] Localize time and duration display in the widget more clearly
- [ ] Improve error display in HTML login/register forms

### 🔧 Deployment & Tooling
- [ ] Add `.dockerignore`
- [ ] Add sample `nginx` config for SSL proxying
- [ ] Add Makefile for setup/dev/test helpers
- [ ] Add GitHub Actions CI for linting/tests

### 📚 Documentation
- [ ] Add full setup guide to `README.md` (Quickstart, .env, Docker)
- [ ] Add API docs (OpenAPI is available, but summarize common endpoints)
- [ ] Add user guide for widget usage and keyboard shortcuts
- [ ] Add admin guide for self-hosted environments

## 🌟 Contributing

This project is open to community contributions. Suggestions, issues, and PRs are welcome.

## ✅ License

MIT License. See `LICENSE` for details.

---

Maintained by Dan Nelson. Originally built for RaterHub power users.

