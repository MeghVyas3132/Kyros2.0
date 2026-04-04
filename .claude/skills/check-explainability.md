# Check Explainability

Verify the explainability panel shows correct and complete information for allocation reasoning.

## Usage

When the ExplainabilityPanel component shows incomplete, wrong, or missing data, use this skill to diagnose.

## Frontend Component

The ExplainabilityPanel is at:
- `frontend/components/allocation/ExplainabilityPanel.tsx`

It expects `AllocationLine.ai_reasoning` to contain these fields:

```typescript
interface AllocationReasoning {
  weekly_ros: number;              // Rate of sale per week
  raw_weekly_ros?: number;       // Before stockout correction
  ros_source: string;            // e.g., "STORE_SKU", "GRADE_SKU"
  is_stockout_corrected: boolean;
  stockout_week?: number;
  lost_sales_estimate?: number;
  store_grade: string;
  grade_multiplier: number;
  cover_target_weeks: number;
  weeks_cover_at_recommended: number;
  narrative_demand: string;
  confidence_basis: string;
  narrative_adjustments: string;
  narrative_cap: string;
  size_split: Record<string, number>;
  size_distribution_source: string;
  excluded_by_capacity?: boolean;
  exclusion_reason?: string;
}
```

## Debug Checklist

### 1. Check Data Exists in Database

```sql
-- Verify ai_reasoning JSON is populated
SELECT
    id,
    recommended_qty,
    ai_reasoning->>'ros_source' as ros_source,
    ai_reasoning->>'store_grade' as grade,
    ai_reasoning->>'narrative_demand' as demand_narrative,
    ai_reasoning->>'weekly_ros' as ros,
    ai_reasoning->>'size_distribution_source' as size_source
FROM allocation_lines
WHERE allocation_id = :allocation_id
LIMIT 5;
```

### 2. Check Backend Construction

In `engine.py`, find where `ai_reasoning` is constructed. It should include ALL fields used by the frontend:

```python
ai_reasoning = {
    "weekly_ros": demand_signal.weekly_ros,
    "raw_weekly_ros": demand_signal.raw_weekly_ros if demand_signal.is_corrected else None,
    "ros_source": demand_signal.ros_source,
    "is_stockout_corrected": demand_signal.is_corrected,
    "stockout_week": demand_signal.stockout_week,
    "lost_sales_estimate": demand_signal.lost_sales_estimate,
    "store_grade": demand_signal.grade,
    "grade_multiplier": demand_signal.grade_multiplier,
    "cover_target_weeks": config.cover_targets.get(...),
    "weeks_cover_at_recommended": recommended_qty / max(demand_signal.weekly_ros, 0.1),
    "narrative_demand": build_demand_narrative(...),
    "confidence_basis": build_confidence_narrative(...),
    "narrative_adjustments": build_adjustment_narrative(...),
    "narrative_cap": build_inventory_narrative(...),
    "size_split": size_distribution,
    "size_distribution_source": size_source,
}
```

### 3. Check Frontend Parsing

In `ExplainabilityPanel.tsx`, verify null-safety:

```typescript
const r = line.ai_reasoning as AllocationReasoning | null;
if (!r) {
  return <div>No reasoning data available...</div>;
}
```

### 4. Common Issues

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| "No reasoning data" | ai_reasoning is null | Check engine.py constructs reasoning for all lines |
| "Demand narrative unavailable" | narrative_demand missing | Add narrative construction in engine.py |
| Size split not showing | size_split empty or null | Check size_curve.py output |
| Wrong ROS showing | weekly_ros not set correctly | Check demand.py DemandSignal construction |
| Stockout correction not showing | is_stockout_corrected not set | Check demand.py stockout logic |
| Grade showing as "-" | store_grade missing | Check demand signal grade field |

### 5. Verify Size Distribution

Size splits come from `size_curve.py`. Check:

```python
# size_curve.py get_size_distribution()
# Returns: dict[size, percentage]

# If season_id bug affects this, sizes may be empty
```

### 6. Test with Sample Data

```sql
-- Get one line with full reasoning
SELECT
    al.id,
    al.store_id,
    al.sku_id,
    al.recommended_qty,
    al.ai_reasoning
FROM allocation_lines al
WHERE al.allocation_id = :allocation_id
    AND al.ai_reasoning IS NOT NULL
LIMIT 1;

-- Then verify the numbers make sense:
-- weekly_ros * cover_target_weeks ≈ recommended_qty (before cap)
-- size_split percentages should sum to 100%
```

## Output Format

When complete, report:
1. Which fields are missing/null
2. Root cause (frontend vs backend)
3. Specific file/line needing fix
4. Expected vs actual JSON structure
