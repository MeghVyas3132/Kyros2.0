# Run Allocation

Execute an allocation manually and verify the results are correct.

## Usage

When you need to run an allocation, either via API or direct function call, and verify the outputs match expectations.

## Steps

### 1. Verify Prerequisites

Check these tables have data:

```sql
-- 1. GRN/Buy File data
SELECT COUNT(*) FROM grn_line WHERE brand_id = :brand_id;

-- 2. Sales history (critical for demand calculation)
SELECT
    COUNT(*),
    MIN(week_start_date),
    MAX(week_start_date)
FROM sales_data
WHERE brand_id = :brand_id;

-- 3. Store grades
SELECT grade, COUNT(*) FROM store_grades
WHERE brand_id = :brand_id
GROUP BY grade;

-- 4. Size guides (for size curve)
SELECT COUNT(*) FROM size_guides WHERE brand_id = :brand_id;
```

### 2. Trigger Allocation

Option A - Via API:
```
POST /api/v1/allocation/generate
{
  "brand_id": "uuid",
  "name": "Spring 2026 Allocation"
}
```

Option B - Direct function call:
```python
from app.services.allocation.engine import AllocationEngine
from app.services.allocation.demand import DemandCalculationService

# Get dependencies
session_factory = ...  # AsyncSessionLocal
grn_repo = GRNRepository(db)
sales_repo = SalesRepository(db)
store_repo = StoreRepository(db)

# Create engine
demand_svc = DemandCalculationService(sales_repo, store_repo)
engine = AllocationEngine(demand_svc, session_factory)

# Run allocation
result = await engine.generate(
    brand_id=brand_id,
    grn_line_ids=grn_line_ids,
    config=AllocationConfig(
        default_cover_weeks=4,
        enable_size_curves=True
    )
)
```

### 3. Monitor Progress

```sql
-- Check allocation session status
SELECT
    id,
    status,
    created_at,
    started_at,
    completed_at,
    total_styles,
    processed_styles,
    error_message
FROM allocation_sessions
WHERE brand_id = :brand_id
ORDER BY created_at DESC
LIMIT 5;
```

### 4. Verify Output

```sql
-- Check allocation lines were created
SELECT
    COUNT(*) as total_lines,
    SUM(grn_qty) as total_grn,
    SUM(recommended_qty) as total_recommended,
    SUM(final_qty) as total_final,
    AVG(CASE WHEN recommended_qty > 0 THEN 1.0 ELSE 0 END) * 100 as pct_allocated
FROM allocation_lines
WHERE allocation_id = :allocation_id;

-- Check explainability data
SELECT
    COUNT(*) as lines_with_reasoning,
    COUNT(CASE WHEN ai_reasoning IS NULL THEN 1 END) as lines_without_reasoning
FROM allocation_lines
WHERE allocation_id = :allocation_id;

-- Sample some results
SELECT
    al.*,
    s.name as store_name,
    sku.sku_code
FROM allocation_lines al
JOIN stores s ON s.id = al.store_id
JOIN skus sku ON sku.id = al.sku_id
WHERE al.allocation_id = :allocation_id
ORDER BY al.recommended_qty DESC
LIMIT 10;
```

### 5. Validate Reasonableness

Check these metrics:

- **Total GRN qty ≈ Total recommended qty** (should be close if inventory is the cap)
- **Lines with reasoning** should be 100%
- **Zero allocations** should be less than 20% of lines (unless intentional)
- **Grade distribution** should match store grade distribution

### 6. Common Failures

| Failure | Symptom | Fix |
|---------|---------|-----|
| No demand signals | All recommended_qty = 0 | Check sales_data exists for the SKUs |
| Missing reasoning | ai_reasoning is NULL | Check AllocationReasoning construction |
| Over-allocation | recommended > grn_qty * 2 | Grade multiplier double-application |
| Size split errors | Sizes don't add to total | size_curve.py season_id bug |

### 7. Re-run After Fixes

If you fix bugs, re-run:

```sql
-- Delete old allocation
DELETE FROM allocation_lines WHERE allocation_id = :allocation_id;
DELETE FROM allocations WHERE id = :allocation_id;
```

Then trigger new allocation.

## Output Format

When complete, report:
1. Allocation session ID
2. Status (SUCCESS / PARTIAL / FAILED)
3. Total styles processed
4. Total units recommended
5. Any anomalies found
6. Confidence in results
