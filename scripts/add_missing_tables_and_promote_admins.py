"""Helper migration to align production schema and admin roles.

This script creates any missing core tables and ensures the existing
users in production are promoted to admins (useful when roles were
introduced after those accounts were created). The operations are
idempotent and safe to re-run.

Usage (from repo root):
    SECRET_KEY=... DATABASE_URL=... python scripts/add_missing_tables_and_promote_admins.py
"""
from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import NoSuchTableError

from app.database import engine
from app.db_models import (
    Base,
    Event,
    LoginAttempt,
    PasswordHistory,
    Question,
    ReportAudit,
    Session,
    User,
)


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


def _create_tables_if_missing(engine: Engine, tables: Sequence[str]) -> list[str]:
    created: list[str] = []
    for table_name in tables:
        if _table_exists(engine, table_name):
            continue

        print(f"Creating table: {table_name}")
        Base.metadata.tables[table_name].create(bind=engine, checkfirst=True)
        created.append(table_name)

    return created


def _ensure_role_column(engine: Engine) -> bool:
    if _has_column(engine, "users", "role"):
        return False

    dialect = engine.dialect.name
    ddl_sqlite = "ALTER TABLE users ADD COLUMN role VARCHAR(255) DEFAULT 'user' NOT NULL;"
    ddl_postgres = "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(255) DEFAULT 'user' NOT NULL;"
    ddl = text(ddl_postgres if dialect == "postgresql" else ddl_sqlite)

    print("Adding column to users: role")
    with engine.begin() as conn:
        conn.execute(ddl)

    return True


def _promote_existing_users_to_admin(engine: Engine) -> int:
    if not _table_exists(engine, "users"):
        print("Users table not found; skipping role promotion.")
        return 0

    if not _has_column(engine, "users", "role"):
        print("Users table missing role column; skipping promotion until column exists.")
        return 0

    update_stmt = text("UPDATE users SET role = 'admin' WHERE role IS NULL OR role != 'admin'")

    with engine.begin() as conn:
        result = conn.execute(update_stmt)
        # SQLAlchemy 1.4 result.rowcount may be None depending on backend; coerce to int.
        return int(result.rowcount or 0)


if __name__ == "__main__":
    tables_to_ensure = (
        User.__tablename__,
        Session.__tablename__,
        Event.__tablename__,
        Question.__tablename__,
        PasswordHistory.__tablename__,
        LoginAttempt.__tablename__,
        ReportAudit.__tablename__,
    )

    created_tables = _create_tables_if_missing(engine, tables_to_ensure)
    role_added = _ensure_role_column(engine)
    promoted_count = _promote_existing_users_to_admin(engine)

    if created_tables or role_added or promoted_count:
        print("Migration actions complete.")
        if created_tables:
            for table in created_tables:
                print(f"  - {table} table created")
        if role_added:
            print("  - users.role column added")
        if promoted_count:
            print(f"  - promoted {promoted_count} existing user(s) to admin")
    else:
        print("Nothing to do; schema and admin roles already up to date.")
