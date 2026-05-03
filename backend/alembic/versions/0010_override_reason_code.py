"""add override_reason_code enum to allocation_lines

Revision ID: 0010_override_reason_code
Revises: 0009_season_status_expanded
Create Date: 2026-04-24 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_override_reason_code"
down_revision = "0009_season_status_expanded"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type
    op.execute("""
        CREATE TYPE override_reason_code AS ENUM (
            'GRADE_DRIFT', 'LOCAL_TREND', 'VENDOR_DELAY',
            'CATEGORY_SHIFT', 'STORE_CLOSURE', 'OTHER'
        )
    """)
    # Add column, defaulting existing rows to OTHER
    op.add_column(
        "allocation_lines",
        sa.Column(
            "override_reason_code",
            sa.Enum(
                "GRADE_DRIFT", "LOCAL_TREND", "VENDOR_DELAY",
                "CATEGORY_SHIFT", "STORE_CLOSURE", "OTHER",
                name="override_reason_code",
            ),
            nullable=True,
        ),
    )
    # Backfill: rows that were already overridden get OTHER
    op.execute("""
        UPDATE allocation_lines
        SET override_reason_code = 'OTHER'
        WHERE was_overridden = true AND override_reason_code IS NULL
    """)


def downgrade() -> None:
    op.drop_column("allocation_lines", "override_reason_code")
    op.execute("DROP TYPE IF EXISTS override_reason_code")
