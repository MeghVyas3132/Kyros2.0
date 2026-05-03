"""Wipe all operational data while preserving brands + users + brand_settings.

Order of deletion respects FK chains. Tables touched:

  KEPT  : brands, users, brand_settings
  WIPED : alerts, allocation_lines, allocation_sessions, buy_plan_lines,
          buy_plan_files, grn_lines, grn_line_reservations, grns,
          inventory_reservation_types, inventory_states, performance_snapshots,
          sales_data, season_otb, seasons, size_guides, skus,
          store_behavior_profiles, store_display_capacity,
          store_product_grades, stores, style_store_lists, clusters, uploads

Run:
    cd backend && DATABASE_URL=postgresql+asyncpg://... python -m scripts.clean_db_keep_seeds
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

# Order: leaves → roots. Each row references its FK parents which appear later.
WIPE_TABLES_IN_ORDER = [
    "alerts",
    "allocation_lines",
    "allocation_sessions",
    "performance_snapshots",
    "buy_plan_lines",
    "buy_plan_files",
    "grn_line_reservations",
    "grn_lines",
    "grns",
    "sales_data",
    "inventory_state",
    "store_behavior_profiles",
    "store_display_capacity",
    "store_product_grades",
    "size_guides",
    "season_otb",
    "seasons",
    "skus",
    "style_store_lists",
    "stores",
    "clusters",
    "inventory_reservation_types",
    "uploads",
]


async def _existing_tables(conn) -> set[str]:
    rows = await conn.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
        )
    )
    return {row[0] for row in rows.all()}


async def main() -> None:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://kyros:kyros_dev_password@localhost:5432/kyros_dev",
    )
    engine = create_async_engine(db_url, poolclass=NullPool)

    print(f"[clean] Connecting to {db_url.split('@')[-1]}")
    async with engine.begin() as conn:
        present = await _existing_tables(conn)
        wipe_targets = [t for t in WIPE_TABLES_IN_ORDER if t in present]
        skipped = [t for t in WIPE_TABLES_IN_ORDER if t not in present]
        if skipped:
            print(f"[clean] Note: tables not in schema (skipped): {', '.join(skipped)}")

        # Snapshot before.
        print("\n[clean] Pre-wipe row counts:")
        for table in wipe_targets + ["brands", "users", "brand_settings"]:
            count = (await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()
            print(f"  {table:35s} {count}")

        # TRUNCATE ... CASCADE walks FK arrows for us. CASCADE on these targets
        # is safe — none of brands / users / brand_settings sit downstream of
        # the wipe set, so the cascade stops at the operational tables.
        joined = ", ".join(f'"{t}"' for t in wipe_targets)
        print(f"\n[clean] TRUNCATE {len(wipe_targets)} tables (CASCADE)...")
        await conn.execute(text(f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"))

        print("\n[clean] Post-wipe row counts:")
        for table in wipe_targets + ["brands", "users", "brand_settings"]:
            count = (await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()
            kept = "  ← KEPT" if table in {"brands", "users", "brand_settings"} else ""
            print(f"  {table:35s} {count}{kept}")

        print("\n[clean] Seed credentials retained:")
        rows = (
            await conn.execute(
                text(
                    "SELECT u.email, u.role, b.slug, b.name "
                    "FROM users u JOIN brands b ON b.id = u.brand_id ORDER BY u.created_at"
                )
            )
        ).all()
        if not rows:
            print("  (no users — bootstrap a fresh admin via POST /api/v1/auth/bootstrap)")
        for r in rows:
            print(f"  email={r.email}  role={r.role}  brand={r.slug} ({r.name})")

    await engine.dispose()
    print("\n[clean] Done.")


if __name__ == "__main__":
    asyncio.run(main())
