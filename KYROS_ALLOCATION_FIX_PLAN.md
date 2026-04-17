# KYROS ALLOCATION ENGINE — FIX & STABILIZATION PLAN

> **Owner**: Engineering  
> **Target**: Production pilot with Indian retail brand in 30 days  
> **Status**: PRE-PILOT — Critical stabilization required  
> **Last Updated**: April 2026

---

## 1. SYSTEM DIAGNOSIS

### What Works Well

| Capability | Assessment |
|-----------|-----------|
| **5-tier demand fallback** | Solid cold-start strategy. Store → Cluster → Grade → Style DNA → Min Presentation degrades gracefully. |
| **Explainability layer** | Every allocation line carries 30+ field JSONB reasoning. Rare for allocation systems. Directly enables merchandiser trust. |
| **Grade-based cover targets** | The `(risk_level, grade) → weeks` matrix is clean, tunable, and reflects real retail planning. |
| **Reservation system** | `GRNLineReservation` with `deducts_from_first_allocation` handles e-com/ARS holds correctly. |
| **Session state machine** | DRAFT → GENERATING → UNDER_REVIEW → APPROVED → DISPATCHED lifecycle is production-correct. |
| **Benchmark quality scoring** | `benchmark.py` provides override rate, grade compliance, utilization — useful acceptance testing. |
| **Size curve blending** | Historical ratios weighted against brand size guide with 1.5× cap prevents extreme size skew. |

### What Is Fundamentally Broken

| Issue | Root Cause | File Reference |
|-------|-----------|----------------|
| **Demand signals are corrupted** | Synthetic week spreading destroys temporal patterns. Flattens all sales to uniform weekly rate. | `processor.py:409-414` |
| **Sales treated as demand** | System uses `units_sold` (constrained by stock availability) as proxy for true demand. High-performing stores that stock out get systematically under-allocated. | `demand.py:148-182` |
| **Scoring is effectively single-variable** | ROS/Grade/Cover components are on different scales (0.1-50 vs 2-5 vs 0.07-10). ROS dominates at ~95% effective weight. The 50/25/25 weighting is mathematically meaningless. | `engine.py:839-843` |
| **Data loss on re-upload** | Full `DELETE FROM sales_data WHERE brand_id=X` before re-insert. Partial upload failure = total history loss. | `processor.py:362-366` |
| **Partial transaction commits** | `db.commit()` every 500 lines mid-loop. Engine crash leaves orphaned allocation lines and inconsistent session state. | `engine.py:571-574` |

### What Is Risky for Deployment

| Risk | Probability | Impact |
|------|------------|--------|
| Extreme allocation skew (one store gets 80%+ of inventory) | HIGH (un-normalized scoring) | Merchandiser loses trust immediately |
| No warning when stores default to grade C | HIGH (silent fallback) | Incorrect allocations blamed on system |
| CSV export OOM for large datasets | MEDIUM (loads all lines into memory) | System appears broken to user |
| Concurrent allocation runs create conflicts | MEDIUM (no locking) | Duplicate/corrupt allocation data |
| `was_overridden` flag is wrong | HIGH (compares to raw demand, not engine final) | Override analytics are meaningless |

---

## 2. CRITICAL FAILURE POINTS

### FP-1: The "Size-Level Allocation" Fragmentation (MASSIVE ZEROS BUG)

**Location**: `backend/app/services/allocation/engine.py:225` (the main GRN loop)

**Logic**: The engine operates its main algorithm at the `grn_line` level. Each `grn_line` corresponds to a single **Size** of a **Style** (e.g., "BC-EWS...__L").

**Impact**: 
- The system computes minimum demand across all stores (e.g. 184 stores × 2 units = 368 minimum demand).
- The available quantity *per size* is roughly 55 units.
- The scale factor becomes `55 / 368 = 0.149`.
- The final per-store allocation becomes `round(2 × 0.149) = 0`.
- **Result**: The engine fragments the available volume across individual sizes, leading the inventory cap logic to aggressively round everyone down to zero. The system produces almost 100% 0, 1, or 2 unit allocations.

**Real-world failure**: You have a Style with 440 available units across 8 sizes. Instead of allocating ~3 units of the *Style* to each of 150 stores and then breaking it down by size, the system runs 8 independent allocations of 55 units each, resulting in almost every store getting 0 units of every size.

---

### FP-2: Synthetic Time-Series Corruption

**Location**: `backend/app/services/ingestion/processor.py:409-414`

**Logic**: When `week_start_date` is missing, system generates 8 synthetic weeks and spreads `units_sold` uniformly.

**Impact**: 
- ALL stockout detection is disabled (zero-sale weeks never appear)
- Seasonal demand curves are destroyed (summer-only items show consistent year-round rate)
- ROS calculation is artificially flattened

**Real-world failure**: A store sold 200 units of linen shirts in April-May (8 weeks at 25/week), then 0 from June onward. Synthetic spreading shows 25 units across 8 recent weeks → system thinks demand is stable at 25/week when the season is already ending.

---

### FP-3: Un-Normalized Scoring

**Location**: `backend/app/services/allocation/engine.py:839-843`

```python
score = (0.50 * ros_component) + (0.25 * grade_score) + (0.25 * (1 / max(cover, 0.1)))
```

**Impact**: A store with ROS=30 gets score ≈16.43. A store with ROS=0.5 gets score ≈1.68. Grade and cover contribute <5% to the actual score variance. Distribution is effectively "just rank by ROS."

**Real-world failure**: An A+ grade store with 3 days of cover and moderate ROS gets less inventory than a C grade store with 60 days of cover but higher historical sales — because ROS dominates.

---

### FP-4: Winner-Take-All Distribution

**Location**: `backend/app/services/allocation/engine.py:1029-1059`

**Logic**: When stores receive less than `min_units_per_store` (6), they get zero and units go to top-scoring store.

**Impact**: For scarce SKUs (e.g., 30 units across 20 stores), every store falls below minimum → ALL units go to one store. Fashion retail needs broad distribution for brand visibility.

**Real-world failure**: A limited-edition jacket (50 units, 30 eligible stores) ends up entirely at 2 stores. The other 28 stores show empty shelves for this style. Brand perception suffers.

---

### FP-5: Sales ≠ Demand Vicious Cycle

**Location**: `backend/app/services/allocation/demand.py:148-182`

**Logic**: `weekly_ros = total_units_sold / weeks_with_data`

**Impact**: A store that stocked out 4 of 8 weeks shows 50% of its true demand rate. Next allocation gives it 50% of what it needs → stocks out again → even lower future allocation.

**Real-world failure**: Top-performing Mumbai store sells out of denim in 2 weeks. System records only 2 weeks of sales against 8-week window. ROS looks low. Next season allocation is halved. Store stocks out faster. Cycle continues.

---

### FP-6: Full DELETE on Sales Re-Upload

**Location**: `backend/app/services/ingestion/processor.py:362-366`

**Logic**: `DELETE FROM sales_data WHERE brand_id = X` runs before any inserts.

**Real-world failure**: Merchandiser uploads updated sales file. Network drops at 60% progress. Result: 40% of historical sales data is permanently lost. All subsequent allocations are based on incomplete history. No recovery path.

---

### FP-7: `was_overridden` Logic Bug

**Location**: `backend/app/routers/allocation.py:425`

```python
line.was_overridden = payload.final_qty != line.ai_recommended_qty
```

`ai_recommended_qty` is the raw pre-cap demand, not the engine's post-cap `final_qty`. If engine recommended 15 (raw) but set `final_qty=10` (after cap), and user confirms 10, `was_overridden = True` — even though user didn't change anything. This breaks all override analytics and future ML training data.

---

## 3. PILOT RISK ANALYSIS

### What Will Make a Retailer Lose Trust Immediately

| Scenario | Why It Happens | Trust Impact |
|----------|---------------|-------------|
| **"Why did Store X get 200 units and Store Y got 3?"** | Un-normalized scoring + winner-take-all redistribution | 🔴 Instant credibility loss |
| **"The system gave my worst store the same allocation as my best"** | Grade multiplier only applies a 2× range (0.5 to 1.25); ROS differences dwarf grade signal | 🔴 "AI doesn't understand my business" |
| **"We uploaded new data and all our history disappeared"** | Full sales DELETE on re-upload | 🔴 Data trust destroyed |
| **"The numbers changed when we regenerated without changing anything"** | Synthetic weeks computed from `today` — different run date = different week boundaries = different ROS | 🟡 System appears non-deterministic |
| **"We have 500 units and the system only allocated 50"** | Demand-capped allocation with no user feedback about remaining inventory | 🟡 "What's the point of this system?" |
| **"The override analytics say we changed 60% of allocations"** | `was_overridden` bug inflates override rate | 🟡 KPIs are wrong, dashboards lie |

### What Is Acceptable for Pilot

| Limitation | Why It's OK |
|------------|------------|
| Style DNA matching rarely fires | Tier 1-3 cover most cases in pilot |
| Cannibalization factor is fixed at 0.65 | Manual override handles edge cases |
| No inter-store transfers | Pre-season allocation only for pilot |
| No ML-based demand forecasting | Rules-based is fine for V1 |
| Single Celery worker | One brand, one concurrent allocation |

---

## 4. FIX STRATEGY

### PHASE 1 — BLOCKERS (Must Fix Before Any Pilot)

**Timeline**: Days 1-10  
**Goal**: Produce mathematically correct, stable allocations

---

#### 1.1 ARCHITECTURE REFACTOR: Style → Store → Size Flow

**What**: Change the engine's fundamental loop from `Size-Level` to `Style-Level` allocation to prevent demand fragmentation and the "wall of zeros" bug.

**Where**: `backend/app/services/allocation/engine.py` (main generate loop)

**Change**:
```python
# BEFORE (broken):
for grn_line in grn_lines:  # grn_line = 1 size
    # Calculate demand for this size
    # Cap inventory for this size (fails because available is too low per size)

# AFTER (safe):
# 1. Group GRN lines by Style ID
style_groups = group_by_style(grn_lines)

for style_id, sizes_available in style_groups.items():
    total_style_available = sum(sizes_available.values())
    
    # 2. Allocate the STYLE to stores
    style_allocations = allocate_style_to_stores(total_style_available, stores)
    # Result: Store A gets 3 units of Style X
    
    # 3. Distribute the sizes
    for store_id, total_qty_for_store in style_allocations.items():
        size_split = calculate_size_distribution(total_qty_for_store, store_profile, size_guide)
        # Store A gets 1-M, 1-L, 1-XL
```

**Effort**: 3 days

---

#### 1.2 Fix Transaction Safety

**What**: Remove mid-loop `db.commit()`, use single transaction.

**Where**: `backend/app/services/allocation/engine.py:571-574`

**Change**:
```python
# BEFORE (broken):
if len(batch) >= BATCH_SIZE:
    db.add_all(batch)
    await db.commit()      # ← partial commit, crash = inconsistency
    batch.clear()

# AFTER (safe):
if len(batch) >= BATCH_SIZE:
    db.add_all(batch)
    await db.flush()        # ← writes to DB but stays in transaction
    batch.clear()
# Single db.commit() after entire loop completes (already exists at engine.py:~660)
```

**Effort**: 0.5 day

---

#### 1.2 Add Concurrent Run Protection

**What**: Prevent two users from generating allocations for the same GRN simultaneously.

**Where**: `backend/app/services/allocation/engine.py:115-120`

**Change**:
```python
# Add SELECT FOR UPDATE to lock the session row
session = await db.scalar(
    select(AllocationSession)
    .where(
        AllocationSession.grn_id == grn_id,
        AllocationSession.brand_id == brand_id,
    )
    .with_for_update(nowait=True)  # ← fails immediately if another worker holds lock
)
```

Also add a unique partial index to prevent multiple GENERATING sessions:
```sql
CREATE UNIQUE INDEX uq_alloc_session_generating 
ON allocation_sessions (grn_id, brand_id) 
WHERE status = 'GENERATING';
```

**Effort**: 0.5 day

---

#### 1.3 Fix Sales Re-Upload Data Loss

**What**: Replace destructive DELETE+INSERT with idempotent upsert.

**Where**: `backend/app/services/ingestion/processor.py:362-366`

**Change**:
```python
# BEFORE (destructive):
await db.execute(delete(SalesData).where(SalesData.brand_id == brand_id))

# AFTER (safe):
# Remove the DELETE entirely. The upsert at processor.py:496-507 already handles
# ON CONFLICT DO UPDATE. For rows that exist in DB but not in new file, add a 
# post-upload cleanup step that marks them (not deletes):

# After all inserts complete:
await db.execute(
    update(SalesData)
    .where(
        SalesData.brand_id == brand_id,
        SalesData.upload_id != upload_id,  # rows not touched by this upload
    )
    .values(is_stale=True)  # new boolean column, default False
)
```

**Prerequisite**: Add `is_stale` boolean column to `SalesData` model. Allocation engine filters `WHERE is_stale = FALSE`.

**Effort**: 1 day

---

#### 1.4 Normalize Scoring Components

**What**: Scale ROS, grade, and cover to [0,1] before applying weights.

**Where**: `backend/app/services/allocation/engine.py:835-843`

**Change**:
```python
async def score_stores(self, sku, stores, ...) -> dict[UUID, ScoreData]:
    # Step 1: Compute raw values for all stores
    raw_values = {}
    for store in stores:
        ros = float(ros_entry.get("ros", 0))
        grade = GRADE_SCORES.get(store_grade, 2)
        cover_inv = 1 / max(self._attribute_cover(store.id, inventory), 0.1)
        raw_values[store.id] = (ros, grade, cover_inv)
    
    # Step 2: Min-max normalize each component across all stores
    def normalize(values):
        lo, hi = min(values), max(values)
        if hi <= lo:
            return [0.5] * len(values)
        return [(v - lo) / (hi - lo) for v in values]
    
    store_ids = list(raw_values.keys())
    norm_ros = normalize([raw_values[sid][0] for sid in store_ids])
    norm_grade = normalize([raw_values[sid][1] for sid in store_ids])
    norm_cover = normalize([raw_values[sid][2] for sid in store_ids])
    
    # Step 3: Apply weights to normalized components
    for i, store_id in enumerate(store_ids):
        score = (ROS_WEIGHT * norm_ros[i]) + (GRADE_WEIGHT * norm_grade[i]) + (COVER_WEIGHT * norm_cover[i])
        scores[store_id] = ScoreData(score=score, ...)
```

**Effort**: 1 day

---

#### 1.5 Fix `was_overridden` Flag

**What**: Compare override against engine's `final_qty`, not raw demand.

**Where**: `backend/app/routers/allocation.py:425`

**Change**:
```python
# BEFORE:
line.was_overridden = payload.final_qty != line.ai_recommended_qty

# AFTER:
# ai_recommended_qty is the raw demand. The engine's actual recommendation is
# stored in final_qty before the user touches it. We need to compare against
# the PREVIOUS final_qty value.
original_engine_qty = line.final_qty if line.final_qty is not None else line.ai_recommended_qty
line.was_overridden = int(payload.final_qty) != int(original_engine_qty)
```

**Effort**: 0.5 day

---

#### 1.6 Handle Synthetic Weeks Explicitly

**What**: Mark synthetic-spread data clearly. Add data quality warnings. Require real dates for production brands.

**Where**: `backend/app/services/ingestion/processor.py:409-414`

**Change**:
```python
# Add a brand-level setting: allow_synthetic_weeks (default: True for demo, False for production)
brand_config = await _load_brand_config(db, brand_id)
production_mode = brand_config.get("production_mode", False)

parsed_week = _try_parse_week_start_date(row.get("week_start_date"))
if parsed_week is None:
    if production_mode:
        # In production mode, REJECT uploads without dates
        skipped_missing_date += 1
        continue  # skip this row, don't synthesize
    else:
        # Demo/onboarding mode: synthesize but LOG prominently
        if synthetic_week_starts is None:
            synthetic_week_starts = _generate_synthetic_week_starts(SYNTHETIC_SALES_WEEKS)
            logger.warning(
                "SYNTHETIC WEEKING ACTIVE for brand %s upload %s — "
                "demand signals will be approximate",
                brand_id, upload_id
            )
        targets = _spread_units_across_weeks(units_sold, synthetic_week_starts)
```

Also add a `data_quality_flags` field to `AllocationSession`:
```python
session.data_quality_flags = {
    "synthetic_weeks_used": used_synthetic_weeking,
    "synthetic_row_count": synthetic_weeking_rows,
    "total_sales_rows": len(rows),
    "pct_synthetic": round(synthetic_weeking_rows / max(len(rows), 1) * 100, 1),
    "stores_with_no_grade": len(stores_defaulting_to_c),
}
```

**Effort**: 1.5 days

---

#### 1.7 Fix Distribution Bias

**What**: Replace winner-take-all redistribution with proportional floor enforcement.

**Where**: `backend/app/services/allocation/engine.py:1037-1059`

**Change**:
```python
# BEFORE: stores below minimum get zeroed, units go to top store

# AFTER: Proportional redistribution to ALL stores above minimum
final: dict[UUID, int] = {}
below_min: list[UUID] = []

for store_id, qty in raw_distribution.items():
    if qty >= min_units:
        final[store_id] = qty
    else:
        below_min.append(store_id)

if below_min and final:
    redistributable = sum(raw_distribution[store_id] for store_id in below_min)
    # Distribute proportionally to ALL above-minimum stores, not just top
    total_above = sum(final.values())
    if total_above > 0:
        for store_id in final:
            share = final[store_id] / total_above
            final[store_id] += round(redistributable * share)
        # Fix rounding
        diff = available_units - sum(final.values())
        if diff != 0:
            top_store = max(final.keys(), key=lambda sid: eligible_stores[sid].score)
            final[top_store] += diff
```

**Effort**: 0.5 day

---

### PHASE 2 — TRUST & SAFETY

**Timeline**: Days 8-14  
**Goal**: Prevent dangerous outputs, surface data quality issues

---

#### 2.1 Allocation Guardrails

**Where**: New file `backend/app/services/allocation/guardrails.py`

```python
from dataclasses import dataclass

@dataclass
class GuardrailResult:
    passed: bool
    warnings: list[str]
    adjustments: dict[UUID, int]  # store_id → adjusted qty (if capped)

def apply_guardrails(
    allocations: dict[UUID, int],
    available_units: int,
    store_grades: dict[UUID, str],
    brand_config: dict,
) -> GuardrailResult:
    warnings = []
    adjusted = dict(allocations)
    
    # Guard 1: Max single-store concentration (default 30%)
    max_pct = brand_config.get("max_store_pct", 0.30)
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
    for sid_a, qty_a in adjusted.items():
        grade_a = store_grades.get(sid_a, "C")
        for sid_b, qty_b in adjusted.items():
            grade_b = store_grades.get(sid_b, "C")
            if GRADE_SCORES.get(grade_a, 1) > GRADE_SCORES.get(grade_b, 1) and qty_a < qty_b * 0.5:
                warnings.append(
                    f"Grade inversion: {grade_a} store getting <50% of {grade_b} store allocation"
                )
    
    passed = len(warnings) == 0
    return GuardrailResult(passed=passed, warnings=warnings, adjustments=adjusted)
```

**Integration point**: Call after `apply_inventory_cap()` in `engine.py:361-366`.

**Effort**: 2 days

---

#### 2.2 Risk Flags per Allocation Line

**Where**: Extend `build_allocation_reasoning()` in `demand.py:871-988`

Add to the reasoning JSONB:
```python
"risk_flags": {
    "stockout_risk": weeks_cover_at_final < 2.0,
    "over_allocation_risk": final_qty > 3 * weekly_ros * season_weeks_remaining,
    "low_confidence": data_sample_size < 4,
    "no_history": ros_source == "minimum_presentation",
    "heavy_cap_applied": scale_factor < 0.30,
    "grade_defaulted": grade == DEFAULT_GRADE and grade_was_defaulted,
    "synthetic_demand": is_synthetic_data,
}
```

Surface these in the frontend ExplainabilityPanel with color-coded badges.

**Effort**: 1 day

---

#### 2.3 Allocation Health Summary

**Where**: New fields on `AllocationSession` model + API response

```python
# Add to AllocationSession or as computed fields:
session_health = {
    "utilization_pct": round(total_allocated / available_units * 100, 1),
    "stores_receiving_allocation": n_stores_with_qty,
    "stores_at_minimum": n_stores_at_min_presentation,
    "stores_defaulted_to_grade_c": n_stores_defaulted,
    "demand_source_breakdown": {
        "store_historical": n_tier1,
        "cluster_average": n_tier2,
        "grade_average": n_tier3,
        "style_dna": n_tier4,
        "minimum_presentation": n_tier5,
    },
    "data_quality_warnings": [...],
    "skus_fully_allocated": n_skus_100pct,
    "skus_partially_allocated": n_skus_partial,
    "skus_skipped": n_skus_skipped,
}
```

**Effort**: 1.5 days

---

#### 2.4 Confidence Scoring Improvement

**Where**: `backend/app/services/allocation/demand.py` — `build_allocation_reasoning()` L970-977

**Current**: String-based ("High confidence (12w history)") using only `data_sample_size`.

**Improved**:
```python
def calculate_confidence_score(
    ros_source: str,
    data_sample_size: int,
    cap_scale_factor: float,
    is_synthetic: bool,
    is_stockout_corrected: bool,
) -> tuple[str, float]:
    """Returns (tier, numeric_score) where tier is HIGH/MEDIUM/LOW and score is 0-1."""
    
    base_scores = {
        "store_historical": 0.80,
        "cluster_average": 0.55,
        "grade_average": 0.40,
        "style_dna": 0.30,
        "minimum_presentation": 0.10,
    }
    score = base_scores.get(ros_source, 0.10)
    
    # Adjust for sample size
    if data_sample_size >= 12:
        score += 0.15
    elif data_sample_size >= 6:
        score += 0.05
    elif data_sample_size < 4:
        score -= 0.10
    
    # Penalize synthetic data
    if is_synthetic:
        score *= 0.6
    
    # Penalize heavy capping
    if cap_scale_factor < 0.3:
        score -= 0.10
    
    score = max(0.0, min(1.0, score))
    tier = "HIGH" if score >= 0.65 else "MEDIUM" if score >= 0.35 else "LOW"
    return tier, round(score, 3)
```

**Effort**: 1 day

---

#### 2.5 Streaming CSV Export

**Where**: `backend/app/routers/allocation.py:488-531`

**Change**: Replace in-memory DataFrame with streaming response:
```python
from fastapi.responses import StreamingResponse

async def _csv_row_generator(session_id, brand_id, db, include_zero):
    yield "GRN Code,SKU Code,Style Name,Size,Store Code,Store Name,City,Quantity\n"
    
    offset = 0
    batch_size = 5000
    while True:
        lines = await _load_session_lines(session_id, brand_id, db, 
                                           line_limit=batch_size, line_offset=offset)
        if not lines:
            break
        for line in lines:
            qty = line.get("final_qty") or line.get("ai_recommended_qty", 0)
            if not include_zero and int(qty or 0) <= 0:
                continue
            yield f"{grn_code},{line['sku_code']},...,{qty}\n"
        offset += batch_size

return StreamingResponse(_csv_row_generator(...), media_type="text/csv", ...)
```

**Effort**: 1 day

---

### PHASE 3 — ML-READY FOUNDATION

**Timeline**: Days 15-22  
**Goal**: Log decisions, capture outcomes, modularize for future ML

---

#### 3.1 Decision Logging Table

**New table**: `allocation_decision_logs`

```sql
CREATE TABLE allocation_decision_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES allocation_sessions(id),
    brand_id UUID REFERENCES brands(id),
    store_id UUID REFERENCES stores(id),
    sku_id UUID REFERENCES skus(id),
    
    -- Store context
    store_grade VARCHAR(10),
    store_cluster_id UUID,
    store_climate_zone VARCHAR(50),
    
    -- SKU context
    sku_category VARCHAR(100),
    sku_fabric VARCHAR(100),
    sku_price_band VARCHAR(50),
    sku_risk_level VARCHAR(20),
    is_new_sku BOOLEAN DEFAULT FALSE,
    
    -- Demand features
    ros_source VARCHAR(30),
    weekly_ros FLOAT,
    raw_weekly_ros FLOAT,
    is_stockout_corrected BOOLEAN DEFAULT FALSE,
    grade_multiplier FLOAT,
    affinity_multiplier FLOAT DEFAULT 1.0,
    data_sample_size INT DEFAULT 0,
    
    -- Decision
    cover_target_weeks INT,
    season_weeks_remaining INT,
    raw_demand INT,
    final_qty INT,
    available_qty INT,
    cap_scale_factor FLOAT,
    cannibalization_factor FLOAT,
    confidence_score FLOAT,
    composite_store_score FLOAT,
    
    -- Risk flags
    risk_flags JSONB,
    
    -- Outcome (populated later by Celery beat)
    actual_sold_4w INT,
    actual_sold_8w INT,
    actual_sold_eow INT,
    
    -- Override tracking
    was_overridden BOOLEAN DEFAULT FALSE,
    override_qty INT,
    override_reason VARCHAR(100),
    
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_decision_logs_session ON allocation_decision_logs(session_id);
CREATE INDEX idx_decision_logs_brand_store ON allocation_decision_logs(brand_id, store_id);
```

**Integration**: After each allocation line is computed in `engine.py`, append a log row.

**Effort**: 2 days

---

#### 3.2 Outcome Tracking (Celery Beat)

**New task**: `backend/app/tasks/outcomes.py`

```python
@celery_app.task(name="app.tasks.outcomes.track_sellthrough")
def track_sellthrough():
    """
    Runs weekly. For each APPROVED session older than 4 weeks:
    1. Query actual sales for each (store, sku) pair
    2. Populate actual_sold_4w / 8w / eow on decision_logs
    3. Compute ai_was_better on allocation_lines
    """
    # Find sessions approved 4+ weeks ago without outcome data
    sessions = db.query(AllocationSession).filter(
        AllocationSession.status == "APPROVED",
        AllocationSession.approved_at <= now - timedelta(weeks=4),
    ).all()
    
    for session in sessions:
        lines = db.query(AllocationLine).filter_by(session_id=session.id).all()
        for line in lines:
            actual_sales = db.query(func.sum(SalesData.units_sold)).filter(
                SalesData.store_id == line.store_id,
                SalesData.sku_id == line.sku_id,
                SalesData.week_start_date >= session.approved_at,
                SalesData.week_start_date < session.approved_at + timedelta(weeks=4),
            ).scalar() or 0
            
            log = db.query(AllocationDecisionLog).filter_by(
                session_id=session.id, store_id=line.store_id, sku_id=line.sku_id
            ).first()
            if log:
                log.actual_sold_4w = actual_sales
            
            # ai_was_better: compare sell-through rate
            if line.was_overridden and line.final_qty and line.ai_recommended_qty:
                ai_sellthrough = actual_sales / max(line.ai_recommended_qty, 1)
                override_sellthrough = actual_sales / max(line.final_qty, 1)
                line.ai_was_better = ai_sellthrough >= override_sellthrough
```

**Celery beat config**:
```python
celery_app.conf.beat_schedule["weekly-outcome-tracking"] = {
    "task": "app.tasks.outcomes.track_sellthrough",
    "schedule": crontab(day_of_week="monday", hour=5, minute=0),
}
```

**Effort**: 2 days

---

#### 3.3 Modularize Engine

**Current**: `engine.py:generate()` is ~600 lines mixing scoring, demand, distribution, capping, cannibalization, size curves, reasoning, and persistence.

**Target structure**:
```
services/allocation/
├── engine.py              # Orchestrator only (~150 lines)
├── context.py             # AllocationContext dataclass (preloaded data)
├── scorer.py              # Store scoring (normalize + weight)
├── demand.py              # Demand calculation (existing, cleaned up)
├── distributor.py         # Unit distribution logic
├── cap.py                 # Inventory capping (existing)
├── cannibalization.py     # Story concentration logic
├── size_curve.py          # Size distribution (existing)
├── guardrails.py          # Safety checks (new in Phase 2)
├── decision_logger.py     # ML logging (new in Phase 3)
├── constants.py           # Grade scores, cover targets (existing)
└── store_profile.py       # Affinity computation (existing)
```

Data flow:
```
engine.generate()
  ├→ context.build()           # Preload all data maps
  ├→ for each GRN line:
  │   ├→ scorer.score()        # Normalize + weight
  │   ├→ demand.calculate()    # 5-tier fallback
  │   ├→ cannibalization.apply() 
  │   ├→ distributor.distribute()
  │   ├→ cap.apply()           # Inventory cap
  │   ├→ guardrails.check()    # Safety checks
  │   ├→ size_curve.split()    # Size distribution
  │   └→ decision_logger.log() # ML feature capture
  └→ engine.commit()           # Single transaction
```

**Effort**: 3 days

---

### PHASE 4 — IN-SEASON CAPABILITY

**Timeline**: Days 23-30  
**Goal**: Support iterative allocation runs, surface actionable in-season signals

---

#### 4.1 Delta-Based Reallocation

**Concept**: After initial pre-season allocation, support "top-up" allocations when:
- New GRN arrives (additional inventory)
- Replenishment triggered (store running low)

**Architecture**: Reuse existing engine with `mode="TOPUP"` parameter:
```python
class AllocationEngine:
    async def generate(self, grn_id, brand_id, db, mode="FULL"):
        if mode == "TOPUP":
            # Don't reset existing allocations
            # Only allocate ADDITIONAL units from new GRN
            # Skip stores already at cover target
            # Prioritize stores with < 2 weeks cover
```

**Effort**: 2 days

---

#### 4.2 Replenishment Triggers

**New table + Celery beat task**:

```sql
CREATE TABLE replenishment_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID REFERENCES brands(id),
    store_id UUID REFERENCES stores(id),
    sku_id UUID REFERENCES skus(id),
    signal_type VARCHAR(30),  -- STOCKOUT_IMMINENT, BELOW_REORDER, SLOW_MOVER
    current_stock INT,
    weekly_ros FLOAT,
    days_of_cover FLOAT,
    suggested_action VARCHAR(50),  -- REPLENISH, TRANSFER_IN, MARKDOWN
    suggested_qty INT,
    priority VARCHAR(10),  -- HIGH, MEDIUM, LOW
    created_at TIMESTAMPTZ DEFAULT NOW(),
    acknowledged_at TIMESTAMPTZ
);
```

**Logic**:
```python
async def check_replenishment_signals(brand_id, db):
    """Run weekly. Check all active store×SKU pairs for replenishment needs."""
    for store_id, sku_id in active_pairs:
        current_stock = get_current_stock(store_id, sku_id)
        weekly_ros = get_recent_ros(store_id, sku_id, weeks=4)
        days_of_cover = current_stock / max(weekly_ros / 7, 0.01)
        
        if days_of_cover < 7:
            create_signal("STOCKOUT_IMMINENT", priority="HIGH", 
                         suggested_qty=round(weekly_ros * 4))
        elif days_of_cover < 14:
            create_signal("BELOW_REORDER", priority="MEDIUM",
                         suggested_qty=round(weekly_ros * 2))
```

**Effort**: 2 days

---

#### 4.3 Transfer Recommendations

**Concept**: When Store A is overstocked (>3× cover target) and Store B is understocked (<1× cover target) for the same SKU, recommend a transfer.

```python
async def compute_transfer_recommendations(brand_id, db):
    """Identify store-to-store transfer opportunities."""
    for sku_id in active_skus:
        stores_over = []   # (store_id, excess_qty, cover_ratio)
        stores_under = []  # (store_id, deficit_qty, cover_ratio)
        
        for store_id in active_stores:
            cover_ratio = current_cover / cover_target
            if cover_ratio > 3.0:
                excess = current_stock - (weekly_ros * cover_target)
                stores_over.append((store_id, excess, cover_ratio))
            elif cover_ratio < 1.0:
                deficit = (weekly_ros * cover_target) - current_stock
                stores_under.append((store_id, deficit, cover_ratio))
        
        # Match: prioritize highest-deficit stores
        for under_store, deficit, _ in sorted(stores_under, key=lambda x: x[1], reverse=True):
            for over_store, excess, _ in sorted(stores_over, key=lambda x: x[1], reverse=True):
                transfer_qty = min(deficit, excess)
                if transfer_qty >= min_transfer_qty:
                    create_transfer_recommendation(from=over_store, to=under_store, qty=transfer_qty)
```

**Effort**: 2 days

---

## 5. TECHNICAL IMPLEMENTATION DETAILS

### Phase 1 Data Flow (After Fixes)

```
CSV Upload
    │
    ├→ Column auto-mapping (mapping.py)
    ├→ Validation (validator.py — existing)
    ├→ Schema enforcement (NEW: data contract validation)
    │     ├ Production mode: REJECT if week_start_date missing
    │     └ Demo mode: WARN + synthesize
    ├→ Upsert (NOT delete+insert)
    │     └ Mark stale rows from previous upload
    └→ Data quality report persisted to session
    
Allocation Generation
    │
    ├→ Preload all data maps (existing — working well)
    ├→ For each GRN line:
    │     ├→ Compute available qty (existing)
    │     ├→ Filter eligible stores (existing)
    │     ├→ Score stores (FIXED: normalized components)
    │     ├→ Calculate demand (existing 5-tier)
    │     ├→ Apply cannibalization (existing, noted for future improvement)
    │     ├→ Distribute units (FIXED: no winner-take-all)
    │     ├→ Apply inventory cap (existing — working well)
    │     ├→ Apply guardrails (NEW: concentration cap, grade coherence)
    │     ├→ Size distribution (existing, TODO: cache in Phase 3)
    │     ├→ Build reasoning (existing + NEW risk flags)
    │     └→ Log decision (NEW in Phase 3)
    │
    ├→ db.flush() per batch (FIXED: no mid-loop commit)
    ├→ Generate session health summary (NEW)
    └→ Single db.commit() at end
```

### Integration Points

| New Component | Integrates With | How |
|--------------|----------------|-----|
| `guardrails.py` | `engine.py` after `apply_inventory_cap()` | Called as `apply_guardrails(final_allocations, ...)` |
| Normalized scoring | `engine.py:score_stores()` | Replaces existing scoring in-place |
| Decision logger | `engine.py` main loop, after reasoning build | `await decision_logger.log(context, signal, ...)` |
| Outcome tracker | Celery beat schedule | Independent task, reads `allocation_lines` + `sales_data` |
| Data contract | `processor.py` before upsert | Validation gate that rejects/warns before data enters DB |

---

## 6. DATA CONTRACT DESIGN

### Sales Upload Contract

```yaml
sales_data:
  required:
    store_code:
      type: string
      max_length: 50
      validation: must exist in stores table (unless auto_create=true)
      on_failure: SKIP_ROW + log warning
    
    sku_code:
      type: string
      max_length: 100
      validation: must exist in skus table (unless auto_create=true)
      on_failure: SKIP_ROW + log warning
    
    units_sold:
      type: integer
      min: 0
      validation: non-negative integer
      on_failure: SKIP_ROW
  
  strongly_recommended:
    week_start_date:
      type: date
      format: "YYYY-MM-DD" or "DD/MM/YYYY" or "MM/DD/YYYY"
      validation: must be a Monday; auto-adjust to nearest Monday if not
      on_failure:
        production_mode: REJECT_UPLOAD with message
        demo_mode: SYNTHESIZE + log warning
    
    was_in_stock:
      type: boolean
      values: true/false, yes/no, 1/0
      default: null (not True — explicit unknown)
      on_failure: DEFAULT_TO_NULL
  
  optional:
    revenue: { type: float, min: 0, on_failure: SET_NULL }
    was_on_promotion: { type: boolean, default: false }

  upload_level_rules:
    - REJECT if < 100 total rows (likely wrong file)
    - REJECT if > 50% of rows have zero units_sold (likely inventory, not sales)
    - WARN if < 4 distinct weeks (low temporal resolution)
    - WARN if > 30% of store_codes not found (possible code format mismatch)
    - WARN if > 20% of sku_codes not found
```

### GRN Upload Contract

```yaml
grn_data:
  required:
    grn_code: { type: string, max_length: 100 }
    grn_date: { type: date }
    sku_code: { type: string, must_exist_in: skus }
    units_received: { type: integer, min: 1 }
  
  optional:
    ecom_reserved_qty: { type: integer, min: 0, default: 0 }
    ars_reserved_qty: { type: integer, min: 0, default: 0 }
    warehouse_id: { type: string }
  
  upload_level_rules:
    - REJECT if any sku_code not found in skus table
    - WARN if total_units < 50 (suspiciously small GRN)
    - REJECT if grn_date is in the future
```

---

## 7. DECISION SAFETY LAYER

### Guardrail Matrix

| Guardrail | Threshold | Action | Default |
|-----------|-----------|--------|---------|
| **Max store concentration** | Single store gets > X% of available | Cap to X%, redistribute excess | 30% |
| **Min store count** | Fewer than 3 stores receiving allocation | Warn in session health | 3 |
| **Grade inversion** | A+ store gets < 50% of C store for same SKU | Warn in reasoning | 50% |
| **Over-allocation risk** | `final_qty > 3 × weekly_ros × season_weeks` | Flag as "over_allocation_risk" | 3× |
| **Stockout risk** | `weeks_cover_at_final < 2.0` | Flag as "stockout_risk" | 2 weeks |
| **Demand source quality** | > 50% of lines use tier 4/5 demand | Warn in session health | 50% |
| **Utilization anomaly** | < 60% of available inventory allocated | Warn in session health | 60% |

### Implementation

All guardrails configurable per brand via `brand_settings.config.allocation.guardrails`:

```json
{
  "allocation": {
    "guardrails": {
      "max_store_concentration_pct": 0.30,
      "min_receiving_stores": 3,
      "grade_inversion_threshold": 0.50,
      "over_allocation_multiplier": 3.0,
      "stockout_risk_weeks": 2.0,
      "low_confidence_source_warn_pct": 0.50,
      "min_utilization_pct": 0.60
    }
  }
}
```

---

## 8. DEMAND MODEL IMPROVEMENT (NO ML)

### Stockout-Aware Demand Estimation

**Current problem**: `weekly_ros = total_sold / weeks_with_data` counts stockout weeks as zero-demand weeks, deflating the rate.

**Fix**: Weight weeks by `was_in_stock`:

```python
def calculate_adjusted_ros(weekly_sales: list[tuple[date, int, bool]]) -> float:
    """
    weekly_sales: list of (week_date, units_sold, was_in_stock)
    Returns: stockout-adjusted weekly ROS
    """
    in_stock_weeks = [(units, in_stock) for _, units, in_stock in weekly_sales if in_stock]
    
    if len(in_stock_weeks) >= 3:
        # Use only in-stock weeks for ROS calculation
        return sum(u for u, _ in in_stock_weeks) / len(in_stock_weeks)
    
    # Not enough in-stock weeks — use all weeks but apply correction factor
    all_weeks_ros = sum(u for _, u, _ in weekly_sales) / max(len(weekly_sales), 1)
    in_stock_ratio = len(in_stock_weeks) / max(len(weekly_sales), 1)
    
    if in_stock_ratio < 0.5:
        # More than half the time out of stock — extrapolate from in-stock periods
        if in_stock_weeks:
            return sum(u for u, _ in in_stock_weeks) / len(in_stock_weeks)
    
    return all_weeks_ros
```

### Trend Weighting

**Add recency bias**: Recent weeks count more than older weeks.

```python
def recency_weighted_ros(weekly_sales: list[tuple[date, int]], decay: float = 0.85) -> float:
    """
    More recent weeks get higher weight.
    decay=0.85 means each older week counts 85% of the next.
    """
    # Sort by date descending (most recent first)
    sorted_sales = sorted(weekly_sales, key=lambda x: x[0], reverse=True)
    
    weighted_sum = 0.0
    weight_sum = 0.0
    for i, (_, units) in enumerate(sorted_sales):
        weight = decay ** i
        weighted_sum += units * weight
        weight_sum += weight
    
    return weighted_sum / max(weight_sum, 0.01)
```

### Confidence Scoring

Map each demand signal to a numeric confidence:

| Source | Base Score | Sample Adjustment | Final Range |
|--------|-----------|-------------------|-------------|
| Store historical (12+ weeks) | 0.80 | +0.15 | 0.85-0.95 |
| Store historical (6-11 weeks) | 0.80 | +0.05 | 0.75-0.85 |
| Store historical (<6 weeks) | 0.80 | -0.10 | 0.60-0.70 |
| Cluster average | 0.55 | by store count | 0.45-0.65 |
| Grade average | 0.40 | by store count | 0.30-0.50 |
| Style DNA | 0.30 | by similarity score | 0.20-0.40 |
| Minimum presentation | 0.10 | none | 0.10 |

Penalize by 40% if synthetic data is used. Penalize by 10% if heavy cap (scale < 0.3) applied.

---

## 9. LOGGING & FUTURE ML DESIGN

### What to Log (Per Decision)

| Category | Fields | Purpose |
|----------|--------|---------|
| **Context** | session_id, brand_id, store_id, sku_id, timestamp | Identify the decision |
| **Store features** | grade, cluster_id, climate_zone, opening_days | Store-level ML features |
| **SKU features** | category, fabric, price_band, risk_level, is_new | Product-level ML features |
| **Demand signals** | ros_source, weekly_ros, raw_ros, sample_size, grade_mult, affinity_mult | Feature vector for demand model |
| **Decision** | cover_target, raw_demand, final_qty, cap_factor, confidence | What the system decided |
| **Competition** | competing_colorways, total_skus_at_store | Cannibalization features |
| **Risk** | risk_flags JSONB | Safety signals |
| **Outcome** | actual_sold_4w, 8w, eow (populated later) | Training labels |
| **Override** | was_overridden, override_qty, override_reason | Human feedback signal |

### How This Enables Future ML

```
Phase A (Now): Log decisions → build dataset
Phase B (3 months): Train offline model on logged data
  - Target: predict sell-through rate from features
  - Model: LightGBM / XGBoost regressor
  - Features: store_grade, ros_source, weekly_ros, category, risk_level, etc.
  - Label: actual_sold_4w / final_qty (sell-through rate)

Phase C (6 months): Shadow mode
  - Run ML model alongside rules engine
  - Log both recommendations
  - Compare accuracy without affecting production

Phase D (9 months): A/B test
  - Split allocation: 50% rules, 50% ML
  - Measure sell-through difference
  - Graduate to ML if ≥5% improvement
```

---

## 10. SUCCESS METRICS

### What "Working System" Means

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Allocation accuracy** | >70% of allocated units sell within season | `actual_sold_eow / final_qty` |
| **Override rate** | <20% of lines manually overridden | `was_overridden` count / total lines |
| **Utilization** | >90% of available inventory allocated | Session health summary |
| **Grade compliance** | >98% of lines respect min_grade rule | Benchmark report |
| **Time-to-allocate** | <10 minutes for 162 stores × 3,500 SKUs | Celery task duration logging |
| **System availability** | Zero data-loss incidents in pilot | Upload failure monitoring |
| **User trust (qualitative)** | Merchandiser says "allocations make sense" | Weekly pilot check-in |

### Pilot KPIs (First 30 Days)

1. **Week 1**: System produces allocation → merchandiser reviews → <30% manual overrides
2. **Week 2**: Second allocation run → user notices improvement from feedback
3. **Week 4**: Compare AI vs. override sell-through → show `ai_was_better` stats
4. **Month 1**: Produce a report: "AI allocation outperformed manual on X% of overrides"

---

## 11. EXECUTION PRIORITY

### Summary Timeline

```
Day  1 ────── Day 7 ────── Day 14 ────── Day 22 ────── Day 30
│  PHASE 1   │  PHASE 2    │   PHASE 3    │   PHASE 4    │
│  BLOCKERS  │  TRUST      │   ML-READY   │   IN-SEASON  │
│            │  & SAFETY   │   FOUNDATION │   CAPABILITY │
```

### Task-Level Priority

| Priority | Task | Phase | Effort | Dependencies |
|----------|------|-------|--------|-------------|
| **P0** | Fix mid-loop commit → flush | 1 | 0.5d | None |
| **P0** | Add concurrent run lock | 1 | 0.5d | None |
| **P0** | Fix sales re-upload data loss | 1 | 1d | Add `is_stale` column |
| **P0** | Normalize scoring components | 1 | 1d | None |
| **P0** | Fix `was_overridden` flag | 1 | 0.5d | None |
| **P0** | Handle synthetic weeks explicitly | 1 | 1.5d | Brand settings update |
| **P0** | Fix distribution bias | 1 | 0.5d | None |
| **P1** | Allocation guardrails | 2 | 2d | Normalized scoring |
| **P1** | Risk flags per line | 2 | 1d | None |
| **P1** | Session health summary | 2 | 1.5d | Guardrails |
| **P1** | Confidence scoring improvement | 2 | 1d | None |
| **P1** | Streaming CSV export | 2 | 1d | None |
| **P2** | Decision logging table | 3 | 2d | Schema migration |
| **P2** | Outcome tracking Celery beat | 3 | 2d | Decision logging |
| **P2** | Engine modularization | 3 | 3d | All Phase 1 fixes |
| **P3** | Delta-based reallocation | 4 | 2d | Modularized engine |
| **P3** | Replenishment triggers | 4 | 2d | Inventory snapshot |
| **P3** | Transfer recommendations | 4 | 2d | Replenishment |

### Critical Path

```
[Fix commit] ──→ [Fix scoring] ──→ [Fix distribution] ──→ [Guardrails] ──→ [Decision logging]
[Fix sales upload] ──→ [Handle synthetic weeks] ──→ [Data contract]
[Fix was_overridden] ──→ [Confidence scoring] ──→ [Outcome tracking]
```

**Phase 1 is fully parallelizable** — each fix is independent. A single engineer can complete all 7 items in 5 working days. Two engineers can do it in 3.

---

> **This document is a living plan. Update after each phase completion.**
