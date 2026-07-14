"""add openapi detection support

Revision ID: 20260710_0001
Revises: 1f3d4c5b6a78
Create Date: 2026-07-10 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "20260710_0001"
down_revision = "1f3d4c5b6a78"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "detect_records",
        sa.Column("source", sa.String(20), nullable=False, server_default="web"),
    )
    op.create_index("ix_detect_records_source", "detect_records", ["source"], unique=False)
    op.create_table(
        "openapi_idempotency_keys",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("detect_record_id", sa.BigInteger(), sa.ForeignKey("detect_records.id"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_openapi_idempotency_user_key"),
    )
    op.create_index("ix_openapi_idempotency_keys_user_id", "openapi_idempotency_keys", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_openapi_idempotency_keys_user_id", table_name="openapi_idempotency_keys")
    op.drop_table("openapi_idempotency_keys")
    op.drop_index("ix_detect_records_source", table_name="detect_records")
    op.drop_column("detect_records", "source")
