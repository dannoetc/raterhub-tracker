from datetime import datetime, timedelta, timezone
from typing import Optional, List
from zoneinfo import ZoneInfo

from fastapi import (
    FastAPI,
    Depends,
    HTTPException,
    Request,
    Form,
    Cookie,
    Query,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from sqlalchemy.orm import Session as OrmSession

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .database import SessionLocal, engine
from .db_models import Base, User, Session as DbSession, Event, Question
from .models import (
    EventIn,
    EventOut,
    HealthStatus,
    SessionSummary,
    SessionQuestionSummary,
    TodaySummary,
    TodaySessionItem,
    UserCreate,
    UserLogin,
    Token,
)
from .auth import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)
from .config import settings

# ============================================================
# FastAPI initialization
# ============================================================

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend for timing and scoring RaterHub rating sessions.",
    version=settings.VERSION,
)

Base.metadata.create_all(bind=engine)

templates = Jinja2Templates(directory=settings.TEMPLATES_DIR)

# CORS – allow your UI/API and RaterHub origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiter (per client IP)
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

security = HTTPBearer(auto_error=False)  # allow missing header, fallback to cookie

# ============================================================
# DB dependency
# ============================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================
# Utility helpers
# ============================================================

def format_mmss(seconds: float) -> str:
    if seconds is None:
        return ""
    if seconds < 0:
        seconds = 0
    minutes = int(seconds // 60)
    secs = int(round(seconds - minutes * 60))
    return f"{minutes:02d}:{secs:02d}"


def format_hhmm_or_mmss_for_dashboard(seconds: float) -> str:
    """
    For dashboard totals/averages:
    - Under 60 minutes => MM:SS
    - 60 minutes or more => HH:MM (no seconds, like a workday timer)
    """
    if seconds is None:
        return ""
    if seconds < 0:
        seconds = 0

    total_minutes = int(seconds // 60)
    secs = int(round(seconds - total_minutes * 60))

    if total_minutes < 60:
        # show MM:SS
        return f"{total_minutes:02d}:{secs:02d}"
    else:
        hours = total_minutes // 60
        minutes = total_minutes % 60
        # show HH:MM
        return f"{hours:02d}:{minutes:02d}"


def compute_pace(avg_seconds: float, target_minutes: float):
    """
    Compute pace label/emoji/score based on average time vs target.
    """
    target_seconds = target_minutes * 60
    if avg_seconds <= 0 or target_seconds <= 0:
        return {
            "pace_label": "No questions",
            "pace_emoji": "😴",
            "score": 0,
            "ratio": 0.0,
        }

    ratio = avg_seconds / target_seconds

    if ratio < 0.5:
        pace_label, pace_emoji = "way too fast (<50%)", "⚡🐇"
    elif ratio < 0.7:
        pace_label, pace_emoji = "fast (50–70%)", "🐇"
    elif ratio < 0.9:
        pace_label, pace_emoji = "slightly fast", "🙂"
    elif ratio < 1.1:
        pace_label, pace_emoji = "on target", "💜✅"
    elif ratio < 1.3:
        pace_label, pace_emoji = "a bit slow", "🐢"
    else:
        pace_label, pace_emoji = "slow", "🐌"

    import math
    score = round(max(0, min(100, 100 * math.exp(-1.2 * abs(ratio - 1)))))

    return {
        "pace_label": pace_label,
        "pace_emoji": pace_emoji,
        "score": score,
        "ratio": ratio,
    }


def is_ghost_question(q: Question) -> bool:
    """
    Ghost questions = the zero-length placeholders we want to hide from reports:
    - index == 1
    - raw_seconds == 0
    - active_seconds == 0
    - started_at == ended_at
    """
    return (
        q.index == 1
        and (q.raw_seconds or 0.0) == 0.0
        and (q.active_seconds or 0.0) == 0.0
        and q.started_at == q.ended_at
    )


def get_user_tz(user: User) -> ZoneInfo:
    """
    Return the user's configured timezone (IANA name) or UTC.
    Assumes User has a .timezone string column.
    """
    tzname = getattr(user, "timezone", None) or "UTC"
    try:
        return ZoneInfo(tzname)
    except Exception:
        return ZoneInfo("UTC")


def to_user_local(dt: Optional[datetime], user: User) -> Optional[datetime]:
    if dt is None:
        return None
    tz = get_user_tz(user)
    # DB timestamps are naive UTC
    if dt.tzinfo is None:
        dt_utc = dt.replace(tzinfo=timezone.utc)
    else:
        dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.astimezone(tz)

# ============================================================
# Auth: current user via header or cookie
# ============================================================

def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    access_token: Optional[str] = Cookie(default=None),
    db: OrmSession = Depends(get_db),
) -> User:
    token = None

    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
    elif access_token:
        token = access_token

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid token")

    user_id = int(payload.get("sub"))
    email = payload.get("email")

    user = db.query(User).filter(User.id == user_id, User.email == email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user

# ============================================================
# Root & health
# ============================================================

@app.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    return HealthStatus(status="ok", timestamp=datetime.utcnow())


@app.get("/", response_class=HTMLResponse)
def root(
    request: Request,
    access_token: Optional[str] = Cookie(default=None),
):
    """
    Smart landing:
    - If user has a valid JWT cookie → /dashboard/today
    - Otherwise → /login
    """
    if access_token:
        payload = decode_access_token(access_token)
        if payload is not None:
            return RedirectResponse(url="/dashboard/today", status_code=303)
    return RedirectResponse(url="/login", status_code=303)

# ============================================================
# Auth endpoints (API-style)
# ============================================================

@limiter.limit("3/minute")
@app.post("/auth/register", response_model=Token)
def register_api(
    request: Request, user_in: UserCreate, db: OrmSession = Depends(get_db)
):
    exists = db.query(User).filter(User.email == user_in.email).first()
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")

    now = datetime.utcnow()
    user = User(
        external_id=user_in.email,
        email=user_in.email,
        created_at=now,
        last_login_at=now,
        password_hash=get_password_hash(user_in.password),
        auth_provider="local",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user=user)
    return Token(access_token=token)

@limiter.limit("5/minute")
@app.post("/auth/login", response_model=Token)
def login_api(request: Request, user_in: UserLogin, db: OrmSession = Depends(get_db)):
    user = db.query(User).filter(User.email == user_in.email).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(user_in.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user.last_login_at = datetime.utcnow()
    db.commit()

    token = create_access_token(user=user)
    return Token(access_token=token)

# ============================================================
# HTML login / logout / register (browser flow)
# ============================================================

@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
def login_web(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: OrmSession = Depends(get_db),
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.password_hash or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid email or password", "email": email},
            status_code=400,
        )

    token = create_access_token(user=user)

    response = RedirectResponse(url="/dashboard/today", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=60 * 60 * 24,
    )
    return response


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    """
    Show a simple registration form for creating a local account.
    """
    return templates.TemplateResponse(
        "register.html",
        {"request": request},
    )


@app.post("/register")
def register_web(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: OrmSession = Depends(get_db),
):
    """
    Handle registration via HTML form:
    - Validates passwords match
    - Ensures email is not already registered
    - Creates user, logs them in, sets cookie
    """
    if password != password_confirm:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "Passwords do not match.",
                "email": email,
            },
            status_code=400,
        )

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return templates.TemplateResponse(
            "register.html",
            {
                "request": request,
                "error": "That email is already registered.",
                "email": email,
            },
            status_code=400,
        )

    now = datetime.utcnow()
    user = User(
        external_id=email,
        email=email,
        created_at=now,
        last_login_at=now,
        password_hash=get_password_hash(password),
        auth_provider="local",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user=user)

    response = RedirectResponse(url="/dashboard/today", status_code=303)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=60 * 60 * 24,
    )
    return response


@app.get("/logout")
def logout(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(
        key="access_token",
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )
    return response


@app.post("/logout")
def logout_post(request: Request):
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(
        key="access_token",
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
    )
    return response

# ============================================================
# /me and helper endpoints
# ============================================================

@app.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "external_id": current_user.external_id,
        "created_at": current_user.created_at,
        "last_login_at": current_user.last_login_at,
        "is_active": current_user.is_active,
        "timezone": getattr(current_user, "timezone", None),
    }


@app.get("/sessions/recent")
def recent_sessions(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100

    sessions = (
        db.query(DbSession)
        .filter(DbSession.user_id == current_user.id)
        .order_by(DbSession.started_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "session_id": s.public_id,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
            "is_active": s.is_active,
            "current_question_index": s.current_question_index,
        }
        for s in sessions
    ]

# ============================================================
# Event ingestion (/events) – NEXT / PAUSE / EXIT / UNDO
# ============================================================

# Probably enough events in a minute. Maybe. 

@limiter.limit("15/minute")
@app.post("/events", response_model=EventOut)
def post_event(
    request: Request,
    event: EventIn,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
) -> EventOut:
    """
    Receive a NEXT/PAUSE/EXIT/UNDO event and update:
    - User's active session
    - Events table
    - Questions table (for NEXT/EXIT)
    - Session state (UNDO rolls back last question)

    IMPORTANT:
    - Only NEXT is allowed to *start* a new session.
    - PAUSE / EXIT / UNDO require an existing active session.
    """
    now = datetime.utcnow()
    ts = event.timestamp

    # Normalize client timestamp to naive UTC
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)

    user = current_user

    # Ensure user timestamps are sane
    if not user.created_at:
        user.created_at = now
    user.last_login_at = now
    db.commit()

    # Find active session for this user (if any)
    session = (
        db.query(DbSession)
        .filter(DbSession.user_id == user.id, DbSession.is_active == True)
        .order_by(DbSession.started_at.desc())
        .first()
    )

    # 🔒 NEW BEHAVIOR: Only NEXT can start a session
    if session is None:
        if event.type != "NEXT":
            # No active session and event is PAUSE/EXIT/UNDO → reject
            raise HTTPException(
                status_code=400,
                detail="No active session. Press NEXT to start a session before sending "
                       f"{event.type} events.",
            )

        # Create a new session for FIRST NEXT
        session = DbSession(
            user_id=user.id,
            started_at=ts,
            is_active=True,
            target_minutes_per_question=5.5,
            current_question_index=1,
            current_question_started_at=ts,
            pause_accumulated_seconds=0.0,
            is_paused=False,
            pause_started_at=None,
        )
        db.add(session)
        db.commit()
        db.refresh(session)

    # At this point we are guaranteed to have a session
    # Record the event itself
    db.add(Event(session_id=session.id, type=event.type, timestamp=ts))

    last_q_active: Optional[float] = None
    last_q_raw: Optional[float] = None

    # ----- PAUSE -----
    if event.type == "PAUSE":
        if not session.is_paused:
            # running -> paused
            session.is_paused = True
            session.pause_started_at = ts
        else:
            # paused -> running (accumulate pause)
            if session.pause_started_at is not None:
                delta = (ts - session.pause_started_at).total_seconds()
                if delta > 0:
                    session.pause_accumulated_seconds += delta
            session.is_paused = False
            session.pause_started_at = None

    # ----- UNDO -----
    elif event.type == "UNDO":
        # Undo the last closed question for this session
        last_q = (
            db.query(Question)
            .filter(Question.session_id == session.id)
            .order_by(Question.index.desc())
            .first()
        )

        if last_q is not None:
            old_pause = (last_q.raw_seconds or 0.0) - (last_q.active_seconds or 0.0)
            if old_pause < 0:
                old_pause = 0.0

            session.current_question_index = last_q.index
            session.current_question_started_at = last_q.started_at
            session.pause_accumulated_seconds = old_pause
            session.is_paused = False
            session.pause_started_at = None

            db.delete(last_q)

    # ----- NEXT / EXIT -----
    elif event.type in ("NEXT", "EXIT"):
        # Close any active pause interval
        if session.is_paused and session.pause_started_at is not None:
            delta = (ts - session.pause_started_at).total_seconds()
            if delta > 0:
                session.pause_accumulated_seconds += delta
            session.is_paused = False
            session.pause_started_at = None

        if session.current_question_started_at is None:
            session.current_question_started_at = session.started_at or ts

        raw_seconds = (ts - session.current_question_started_at).total_seconds()
        if raw_seconds < 0:
            raw_seconds = 0.0

        active_seconds = raw_seconds - (session.pause_accumulated_seconds or 0.0)
        if active_seconds < 0:
            active_seconds = 0.0

        q = Question(
            session_id=session.id,
            index=session.current_question_index,
            started_at=session.current_question_started_at,
            ended_at=ts,
            raw_seconds=raw_seconds,
            active_seconds=active_seconds,
        )
        db.add(q)

        last_q_active = active_seconds
        last_q_raw = raw_seconds

        if event.type == "NEXT":
            session.current_question_index += 1
            session.current_question_started_at = ts
            session.pause_accumulated_seconds = 0.0
            session.is_paused = False
            session.pause_started_at = None

        if event.type == "EXIT":
            session.is_active = False
            session.ended_at = ts
            session.current_question_started_at = None
            session.pause_accumulated_seconds = 0.0
            session.is_paused = False
            session.pause_started_at = None

    db.commit()

    total_questions = (
        db.query(Question)
        .filter(Question.session_id == session.id)
        .count()
    )

    return EventOut(
        status="ok",
        message=f"Event {event.type} recorded for user {user.email}",
        server_timestamp=datetime.utcnow(),
        session_id=session.public_id,
        total_questions=total_questions,
        last_event_type=event.type,
        last_question_index=total_questions,
        last_question_active_seconds=last_q_active,
        last_question_raw_seconds=last_q_raw,
        last_question_active_mmss=format_mmss(last_q_active)
        if last_q_active is not None
        else None,
    )

# ============================================================
# Session summary (single session) – ignores ghost rows
# ============================================================

def build_session_summary(
    db: OrmSession,
    user: User,
    session_public_id: str
) -> SessionSummary:
    session = (
        db.query(DbSession)
        .filter(DbSession.public_id == session_public_id, DbSession.user_id == user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    all_questions = (
        db.query(Question)
        .filter(Question.session_id == session.id)
        .order_by(Question.index.asc())
        .all()
    )

    # Filter out ghost zero-length Q1 rows
    questions = [q for q in all_questions if not is_ghost_question(q)]

    if not questions:
        return SessionSummary(
            session_id=session.public_id,
            user_external_id=user.email,
            started_at=session.started_at,
            ended_at=session.ended_at,
            is_active=session.is_active,
            target_minutes_per_question=session.target_minutes_per_question,
            total_questions=0,
            total_raw_seconds=0.0,
            total_active_seconds=0.0,
            avg_active_seconds=0.0,
            avg_active_mmss="00:00",
            pace_label="No questions",
            pace_emoji="😴",
            score=0,
            questions=[],
        )

    total_raw = sum(q.raw_seconds for q in questions)
    total_active = sum(q.active_seconds for q in questions)
    total_questions = len(questions)
    avg_active_seconds = total_active / total_questions if total_questions else 0.0

    pace = compute_pace(
        avg_active_seconds,
        session.target_minutes_per_question or 5.5,
    )

    question_summaries: List[SessionQuestionSummary] = []
    target_seconds = (session.target_minutes_per_question or 5.5) * 60

    display_index = 1
    for q in questions:
        over_under = q.active_seconds - target_seconds
        question_summaries.append(
            SessionQuestionSummary(
                id=q.id,
                index=display_index,
                started_at=q.started_at,
                ended_at=q.ended_at,
                raw_seconds=q.raw_seconds,
                active_seconds=q.active_seconds,
                active_mmss=format_mmss(q.active_seconds),
                over_under_target_seconds=over_under,
                over_under_target_mmss=format_mmss(abs(over_under)),
            )
        )
        display_index += 1

    return SessionSummary(
        session_id=session.public_id,
        user_external_id=user.email,
        started_at=session.started_at,
        ended_at=session.ended_at,
        is_active=session.is_active,
        target_minutes_per_question=session.target_minutes_per_question,
        total_questions=total_questions,
        total_raw_seconds=total_raw,
        total_active_seconds=total_active,
        avg_active_seconds=avg_active_seconds,
        avg_active_mmss=format_mmss(avg_active_seconds),
        pace_label=pace["pace_label"],
        pace_emoji=pace["pace_emoji"],
        score=pace["score"],
        questions=question_summaries,
    )


@app.get("/sessions/{session_public_id}/summary", response_model=SessionSummary)
def get_session_summary(
    session_public_id: str,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    return build_session_summary(db, current_user, session_public_id)


@app.get("/dashboard/sessions/{session_public_id}", response_class=HTMLResponse)
def dashboard_session(
    session_public_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    summary = build_session_summary(db, current_user, session_public_id)
    return templates.TemplateResponse(
        "session.html",
        {"request": request, "summary": summary},
    )

# ============================================================
# Day summary (today or any date) – ignores ghost rows + user TZ
# ============================================================

def build_day_summary(
    db: OrmSession,
    user: User,
    target_date: datetime,  # only Y-M-D used; interpreted in user's TZ
) -> TodaySummary:
    """
    Build a summary for a given calendar date in the user's timezone.
    """
    tz = get_user_tz(user)

    # target_date is interpreted in user's local TZ
    local_start = datetime(
        target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=tz
    )
    local_end = local_start + timedelta(days=1)

    # Convert local bounds to UTC naive for DB queries
    utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
    utc_end = local_end.astimezone(timezone.utc).replace(tzinfo=None)

    sessions = (
        db.query(DbSession)
        .filter(
            DbSession.user_id == user.id,
            DbSession.started_at >= utc_start,
            DbSession.started_at < utc_end,
        )
        .order_by(DbSession.started_at.asc())
        .all()
    )

    if not sessions:
        return TodaySummary(
            date=local_start,  # report date as local midnight
            user_external_id=user.email,
            total_sessions=0,
            total_questions=0,
            total_active_seconds=0.0,
            total_active_mmss="00:00",
            avg_active_seconds=0.0,
            avg_active_mmss="00:00",
            daily_pace_label="No questions",
            daily_pace_emoji="😴",
            sessions=[],
        )

    total_sessions = 0
    total_questions_all = 0
    total_active_all = 0.0
    total_target_minutes_weighted = 0.0
    items: List[TodaySessionItem] = []

    for s in sessions:
        qs_all = (
            db.query(Question)
            .filter(Question.session_id == s.id)
            .order_by(Question.index.asc())
            .all()
        )

        # Filter ghost questions
        qs = [q for q in qs_all if not is_ghost_question(q)]

        if not qs:
            items.append(
                TodaySessionItem(
                    session_id=s.public_id,
                    started_at=to_user_local(s.started_at, user),
                    ended_at=to_user_local(s.ended_at, user),
                    is_active=s.is_active,
                    total_questions=0,
                    total_active_seconds=0.0,
                    avg_active_seconds=0.0,
                    avg_active_mmss="00:00",
                    pace_label="No questions",
                    pace_emoji="😴",
                    score=0,
                )
            )
            total_sessions += 1
            continue

        total_sessions += 1

        total_active = sum(q.active_seconds for q in qs)
        count = len(qs)
        avg_active = total_active / count if count else 0.0

        target_minutes = s.target_minutes_per_question or 5.5
        pace = compute_pace(avg_active, target_minutes)

        total_questions_all += count
        total_active_all += total_active
        total_target_minutes_weighted += target_minutes * count

        items.append(
            TodaySessionItem(
                session_id=s.public_id,
                started_at=to_user_local(s.started_at, user),
                ended_at=to_user_local(s.ended_at, user),
                is_active=s.is_active,
                total_questions=count,
                total_active_seconds=total_active,
                avg_active_seconds=avg_active,
                avg_active_mmss=format_hhmm_or_mmss_for_dashboard(avg_active),
                pace_label=pace["pace_label"],
                pace_emoji=pace["pace_emoji"],
                score=pace["score"],
            )
        )

    avg_active_day = (
        total_active_all / total_questions_all if total_questions_all else 0.0
    )
    avg_target_minutes = (
        total_target_minutes_weighted / total_questions_all
        if total_questions_all
        else 0.0
    )
    daily_pace = (
        compute_pace(avg_active_day, avg_target_minutes)
        if total_questions_all
        else {"pace_label": "No questions", "pace_emoji": "😴"}
    )

    return TodaySummary(
        date=local_start,  # stored as local midnight in user's TZ
        user_external_id=user.email,
        total_sessions=total_sessions,
        total_questions=total_questions_all,
        total_active_seconds=total_active_all,
        total_active_mmss=format_hhmm_or_mmss_for_dashboard(total_active_all),
        avg_active_seconds=avg_active_day,
        avg_active_mmss=format_hhmm_or_mmss_for_dashboard(avg_active_day),
        daily_pace_label=daily_pace["pace_label"],
        daily_pace_emoji=daily_pace["pace_emoji"],
        sessions=items,
    )


@app.get("/sessions/today", response_model=TodaySummary)
def get_day_sessions(
    date: Optional[str] = Query(
        default=None,
        description="Optional date in YYYY-MM-DD (user's local timezone). If omitted, uses today.",
    ),
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format, use YYYY-MM-DD"
            )
    else:
        # 'today' in user's local timezone
        tz = get_user_tz(current_user)
        now_local = datetime.now(tz)
        target_date = datetime(now_local.year, now_local.month, now_local.day)

    return build_day_summary(db, current_user, target_date)


@app.get("/dashboard/today", response_class=HTMLResponse)
def dashboard_today(
    request: Request,
    date: Optional[str] = Query(
        default=None,
        description="Optional date in YYYY-MM-DD (user's local timezone). If omitted, uses today.",
    ),
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid date format, use YYYY-MM-DD"
            )
    else:
        tz = get_user_tz(current_user)
        now_local = datetime.now(tz)
        target_date = datetime(now_local.year, now_local.month, now_local.day)

    summary = build_day_summary(db, current_user, target_date)
    selected_date_str = summary.date.strftime("%Y-%m-%d") if summary.date else ""

    return templates.TemplateResponse(
        "today.html",
        {
            "request": request,
            "summary": summary,
            "selected_date": selected_date_str,
            "user_timezone": getattr(current_user, "timezone", None),
        },
    )

# ============================================================
# Session / question delete (API & HTML)
# ============================================================

@app.delete("/sessions/{session_public_id}")
def delete_session_api(
    session_public_id: str,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """
    Hard-delete a session and all its events/questions (API).
    """
    session = (
        db.query(DbSession)
        .filter(
            DbSession.public_id == session_public_id,
            DbSession.user_id == current_user.id,
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(session)  # cascades to events/questions
    db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ok", "message": "Session deleted."},
    )


@app.post("/dashboard/sessions/{session_public_id}/delete")
def delete_session_web(
    session_public_id: str,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """
    HTML form path to delete a session from the dashboard.
    """
    session = (
        db.query(DbSession)
        .filter(
            DbSession.public_id == session_public_id,
            DbSession.user_id == current_user.id,
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    db.delete(session)
    db.commit()

    return RedirectResponse(url="/dashboard/today", status_code=303)


@app.delete("/sessions/{session_public_id}/questions/{question_id}")
def delete_question_api(
    session_public_id: str,
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """
    Hard-delete a single question inside a session (API).
    """
    session = (
        db.query(DbSession)
        .filter(
            DbSession.public_id == session_public_id,
            DbSession.user_id == current_user.id,
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    question = (
        db.query(Question)
        .filter(
            Question.id == question_id,
            Question.session_id == session.id,
        )
        .first()
    )

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    db.delete(question)
    db.commit()

    # Optionally renumber remaining questions
    remaining = (
        db.query(Question)
        .filter(Question.session_id == session.id)
        .order_by(Question.started_at.asc())
        .all()
    )
    idx = 1
    for row in remaining:
        row.index = idx
        idx += 1
    db.commit()

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "ok", "message": "Question deleted."},
    )


@app.post("/dashboard/sessions/{session_public_id}/questions/{question_id}/delete")
def delete_question_web(
    session_public_id: str,
    question_id: int,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    """
    HTML form path to delete a single question row from the session detail page.
    """
    session = (
        db.query(DbSession)
        .filter(
            DbSession.public_id == session_public_id,
            DbSession.user_id == current_user.id,
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    question = (
        db.query(Question)
        .filter(
            Question.id == question_id,
            Question.session_id == session.id,
        )
        .first()
    )

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    db.delete(question)
    db.commit()

    # Renumber remaining questions so indexes stay 1..N
    remaining = (
        db.query(Question)
        .filter(Question.session_id == session.id)
        .order_by(Question.started_at.asc())
        .all()
    )
    idx = 1
    for row in remaining:
        row.index = idx
        idx += 1
    db.commit()

    return RedirectResponse(
        url=f"/dashboard/sessions/{session_public_id}",
        status_code=303,
    )

# ============================================================
# Admin debug endpoints + HTML dashboard
# ============================================================

@app.get("/admin/debug/user-sessions")
def debug_user_sessions(
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    sessions = (
        db.query(DbSession)
        .filter(DbSession.user_id == current_user.id)
        .order_by(DbSession.started_at.desc())
        .all()
    )

    return [
        {
            "session_id": s.public_id,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
            "is_active": s.is_active,
            "current_question_index": s.current_question_index,
        }
        for s in sessions
    ]


@app.get("/admin/debug/user-events/{session_public_id}")
def debug_user_events(
    session_public_id: str,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    session = (
        db.query(DbSession)
        .filter(
            DbSession.public_id == session_public_id,
            DbSession.user_id == current_user.id,
        )
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    events = (
        db.query(Event)
        .filter(Event.session_id == session.id)
        .order_by(Event.timestamp.asc(), Event.id.asc())
        .all()
    )

    return [
        {
            "id": e.id,
            "type": e.type,
            "timestamp": e.timestamp,
        }
        for e in events
    ]


@app.get("/admin/dashboard", response_class=HTMLResponse)
def admin_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    sessions = (
        db.query(DbSession)
        .filter(DbSession.user_id == current_user.id)
        .order_by(DbSession.started_at.desc())
        .limit(20)
        .all()
    )

    return templates.TemplateResponse(
        "admin_dashboard.html",
        {
            "request": request,
            "sessions": sessions,
            "user": current_user,
        },
    )

# ============================================================
# Profile (timezone, etc.)
# ============================================================

@app.get("/profile", response_class=HTMLResponse)
def profile_form(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": current_user,
        },
    )


@app.post("/profile", response_class=HTMLResponse)
def profile_update(
    request: Request,
    timezone_name: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: OrmSession = Depends(get_db),
):
    # Basic validation: must be a valid IANA timezone or fall back to UTC
    try:
        _ = ZoneInfo(timezone_name)
        valid_tz = timezone_name
    except Exception:
        valid_tz = "UTC"

    current_user.timezone = valid_tz
    db.commit()
    db.refresh(current_user)

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "user": current_user,
            "message": "Profile updated.",
        },
    )