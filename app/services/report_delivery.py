import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.db_models import ReportAudit, User
from app.services.audit import log_report_event
from app.services.email_client import send_email
from app.services.report_exports import daily_report_to_csv, daily_report_to_pdf
from app.services.reporting import build_daily_report

logger = logging.getLogger(__name__)


def _user_display_name(user: User) -> str:
    name = f"{(user.first_name or '').strip()} {(user.last_name or '').strip()}".strip()
    return name or user.email


def _get_tz(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "UTC")
    except Exception:
        return ZoneInfo("UTC")


def _should_send_now(now_local: datetime) -> bool:
    local_midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    seconds_since_midnight = (now_local - local_midnight).total_seconds()
    return 0 <= seconds_since_midnight < 3600


def _report_date_for_window(now_local: datetime) -> datetime:
    midnight = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=1)


def deliver_daily_reports(
    *,
    now_utc: Optional[datetime] = None,
    db: Optional[Session] = None,
) -> List[str]:
    if not settings.EMAIL_SENDING_ENABLED:
        logger.info("Email sending disabled; skipping scheduled reports.")
        return []

    owns_session = False
    session = db
    if session is None:
        session = SessionLocal()
        owns_session = True

    delivered: List[str] = []
    now_utc = now_utc or datetime.now(timezone.utc)

    try:
        users = (
            session.query(User)
            .filter(User.is_active.is_(True), User.wants_report_emails.is_(True))
            .all()
        )

        for user in users:
            tz = _get_tz(user)
            now_local = now_utc.astimezone(tz)
            if not _should_send_now(now_local):
                continue

            report_local_date = _report_date_for_window(now_local)
            already_sent = (
                session.query(ReportAudit)
                .filter(
                    ReportAudit.user_id == user.id,
                    ReportAudit.report_scope == "daily",
                    ReportAudit.report_format == "email",
                    ReportAudit.report_date == report_local_date.date(),
                )
                .first()
            )
            if already_sent:
                continue

            report = build_daily_report(
                session,
                user.id,
                datetime(
                    report_local_date.year,
                    report_local_date.month,
                    report_local_date.day,
                    tzinfo=tz,
                ),
            )

            csv_content = daily_report_to_csv(report)
            pdf_content = daily_report_to_pdf(
                report,
                user_name=_user_display_name(user),
                user_timezone=user.timezone or "UTC",
            )

            subject = f"Your daily report for {report_local_date.date().isoformat()}"
            body = "Attached is your daily RaterHub report."

            try:
                send_email(
                    to_address=user.email,
                    subject=subject,
                    body=body,
                    attachments=[
                        (
                            f"daily_report_{report_local_date.date().isoformat()}.csv",
                            csv_content,
                            "text/csv",
                        ),
                        (
                            f"daily_report_{report_local_date.date().isoformat()}.pdf",
                            pdf_content,
                            "application/pdf",
                        ),
                    ],
                )
                log_report_event(
                    session,
                    user_id=user.id,
                    report_scope="daily",
                    report_format="email",
                    report_date=report_local_date.date(),
                    triggered_by="scheduler",
                    details="sent",
                )
                delivered.append(user.email)
            except Exception as exc:  # pragma: no cover - network errors are environment-specific
                logger.exception("Failed to deliver report email for %s", user.email)
                log_report_event(
                    session,
                    user_id=user.id,
                    report_scope="daily",
                    report_format="email",
                    report_date=report_local_date.date(),
                    triggered_by="scheduler",
                    details=f"failed: {exc}",
                )

        return delivered
    finally:
        if owns_session:
            session.close()
