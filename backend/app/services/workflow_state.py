"""Season workflow state machine.

The canonical pre-season → in-season order is:

    DRAFT → PLANNING → BUYING → RECEIVING → ALLOCATING → IN_SEASON → CLOSED

We *only ever advance forward*. Going backwards requires manual intervention
(e.g. a planner explicitly editing the season). The helper here is meant to
be called as a side-effect of milestone events:

  - First OTB row saved          → PLANNING
  - First BuyPlanFile created    → BUYING
  - First GRN created            → RECEIVING
  - Allocation generated         → ALLOCATING (handled in the allocation task)
  - Allocation approved          → IN_SEASON

It's intentionally non-blocking — if a season is already past the requested
target, it stays put. If the season doesn't exist or is for a different
brand, it's a no-op (the caller already validated ownership).
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Season, SeasonStatus

logger = logging.getLogger(__name__)


# Canonical ordering. Any status not in this list is treated as "unknown" and
# never advanced.
_ORDER = [
    SeasonStatus.DRAFT,
    SeasonStatus.PLANNING,
    SeasonStatus.BUYING,
    SeasonStatus.RECEIVING,
    SeasonStatus.ALLOCATING,
    SeasonStatus.IN_SEASON,
    SeasonStatus.CLOSED,
]


def _rank(status: SeasonStatus | None) -> int:
    if status is None:
        return -1
    try:
        return _ORDER.index(status)
    except ValueError:
        return -1


async def advance_season_if_earlier(
    db: AsyncSession,
    *,
    brand_id: UUID,
    season_id: UUID | None,
    target: SeasonStatus,
) -> None:
    """Move the season forward to `target` if it's currently earlier.

    No-ops when:
      - season_id is None (no linked season),
      - season belongs to another brand (defensive),
      - season is already at or past `target`,
      - target isn't in the canonical order.

    Caller is responsible for committing the surrounding transaction. We
    intentionally do not commit here so the milestone-write and the status
    advance land atomically.
    """
    if season_id is None:
        return

    season = await db.get(Season, season_id)
    if season is None or season.brand_id != brand_id:
        return

    target_rank = _rank(target)
    if target_rank < 0:
        return

    current_rank = _rank(season.status)
    if current_rank >= target_rank:
        return

    logger.info(
        "Advancing season %s from %s → %s",
        season.id,
        season.status,
        target,
    )
    season.status = target
