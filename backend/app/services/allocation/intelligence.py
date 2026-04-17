from typing import Any, Dict
from uuid import UUID



def auto_detect_strategy(
    available_units: int,
    eligible_store_count: int,
    risk_level: str,
    min_depth: int,
) -> str:
    """Auto-detect the depth vs spread strategy."""
    if eligible_store_count == 0 or min_depth == 0:
        return "balanced"
        
    depth_ratio = available_units / (eligible_store_count * min_depth)

    if risk_level == "EXPERIMENTAL" or depth_ratio < 0.5:
        return "depth_first"
    elif depth_ratio >= 1.5:
        return "spread_first"
    else:
        return "balanced"


def prioritize_stores(
    eligible_scores: Dict[UUID, Any],
    available_units: int,
    min_depth: int,
    strategy: str,
) -> Dict[UUID, Any]:
    """
    Narrow the eligible store list to ensure minimum depth.
    """
    if not eligible_scores:
        return {}

    ranked = sorted(
        eligible_scores.items(),
        key=lambda item: item[1].score,
        reverse=True,
    )

    if min_depth <= 0:
        min_depth = 3

    # How many stores can we serve at minimum depth?
    max_stores = max(available_units // min_depth, 1)

    if strategy == "depth_first":
        # Aggressive: serve fewer stores with strong depth
        target_stores = min(max_stores, int(len(ranked) * 0.35))
    elif strategy == "balanced":
        # Default: serve as many as possible at min depth
        target_stores = min(max_stores, int(len(ranked) * 0.65))
    else:  # spread_first
        target_stores = min(max_stores, len(ranked))

    target_stores = max(target_stores, 3)  # always serve at least 3
    target_stores = min(target_stores, len(ranked)) # don't exceed total eligible
    
    return dict(ranked[:target_stores])


def enforce_mva(
    allocations: Dict[UUID, int],
    store_grades: Dict[UUID, str],
    base_mva: int,
    eligible_scores: Dict[UUID, Any],
) -> dict[UUID, int]:
    """
    Remove sub-MVA stores and redistribute freed units upward.
    """
    survivors = {}
    freed_units = 0

    for store_id, qty in allocations.items():
        # Dynamically scale MVA based on store grade (optional basic modifier)
        grade = store_grades.get(store_id, "C")
        grade_multiplier = 1.0
        if grade == "A+": grade_multiplier = 1.5
        elif grade == "A": grade_multiplier = 1.2
        elif grade == "C": grade_multiplier = 0.8
        
        effective_mva = max(int(base_mva * grade_multiplier), 1)

        if qty >= effective_mva:
            survivors[store_id] = qty
        else:
            freed_units += qty  # return to pool

    # Redistribute freed units to top survivors proportionally
    if freed_units > 0 and survivors:
        total_score = sum(
            eligible_scores[sid].score
            for sid in survivors
        )
        # Avoid division by zero
        if total_score > 0:
            for sid in sorted(survivors, key=lambda s: eligible_scores[s].score, reverse=True):
                share = round(freed_units * eligible_scores[sid].score / total_score)
                # Ensure we don't dispense more than we have due to rounding
                share = min(share, freed_units)
                survivors[sid] += share
                freed_units -= share
                if freed_units <= 0:
                    break
        
        # Give remaining loose units to the top store
        if freed_units > 0:
            top_store = max(survivors.keys(), key=lambda s: eligible_scores[s].score)
            survivors[top_store] += freed_units

    return survivors
