"""add_detect_records_query_indexes

Revision ID: 1f3d4c5b6a78
Revises: rename_detect_record_id
Create Date: 2026-07-02 00:00:00.000000
"""
from alembic import op


revision = "1f3d4c5b6a78"
down_revision = "rename_detect_record_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_detect_records_user_visible_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_detect_records_user_visible_fault_cat_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "fault_category", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_detect_records_user_visible_status_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_detect_records_user_visible_verdict_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "verdict", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_detect_records_user_visible_issue_created_at",
        "detect_records",
        ["user_id", "is_visible_in_workbench", "issue_detected", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_detect_records_user_visible_issue_created_at",
        table_name="detect_records",
    )
    op.drop_index(
        "ix_detect_records_user_visible_verdict_created_at",
        table_name="detect_records",
    )
    op.drop_index(
        "ix_detect_records_user_visible_status_created_at",
        table_name="detect_records",
    )
    op.drop_index(
        "ix_detect_records_user_visible_fault_cat_created_at",
        table_name="detect_records",
    )
    op.drop_index(
        "ix_detect_records_user_visible_created_at",
        table_name="detect_records",
    )
