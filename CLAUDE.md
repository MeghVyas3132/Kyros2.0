# KYROS — Claude Code Memory File

## What This Product Is

Kyros is a merchandising intelligence platform for fashion retailers in India. It helps retail brands (50-500 stores, ₹50 crore–₹5,000 crore revenue) allocate inventory to stores based on historical sales, store grades, climate zones, display capacity, and style risk levels. It replaces Excel-based workflows with an API-first platform that can tell a brand which stores should receive how many units of each SKU.

**The core workflow:**
1. Upload sales history (what sold where, when, and how much)
2. Upload store grades (which stores are A+/A/B/C for which product categories)
3. Upload buy file (what you're buying for the new season)
4. Upload GRN (what actually arrived in warehouse)
5. Generate allocation (Kyros calculates optimal store distribution)
6. Review, adjust, approve, export

---

## Current Status

### What Is Working

- **Ingestion pipeline**: CSV/Excel uploads work with column auto-mapping for SALES, STORE_GRADES, SIZE_GUIDE, BUY_FILE, GRN
- **Allocation engine**: Generates store-level distributions based on historical ROS, store grades, risk tiers, and inventory caps
- **Explainability panel**: Frontend shows demand reasoning, stockout corrections, size splits, cover targets
- **Export**: CSV export of allocations with GRN Code, SKU Code, Style Name, Size, Store Code, Store Name, City, Quantity
- **Basic auth**: JWT access tokens with localStorage storage
- **Database**: Full schema with all tables from migrations
- **UNDER_REVIEW protection**: System prevents regeneration of sessions under review (HTTP 409)
- **GRN protection**: System prevents GRN deletion when active allocations exist

### What Is In Progress / Known Issues

| Issue | Status | Details |
|-------|--------|---------|
| Week_start_date synthetic spreading | **WORKING** | Pilot CSV has no week_start_date — code spreads units across 8 synthetic weeks |

---

## Architecture

### Backend

- **Framework**: FastAPI 0.109+, Python 3.11+
- **Database**: PostgreSQL 15 with asyncpg driver (postgresql+asyncpg://)
- **ORM**: SQLAlchemy 2.0 with async session
- **Migrations**: Alembic (versions in `backend/alembic/versions/`)
- **Task Queue**: Celery 5.x with Redis broker (DB 1) and result backend (DB 2)
- **Key Libraries**: pandas, pydantic, python-jose, passlib

**File Structure:**
```
backend/app/
  models/           # SQLAlchemy models (declarative)
  routers/          # FastAPI route handlers
  services/         # Business logic
    allocation/     # Engine, demand, size curves, cap logic
    ingestion/      # Upload processing, mapping, validation
    inventory/      # Snapshotting
    performance/    # Metrics calculation
    alerts/         # Alert generation
  tasks/            # Celery task definitions
  utils/            # CSV parsing, S3, dates, security
  schemas/          # Pydantic request/response models
```

### Frontend

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript 5.x
- **UI**: React 18, Tailwind CSS 3.x
- **State**: SWR for data fetching, React Hook Form for forms
- **Charts**: Recharts

**Key Pages:**
- `/` → Dashboard
- `/ingestion` → Upload CSV/Excel files
- `/grn` → View GRNs and trigger allocation
- `/grn/[id]` → GRN detail with allocation generation
- `/allocation` → Review allocation sessions

**Key Components:**
- `ExplainabilityPanel.tsx` → Shows demand reasoning per allocation line
- `AllocationTable.tsx` → Tabular view of allocation lines
- `ScenarioSimulator.tsx` → What-if quantity simulator

### Docker

**Services** (from `docker-compose.yml`):
1. `postgres` — PostgreSQL 15, port 5432, volume `postgres_data`
2. `redis` — Redis 7, port 6379
3. `backend` — FastAPI dev server, port 8000, `--reload` enabled
4. `celery_worker` — Celery worker with `--pool=solo`
5. `celery_beat` — Celery beat scheduler
6. `frontend` — Next.js dev server, port 3000

All services have `restart: unless-stopped`.

---

## Database Schema — Key Tables

| Table | Purpose | Key Columns | Gotchas |
|-------|---------|-------------|---------|
| **sales_data** | Historical sales by store/SKU/week | `brand_id`, `store_id`, `sku_id`, `week_start_date`, `units_sold`, `revenue`, `was_in_stock` | **NO season_id column**. Week_start_date is synthetic if not in CSV. |
| **allocation_lines** | One row per store × SKU allocation | `session_id`, `store_id`, `sku_id`, `ai_recommended_qty`, `final_qty`, `ai_reasoning` (JSONB), `ai_projections` (JSONB), `was_overridden` | ai_reasoning contains full explainability payload |
| **allocation_sessions** | Allocation run per GRN | `grn_id`, `status` (DRAFT/GENERATING/FAILED/UNDER_REVIEW/APPROVED/DISPATCHED/CANCELLED), `total_units_recommended`, `failure_reason` | Status is GENERATING during Celery run |
| **grn_lines** | Received inventory per SKU | `grn_id`, `sku_id`, `units_received`, `ecom_reserved_qty`, `ars_reserved_qty` | Availability = units_received - ecom_reserved - ars_reserved |
| **skus** | Product master | `sku_code`, `style_code`, `category`, `store_group_rule`, `resolved_min_grade`, `style_risk_group`, `resolved_risk_level`, `story`, `sub_story` | **NO silhouette, construction_type** columns yet |
| **stores** | Store master | `store_code`, `store_name`, `city`, `cluster_id`, `climate_zone` | **NO behavior_profile column** — that's in separate store_behavior_profiles table |
| **store_product_grades** | Multi-dimensional store grading | `store_id`, `product_category`, `price_band`, `grade` | Lookup: exact match first, then category-only, then default "C" |
| **size_guides** | Size distribution rules | `product_category`, `size`, `min_max_ratio`, `applies_to_grades`, `is_size_set` | Ratio 0 means size never allocated |

---

## Known Bugs and Their Status

### ✅ All P0 Bugs Fixed!

The following critical bugs have been resolved in the current codebase:

| File:Line | Bug | Status | Fix Applied |
|-----------|-----|--------|-------------|
| `allocation.py:182-192` | UNDER_REVIEW status regeneration | **✅ FIXED** | Returns HTTP 409 CONFLICT with clear error message |
| `processor.py:1313-1322` | Buy file re-upload destroys GRN | **✅ FIXED** | Checks for locked allocation sessions before GRN replacement |

### P1 — Performance Optimizations (Already Implemented)

| File:Line | Optimization | Status |
|-----------|--------------|--------|
| `demand.py:173-208` | Preload stockout signals | **✅ IMPLEMENTED** | `preload_stockout_signals()` batches all queries upfront |

---

## Data Facts

### Pilot Data (SS25 → SS26)

| Metric | Value |
|--------|-------|
| Stores | 162 |
| Styles | 3,536 |
| Sales rows | ~281,460 |
| Sales weeks | Synthetic 8-week spread (no week_start_date in CSV) |
| Season | SS26 (Summer/Spring 2026) |

### Sales CSV Structure (Actual Columns)

```
store_code, SOURCE CITY, REGION, DEPARTMENT, MRP, PRICEBAND,
sku_code, SIZE_FINAL, SIZE TYPE, Standardized Colour,
MATERIAL, units_sold, revenue, STORE GRN QTY
```

**Missing columns that code expects:**
- `week_start_date` → handled by synthetic spreading across 8 weeks
- `was_in_stock` → defaults to None

---

## API Endpoints — Complete List

| Method | Path | What It Does | Frontend Caller |
|--------|------|--------------|-----------------|
| POST | `/api/v1/auth/login` | JWT login | `useAuth.ts` |
| POST | `/api/v1/auth/refresh` | Refresh access token | `api.ts` (auto) |
| POST | `/api/v1/ingestion/upload` | Upload CSV with type | `UploadDropzone.tsx` |
| POST | `/api/v1/ingestion/smart-upload` | Auto-detect sheet types | `SmartUploadCard.tsx` |
| GET | `/api/v1/ingestion/uploads` | List uploads | Ingestion page |
| GET | `/api/v1/ingestion/uploads/{task_id}/progress` | Poll upload progress | `useUploadProgress.ts` |
| GET | `/api/v1/ingestion/uploads/{upload_id}` | Get upload details | Ingestion page |
| GET | `/api/v1/ingestion/uploads/{upload_id}/errors` | Get upload errors | Error report |
| POST | `/api/v1/allocation/generate` | Trigger allocation (dispatch to Celery) | `allocation/page.tsx` |
| GET | `/api/v1/allocation/sessions` | List all sessions | `useAllocation.ts` |
| GET | `/api/v1/allocation/sessions/by-grn/{grn_id}` | Get session by GRN | GRN detail page |
| GET | `/api/v1/allocation/sessions/{session_id}` | Get session with lines | `allocation/[id]/page.tsx` |
| POST | `/api/v1/allocation/sessions/{session_id}/recover` | Recover stuck GENERATING session | Admin tools |
| POST | `/api/v1/allocation/sessions/{session_id}/approve` | Approve allocation | Allocation detail |
| GET | `/api/v1/allocation/sessions/{session_id}/export` | Download CSV | Export button |
| GET | `/api/v1/allocation/{allocation_id}/insights` | Get allocation insights | Dashboard |
| PUT | `/api/v1/allocation/lines/{line_id}` | Override line quantity | Allocation table |
| POST | `/api/v1/allocation/simulate` | Simulate quantity change | `ScenarioSimulator.tsx` |
| GET | `/api/v1/grns` | List GRNs | GRN page |
| GET | `/api/v1/grns/{grn_id}` | Get GRN detail | GRN detail page |
| POST | `/api/v1/grns` | Create new GRN | GRN creation |
| GET | `/api/v1/stores` | List stores | Setup pages |
| GET | `/api/v1/skus` | List SKUs | Setup pages |
| GET | `/api/v1/seasons` | List seasons | Setup pages |

---

## Allocation Engine — How It Works

### Entry Point

`backend/app/tasks/allocation.py:run_allocation_task()` → `engine.generate()`

### Step-by-Step Flow

1. **Load GRN** (`engine.py:96-98`)
   - Get the GRN record, verify it exists

2. **Load stores** (`engine.py:109-117`)
   - Load all active stores for brand into cache

3. **Load supporting data** (`engine.py:194-210`)
   - Previous season ID (for historical ROS)
   - Season weeks remaining (for cover calculation)
   - Min presentation qty (from brand settings)
   - Grade map (store_id × category → grade)
   - Sales history (store × SKU → weekly ROS)
   - Grade ROS averages (grade × SKU → avg ROS)
   - Stockout signals (preloaded for correction)
   - Brand settings (allocation config)

4. **Per GRN Line** (`engine.py:218-578`)
   - For each SKU in the GRN:

   a. **Calculate available units** (`engine.py:228-230`)
      - `available = units_received - ecom_reserved - ars_reserved`

   b. **Filter eligible stores** (`engine.py:235-263`)
      - Check store_group_rule (A+ only, A+ & A, etc.)
      - Score stores: ROS (50%) + Grade score (25%) + Cover (25%)
      - Filter: store list, min grade, climate match, display capacity

   c. **Calculate demand per store** (`engine.py:266-301`)
      - Three-tier fallback:
        - TIER 1: Store-specific historical ROS for this SKU
        - TIER 2: Grade-level average ROS for this SKU
        - TIER 3: Minimum presentation quantity
      - Apply stockout correction if detected
      - Apply grade multiplier
      - Calculate raw demand: `weekly_ros × cover_target_weeks`

   d. **Distribute units** (`engine.py:304-320`)
      - Standard distribution for PROVEN/CONFIDENT
      - Concentrated distribution for EXPERIMENTAL (max 5 stores)
      - Result: store_id → quantity mapping

   e. **Apply inventory cap** (`engine.py:315`)
      - If total demand > available, scale down proportionally
      - Then enforce minimums by grade priority

   f. **Apply size curves** (`engine.py:322`)
      - Calculate size distribution per store
      - Filter by grade eligibility (applies_to_grades)

   g. **Save allocation lines** (`engine.py:359-502`)
      - Create/update AllocationLine records
      - Populate ai_reasoning JSON with full context
      - Populate ai_projections with size splits

5. **Finalize session** (`engine.py:584-588`)
   - Set status to UNDER_REVIEW
   - Set total_units_recommended
   - Commit

### Three-Tier Demand Fallback

From `demand.py:320-408`:

```python
# TIER 1: Store-specific historical
store_ros = sales_by_store_category.get((store.id, sku.id))
if store_ros:
    return store_ros with confidence HIGH

# TIER 2: Grade-level average
grade_ros = grade_ros_averages.get((grade, sku.id))
if grade_ros:
    return grade_ros with confidence MEDIUM

# TIER 3: Minimum presentation
return min_presentation_qty with confidence LOW
```

### Cover Targets by Grade and Risk

From `constants.py:11-24`:

```python
DEFAULT_COVER_TARGETS = {
    ("PROVEN", "A+"): 7,      # 7 weeks of cover for A+ proven styles
    ("PROVEN", "A"): 5,
    ("PROVEN", "B"): 4,
    ("PROVEN", "C"): 3,
    ("CONFIDENT", "A+"): 6,
    ("CONFIDENT", "A"): 5,
    ("CONFIDENT", "B"): 3,
    ("CONFIDENT", "C"): 2,
    ("EXPERIMENTAL", "A+"): 4,
    ("EXPERIMENTAL", "A"): 3,
    ("EXPERIMENTAL", "B"): 2,
    ("EXPERIMENTAL", "C"): 0,  # No allocation to C for experimental
}
```

### Inventory Cap Logic

From `cap.py:11-45`:

1. If total demand ≤ available: return raw demands
2. Calculate scale_factor = available / total_demand
3. Scale all demands proportionally
4. Fix rounding difference by adding/subtracting from largest
5. Enforce minimums by grade priority (A+ first, then A, B, C)

---

## Ingestion — How It Works

### Upload Types

| Type | Expected Format | Required Columns | Handler |
|------|----------------|------------------|---------|
| **SALES** | CSV with sales history | store_code, sku_code, units_sold | `_upsert_sales()` in processor.py:412 |
| **STORE_GRADES** | CSV with store × category grades | store_name, product_category, grade | `_upsert_store_grades()` in processor.py:952 |
| **SIZE_GUIDE** | CSV with size ratios | product_category, size, min_max_ratio | `_upsert_size_guide()` in processor.py:1014 |
| **BUY_FILE** | CSV with purchase orders | sku_code, category | `_upsert_buy_file()` in processor.py:1104 |
| **GRN** | CSV with warehouse receipts | grn_code, grn_date, sku_code, units_received | `_upsert_grn()` in processor.py:737 |

### Column Mapping

1. User uploads file
2. System auto-detects columns using `mapping.py:151` (detect_column_mapping)
3. Maps variations like "Store Name", "STORE", "store_name" → canonical `store_code`
4. If mapping fails, returns 422 with MAPPING_REQUIRED error
5. User confirms mapping, system transforms and re-uploads

### Synthetic Week Spreading

When `week_start_date` is missing from CSV (`processor.py:469-475`):

```python
synthetic_week_starts = _generate_synthetic_week_starts(8)  # 8 weeks
# Returns: [today-7*7, today-6*7, ..., today]
targets = _spread_units_across_weeks(units_sold, synthetic_week_starts)
# Spreads units evenly across weeks with remainder to first weeks
```

---

## Environment

### Start Everything

```bash
docker compose up -d
```

### Check Logs

```bash
docker compose logs -f celery_worker   # Allocation task logs
docker compose logs -f backend         # API request logs
docker compose logs -f frontend        # Frontend dev server
```

### Connect to Database

```bash
docker exec kyros20-postgres-1 psql -U kyros -d kyros_dev -c "YOUR QUERY"
```

### Run Tests

```bash
cd backend
python -m pytest tests/ -v
```

### Database Connection String

```
postgresql+asyncpg://kyros:kyros_dev_password@localhost:5432/kyros_dev
```

---

## Commands I Use Constantly

```bash
# Check all services running
docker compose ps

# Check celery worker logs (where allocation runs)
docker compose logs -f celery_worker --tail=100

# Query allocation status
docker exec kyros20-postgres-1 psql -U kyros -d kyros_dev -c "SELECT id, status, total_units_recommended FROM allocation_sessions ORDER BY created_at DESC LIMIT 5;"

# Check data counts
docker exec kyros20-postgres-1 psql -U kyros -d kyros_dev -c "SELECT (SELECT COUNT(*) FROM sales_data) as sales, (SELECT COUNT(*) FROM stores) as stores, (SELECT COUNT(*) FROM allocation_lines) as alloc_lines;"

# Restart services
docker compose restart celery_worker backend

# Check backend logs
docker compose logs backend --tail=100
```

---

## What NOT To Do

1. **Do not reference `SalesData.season_id`** — column does not exist. Use `upload_id` or join via SKU table (SKU.season_id exists).

2. **Do not default `week_start_date` to today** — this collapses all history into one week. Use synthetic spreading across 8 weeks.

3. **Do not call synchronous allocation from async endpoint** — causes timeouts. Always dispatch to Celery via `run_allocation_task.apply_async()`.

4. **The system now protects against:**
   - Regenerating UNDER_REVIEW sessions (returns 409 CONFLICT)
   - Deleting GRNs with active allocations (raises ValueError)

5. **grade_multiplier is applied ONCE in engine.py:300** — demand.py stores it for reference but does NOT apply it to weekly_ros (see demand.py:391-393 comment).

6. **Always use preload functions** — `preload_stockout_signals()`, `load_sales_history()`, `load_grade_map()` to avoid N+1 queries.

---

## Roadmap Context

### Phase 0: Foundations (Current)
- ✅ Ingestion pipeline with column mapping
- ✅ Allocation engine with three-tier demand fallback
- ✅ Basic explainability panel with full reasoning payload
- ✅ Store grades (multi-dimensional with price_band support)
- ✅ Size curves (uses historical_season_id parameter correctly)
- ⚠️ Store behavior profiles (table exists, build function needs completion)

### Phase 1: Lost Sales Correction + Cover-Day Framing
- ✅ Stockout detection in demand.py (both explicit and inferred)
- ✅ Lost sales estimation with correction applied to ROS
- ✅ Cover target weeks by risk × grade (DEFAULT_COVER_TARGETS)
- ✅ grade_multiplier correctly applied once in engine.py line 300

### Phase 2: Style DNA Matching + Store Behavior Profiling
- 🔄 Style DNA similarity scoring (stubbed in reasoning as null)
- 🔄 Store behavior profiles (table exists, build function has bug)
- 🔄 Category/fabric affinity scoring
- 🔄 Cannibalization detection

### Phase 3: Explainability Product
- ✅ Basic narrative fields
- 🔄 Cluster benchmarking
- 🔄 Style DNA match visualization

### Phase 4: In-Season Intelligence
- 🔄 Performance snapshots
- 🔄 Alert generation
- 🔄 Transfer recommendations

---

## The Pilot

- **Data**: SS25 Sales History + SS26 Buy File
- **Stores**: 162
- **Styles**: 3,536
- **Sales rows**: ~281,460
- **SS25 data lacks**: `week_start_date` column (uses synthetic spreading)
- **Season**: SS26 (Summer/Spring 2026)
- **Status**: Brands waiting for allocation accuracy validation

---

*Last updated: 2026-03-29*
*Based on: forensic analysis, codebase read, PILOT_DATA_CHANGES.md, KYROS_ALLOCATION_ROADMAP.md*
