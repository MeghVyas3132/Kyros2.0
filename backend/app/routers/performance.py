from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import PerformanceSnapshot, SKU, Store, User
from app.routers._helpers import envelope

router = APIRouter(prefix="/api/v1/performance", tags=["performance"])


@router.get("/styles")
async def performance_styles(
    season_id: UUID | None = None,
    category: str | None = None,
    store_id: UUID | None = None,
    cluster_id: UUID | None = None,
    status: str | None = None,
    sort_by: str = "sell_through_pct",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 50,
    export: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved_season_id = season_id
    if resolved_season_id is None:
        resolved_season_id = (
            await db.execute(
                select(PerformanceSnapshot.season_id)
                .where(
                    PerformanceSnapshot.brand_id == current_user.brand_id,
                    PerformanceSnapshot.season_id.is_not(None),
                )
                .order_by(PerformanceSnapshot.snapshot_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if resolved_season_id is None:
            return envelope([])

    latest_date = (
        await db.execute(
            select(func.max(PerformanceSnapshot.snapshot_date)).where(
                PerformanceSnapshot.brand_id == current_user.brand_id,
                PerformanceSnapshot.season_id == resolved_season_id,
            )
        )
    ).scalar_one_or_none()
    if latest_date is None:
        return envelope([])

    where_clause = [
        PerformanceSnapshot.brand_id == current_user.brand_id,
        PerformanceSnapshot.season_id == resolved_season_id,
        PerformanceSnapshot.snapshot_date == latest_date,
    ]
    if status:
        where_clause.append(PerformanceSnapshot.style_status == status)
    if store_id:
        where_clause.append(PerformanceSnapshot.store_id == store_id)

    query = (
        select(
            PerformanceSnapshot.sku_id,
            SKU.style_code,
            SKU.style_name,
            SKU.category,
            func.avg(PerformanceSnapshot.ros_7d).label("ros_7d"),
            func.avg(PerformanceSnapshot.sell_through_pct).label("sell_through_pct"),
            func.avg(PerformanceSnapshot.stock_cover_days).label("stock_cover_days"),
            func.sum(PerformanceSnapshot.units_on_hand).label("units_on_hand"),
            func.max(PerformanceSnapshot.days_since_grn).label("days_since_grn"),
            func.max(PerformanceSnapshot.style_status).label("style_status"),
            func.count(func.distinct(PerformanceSnapshot.store_id)).label("stores_exposed"),
            func.sum(case((PerformanceSnapshot.is_stockout.is_(True), 1), else_=0)).label(
                "stores_stockout"
            ),
        )
        .join(SKU, SKU.id == PerformanceSnapshot.sku_id)
        .where(*where_clause)
    )

    if category:
        query = query.where(SKU.category == category)

    if cluster_id:
        query = query.join(Store, Store.id == PerformanceSnapshot.store_id).where(Store.cluster_id == cluster_id)

    query = query.group_by(PerformanceSnapshot.sku_id, SKU.style_code, SKU.style_name, SKU.category)

    sort_map = {
        "ros_7d": "ros_7d",
        "sell_through_pct": "sell_through_pct",
        "stock_cover_days": "stock_cover_days",
        "units_on_hand": "units_on_hand",
        "days_since_grn": "days_since_grn",
    }
    sort_col = sort_map.get(sort_by, "sell_through_pct")
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    query = query.order_by(text(f"{sort_col} {direction}"))

    if not export:
        query = query.offset((page - 1) * page_size).limit(page_size)

    rows = [dict(row._mapping) for row in (await db.execute(query)).all()]

    if export:
        csv_data = pd.DataFrame(rows).to_csv(index=False)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=performance-styles.csv"},
        )

    return envelope(rows)


@router.get("/stores")
async def performance_stores(
    season_id: UUID | None = None,
    category: str | None = None,
    store_id: UUID | None = None,
    cluster_id: UUID | None = None,
    status: str | None = None,
    sort_by: str = "avg_sell_through_pct",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 50,
    export: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resolved_season_id = season_id
    if resolved_season_id is None:
        resolved_season_id = (
            await db.execute(
                select(PerformanceSnapshot.season_id)
                .where(
                    PerformanceSnapshot.brand_id == current_user.brand_id,
                    PerformanceSnapshot.season_id.is_not(None),
                )
                .order_by(PerformanceSnapshot.snapshot_date.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if resolved_season_id is None:
            return envelope([])

    latest_date = (
        await db.execute(
            select(func.max(PerformanceSnapshot.snapshot_date)).where(
                PerformanceSnapshot.brand_id == current_user.brand_id,
                PerformanceSnapshot.season_id == resolved_season_id,
            )
        )
    ).scalar_one_or_none()
    if latest_date is None:
        return envelope([])

    where_clause = [
        PerformanceSnapshot.brand_id == current_user.brand_id,
        PerformanceSnapshot.season_id == resolved_season_id,
        PerformanceSnapshot.snapshot_date == latest_date,
    ]
    if store_id:
        where_clause.append(PerformanceSnapshot.store_id == store_id)
    if status:
        where_clause.append(PerformanceSnapshot.style_status == status)

    query = (
        select(
            Store.id.label("store_id"),
            Store.store_name,
            func.avg(PerformanceSnapshot.sell_through_pct).label("avg_sell_through_pct"),
            func.avg(PerformanceSnapshot.ros_7d).label("avg_ros"),
            func.avg(PerformanceSnapshot.stock_cover_days).label("avg_stock_cover_days"),
            func.count(PerformanceSnapshot.id).label("styles_exposed"),
            func.sum(case((PerformanceSnapshot.style_status == "HEALTHY", 1), else_=0)).label(
                "styles_healthy"
            ),
            func.sum(case((PerformanceSnapshot.style_status == "WATCH", 1), else_=0)).label(
                "styles_watch"
            ),
            func.sum(case((PerformanceSnapshot.style_status == "PROBLEM", 1), else_=0)).label(
                "styles_problem"
            ),
            func.sum(case((PerformanceSnapshot.style_status == "CRITICAL", 1), else_=0)).label(
                "styles_critical"
            ),
            func.sum(case((PerformanceSnapshot.is_stockout.is_(True), 1), else_=0)).label(
                "styles_stockout"
            ),
        )
        .join(Store, Store.id == PerformanceSnapshot.store_id)
        .where(*where_clause)
    )

    if cluster_id:
        query = query.where(Store.cluster_id == cluster_id)
    if category:
        query = query.join(SKU, SKU.id == PerformanceSnapshot.sku_id).where(SKU.category == category)

    query = query.group_by(Store.id, Store.store_name)

    sort_map = {
        "avg_sell_through_pct": "avg_sell_through_pct",
        "avg_ros": "avg_ros",
        "avg_stock_cover_days": "avg_stock_cover_days",
        "styles_exposed": "styles_exposed",
    }
    sort_col = sort_map.get(sort_by, "avg_sell_through_pct")
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    query = query.order_by(text(f"{sort_col} {direction}"))

    if not export:
        query = query.offset((page - 1) * page_size).limit(page_size)

    rows = [dict(row._mapping) for row in (await db.execute(query)).all()]

    if export:
        csv_data = pd.DataFrame(rows).to_csv(index=False)
        return Response(
            content=csv_data,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=performance-stores.csv"},
        )

    return envelope(rows)
