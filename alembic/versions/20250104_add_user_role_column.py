"""Add user role column

Revision ID: 20250104_add_user_role
Revises: None
Create Date: 2025-01-04
"""

from alembic import op
import sqlalchemy as sa

revision = "20250104_add_user_role"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(), nullable=False, server_default="user"),
    )
    op.alter_column("users", "role", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "role")
