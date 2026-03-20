"""add store behavior profiles table

Revision ID: 0006_store_profiles
Revises: 0005_alloc_failed
Create Date: 2026-03-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_store_profiles"
down_revision: str | None = "0005_alloc_failed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "store_behavior_profiles",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("brand_id", sa.UUID(), nullable=False),
        sa.Column("store_id", sa.UUID(), nullable=False),
        sa.Column("primary_category_affinity", sa.String(length=100), nullable=True),
        sa.Column("primary_fabric_affinity", sa.String(length=100), nullable=True),
        sa.Column("category_affinity_score", sa.Float(), nullable=True),
        sa.Column("fabric_affinity_score", sa.Float(), nullable=True),
        sa.Column("profile_window_weeks", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "store_id", name="uq_store_behavior_profiles_brand_store"),
    )
    op.create_index("idx_store_behavior_profiles_brand", "store_behavior_profiles", ["brand_id"])
    op.create_index("idx_store_behavior_profiles_store", "store_behavior_profiles", ["store_id"])


def downgrade() -> None:
    op.drop_index("idx_store_behavior_profiles_store", table_name="store_behavior_profiles")
    op.drop_index("idx_store_behavior_profiles_brand", table_name="store_behavior_profiles")
    op.drop_table("store_behavior_profiles")
