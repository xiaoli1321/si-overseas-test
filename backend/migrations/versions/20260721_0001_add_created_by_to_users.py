"""add created_by to users

Tracks which manager account provisioned each user so the account-management
center can list "accounts you created" and gate password resets to them.

Revision ID: 20260721_0001
Revises: 20260710_0001
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa


revision = "20260721_0001"
down_revision = "20260710_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("created_by", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        op.f("ix_users_created_by"), "users", ["created_by"], unique=False
    )
    op.create_foreign_key(
        "fk_users_created_by_users",
        "users",
        "users",
        ["created_by"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_created_by_users", "users", type_="foreignkey")
    op.drop_index(op.f("ix_users_created_by"), table_name="users")
    op.drop_column("users", "created_by")
