"""Re-run allocation against an existing GRN after the demand-bridge change.

Targets brand1's main SS26-INITIAL-STOCK GRN by default. Drops any prior
allocation session for that GRN (so we don't pin the engine to its old
output via the locked-row guard), then re-runs the engine + the verdict
layer and prints a one-screen comparison.

Usage:
    cd backend
    DATABASE_URL=postgresql+asyncpg://... python -m scripts.rerun_allocation_with_bridge \
        [GRN_ID]
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.models import AllocationLine, AllocationSession, GRN  # noqa: E402
from app.services.allocation.engine import AllocationEngine  # noqa: E402
from app.services.allocation.health import (  # noqa: E402
    AllocationHealthAnalyzer,
    compute_decision,
)


async def main() -> None:
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://kyros:kyros_dev_password@localhost:5432/kyros_dev",
    )
    target_grn_id = sys.argv[1] if len(sys.argv) > 1 else None

    engine = create_async_engine(db_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)

    async with sf() as db:
        if target_grn_id is None:
            grn = (
                await db.execute(
                    select(GRN).order_by(GRN.total_units.desc()).limit(1)
                )
            ).scalars().first()
        else:
            grn = await db.get(GRN, UUID(target_grn_id))

        if grn is None:
            raise SystemExit("No GRN found.")

        print(f"[rerun] Target GRN: {grn.grn_code}  units={grn.total_units}  brand={grn.brand_id}")

        # Drop any prior session + lines so the engine builds fresh.
        prior_sessions = (
            await db.execute(
                select(AllocationSession.id).where(AllocationSession.grn_id == grn.id)
            )
        ).all()
        prior_ids = [row[0] for row in prior_sessions]
        if prior_ids:
            await db.execute(
                delete(AllocationLine).where(AllocationLine.session_id.in_(prior_ids))
            )
            await db.execute(
                delete(AllocationSession).where(AllocationSession.id.in_(prior_ids))
            )
            await db.commit()
            print(f"[rerun] Dropped {len(prior_ids)} prior session(s)")

    print("[rerun] Running engine...")
    async with sf() as db:
        alloc_engine = AllocationEngine()
        session = await alloc_engine.generate(grn.id, grn.brand_id, db)
        await db.commit()
        session_id = session.id

    print("[rerun] Computing health + verdict...")
    async with sf() as db:
        analyzer = AllocationHealthAnalyzer(session_id, grn.brand_id, db)
        report = await analyzer.analyze()
        decision = compute_decision(
            health_score=report.score,
            risks=report.risks,
            context=await analyzer.get_context(),
            sub_scores=report.sub_scores,
            line_diagnostics=report.line_diagnostics,
        )
        # Persist on the session row so the UI picks it up.
        sess = await db.get(AllocationSession, session_id)
        sess.health_score = report.score
        sess.health_report = report.to_json()
        sess.decision = decision
        await db.commit()

    diag = report.line_diagnostics
    print()
    print("─" * 70)
    print(f"  HEALTH SCORE:        {report.score}/100  ({report.label})")
    print(f"  VERDICT:             {decision['verdict']}")
    print(f"  FAILURE CLASS:       {decision.get('failure_class')}")
    print()
    print("  Sub-scores:")
    for key, val in (report.sub_scores or {}).items():
        print(f"    {key:15s} {val:6.1f}")
    print()
    print(f"  Allocated / received: {diag.get('allocated_units'):,} / "
          f"{diag.get('received_units'):,} "
          f"({(diag.get('alloc_to_received_ratio') or 0) * 100:.1f}%)")
    print(f"  Stores receiving:     {diag.get('distinct_stores_with_allocation')} / "
          f"{diag.get('total_active_stores')}")
    print(f"  Confidence:           HIGH={diag.get('high_confidence_lines')}  "
          f"MED={diag.get('moderate_confidence_lines')}  "
          f"LOW={diag.get('low_confidence_lines')}")
    print(f"  GRN ↔ sales overlap:  "
          f"{(diag.get('sku_overlap_with_sales_pct') or 0) * 100:.1f}%")
    print()
    print("  Demand source breakdown:")
    breakdown = diag.get("demand_source_breakdown") or {}
    total = sum(breakdown.values()) or 1
    for src, count in sorted(breakdown.items(), key=lambda kv: -kv[1]):
        print(f"    {src:25s} {count:>8,}  ({count / total * 100:5.1f}%)")
    print()
    if decision.get("blocked_reason"):
        print(f"  Blocked reason: {decision['blocked_reason']}")
        print(f"  Fix:            {decision['fix']}")
    else:
        print("  No blocking issues.")
    print("─" * 70)
    print()
    print(f"[rerun] session_id={session_id}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
