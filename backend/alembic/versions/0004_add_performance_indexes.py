"""add performance-oriented indexes for ingestion and allocation

Revision ID: 0004_add_performance_indexes
Revises: 0003_add_generating_status
Create Date: 2026-03-19
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_add_performance_indexes"
down_revision: str | None = "0003_add_generating_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sales_data_upload_id ON sales_data (upload_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sales_data_brand_upload ON sales_data (brand_id, upload_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_buy_plan_lines_brand_file ON buy_plan_lines (brand_id, buy_plan_file_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_grn_lines_brand_sku ON grn_lines (brand_id, sku_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_uploads_brand_status_created ON uploads (brand_id, status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_uploads_brand_status_created")
    op.execute("DROP INDEX IF EXISTS idx_grn_lines_brand_sku")
    op.execute("DROP INDEX IF EXISTS idx_buy_plan_lines_brand_file")
    op.execute("DROP INDEX IF EXISTS idx_sales_data_brand_upload")
    op.execute("DROP INDEX IF EXISTS idx_sales_data_upload_id")
