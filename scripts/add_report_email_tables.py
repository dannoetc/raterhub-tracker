"""Ensure email-related tables/columns exist for scheduled reports.

This lightweight migration script is intended for production deployments.
It safely creates the `report_audit_logs` table (added for email delivery
tracking) and adds the supporting user columns when missing. The script is
idempotent and can be re-run.

Usage (from repo root):
    SECRET_KEY=... DATABASE_URL=... python scripts/add_report_email_tables.py
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoSuchTableError

from app.database import engine
from app.db_models import ReportAudit


def _table_exists(engine: Engine, table: str) -> bool:
    inspector = inspect(engine)
    return inspector.has_table(table)


def _has_column(engine: Engine, table: str, column: str) -> bool:
    inspector = inspect(engine)
    try:
        columns: Iterable[dict] = inspector.get_columns(table)
    except NoSuchTableError:
        return False

    return any(col.get("name") == column for col in columns)


def _create_report_audit_logs(engine: Engine) -> bool:
    if _table_exists(engine, "report_audit_logs"):
        print("Table report_audit_logs already exists. Skipping creation.")
        return False

    print("Creating table: report_audit_logs")
    ReportAudit.__table__.create(bind=engine, checkfirst=True)
    return True


def _ensure_user_columns(engine: Engine) -> list[str]:
    added: list[str] = []
    for column_name, ddl_sqlite, ddl_postgres in (
        (
            "timezone",
            "ALTER TABLE users ADD COLUMN timezone VARCHAR(255) DEFAULT 'UTC' NOT NULL;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS timezone VARCHAR(255) DEFAULT 'UTC' NOT NULL;",
        ),
        (
            "wants_report_emails",
            "ALTER TABLE users ADD COLUMN wants_report_emails BOOLEAN DEFAULT 0 NOT NULL;",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS wants_report_emails BOOLEAN DEFAULT FALSE NOT NULL;",
        ),
    ):
        if _has_column(engine, "users", column_name):
            continue

        print(f"Adding column to users: {column_name}")
        dialect = engine.dialect.name
        ddl = text(ddl_postgres if dialect == "postgresql" else ddl_sqlite)
        with engine.begin() as conn:
            conn.execute(ddl)
        added.append(column_name)

    return added


if __name__ == "__main__":
    created_table = _create_report_audit_logs(engine)
    added_columns = _ensure_user_columns(engine)

    if created_table or added_columns:
        print("Migration complete. Changes applied:")
        if created_table:
            print("  - report_audit_logs table created")
        for column in added_columns:
            print(f"  - users.{column} column added")
    else:
        print("Nothing to do; email-related tables/columns already present.")
