"""create analytics events table (no-op)

Revision ID: 20260611_0002
Revises: 20260611_0001
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa


revision = "20260611_0002"
down_revision = "20260611_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
