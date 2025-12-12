from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession, sessionmaker

from app.db_models import Base, Question, Session as DbSession, User
from app.services.reporting import build_daily_report, build_weekly_report


def make_db_session() -> OrmSession:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_build_daily_report_respects_user_timezone():
    db = make_db_session()

    user = User(
        external_id="u1",
        email="tz-user@example.com",
        timezone="America/Los_Angeles",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    session = DbSession(
        user_id=user.id,
        started_at=datetime(2024, 1, 2, 7, 30, 0),  # 2024-01-01 23:30 PST
        ended_at=datetime(2024, 1, 2, 7, 45, 0),
        is_active=False,
        target_minutes_per_question=5.5,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    question = Question(
        session_id=session.id,
        index=1,
        started_at=session.started_at,
        ended_at=session.ended_at,
        raw_seconds=900.0,
        active_seconds=600.0,
    )
    db.add(question)
    db.commit()

    report = build_daily_report(db, user.id, datetime(2024, 1, 1))

    hour_23_bucket = next(b for b in report.day_summary.hourly_activity if b.hour == 23)
    assert hour_23_bucket.total_questions == 1
    assert report.day_summary.total_sessions == 1
    assert report.session_summaries[0].session_id == session.public_id

    db.close()


def test_build_daily_report_normalizes_timezone_aware_dates():
    db = make_db_session()

    user = User(
        external_id="aware",
        email="aware@example.com",
        timezone="Asia/Tokyo",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    session = DbSession(
        user_id=user.id,
        started_at=datetime(2023, 12, 31, 18, 30, 0),  # 2024-01-01 03:30 JST
        ended_at=datetime(2023, 12, 31, 18, 45, 0),
        is_active=False,
        target_minutes_per_question=5.5,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    db.add(
        Question(
            session_id=session.id,
            index=1,
            started_at=session.started_at,
            ended_at=session.ended_at,
            raw_seconds=600.0,
            active_seconds=480.0,
        )
    )
    db.commit()

    report = build_daily_report(
        db,
        user.id,
        datetime(2023, 12, 31, 18, 0, 0, tzinfo=timezone.utc),
    )

    assert report.day_summary.date.day == 1
    assert report.day_summary.total_sessions == 1
    assert report.day_summary.total_questions == 1

    db.close()


def test_build_weekly_report_groups_daily_reports():
    db = make_db_session()

    user = User(
        external_id="u1",
        email="weekly@example.com",
        timezone="Asia/Kolkata",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    first_session = DbSession(
        user_id=user.id,
        started_at=datetime(2024, 1, 1, 18, 30, 0),  # Local 2024-01-02 00:00 IST
        ended_at=datetime(2024, 1, 1, 18, 45, 0),
        is_active=False,
        target_minutes_per_question=5.5,
    )
    second_session = DbSession(
        user_id=user.id,
        started_at=datetime(2024, 1, 3, 4, 0, 0),  # Local 2024-01-03 09:30 IST
        ended_at=datetime(2024, 1, 3, 4, 20, 0),
        is_active=False,
        target_minutes_per_question=5.5,
    )
    db.add_all([first_session, second_session])
    db.commit()
    db.refresh(first_session)
    db.refresh(second_session)

    db.add_all(
        [
            Question(
                session_id=first_session.id,
                index=1,
                started_at=first_session.started_at,
                ended_at=first_session.ended_at,
                raw_seconds=900.0,
                active_seconds=600.0,
            ),
            Question(
                session_id=second_session.id,
                index=1,
                started_at=second_session.started_at,
                ended_at=second_session.ended_at,
                raw_seconds=600.0,
                active_seconds=420.0,
            ),
        ]
    )
    db.commit()

    weekly_report = build_weekly_report(db, user.id, datetime(2024, 1, 1))

    assert len(weekly_report.daily_reports) == 7
    jan_2_report = next(
        r for r in weekly_report.daily_reports if r.day_summary.date.day == 2
    )
    jan_3_report = next(
        r for r in weekly_report.daily_reports if r.day_summary.date.day == 3
    )

    assert jan_2_report.day_summary.total_sessions == 1
    assert jan_3_report.day_summary.total_sessions == 1
    assert weekly_report.totals["total_questions"] == 2
    assert weekly_report.totals["total_sessions"] == 2

    db.close()


def test_build_weekly_report_normalizes_start_date_timezone():
    db = make_db_session()

    user = User(
        external_id="weekly-aware",
        email="weekly-aware@example.com",
        timezone="America/New_York",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    session = DbSession(
        user_id=user.id,
        started_at=datetime(2024, 1, 7, 15, 0, 0),  # 2024-01-07 10:00 EST
        ended_at=datetime(2024, 1, 7, 15, 20, 0),
        is_active=False,
        target_minutes_per_question=5.5,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    db.add(
        Question(
            session_id=session.id,
            index=1,
            started_at=session.started_at,
            ended_at=session.ended_at,
            raw_seconds=900.0,
            active_seconds=840.0,
        )
    )
    db.commit()

    weekly_report = build_weekly_report(
        db,
        user.id,
        datetime(2024, 1, 8, 2, 0, 0, tzinfo=timezone.utc),
    )

    assert weekly_report.week_start.day == 7
    jan7_report = next(
        r for r in weekly_report.daily_reports if r.day_summary.date.day == 7
    )
    assert jan7_report.day_summary.total_sessions == 1
    assert weekly_report.totals["total_sessions"] == 1
    assert weekly_report.totals["total_questions"] == 1

    db.close()
