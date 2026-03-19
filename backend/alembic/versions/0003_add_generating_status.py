"""add GENERATING to allocation_status enum

Revision ID: 0003_add_generating_status
Revises: 0002_pilot_data_patterns
Create Date: 2026-03-10
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_add_generating_status"
down_revision: str | None = "0002_pilot_data_patterns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE allocation_status ADD VALUE IF NOT EXISTS 'GENERATING' BEFORE 'UNDER_REVIEW'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    pass
