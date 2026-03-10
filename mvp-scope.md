# Kyros MVP — Engineering Specification
### Version: 1.0 | Status: Active Build Reference | Audience: Engineers + GitHub Copilot

---

## Table of Contents

1. [What We Are Building](#1-what-we-are-building)
2. [What We Are NOT Building](#2-what-we-are-not-building)
3. [Tech Stack](#3-tech-stack)
4. [Project Structure](#4-project-structure)
5. [Database Schema](#5-database-schema)
6. [Module 1: Data Ingestion](#6-module-1-data-ingestion)
7. [Module 2: Inventory Truth Engine](#7-module-2-inventory-truth-engine)
8. [Module 3: Season and Setup](#8-module-3-season-and-setup)
9. [Module 4: Allocation Engine](#9-module-4-allocation-engine)
10. [Module 5: Performance Dashboard](#10-module-5-performance-dashboard)
11. [Module 6: Alerts](#11-module-6-alerts)
12. [API Endpoints](#12-api-endpoints)
13. [Background Jobs](#13-background-jobs)
14. [Frontend Screens](#14-frontend-screens)
15. [Auth and RBAC](#15-auth-and-rbac)
16. [Error Handling Standards](#16-error-handling-standards)
17. [16-Week Engineering Plan](#17-16-week-engineering-plan)
18. [Success Metrics](#18-success-metrics)

---

## 1. What We Are Building

**Kyros v1** is an allocation intelligence platform for Indian fashion retail brands (50–500 stores).

### The Core Problem
An allocator at a 150-store brand spends 3–5 days building an allocation in Excel every time a GRN (Goods Received Note) arrives. They manually cross-reference: store grades, trailing ROS by attribute, display capacity, size curves, current stock positions — all from separate files. 40% of what they allocate gets transferred out 6 weeks later because the allocation was wrong.

### The Core Solution
Kyros ingests a GRN, generates a recommended allocation for every SKU across every eligible store in under 30 seconds, explains every recommendation in plain language, lets the planner adjust and simulate scenarios, tracks what actually happened vs what was recommended, and gets smarter over time.

### The One User
**The Allocator / Merchandising Planner.** Not the CEO. Not the CFO. The person who opens their laptop at 9am when a GRN arrives and decides where inventory goes. If this person opens Kyros every morning because it saves them time, the product is working.

### How We Know It's Working
**Transfer rate drops.** Transfer rate = stock moved between stores after initial allocation. If Kyros is allocating correctly, less stock needs to move later. This is measurable, fast to observe, and something every brand already tracks.

---

## 2. What We Are NOT Building

Be ruthless about this. If it is not on the list in Section 1, it does not get built in v1.

| Not Building | Why Deferred |
|---|---|
| Full OTB dynamic engine with real-time recalculation | Pilots need OTB as a number, not an engine |
| Range planning module | No validated assumption on how planners structure this yet |
| Buy planning and PO management | Brands have this in their ERP/Excel |
| Vendor management | Not needed for allocation |
| Demand forecasting ML model | Need 2 seasons of override data first |
| Markdown optimisation | In-season action — comes after allocation is validated |
| Replenishment engine | Comes after allocation |
| Post-season learning loop | Needs a full season to complete first |
| Transfer recommendation engine | Comes after allocation is trusted |
| Cross-brand federated learning | No data yet |
| Mobile app | Desktop workflow for now |
| WMS integration | CSV export is sufficient for v1 |
| External REST API | No external customers yet |
| Kubernetes | ECS is sufficient |
| Elasticsearch | Postgres full-text search is sufficient |

**Rule for any new feature request during v1 build:**
Ask: "Did a real pilot show us they cannot complete their allocation workflow without this?" If no → defer.

---

## 3. Tech Stack

### Backend
```
Language:         Python 3.11+
Framework:        FastAPI 0.109+
ORM:              SQLAlchemy 2.0+ (async)
Migrations:       Alembic
Validation:       Pydantic v2
Auth:             python-jose (JWT), passlib (bcrypt)
Task Queue:       Celery 5.x
Message Broker:   Redis 7+
HTTP Client:      httpx
Testing:          pytest, pytest-asyncio, httpx (for API tests)
```

### Frontend
```
Framework:        Next.js 14 (App Router)
Language:         TypeScript 5
Styling:          Tailwind CSS 3
Forms:            React Hook Form 7 + Zod 3
Data Fetching:    SWR 2
Tables:           TanStack Table 8
Charts:           Recharts 2
Icons:            Lucide React
```

### Data
```
Primary DB:       PostgreSQL 15+ (AWS RDS)
Cache/Queue:      Redis 7+ (AWS ElastiCache)
File Storage:     AWS S3 (CSV uploads)
```

### Infrastructure
```
Containers:       Docker
Orchestration:    AWS ECS (NOT Kubernetes in v1)
Load Balancer:    AWS ALB
CI/CD:            GitHub Actions
Monitoring:       AWS CloudWatch (v1), Prometheus + Grafana (later)
Logging:          Structured JSON logs → AWS CloudWatch
```

### Development
```
Package Manager:  uv (Python), pnpm (Node)
Linting:          ruff (Python), ESLint (TS)
Formatting:       black (Python), prettier (TS)
Type Checking:    mypy (Python), tsc (TS)
```

---

## 4. Project Structure

```
kyros/
├── backend/
│   ├── alembic/
│   │   ├── versions/
│   │   └── env.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app factory
│   │   ├── config.py                  # Settings via pydantic-settings
│   │   ├── database.py                # Async SQLAlchemy engine + session
│   │   ├── dependencies.py            # FastAPI dependency injection
│   │   │
│   │   ├── models/                    # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── brand.py
│   │   │   ├── store.py
│   │   │   ├── cluster.py
│   │   │   ├── sku.py
│   │   │   ├── season.py
│   │   │   ├── otb.py
│   │   │   ├── grn.py
│   │   │   ├── inventory_state.py
│   │   │   ├── allocation.py
│   │   │   ├── performance_snapshot.py
│   │   │   └── alert.py
│   │   │
│   │   ├── schemas/                   # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── user.py
│   │   │   ├── store.py
│   │   │   ├── sku.py
│   │   │   ├── season.py
│   │   │   ├── ingestion.py
│   │   │   ├── allocation.py
│   │   │   ├── performance.py
│   │   │   └── alert.py
│   │   │
│   │   ├── routers/                   # FastAPI routers
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── stores.py
│   │   │   ├── skus.py
│   │   │   ├── seasons.py
│   │   │   ├── ingestion.py
│   │   │   ├── grn.py
│   │   │   ├── allocation.py
│   │   │   ├── performance.py
│   │   │   └── alerts.py
│   │   │
│   │   ├── services/                  # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── ingestion/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── validator.py       # Schema + reference + business validation
│   │   │   │   ├── normalizer.py      # Messy data cleaning
│   │   │   │   └── processor.py       # Validated data → DB
│   │   │   ├── inventory/
│   │   │   │   ├── __init__.py
│   │   │   │   └── snapshot.py        # Daily inventory truth builder
│   │   │   ├── allocation/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── engine.py          # Core allocation scoring
│   │   │   │   ├── constraints.py     # Hard constraint application
│   │   │   │   ├── size_curve.py      # Size distribution logic
│   │   │   │   ├── explainer.py       # Generates human-readable reasoning
│   │   │   │   └── simulator.py       # Scenario simulation
│   │   │   ├── performance/
│   │   │   │   ├── __init__.py
│   │   │   │   └── calculator.py      # ROS, ST%, cover, status
│   │   │   └── alerts/
│   │   │       ├── __init__.py
│   │   │       └── generator.py       # Alert detection rules
│   │   │
│   │   ├── tasks/                     # Celery tasks
│   │   │   ├── __init__.py
│   │   │   ├── celery_app.py
│   │   │   ├── inventory_snapshot.py  # Runs nightly at 1 AM
│   │   │   ├── performance_snapshot.py # Runs nightly at 2 AM
│   │   │   └── alert_generation.py    # Runs nightly at 6 AM
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── csv_parser.py
│   │       ├── s3.py
│   │       └── date_utils.py
│   │
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_ingestion/
│   │   ├── test_allocation/
│   │   ├── test_inventory/
│   │   └── test_api/
│   │
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── alembic.ini
│
├── frontend/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx                   # Redirect to dashboard
│   │   ├── (auth)/
│   │   │   ├── login/page.tsx
│   │   │   └── layout.tsx
│   │   └── (dashboard)/
│   │       ├── layout.tsx
│   │       ├── dashboard/page.tsx     # Home — alerts + recent GRNs
│   │       ├── setup/
│   │       │   ├── stores/page.tsx
│   │       │   ├── clusters/page.tsx
│   │       │   ├── skus/page.tsx
│   │       │   └── seasons/page.tsx
│   │       ├── ingestion/
│   │       │   └── page.tsx           # Upload hub
│   │       ├── grn/
│   │       │   ├── page.tsx           # GRN list
│   │       │   └── [id]/page.tsx      # GRN detail + allocation
│   │       └── performance/
│   │           ├── styles/page.tsx
│   │           └── stores/page.tsx
│   │
│   ├── components/
│   │   ├── ui/                        # Base components (Button, Input, Table etc)
│   │   ├── allocation/
│   │   │   ├── AllocationTable.tsx
│   │   │   ├── ExplainabilityPanel.tsx
│   │   │   ├── ScenarioSimulator.tsx
│   │   │   └── OverrideModal.tsx
│   │   ├── performance/
│   │   │   ├── StylePerformanceTable.tsx
│   │   │   └── StorePerformanceTable.tsx
│   │   ├── ingestion/
│   │   │   ├── UploadDropzone.tsx
│   │   │   └── ErrorReport.tsx
│   │   └── shared/
│   │       ├── StatusBadge.tsx
│   │       ├── AlertBanner.tsx
│   │       └── PageHeader.tsx
│   │
│   ├── lib/
│   │   ├── api.ts                     # API client (wraps fetch + auth headers)
│   │   ├── hooks/                     # SWR hooks
│   │   └── utils.ts
│   │
│   ├── types/
│   │   └── index.ts                   # Shared TypeScript types
│   │
│   └── Dockerfile
│
├── docker-compose.yml                 # Local development
├── docker-compose.prod.yml
└── README.md
```

---

## 5. Database Schema

All tables include `created_at`, `updated_at` timestamps. Soft deletes via `is_active` flag where relevant.

### 5.1 Multi-tenancy
Every table that contains brand data includes a `brand_id` foreign key. All queries MUST filter by `brand_id` extracted from the JWT. This is enforced at the service layer, not just the router layer.

```sql
-- brands table
CREATE TABLE brands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 5.2 Users

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL,         -- ADMIN | PLANNER | VIEWER
    is_active BOOLEAN DEFAULT true,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_brand_id ON users(brand_id);
CREATE INDEX idx_users_email ON users(email);
```

### 5.3 Store Master

```sql
CREATE TABLE clusters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    name VARCHAR(100) NOT NULL,        -- "Metro", "Tier1", "South"
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, name)
);

CREATE TABLE stores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    store_code VARCHAR(50) NOT NULL,   -- Brand's own code e.g. "BLR-09"
    store_name VARCHAR(255) NOT NULL,
    city VARCHAR(100),
    state VARCHAR(100),
    cluster_id UUID REFERENCES clusters(id),
    store_grade VARCHAR(5) NOT NULL,   -- A | B | C | D
    store_type VARCHAR(50),            -- EBO | LFS | MBO
    climate_zone VARCHAR(50),          -- North | South | East | West | Central
    is_active BOOLEAN DEFAULT true,
    opening_date DATE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, store_code)
);

-- Display capacity per store per category
CREATE TABLE store_display_capacity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    store_id UUID NOT NULL REFERENCES stores(id),
    category VARCHAR(100) NOT NULL,    -- "Kurta", "Bottom", "Dress"
    max_styles INTEGER NOT NULL,       -- max styles displayable
    max_units INTEGER,                 -- max units (optional)
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(store_id, category)
);

CREATE INDEX idx_stores_brand_id ON stores(brand_id);
CREATE INDEX idx_stores_cluster_id ON stores(cluster_id);
```

### 5.4 SKU Master

```sql
CREATE TABLE skus (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    sku_code VARCHAR(100) NOT NULL,    -- Brand's own SKU code
    style_code VARCHAR(100) NOT NULL,  -- Parent style (multiple SKUs per style)
    style_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    sub_category VARCHAR(100),
    fabric VARCHAR(100),
    colour VARCHAR(100),
    colour_family VARCHAR(50),         -- Neutrals | Brights | Pastels | Darks
    price_band VARCHAR(50),            -- Budget | Mid | Premium
    mrp DECIMAL(10,2),
    cost_price DECIMAL(10,2),
    size VARCHAR(20),                  -- XS | S | M | L | XL | XXL | Free
    fit_type VARCHAR(50),
    sku_type VARCHAR(20) DEFAULT 'FASHION',  -- CORE | FASHION
    season_id UUID REFERENCES seasons(id),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, sku_code)
);

CREATE INDEX idx_skus_brand_id ON skus(brand_id);
CREATE INDEX idx_skus_style_code ON skus(brand_id, style_code);
CREATE INDEX idx_skus_category ON skus(brand_id, category);
```

### 5.5 Seasons

```sql
CREATE TABLE seasons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    name VARCHAR(100) NOT NULL,        -- "Summer 2025", "AW 2025"
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    categories TEXT[],                 -- categories in scope
    status VARCHAR(20) DEFAULT 'PLANNING',  -- PLANNING | ACTIVE | CLOSED
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Simple OTB input per season per category per month
CREATE TABLE season_otb (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id UUID NOT NULL REFERENCES seasons(id),
    brand_id UUID NOT NULL REFERENCES brands(id),
    category VARCHAR(100) NOT NULL,
    month DATE NOT NULL,               -- First day of month
    planned_sales DECIMAL(12,2) NOT NULL,
    planned_closing_stock DECIMAL(12,2) NOT NULL,
    opening_stock DECIMAL(12,2) NOT NULL,
    on_order DECIMAL(12,2) DEFAULT 0,
    -- Calculated field (also stored for performance)
    otb_value DECIMAL(12,2) GENERATED ALWAYS AS 
        (planned_sales + planned_closing_stock - opening_stock - on_order) STORED,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(season_id, category, month)
);
```

### 5.6 Ingestion Upload Tracking

```sql
CREATE TYPE upload_type AS ENUM ('SALES', 'INVENTORY', 'GRN', 'STORE_MASTER', 'SKU_MASTER');
CREATE TYPE upload_status AS ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'PARTIAL');

CREATE TABLE uploads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    uploaded_by UUID NOT NULL REFERENCES users(id),
    upload_type upload_type NOT NULL,
    filename VARCHAR(255) NOT NULL,
    s3_key VARCHAR(500) NOT NULL,
    status upload_status DEFAULT 'PENDING',
    total_rows INTEGER,
    successful_rows INTEGER DEFAULT 0,
    failed_rows INTEGER DEFAULT 0,
    error_summary JSONB,               -- { "row_errors": [{row: 42, error: "..."}] }
    processing_started_at TIMESTAMPTZ,
    processing_completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_uploads_brand_id ON uploads(brand_id);
```

### 5.7 Raw Sales Data

```sql
CREATE TABLE sales_data (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    upload_id UUID REFERENCES uploads(id),
    store_id UUID NOT NULL REFERENCES stores(id),
    sku_id UUID NOT NULL REFERENCES skus(id),
    week_start_date DATE NOT NULL,
    units_sold INTEGER NOT NULL DEFAULT 0,
    revenue DECIMAL(12,2),
    was_on_promotion BOOLEAN DEFAULT false,
    was_in_stock BOOLEAN DEFAULT true,  -- CRITICAL: false = stockout week
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, store_id, sku_id, week_start_date)
);

CREATE INDEX idx_sales_brand_store_sku ON sales_data(brand_id, store_id, sku_id);
CREATE INDEX idx_sales_week ON sales_data(brand_id, week_start_date);
CREATE INDEX idx_sales_sku ON sales_data(brand_id, sku_id);
```

### 5.8 GRN

```sql
CREATE TABLE grns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    grn_code VARCHAR(100) NOT NULL,
    grn_date DATE NOT NULL,
    warehouse_id VARCHAR(100),         -- warehouse identifier
    supplier_name VARCHAR(255),
    status VARCHAR(30) DEFAULT 'RECEIVED',  -- RECEIVED | ALLOCATED | DISPATCHED
    total_units INTEGER DEFAULT 0,
    total_skus INTEGER DEFAULT 0,
    season_id UUID REFERENCES seasons(id),
    upload_id UUID REFERENCES uploads(id),
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, grn_code)
);

CREATE TABLE grn_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grn_id UUID NOT NULL REFERENCES grns(id),
    brand_id UUID NOT NULL REFERENCES brands(id),
    sku_id UUID NOT NULL REFERENCES skus(id),
    units_received INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_grns_brand_id ON grns(brand_id);
CREATE INDEX idx_grn_lines_grn_id ON grn_lines(grn_id);
```

### 5.9 Inventory Truth Layer

```sql
-- This table is rebuilt nightly by the Celery job
-- It is the single source of truth for all inventory positions
CREATE TABLE inventory_state (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    snapshot_date DATE NOT NULL,
    location_id VARCHAR(100) NOT NULL, -- store_id or warehouse identifier
    location_type VARCHAR(20) NOT NULL, -- STORE | WAREHOUSE
    sku_id UUID NOT NULL REFERENCES skus(id),
    
    -- Raw position
    units_on_hand INTEGER NOT NULL DEFAULT 0,
    units_in_transit INTEGER DEFAULT 0,  -- allocated but not received
    
    -- Velocity metrics (calculated from sales_data)
    units_sold_7d INTEGER DEFAULT 0,
    units_sold_28d INTEGER DEFAULT 0,
    ros_7d DECIMAL(8,2),               -- units per day, last 7 days
    ros_28d DECIMAL(8,2),              -- units per day, last 28 days
    
    -- Health metrics
    stock_cover_days DECIMAL(8,1),     -- units_on_hand / ros_7d
    days_since_grn INTEGER,            -- age of stock
    days_since_first_sale INTEGER,
    sell_through_pct DECIMAL(5,2),     -- % of received stock that has sold
    
    -- Flags
    is_stockout BOOLEAN DEFAULT false,
    is_new_arrival BOOLEAN DEFAULT false,  -- first 14 days
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(brand_id, snapshot_date, location_id, location_type, sku_id)
);

-- Partial index for active positions only
CREATE INDEX idx_inv_state_latest ON inventory_state(brand_id, snapshot_date DESC);
CREATE INDEX idx_inv_state_location ON inventory_state(brand_id, location_id, snapshot_date);
CREATE INDEX idx_inv_state_sku ON inventory_state(brand_id, sku_id, snapshot_date);
```

### 5.10 Allocation

```sql
CREATE TYPE allocation_status AS ENUM (
    'DRAFT',           -- generated, not reviewed
    'UNDER_REVIEW',    -- planner is reviewing
    'APPROVED',        -- planner approved
    'DISPATCHED',      -- warehouse has executed
    'CANCELLED'
);

CREATE TABLE allocation_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    grn_id UUID NOT NULL REFERENCES grns(id),
    season_id UUID REFERENCES seasons(id),
    status allocation_status DEFAULT 'DRAFT',
    
    -- Engine metadata
    engine_version VARCHAR(20) DEFAULT '1.0',
    generated_at TIMESTAMPTZ,
    generated_by_user UUID REFERENCES users(id),  -- null if auto-generated
    
    -- Summary
    total_stores INTEGER DEFAULT 0,
    total_skus INTEGER DEFAULT 0,
    total_units_recommended INTEGER DEFAULT 0,
    total_units_approved INTEGER DEFAULT 0,
    
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- One row per store per SKU per allocation session
CREATE TABLE allocation_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES allocation_sessions(id),
    brand_id UUID NOT NULL REFERENCES brands(id),
    store_id UUID NOT NULL REFERENCES stores(id),
    sku_id UUID NOT NULL REFERENCES skus(id),
    
    -- What AI recommended
    ai_recommended_qty INTEGER NOT NULL DEFAULT 0,
    ai_confidence VARCHAR(10),         -- HIGH | MEDIUM | LOW
    ai_reasoning JSONB NOT NULL,       -- structured reasoning (see below)
    ai_projections JSONB,              -- sell-through projections at different qtys
    
    -- What planner decided
    final_qty INTEGER,                 -- null until planner approves
    was_overridden BOOLEAN DEFAULT false,
    override_reason VARCHAR(100),      -- dropdown: VENDOR_CONSTRAINT | STORE_REQUEST |
                                       --          LOCAL_EVENT | GUT_FEEL | OTHER
    override_notes TEXT,
    
    -- Outcome tracking (filled in later by snapshot job)
    actual_sellthrough_4w DECIMAL(5,2),
    actual_sellthrough_8w DECIMAL(5,2),
    actual_sellthrough_eow DECIMAL(5,2),  -- end of season sell-through
    ai_was_better BOOLEAN,             -- did AI rec outperform override?
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(session_id, store_id, sku_id)
);

CREATE INDEX idx_alloc_lines_session ON allocation_lines(session_id);
CREATE INDEX idx_alloc_lines_store ON allocation_lines(brand_id, store_id);
CREATE INDEX idx_alloc_lines_sku ON allocation_lines(brand_id, sku_id);
```

**ai_reasoning JSONB structure:**
```json
{
  "store_grade": "A",
  "store_ros_attribute": 2.8,
  "cluster_avg_ros_attribute": 2.1,
  "ros_vs_cluster_pct": 33,
  "current_stock_cover_days": 9.8,
  "display_capacity_available": 6,
  "season_weeks_remaining": 8,
  "weeks_cover_at_recommended": 6.4,
  "stockout_risk_at_lower_qty": true,
  "climate_match": true,
  "confidence_basis": "Based on 847 comparable store-weeks of data"
}
```

### 5.11 Performance Snapshots

```sql
CREATE TABLE performance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    snapshot_date DATE NOT NULL,
    season_id UUID REFERENCES seasons(id),
    store_id UUID NOT NULL REFERENCES stores(id),
    sku_id UUID NOT NULL REFERENCES skus(id),
    
    -- Core metrics
    units_sold_today INTEGER DEFAULT 0,
    units_sold_7d INTEGER DEFAULT 0,
    units_sold_28d INTEGER DEFAULT 0,
    units_on_hand INTEGER DEFAULT 0,
    sell_through_pct DECIMAL(5,2),
    ros_7d DECIMAL(8,2),
    stock_cover_days DECIMAL(8,1),
    days_since_grn INTEGER,
    
    -- Status classification
    -- HEALTHY | WATCH | PROBLEM | CRITICAL
    style_status VARCHAR(20),
    
    -- Lost sales tracking (for future ML)
    is_stockout BOOLEAN DEFAULT false,
    lost_sales_estimate DECIMAL(8,2),  -- units, estimated
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(brand_id, snapshot_date, store_id, sku_id)
);

CREATE INDEX idx_perf_snap_brand_date ON performance_snapshots(brand_id, snapshot_date DESC);
CREATE INDEX idx_perf_snap_sku ON performance_snapshots(brand_id, sku_id, snapshot_date);
```

### 5.12 Alerts

```sql
CREATE TYPE alert_type AS ENUM (
    'STOCKOUT_RISK',
    'AGING_STOCK',
    'WAREHOUSE_STOCK_SITTING',
    'HIGH_COVER',
    'GRN_UNALLOCATED'
);

CREATE TABLE alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id UUID NOT NULL REFERENCES brands(id),
    alert_type alert_type NOT NULL,
    severity VARCHAR(10) NOT NULL,     -- HIGH | MEDIUM | LOW
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    
    -- Linked entities
    store_id UUID REFERENCES stores(id),
    sku_id UUID REFERENCES skus(id),
    grn_id UUID REFERENCES grns(id),
    season_id UUID REFERENCES seasons(id),
    
    -- Action link
    action_url VARCHAR(500),           -- where to go to act on this alert
    
    is_read BOOLEAN DEFAULT false,
    is_dismissed BOOLEAN DEFAULT false,
    
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_alerts_brand_active ON alerts(brand_id, is_dismissed, generated_at DESC);
```

---

## 6. Module 1: Data Ingestion

### 6.1 Overview

Every upload follows this flow:
```
CSV Upload → S3 → Upload Record Created → Celery Task Triggered →
Schema Validation → Reference Validation → Business Logic Validation →
Partial Write (valid rows only) → Error Report Generated → Status Updated
```

### 6.2 Upload Flow

**POST /api/v1/ingestion/upload**

1. Receive multipart file
2. Store raw CSV to S3 at key: `{brand_id}/uploads/{upload_type}/{uuid}/{filename}`
3. Create `uploads` record with status `PENDING`
4. Trigger Celery task `process_upload.delay(upload_id)`
5. Return `upload_id` immediately (async processing)

**GET /api/v1/ingestion/uploads/{upload_id}/status**
- Polls for processing status
- Returns: status, progress, row counts, error summary

### 6.3 Validation Layers

#### Layer 1: Schema Validation
```python
# For every upload type, define required and optional columns
SALES_SCHEMA = {
    "required": ["store_code", "sku_code", "week_start_date", "units_sold"],
    "optional": ["revenue", "was_on_promotion", "was_in_stock"],
    "types": {
        "week_start_date": "date",  # Accepts: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY
        "units_sold": "integer",
        "revenue": "decimal",
        "was_on_promotion": "boolean",  # Accepts: true/false, 1/0, yes/no
        "was_in_stock": "boolean"
    }
}
```

If schema fails: reject entire file. Return specific errors.

#### Layer 2: Reference Validation
For sales upload, every `store_code` must exist in the brand's stores table.
For sales upload, every `sku_code` must exist in the brand's skus table.
Collect all failures — do not stop at first error.

```python
# Batch lookup: resolve codes to IDs in one query
store_code_map = {s.store_code: s.id for s in brand_stores}
sku_code_map = {s.sku_code: s.id for s in brand_skus}

for row in rows:
    if row.store_code not in store_code_map:
        errors.append(RowError(row_num=row.num, 
                               field="store_code",
                               value=row.store_code,
                               message=f"Store '{row.store_code}' not found"))
```

#### Layer 3: Business Logic Validation
- `units_sold` cannot be negative
- `week_start_date` cannot be in the future
- `mrp` cannot be zero or negative
- `units_received` in GRN cannot be zero

#### Partial Upload Handling
Valid rows → write to DB.
Invalid rows → log to `uploads.error_summary`.
Update `uploads` with counts and status `PARTIAL` or `COMPLETED`.

#### Error Report
Generate a downloadable CSV of failed rows with:
- Original row data
- Row number
- Field that failed
- Error message
- Suggested fix (where deterministic)

### 6.4 Upload Types

| Upload Type | Target Table | Key Validations |
|---|---|---|
| `STORE_MASTER` | `stores` | No duplicate store_code per brand |
| `SKU_MASTER` | `skus` | No duplicate sku_code per brand, valid category values |
| `SALES` | `sales_data` | Store and SKU must exist, date not in future, no negative units |
| `INVENTORY` | Raw → inventory_state | Location must exist, units cannot be negative |
| `GRN` | `grns` + `grn_lines` | SKU must exist, units > 0 |

### 6.5 Normaliser
Before validation, run normalisation:
```python
# Normalise common messiness
def normalise_row(row, upload_type):
    # Strip whitespace from all string fields
    # Uppercase store codes and SKU codes
    # Parse dates flexibly (DD/MM/YYYY, YYYY-MM-DD, DD-MM-YYYY)
    # Convert "Yes"/"No"/"1"/"0" to boolean
    # Strip currency symbols from numeric fields
    # Replace empty strings with None
    return normalised_row
```

---

## 7. Module 2: Inventory Truth Engine

### 7.1 Purpose
A single, clean, reconciled daily snapshot of every SKU's position at every location. Every other module reads from this. Never from raw tables directly.

### 7.2 Nightly Job (1:00 AM)

```python
# tasks/inventory_snapshot.py
@celery_app.task
def build_inventory_snapshots(brand_id: str, snapshot_date: str):
    """
    For every brand, for every active store + warehouse,
    for every SKU that has had any activity in the last 90 days:
    
    1. Get current units_on_hand from latest inventory upload
    2. Calculate units_sold_7d and units_sold_28d from sales_data
    3. Calculate ROS (units per day)
    4. Calculate stock_cover_days = units_on_hand / ros_7d
    5. Calculate days_since_grn (find most recent GRN for this SKU at this location)
    6. Calculate sell_through_pct = total_sold / (total_sold + units_on_hand)
    7. Set is_stockout = (units_on_hand == 0)
    8. Upsert into inventory_state
    """
```

### 7.3 ROS Calculation Rules
```python
def calculate_ros(units_sold_7d: int, units_sold_28d: int, 
                  days_in_stock_7d: int, days_in_stock_28d: int) -> dict:
    """
    Use 7-day ROS for recent trend.
    Use 28-day ROS for stability.
    
    IMPORTANT: Only count days when stock was actually available.
    If stockout for 3 of 7 days → divide by 4 (days in stock), not 7.
    This is the foundation of lost sales correction later.
    
    Returns:
        ros_7d: units per day (trailing 7 days, stock-adjusted)
        ros_28d: units per day (trailing 28 days, stock-adjusted)
    """
    ros_7d = units_sold_7d / max(days_in_stock_7d, 1)
    ros_28d = units_sold_28d / max(days_in_stock_28d, 1)
    return {"ros_7d": round(ros_7d, 3), "ros_28d": round(ros_28d, 3)}
```

### 7.4 Stock Cover Edge Cases
```python
# If ROS is zero (new arrival, no sales yet)
# → stock_cover_days = NULL (cannot divide by zero)
# Do not show "infinite" cover — show "No sales yet"

# If stockout (units_on_hand = 0)
# → stock_cover_days = 0
# → is_stockout = true

# If ROS < 0.01 (extremely slow mover)
# → stock_cover_days = units_on_hand / 0.01 (cap to avoid huge numbers)
# → Flag as LOW_VELOCITY
```

---

## 8. Module 3: Season and Setup

### 8.1 Season
Simple CRUD. No workflow enforcement in v1.

Fields:
- `name` (e.g. "Summer 2025")
- `start_date`, `end_date`
- `categories` (multi-select from brand's category list)
- `status`: PLANNING → ACTIVE → CLOSED (manually updated by admin)

### 8.2 OTB Input
One form per season. Planner fills in:
- Category (dropdown)
- Month (date picker, first of month)
- Planned Sales (₹)
- Planned Closing Stock (₹)
- Opening Stock (₹) — auto-filled from inventory state if available
- On Order (₹) — manual

System calculates and displays:
```
OTB = Planned Sales + Planned Closing Stock − Opening Stock − On Order
```

Colour coding:
- Green: OTB > 0 (buying room available)
- Amber: OTB between 0 and -10% of planned sales (near limit)
- Red: OTB < 0 (over-bought)

### 8.3 Clusters
Simple CRUD. Name, description, assign stores to cluster.

### 8.4 Store Display Capacity
Per store, per category: max styles and max units displayable. Used as hard constraint in allocation engine.

---

## 9. Module 4: Allocation Engine

### 9.1 Trigger
User navigates to a GRN detail page and clicks **"Generate Allocation."**

The engine runs synchronously for small GRNs (<500 SKU-store combinations) and via Celery for larger ones. Target response time: <30 seconds for any GRN.

### 9.2 Engine Pipeline

```python
# services/allocation/engine.py

class AllocationEngine:
    def generate(self, grn_id: str, brand_id: str) -> AllocationSession:
        
        # Step 1: Load GRN lines
        grn_lines = self.load_grn(grn_id)
        
        # Step 2: Load active stores for this brand
        stores = self.load_active_stores(brand_id)
        
        # Step 3: Load today's inventory state
        inventory = self.load_inventory_state(brand_id, date.today())
        
        # Step 4: Load trailing ROS by store by attribute
        # Attribute = category + fabric + price_band combination
        ros_by_store_attribute = self.load_ros_by_attribute(brand_id)
        
        # Step 5: Load size curves by cluster by category
        size_curves = self.load_size_curves(brand_id)
        
        # Step 6: For each GRN line (each SKU)
        allocation_lines = []
        for grn_line in grn_lines:
            sku = grn_line.sku
            available_units = grn_line.units_received
            
            # Step 6a: Score every store
            store_scores = self.score_stores(
                sku=sku,
                stores=stores,
                inventory=inventory,
                ros_by_store_attribute=ros_by_store_attribute
            )
            
            # Step 6b: Filter ineligible stores
            eligible_stores = self.filter_eligible(store_scores, sku)
            
            # Step 6c: Distribute units proportionally to scores
            raw_allocation = self.distribute_units(
                eligible_stores=eligible_stores,
                available_units=available_units
            )
            
            # Step 6d: Apply size curves
            sized_allocation = self.apply_size_curves(
                raw_allocation=raw_allocation,
                sku=sku,
                size_curves=size_curves
            )
            
            # Step 6e: Apply hard constraints
            constrained_allocation = self.apply_constraints(
                allocation=sized_allocation,
                inventory=inventory,
                sku=sku
            )
            
            # Step 6f: Generate explainability for each line
            for store_id, qty in constrained_allocation.items():
                reasoning = self.generate_reasoning(
                    store_id=store_id,
                    sku=sku,
                    qty=qty,
                    store_scores=store_scores,
                    inventory=inventory,
                    ros_by_store_attribute=ros_by_store_attribute
                )
                allocation_lines.append(AllocationLine(
                    store_id=store_id,
                    sku_id=sku.id,
                    ai_recommended_qty=qty,
                    ai_reasoning=reasoning,
                    ai_confidence=self.calculate_confidence(store_id, sku, ros_by_store_attribute)
                ))
        
        return self.save_session(grn_id, brand_id, allocation_lines)
```

### 9.3 Store Scoring

```python
def score_stores(self, sku, stores, inventory, ros_by_store_attribute):
    scores = {}
    attribute_key = f"{sku.category}_{sku.fabric}_{sku.price_band}"
    
    for store in stores:
        # Get this store's trailing ROS for this attribute
        store_ros = ros_by_store_attribute.get(
            (store.id, attribute_key), 
            default=self.get_cluster_avg_ros(store.cluster_id, attribute_key)
        )
        
        # Grade score: A=4, B=3, C=2, D=1
        grade_score = {"A": 4, "B": 3, "C": 2, "D": 1}.get(store.store_grade, 1)
        
        # Current cover (lower = more urgent)
        # Cover of existing similar styles at this store
        current_cover = self.get_attribute_cover(store.id, attribute_key, inventory)
        
        # Composite score
        # Weights are configurable per brand — start with these defaults
        score = (
            (0.50 * store_ros) +           # ROS is most important
            (0.25 * grade_score) +         # Grade is second
            (0.25 * (1 / max(current_cover, 0.1)))  # Low cover = higher score
        )
        
        scores[store.id] = {
            "score": score,
            "store_ros": store_ros,
            "grade_score": grade_score,
            "current_cover": current_cover
        }
    
    return scores
```

### 9.4 Eligibility Filter

```python
def filter_eligible(self, store_scores, sku):
    """Remove stores that should not receive this SKU at all."""
    eligible = {}
    
    for store_id, score_data in store_scores.items():
        store = self.get_store(store_id)
        
        # Check climate zone match
        if not self.climate_match(store.climate_zone, sku):
            continue  # e.g. heavy wool to South India in summer
        
        # Check display capacity
        remaining_capacity = self.get_remaining_display_capacity(
            store_id, sku.category
        )
        if remaining_capacity <= 0:
            continue  # Store is at display capacity for this category
        
        # Store carries this category this season
        if not self.store_carries_category(store_id, sku.category):
            continue
        
        eligible[store_id] = score_data
    
    return eligible
```

### 9.5 Unit Distribution

```python
def distribute_units(self, eligible_stores, available_units):
    """
    Distribute available_units proportionally to scores.
    Apply minimum allocation floor (below which sending is not worth it).
    """
    MINIMUM_ALLOCATION = 6  # configurable per brand
    
    total_score = sum(s["score"] for s in eligible_stores.values())
    
    raw_distribution = {}
    for store_id, score_data in eligible_stores.items():
        proportion = score_data["score"] / total_score
        raw_qty = round(available_units * proportion)
        raw_distribution[store_id] = raw_qty
    
    # Remove stores below minimum (redistribute their units to top scorers)
    final = {}
    below_min = []
    
    for store_id, qty in raw_distribution.items():
        if qty >= MINIMUM_ALLOCATION:
            final[store_id] = qty
        else:
            below_min.append(store_id)
    
    # Redistribute units from below-min stores
    if below_min:
        redistributable = sum(raw_distribution[s] for s in below_min)
        # Add to top store by score
        top_store = max(final.keys(), key=lambda s: eligible_stores[s]["score"])
        final[top_store] = final[top_store] + redistributable
    
    return final
```

### 9.6 Hard Constraints

```python
def apply_constraints(self, allocation, inventory, sku):
    """
    These constraints CANNOT be overridden by the engine.
    They can only be changed by a planner manually.
    """
    constrained = {}
    total_allocated = 0
    
    # Sort by score (allocate to best stores first when supply is scarce)
    sorted_stores = sorted(allocation.items(), 
                          key=lambda x: ..., reverse=True)
    
    for store_id, qty in sorted_stores:
        # Constraint 1: Cannot exceed display capacity remaining
        remaining_capacity = self.get_remaining_display_capacity(
            store_id, sku.category
        )
        qty = min(qty, remaining_capacity)
        
        # Constraint 2: Cannot exceed total available inventory
        remaining_available = grn_line.units_received - total_allocated
        qty = min(qty, remaining_available)
        
        if qty > 0:
            constrained[store_id] = qty
            total_allocated += qty
        
        if total_allocated >= grn_line.units_received:
            break  # No more units to allocate
    
    return constrained
```

### 9.7 Confidence Scoring

```python
def calculate_confidence(self, store_id, sku, ros_data):
    """
    HIGH: >= 20 comparable store-weeks of data
    MEDIUM: 5-19 comparable store-weeks
    LOW: < 5 comparable store-weeks (new store, new category, new cluster)
    """
    attribute_key = f"{sku.category}_{sku.fabric}_{sku.price_band}"
    data_points = ros_data.get_sample_size(store_id, attribute_key)
    
    if data_points >= 20:
        return "HIGH"
    elif data_points >= 5:
        return "MEDIUM"
    else:
        return "LOW"
```

### 9.8 Explainability Generator

Every recommendation produces a structured reasoning object stored in `allocation_lines.ai_reasoning` (JSONB). The frontend renders this in a human-readable panel.

```python
def generate_reasoning(self, store_id, sku, qty, store_scores, inventory, ros_data):
    store = self.get_store(store_id)
    attribute_key = f"{sku.category}_{sku.fabric}_{sku.price_band}"
    cluster_avg = ros_data.get_cluster_avg(store.cluster_id, attribute_key)
    store_ros = store_scores[store_id]["store_ros"]
    current_cover = store_scores[store_id]["current_cover"]
    capacity_available = self.get_remaining_display_capacity(store_id, sku.category)
    season_weeks_remaining = self.get_weeks_remaining()
    weeks_cover = qty / max(store_ros, 0.01) / 7  # convert daily ROS to weeks
    
    return {
        "store_grade": store.store_grade,
        "store_ros_attribute": round(store_ros, 2),
        "cluster_avg_ros_attribute": round(cluster_avg, 2),
        "ros_vs_cluster_pct": round(((store_ros - cluster_avg) / max(cluster_avg, 0.01)) * 100),
        "current_stock_cover_days": round(current_cover, 1),
        "display_capacity_available": capacity_available,
        "season_weeks_remaining": season_weeks_remaining,
        "weeks_cover_at_recommended": round(weeks_cover, 1),
        "weeks_cover_at_minus_25pct": round((qty * 0.75) / max(store_ros, 0.01) / 7, 1),
        "weeks_cover_at_plus_25pct": round((qty * 1.25) / max(store_ros, 0.01) / 7, 1),
        "stockout_risk_at_lower_qty": (qty * 0.75) / max(store_ros, 0.01) / 7 < season_weeks_remaining * 0.7,
        "climate_match": self.climate_match(store.climate_zone, sku),
        "data_sample_size": ros_data.get_sample_size(store_id, attribute_key),
        "confidence_basis": f"Based on {ros_data.get_sample_size(store_id, attribute_key)} comparable store-weeks"
    }
```

### 9.9 Scenario Simulation

The frontend calls this endpoint whenever the planner adjusts a quantity:

**POST /api/v1/allocation/simulate**
```json
{
  "store_id": "uuid",
  "sku_id": "uuid",
  "quantity": 24
}
```

Response:
```json
{
  "quantity": 24,
  "weeks_cover": 8.6,
  "fills_display_capacity": true,
  "remaining_capacity_after": 0,
  "projected_sellthrough_eow": 0.94,
  "stockout_risk": false,
  "overstock_risk": false,
  "notes": "Fills display capacity. No room for follow-up allocation."
}
```

This is simple arithmetic on inventory_state data. No ML. Runs in <100ms.

### 9.10 Override Tracking

When a planner changes a recommended quantity, the frontend sends:
```json
{
  "allocation_line_id": "uuid",
  "final_qty": 20,
  "override_reason": "STORE_REQUEST",
  "override_notes": "Store manager requested extra stock for upcoming event"
}
```

Stored in `allocation_lines`. This dataset becomes the AI training data in v2.

### 9.11 Approval and Export

On approval:
1. `allocation_sessions.status` → `APPROVED`
2. `allocation_sessions.approved_by` → current user
3. Generate transfer list CSV:

```csv
GRN,SKU Code,Style Name,Size,Store Code,Store Name,Quantity,Status
GRN-2025-047,KRT-COT-NVY-M,Cotton Kurta Navy,M,BLR-09,HSR Layout,18,PENDING
GRN-2025-047,KRT-COT-NVY-L,Cotton Kurta Navy,L,BLR-09,HSR Layout,22,PENDING
...
```

This CSV goes to the warehouse team. No WMS integration in v1.

---

## 10. Module 5: Performance Dashboard

### 10.1 Data Source
Everything reads from `performance_snapshots` (latest date) joined with `inventory_state`. Never from raw sales tables.

### 10.2 Style Performance View

**GET /api/v1/performance/styles**

Query params: `season_id`, `category`, `store_id`, `cluster_id`, `status`, `min_age_days`

Returns per SKU per store (or rolled up to brand level):

```json
{
  "sku_id": "uuid",
  "style_code": "KRT-COT-NVY",
  "style_name": "Cotton Kurta Navy",
  "category": "Kurta",
  "ros_7d": 2.8,
  "sell_through_pct": 0.67,
  "stock_cover_days": 9.8,
  "units_on_hand": 145,
  "days_since_grn": 18,
  "style_status": "HEALTHY",
  "stores_exposed": 42,
  "stores_stockout": 3
}
```

**Status Classification Logic:**
```python
def classify_style_status(snap: PerformanceSnapshot, season: Season) -> str:
    pct_season_elapsed = (date.today() - season.start_date).days / (season.end_date - season.start_date).days
    
    # CRITICAL: very old stock with low sell-through
    if snap.days_since_grn > 60 and snap.sell_through_pct < 0.20:
        return "CRITICAL"
    
    # PROBLEM: behind pace for sell-through
    if snap.sell_through_pct < (pct_season_elapsed * 0.6):  # 40% behind pace
        return "PROBLEM"
    
    # WATCH: slightly behind or high cover
    if snap.stock_cover_days > 42 or snap.sell_through_pct < (pct_season_elapsed * 0.8):
        return "WATCH"
    
    return "HEALTHY"
```

### 10.3 Store Performance View

**GET /api/v1/performance/stores**

Returns per store:
```json
{
  "store_id": "uuid",
  "store_name": "HSR Layout",
  "store_grade": "A",
  "avg_sell_through_pct": 0.71,
  "avg_ros": 2.4,
  "avg_stock_cover_days": 14.7,
  "styles_exposed": 48,
  "styles_healthy": 39,
  "styles_watch": 6,
  "styles_problem": 2,
  "styles_critical": 1,
  "styles_stockout": 3
}
```

### 10.4 Filters
Both views must support:
- Filter by season
- Filter by category
- Filter by cluster
- Filter by status (HEALTHY/WATCH/PROBLEM/CRITICAL)
- Filter by store grade
- Sort by any column
- Export to CSV

---

## 11. Module 6: Alerts

### 11.1 Alert Generation Job (6:00 AM daily)

Three alert types in v1:

**Alert Type 1: STOCKOUT_RISK**
```python
# Find SKUs at stores where:
# - units_on_hand > 0 (not yet stocked out)
# - stock_cover_days < 7 (will run out within 7 days)
# - was_selling actively (ros_7d > 0.1)
```

**Alert Type 2: AGING_STOCK**
```python
# Find SKUs at stores where:
# - days_since_grn > 45
# - sell_through_pct < 0.25
# These need markdown or transfer attention
```

**Alert Type 3: WAREHOUSE_STOCK_SITTING**
```python
# Find GRN lines where:
# - grn.created_at > 14 days ago
# - no allocation_session exists for this GRN
# Stock arrived but was never allocated
```

### 11.2 Alert Display
Alerts appear on the main dashboard.
Each alert includes a direct link to the relevant screen (GRN, style, store).
Planners can dismiss alerts (stores them as dismissed, not deleted).
Alert count shown in nav badge.

---

## 12. API Endpoints

All endpoints: `Authorization: Bearer {jwt_token}` required.
All responses include: `{ data: ..., meta: { request_id, timestamp } }`
All errors: `{ error: { code, message, details } }`

### Auth
```
POST   /api/v1/auth/login              # Email + password → JWT
POST   /api/v1/auth/refresh            # Refresh token → new JWT
POST   /api/v1/auth/logout
GET    /api/v1/auth/me                 # Current user info
```

### Setup
```
GET    /api/v1/stores                  # List stores (filterable)
POST   /api/v1/stores                  # Create store
PUT    /api/v1/stores/{id}             # Update store
POST   /api/v1/stores/bulk             # Bulk create from CSV

GET    /api/v1/clusters                # List clusters
POST   /api/v1/clusters                # Create cluster
PUT    /api/v1/clusters/{id}           # Update cluster

GET    /api/v1/skus                    # List SKUs (filterable)
POST   /api/v1/skus                    # Create SKU
PUT    /api/v1/skus/{id}              # Update SKU

GET    /api/v1/seasons                 # List seasons
POST   /api/v1/seasons                 # Create season
PUT    /api/v1/seasons/{id}            # Update season
GET    /api/v1/seasons/{id}/otb        # Get OTB for season
POST   /api/v1/seasons/{id}/otb        # Save OTB inputs
```

### Ingestion
```
POST   /api/v1/ingestion/upload        # Upload CSV file
GET    /api/v1/ingestion/uploads       # List uploads
GET    /api/v1/ingestion/uploads/{id}  # Upload status
GET    /api/v1/ingestion/uploads/{id}/errors  # Download error report CSV
```

### GRN
```
GET    /api/v1/grns                    # List GRNs
GET    /api/v1/grns/{id}              # GRN detail with lines
POST   /api/v1/grns                    # Create GRN manually (if not via upload)
```

### Allocation
```
POST   /api/v1/allocation/generate     # { grn_id } → starts allocation engine
GET    /api/v1/allocation/sessions/{id}       # Get allocation session + lines
PUT    /api/v1/allocation/lines/{id}          # Update a single line (override)
POST   /api/v1/allocation/sessions/{id}/approve  # Approve full session
POST   /api/v1/allocation/simulate     # { store_id, sku_id, quantity } → projections
GET    /api/v1/allocation/sessions/{id}/export   # Download transfer list CSV
```

### Performance
```
GET    /api/v1/performance/styles      # Style performance (filterable, sortable)
GET    /api/v1/performance/stores      # Store performance (filterable, sortable)
GET    /api/v1/performance/styles/export     # CSV export
GET    /api/v1/performance/stores/export     # CSV export
```

### Alerts
```
GET    /api/v1/alerts                  # List active alerts
PUT    /api/v1/alerts/{id}/read        # Mark as read
PUT    /api/v1/alerts/{id}/dismiss     # Dismiss alert
GET    /api/v1/alerts/count            # Unread count (for nav badge)
```

---

## 13. Background Jobs

All Celery tasks. Scheduled via Celery Beat.

| Job | Schedule | What It Does |
|---|---|---|
| `build_inventory_snapshots` | 1:00 AM daily | Rebuilds inventory_state for all brands |
| `build_performance_snapshots` | 2:00 AM daily | Calculates ROS, ST%, cover, status for all active SKUs |
| `generate_alerts` | 6:00 AM daily | Runs alert detection rules, creates new alerts |
| `update_allocation_outcomes` | 3:00 AM weekly | Backfills actual_sellthrough on old allocation_lines |
| `process_upload` | Triggered on upload | Validates and ingests uploaded CSV |

### Job Failure Handling
Every job:
- Logs start and end with duration
- On failure: logs error, sends alert to admin user, does NOT retry indefinitely
- Idempotent: safe to run twice (upserts, not inserts)

---

## 14. Frontend Screens

### Screen 1: Dashboard (Home)
**Path:** `/dashboard`

Components:
- Alert banner: count of active alerts by severity, links to alert list
- Recent GRNs widget: last 5 GRNs with status (RECEIVED/ALLOCATED/DISPATCHED)
- Quick stats: active season sell-through %, styles at risk count, stores below target
- "Pending allocations" CTA if any GRN is RECEIVED but not ALLOCATED

### Screen 2: GRN List
**Path:** `/grn`

Table columns: GRN Code, Date, Supplier, Total Units, Total SKUs, Status, Action

Action button logic:
- Status = RECEIVED → "Generate Allocation" (primary CTA)
- Status = ALLOCATED (draft) → "Review Allocation"
- Status = APPROVED → "View Allocation" + "Download Transfer List"
- Status = DISPATCHED → "View"

### Screen 3: Allocation Screen
**Path:** `/grn/{id}`

This is the most important screen in the product. Every design decision should optimise for the allocator's efficiency.

Layout:
```
┌─────────────────────────────────────────────────────────────┐
│ GRN #247 — Cotton Kurtas — 340 units — 12 SKUs             │
│ Generated: 2 minutes ago  ○ DRAFT                          │
│                                    [Approve All] [Export]   │
├─────────────────────────────────────────────────────────────┤
│ SKU Selector (tabs or dropdown):                            │
│ KRT-COT-NVY-M  KRT-COT-NVY-L  KRT-COT-RED-M ...           │
├───────────────────────────┬─────────────────────────────────┤
│                           │                                 │
│  ALLOCATION TABLE         │   EXPLAINABILITY PANEL          │
│                           │                                 │
│  Store | Rec | Final | Sel │  (shows when row is selected)  │
│  ─────────────────────    │                                 │
│  HSR   |  18 |  [18] | □  │  Store: HSR Layout (Grade A)   │
│  Korm  |  14 |  [14] | □  │  Attribute ROS: 2.8/day        │
│  MG Rd |  12 |  [12] | □  │  Cluster avg: 2.1/day (+33%)  │
│  ...                      │  Current cover: 1.4 weeks      │
│                           │  Capacity available: 6 styles  │
│  [Scenario: 18 ▲▼]       │                                 │
│  Cover: 6.4 weeks OK      │  Confidence: HIGH (847 obs)    │
│  Sellthrough: ~82%        │                                 │
└───────────────────────────┴─────────────────────────────────┘
```

**Interaction design:**
- Clicking any row highlights it and shows explainability in the right panel
- Final quantity is an inline editable number input
- Changing final quantity triggers scenario simulation call (debounced 300ms)
- Scenario simulation result shows below the input: cover days, projected ST%
- Override reason dropdown appears when final_qty ≠ ai_recommended_qty
- "Approve All" approves all lines at their current final_qty values
- Individual row approval checkboxes for partial approval

### Screen 4: Performance — Styles
**Path:** `/performance/styles`

Full-width table with:
- Filter bar: Season, Category, Store/Cluster, Status, Min Age
- Columns: Style, Category, ROS, Sell-Through %, Cover (days), Age (days), Status badge
- Status badge colours: Green=HEALTHY, Amber=WATCH, Orange=PROBLEM, Red=CRITICAL
- Sort on any column
- CSV export button
- Click row → drawer showing store-level breakdown for that style

### Screen 5: Performance — Stores
**Path:** `/performance/stores`

Table with:
- Filter bar: Cluster, Grade, Season
- Columns: Store, Grade, Sell-Through %, Avg ROS, Cover, Styles (total/healthy/watch/problem/critical)
- Click row → drawer showing style-level breakdown for that store

### Screen 6: Upload Hub
**Path:** `/ingestion`

Tabs: Sales | Inventory | GRN | Store Master | SKU Master

Each tab:
- Upload instructions (expected columns, format, example file download)
- Drag-and-drop upload zone
- Upload history table for that type
- Status column: PENDING / PROCESSING / COMPLETED / PARTIAL / FAILED
- Download error report button (visible when PARTIAL or FAILED)

### Screen 7: Setup Pages
Simple CRUD for: Stores, Clusters, SKUs, Seasons, OTB inputs.
Table + form pattern. Bulk upload option on each.

---

## 15. Auth and RBAC

### JWT Structure
```json
{
  "sub": "user_id",
  "brand_id": "brand_uuid",
  "role": "PLANNER",
  "exp": 1234567890
}
```

All queries automatically filter by `brand_id` from JWT. This is NOT optional.

### Roles

| Role | What They Can Do |
|---|---|
| `ADMIN` | Everything including user management and brand settings |
| `PLANNER` | All allocation and performance screens. Cannot manage users. |
| `VIEWER` | Read-only access to performance dashboards. Cannot approve allocations. |

### Token Expiry
- Access token: 8 hours
- Refresh token: 30 days
- On expiry: frontend redirects to login

---

## 16. Error Handling Standards

### API Error Response Format
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Upload failed validation",
    "details": [
      {
        "row": 42,
        "field": "store_code",
        "value": "BLR-999",
        "message": "Store code 'BLR-999' not found in your store master"
      }
    ]
  },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2025-01-15T09:30:00Z"
  }
}
```

### Error Codes
```
AUTH_REQUIRED          — No token provided
AUTH_EXPIRED           — Token expired
AUTH_INVALID           — Token invalid
FORBIDDEN              — Insufficient role
NOT_FOUND              — Resource not found
VALIDATION_ERROR       — Request data invalid
UPLOAD_SCHEMA_ERROR    — CSV missing required columns
UPLOAD_REFERENCE_ERROR — CSV contains unknown codes
ALLOCATION_IN_PROGRESS — Allocation already being generated for this GRN
INSUFFICIENT_INVENTORY — Not enough units in warehouse for allocation
```

### Frontend Error Handling
- API errors → toast notification with specific message
- Upload errors → persistent error banner + download error report link
- Allocation generation failure → inline error with retry button
- Network errors → "Connection lost" banner with auto-retry

---

## 17. 16-Week Engineering Plan

### Weeks 1–4: Data Ingestion

**Backend:**
- [ ] Project setup: FastAPI app factory, SQLAlchemy async, Alembic, Docker
- [ ] Brands, Users, Auth endpoints (JWT)
- [ ] Store master CRUD + bulk upload
- [ ] SKU master CRUD + bulk upload
- [ ] Season CRUD + OTB input
- [ ] Cluster CRUD
- [ ] S3 upload integration
- [ ] CSV validation framework (schema + reference + business layers)
- [ ] Sales data ingestion pipeline
- [ ] Inventory data ingestion pipeline
- [ ] Upload status tracking + error report generation
- [ ] Celery setup with Redis broker

**Frontend:**
- [ ] Next.js project setup, Tailwind, auth flow
- [ ] Layout, navigation
- [ ] Upload Hub screen (all upload types)
- [ ] Error report download
- [ ] Setup screens: Stores, Clusters, SKUs, Seasons

**Done when:** A brand's real messy CSV uploads without crashing. Error messages are specific and actionable.

---

### Weeks 5–8: Inventory Truth Engine + GRN

**Backend:**
- [ ] GRN ingestion pipeline
- [ ] inventory_state table and nightly snapshot job
- [ ] ROS calculation with stock-adjusted days
- [ ] Stock cover, sell-through, aging calculations
- [ ] Store display capacity tracking
- [ ] OTB calculation (formula, colour coding)

**Frontend:**
- [ ] GRN list screen
- [ ] OTB input form with real-time calculation display
- [ ] Basic inventory position view (store × SKU grid)

**Done when:** Inventory state table is accurate for a test dataset. Nightly job runs without errors.

---

### Weeks 9–12: Allocation Engine

**Backend:**
- [ ] Store scoring algorithm
- [ ] Eligibility filter (climate, capacity, category)
- [ ] Unit distribution with minimum allocation floor
- [ ] Size curve application
- [ ] Hard constraint enforcement
- [ ] Confidence scoring
- [ ] Explainability reasoning generator
- [ ] Scenario simulation endpoint
- [ ] Override tracking
- [ ] Allocation session + lines storage
- [ ] Transfer list CSV export

**Done when:** Given a test GRN, engine generates a full recommendation in <30 seconds. Reasoning is readable and accurate.

---

### Weeks 13–16: Planner UI + Performance + Alerts

**Backend:**
- [ ] Performance snapshot nightly job
- [ ] Style status classification
- [ ] Performance API endpoints (styles + stores, filterable, sortable)
- [ ] Alert generation job (3 alert types)
- [ ] Alert API endpoints
- [ ] Allocation approval endpoint
- [ ] Outcome backfill job (weekly)

**Frontend:**
- [ ] Allocation screen (full layout with explainability panel)
- [ ] Inline quantity editing + scenario simulation
- [ ] Override reason capture
- [ ] Approve all / individual approval
- [ ] Performance styles table (all filters, sorting, export)
- [ ] Performance stores table (all filters, sorting, export)
- [ ] Dashboard with alerts widget + recent GRNs
- [ ] Alert list + dismiss

**Done when:** An allocator who has never seen the product can complete a full allocation workflow — from GRN to approved transfer list — without asking for help.

---

## 18. Success Metrics

### The Primary Metric
**Transfer rate reduction.** Measure the % of allocated stock that gets transferred out within 6 weeks of first allocation. Baseline this on pilot brands' historical data before they use Kyros. Measure after first season on Kyros. Target: >20% reduction.

### Secondary Metrics

| Metric | What It Measures | Target |
|---|---|---|
| Allocator time per GRN | Time from GRN received to transfer list approved | Baseline 3 days → Target 4 hours |
| AI override rate | % of lines where planner changes AI recommendation | Measure only — no target in v1 |
| Override delta | Avg size of changes when overriding | Measure only — no target in v1 |
| System adoption | % of GRNs allocated via Kyros vs manually | Target 80% by end of pilot season |
| Upload success rate | % of uploads that complete without errors | Target >90% after first month |
| Sell-through improvement | End-of-season ST% vs brand's LY | Measure only in v1 |

### What NOT To Measure in v1
- AI model accuracy (no ML yet — rule-based engine)
- Demand forecast accuracy (not built yet)
- Revenue impact (too early, too many confounding factors)

### How To Know The Product Is Working
The allocator opens Kyros at 9am without being asked to.
That is the real signal. Everything else is a proxy for it.

---

## Appendix A: Configurable Brand Settings

These are per-brand settings stored in a `brand_settings` table. Defaults shown.

```json
{
  "allocation": {
    "minimum_transfer_qty": 6,
    "ros_weight": 0.50,
    "grade_weight": 0.25,
    "cover_weight": 0.25,
    "cover_reorder_threshold_days": 14,
    "new_arrival_days": 14
  },
  "performance": {
    "problem_threshold_cover_days": 42,
    "critical_threshold_age_days": 60,
    "critical_threshold_sellthrough": 0.20
  },
  "alerts": {
    "stockout_risk_threshold_days": 7,
    "aging_alert_days": 45,
    "aging_alert_sellthrough_below": 0.25,
    "grn_unallocated_alert_days": 14
  }
}
```

---

## Appendix B: Data Volume Estimates (v1 Pilot Scale)

| Entity | Estimated Rows |
|---|---|
| Stores per brand | 50–500 |
| SKUs per brand per season | 500–5,000 |
| Sales rows (weekly, 2 seasons) | 500 stores × 2,000 SKUs × 26 weeks = ~26M |
| Inventory state rows (daily, 90 days) | 500 × 2,000 × 90 = ~90M |
| Allocation lines per session | 500 stores × 20 SKUs per GRN = ~10,000 |

**For pilot scale (2–3 brands, up to 200 stores each):**
All of this fits comfortably on a single RDS r6g.large instance with read replica. No sharding, no partitioning required in v1.

Partition `inventory_state` by `snapshot_date` when exceeding 50M rows.
Partition `sales_data` by `week_start_date` when exceeding 100M rows.

---

## Appendix C: Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/kyros
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=0

# Redis
REDIS_URL=redis://host:6379/0

# JWT
JWT_SECRET_KEY=your-secret-key-min-32-chars
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_HOURS=8
JWT_REFRESH_TOKEN_EXPIRE_DAYS=30

# AWS
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=ap-south-1
S3_BUCKET_NAME=kyros-uploads-prod

# App
APP_ENV=production  # development | staging | production
LOG_LEVEL=INFO
CORS_ORIGINS=https://app.kyros.in

# Celery
CELERY_BROKER_URL=redis://host:6379/1
CELERY_RESULT_BACKEND=redis://host:6379/2
```

---

*Last updated: MVP v1.0 — This document is the single source of truth for the Kyros MVP build. Any feature not described in this document is out of scope for v1. When in doubt, build less and validate with pilots.*
