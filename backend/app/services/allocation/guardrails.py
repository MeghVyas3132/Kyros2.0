from dataclasses import dataclass
from uuid import UUID

from app.config import get_settings
from app.services.allocation.constants import GRADE_SCORES

@dataclass
class GuardrailResult:
    passed: bool
    warnings: list[str]
    adjustments: dict[UUID, int]  # store_id -> adjusted qty (if capped)

def apply_guardrails(
    allocations: dict[UUID, int],
    available_units: int,
    store_grades: dict[UUID, str],
    brand_config: dict,
) -> GuardrailResult:
    warnings: list[str] = []
    adjusted: dict[UUID, int] = allocations.copy()
    
    # Guard 1: Max single-store concentration (default 30%)
    max_pct = float(brand_config.get("max_store_pct", 0.30))
    max_units = int(available_units * max_pct)
    for store_id, qty in adjusted.items():
        if qty > max_units:
            warnings.append(
                f"Store {store_id} capped from {qty} to {max_units} "
                f"(exceeds {max_pct*100:.0f}% concentration limit)"
            )
            adjusted[store_id] = max_units
            
    # Guard 2: Minimum store count (at least 3 stores for non-experimental)
    if len([q for q in adjusted.values() if q > 0]) < 3 and available_units >= 18:
        warnings.append("Allocation concentrated in fewer than 3 stores")
        
    # Guard 3: Grade-demand coherence
    # A+ store should never get less than C store (unless capped by inventory)
    store_ids = list(adjusted.keys())
    for i, sid_a in enumerate(store_ids):
        qty_a = adjusted[sid_a]
        grade_a = store_grades.get(sid_a, "C")
        score_a = GRADE_SCORES.get(grade_a, 1)
        for j, sid_b in enumerate(store_ids):
            if i == j:
                continue
            qty_b = adjusted[sid_b]
            grade_b = store_grades.get(sid_b, "C")
            score_b = GRADE_SCORES.get(grade_b, 1)
            
            if score_a > score_b and qty_a < qty_b * 0.5 and qty_b > 0:
                warnings.append(
                    f"Grade inversion: {grade_a} store getting <50% of {grade_b} store allocation"
                )
                
    passed = len(warnings) == 0
    return GuardrailResult(passed=passed, warnings=warnings, adjustments=adjusted)
