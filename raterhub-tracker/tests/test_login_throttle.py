from datetime import datetime, timedelta

import pytest

from app.auth import get_password_hash
from app.database import SessionLocal, engine
from app.db_models import Base, LoginAttempt, User
from app.main import (
    BACKOFF_AFTER_FAILURES,
    BACKOFF_STEP_SECONDS,
    CSRF_HEADER_NAME,
    LOCKOUT_DURATION,
    LOGIN_FAILURE_THRESHOLD,
    app,
)
from tests.test_csrf_api import JsonASGIClient


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def create_user(email: str = "user@example.com", password: str = "hunter2"):
    db = SessionLocal()
    user = User(
        external_id=email,
        email=email,
        password_hash=get_password_hash(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def _advance_attempt_timestamps(seconds: int):
    db = SessionLocal()
    now = datetime.utcnow() - timedelta(seconds=seconds)
    for attempt in db.query(LoginAttempt).all():
        attempt.last_failure_at = now
        db.add(attempt)
    db.commit()
    db.close()


def _clear_lockouts():
    db = SessionLocal()
    cleared_at = datetime.utcnow() - LOCKOUT_DURATION - timedelta(seconds=5)
    for attempt in db.query(LoginAttempt).all():
        attempt.locked_until = cleared_at
        attempt.last_failure_at = cleared_at
        db.add(attempt)
    db.commit()
    db.close()


@pytest.mark.anyio
async def test_login_lockout_triggers_after_threshold():
    create_user()
    client = JsonASGIClient(app)

    status, _, csrf_body = await client.get_json("/auth/csrf")
    assert status == 200
    csrf_token = csrf_body["csrf_token"]

    for _ in range(LOGIN_FAILURE_THRESHOLD):
        status, _, body = await client.post_json(
            "/auth/login",
            {"email": "user@example.com", "password": "wrong-password"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert status == 401
        assert body["detail"] == "Invalid credentials"
        _advance_attempt_timestamps(BACKOFF_STEP_SECONDS * LOGIN_FAILURE_THRESHOLD + 10)

    status, _, body = await client.post_json(
        "/auth/login",
        {"email": "user@example.com", "password": "hunter2"},
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert status == 429
    assert body["detail"] == "Too many login attempts. Please try again later."


@pytest.mark.anyio
async def test_backoff_applies_before_lockout():
    create_user()
    client = JsonASGIClient(app)

    status, _, csrf_body = await client.get_json("/auth/csrf")
    assert status == 200
    csrf_token = csrf_body["csrf_token"]

    for _ in range(BACKOFF_AFTER_FAILURES):
        status, _, body = await client.post_json(
            "/auth/login",
            {"email": "user@example.com", "password": "wrong-password"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )
        assert status == 401
        assert body["detail"] == "Invalid credentials"

    status, _, body = await client.post_json(
        "/auth/login",
        {"email": "user@example.com", "password": "wrong-password"},
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert status == 429
    assert body["detail"] == "Too many login attempts. Please try again later."

    _advance_attempt_timestamps(BACKOFF_STEP_SECONDS + 5)

    status, _, body = await client.post_json(
        "/auth/login",
        {"email": "user@example.com", "password": "wrong-password"},
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert status == 401
    assert body["detail"] == "Invalid credentials"


@pytest.mark.anyio
async def test_counters_reset_after_cooldown_and_success():
    create_user()
    client = JsonASGIClient(app)

    status, _, csrf_body = await client.get_json("/auth/csrf")
    assert status == 200
    csrf_token = csrf_body["csrf_token"]

    for _ in range(LOGIN_FAILURE_THRESHOLD):
        await client.post_json(
            "/auth/login",
            {"email": "user@example.com", "password": "wrong-password"},
            headers={CSRF_HEADER_NAME: csrf_token},
        )

    status, _, body = await client.post_json(
        "/auth/login",
        {"email": "user@example.com", "password": "hunter2"},
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert status == 429
    assert body["detail"] == "Too many login attempts. Please try again later."

    _clear_lockouts()

    status, _, body = await client.post_json(
        "/auth/login",
        {"email": "user@example.com", "password": "hunter2"},
        headers={CSRF_HEADER_NAME: csrf_token},
    )
    assert status == 200
    assert "access_token" in body

    db = SessionLocal()
    attempts = db.query(LoginAttempt).all()
    assert all(attempt.failure_count == 0 for attempt in attempts)
    assert all(attempt.locked_until is None for attempt in attempts)
    db.close()
