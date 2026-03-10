"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


user_role = sa.Enum("ADMIN", "PLANNER", "VIEWER", name="user_role")
season_status = sa.Enum("PLANNING", "ACTIVE", "CLOSED", name="season_status")
upload_type = sa.Enum("SALES", "INVENTORY", "GRN", "STORE_MASTER", "SKU_MASTER", name="upload_type")
upload_status = sa.Enum("PENDING", "PROCESSING", "COMPLETED", "FAILED", "PARTIAL", name="upload_status")
allocation_status = sa.Enum(
    "DRAFT", "UNDER_REVIEW", "APPROVED", "DISPATCHED", "CANCELLED", name="allocation_status"
)
alert_type = sa.Enum("STOCKOUT_RISK", "AGING_STOCK", "GRN_UNALLOCATED", name="alert_type")


def upgrade() -> None:
    op.create_table(
        "brands",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("idx_users_brand_id", "users", ["brand_id"])
    op.create_index("idx_users_email", "users", ["email"])

    op.create_table(
        "clusters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "name", name="uq_clusters_brand_name"),
    )
    op.create_index("idx_clusters_brand_id", "clusters", ["brand_id"])

    op.create_table(
        "stores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_code", sa.String(length=50), nullable=False),
        sa.Column("store_name", sa.String(length=255), nullable=False),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("cluster_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("store_grade", sa.String(length=5), nullable=False),
        sa.Column("store_type", sa.String(length=50), nullable=True),
        sa.Column("climate_zone", sa.String(length=50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("opening_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["cluster_id"], ["clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "store_code", name="uq_stores_brand_store_code"),
    )
    op.create_index("idx_stores_brand_id", "stores", ["brand_id"])
    op.create_index("idx_stores_cluster_id", "stores", ["cluster_id"])

    op.create_table(
        "store_display_capacity",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("max_styles", sa.Integer(), nullable=False),
        sa.Column("max_units", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "category", name="uq_store_capacity_store_category"),
    )
    op.create_index("idx_store_capacity_brand_id", "store_display_capacity", ["brand_id"])

    op.create_table(
        "seasons",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("categories", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("status", season_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "season_otb",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("planned_sales", sa.Numeric(12, 2), nullable=False),
        sa.Column("planned_closing_stock", sa.Numeric(12, 2), nullable=False),
        sa.Column("opening_stock", sa.Numeric(12, 2), nullable=False),
        sa.Column("on_order", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "otb_value",
            sa.Numeric(12, 2),
            sa.Computed("planned_sales + planned_closing_stock - opening_stock - on_order", persisted=True),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("season_id", "category", "month", name="uq_season_otb_unique"),
    )

    op.create_table(
        "skus",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_code", sa.String(length=100), nullable=False),
        sa.Column("style_code", sa.String(length=100), nullable=False),
        sa.Column("style_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("sub_category", sa.String(length=100), nullable=True),
        sa.Column("fabric", sa.String(length=100), nullable=True),
        sa.Column("colour", sa.String(length=100), nullable=True),
        sa.Column("colour_family", sa.String(length=50), nullable=True),
        sa.Column("price_band", sa.String(length=50), nullable=True),
        sa.Column("mrp", sa.Numeric(10, 2), nullable=True),
        sa.Column("cost_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("size", sa.String(length=20), nullable=True),
        sa.Column("fit_type", sa.String(length=50), nullable=True),
        sa.Column("sku_type", sa.String(length=20), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "sku_code", name="uq_skus_brand_sku_code"),
    )
    op.create_index("idx_skus_brand_id", "skus", ["brand_id"])
    op.create_index("idx_skus_style_code", "skus", ["brand_id", "style_code"])
    op.create_index("idx_skus_category", "skus", ["brand_id", "category"])

    op.create_table(
        "uploads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_type", upload_type, nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("s3_key", sa.String(length=500), nullable=False),
        sa.Column("status", upload_status, nullable=False),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("successful_rows", sa.Integer(), nullable=False),
        sa.Column("failed_rows", sa.Integer(), nullable=False),
        sa.Column("error_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_uploads_brand_id", "uploads", ["brand_id"])

    op.create_table(
        "sales_data",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("units_sold", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Numeric(12, 2), nullable=True),
        sa.Column("was_on_promotion", sa.Boolean(), nullable=False),
        sa.Column("was_in_stock", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "store_id", "sku_id", "week_start_date", name="uq_sales_brand_store_sku_week"),
    )
    op.create_index("idx_sales_brand_store_sku", "sales_data", ["brand_id", "store_id", "sku_id"])
    op.create_index("idx_sales_week", "sales_data", ["brand_id", "week_start_date"])
    op.create_index("idx_sales_sku", "sales_data", ["brand_id", "sku_id"])

    op.create_table(
        "grns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grn_code", sa.String(length=100), nullable=False),
        sa.Column("grn_date", sa.Date(), nullable=False),
        sa.Column("warehouse_id", sa.String(length=100), nullable=True),
        sa.Column("supplier_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("total_units", sa.Integer(), nullable=False),
        sa.Column("total_skus", sa.Integer(), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "grn_code", name="uq_grns_brand_grn_code"),
    )
    op.create_index("idx_grns_brand_id", "grns", ["brand_id"])

    op.create_table(
        "grn_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("units_received", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["grn_id"], ["grns.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grn_id", "sku_id", name="uq_grn_lines_grn_sku"),
    )
    op.create_index("idx_grn_lines_grn_id", "grn_lines", ["grn_id"])

    op.create_table(
        "inventory_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("location_id", sa.String(length=100), nullable=False),
        sa.Column("location_type", sa.String(length=20), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("units_on_hand", sa.Integer(), nullable=False),
        sa.Column("units_in_transit", sa.Integer(), nullable=False),
        sa.Column("units_sold_7d", sa.Integer(), nullable=False),
        sa.Column("units_sold_28d", sa.Integer(), nullable=False),
        sa.Column("ros_7d", sa.Numeric(8, 2), nullable=True),
        sa.Column("ros_28d", sa.Numeric(8, 2), nullable=True),
        sa.Column("stock_cover_days", sa.Numeric(8, 1), nullable=True),
        sa.Column("days_since_grn", sa.Integer(), nullable=True),
        sa.Column("days_since_first_sale", sa.Integer(), nullable=True),
        sa.Column("sell_through_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("is_stockout", sa.Boolean(), nullable=False),
        sa.Column("is_new_arrival", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "brand_id", "snapshot_date", "location_id", "location_type", "sku_id", name="uq_inventory_state_unique"
        ),
    )
    op.create_index("idx_inv_state_latest", "inventory_state", ["brand_id", "snapshot_date"])
    op.create_index("idx_inv_state_location", "inventory_state", ["brand_id", "location_id", "snapshot_date"])
    op.create_index("idx_inv_state_sku", "inventory_state", ["brand_id", "sku_id", "snapshot_date"])

    op.create_table(
        "allocation_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", allocation_status, nullable=False),
        sa.Column("engine_version", sa.String(length=20), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_by_user", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("total_stores", sa.Integer(), nullable=False),
        sa.Column("total_skus", sa.Integer(), nullable=False),
        sa.Column("total_units_recommended", sa.Integer(), nullable=False),
        sa.Column("total_units_approved", sa.Integer(), nullable=False),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["grn_id"], ["grns.id"]),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.ForeignKeyConstraint(["generated_by_user"], ["users.id"]),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "allocation_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ai_recommended_qty", sa.Integer(), nullable=False),
        sa.Column("ai_confidence", sa.String(length=10), nullable=True),
        sa.Column("ai_reasoning", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("ai_projections", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("final_qty", sa.Integer(), nullable=True),
        sa.Column("was_overridden", sa.Boolean(), nullable=False),
        sa.Column("override_reason", sa.String(length=100), nullable=True),
        sa.Column("override_notes", sa.Text(), nullable=True),
        sa.Column("actual_sellthrough_4w", sa.Numeric(5, 2), nullable=True),
        sa.Column("actual_sellthrough_8w", sa.Numeric(5, 2), nullable=True),
        sa.Column("actual_sellthrough_eow", sa.Numeric(5, 2), nullable=True),
        sa.Column("ai_was_better", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["allocation_sessions.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "store_id", "sku_id", name="uq_alloc_lines_session_store_sku"),
    )
    op.create_index("idx_alloc_lines_session", "allocation_lines", ["session_id"])
    op.create_index("idx_alloc_lines_store", "allocation_lines", ["brand_id", "store_id"])
    op.create_index("idx_alloc_lines_sku", "allocation_lines", ["brand_id", "sku_id"])

    op.create_table(
        "performance_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("units_sold_today", sa.Integer(), nullable=False),
        sa.Column("units_sold_7d", sa.Integer(), nullable=False),
        sa.Column("units_sold_28d", sa.Integer(), nullable=False),
        sa.Column("units_on_hand", sa.Integer(), nullable=False),
        sa.Column("sell_through_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("ros_7d", sa.Numeric(8, 2), nullable=True),
        sa.Column("stock_cover_days", sa.Numeric(8, 1), nullable=True),
        sa.Column("days_since_grn", sa.Integer(), nullable=True),
        sa.Column("style_status", sa.String(length=20), nullable=True),
        sa.Column("is_stockout", sa.Boolean(), nullable=False),
        sa.Column("lost_sales_estimate", sa.Numeric(8, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "snapshot_date", "store_id", "sku_id", name="uq_perf_snapshot_brand_date_store_sku"),
    )
    op.create_index("idx_perf_snap_brand_date", "performance_snapshots", ["brand_id", "snapshot_date"])
    op.create_index("idx_perf_snap_sku", "performance_snapshots", ["brand_id", "sku_id", "snapshot_date"])

    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_type", alert_type, nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("grn_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action_url", sa.String(length=500), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_dismissed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.ForeignKeyConstraint(["grn_id"], ["grns.id"]),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_alerts_brand_active", "alerts", ["brand_id", "is_dismissed", "generated_at"])


def downgrade() -> None:
    op.drop_index("idx_alerts_brand_active", table_name="alerts")
    op.drop_table("alerts")
    op.drop_index("idx_perf_snap_sku", table_name="performance_snapshots")
    op.drop_index("idx_perf_snap_brand_date", table_name="performance_snapshots")
    op.drop_table("performance_snapshots")
    op.drop_index("idx_alloc_lines_sku", table_name="allocation_lines")
    op.drop_index("idx_alloc_lines_store", table_name="allocation_lines")
    op.drop_index("idx_alloc_lines_session", table_name="allocation_lines")
    op.drop_table("allocation_lines")
    op.drop_table("allocation_sessions")
    op.drop_index("idx_inv_state_sku", table_name="inventory_state")
    op.drop_index("idx_inv_state_location", table_name="inventory_state")
    op.drop_index("idx_inv_state_latest", table_name="inventory_state")
    op.drop_table("inventory_state")
    op.drop_index("idx_grn_lines_grn_id", table_name="grn_lines")
    op.drop_table("grn_lines")
    op.drop_index("idx_grns_brand_id", table_name="grns")
    op.drop_table("grns")
    op.drop_index("idx_sales_sku", table_name="sales_data")
    op.drop_index("idx_sales_week", table_name="sales_data")
    op.drop_index("idx_sales_brand_store_sku", table_name="sales_data")
    op.drop_table("sales_data")
    op.drop_index("idx_uploads_brand_id", table_name="uploads")
    op.drop_table("uploads")
    op.drop_index("idx_skus_category", table_name="skus")
    op.drop_index("idx_skus_style_code", table_name="skus")
    op.drop_index("idx_skus_brand_id", table_name="skus")
    op.drop_table("skus")
    op.drop_table("season_otb")
    op.drop_table("seasons")
    op.drop_index("idx_store_capacity_brand_id", table_name="store_display_capacity")
    op.drop_table("store_display_capacity")
    op.drop_index("idx_stores_cluster_id", table_name="stores")
    op.drop_index("idx_stores_brand_id", table_name="stores")
    op.drop_table("stores")
    op.drop_index("idx_clusters_brand_id", table_name="clusters")
    op.drop_table("clusters")
    op.drop_index("idx_users_email", table_name="users")
    op.drop_index("idx_users_brand_id", table_name="users")
    op.drop_table("users")
    op.drop_table("brands")

    # Enum types are dropped automatically with dependent tables in PostgreSQL.
