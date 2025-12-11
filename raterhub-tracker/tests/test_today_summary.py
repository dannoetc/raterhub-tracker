import os
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession, sessionmaker
from starlette.requests import Request

os.environ.setdefault("SECRET_KEY", "test-key")

from app.db_models import Base, Question, Session as DbSession, User
from app.main import app, build_day_summary, dashboard_today


def make_db_session() -> OrmSession:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_build_day_summary_populates_hourly_buckets():
    db, user = seed_single_question()

    summary = build_day_summary(db, user, datetime(2024, 1, 1))

    ten_am_bucket = next(b for b in summary.hourly_activity if b.hour == 10)

    assert ten_am_bucket.total_questions == 1
    assert ten_am_bucket.active_seconds == 45.0
    assert summary.total_questions == 1
    assert summary.total_active_seconds == 45.0
    assert summary.total_sessions == 1


def seed_single_question():
    db = make_db_session()

    user = User(
        external_id="u1",
        email="u1@example.com",
        timezone="UTC",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    session = DbSession(
        user_id=user.id,
        started_at=datetime(2024, 1, 1, 10, 0, 0),
        ended_at=datetime(2024, 1, 1, 10, 5, 0),
        is_active=False,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    question = Question(
        session_id=session.id,
        index=1,
        started_at=datetime(2024, 1, 1, 10, 0, 0),
        ended_at=datetime(2024, 1, 1, 10, 1, 0),
        raw_seconds=60.0,
        active_seconds=45.0,
    )
    db.add(question)
    db.commit()

    return db, user


def test_dashboard_today_endpoint_renders_with_hourly_data():
    db, user = seed_single_question()

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/dashboard/today",
        "headers": [],
        "app": app,
    }

    request = Request(scope)
    response = dashboard_today(request=request, date=None, current_user=user, db=db)

    db.close()

    assert response.status_code == 200
