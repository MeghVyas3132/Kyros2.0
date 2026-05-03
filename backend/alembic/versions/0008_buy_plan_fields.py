"""add buy plan fields to buy_plan_lines and buy_plan_files

Revision ID: 0008_buy_plan_fields
Revises: 0007_add_alert_type_values
Create Date: 2026-04-24 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0008_buy_plan_fields"
down_revision: str | None = "0007_add_alert_type_values"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add new columns to buy_plan_lines
    op.add_column("buy_plan_lines", sa.Column("vendor_name", sa.String(length=255), nullable=True))
    op.add_column("buy_plan_lines", sa.Column("expected_delivery_week", sa.Date(), nullable=True))
    op.add_column("buy_plan_lines", sa.Column("planned_cost_per_unit", sa.Numeric(10, 2), nullable=True))
    op.add_column("buy_plan_lines", sa.Column("moq", sa.Integer(), nullable=True))
    op.add_column("buy_plan_lines", sa.Column("planned_price_per_unit", sa.Numeric(10, 2), nullable=True))
    op.add_column("buy_plan_lines", sa.Column("planned_margin_pct", sa.Numeric(5, 2), nullable=True))

    # Add notes column to buy_plan_files
    op.add_column("buy_plan_files", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("buy_plan_lines", "vendor_name")
    op.drop_column("buy_plan_lines", "expected_delivery_week")
    op.drop_column("buy_plan_lines", "planned_cost_per_unit")
    op.drop_column("buy_plan_lines", "moq")
    op.drop_column("buy_plan_lines", "planned_price_per_unit")
    op.drop_column("buy_plan_lines", "planned_margin_pct")
    op.drop_column("buy_plan_files", "notes")
