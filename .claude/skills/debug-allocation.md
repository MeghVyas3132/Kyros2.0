# Debug Allocation

Debug the Kyros allocation engine when allocations seem wrong, are zero, or don't match expectations.

## Usage

Given symptoms like "allocations are zero", "allocations seem too low/high", or "explainability panel looks wrong", invoke this skill to systematically diagnose the root cause.

## Debug Checklist

### 1. Check for Blocking Bugs First

There are known bugs that commonly cause allocation issues:

- **size_curve.py:119,133**: References `SalesData.season_id` which doesn't exist
- **demand.py:393 & engine.py:299**: Grade multiplier applied twice (over-inflated demand)
- **allocation.py:177-191**: UNDER_REVIEW falls through to regeneration

### 2. Verify Data Exists in Database

```sql
-- Check buy file data (GRN quantities)
SELECT
    grn.style_code,
    grn.color_code,
    grn.total_quantity,
    COUNT(s.id) as sku_count
FROM grn_line grn
LEFT JOIN skus s ON s.style_id = grn.style_id AND s.color_id = grn.color_id
WHERE grn.brand_id = :brand_id
GROUP BY grn.style_code, grn.color_code, grn.total_quantity
ORDER BY grn.total_quantity DESC
LIMIT 10;

-- Check sales data availability
SELECT
    COUNT(*) as total_sales,
    COUNT(DISTINCT store_id) as stores_with_sales,
    COUNT(DISTINCT sku_id) as skus_with_sales,
    MIN(week_start_date) as earliest_week,
    MAX(week_start_date) as latest_week
FROM sales_data
WHERE brand_id = :brand_id;

-- Check store grades
SELECT
    grade,
    COUNT(*) as store_count
FROM store_grades
WHERE brand_id = :brand_id
GROUP BY grade;
```

### 3. Trace Through Allocation Flow

Read these files in order:

1. **allocation.py** - API endpoint that triggers allocation
2. **engine.py** - Core allocation logic
   - Look for `generate()` method
   - Check demand calculation
   - Check inventory cap application
3. **demand.py** - Demand signal calculation
   - Three-tier fallback: store-specific → grade-average → minimum
   - Stockout correction logic
4. **cap.py** - Inventory capping
   - Grade priority enforcement

### 4. Common Root Causes

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| All allocations zero | Missing sales data or zero GRN quantities | Check buy file upload and sales_data table |
| Allocations way too high | Grade multiplier double-application | Fix demand.py or engine.py (only apply once) |
| Allocations uneven | Store grading wrong or missing | Verify store_grades table populated |
| Size splits wrong | size_curve.py season_id bug | Remove season_id reference |
| Stockout stores getting nothing | Stockout correction overly aggressive | Check demand.py _calculate_stockout_correction |
| UNDER_REVIEW regenerating | allocation.py:177-191 bug | Fix fallthrough logic |

### 5. Verify Explainability Data

If explainability panel is incomplete, check `AllocationReasoning` is being populated:

```python
# In engine.py, look for:
ai_reasoning = {
    "weekly_ros": demand_signal.weekly_ros,
    "ros_source": demand_signal.ros_source,
    "store_grade": demand_signal.grade,
    "grade_multiplier": demand_signal.grade_multiplier,
    # ... should include all fields used in ExplainabilityPanel.tsx
}
```

### 6. Test with Specific Store/SKU

```sql
-- Pick one allocation line and trace its inputs
SELECT
    al.store_id,
    al.sku_id,
    al.grn_qty,
    al.recommended_qty,
    al.final_qty,
    al.ai_reasoning->>'ros_source' as ros_source,
    al.ai_reasoning->>'store_grade' as grade
FROM allocation_lines al
WHERE al.allocation_id = :allocation_id
LIMIT 1;

-- Then trace its demand inputs
SELECT
    sd.week_start_date,
    sd.units_sold,
    sd.was_in_stock
FROM sales_data sd
WHERE sd.sku_id = :sku_id
ORDER BY sd.week_start_date;
```

## Output Format

When complete, report:
1. Root cause identified
2. File(s) and line(s) needing change
3. Suggested fix
4. Testing approach to verify fix
