"""add store_category_demand bridge table

The allocation engine's demand cascade lacked a tier between
cluster-average and minimum-presentation. For a cold-start brand whose
new-season SKU codes don't overlap with last-season sales, the cascade
fell straight to minimum-presentation and produced ~0% allocation.

This table stores aggregated weekly ROS per ``(store, category, price_band)``
so the cascade can bridge from sold-out style codes to comparable
cells in the new buy file. Aggregation runs at sales-ingestion time and
on backfill.

Revision ID: 0013_store_category_demand
Revises: 0012_super_admin_signup_requests
Create Date: 2026-04-29 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0013_store_category_demand"
down_revision = "0012_super_admin_signup_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_category_demand",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("price_band", sa.String(length=100), nullable=False, server_default="*"),
        sa.Column("weekly_ros", sa.Numeric(10, 4), nullable=False, server_default="0"),
        sa.Column("units_observed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("weeks_observed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_observed_week", sa.Date(), nullable=True),
        sa.Column("sample_skus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.UniqueConstraint(
            "brand_id",
            "store_id",
            "category",
            "price_band",
            name="uq_store_category_demand_unique",
        ),
    )
    op.create_index(
        "idx_store_category_demand_lookup",
        "store_category_demand",
        ["brand_id", "store_id", "category", "price_band"],
    )
    op.create_index(
        "idx_store_category_demand_brand",
        "store_category_demand",
        ["brand_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_store_category_demand_brand", table_name="store_category_demand")
    op.drop_index("idx_store_category_demand_lookup", table_name="store_category_demand")
    op.drop_table("store_category_demand")
