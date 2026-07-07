"""Rename detectRecordID to detect_record_id in uploaded_files"""
from alembic import op
import sqlalchemy as sa

revision = "rename_detect_record_id"
down_revision = "984489ceb537"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("uploaded_files", "detectRecordID", new_column_name="detect_record_id")


def downgrade() -> None:
    op.alter_column("uploaded_files", "detect_record_id", new_column_name="detectRecordID")
