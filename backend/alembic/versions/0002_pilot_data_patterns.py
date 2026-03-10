"""pilot data pattern schema updates

Revision ID: 0002_pilot_data_patterns
Revises: 0001_initial_schema
Create Date: 2026-03-09
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002_pilot_data_patterns"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE upload_type ADD VALUE IF NOT EXISTS 'STORE_GRADES'")
    op.execute("ALTER TYPE upload_type ADD VALUE IF NOT EXISTS 'SIZE_GUIDE'")
    op.execute("ALTER TYPE upload_type ADD VALUE IF NOT EXISTS 'BUY_FILE'")
    op.execute("ALTER TYPE upload_type ADD VALUE IF NOT EXISTS 'RESERVATION_TYPES'")

    op.create_table(
        "brand_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", name="uq_brand_settings_brand_id"),
    )
    op.create_index(
        "idx_brand_settings_config_gin",
        "brand_settings",
        ["config"],
        postgresql_using="gin",
    )

    op.create_table(
        "style_store_lists",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("list_name", sa.String(length=100), nullable=False),
        sa.Column("store_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "list_name", name="uq_style_store_lists_brand_name"),
    )
    op.create_index("idx_style_store_lists_brand_id", "style_store_lists", ["brand_id"])

    op.create_table(
        "store_product_grades",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_category", sa.String(length=100), nullable=False),
        sa.Column("price_band", sa.String(length=100), nullable=True),
        sa.Column("grade", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "brand_id",
            "store_id",
            "product_category",
            "price_band",
            name="uq_store_product_grades_unique",
        ),
    )
    op.create_index(
        "idx_store_product_grades_lookup",
        "store_product_grades",
        ["brand_id", "store_id", "product_category", "price_band"],
    )

    op.create_table(
        "size_guides",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_category", sa.String(length=100), nullable=False),
        sa.Column("size", sa.String(length=20), nullable=False),
        sa.Column("size_type", sa.String(length=20), nullable=False, server_default="PIVOTAL"),
        sa.Column("min_max_ratio", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_size_set", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("applies_to_grades", sa.String(length=20), nullable=False, server_default="ALL"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "product_category", "size", name="uq_size_guides_unique"),
    )
    op.create_index(
        "idx_size_guides_lookup",
        "size_guides",
        ["brand_id", "product_category", "display_order"],
    )

    op.create_table(
        "inventory_reservation_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=False),
        sa.Column(
            "deducts_from_first_allocation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "code", name="uq_inventory_reservation_types_brand_code"),
    )
    op.create_index(
        "idx_inventory_reservation_types_brand_id",
        "inventory_reservation_types",
        ["brand_id"],
    )

    op.create_table(
        "buy_plan_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("upload_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("season_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"]),
        sa.ForeignKeyConstraint(["season_id"], ["seasons.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "name", name="uq_buy_plan_files_brand_name"),
    )
    op.create_index("idx_buy_plan_files_brand_id", "buy_plan_files", ["brand_id"])

    op.create_table(
        "buy_plan_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("buy_plan_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sku_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("store_group_rule", sa.String(length=200), nullable=True),
        sa.Column("style_risk_group", sa.String(length=50), nullable=True),
        sa.Column("total_buy_qty", sa.Integer(), nullable=True),
        sa.Column("expected_first_allocation_qty", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["buy_plan_file_id"], ["buy_plan_files.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["sku_id"], ["skus.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "buy_plan_file_id",
            "sku_id",
            "store_group_rule",
            name="uq_buy_plan_lines_file_sku_group",
        ),
    )
    op.create_index("idx_buy_plan_lines_buy_plan_file", "buy_plan_lines", ["buy_plan_file_id"])
    op.create_index("idx_buy_plan_lines_brand_sku", "buy_plan_lines", ["brand_id", "sku_id"])

    op.add_column("skus", sa.Column("store_group_rule", sa.String(length=200), nullable=True))
    op.add_column("skus", sa.Column("resolved_min_grade", sa.String(length=10), nullable=True))
    op.add_column("skus", sa.Column("style_risk_group", sa.String(length=50), nullable=True))
    op.add_column("skus", sa.Column("resolved_risk_level", sa.String(length=20), nullable=True))
    op.add_column("skus", sa.Column("story", sa.String(length=200), nullable=True))
    op.add_column("skus", sa.Column("sub_story", sa.String(length=200), nullable=True))
    op.add_column("skus", sa.Column("buyer_name", sa.String(length=200), nullable=True))
    op.add_column("skus", sa.Column("vendor_name", sa.String(length=200), nullable=True))
    op.add_column("skus", sa.Column("store_list_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_skus_store_list_id_style_store_lists", "skus", "style_store_lists", ["store_list_id"], ["id"])

    op.add_column("grn_lines", sa.Column("buy_plan_line_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("grn_lines", sa.Column("total_buy_qty", sa.Integer(), nullable=True))
    op.add_column(
        "grn_lines",
        sa.Column("ecom_reserved_qty", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "grn_lines",
        sa.Column("ars_reserved_qty", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_foreign_key(
        "fk_grn_lines_buy_plan_line_id_buy_plan_lines",
        "grn_lines",
        "buy_plan_lines",
        ["buy_plan_line_id"],
        ["id"],
    )

    op.create_table(
        "grn_line_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grn_line_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reservation_type_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reserved_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["grn_line_id"], ["grn_lines.id"]),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["reservation_type_id"], ["inventory_reservation_types.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "grn_line_id",
            "reservation_type_id",
            name="uq_grn_line_reservations_unique",
        ),
    )
    op.create_index("idx_grn_line_reservations_line_id", "grn_line_reservations", ["grn_line_id"])

    op.drop_column("stores", "store_grade")


def downgrade() -> None:
    op.add_column(
        "stores",
        sa.Column("store_grade", sa.String(length=5), nullable=False, server_default="C"),
    )

    op.drop_index("idx_grn_line_reservations_line_id", table_name="grn_line_reservations")
    op.drop_table("grn_line_reservations")

    op.drop_constraint("fk_grn_lines_buy_plan_line_id_buy_plan_lines", "grn_lines", type_="foreignkey")
    op.drop_column("grn_lines", "ars_reserved_qty")
    op.drop_column("grn_lines", "ecom_reserved_qty")
    op.drop_column("grn_lines", "total_buy_qty")
    op.drop_column("grn_lines", "buy_plan_line_id")

    op.drop_constraint("fk_skus_store_list_id_style_store_lists", "skus", type_="foreignkey")
    op.drop_column("skus", "store_list_id")
    op.drop_column("skus", "vendor_name")
    op.drop_column("skus", "buyer_name")
    op.drop_column("skus", "sub_story")
    op.drop_column("skus", "story")
    op.drop_column("skus", "resolved_risk_level")
    op.drop_column("skus", "style_risk_group")
    op.drop_column("skus", "resolved_min_grade")
    op.drop_column("skus", "store_group_rule")

    op.drop_index("idx_buy_plan_lines_brand_sku", table_name="buy_plan_lines")
    op.drop_index("idx_buy_plan_lines_buy_plan_file", table_name="buy_plan_lines")
    op.drop_table("buy_plan_lines")

    op.drop_index("idx_buy_plan_files_brand_id", table_name="buy_plan_files")
    op.drop_table("buy_plan_files")

    op.drop_index("idx_inventory_reservation_types_brand_id", table_name="inventory_reservation_types")
    op.drop_table("inventory_reservation_types")

    op.drop_index("idx_size_guides_lookup", table_name="size_guides")
    op.drop_table("size_guides")

    op.drop_index("idx_store_product_grades_lookup", table_name="store_product_grades")
    op.drop_table("store_product_grades")

    op.drop_index("idx_style_store_lists_brand_id", table_name="style_store_lists")
    op.drop_table("style_store_lists")

    op.drop_index("idx_brand_settings_config_gin", table_name="brand_settings")
    op.drop_table("brand_settings")

    # Enum values added in upgrade are left in place, because removing enum
    # labels safely requires recreating dependent types.
