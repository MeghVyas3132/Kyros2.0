# KYROS — Claude Code Context File

---

## What This Product Is

Kyros is a pre-season merchandising planning platform for fashion retailers in India (50–500 stores, ₹50 crore–₹5,000 crore revenue). It replaces Excel-based workflows with a structured, data-driven system for making buying and allocation decisions before a season begins.

**The product vision (README.md):** A closed-loop OS covering season planning → OTB → buy planning → allocation → in-season performance → post-season learning. Every season on Kyros should produce better defaults for the next.

**Current reality (April 2026):** We have only the back half of this loop. The allocation engine (distribution of received inventory to stores) is built and sophisticated. Everything before it — range planning, OTB, buy planning — is either missing or broken. This is the core philosophical problem.

---

## The Philosophical Problem — Why Allocation Is Failing

The allocation engine is technically impressive (1672 lines in engine.py) but it is solving the **wrong problem first**. Pilots are failing not because the math is wrong but because:

### 1. We skipped the upstream workflow
A brand cannot use allocation unless they first know:
- **What season are they planning for?** (season model exists, barely used)
- **What's their budget / OTB?** (SeasonOTB model exists, no calculation logic)
- **What are they buying?** (BuyPlan model exists, no workflow for it)
- **What arrived in the warehouse?** (GRN works, but without buy plan context it's disconnected)

Brands come to Kyros needing to answer "what should we buy?" and we respond with "upload your GRN and we'll allocate it." That's backwards. They can't generate a GRN until they know what they bought.

### 2. The allocation engine is over-engineered for trust-building
The engine has: style DNA matching, cannibalization dampening, affinity multipliers, cold-start supply-led mode, 4-tier demand fallback, per-store historical size ratios. A pilot customer (merchandiser with 10 years of Excel experience) cannot verify these recommendations because the reasoning is too complex to audit.

For PMF validation, the goal is not "best possible allocation math." It is "will a brand trust this enough to replace their Excel file?" Trust requires simplicity and transparency — not sophistication.

### 3. There is no end-to-end workflow
The frontend has pages for ingestion, GRN, allocation, and performance — but no guided workflow. A brand cannot be onboarded in a single sitting. There is no "you're at step 2 of 5" structure. Each page is a standalone tool, not a connected process.

---

## What MVP Actually Needs for PMF

We are validating one hypothesis: **"Can we get a fashion brand to make a better pre-season allocation decision using Kyros than they would make in Excel?"**

The minimal path to validate this:

### Step 1 — Season Setup (2 screens)
- Create a season (name, start date, end date, weeks remaining)
- Set category-level OTB budget (how much cash per category)

### Step 2 — Data Ingestion (already exists, mostly works)
- Upload last season's sales history → store ROS baselines
- Upload store grades (A+/A/B/C per category)
- Upload size guide (size split ratios by category)

### Step 3 — Buy Plan (MISSING — must be built)
- Upload or enter style-level buy decisions: style code, category, total units bought, vendor, expected delivery
- System validates: does this exceed OTB? If yes, warn.
- This creates the "what you're buying" record that feeds into GRN

### Step 4 — GRN (works, but needs buy plan link)
- When inventory arrives, create GRN against the buy plan
- GRN lines = units actually received per SKU

### Step 5 — Allocation (engine exists, needs simplification)
- Run allocation for a GRN
- Show: which stores get how many units of each SKU
- Explanation must be readable by a non-technical merchandiser
- Allow manual override with reason

### Step 6 — Review & Approve (partially exists)
- Summary view: total units, by store, by category, by grade
- Export to Excel/CSV for WMS handoff

**What to cut from MVP scope:**
- Style DNA matching (too complex, not auditable)
- Cannibalization dampening (hard to explain)
- Affinity multipliers (nice-to-have, not P0)
- Health score / benchmark report (internal QA tool, not user-facing yet)
- Cold-start mode (edge case — most pilot brands have 1+ season of data)
- In-season performance tracking
- Alert generation
- Transfer orders
- Markdown strategy
- Multi-tenant / multi-country

---

## Architecture

### Backend

- **Framework**: FastAPI 0.109+, Python 3.11+
- **Database**: PostgreSQL 15 with asyncpg driver (`postgresql+asyncpg://`)
- **ORM**: SQLAlchemy 2.0 with async session
- **Migrations**: Alembic (`backend/alembic/versions/`)
- **Task Queue**: Celery 5.x with Redis broker (DB 1) and result backend (DB 2)
- **Key Libraries**: pandas, pydantic, python-jose, passlib

### Frontend

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript 5.x
- **UI**: React 18, Tailwind CSS 3.x
- **State**: SWR for data fetching, React Hook Form
- **Charts**: Recharts

### Docker Services

1. `postgres` — PostgreSQL 15, port 5432
2. `redis` — Redis 7, port 6379
3. `backend` — FastAPI dev server, port 8000, `--reload`
4. `celery_worker` — Celery worker, `--pool=solo`
5. `celery_beat` — Celery beat scheduler
6. `frontend` — Next.js dev server, port 3000

---

## File Map — Backend (`backend/app/`)

### Models (`models/`)

| File | What It Stores |
|------|----------------|
| `brand.py` | Brand (name, slug, is_active) |
| `user.py` | Users (email, role: ADMIN/PLANNER/VIEWER, brand_id) |
| `season.py` | Season (name, start/end date, status), SeasonOTB (monthly cash budget per category) |
| `store.py` | Stores (store_code, city, cluster_id, climate_zone), StoreProductGrade (store×category grade) |
| `cluster.py` | Store clusters |
| `sku.py` | SKU master (style_code, size, category, fabric, price_band, color, grade requirements, style_risk_group, store_group_rule, story/sub_story) |
| `grn.py` | GRN header + GRN lines (units_received, ecom_reserved, ars_reserved) |
| `buy_plan.py` | BuyPlan + BuyPlanLine (season-level style purchase decisions) — **model exists, no workflow** |
| `sales_data.py` | Weekly sales rows (store, SKU, week_start_date, units_sold, was_in_stock) |
| `inventory_state.py` | Snapshot: units_on_hand, ros_7d per store×SKU |
| `allocation.py` | AllocationSession (status, health_score, total_units_recommended), AllocationLine (ai_recommended_qty, ai_confidence, ai_reasoning JSONB, final_qty, was_overridden) |
| `size_guide.py` | Size distribution ratios per category (min_max_ratio, applies_to_grades) |
| `brand_settings.py` | Config JSON per brand (min_presentation_qty, opening_order_pct, season_weeks_remaining, etc.) |
| `store_profile.py` | Store behavior profiles (category_affinity, fabric_affinity) |
| `performance_snapshot.py` | Weekly performance aggregates |
| `alert.py` | Stock-out / overstock alerts |
| `upload.py` | Upload job tracking (status, progress, error_log) |

### Routers (`routers/`)

| File | Endpoints | Notes |
|------|-----------|-------|
| `auth.py` | POST /login, POST /refresh | JWT, bcrypt |
| `seasons.py` | GET/POST /seasons, GET/POST /seasons/{id}/otb | OTB is manual input only — no calculation |
| `grn.py` | GET/POST /grns, GET /grns/{id} | GRN creation + reservation management |
| `skus.py` | GET/POST /skus | SKU master CRUD |
| `stores.py` | GET/POST /stores, GET/POST /stores/grades | Store + grade management |
| `clusters.py` | GET/POST /clusters | Cluster CRUD |
| `ingestion.py` | POST /upload, GET /uploads, GET /uploads/{id}/progress | CSV ingestion with column mapping |
| `allocation.py` | POST /generate, GET /sessions, GET /sessions/{id}, PATCH /lines/{id}, POST /simulate, POST /approve, GET /sessions/{id}/export | Full allocation lifecycle |
| `performance.py` | GET /performance/styles, /performance/stores | Sellthrough dashboards |
| `alerts.py` | GET /alerts | Stockout/overstock notifications |
| `onboarding.py` | POST /onboarding | Initial brand setup |

**Missing router:** `buy_plan.py` — model exists but no API endpoints

### Services (`services/`)

#### `services/allocation/` — The Allocation Engine

| File | What It Does | Size/Complexity |
|------|--------------|-----------------|
| `engine.py` | Main orchestrator: loads GRN → filters stores → calculates demand → distributes units → applies size curves → saves AllocationLines | 1,672 lines — very complex |
| `demand.py` | 4-tier demand fallback: store history → cluster avg → grade avg → style DNA analogues. Stockout correction included. | 1,237 lines |
| `health.py` | Post-generation health analyzer: coverage score, demand alignment, balance, presentation, confidence. Outputs verdict (SAFE/CAUTION/RISKY/CRITICAL) | 413 lines |
| `benchmark.py` | Quality report: override rate, grade compliance, utilization, confidence mix, demand source breakdown | 320 lines |
| `intelligence.py` | Store prioritization (PROVEN=wide distribution, EXPERIMENTAL=concentrate top 5) | - |
| `store_profile.py` | Preload store affinity scores (category/fabric match multipliers) | - |
| `story_concentration.py` | Cannibalization dampening (story colourway competition) | - |
| `size_curve.py` | Per-store historical size ratios or fallback to brand size guide | - |
| `simulator.py` | What-if: recalculate with modified inputs | - |
| `cap.py` | Proportional scale-down when demand > available units | - |
| `guardrails.py` | Override bounds checking | - |
| `explainer.py` | Normalize ai_reasoning JSON for API response | - |
| `constants.py` | DEFAULT_COVER_TARGETS by (risk_group, grade), GRADE_MULTIPLIERS | - |

#### `services/ingestion/`

| File | What It Does |
|------|--------------|
| `processor.py` | Main ETL: load from S3 → parse CSV → validate → upsert in batches → emit progress via Redis |
| `mapping.py` | Column name detection (handles "Store Code", "STORE", "store_code" → canonical field) |
| `normalizer.py` | Type coercion, field cleaning |
| `validator.py` | Row-level validation (FK checks, required fields, date formats) |
| `bulk.py` | Batch upsert with conflict handling (INSERT ON CONFLICT UPDATE) |
| `lookup.py` | Preload store/SKU/season dict for O(1) FK resolution |
| `understanding.py` | Infer file type from headers (sales_data vs. grn vs. buy_plan etc.) |

#### `services/inventory/`
- `snapshot.py` — Seed InventoryState from SalesData rolling aggregates

#### `services/performance/`
- `calculator.py` — Weekly ROS trending, style sellthrough %, grade/store comparisons

#### `services/alerts/`
- Alert generation (stockout, overstock detection)

### Tasks (`tasks/`)

| File | What It Does |
|------|--------------|
| `allocation.py` | Runs engine.generate(), calls HealthAnalyzer, makes APPROVE/REVIEW decision, retries 2x on failure |
| `upload_runner.py` | Dispatches ingestion processor for an uploaded file |
| `performance_snapshot.py` | Weekly job: aggregate sales into snapshots |
| `alert_generation.py` | Detect stockout/overstock conditions |
| `celery_app.py` | Celery config (Redis broker, result backend, task routing) |

---

## Database Schema — Key Tables

| Table | Purpose | Key Columns | Gotchas |
|-------|---------|-------------|---------|
| `sales_data` | Weekly historical sales | `brand_id`, `store_id`, `sku_id`, `week_start_date`, `units_sold`, `was_in_stock` | **NO season_id column**. Use `upload_id` or join via SKU. week_start_date is synthetic if not in CSV. |
| `allocation_sessions` | Allocation run per GRN | `grn_id`, `status` (DRAFT/GENERATING/FAILED/UNDER_REVIEW/APPROVED/DISPATCHED/CANCELLED), `total_units_recommended`, `health_score`, `health_report` (JSONB), `decision` (JSONB), `failure_reason` | Status is GENERATING during Celery run |
| `allocation_lines` | One row per store × SKU × session | `session_id`, `store_id`, `sku_id`, `ai_recommended_qty`, `ai_confidence`, `ai_reasoning` (JSONB), `ai_projections` (JSONB), `final_qty`, `was_overridden`, `override_reason` | ai_reasoning contains full explainability payload |
| `grn_lines` | Received inventory per SKU | `grn_id`, `sku_id`, `units_received`, `ecom_reserved_qty`, `ars_reserved_qty` | Availability = units_received - ecom_reserved - ars_reserved |
| `skus` | Product master | `sku_code`, `style_code`, `category`, `store_group_rule`, `resolved_min_grade`, `style_risk_group`, `resolved_risk_level`, `story`, `sub_story` | **NO silhouette, construction_type** columns |
| `stores` | Store master | `store_code`, `store_name`, `city`, `cluster_id`, `climate_zone` | **NO behavior_profile column** — that's in separate store_behavior_profiles table |
| `store_product_grades` | Multi-dimensional store grading | `store_id`, `product_category`, `price_band`, `grade` | Lookup: exact match first, then category-only, then default "C" |
| `size_guides` | Size distribution rules | `product_category`, `size`, `min_max_ratio`, `applies_to_grades`, `is_size_set` | Ratio 0 = size never allocated |
| `season_otb` | Monthly OTB budget per category | `season_id`, `category`, `month`, `planned_sales`, `planned_closing_stock`, `opening_stock`, `on_order`, `otb_value` | otb_value = planned_sales + closing - opening - on_order. Manual input only, no calculation. |
| `buy_plan` / `buy_plan_lines` | Purchase intent per style | `season_id`, `style_code`, `units_planned`, `store_group_rule` | **Model exists, no API router, no workflow** |
| `brand_settings` | Config per brand | JSON blob: min_presentation_qty, opening_order_pct, experimental_max_stores, etc. | Controls allocation behavior |

---

## Allocation Engine — How It Actually Works

### Entry Point
`tasks/allocation.py:run_allocation_task()` → `engine.generate()` → `AllocationHealthAnalyzer()` → decision

### Step-by-Step

1. **Load GRN + stores** — All active stores for brand loaded into cache
2. **Load supporting data** — Sales history, grade map, stockout signals, store profiles, grade ROS averages (all preloaded to avoid N+1)
3. **Per style in GRN** (style-level grouping, not SKU-level — all sizes treated as one unit):
   - Calculate `available = units_received - ecom_reserved - ars_reserved`
   - Filter eligible stores: store_group_rule, grade, climate_zone
   - Score stores: 50% ROS + 25% grade + 25% current cover (min-max normalized)
   - Auto-detect strategy: PROVEN=wide spread, EXPERIMENTAL=concentrate top 5 stores
   - Calculate demand per store (4-tier: store hist → cluster avg → grade avg → style DNA → minimum)
   - Apply stockout correction if detected (zero weeks mid-season = re-estimate ROS from pre-stockout rate)
   - Apply affinity multipliers (category/fabric match between store profile and SKU)
   - Apply cannibalization dampening (story colourway competition factor 0.65–0.90)
   - Apply inventory cap (scale down proportionally if total demand > available)
   - Enforce MVA (minimum viable amount per store)
   - Split style allocation across sizes (store-specific historical ratios or brand size guide)
   - Save AllocationLines with rich ai_reasoning JSON
4. **Health analysis** — Score session: coverage, demand alignment, balance, presentation, confidence
5. **Decision** — APPROVE (≥75), APPROVE_WITH_CAUTION (55-75), REVIEW_REQUIRED (<55)
6. **Finalize** — Set session status to UNDER_REVIEW, set total_units_recommended

### Demand 4-Tier Fallback

```
TIER 1: Store-specific historical ROS for this SKU (confidence: HIGH)
TIER 2: Cluster-average ROS for this SKU (confidence: MEDIUM)
TIER 3: Grade-average ROS for this SKU (confidence: MEDIUM)
TIER 4: Style DNA — top 5 analogous SKUs by fabric/price/risk/color similarity (confidence: LOW)
TIER 5: min_presentation_qty (confidence: LOW — last resort)
```

### Cover Targets by Grade × Risk

```python
DEFAULT_COVER_TARGETS = {
    ("PROVEN", "A+"): 7, ("PROVEN", "A"): 5, ("PROVEN", "B"): 4, ("PROVEN", "C"): 3,
    ("CONFIDENT", "A+"): 6, ("CONFIDENT", "A"): 5, ("CONFIDENT", "B"): 3, ("CONFIDENT", "C"): 2,
    ("EXPERIMENTAL", "A+"): 4, ("EXPERIMENTAL", "A"): 3, ("EXPERIMENTAL", "B"): 2,
    ("EXPERIMENTAL", "C"): 0,  # No allocation to C for experimental
}
```

### Grade Multipliers
`A+: 1.1 | A: 1.0 | B: 0.9 | C: 0.75`
Applied ONCE in `engine.py:300`. `demand.py` stores it for reference but does NOT apply it to weekly_ros.

---

## What Is Working

| Component | Status | Notes |
|-----------|--------|-------|
| CSV ingestion (5 file types) | ✅ Working | SALES, STORE_GRADES, SIZE_GUIDE, BUY_FILE, GRN |
| Column auto-mapping | ✅ Working | Handles variant column names |
| Synthetic week spreading | ✅ Working | No week_start_date in pilot CSV — spreads across 8 weeks |
| Allocation engine (core math) | ✅ Working | Generates recommendations per store×SKU |
| Stockout correction | ✅ Working | Detects zero-stock weeks, re-estimates ROS |
| Style DNA matching | ✅ Working | Fallback demand for new styles |
| Health analyzer | ✅ Working | SAFE/CAUTION/RISKY/CRITICAL verdict |
| Allocation review UI | ✅ Working | Line-level override with reason |
| Explainability panel | ✅ Working | demand reasoning, confidence, stockout details |
| Export CSV | ✅ Working | GRN Code, SKU, Style, Size, Store, City, Quantity |
| JWT auth | ✅ Working | localStorage tokens |
| UNDER_REVIEW protection | ✅ Working | HTTP 409 on regeneration attempt |
| GRN protection | ✅ Working | Blocks deletion when active allocations exist |

## What Is Broken / Missing

| Component | Status | Impact |
|-----------|--------|--------|
| Buy plan workflow | ❌ Missing | Brands can't record purchase decisions — GRN is disconnected from intent |
| OTB calculation | ❌ Missing | SeasonOTB model exists but no algorithm to compute from history |
| Range planning | ❌ Missing | No "what should we buy?" — only "here's what you bought, let's allocate it" |
| End-to-end guided workflow | ❌ Missing | No step-by-step UX; each page is standalone |
| Workflow state machine | ❌ Missing | Season can jump states without enforcement |
| Learning loop (N → N+1) | ❌ Missing | Season actuals don't feed next season defaults |
| Planogram constraints | ❌ Missing | README claims this; NOT implemented |
| WMS/POS integration | ❌ Missing | Approved allocations don't trigger downstream |
| Mid-season rebalancing | ❌ Missing | No transfer order logic |
| Markdown / clearance | ❌ Missing | No end-of-season strategy |

---

## Ingestion — How It Works

### Upload Types

| Type | Required Columns | Handler |
|------|-----------------|---------|
| **SALES** | store_code, sku_code, units_sold (week_start_date optional) | `_upsert_sales()` in processor.py |
| **STORE_GRADES** | store_name, product_category, grade | `_upsert_store_grades()` |
| **SIZE_GUIDE** | product_category, size, min_max_ratio | `_upsert_size_guide()` |
| **BUY_FILE** | sku_code, category | `_upsert_buy_file()` |
| **GRN** | grn_code, grn_date, sku_code, units_received | `_upsert_grn()` |

### Column Mapping Flow
1. Upload → system auto-detects columns via `mapping.py:detect_column_mapping()`
2. Maps variants ("Store Name", "STORE", "store_name") → canonical field
3. If mapping fails → 422 with MAPPING_REQUIRED error
4. User confirms mapping → system transforms and processes

### Synthetic Week Spreading
When `week_start_date` missing from CSV (`processor.py:469-475`):
```python
synthetic_week_starts = _generate_synthetic_week_starts(8)  # [today-7*7, ..., today]
targets = _spread_units_across_weeks(units_sold, synthetic_week_starts)
```

---

## Pilot Data (SS25 → SS26)

| Metric | Value |
|--------|-------|
| Stores | 162 |
| Styles | 3,536 |
| Sales rows | ~281,460 |
| Sales weeks | Synthetic 8-week spread (no week_start_date in CSV) |
| Season | SS26 (Summer/Spring 2026) |

### Sales CSV Actual Columns
```
store_code, SOURCE CITY, REGION, DEPARTMENT, MRP, PRICEBAND,
sku_code, SIZE_FINAL, SIZE TYPE, Standardized Colour,
MATERIAL, units_sold, revenue, STORE GRN QTY
```

Missing: `week_start_date` (handled), `was_in_stock` (defaults to None)

---

## API Endpoints — Complete List

| Method | Path | What It Does |
|--------|------|--------------|
| POST | `/api/v1/auth/login` | JWT login |
| POST | `/api/v1/auth/refresh` | Refresh access token |
| POST | `/api/v1/ingestion/upload` | Upload CSV with type |
| POST | `/api/v1/ingestion/smart-upload` | Auto-detect sheet types |
| GET | `/api/v1/ingestion/uploads` | List uploads |
| GET | `/api/v1/ingestion/uploads/{task_id}/progress` | Poll upload progress |
| GET | `/api/v1/ingestion/uploads/{upload_id}` | Upload details |
| GET | `/api/v1/ingestion/uploads/{upload_id}/errors` | Upload errors |
| GET/POST | `/api/v1/seasons` | Season CRUD |
| GET/POST | `/api/v1/seasons/{id}/otb` | OTB budget (manual entry) |
| GET/POST | `/api/v1/grns` | GRN CRUD |
| GET | `/api/v1/grns/{grn_id}` | GRN detail |
| GET/POST | `/api/v1/stores` | Store CRUD |
| GET/POST | `/api/v1/stores/grades` | Grade CRUD |
| GET/POST | `/api/v1/clusters` | Cluster CRUD |
| GET/POST | `/api/v1/skus` | SKU CRUD |
| POST | `/api/v1/allocation/generate` | Trigger allocation (Celery) |
| GET | `/api/v1/allocation/sessions` | List sessions |
| GET | `/api/v1/allocation/sessions/by-grn/{grn_id}` | Session by GRN |
| GET | `/api/v1/allocation/sessions/{session_id}` | Session + lines |
| POST | `/api/v1/allocation/sessions/{session_id}/recover` | Recover stuck GENERATING |
| POST | `/api/v1/allocation/sessions/{session_id}/approve` | Approve allocation |
| GET | `/api/v1/allocation/sessions/{session_id}/export` | Download CSV |
| PUT | `/api/v1/allocation/lines/{line_id}` | Override line quantity |
| POST | `/api/v1/allocation/simulate` | What-if simulator |
| GET | `/api/v1/performance/styles` | Style sellthrough |
| GET | `/api/v1/performance/stores` | Store KPIs |
| GET | `/api/v1/alerts` | Stockout/overstock alerts |

**Missing:** `/api/v1/buy-plan` — no router despite model existing

---

## Frontend Pages

| Route | What It Does | Status |
|-------|-------------|--------|
| `/login` | Auth | ✅ Works |
| `/dashboard` | Home/overview stats | ✅ Works |
| `/ingestion` | File upload (all types) | ✅ Works |
| `/grn` | List GRNs, create GRN | ✅ Works |
| `/grn/[id]` | GRN detail + reservation management | ✅ Works |
| `/allocation` | List allocation sessions | ✅ Works |
| `/allocation/[id]` | Session review, line overrides, approve | ✅ Works |
| `/performance/styles` | Style sellthrough tracking | ✅ Works |
| `/performance/stores` | Store KPIs | ✅ Works |
| `/setup/seasons` | Season CRUD | ✅ Works |
| `/setup/skus` | SKU master data | ✅ Works |
| `/setup/stores` | Store master data | ✅ Works |
| `/setup/clusters` | Cluster definitions | ✅ Works |
| `/setup/onboarding` | Initial setup wizard | ⚠️ Exists, not guided |

**Missing frontend pages:**
- `/buy-plan` — Purchase planning per style per season
- `/season/[id]/otb` — OTB budget calculator (not just entry form)

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

### Database Connection String
```
postgresql+asyncpg://kyros:kyros_dev_password@localhost:5432/kyros_dev
```

### Common Queries
```bash
# Allocation status
docker exec kyros20-postgres-1 psql -U kyros -d kyros_dev -c \
  "SELECT id, status, total_units_recommended FROM allocation_sessions ORDER BY created_at DESC LIMIT 5;"

# Data counts
docker exec kyros20-postgres-1 psql -U kyros -d kyros_dev -c \
  "SELECT (SELECT COUNT(*) FROM sales_data) AS sales, (SELECT COUNT(*) FROM stores) AS stores, (SELECT COUNT(*) FROM allocation_lines) AS alloc_lines;"

# Restart services
docker compose restart celery_worker backend
```

---

## What NOT To Do

1. **Do not reference `SalesData.season_id`** — column does not exist. Use `upload_id` or join via SKU table (SKU.season_id exists).

2. **Do not default `week_start_date` to today** — collapses all history into one week. Use synthetic spreading across 8 weeks.

3. **Do not call synchronous allocation from async endpoint** — always dispatch to Celery via `run_allocation_task.apply_async()`.

4. **Do not build more allocation complexity** — the engine is already over-engineered for the current pilot. Next features should be in the upstream workflow (buy plan, OTB), not deeper allocation math.

5. **grade_multiplier applied ONCE in engine.py:300** — demand.py stores it for reference but does NOT apply it to weekly_ros.

6. **Always use preload functions** — `preload_stockout_signals()`, `load_sales_history()`, `load_grade_map()` to avoid N+1 queries.

7. **Do not expose health analyzer / benchmark as user-facing** — these are internal QA tools. Pilot users (merchandisers) don't need a "quality score" on the recommendation; they need to understand the recommendation itself.

---

## MVP Roadmap — What To Build Next

Priority order for PMF validation:

### P0 — Complete the Pre-Season Loop (Currently Blocking Pilots)
1. **Buy Plan API + UI** — Let brands record what they're buying (style, category, units, vendor). Link to season. Validate against OTB budget.
2. **GRN → Buy Plan link** — When GRN is created, reference the buy plan line it fulfills
3. **OTB Calculator** — Given last season's actuals and next season targets, calculate recommended OTB per category. Currently manual entry only.

### P1 — Make Allocation Trustworthy for Merchandisers
1. **Simplify allocation explanation** — Current ai_reasoning is a 20-field JSON. Merchandisers need 3 sentences in plain English: "Store X gets 12 units because it sold 4 units/week last season (grade A). This gives 3 weeks of cover."
2. **Guided workflow** — "You're at step 3 of 5. Next: generate allocation for your GRN." No jumping around.
3. **Brand onboarding wizard** — Season → OTB → Upload sales history → Upload grades → Generate. One flow.

### P2 — Post-Season Learning (Differentiator)
1. Feed Season N sellthrough rates back as Season N+1 store grade inputs
2. Update ROS baselines from actual performance
3. Flag stores where allocation accuracy was poor

### Not Building Yet
- Planogram constraints
- Transfer orders
- Markdown strategy
- Multi-country / multi-currency
- POS/WMS integration
- Alert generation (low value pre-season)

---

## The Pilot Situation

- **Data**: SS25 Sales History + SS26 Buy File
- **Stores**: 162
- **Styles**: 3,536
- **Sales rows**: ~281,460
- **SS25 data lacks**: `week_start_date` column (synthetic spreading works)
- **Season**: SS26 (Summer/Spring 2026)
- **Status**: Brands evaluating — waiting to see if allocation recommendations are trustworthy enough to replace their Excel workflow

---

*Last updated: 2026-04-22*
*Based on: full codebase analysis (engine.py 1672L, demand.py 1237L, health.py 413L, benchmark.py 320L, processor.py ~1400L) + README.md product vision*
