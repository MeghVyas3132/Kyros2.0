"""add health_score / health_report / decision to allocation_sessions

These columns existed in the model since the engine introduced the health
analyser, but no migration ever added them. Pre-existing dev DBs had them
hand-added, so the drift was invisible. On a fresh `alembic upgrade head`
the columns were missing and any allocation insert failed.

Revision ID: 0011_alloc_session_health
Revises: 0010_override_reason_code
Create Date: 2026-04-26 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_alloc_session_health"
down_revision = "0010_override_reason_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use IF NOT EXISTS so this is safe to run on hand-patched dev DBs.
    op.execute(
        "ALTER TABLE allocation_sessions "
        "ADD COLUMN IF NOT EXISTS health_score INTEGER"
    )
    op.execute(
        "ALTER TABLE allocation_sessions "
        "ADD COLUMN IF NOT EXISTS health_report JSONB"
    )
    op.execute(
        "ALTER TABLE allocation_sessions "
        "ADD COLUMN IF NOT EXISTS decision JSONB"
    )


def downgrade() -> None:
    op.drop_column("allocation_sessions", "decision")
    op.drop_column("allocation_sessions", "health_report")
    op.drop_column("allocation_sessions", "health_score")
