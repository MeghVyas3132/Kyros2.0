"""expand season_status enum with workflow states

Revision ID: 0009_season_status_expanded
Revises: 0008_buy_plan_fields
Create Date: 2026-04-24 00:00:00.000000
"""
from alembic import op

revision = "0009_season_status_expanded"
down_revision = "0008_buy_plan_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE season_status ADD VALUE IF NOT EXISTS 'DRAFT'")
    op.execute("ALTER TYPE season_status ADD VALUE IF NOT EXISTS 'BUYING'")
    op.execute("ALTER TYPE season_status ADD VALUE IF NOT EXISTS 'RECEIVING'")
    op.execute("ALTER TYPE season_status ADD VALUE IF NOT EXISTS 'ALLOCATING'")
    op.execute("ALTER TYPE season_status ADD VALUE IF NOT EXISTS 'IN_SEASON'")


def downgrade() -> None:
    pass
