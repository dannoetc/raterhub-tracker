from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db_models import ReportAudit


def log_report_event(
    db: Session,
    *,
    user_id: int,
    report_scope: str,
    report_format: str,
    report_date: date,
    triggered_by: str,
    details: Optional[str] = None,
) -> ReportAudit:
    entry = ReportAudit(
        user_id=user_id,
        report_scope=report_scope,
        report_format=report_format,
        report_date=report_date,
        triggered_by=triggered_by,
        details=details,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
