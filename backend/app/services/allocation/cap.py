from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

TStore = TypeVar("TStore")

GRADE_PRIORITY = {"A+": 0, "A": 1, "B": 2, "C": 3}


def apply_inventory_cap(
    store_demands: dict[TStore, int],
    available_qty: int,
    min_presentation_qty: int,
    store_grades: Mapping[TStore, str] | None = None,
) -> dict[TStore, int]:
    if available_qty <= 0 or not store_demands:
        return {store_id: 0 for store_id in store_demands}

    normalized = {store_id: max(int(qty or 0), 0) for store_id, qty in store_demands.items()}
    total_raw_demand = sum(normalized.values())
    if total_raw_demand <= available_qty:
        return normalized

    scale_factor = available_qty / total_raw_demand
    scaled_demands = {
        store_id: max(0, round(raw_demand * scale_factor))
        for store_id, raw_demand in normalized.items()
    }

    _fix_rounding_difference(
        scaled_demands=scaled_demands,
        raw_demands=normalized,
        target_total=available_qty,
    )

    _enforce_minimums(
        scaled_demands=scaled_demands,
        available_qty=available_qty,
        min_presentation_qty=max(int(min_presentation_qty or 0), 0),
        store_grades=store_grades,
    )

    # Note: Due to minimum presentation constraints, sum may not exactly equal available_qty
    # This is acceptable as minimums take precedence over perfect cap matching
    return scaled_demands


def _fix_rounding_difference(
    scaled_demands: dict[TStore, int],
    raw_demands: Mapping[TStore, int],
    target_total: int,
) -> None:
    total_after_scaling = sum(scaled_demands.values())
    difference = target_total - total_after_scaling
    if difference == 0:
        return

    if difference > 0:
        ranked = sorted(raw_demands.items(), key=lambda item: item[1], reverse=True)
        idx = 0
        while difference > 0 and ranked:
            store_id = ranked[idx % len(ranked)][0]
            scaled_demands[store_id] += 1
            difference -= 1
            idx += 1
        return

    ranked = sorted(scaled_demands.items(), key=lambda item: item[1])
    remaining = abs(difference)
    idx = 0
    while remaining > 0 and ranked:
        store_id, current = ranked[idx % len(ranked)]
        if scaled_demands[store_id] > 0:
            scaled_demands[store_id] -= 1
            remaining -= 1
        idx += 1


def _enforce_minimums(
    scaled_demands: dict[TStore, int],
    available_qty: int,
    min_presentation_qty: int,
    store_grades: Mapping[TStore, str] | None,
) -> None:
    if min_presentation_qty <= 0 or not scaled_demands:
        return

    store_count = len(scaled_demands)
    required_for_all = store_count * min_presentation_qty

    if available_qty >= required_for_all:
        _raise_everyone_to_minimum(
            scaled_demands=scaled_demands,
            min_presentation_qty=min_presentation_qty,
            target_total=available_qty,
        )
    else:
        _allocate_by_grade_priority(
            scaled_demands=scaled_demands,
            min_presentation_qty=min_presentation_qty,
            available_qty=available_qty,
            store_grades=store_grades,
        )


def _raise_everyone_to_minimum(
    scaled_demands: dict[TStore, int],
    min_presentation_qty: int,
    target_total: int,
) -> None:
    for store_id, qty in list(scaled_demands.items()):
        if qty < min_presentation_qty:
            scaled_demands[store_id] = min_presentation_qty

    total = sum(scaled_demands.values())
    if total == target_total:
        return

    if total < target_total:
        ranked = sorted(scaled_demands.items(), key=lambda item: item[1], reverse=True)
        idx = 0
        deficit = target_total - total
        while deficit > 0 and ranked:
            store_id = ranked[idx % len(ranked)][0]
            scaled_demands[store_id] += 1
            deficit -= 1
            idx += 1
        return

    removable = total - target_total
    ranked = sorted(scaled_demands.items(), key=lambda item: item[1], reverse=True)
    idx = 0
    while removable > 0 and ranked:
        store_id = ranked[idx % len(ranked)][0]
        if scaled_demands[store_id] > min_presentation_qty:
            scaled_demands[store_id] -= 1
            removable -= 1
        idx += 1


def _allocate_by_grade_priority(
    scaled_demands: dict[TStore, int],
    min_presentation_qty: int,
    available_qty: int,
    store_grades: Mapping[TStore, str] | None,
) -> None:
    for store_id in list(scaled_demands.keys()):
        scaled_demands[store_id] = 0

    grade_map = store_grades or {}
    ranked_stores = sorted(
        scaled_demands.keys(),
        key=lambda sid: (
            GRADE_PRIORITY.get(str(grade_map.get(sid, "C")).upper(), GRADE_PRIORITY["C"]),
            str(sid),
        ),
    )

    remaining = available_qty
    for store_id in ranked_stores:
        if remaining < min_presentation_qty:
            break
        scaled_demands[store_id] = min_presentation_qty
        remaining -= min_presentation_qty

    if remaining <= 0:
        return

    for store_id in ranked_stores:
        if remaining <= 0:
            break
        scaled_demands[store_id] += 1
        remaining -= 1
