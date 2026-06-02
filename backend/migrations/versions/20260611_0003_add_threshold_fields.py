"""add threshold fields

Revision ID: 20260611_0003
Revises: 20260611_0002
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa


revision = "20260611_0003"
down_revision = "20260611_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("thresholds", sa.Column("remark", sa.Text(), nullable=True))
    op.add_column("thresholds", sa.Column("restored_from", sa.Integer(), nullable=True))
    op.add_column("thresholds", sa.Column("is_hidden", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("thresholds", "is_hidden")
    op.drop_column("thresholds", "restored_from")
    op.drop_column("thresholds", "remark")
