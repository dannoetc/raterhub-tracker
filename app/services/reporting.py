from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy.orm import Session as OrmSession

from app.db_models import User
from app.main import build_day_summary, build_session_summary, get_user_tz
from app.models import SessionSummary, TodaySummary


class UserNotFoundError(Exception):
    """Raised when the requested user_id does not exist."""


class DailyReport:
    """Container for a single day's report in the user's timezone."""

    def __init__(
        self,
        date: datetime,
        day_summary: TodaySummary,
        session_summaries: List[SessionSummary],
    ) -> None:
        self.date = date
        self.day_summary = day_summary
        self.session_summaries = session_summaries


class WeeklyReport:
    """Container for a full week's worth of daily reports."""

    def __init__(
        self,
        week_start: datetime,
        week_end: datetime,
        daily_reports: List[DailyReport],
        totals: Dict[str, float],
    ) -> None:
        self.week_start = week_start
        self.week_end = week_end
        self.daily_reports = daily_reports
        self.totals = totals


def _get_user_or_raise(db: OrmSession, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    return user


def _normalize_local_midnight(date: datetime, tz) -> datetime:
    """Return the given datetime snapped to the user's local midnight."""

    if date.tzinfo is not None:
        local_date = date.astimezone(tz)
    else:
        local_date = datetime(date.year, date.month, date.day, tzinfo=tz)

    return datetime(local_date.year, local_date.month, local_date.day, tzinfo=tz)


def build_daily_report(
    db: OrmSession, user_id: int, date: datetime, *, user: User | None = None
) -> DailyReport:
    """
    Build a daily report for the given user on the specified date (interpreted
    in the user's timezone). Includes the JSON day summary and per-session
    summaries for the sessions that started on that local day.
    """

    user = user or _get_user_or_raise(db, user_id)
    tz = get_user_tz(user)
    local_date = _normalize_local_midnight(date, tz)

    day_summary = build_day_summary(db, user, local_date)
    session_summaries: List[SessionSummary] = []
    for session_item in day_summary.sessions:
        session_summaries.append(
            build_session_summary(db, user, session_item.session_id)
        )

    return DailyReport(
        date=day_summary.date,
        day_summary=day_summary,
        session_summaries=session_summaries,
    )


def build_weekly_report(
    db: OrmSession,
    user_id: int,
    week_start: datetime,
) -> WeeklyReport:
    """
    Build a weekly report starting at the given local date for the user.

    The seven-day window is computed in the user's timezone, and each day reuses
    the daily summary/session helpers for consistency.
    """
    user = _get_user_or_raise(db, user_id)
    tz = get_user_tz(user)

    local_week_start = _normalize_local_midnight(week_start, tz)
    local_week_end = local_week_start + timedelta(days=7)

    daily_reports: List[DailyReport] = []
    for offset in range(7):
        day_date = local_week_start + timedelta(days=offset)
        daily_reports.append(
            build_daily_report(
                db,
                user_id,
                day_date,
                user=user,
            )
        )

    totals = {
        "total_sessions": sum(r.day_summary.total_sessions for r in daily_reports),
        "total_questions": sum(r.day_summary.total_questions for r in daily_reports),
        "total_active_seconds": sum(
            r.day_summary.total_active_seconds for r in daily_reports
        ),
    }

    return WeeklyReport(
        week_start=local_week_start,
        week_end=local_week_end,
        daily_reports=daily_reports,
        totals=totals,
    )
