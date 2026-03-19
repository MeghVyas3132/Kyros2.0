"""
Ingestion flow map:
1) Build normalized dict records in memory (no ORM model instances).
2) Execute PostgreSQL upserts in batches (default 1000 rows).
3) Commit every 10k rows to keep transaction cost bounded.
4) Retry failed batches once with smaller chunks.
5) Continue on irrecoverable batch errors and report skipped ranges.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000
COMMIT_EVERY_N_ROWS = 10000
RETRY_BATCH_SIZE = 500

ProgressCallback = Callable[[int, int], Awaitable[None]]
StatementFactory = Callable[[list[dict]], object]


async def execute_with_batching(
    db: AsyncSession,
    records: list[dict],
    statement_factory: StatementFactory,
    *,
    progress_callback: ProgressCallback | None = None,
    batch_size: int = BATCH_SIZE,
    commit_every: int = COMMIT_EVERY_N_ROWS,
    retry_batch_size: int = RETRY_BATCH_SIZE,
    label: str = "bulk_insert",
) -> tuple[int, int]:
    """
    Execute bulk statements with commit cadence and best-effort retry.

    Returns:
        (inserted_rows, failed_rows)
    """
    if not records:
        return 0, 0

    total = len(records)
    inserted = 0
    failed = 0
    rows_since_commit = 0

    for start in range(0, total, batch_size):
        end = min(start + batch_size, total)
        batch = records[start:end]
        try:
            stmt = statement_factory(batch)
            await db.execute(stmt)
            inserted += len(batch)
            rows_since_commit += len(batch)
        except Exception as batch_error:  # noqa: BLE001
            logger.exception(
                "%s batch failed for rows %d-%d. Retrying with smaller batches.",
                label,
                start,
                end - 1,
            )
            retried_inserted, retried_failed = await _retry_batch(
                db=db,
                batch=batch,
                batch_start=start,
                statement_factory=statement_factory,
                retry_batch_size=retry_batch_size,
                label=label,
                original_error=batch_error,
            )
            inserted += retried_inserted
            failed += retried_failed
            rows_since_commit += retried_inserted

        if rows_since_commit >= commit_every:
            await db.commit()
            rows_since_commit = 0

        if progress_callback is not None:
            await progress_callback(inserted + failed, total)

    await db.commit()

    if progress_callback is not None:
        await progress_callback(total, total)

    return inserted, failed


async def _retry_batch(
    db: AsyncSession,
    batch: list[dict],
    batch_start: int,
    statement_factory: StatementFactory,
    retry_batch_size: int,
    label: str,
    original_error: Exception,
) -> tuple[int, int]:
    inserted = 0
    failed = 0

    for local_start in range(0, len(batch), retry_batch_size):
        local_end = min(local_start + retry_batch_size, len(batch))
        global_start = batch_start + local_start
        global_end = batch_start + local_end - 1
        retry_chunk = batch[local_start:local_end]

        try:
            stmt = statement_factory(retry_chunk)
            await db.execute(stmt)
            inserted += len(retry_chunk)
        except Exception:  # noqa: BLE001
            failed += len(retry_chunk)
            logger.exception(
                "%s retry failed for rows %d-%d. Skipping this chunk. Root error: %s",
                label,
                global_start,
                global_end,
                str(original_error),
            )

    return inserted, failed
