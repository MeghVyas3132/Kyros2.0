"""add FAILED status and failure reason to allocation sessions

Revision ID: 0005_alloc_failed
Revises: 0004_add_performance_indexes
Create Date: 2026-03-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_alloc_failed"
down_revision: str | None = "0004_add_performance_indexes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE allocation_status ADD VALUE IF NOT EXISTS 'FAILED'")
    op.add_column("allocation_sessions", sa.Column("failure_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("allocation_sessions", "failure_reason")
    # PostgreSQL does not support removing enum values safely.
