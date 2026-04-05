"""End-to-end allocation generation test - validates Phase 1 completion."""
import pytest
from uuid import UUID, uuid4

from app.models import AllocationStatus
from app.services.allocation.engine import AllocationEngine
from sqlalchemy.ext.asyncio import AsyncSession


async def _build_small_test_grn(db: AsyncSession):
    """Create a one-SKU GRN so E2E tests complete quickly on large pilot databases."""
    from sqlalchemy import select
    from app.models import GRN, GRNLine

    source_grn = (
        await db.execute(
            select(GRN)
            .order_by(GRN.total_skus.asc(), GRN.total_units.asc())
            .limit(1)
        )
    ).scalars().first()
    if source_grn is None:
        return None

    source_line = (
        await db.execute(
            select(GRNLine)
            .where(GRNLine.grn_id == source_grn.id)
            .order_by(GRNLine.units_received.desc())
            .limit(1)
        )
    ).scalars().first()
    if source_line is None:
        return None

    reserved = int(source_line.ecom_reserved_qty or 0) + int(source_line.ars_reserved_qty or 0)
    units_received = max(reserved + 20, 20)

    test_grn = GRN(
        brand_id=source_grn.brand_id,
        grn_code=f"{source_grn.grn_code}-E2E-{uuid4().hex[:8]}",
        grn_date=source_grn.grn_date,
        warehouse_id=source_grn.warehouse_id,
        supplier_name=source_grn.supplier_name,
        status="RECEIVED",
        total_units=units_received,
        total_skus=1,
        season_id=source_grn.season_id,
        upload_id=source_grn.upload_id,
        created_by=source_grn.created_by,
    )
    db.add(test_grn)
    await db.flush()

    db.add(
        GRNLine(
            grn_id=test_grn.id,
            brand_id=source_grn.brand_id,
            sku_id=source_line.sku_id,
            buy_plan_line_id=None,
            units_received=units_received,
            total_buy_qty=units_received,
            ecom_reserved_qty=int(source_line.ecom_reserved_qty or 0),
            ars_reserved_qty=int(source_line.ars_reserved_qty or 0),
        )
    )
    await db.flush()

    return test_grn


@pytest.mark.asyncio
async def test_e2e_allocation_generation_completes(db: AsyncSession):
    """
    Full E2E test: trigger allocation generation and verify it completes successfully.
    This validates that the engine properly calls all methods in sequence and produces valid output.
    """
    test_grn = await _build_small_test_grn(db)
    if test_grn is None:
        pytest.skip("No GRN data found in test database")

    brand_id = test_grn.brand_id
    grn_id = test_grn.id

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
    from sqlalchemy import func, select
    from app.models import AllocationLine
    
    total_allocated = await db.scalar(
        select(func.sum(AllocationLine.final_qty))
        .where(AllocationLine.session_id == session.id, AllocationLine.final_qty > 0)
    ) or 0
    
    assert total_allocated <= test_grn.total_units, \
        f"Inventory cap violated: {total_allocated} allocated > {test_grn.total_units} available"
    
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
    print(f"  - Allocated: {total_allocated} / {test_grn.total_units}")
    print(f"  - Lines with reasoning: {len(lines_with_reasoning)}")


def select_allocation_lines_for_session(session_id: UUID):
    """Helper to construct query for allocation lines."""
    from app.models import AllocationLine
    from sqlalchemy import select
    return select(AllocationLine).where(AllocationLine.session_id == session_id)


@pytest.mark.asyncio
async def test_e2e_allocation_total_does_not_exceed_available(db: AsyncSession):
    """Inventory cap must hold even after cannibalization."""
    from sqlalchemy import select, func
    from app.models import AllocationLine, GRNLine

    grn = await _build_small_test_grn(db)
    if grn is None:
        pytest.skip("No GRN in test database")

    engine = AllocationEngine()
    session = await engine.generate(grn_id=grn.id, brand_id=grn.brand_id, db=db)
    await db.commit()

    # Check cap holds per SKU
    grn_lines = (
        await db.execute(select(GRNLine).where(GRNLine.grn_id == grn.id))
    ).scalars().all()

    for grn_line in grn_lines:
        available = max(
            0,
            int(grn_line.units_received or 0)
            - int(grn_line.ecom_reserved_qty or 0)
            - int(grn_line.ars_reserved_qty or 0),
        )
        allocated = await db.scalar(
            select(func.coalesce(func.sum(AllocationLine.final_qty), 0))
            .where(
                AllocationLine.session_id == session.id,
                AllocationLine.sku_id == grn_line.sku_id,
                AllocationLine.final_qty > 0,
            )
        ) or 0
        assert int(allocated) <= available, (
            f"SKU {grn_line.sku_id}: allocated {allocated} > available {available}"
        )


@pytest.mark.asyncio
async def test_e2e_all_lines_have_reasoning(db: AsyncSession):
    """Every allocation line with qty > 0 must have a non-null reasoning payload."""
    from sqlalchemy import select
    from app.models import AllocationLine
    from app.services.allocation.explainer import normalize_reasoning

    grn = await _build_small_test_grn(db)
    if grn is None:
        pytest.skip("No GRN in test database")

    engine = AllocationEngine()
    session = await engine.generate(grn_id=grn.id, brand_id=grn.brand_id, db=db)
    await db.commit()

    lines = (
        await db.execute(
            select(AllocationLine)
            .where(
                AllocationLine.session_id == session.id,
                AllocationLine.final_qty > 0,
            )
        )
    ).scalars().all()

    assert len(lines) > 0, "No allocation lines generated"

    required_fields = [
        "weekly_ros", "cover_target_weeks", "store_grade", "scale_factor",
        "narrative_demand", "narrative_cap", "confidence_basis",
        "weeks_cover_at_recommended", "size_split",
    ]
    for line in lines:
        assert line.ai_reasoning is not None, f"Line {line.id} has null reasoning"
        normalized = normalize_reasoning(line.ai_reasoning)
        for field in required_fields:
            assert field in normalized, f"Line {line.id} missing field: {field}"


@pytest.mark.asyncio
async def test_store_profiles_built_without_season_id_error(db: AsyncSession):
    """build_all_store_profiles must not raise due to invalid seasonal scoping."""
    from sqlalchemy import select
    from app.models import Season, Brand
    from app.services.allocation.store_profile import build_all_store_profiles

    brand = (await db.execute(select(Brand).limit(1))).scalars().first()
    season = (
        await db.execute(select(Season).where(Season.brand_id == brand.id).limit(1))
    ).scalars().first()

    if brand is None or season is None:
        pytest.skip("No brand or season in test database")

    # Must not raise
    count = await build_all_store_profiles(db=db, brand_id=brand.id, season_id=season.id)
    assert count >= 0  # 0 is valid if no sales history; error would raise, not return 0
