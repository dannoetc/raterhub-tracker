from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session as OrmSession, sessionmaker

from app.db_models import Base, Question, Session as DbSession, User
from app.main import download_daily_report, download_weekly_report
from app.services.report_exports import (
    daily_report_to_csv,
    daily_report_to_pdf,
    render_daily_report_html,
    render_weekly_report_html,
    weekly_report_to_csv,
    weekly_report_to_pdf,
)
from app.services.reporting import build_daily_report, build_weekly_report

FIXTURES = Path(__file__).parent / "fixtures"


def make_db_session() -> OrmSession:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def seed_daily_data(db: OrmSession) -> User:
    user = User(
        external_id="csv-user",
        email="csv-user@example.com",
        timezone="UTC",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    session = DbSession(
        user_id=user.id,
        public_id="daily-session-1",
        started_at=datetime(2024, 1, 1, 10, 0, 0),
        ended_at=datetime(2024, 1, 1, 10, 10, 0),
        is_active=False,
        target_minutes_per_question=5.0,
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
            raw_seconds=320.0,
            active_seconds=300.0,
        )
    )
    db.commit()

    return user


def seed_weekly_data(db: OrmSession) -> User:
    user = User(
        external_id="csv-weekly",
        email="csv-weekly@example.com",
        timezone="UTC",
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    first_session = DbSession(
        user_id=user.id,
        public_id="weekly-session-1",
        started_at=datetime(2024, 1, 1, 9, 0, 0),
        ended_at=datetime(2024, 1, 1, 9, 8, 0),
        is_active=False,
        target_minutes_per_question=5.0,
    )
    third_session = DbSession(
        user_id=user.id,
        public_id="weekly-session-3",
        started_at=datetime(2024, 1, 3, 11, 0, 0),
        ended_at=datetime(2024, 1, 3, 11, 5, 0),
        is_active=False,
        target_minutes_per_question=4.0,
    )
    db.add_all([first_session, third_session])
    db.commit()
    db.refresh(first_session)
    db.refresh(third_session)

    db.add_all(
        [
            Question(
                session_id=first_session.id,
                index=1,
                started_at=first_session.started_at,
                ended_at=first_session.ended_at,
                raw_seconds=320.0,
                active_seconds=300.0,
            ),
            Question(
                session_id=third_session.id,
                index=1,
                started_at=third_session.started_at,
                ended_at=third_session.ended_at,
                raw_seconds=240.0,
                active_seconds=180.0,
            ),
        ]
    )
    db.commit()

    return user


def test_daily_csv_builder_matches_fixture():
    db = make_db_session()
    user = seed_daily_data(db)

    report = build_daily_report(db, user.id, datetime(2024, 1, 1))
    csv_content = daily_report_to_csv(report)

    expected = (FIXTURES / "daily_report.csv").read_text()

    db.close()

    assert csv_content == expected


def test_weekly_csv_builder_matches_fixture():
    db = make_db_session()
    user = seed_weekly_data(db)

    report = build_weekly_report(db, user.id, datetime(2024, 1, 1))
    csv_content = weekly_report_to_csv(report)

    expected = (FIXTURES / "weekly_report.csv").read_text()

    db.close()

    assert csv_content == expected


def test_csv_endpoints_return_csv_responses():
    db = make_db_session()
    user = seed_daily_data(db)

    response = download_daily_report(date="2024-01-01", current_user=user, db=db)
    assert response.media_type.startswith("text/csv")
    assert "daily_report_2024-01-01" in response.headers.get("content-disposition", "")
    assert response.body.decode() == (FIXTURES / "daily_report.csv").read_text()

    weekly_response = download_weekly_report(
        week_start="2024-01-01", current_user=user, db=db
    )
    assert weekly_response.media_type.startswith("text/csv")
    assert "weekly_report_2024-01-01" in weekly_response.headers.get(
        "content-disposition", ""
    )

    db.close()

    assert weekly_response.body.decode().startswith("date,session_count")


def test_daily_pdf_renderer_matches_template_snapshot():
    db = make_db_session()
    user = seed_daily_data(db)
    generated_at = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)

    report = build_daily_report(db, user.id, datetime(2024, 1, 1))
    html = render_daily_report_html(
        report,
        user_name="csv-user@example.com",
        user_timezone="UTC",
        generated_at=generated_at,
    )

    expected_html = (FIXTURES / "daily_report.html").read_text()

    pdf_bytes = daily_report_to_pdf(
        report,
        user_name="csv-user@example.com",
        user_timezone="UTC",
        generated_at=generated_at,
    )

    db.close()

    assert html.strip() == expected_html.strip()
    assert pdf_bytes.startswith(b"%PDF")


def test_weekly_pdf_renderer_matches_template_snapshot():
    db = make_db_session()
    user = seed_weekly_data(db)
    generated_at = datetime(2024, 1, 4, 9, 30, tzinfo=timezone.utc)

    report = build_weekly_report(db, user.id, datetime(2024, 1, 1))
    html = render_weekly_report_html(
        report,
        user_name="csv-weekly@example.com",
        user_timezone="UTC",
        generated_at=generated_at,
    )

    expected_html = (FIXTURES / "weekly_report.html").read_text()

    pdf_bytes = weekly_report_to_pdf(
        report,
        user_name="csv-weekly@example.com",
        user_timezone="UTC",
        generated_at=generated_at,
    )

    db.close()

    assert html.strip() == expected_html.strip()
    assert pdf_bytes.startswith(b"%PDF")
