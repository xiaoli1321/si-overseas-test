"""initial backend mvp schema

Revision ID: 20260602_0001
Revises:
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260602_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("distributor_name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "thresholds",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "version", name="uq_threshold_user_version"),
    )
    op.create_index(op.f("ix_thresholds_is_active"), "thresholds", ["is_active"], unique=False)
    op.create_index(op.f("ix_thresholds_user_id"), "thresholds", ["user_id"], unique=False)

    op.create_table(
        "batch_tasks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("fault_category", sa.String(length=50), nullable=False),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_batch_tasks_status"), "batch_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_batch_tasks_user_id"), "batch_tasks", ["user_id"], unique=False)

    op.create_table(
        "detect_records",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("batch_task_id", sa.BigInteger(), nullable=True),
        sa.Column("serial_no", sa.String(length=50), nullable=False),
        sa.Column("device_type", sa.String(length=20), nullable=False),
        sa.Column("fault_category", sa.String(length=50), nullable=False),
        sa.Column("fault_subtype", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("verdict", sa.String(length=50), nullable=True),
        sa.Column("issue_detected", sa.Boolean(), nullable=True),
        sa.Column("reasons", sa.Text(), nullable=True),
        sa.Column("threshold_id", sa.BigInteger(), nullable=True),
        sa.Column("threshold_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("feedback_status", sa.String(length=20), nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("is_visible_in_workbench", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["batch_task_id"], ["batch_tasks.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["threshold_id"], ["thresholds.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_detect_records_batch_task_id"), "detect_records", ["batch_task_id"], unique=False)
    op.create_index(op.f("ix_detect_records_fault_category"), "detect_records", ["fault_category"], unique=False)
    op.create_index(op.f("ix_detect_records_serial_no"), "detect_records", ["serial_no"], unique=False)
    op.create_index(op.f("ix_detect_records_status"), "detect_records", ["status"], unique=False)
    op.create_index(op.f("ix_detect_records_user_id"), "detect_records", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_detect_records_user_id"), table_name="detect_records")
    op.drop_index(op.f("ix_detect_records_status"), table_name="detect_records")
    op.drop_index(op.f("ix_detect_records_serial_no"), table_name="detect_records")
    op.drop_index(op.f("ix_detect_records_fault_category"), table_name="detect_records")
    op.drop_index(op.f("ix_detect_records_batch_task_id"), table_name="detect_records")
    op.drop_table("detect_records")
    op.drop_index(op.f("ix_batch_tasks_user_id"), table_name="batch_tasks")
    op.drop_index(op.f("ix_batch_tasks_status"), table_name="batch_tasks")
    op.drop_table("batch_tasks")
    op.drop_index(op.f("ix_thresholds_user_id"), table_name="thresholds")
    op.drop_index(op.f("ix_thresholds_is_active"), table_name="thresholds")
    op.drop_table("thresholds")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
