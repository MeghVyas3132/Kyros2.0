"""End-to-end allocation generation test - validates Phase 1 completion."""
import pytest
from uuid import UUID

from app.models import AllocationStatus
from app.services.allocation.engine import AllocationEngine
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_e2e_allocation_generation_completes(db: AsyncSession):
    """
    Full E2E test: trigger allocation generation and verify it completes successfully.
    This validates that the engine properly calls all methods in sequence and produces valid output.
    """
    # Load a GRN from the pilot data
    from sqlalchemy import select
    from app.models import GRN, AllocationSession

    grns = (await db.execute(select(GRN).limit(1))).scalars().first()
    assert grns is not None, "No GRN data found in test database"
    
    brand_id = grns.brand_id
    grn_id = grns.id

    # Create engine and generate allocation
    engine = AllocationEngine()
    session = await engine.generate(grn_id=grn_id, brand_id=brand_id, db=db)

    # Verify session created
    assert session is not None
    assert session.grn_id == grn_id
    assert session.brand_id == brand_id
    assert session.status in [AllocationStatus.DRAFT, AllocationStatus.UNDER_REVIEW], \
        f"Unexpected status: {session.status}"

    # Verify allocation lines created
    lines = (
        await db.execute(
            select_allocation_lines_for_session(session.id)
        )
    ).scalars().all()
    
    assert len(lines) > 0, "No allocation lines created"
    
    # Verify inventory cap: sum of allocations <= GRN total_units
    from sqlalchemy import func
    from app.models import AllocationLine
    
    total_allocated = await db.scalar(
        select(func.sum(AllocationLine.final_qty))
        .where(AllocationLine.session_id == session.id, AllocationLine.final_qty > 0)
    ) or 0
    
    assert total_allocated <= grns.total_units, \
        f"Inventory cap violated: {total_allocated} allocated > {grns.total_units} available"
    
    # Verify reasoning payloads exist
    lines_with_reasoning = [
        l for l in lines 
        if l.final_qty > 0 and l.ai_reasoning
    ]
    assert len(lines_with_reasoning) > 0, "No reasoning payloads generated"
    
    # Verify reason payload structure
    sample_reasoning = lines_with_reasoning[0].ai_reasoning
    required_fields = [
        'weekly_ros', 'cover_target_weeks', 'store_grade', 'scale_factor',
        'narrative_demand', 'narrative_cap', 'confidence_basis'
    ]
    for field in required_fields:
        assert field in sample_reasoning, f"Missing field in reasoning: {field}"
    
    print(f"✅ E2E Test PASSED")
    print(f"  - Session: {session.id}")
    print(f"  - Lines: {len(lines)}")
    print(f"  - Allocated: {total_allocated} / {grns.total_units}")
    print(f"  - Lines with reasoning: {len(lines_with_reasoning)}")


def select_allocation_lines_for_session(session_id: UUID):
    """Helper to construct query for allocation lines."""
    from app.models import AllocationLine
    from sqlalchemy import select
    return select(AllocationLine).where(AllocationLine.session_id == session_id)
