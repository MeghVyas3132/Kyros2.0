# Kyros 2.0 — System Overview

> **Internal Reference Only** — This document is the single source of truth for the Kyros 2.0 system architecture, business logic, and codebase layout. Every file in the repository has been audited.

---

## 1. What This System Does (Plain English)

Kyros is an **AI-powered retail allocation engine** for fashion brands. When new inventory arrives at a central warehouse (documented as a GRN — Goods Received Note), Kyros decides how many units of each style and size should be sent to each retail store. It makes these decisions by analyzing historical sales velocity, store performance grades, climate compatibility, display capacity, and dozens of other signals. The result is a recommended allocation that merchandising teams can review, override line-by-line, and approve — all from a browser-based dashboard. The system also tracks post-allocation performance, generates alerts (stockout, overstock, dead stock), and provides quality benchmarks so teams can measure the engine's accuracy over time.

---

## 2. Tech Stack

| Layer | Technology | Version / Notes |
|-------|-----------|----------------|
| **Backend framework** | FastAPI | Python 3.11+ (async) |
| **ORM** | SQLAlchemy 2.x | Async via `asyncpg` driver |
| **Database** | PostgreSQL | 5432 (default) |
| **Task queue** | Celery | Redis broker (db 1), Redis result backend (db 2) |
| **Cache / broker** | Redis | `redis://localhost:6379` |
| **Frontend framework** | Next.js (App Router) | TypeScript, React |
| **State management** | SWR | Client-side data fetching / caching |
| **Auth** | JWT (HS256) | Access tokens (8h), refresh tokens (30d) |
| **File storage** | Local filesystem or AWS S3 | Configurable via `LOCAL_STORAGE` env |
| **Configuration** | Pydantic Settings | `.env` file, `app/config.py` |
| **Data / ML utilities** | Pandas (indirect via data processing) | Statistical calculations in pure Python |
| **Scheduled jobs** | Celery Beat | Crontab: inventory@01:00, performance@02:00, alerts@06:00 IST |

---

## 3. Repository Structure

```
Kyros2.0/
├── backend/
│   ├── app/
│   │   ├── config.py                    # Pydantic Settings — all env vars
│   │   ├── database.py                  # AsyncSessionLocal factory
│   │   ├── main.py                      # FastAPI app, CORS, router mounts
│   │   ├── models/
│   │   │   ├── __init__.py              # Re-exports all models
│   │   │   ├── base.py                  # UUIDMixin, TimestampMixin
│   │   │   ├── user.py                  # User, Brand
│   │   │   ├── store.py                 # Store, StoreCluster
│   │   │   ├── sku.py                   # SKU (core product model)
│   │   │   ├── grn.py                   # GRN, GRNLine
│   │   │   ├── allocation.py            # AllocationSession, AllocationLine, AllocationStatus
│   │   │   ├── season.py                # Season
│   │   │   ├── buy_plan.py              # BuyPlan, BuyPlanLine
│   │   │   ├── sales.py                 # SalesData
│   │   │   ├── inventory.py             # InventoryState, InventoryReservationType, GRNLineReservation
│   │   │   ├── settings.py              # BrandSettings
│   │   │   ├── grades.py                # StoreProductGrade
│   │   │   ├── display_capacity.py      # StoreDisplayCapacity
│   │   │   ├── size_guide.py            # SizeGuide
│   │   │   ├── upload.py                # Upload, UploadStatus
│   │   │   ├── store_behavior.py        # StoreBehaviorProfile
│   │   │   ├── style_store_list.py      # StyleStoreList
│   │   │   ├── alert.py                 # Alert
│   │   │   └── performance.py           # PerformanceSnapshot
│   │   ├── routers/
│   │   │   ├── auth.py                  # Login, register, refresh, me
│   │   │   ├── allocation.py            # Generate, review, approve, simulate, benchmark
│   │   │   ├── ingestion.py             # File upload + processing trigger
│   │   │   ├── stores.py                # CRUD + cluster management
│   │   │   ├── grn.py                   # GRN list, detail, lines
│   │   │   ├── skus.py                  # SKU listing with filters
│   │   │   ├── seasons.py               # Season CRUD
│   │   │   ├── onboarding.py            # Brand + user provisioning
│   │   │   ├── performance.py           # Store performance snapshots
│   │   │   ├── alerts.py                # Alert listing + dismissal
│   │   │   └── clusters.py              # Cluster CRUD
│   │   ├── schemas/
│   │   │   ├── auth.py                  # LoginRequest, RegisterRequest, TokenResponse
│   │   │   ├── allocation.py            # AllocationGenerate, LineUpdate, SimulateRequest
│   │   │   ├── ingestion.py             # UploadCreate, UploadStatus
│   │   │   ├── store.py                 # StoreCreate, StoreUpdate
│   │   │   ├── grn.py                   # GRNResponse, GRNLineResponse
│   │   │   ├── sku.py                   # SKUResponse
│   │   │   ├── season.py                # SeasonCreate, SeasonUpdate, SeasonResponse
│   │   │   ├── onboarding.py            # OnboardingStart
│   │   │   ├── performance.py           # StorePerformanceResponse
│   │   │   └── alert.py                 # AlertResponse, AlertDismiss
│   │   ├── services/
│   │   │   ├── settings.py              # BrandSettings CRUD + deep_merge
│   │   │   ├── allocation/              # ★ Core allocation engine (14 modules)
│   │   │   │   ├── engine.py            # AllocationEngine class (1593 lines)
│   │   │   │   ├── demand.py            # 5-tier demand fallback (1235 lines)
│   │   │   │   ├── cap.py               # Inventory capping + grade-priority enforcement
│   │   │   │   ├── guardrails.py        # Concentration limits + grade coherence
│   │   │   │   ├── intelligence.py      # Strategy detection + MVA enforcement
│   │   │   │   ├── constants.py         # Grade scores, multipliers, cover targets
│   │   │   │   ├── size_curve.py        # Size distribution (store→cluster→brand fallback)
│   │   │   │   ├── store_profile.py     # Category/fabric affinity + velocity archetype
│   │   │   │   ├── health.py            # Allocation health scorer (5 metrics)
│   │   │   │   ├── benchmark.py         # Quality scoring + acceptance checks
│   │   │   │   ├── simulator.py         # What-if quantity simulation
│   │   │   │   ├── explainer.py         # AI reasoning normalization for frontend
│   │   │   │   └── story_concentration.py # Story overlap detection
│   │   │   ├── ingestion/               # Data upload pipeline
│   │   │   │   ├── processor.py         # Master upload dispatcher
│   │   │   │   ├── bulk.py              # Bulk insert/upsert logic
│   │   │   │   ├── lookup.py            # Entity resolution (store/sku/season)
│   │   │   │   ├── mapping.py           # Column mapping + header normalization
│   │   │   │   ├── normalizer.py        # Value cleaning + type coercion
│   │   │   │   ├── understanding.py     # Auto-detect upload file type
│   │   │   │   └── validator.py         # Row-level validation rules
│   │   │   ├── alerts/
│   │   │   │   └── generator.py         # Nightly alert generation
│   │   │   ├── inventory/
│   │   │   │   └── snapshot.py          # Daily inventory state builder
│   │   │   └── performance/
│   │   │       └── calculator.py        # Performance metric snapshots
│   │   ├── tasks/
│   │   │   ├── celery_app.py            # Celery config + beat schedule
│   │   │   ├── allocation.py            # Async allocation task (retry, timeout)
│   │   │   ├── uploads.py               # Upload processing (subprocess isolation)
│   │   │   ├── upload_runner.py         # Subprocess entry point
│   │   │   ├── inventory_snapshot.py    # Daily inventory snapshot job
│   │   │   ├── performance_snapshot.py  # Daily performance job
│   │   │   ├── alert_generation.py      # Daily alert job
│   │   │   └── run_jobs.py              # Manual job runner CLI
│   │   └── utils/
│   │       └── date_utils.py            # UTC datetime helpers
│   ├── scripts/
│   │   ├── seed_season.py               # Seed season data
│   │   └── reset_db_keep_user.py        # Truncate all tables except users/brands/seasons
│   ├── alembic/                         # Database migrations
│   └── requirements.txt
├── frontend/
│   ├── app/
│   │   ├── (auth)/login/                # Login page
│   │   └── (dashboard)/
│   │       ├── allocation/              # Allocation review page
│   │       ├── dashboard/               # Main dashboard
│   │       ├── grn/                     # GRN listing
│   │       ├── ingestion/               # File upload page
│   │       ├── performance/             # Store performance page
│   │       └── setup/                   # Setup / onboarding
│   ├── components/
│   │   ├── allocation/                  # AllocationTable, ReasoningPanel, SimulationPanel
│   │   ├── ingestion/                   # UploadForm, StatusTracker
│   │   ├── performance/                 # PerformanceTable
│   │   ├── shared/                      # Layout, Sidebar, AuthGuard
│   │   └── ui/                          # Base components (Button, Card, Input, etc.)
│   ├── lib/
│   │   ├── api.ts                       # API client (fetch wrapper, JWT management)
│   │   ├── utils.ts                     # Frontend utility functions
│   │   └── hooks/
│   │       ├── useAllocation.ts         # SWR hook: allocation session detail
│   │       ├── useAlerts.ts             # SWR hook: alert counts + listing
│   │       ├── useAuth.ts              # Auth hook: login, logout, user state
│   │       ├── useGrns.ts              # SWR hook: GRN listing
│   │       └── usePerformance.ts       # SWR hook: store performance
│   └── types/index.ts                   # All TypeScript interfaces (314 lines)
└── SYSTEM_OVERVIEW.md                   # This file
```

---

## 4. Database Schema (Complete)

### Users & Brands

#### `brands`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK, default gen |
| `name` | VARCHAR | NOT NULL |
| `slug` | VARCHAR | UNIQUE |
| `is_active` | BOOLEAN | default `true` |
| `created_at` / `updated_at` | TIMESTAMP | auto |

#### `users`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `email` | VARCHAR | UNIQUE |
| `hashed_password` | VARCHAR | NOT NULL |
| `full_name` | VARCHAR | |
| `role` | ENUM | `ADMIN`, `PLANNER`, `VIEWER` |
| `is_active` | BOOLEAN | default `true` |
| `created_at` / `updated_at` | TIMESTAMP | auto |

---

### Stores & Clusters

#### `stores`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `store_code` | VARCHAR | NOT NULL |
| `store_name` | VARCHAR | |
| `city` | VARCHAR | |
| `state` | VARCHAR | |
| `region` | VARCHAR | |
| `climate_zone` | VARCHAR | `North`, `South`, etc. |
| `cluster_id` | UUID | FK → `store_clusters.id`, nullable |
| `is_active` | BOOLEAN | default `true` |
| `created_at` / `updated_at` | TIMESTAMP | auto |

#### `store_clusters`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `name` | VARCHAR | NOT NULL |
| `description` | TEXT | |
| `created_at` / `updated_at` | TIMESTAMP | auto |

---

### Products

#### `skus`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `sku_code` | VARCHAR | UNIQUE per brand |
| `style_code` | VARCHAR | groups size-level SKUs into one style |
| `style_name` | VARCHAR | |
| `category` | VARCHAR | e.g. `Shirts`, `Trousers` |
| `sub_category` | VARCHAR | |
| `fabric` | VARCHAR | e.g. `Cotton`, `Wool` |
| `colour` | VARCHAR | |
| `colour_family` | VARCHAR | |
| `size` | VARCHAR | e.g. `S`, `M`, `L`, `38`, `FREE SIZE` |
| `price_band` | VARCHAR | e.g. `MID`, `PREMIUM` |
| `mrp` | NUMERIC | Maximum Retail Price |
| `story` | VARCHAR | story/collection name for cannibalization logic |
| `sub_story` | VARCHAR | |
| `store_group_rule` | VARCHAR | `All Stores`, `A+ Only`, `A+ & A`, `A+, A & B` |
| `resolved_min_grade` | VARCHAR | minimum store grade to receive this SKU |
| `style_risk_group` | VARCHAR | `PROVEN`, `CONFIDENT`, `EXPERIMENTAL` |
| `resolved_risk_level` | VARCHAR | |
| `store_list_id` | UUID | FK → `style_store_lists.id`, nullable |
| `season_id` | UUID | FK → `seasons.id`, nullable |
| `created_at` / `updated_at` | TIMESTAMP | auto |

#### `style_store_lists`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `name` | VARCHAR | |
| `store_ids` | ARRAY(UUID) | explicit store whitelist |
| `created_at` / `updated_at` | TIMESTAMP | auto |

---

### GRN (Goods Received Notes)

#### `grns`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `grn_code` | VARCHAR | unique receipt code |
| `grn_date` | DATE | |
| `warehouse_id` | VARCHAR | nullable |
| `supplier_name` | VARCHAR | nullable |
| `status` | ENUM | `RECEIVED`, `ALLOCATED`, `DISPATCHED` |
| `total_units` | INTEGER | sum of all GRN lines |
| `total_skus` | INTEGER | count of distinct SKUs |
| `season_id` | UUID | FK → `seasons.id` |
| `created_at` / `updated_at` | TIMESTAMP | auto |

#### `grn_lines`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `grn_id` | UUID | FK → `grns.id` |
| `brand_id` | UUID | FK → `brands.id` |
| `sku_id` | UUID | FK → `skus.id` |
| `units_received` | INTEGER | physical units received |
| `ecom_reserved_qty` | INTEGER | held for e-commerce |
| `ars_reserved_qty` | INTEGER | held for ARS (auto-replenishment) |
| `buy_plan_line_id` | UUID | FK → `buy_plan_lines.id`, nullable |
| `created_at` / `updated_at` | TIMESTAMP | auto |

#### `grn_line_reservations`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `grn_line_id` | UUID | FK → `grn_lines.id` |
| `reservation_type_id` | UUID | FK → `inventory_reservation_types.id` |
| `reserved_qty` | INTEGER | |

#### `inventory_reservation_types`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `code` | VARCHAR | e.g. `ECOM`, `ARS` |
| `label` | VARCHAR | |
| `is_active` | BOOLEAN | |
| `deducts_from_first_allocation` | BOOLEAN | whether to subtract from available qty |

---

### Seasons & Buy Plans

#### `seasons`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `name` | VARCHAR | e.g. `SS25`, `AW24` |
| `start_date` | DATE | |
| `end_date` | DATE | |
| `created_at` / `updated_at` | TIMESTAMP | auto |

#### `buy_plans` / `buy_plan_lines`
Buy plan data ingested from files. Lines link to GRN lines to carry the `store_group_rule` override.

---

### Allocation

#### `allocation_sessions`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `grn_id` | UUID | FK → `grns.id` |
| `season_id` | UUID | FK → `seasons.id` |
| `status` | ENUM | `DRAFT`, `GENERATING`, `FAILED`, `UNDER_REVIEW`, `APPROVED`, `DISPATCHED`, `CANCELLED` |
| `total_stores` | INTEGER | |
| `total_skus` | INTEGER | count of unique styles processed |
| `total_units_recommended` | INTEGER | |
| `total_units_approved` | INTEGER | |
| `health_score` | INTEGER | 0–100 |
| `health_report` | JSONB | full health analysis payload |
| `decision` | JSONB | approval recommendation |
| `failure_reason` | TEXT | |
| `approved_by` | UUID | FK → `users.id` |
| `approved_at` | TIMESTAMP | |
| `generated_at` | TIMESTAMP | |
| `created_at` / `updated_at` | TIMESTAMP | auto |

#### `allocation_lines`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `session_id` | UUID | FK → `allocation_sessions.id` |
| `brand_id` | UUID | FK → `brands.id` |
| `store_id` | UUID | FK → `stores.id` |
| `sku_id` | UUID | FK → `skus.id` |
| `ai_recommended_qty` | INTEGER | engine's recommendation |
| `final_qty` | INTEGER | after human override |
| `ai_confidence` | VARCHAR | `HIGH`, `MEDIUM`, `LOW` |
| `ai_reasoning` | JSONB | ~40-field explainability payload |
| `ai_projections` | JSONB | size_split, cap_scale_factor, etc. |
| `was_overridden` | BOOLEAN | |
| `override_reason` | VARCHAR | |
| `override_notes` | TEXT | |
| `created_at` / `updated_at` | TIMESTAMP | auto |

---

### Grades, Capacity & Size Guides

#### `store_product_grades`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `store_id` | UUID | FK → `stores.id` |
| `product_category` | VARCHAR | |
| `price_band` | VARCHAR | nullable |
| `grade` | VARCHAR | `A+`, `A`, `B`, `C` |

#### `store_display_capacities`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `store_id` | UUID | FK → `stores.id` |
| `category` | VARCHAR | |
| `max_units` | INTEGER | nullable |
| `max_styles` | INTEGER | nullable (fallback: `max_styles × 6`) |

#### `size_guides`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `product_category` | VARCHAR | |
| `size` | VARCHAR | |
| `min_max_ratio` | FLOAT | 0 = size blocked entirely |
| `display_order` | INTEGER | |
| `applies_to_grades` | VARCHAR | `ALL`, `A+_ONLY`, `A+_A`, `A+_A_B` |
| `is_size_set` | BOOLEAN | combined size sets (e.g. `S/M`) |

---

### Sales, Inventory & Performance

#### `sales_data`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `store_id` | UUID | FK → `stores.id` |
| `sku_id` | UUID | FK → `skus.id` |
| `week_start_date` | DATE | |
| `units_sold` | INTEGER | |
| `was_in_stock` | BOOLEAN | nullable |

#### `inventory_state`
| Column | Type | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → `brands.id` |
| `location_id` | VARCHAR | store_id as string |
| `location_type` | VARCHAR | `STORE` |
| `sku_id` | UUID | FK → `skus.id` |
| `snapshot_date` | DATE | |
| `units_on_hand` | INTEGER | |
| `ros_7d` | FLOAT | 7-day rate of sale |

#### `performance_snapshots`
Daily store-level metrics: `sell_through_pct`, `avg_ros`, `stock_cover_days`, style breakdowns by health status.

#### `store_behavior_profiles`
Per-store affinity signals: `primary_category_affinity`, `primary_fabric_affinity`, `category_affinity_score`, `fabric_affinity_score`, `sample_size`, `profile_window_weeks`.

---

### Other

#### `uploads`
Tracks CSV/Excel file uploads. Columns: `id`, `brand_id`, `file_name`, `file_type` (ENUM: stores, skus, grns, sales, grades, etc.), `status` (PENDING, PROCESSING, DONE, FAILED), `total_rows`, `successful_rows`, `failed_rows`, `errors` (JSONB), `s3_key`.

#### `alerts`
System-generated alerts: `id`, `brand_id`, `alert_type` (stockout_risk, overstock, dead_stock, etc.), `severity` (HIGH, MEDIUM, LOW), `title`, `message`, `store_id`, `sku_id`, `grn_id`, `action_url`, `is_read`, `is_dismissed`, `generated_at`.

#### `brand_settings`
Per-brand JSON config: `id`, `brand_id` (UNIQUE), `config` (JSONB). Stores `min_presentation_qty`, `season_weeks_remaining`, `max_store_pct`, `min_depth`, allocation strategy overrides, etc.

---

## 5. API Surface (Complete)

All routes prefixed with `/api/v1/`. Standard envelope: `{ data: T, meta: { request_id, timestamp } }`.

### Auth (`/api/v1/auth/`)
| Method | Path | Description | Auth |
|--------|------|-------------|------|
| POST | `/login` | Email + password → JWT tokens | No |
| POST | `/register` | Create user (admin only) | Yes |
| POST | `/refresh` | Refresh access token | No (refresh token in body) |
| GET | `/me` | Current user info | Yes |

### Allocation (`/api/v1/allocation/`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate` | Dispatch allocation (→ Celery task) |
| GET | `/sessions/{id}` | Session detail + paginated lines |
| GET | `/sessions` | List sessions for brand |
| PATCH | `/sessions/{id}/lines` | Batch update final_qty (override) |
| POST | `/sessions/{id}/approve` | Mark APPROVED |
| POST | `/sessions/{id}/cancel` | Mark CANCELLED |
| POST | `/simulate` | What-if simulation for a store×SKU×qty |
| GET | `/sessions/{id}/benchmark` | Quality benchmark report |
| GET | `/sessions/{id}/insights` | Lost sales, coverage, confidence breakdown |
| GET | `/sessions/{id}/story-concentration/{store_id}` | Story overlap for a store |
| GET | `/sessions/{id}/health` | Health score + sub-scores |

### Ingestion (`/api/v1/ingestion/`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/upload` | Upload CSV/Excel file (multipart) |
| GET | `/uploads` | List uploads for brand |
| GET | `/uploads/{id}` | Upload status + error details |

### Stores (`/api/v1/stores/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List all stores (filterable) |
| POST | `/` | Create store |
| PATCH | `/{id}` | Update store |
| POST | `/bulk` | Bulk upsert |

### GRN (`/api/v1/grns/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List GRNs |
| GET | `/{id}` | GRN detail + lines |

### SKUs (`/api/v1/skus/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List SKUs (filter by category, season, style_code, etc.) |

### Seasons (`/api/v1/seasons/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List seasons |
| POST | `/` | Create season |
| PATCH | `/{id}` | Update season dates |
| DELETE | `/{id}` | Delete season |

### Clusters (`/api/v1/clusters/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List clusters |
| POST | `/` | Create cluster |
| PATCH | `/{id}` | Update cluster |
| DELETE | `/{id}` | Delete cluster |

### Onboarding (`/api/v1/onboarding/`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/start` | Provision brand + admin user |

### Performance (`/api/v1/performance/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/stores` | Store-level performance metrics |
| GET | `/stores/{id}` | Individual store performance |

### Alerts (`/api/v1/alerts/`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | List alerts (filter by severity, read status) |
| GET | `/counts` | Unread alert counts by severity |
| POST | `/{id}/dismiss` | Dismiss an alert |
| POST | `/{id}/read` | Mark alert as read |

---

## 6. Business Logic Overview

### The Allocation Lifecycle

```
1. GRN received → status RECEIVED
2. User clicks "Generate Allocation" → AllocationSession created (GENERATING)
3. Celery task dispatches AllocationEngine.generate()
4. Engine groups GRN lines by style_code
5. For each style:
   a. Filter eligible stores (group rule, climate, display capacity)
   b. Score stores (50% ROS + 25% Grade + 25% Cover)
   c. Filter by eligibility (store list, min grade, climate, capacity)
   d. Detect strategy (depth_first / balanced / spread_first)
   e. Prioritize stores (narrow to affordable count at min depth)
   f. Calculate demand per store (5-tier fallback)
   g. Apply demand multipliers (grade, affinity)
   h. Distribute units proportionally to scores
   i. Apply story cannibalization (0.65 factor)
   j. Cap to available inventory
   k. Enforce MVA (minimum viable allocation)
   l. Apply guardrails (30% concentration, grade coherence)
   m. Apply constraints (display capacity)
   n. Filter by size eligibility
   o. Top-up with residual demand
   p. Split into per-size quantities
   q. Write AllocationLine per (store × size-SKU)
6. Run health analysis → score + decision
7. Session → UNDER_REVIEW
8. User reviews, overrides, approves → APPROVED
```

---

## 7. Allocation Engine Deep-Dive

### 7.1 Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `GRADE_SCORES` | `A+:5, A:4, B:3, C:2` | Numeric ranking for grades |
| `GRADE_MULTIPLIERS` | `A+:1.25, A:1.00, B:0.75, C:0.50` | Demand multiplier by grade |
| `MINIMUM_ALLOCATION_QTY` | `6` | Min units per store for standard styles |
| `DEFAULT_MIN_PRESENTATION_QTY` | `2` | Absolute minimum to "present" on shelf |
| `DEFAULT_SEASON_WEEKS_REMAINING` | `8` | Fallback if no season dates |
| `DEFAULT_COVER_TARGETS` | Matrix | Weeks of cover by (risk × grade) |

**Cover target matrix (weeks):**

| Risk \ Grade | A+ | A | B | C |
|----------|---|---|---|---|
| **PROVEN** | 7 | 5 | 4 | 3 |
| **CONFIDENT** | 6 | 5 | 3 | 2 |
| **EXPERIMENTAL** | 4 | 3 | 2 | 0 |

### 7.2 Store Scoring

Three-component weighted score, min-max normalized across all eligible stores:

```
Score = 0.50 × norm(ROS) + 0.25 × norm(Grade) + 0.25 × norm(1/Cover)
```

- **ROS component**: Category×fabric×price_band attribute-level rate of sale
- **Grade component**: Numeric grade score (5 for A+, down to 2 for C)
- **Cover component**: Inverse of current stock cover (lower cover = higher need)

Cold-start scoring: When `sample_size == 0` and `scoring_mode == "GRADE_ONLY"`, ROS component is zeroed; scores are entirely grade-driven.

### 7.3 Demand Calculation (5-Tier Fallback)

For each store × SKU:

| Tier | Source | Description |
|------|--------|-------------|
| **1** | `store_historical` | Store-specific ROS for this exact SKU, with stockout correction |
| **2** | `cluster_average` | Average ROS across all stores in the same cluster |
| **3** | `grade_average` | Average ROS across all stores of the same grade |
| **4** | `style_dna_analogue` | Weighted average ROS of similar styles (≥45% similarity) |
| **5** | `minimum_presentation` | Hard floor: `min_presentation_qty` units, 0 ROS |

**Stockout correction**: Detects weeks where a store ran out of stock (via `was_in_stock` flag or zero-sales tail). Calculates what the full-season ROS would have been if stock had been available, then uses the higher of corrected vs. raw ROS.

**Style DNA matching**: When no direct or aggregated history exists, the engine finds similar styles that sold at the same store. Similarity is scored by: category (35%), fabric (20%), price_band (15%), colour_family (15%), risk_level (10%), sub_category (5%). Top 5 matches (≥45% similarity) are weighted-averaged.

**Demand formula**:
```
base_demand = weekly_ros × grade_multiplier × affinity_multiplier × cover_target_weeks
```

### 7.4 Affinity Multiplier

Computed from `StoreBehaviorProfile`:
- If the store's top category matches the SKU's category AND the affinity score > 1.0 → multiply by `min(score, 1.5)`
- Same logic for fabric affinity
- Total affinity multiplier capped at 1.8

### 7.5 Strategy Detection & Prioritization

**Auto-detect strategy** based on `depth_ratio = available_units / (eligible_stores × min_depth)`:

| Condition | Strategy | Effect |
|-----------|----------|--------|
| EXPERIMENTAL or depth_ratio < 0.5 | `depth_first` | Top 35% of stores only |
| depth_ratio ≥ 1.5 | `spread_first` | All eligible stores |
| Otherwise | `balanced` | Top 65% of stores |

Minimum 3 stores always served (if eligible).

### 7.6 MVA Enforcement

Minimum Viable Allocation scales by grade:
- A+ → 1.5× base MVA
- A → 1.2× base MVA
- B → 1.0× base MVA
- C → 0.8× base MVA

Stores below their effective MVA are removed; freed units redistributed proportionally to score among survivors.

### 7.7 Inventory Capping

`apply_inventory_cap()`:
1. If total demand ≤ available → no capping
2. Scale all demands by `available / total_demand`
3. Fix rounding to sum exactly to available
4. Enforce minimums:
   - If enough inventory for all stores at minimum → raise everyone to floor
   - Otherwise → allocate by grade priority (A+ first, then A, B, C)

### 7.8 Guardrails

Three rules:
1. **Max concentration**: No single store gets > 30% of available units (configurable via `max_store_pct`)
2. **Min store count**: Warning if < 3 stores receive units (when ≥ 18 available)
3. **Grade coherence**: Warning if A+ store gets < 50% of what a C store gets

### 7.9 Story Cannibalization

If a style belongs to a `story` and there are already allocated colourways of the same story + (same fabric OR same sub_story) at a store, the allocation is dampened by **0.65 factor**.

### 7.10 Size Distribution

Three-tier fallback for size ratios:
1. **Store-level historical** sales in this category
2. **Cluster-level historical** sales
3. **Brand-level historical** sales

Size guide `min_max_ratio` values provide base weights. Historical ratios adjust weights (capped at 1.5× of expected). Special handling for:
- `FREE SIZE` / `ONE SIZE` → 100% allocation
- Size sets (e.g., `S/M`, `L/XL`) → dedicated distribution logic

### 7.11 Confidence Classification

| Condition | Confidence |
|-----------|-----------|
| `sample_size ≥ 20` | HIGH |
| `sample_size ≥ 5` | MEDIUM |
| `sample_size < 5` | LOW |
| `sample_size == 0` + GRADE_ONLY mode | LOW |

**Numeric confidence score (Phase 2)**:
Base scores by source: store_historical (0.80), cluster (0.55), grade (0.40), style_dna (0.30), minimum_presentation (0.10). Adjusted by sample size and cap severity.

### 7.12 Health Analysis

Five sub-metrics (weighted):
| Metric | Weight | What it measures |
|--------|--------|-----------------|
| Coverage | 0.30 | % of lines with healthy weeks-cover (4–8 weeks) |
| Demand alignment | 0.25 | % of lines where final_qty ≈ raw demand (0.7–1.2×) |
| Confidence | 0.20 | Distribution of HIGH/MEDIUM/LOW |
| Presentation | 0.15 | % of stores with adequate depth (>4 units total) |
| Balance | 0.10 | Top-5-store concentration (ideal < 40%) |

**Hard penalties** applied to base score:
- Stockout risk > 15% → up to −20 pts
- Thin presentation > 40% → up to −15 pts

**Labels**: SAFE (≥75), CAUTION (≥55), RISKY (≥35), CRITICAL (<35)

**Decision engine**:
| Score | Verdict | Action |
|-------|---------|--------|
| ≥75 | APPROVE | Safe to release |
| ≥55 | APPROVE_WITH_CAUTION | Release Tier 1–2 only, hold rest |
| ≥35 | REVIEW_REQUIRED | Manual override needed |
| <35 | REJECT | Do not release |

### 7.13 Benchmark Report

Quality scoring formula:
```
quality_score = 100 × (
  0.30 × (1 − override_rate)
  + 0.25 × grade_compliance_rate
  + 0.20 × min(inventory_utilization_rate, 1.0)
  + 0.15 × (1 − under_coverage_rate)
  + 0.10 × high_confidence_share
)
```

Acceptance checks (all must pass):
- Override rate ≤ 20%
- Under-coverage rate ≤ 25%
- Grade compliance ≥ 98%
- Inventory utilization ≥ 95%
- High confidence share ≥ 50%

---

## 8. Background Jobs (Celery)

| Task | Schedule | Description |
|------|----------|-------------|
| `build_inventory_snapshots` | Daily 01:00 IST | Builds `inventory_state` rows for all brands |
| `build_performance_snapshots` | Daily 02:00 IST | Builds `performance_snapshots` for all brands |
| `generate_alerts_task` | Daily 06:00 IST | Generates stockout/overstock/dead-stock alerts |
| `process_upload_task` | On demand | Processes uploaded files (runs in subprocess for isolation) |
| `run_allocation_task` | On demand | Runs full allocation engine for a GRN |

### Allocation Task Configuration
- **Max retries**: 2 (with 30s × (retry#) backoff)
- **Soft time limit**: 30 minutes
- **Hard time limit**: 35 minutes
- Failure is persisted to `allocation_sessions.failure_reason`

### Upload Processing
Uploads run in a **subprocess** (`upload_runner.py`) for memory isolation. If Celery is unreachable, a synchronous subprocess fallback is used.

---

## 9. Frontend Components

### Pages (Next.js App Router)
| Route | Page | Description |
|-------|------|-------------|
| `/login` | AuthLogin | Email + password form |
| `/dashboard` | Dashboard | Overview metrics |
| `/allocation` | AllocationReview | Session detail with line-level table |
| `/grn` | GRNList | GRN browser |
| `/ingestion` | IngestionUpload | Drag-and-drop file upload |
| `/performance` | PerformanceView | Store performance metrics |
| `/setup` | Setup | Brand onboarding |

### Key Component Groups
- **allocation/** — `AllocationTable` (sortable/filterable data grid), `ReasoningPanel` (AI explainability drawer), `SimulationPanel` (what-if slider)
- **ingestion/** — `UploadForm` (file type selector + drag-drop), `StatusTracker` (upload progress)
- **performance/** — `PerformanceTable` (store-level metrics grid)
- **shared/** — `Layout`, `Sidebar`, `AuthGuard` (JWT route protection)
- **ui/** — Base design system: `Button`, `Card`, `Input`, `Select`, `Badge`, `Dialog`, etc.

### Data Fetching Pattern
- **SWR** hooks wrap every API call with automatic revalidation
- **API client** (`lib/api.ts`) handles: JWT injection, 401 auto-refresh, request timeouts (12s default), retry logic, error parsing
- Tokens stored in `localStorage` (`kyros_access_token`, `kyros_refresh_token`)

---

## 10. Data Ingestion Pipeline

### Supported File Types
Files are uploaded via the `/api/v1/ingestion/upload` endpoint (multipart). The `understanding.py` module auto-detects file type from headers/content:

| File Type | Creates/Updates |
|-----------|----------------|
| Stores | `stores` table |
| SKUs | `skus` table |
| GRNs + GRN Lines | `grns` + `grn_lines` tables |
| Sales Data | `sales_data` table |
| Store Grades | `store_product_grades` table |
| Size Guides | `size_guides` table |
| Display Capacity | `store_display_capacities` table |
| Buy Plans | `buy_plans` + `buy_plan_lines` tables |
| Inventory | `inventory_state` table |
| Reservation Types | `inventory_reservation_types` table |
| GRN Reservations | `grn_line_reservations` table |

### Pipeline Flow
```
Upload → Understand (auto-detect type) → Map (normalize columns)
       → Validate (required fields, types) → Normalize (clean values)
       → Lookup (resolve FKs: store_code→store_id, sku_code→sku_id)
       → Bulk Upsert → Report success/failure counts
```

---

## 11. Mocked, Hardcoded, and Missing Features

### Hardcoded Values
| Location | Value | Notes |
|----------|-------|-------|
| `engine.py:60–61` | `ROS_WEIGHT=0.50, GRADE_WEIGHT=0.25, COVER_WEIGHT=0.25` | Store scoring weights not configurable |
| `engine.py:63–66` | `CLIMATE_RULES` | Only South→blocked fabrics. North has empty rules |
| `guardrails.py:23` | `max_store_pct=0.30` | Default 30% concentration limit |
| `guardrails.py:34` | `min_store_count=3, min_units=18` | Hardcoded minimum store count threshold |
| `intelligence.py:83` | MVA grade multipliers | `A+:1.5, A:1.2, B:1.0, C:0.8` inline |
| `engine.py:1463` | Cannibalization factor `0.65` | Not configurable |
| `config.py:25` | `JWT_ACCESS_TOKEN_EXPIRE_HOURS=8` | Non-configurable via brand settings |
| `api.ts:4` | `DEFAULT_REQUEST_TIMEOUT_MS=12000` | Frontend request timeout |

### Placeholder / Stub Implementations
| Location | Description |
|----------|-------------|
| `health.py:39–49` | `get_context()` returns hardcoded `is_cold_start: True, season_week: 1` — not connected to actual season |
| `store_profile.py:357` | Velocity archetype is computed but **never persisted** or used in allocation |
| `filter_eligible()` L1040 | `del inventory` — inventory-specific eligibility check stubbed with TODO |
| `demand.py:1166–1169` | `calculate_demand_with_fallback()` has TODO noting it's a future replacement for `calculate_store_demand_details()` |
| `intelligence.py` | Strategy detection uses simple ratio thresholds — no ML component |

### Missing Features (Referenced but Not Implemented)
| Feature | Evidence |
|---------|---------|
| **Multi-warehouse allocation** | `GRN.warehouse_id` exists but engine treats all GRNs as single-source |
| **GRN dispatch tracking** | `AllocationStatus.DISPATCHED` exists but no dispatch workflow endpoint |
| **Inventory reservation UI** | Backend supports typed reservations but no frontend management |
| **Season-aware health context** | Health analyzer has `get_context()` placeholder, not wired to season model |
| **Replenishment / follow-up allocation** | Simulator notes mention "follow-up allocation" but no automated reorder logic |
| **User activity audit log** | No audit trail for overrides, approvals, or config changes |
| **Role-based access control** | User has `role` field (`ADMIN`, `PLANNER`, `VIEWER`) but middleware only enforces auth, not role-specific permissions |
| **Email notifications** | No email service or notification system |
| **Real-time WebSocket updates** | Allocation polling uses HTTP; no push-based status updates |
| **Performance trend visualization** | Backend snapshots exist but frontend only shows latest snapshot |
| **Cluster-based profiles** | `StoreCluster` model exists, cluster_id used in size fallback, but no dedicated cluster analytics page |

---

*Generated from exhaustive codebase audit — every file in the repository was read before producing this document.*
