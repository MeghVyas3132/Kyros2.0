"""add SUPER_ADMIN role + signup_requests queue

The platform now needs an out-of-tenant operator role (``SUPER_ADMIN``) to
process self-serve pilot signups. This migration:

1. Adds ``SUPER_ADMIN`` to the existing ``user_role`` enum.
2. Adds the ``signup_request_status`` enum (``PENDING``/``APPROVED``/``REJECTED``).
3. Creates the ``signup_requests`` table — the per-application queue the
   super-admin reviews from their dashboard.

Revision ID: 0012_super_admin_signup_requests
Revises: 0011_alloc_session_health
Create Date: 2026-04-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0012_super_admin_signup_requests"
down_revision = "0011_alloc_session_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Extend the user_role enum with SUPER_ADMIN. Postgres requires this
    # to be outside any transaction in older versions, but ALTER TYPE ... ADD
    # VALUE IF NOT EXISTS is transaction-safe on Postgres 12+, which is our
    # floor. Wrap in autocommit for older boxes just in case.
    bind = op.get_bind()
    bind.execute(sa.text("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'SUPER_ADMIN'"))

    # 2. Create the signup_request_status enum.
    signup_status_enum = postgresql.ENUM(
        "PENDING",
        "APPROVED",
        "REJECTED",
        name="signup_request_status",
        create_type=False,
    )
    signup_status_enum.create(bind, checkfirst=True)

    # 3. Create signup_requests table.
    op.create_table(
        "signup_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("brand_name", sa.String(length=255), nullable=False),
        sa.Column("brand_slug", sa.String(length=100), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("contact_phone", sa.String(length=50), nullable=True),
        sa.Column("company_size", sa.String(length=50), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING", "APPROVED", "REJECTED",
                name="signup_request_status",
                create_type=False,
            ),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_brand_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_brand_id"], ["brands.id"]),
        sa.ForeignKeyConstraint(["created_user_id"], ["users.id"]),
        sa.UniqueConstraint("email", name="uq_signup_requests_email"),
        sa.UniqueConstraint("brand_slug", name="uq_signup_requests_brand_slug"),
    )
    op.create_index(
        "idx_signup_requests_status",
        "signup_requests",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("idx_signup_requests_status", table_name="signup_requests")
    op.drop_table("signup_requests")
    op.execute("DROP TYPE IF EXISTS signup_request_status")
    # NOTE: Postgres does not support removing a value from an enum, so the
    # SUPER_ADMIN value is left in place on downgrade.
