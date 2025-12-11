"""Ensure the users table has first_name and last_name columns.

This lightweight migration script is intended for production deployments.
It checks whether the columns already exist and adds them if missing. The
script is safe to re-run.

Usage (from repo root):
    SECRET_KEY=... DATABASE_URL=... python scripts/add_user_name_columns.py
"""

from __future__ import annotations

import sys
from typing import Iterable

from sqlalchemy import inspect, text
from sqlalchemy.exc import NoSuchTableError
from sqlalchemy.engine import Engine

from app.database import engine


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


def _add_column(engine: Engine, column_name: str) -> None:
    dialect = engine.dialect.name

    if dialect == "postgresql":
        ddl = text(
            f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column_name} VARCHAR(255) DEFAULT '';"
        )
    else:
        # SQLite supports ADD COLUMN without IF NOT EXISTS; we guard with inspector instead.
        ddl = text(
            f"ALTER TABLE users ADD COLUMN {column_name} VARCHAR(255) DEFAULT '';"
        )

    with engine.begin() as conn:
        conn.execute(ddl)


if __name__ == "__main__":
    if not _table_exists(engine, "users"):
        print("Users table not found. Ensure the database is initialized before running this script.")
        sys.exit(1)

    missing_columns = [
        name
        for name in ("first_name", "last_name")
        if not _has_column(engine, "users", name)
    ]

    if not missing_columns:
        print("Users table already has first_name and last_name columns. Nothing to do.")
        sys.exit(0)

    for column in missing_columns:
        print(f"Adding column: {column}")
        _add_column(engine, column)

    print("Migration complete.")
