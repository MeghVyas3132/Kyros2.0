# KYROS — Complete Forensic Analysis Report
### Status: Ship-Blocker Review | Every File Audited Against Spec

---

## Executive Summary

The product has **solid bones**: schema is well-designed, the ingestion pipeline is architecturally sound, the frontend components are clean, and the data model matches the spec. However there are **7 ship-blocking bugs**, **6 reliability failures**, **12 correctness/UX issues**, and significant dead code that must be resolved before any pilot. The single most dangerous bug is a "split-brain" in the allocation engine where the production code path silently bypasses all the sophisticated logic that was written.

---

## Priority Legend

| Level | Meaning |
|---|---|
| **P0** | Will crash or produce wrong allocations in production. Do not ship. |
| **P1** | Will fail under realistic data volumes or multi-process deployment. |
| **P2** | Wrong behavior, bad UX, or accumulating technical debt. |
| **DEAD** | Unused, orphaned, or stub code that should be deleted or completed. |
| **SEC** | Security vulnerability. |

---

## P0 — Ship Blockers

---

### P0-1 · Allocation Engine "Split Brain" — `backend/app/services/allocation/engine.py`

**The most critical bug in the entire codebase.**

`AllocationEngine.generate()` contains its own complete inline implementation. It does **not** call the class's own `filter_eligible()`, `score_stores()`, `distribute_units()`, `apply_constraints()`, `apply_size_curves()`, or `generate_reasoning()` methods. Those methods are fully implemented but completely dead.

**What the active `generate()` path SKIPS:**

| Dead Method | What It Was Supposed To Do |
|---|---|
| `filter_eligible()` | Climate zone check, display capacity check, store-specific list filtering |
| `score_stores()` | ROS × grade × cover composite scoring per store |
| `distribute_units()` / `_distribute_standard()` / `_distribute_concentrated()` | Risk-tiered distribution (PROVEN vs EXPERIMENTAL) |
| `apply_constraints()` | Hard display capacity ceiling enforcement |
| `apply_size_curves()` | Grade-based size eligibility (`applies_to_grades`) |
| `generate_reasoning()` | Full per-line reasoning with cluster benchmarking |
| `_season_weeks_remaining()` | Dynamic weeks calculation from season end date |
| `_load_latest_inventory()` | Warehouse inventory state |
| `_load_ros_by_attribute()` | ROS by fabric+category+price_band combination |

**Consequence in production:**
- Climate zone rules are ignored — wool to South India in summer will be allocated
- Display capacity is never enforced — a store with capacity for 40 Kurta styles can receive 200
- Store-specific lists (`sku.store_list_id`) are ignored in the active path
- `EXPERIMENTAL` styles are not concentrated — they scatter to all stores like `PROVEN` styles
- The brilliant cover-target system (`DEFAULT_COVER_TARGETS`) only partially executes — `_cover_target_weeks()` is called, but `score_stores()` (which feeds it) is dead

**Fix:** Wire `generate()` to call `filter_eligible()` → `score_stores()` → `distribute_units()` → `apply_constraints()` → `apply_size_curves()` in sequence, removing the duplicate inline logic. The dead methods are the better implementation.

---

### P0-2 · Buy File Re-Upload Destroys Existing Allocations — `backend/app/services/ingestion/processor.py`

In `_upsert_buy_file()`, every re-upload deletes the GRN and its lines:

```python
existing_grn = await db.scalar(
    select(GRN).where(GRN.brand_id == brand_id, GRN.grn_code == "SS26-INITIAL-STOCK")
)
if existing_grn is not None:
    # deletes GRN lines, reservations, then the GRN itself
    await db.delete(existing_grn)
    await db.flush()
```

`AllocationSession` has `grn_id UUID NOT NULL REFERENCES grns(id)` with **no `ON DELETE CASCADE`**. The second buy file upload will either:
1. Raise a foreign key violation (crash with HTTP 500 if an allocation session exists), OR
2. Leave allocation sessions orphaned pointing to a non-existent GRN

Both outcomes are silent data corruption in production.

**Fix:** Before deleting the GRN, delete or re-parent any allocation sessions. Better: use upsert on GRN lines instead of delete-and-recreate.

---

### P0-3 · Season Hardcoded to "SS26" — `backend/app/services/ingestion/processor.py`

```python
season = Season(
    brand_id=brand_id,
    name="SS26",
    start_date=date(2026, 3, 1),
    end_date=date(2026, 9, 30),
    status=SeasonStatus.ACTIVE,
)
```

This is in `_upsert_buy_file()`. Any brand not running SS26 — any brand running AW26, SS27, or a fiscal-year season — gets silently mis-assigned. Their allocations will calculate `season_weeks_remaining` against wrong dates, producing completely wrong cover targets.

The GRN code is also hardcoded:
```python
grn = GRN(..., grn_code="SS26-INITIAL-STOCK", ...)
```
This means only **one buy file can ever exist** per brand, ever. A second season is impossible.

**Fix:** Derive season name from the `buy_plan_name` column in the upload. Fall back to the brand's currently ACTIVE season. Never hardcode dates or codes.

---

### P0-4 · Refresh Token Store is In-Memory — `backend/app/routers/auth.py`

```python
refresh_token_store: dict[str, str] = {}  # module-level global
```

This is a process-local Python dict. Consequences:
- Every Gunicorn/uvicorn worker has its own copy — tokens issued by worker A are invalid on worker B
- Restarting the backend invalidates every logged-in user's session
- Horizontal scaling is impossible

The spec explicitly says refresh tokens should be stored in Redis with HttpOnly cookies.

**Fix:** Replace with Redis-backed store using `settings.redis_url`. Key: `refresh_token:{token_hash}`, value: `user_id`, TTL: 30 days.

---

### P0-5 · Blocking Subprocess Call Inside Async Endpoint — `backend/app/tasks/uploads.py`

```python
async def process_upload_with_fallback(upload_id: str, brand_id: str) -> dict:
    try:
        ...
    except Exception:
        process_upload_sync(upload_id, brand_id)  # ← called from async context
```

`process_upload_sync()` calls `_run_upload_subprocess()` which calls:
```python
subprocess.run([sys.executable, "-m", "app.tasks.upload_runner", upload_id],
               check=True, capture_output=True, ...)
```

`subprocess.run()` is a **synchronous blocking call**. When Celery is unavailable (common in dev), every upload blocks the entire FastAPI event loop for the duration of the upload. No other requests can be served during this time. For a 100k-row sales file, this could be 30–120 seconds of complete server lockout.

**Fix:** Use `asyncio.create_subprocess_exec()` or call `process_upload()` directly with `asyncio.run_in_executor()`.

---

### P0-6 · N+1 Query Catastrophe in `build_inventory_snapshots` — `backend/app/services/inventory/snapshot.py`

The snapshot builder loops over every (store, SKU) pair and makes **4 separate database queries per pair**:

```python
for store_id, sku_id in pairs:
    recent_inv = await db.execute(...)   # Query 1 — latest inventory
    sales_7d   = await db.execute(...)   # Query 2 — 7-day sales
    sales_28d  = await db.execute(...)   # Query 3 — 28-day sales
    latest_grn = await db.execute(...)   # Query 4 — last GRN date
```

At pilot scale (200 stores × 2000 SKUs = 400k pairs): **1.6 million queries per nightly run**. This will time out. Even at 50 stores × 500 SKUs it is 100k queries — already impractical.

**Fix:** Batch all four metrics in a single CTE or use window functions. Load all relevant sales aggregated by (store, sku, date_bucket) in one query, join to inventory state, compute everything set-based.

---

### P0-7 · `generate()` Silently Regenerates UNDER_REVIEW Sessions — `backend/app/routers/allocation.py`

```python
if existing.status == AllocationStatus.GENERATING:
    return envelope(existing)   # guarded
if existing.status == AllocationStatus.APPROVED:
    return envelope(existing)   # guarded
# UNDER_REVIEW falls through — gets regenerated silently
```

A planner spends an hour reviewing and adjusting allocations. Their colleague clicks "Generate" again. All their work is wiped. There is no warning, no error, no confirmation.

**Fix:** Add `if existing.status == AllocationStatus.UNDER_REVIEW: raise HTTPException(409, ...)` with a meaningful message.

---

## P1 — Reliability Failures

---

### P1-1 · N+1 in `_calculate_stockout_correction` — `backend/app/services/allocation/demand.py`

`calculate_store_demand_details()` calls `_calculate_stockout_correction()` once per (store, category, season) combination. In `engine.py`, this is called via `asyncio.gather()` for all eligible stores per SKU:

```python
demand_tasks = [calculate_store_demand_details(...) for store in eligible_stores]
demand_signals = await asyncio.gather(*demand_tasks)
```

Each `calculate_store_demand_details` call makes a DB query for stockout correction. For 184 stores × 10 categories = **1840 DB queries per GRN line** just for stockout correction, multiplied by the number of SKUs in the GRN. This explains why allocations take 129+ seconds and will get worse with more data.

**Fix:** Batch-load all (store, category) stockout signals for the brand in one query before the allocation loop starts. Pass the results as a map into `calculate_store_demand_details`.

---

### P1-2 · N+1 in `list_sessions` — `backend/app/routers/allocation.py`

```python
for session in sessions:
    grn = await db.get(GRN, session.grn_id)  # one query per session
```

For a brand with 50 allocation sessions, this is 50 sequential DB round-trips.

**Fix:** Collect all `grn_id` values first, load with `select(GRN).where(GRN.id.in_(grn_ids))`, build a dict.

---

### P1-3 · No Pagination on Any List Endpoint

`/api/v1/stores`, `/api/v1/skus`, `/api/v1/grns`, `/api/v1/uploads` all return the complete dataset with no `limit`/`offset`. A brand with 500 stores and 5000 SKUs will return multi-MB JSON responses on every page load.

The spec (section 9, Rate Limits) and the README list pagination as standard. It is defined in the Pydantic schemas (`meta.page`, `meta.per_page`, `meta.total`) but never implemented in the routers.

**Fix:** Add `page: int = 1, page_size: int = 50` query params to all list endpoints. Return proper `meta` pagination envelope.

---

### P1-4 · `_run_simple_mode_jobs` Runs After Every Sales/Inventory/GRN Upload — `backend/app/services/ingestion/processor.py`

```python
if upload.upload_type.value in {"SALES", "INVENTORY", "GRN"}:
    await _run_simple_mode_jobs(db, upload.brand_id)
```

`_run_simple_mode_jobs` calls `build_snapshot_for_brand()` (already identified as catastrophically slow), `build_performance_snapshots()`, and `generate_alerts()`. For every single upload — including incremental daily sales files — the entire snapshot and alert pipeline re-runs synchronously inside the upload task. This compounds P0-6 into every upload.

**Fix:** Remove from the upload path entirely. These are scheduled nightly Celery jobs and should only run on schedule (or be manually triggered by admins for backfills).

---

### P1-5 · Duplicate Constant Definitions

`GRADE_SCORES` is defined in both:
- `backend/app/services/allocation/engine.py`: `{"A+": 5, "A": 4, "B": 3, "C": 2}`
- Referenced/expected in `PILOT_DATA_CHANGES.md`

`DEFAULT_GRADE = "C"` is defined in both:
- `backend/app/services/allocation/engine.py`
- `backend/app/services/allocation/demand.py`

`GRADE_MULTIPLIERS` is in `demand.py` only, but its values are implied (not shared) with `engine.py`'s `GRADE_SCORES`.

If anyone changes a value in one place, the other silently diverges. This has already happened — `demand.py` has `GRADE_MULTIPLIERS: dict[str, float] = {"A+": 1.25, "A": 1.00, "B": 0.75, "C": 0.50}` while `engine.py` uses `GRADE_SCORES` with completely different integer values for a different purpose (scoring, not multiplying).

**Fix:** Create `backend/app/services/allocation/constants.py`. Define `GRADE_SCORES`, `DEFAULT_GRADE`, `GRADE_MULTIPLIERS`, `DEFAULT_COVER_TARGETS`, `MINIMUM_ALLOCATION_QTY` once. Import everywhere.

---

### P1-6 · ROS Units Inconsistency — `demand.py` vs `inventory_state`

`demand.py` calculates and uses **weekly ROS** (units per week):
```python
weekly_ros = units_sold / distinct_weeks  # units/week
```

`InventoryState.ros_7d` is stored as **daily ROS** (units per day):
```python
ros_7d = units_sold_7d / days_in_stock_7d  # units/day
```

`engine.py` correctly uses `weekly_ros` from demand for its cover calculation:
```python
weeks_cover = (final_qty / signal.weekly_ros) if signal.weekly_ros > 0 else 0.0
```

But `simulator.py` uses `ros_7d` from inventory state:
```python
ros_7d = float(state.ros_7d or 0) if state else 0.0
weeks_cover = quantity / max((ros_7d * 7), 0.01)  # correctly multiplies by 7
```

The simulator works, but the two ROS values for the same SKU+store can differ because one is from sales_data (demand.py's `_load_store_weekly_ros_from_db`) and the other is from inventory_state (snapshot job). A planner looking at the explainability panel and the simulation panel will see different ROS values for the same allocation line.

**Fix:** Document the unit convention explicitly. Add `_weekly` and `_daily` suffixes. Standardize on one source of truth for each purpose.

---

## P2 — Correctness and UX Issues

---

### P2-1 · Allocation Retry Button Has No State Update — `frontend/app/(dashboard)/allocation/page.tsx`

```typescript
onClick={async () => {
    await apiRequest("/api/v1/allocation/generate", {
        method: "POST",
        body: JSON.stringify({ grn_id: allocation.grn_id }),
    });
    // ← no mutate(), no state update
}}
```

After clicking "Retry", the list will not show `GENERATING` status until the next 5-second poll fires. The UI appears unresponsive.

**Fix:** Add `loadAllocations()` call (or `mutate()` if using SWR) immediately after the POST resolves.

---

### P2-2 · Unconditional 5-Second Poll — `frontend/app/(dashboard)/allocation/page.tsx`

```typescript
const interval = setInterval(loadAllocations, 5000);
```

This runs forever regardless of session state. Every browser tab open to this page fires a request every 5 seconds. For 10 concurrent planners, that's 120 requests/minute to list allocations indefinitely.

**Fix:** Only start the interval when at least one session has `status === "GENERATING"`. Clear it when none remain in that state.

---

### P2-3 · `console.log` Statements in Production Code — `frontend/app/(dashboard)/allocation/page.tsx`

Three `console.log` calls ship to production:
```typescript
console.log("Fetching allocations from /api/v1/allocation/sessions");
console.log("Allocations response:", response);
console.log("Filtering allocations:", { total: ..., data: allocations });
```

The third one logs full allocation payload on every filter change. This leaks business data to browser developer tools.

---

### P2-4 · Sales Validation Check After Delete — `backend/app/services/ingestion/processor.py`

In `_upsert_sales`, the upload starts by deleting existing rows for this `upload_id`:
```python
await db.execute(
    delete(SalesData).where(SalesData.upload_id == upload_id)
)
```

Then it processes rows. Then, near the end:
```python
if rows and distinct_weeks < 4 and not used_synthetic_weeking:
    raise ValueError("Sales data appears to have collapsed...")
```

If this raises, the delete has already been committed to the session (though not yet committed to the DB transaction). Depending on transaction isolation, this is fragile. The validation should happen **before** any writes.

---

### P2-5 · `AllocationSession` TypeScript Interface Missing `season_id` — `frontend/types/index.ts`

```typescript
export interface AllocationSession {
  id: string;
  brand_id: string;
  grn_id: string;
  status: ...
  // season_id is absent
```

The backend serializes `season_id` in the list_sessions response. The frontend simply doesn't type it. Any future code that tries to use `session.season_id` will get `undefined` with no TypeScript error.

---

### P2-6 · `list_sessions` Uses Manual Serialization — `backend/app/routers/allocation.py`

Every other endpoint uses `envelope(data)` + `jsonable_encoder`. The `list_sessions` endpoint manually builds a dict:
```python
session_data = {
    "id": str(session.id),
    "grn_id": str(session.grn_id),
    ...
}
```

Inconsistent pattern. Also missing fields that `AllocationSessionOut` schema defines (`engine_version`, `total_skus`, `total_units_recommended`, `total_units_approved`, `approved_by`, `approved_at`).

---

### P2-7 · GRN `_upsert_grn` Does Not Set `season_id` — `backend/app/services/ingestion/processor.py`

The standalone GRN upload (`_upsert_grn`) never sets `season_id` on the GRN. If a planner uploads a GRN file (not a buy file), the GRN has `season_id = NULL`. When the allocation engine runs `season_weeks_remaining`, it falls back to `DEFAULT_SEASON_WEEKS_REMAINING = 8` and `get_previous_season_id()` returns the most recent season rather than the linked one. Allocations will use wrong cover targets.

---

### P2-8 · Celery Beat Does Not Register Performance Snapshot Task — `backend/app/tasks/celery_app.py`

```python
celery_app.conf.beat_schedule = {
    "build-inventory-snapshots-daily": {...},
    "build-performance-snapshots-daily": {
        "task": "app.tasks.performance_snapshot.build_performance_snapshots",
        ...
    },
    "generate-alerts-daily": {...},
}
```

The performance snapshot task name is `build_performance_snapshots` but the Celery task in `performance_snapshot.py` is decorated as:
```python
@celery_app.task(name="app.tasks.performance_snapshot.build_performance_snapshots")
def build_performance_snapshots_task() -> dict:
```

The function is named `build_performance_snapshots_task` (with `_task` suffix) but the beat schedule references `build_performance_snapshots` (the name in the `@task` decorator, which matches). This one is fine on inspection — the name string matches. **But**: the beat schedule key says `build-performance-snapshots-daily` and maps to `app.tasks.performance_snapshot.build_performance_snapshots`. The task module imports OK. This is fine, no bug.

Actually, re-checking: there's a name collision between the service function `build_performance_snapshots` in `performance/calculator.py` and the Celery task. The Celery task imports and calls the service function. This works but is confusing naming.

---

### P2-9 · `apply_size_curves()` in Engine Does Not Use `size_curve.py` Logic — `backend/app/services/allocation/engine.py`

`apply_size_curves()` (the dead method) only checks if a single size is in the size guide. But `size_curve.py` contains the full `calculate_size_distribution()` function with historical fallback chains (store → cluster → brand → guide). The active `generate()` path DOES call `calculate_size_distribution()` from `size_curve.py` directly, so this part works. But `apply_size_curves()` is dead and misleading — it does something completely different (grade-based size eligibility filtering) and should either be renamed or removed.

---

### P2-10 · `StoreProductGrade` Unique Constraint Allows `NULL` Price Band Ambiguity

The unique constraint is `(brand_id, store_id, product_category, price_band)`. In PostgreSQL, `NULL != NULL` for uniqueness purposes. A store could have multiple rows with `price_band = NULL` for the same category, violating the intent of "one grade per store per category." The `get_store_grade` fallback chain assumes one product-level grade. Multiple NULL-band rows will return whichever one the ORM finds first.

**Fix:** Use a partial unique index: `CREATE UNIQUE INDEX ... WHERE price_band IS NULL` plus `CREATE UNIQUE INDEX ... WHERE price_band IS NOT NULL`.

---

### P2-11 · `generate()` Doesn't Clear Stale Lines Before Re-Generation for New SKU Sets

When a session is re-generated with a different GRN (same `grn_id` but changed buy file), `existing_lines_by_sku` may contain SKUs that no longer exist in the GRN. The code handles this with the `stale_lines` loop which zeros them out. However, if a SKU was removed from the GRN entirely, that SKU's allocation line remains in the DB (with `final_qty = 0`). The export will include these zero-quantity lines, cluttering the transfer sheet.

---

### P2-12 · `generate()` Sets `ai_recommended_qty = raw_demand` Not `final_qty` — `engine.py`

```python
existing_line.ai_recommended_qty = raw_demand   # before cap
existing_line.final_qty = final_qty              # after cap
```

`raw_demand` is the pre-cap demand. `final_qty` is post-cap. The explainability panel reads `ai_recommended_qty` as the recommendation. A planner sees a recommendation of 24 units but the actual allocation is 18. They don't understand why. The reasoning panel shows `scale_factor` but this is counter-intuitive.

This is actually the intended behavior per spec ("what AI recommended before cap") but it's not explained in the UI — the panel header says "Rec" which the planner will read as "what should be sent."

---

## Dead / Stub Code

---

### DEAD-1 · `constraints.py` is Entirely a Comment — `backend/app/services/allocation/constraints.py`

```python
# Constraint logic is currently implemented in AllocationEngine.apply_constraints.
# TODO: confirm with spec - split into this module when engine rules expand.
```

This file is imported nowhere, does nothing, and confuses anyone reading the directory structure. Delete it.

---

### DEAD-2 · `OverrideModal.tsx` Returns Null — `frontend/components/allocation/OverrideModal.tsx`

```typescript
export function OverrideModal() {
  return null;
}
```

Complete stub. Not used anywhere. Delete or implement.

---

### DEAD-3 · `ScenarioSimulator.tsx` is a Thin Wrapper Not Used in Main Flow — `frontend/components/allocation/ScenarioSimulator.tsx`

The scenario simulation logic is inline in `AllocationTable.tsx`. `ScenarioSimulator.tsx` exists as a separate component but is never imported or used in the allocation page. Dead code.

---

### DEAD-4 · `AlertBanner.tsx` is Not Used — `frontend/components/shared/AlertBanner.tsx`

The dashboard renders alerts inline. `AlertBanner` component exists, takes an `AlertCount` prop, is never imported in the dashboard or anywhere else.

---

### DEAD-5 · Eight Class Methods in `AllocationEngine` are Never Called from `generate()` — `backend/app/services/allocation/engine.py`

As documented in P0-1: `filter_eligible`, `score_stores`, `distribute_units`, `_distribute_standard`, `_distribute_concentrated`, `apply_size_curves`, `apply_constraints`, `generate_reasoning`, `_season_weeks_remaining`, `_load_ros_by_attribute`, `_load_latest_inventory`, `get_available_for_first_allocation` (on the engine class — a duplicate of the one in `inventory/snapshot.py`).

These are fully implemented and correct. They should be **wired in**, not deleted.

---

### DEAD-6 · `get_available_for_first_allocation` Defined Twice

`backend/app/services/allocation/engine.py` — method on `AllocationEngine`  
`backend/app/services/inventory/snapshot.py` — standalone async function

Identical logic. One is never called. Use the one in `snapshot.py` (or move to a shared utility) and remove the other.

---

### DEAD-7 · Makefile Referenced in README_DEV.md but Does Not Exist

`README_DEV.md` shows:
```bash
make up
make migrate
make load-pilot
make test
make jobs
```

None of these targets exist. `docker-compose.yml` is also not present in the provided files. New engineers and pilots cannot onboard without this.

---

## Security Issues

---

### SEC-1 · JWT Stored in `localStorage` — `frontend/lib/api.ts` and `frontend/app/(auth)/login/page.tsx`

```typescript
localStorage.setItem("kyros_access_token", accessToken);
localStorage.setItem("kyros_refresh_token", refreshToken);
```

`localStorage` is accessible to any JavaScript running on the page (including injected scripts via XSS). The spec explicitly requires HttpOnly cookies for refresh tokens.

**Fix:** Serve refresh tokens as `HttpOnly; Secure; SameSite=Strict` cookies from the backend. Access tokens can remain in memory (not localStorage) for SPA usage.

---

### SEC-2 · CORS Default Hardcoded to Localhost — `backend/app/config.py`

```python
cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
```

If `CORS_ORIGINS` env var is not set in production, the API will silently refuse all cross-origin requests from the real domain, or worse, if someone sets it too broadly.

---

### SEC-3 · In-Memory Refresh Token Store (Repeat of P0-4)

Also a security issue: tokens cannot be revoked across workers. A logged-out user's refresh token remains valid on other processes.

---

## Schema vs Spec Mismatches

---

### MISMATCH-1 · `AlertType` Enum Missing Two Values — `backend/app/models/alert.py`

**Spec (`mvp-scope.md`, Section 12 Schema):**
```sql
CREATE TYPE alert_type AS ENUM (
    'STOCKOUT_RISK', 'AGING_STOCK', 'WAREHOUSE_STOCK_SITTING', 'HIGH_COVER', 'GRN_UNALLOCATED'
);
```

**Actual code:**
```python
class AlertType(str, enum.Enum):
    STOCKOUT_RISK = "STOCKOUT_RISK"
    AGING_STOCK = "AGING_STOCK"
    GRN_UNALLOCATED = "GRN_UNALLOCATED"
    # WAREHOUSE_STOCK_SITTING missing
    # HIGH_COVER missing
```

`generate_alerts()` in `generator.py` also only implements 3 of the 5 types.

---

### MISMATCH-2 · `store_grade` Dropped But Referenced Throughout Spec

Migration 0002 drops the `store_grade` column from `stores` and replaces it with `store_product_grades`. This is correct per `PILOT_DATA_CHANGES.md`. However `mvp-scope.md` (the base spec) still references `store.store_grade` in multiple places. The engine uses `grade_map` from `store_product_grades` which is correct, but new engineers reading `mvp-scope.md` will be confused. **Documentation debt**, not a code bug.

---

### MISMATCH-3 · OTB Form Referenced in Spec but Unreachable in UI

`seasons.py` backend has `POST /api/v1/seasons/{id}/otb` endpoint. `frontend/app/(dashboard)/setup/seasons/page.tsx` has a form for creating seasons but **no OTB input form**. The spec (Section 8.2) requires a full OTB entry form with planned sales, closing stock, opening stock, on order. It doesn't exist in the frontend.

---

### MISMATCH-4 · Store Display Capacity Frontend Page Missing

`backend/app/routers/stores.py` has full endpoints for `GET/POST/PUT /api/v1/stores/display-capacity`. The frontend has no page or component to manage these. They can only be set via direct API calls.

---

### MISMATCH-5 · `actual_sellthrough` Weekly Update Job Not Implemented

`mvp-scope.md` Section 13 lists `update_allocation_outcomes` as a weekly Celery job that backfills `actual_sellthrough_4w`, `actual_sellthrough_8w`, `actual_sellthrough_eow` and `ai_was_better` on old allocation lines. This job does not exist. The fields are in the schema but will always be NULL.

---

### MISMATCH-6 · No `DELETE` Endpoints Anywhere

The spec's API design (Section 12) implies full resource lifecycle. Zero `DELETE` endpoints exist for any resource — stores, SKUs, seasons, clusters, GRNs, allocation sessions. The only way to deactivate is `PUT /{id}` with `is_active: false`. For GRNs and allocations, not even that exists.

---

## Missing Implementations

| Feature | Where Specified | Status |
|---|---|---|
| Climate zone eligibility filtering | `mvp-scope.md` §9.4, `PILOT_DATA_CHANGES.md` | Dead code (method exists, not called) |
| Display capacity enforcement | `mvp-scope.md` §9.6, spec schema | Dead code (method exists, not called) |
| Store-specific list filtering | `PILOT_DATA_CHANGES.md` Change 2 | Dead code (method exists, not called) |
| `WAREHOUSE_STOCK_SITTING` alert | `mvp-scope.md` §11.1 | Missing from enum and generator |
| `HIGH_COVER` alert | `mvp-scope.md` §11.1 | Missing from enum and generator |
| OTB input form | `mvp-scope.md` §8.2 | Backend exists, no frontend |
| Display capacity UI | `mvp-scope.md` §8.4 | Backend exists, no frontend |
| `actual_sellthrough` backfill job | `mvp-scope.md` §13 | Not implemented |
| Pagination on list endpoints | `mvp-scope.md` §12, `README.md` | Not implemented |
| Makefile | `README_DEV.md` | Entirely missing |
| DELETE endpoints | `mvp-scope.md` §12 | None exist |
| `HIGH/MEDIUM/LOW` role in nav RBAC | `mvp-scope.md` §15 | VIEWER role has no restricted routes |

---

## Prioritized Fix Order

### Sprint 1 — Core Engine (P0)

1. **Wire `generate()` to call dead methods** (P0-1) — most impactful fix
2. **Fix `_upsert_buy_file` GRN deletion** — remove delete-recreate, use upsert; add CASCADE or session re-parenting (P0-2)
3. **Remove hardcoded SS26 season** — derive from active season (P0-3)
4. **Move refresh token store to Redis** (P0-4)
5. **Fix blocking subprocess in async upload fallback** (P0-5)
6. **Guard UNDER_REVIEW re-generation** (P0-7)

### Sprint 2 — Performance (P0-P1)

7. **Batch `build_inventory_snapshots`** — rewrite inner loop as set-based SQL (P0-6)
8. **Batch `_calculate_stockout_correction`** — pre-load per brand/season (P1-1)
9. **Fix `list_sessions` N+1** — join query (P1-2)
10. **Remove `_run_simple_mode_jobs` from upload path** (P1-4)
11. **Add pagination to all list endpoints** (P1-3)

### Sprint 3 — Correctness (P2)

12. **Create `constants.py`** — deduplicate GRADE_SCORES, DEFAULT_GRADE (P1-5)
13. **Fix allocation retry button** — add loadAllocations() after POST (P2-1)
14. **Make poll conditional** on GENERATING sessions (P2-2)
15. **Remove console.log** (P2-3)
16. **Add UNDER_REVIEW guard** in generate endpoint (P0-7 — repeat)
17. **Add WAREHOUSE_STOCK_SITTING and HIGH_COVER** to AlertType enum and generator
18. **Add season_id to AllocationSession TypeScript interface**

### Sprint 4 — Missing UI + Cleanup

19. **Build OTB input form** in seasons page
20. **Build display capacity management UI**
21. **Delete dead stubs**: `constraints.py`, `OverrideModal.tsx`, `ScenarioSimulator.tsx`, `AlertBanner.tsx`
22. **Write Makefile** matching README_DEV.md commands
23. **Fix SEC-1**: Move tokens out of localStorage to httpOnly cookies or memory
24. **Add actual_sellthrough backfill Celery job**

---

## Quick Reference: Files with the Highest Bug Density

| File | Issues |
|---|---|
| `backend/app/services/allocation/engine.py` | P0-1 (split brain), 5 dead methods, duplicate constants, stale-line export pollution |
| `backend/app/services/ingestion/processor.py` | P0-2 (GRN deletion), P0-3 (hardcoded season), P1-4 (job triggered on upload), P2-4 (validation order) |
| `backend/app/services/inventory/snapshot.py` | P0-6 (N+1 catastrophe), duplicate `get_available_for_first_allocation` |
| `backend/app/routers/allocation.py` | P0-7 (UNDER_REVIEW re-gen), P1-2 (N+1 GRN), inconsistent serialization |
| `backend/app/routers/auth.py` | P0-4 (in-memory token store), SEC-1, SEC-3 |
| `frontend/app/(dashboard)/allocation/page.tsx` | P2-1 (no mutate), P2-2 (unconditional poll), P2-3 (console.log ×3) |
| `backend/app/models/alert.py` | MISMATCH-1 (missing enum values) |

---

*End of Forensic Analysis — KYROS v0.1 | March 2026*