"""add missing alert type enum values

Revision ID: 0007_add_alert_type_values
Revises: 0006_store_profiles
Create Date: 2026-03-23 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "0007_add_alert_type_values"
down_revision = "0006_store_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE alert_type ADD VALUE IF NOT EXISTS 'WAREHOUSE_STOCK_SITTING'")
    op.execute("ALTER TYPE alert_type ADD VALUE IF NOT EXISTS 'HIGH_COVER'")


def downgrade() -> None:
    # PostgreSQL enum value removal is non-trivial and intentionally not attempted here.
    pass
