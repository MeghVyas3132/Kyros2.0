# Kyros
### The Merchandising Intelligence Platform Built for How Retail Actually Works

> **Closed-loop. API-first. Forecast-accurate.**  
> From season planning to post-season learning — one platform, zero spreadsheets, no black boxes.

---

## Table of Contents

1. [The Problem](#1-the-problem)
2. [The Market](#2-the-market)
3. [Why Everything Else Falls Short](#3-why-everything-else-falls-short)
4. [What Kyros Is](#4-what-kyros-is)
5. [The Closed Loop](#5-the-closed-loop)
6. [Platform Architecture](#6-platform-architecture)
7. [Core Capabilities](#7-core-capabilities)
8. [Technical Specification](#8-technical-specification)
9. [API Design](#9-api-design)
10. [Data Model](#10-data-model)
11. [Security & Compliance](#11-security--compliance)
12. [Infrastructure](#12-infrastructure)
13. [Integrations](#13-integrations)
14. [Performance Standards](#14-performance-standards)
15. [Roadmap](#15-roadmap)
16. [Success Metrics](#16-success-metrics)

---

## 1. The Problem

Retail merchandising is a multi-billion dollar decision process running on decade-old infrastructure.

A merchandising planner at a 150-store fashion brand makes decisions in October that determine whether February is profitable. They are deciding what to buy, how much, from which vendors, at which price points, for which stores — six months before the customer walks in.

They make these decisions using:
- Excel files emailed between departments
- Disconnected ERP reports with 48-hour data lag
- Tribal knowledge that walks out the door when a senior planner leaves
- Gut instinct dressed up as "market experience"

**The consequences are not abstract:**

- ₹70,000–₹1,40,000 crore worth of excess stock is produced globally every year
- Inaccurate size buying alone causes 20% average monthly profit loss in apparel
- By the time a slow seller is identified, the markdown window has passed
- When a star product runs out, there is no system telling anyone to reorder

The core failure is not that retailers lack data. They have too much of it, in too many places, with no system connecting planning decisions to execution reality to outcome learning.

**Kyros is that system.**

---

## 2. The Market

### Total Addressable Market

India's fashion retail market is **$60 billion in 2024**, growing at **12.87% CAGR** through 2030. Globally, the retail merchandise financial planning software market is expanding alongside a structural shift: brands that have crossed ₹100 crore in revenue are outgrowing Excel but cannot afford or justify a ₹5 crore enterprise implementation.

That band — brands operating **50 to 500 stores**, growing at 20–40% year-on-year, building technology stacks for the first time — is the most underserved segment in retail software today.

### The Real Serviceable Market

| Segment | Store Count | Revenue Range | Technology Status |
|---|---|---|---|
| D2C Fashion Brands | 10–80 stores | ₹50–300 cr | Excel + basic ERP |
| Multi-brand Fashion Retailers | 80–300 stores | ₹300 cr–₹2,000 cr | Fragmented point solutions |
| Regional Apparel Chains | 100–500 stores | ₹500 cr–₹5,000 cr | Legacy systems or Excel |
| International Brands (India ops) | 50–200 stores | ₹200 cr–₹3,000 cr | Global tools not India-fit |

Over **700 digital fashion brands** exist in India. Fewer than 10% have scaled beyond ₹50 crore. The brands breaking out — the ones hitting ₹200 crore and above — share one characteristic: they stop winging it on spreadsheets and start making structured buying decisions. Kyros is built for the moment they're ready to make that shift.

### Why Now

Three forces are converging:

**Post-COVID inventory trauma** — Every fashion brand that over-bought in 2021–2022 and sat on dead stock for 18 months is now willing to pay for a system that prevents it from happening again.

**D2C maturity** — The first generation of Indian D2C brands that bootstrapped to scale is hitting the operational ceiling of founder-led buying. They need institutional process without enterprise complexity.

**Data infrastructure readiness** — POS, WMS, and ERP systems are now generating clean enough data that a planning intelligence layer can actually consume it meaningfully.

---

## 3. Why Everything Else Falls Short

### The Enterprise Tier: Not For You

Oracle Retail, Blue Yonder, SAP Retail. These are $500K–$2M+ annual contracts. 12–18 month implementations. Dedicated IT teams required to operate. Built for Walmart, not for a 150-store kurta brand in Bengaluru. Not the competition. Not the customer.

### The Actual Competitors — And Their Real Problems

#### Increff

The most direct competitor. Indian, established, serving brands like Puma, Lenskart, and Blackberrys. Their pitch is end-to-end merchandising. But here is what their own customers say publicly:

> *"The unreliable demand forecast is a big drawback. Lost sales and excess inventory puts me in a bad position for my business."*
> — Verified Gartner Review, Increff Customer

That is not a minor complaint. That is the core function of a merchandising platform failing in production.

Additionally:
- **No public API.** Integrations happen over SFTP file drops. In 2025.
- **Opaque pricing.** Brands cannot evaluate the product commercially without going through a sales call.
- **Steep reporting curve.** New users struggle with setup, requiring significant implementation time.
- **Domestic-first architecture.** Multi-country, multi-currency, and cross-border operations are afterthoughts.

#### Toolio

US-based, cloud-native, well-marketed. But:

- **No API.** Same problem as Increff.
- **Cannot account for historical stockouts.** If a SKU was out of stock for 6 weeks last season, Toolio plans from that corrupted demand signal without correcting for lost sales. It underestimates demand for your best products.
- **~20 brands after years in market.** Their go-to-market is broken.
- **Steep learning curve** despite positioning as the modern, easy alternative.

### The Gap Kyros Fills

| Capability | Increff | Toolio | **Kyros** |
|---|---|---|---|
| End-to-end merchandising loop | Yes | Partial | Yes |
| Open REST API | No | No | Yes |
| Lost sales correction in forecasting | No | No | Yes |
| Transparent self-serve pricing | No | No | Yes |
| Planogram-aware allocation | Partial | No | Yes |
| Workflow enforcement (not optional) | No | No | Yes |
| Season-to-season learning loop | Partial | No | Yes |
| Multi-country support | Limited | No | Yes |
| Self-serve onboarding | No | No | Yes |

---

## 4. What Kyros Is

Kyros is an enterprise merchandising management platform that closes the loop between seasonal planning, buying execution, store allocation, in-season performance management, and post-season learning.

It is not a point solution for one part of the merchandising process. It is the operating system for the entire buying cycle.

### Core Principles

**Forecast accuracy is non-negotiable.** Every recommendation Kyros makes — how much to buy, where to allocate, when to markdown — is only as good as its demand signal. Kyros corrects for historical stockouts, adjusts for seasonality, and builds confidence intervals into every projection. The system never plans from a lie.

**Workflow integrity without rigidity.** Kyros enforces the correct sequence of merchandising activities — a season cannot move to buying without an approved range, a PO cannot be raised without OTB headroom — but provides exception handling for the real-world edge cases that every merchandising team encounters.

**API-first, always.** Every function in Kyros is accessible via documented REST API. No SFTP. No file drops. No integration projects that take 3 months. Brands connect their POS, WMS, and ERP in days, not quarters.

**The closed loop is the product.** Learnings from each season's performance flow directly into the next season's planning defaults. Store grades update. Attribute weights recalibrate. Allocation rules adjust. A brand running Kyros for three seasons plans materially better than a brand running it for one. That data flywheel is the moat.

**Transparent by design.** Pricing is public. Onboarding is self-serve. Recommendations show their reasoning. When the system suggests a markdown, it shows you exactly which metrics triggered it and what outcome it projects.

---

## 5. The Closed Loop

This is the architectural heart of Kyros. Most merchandising tools handle one or two phases. Kyros connects all seven into a single continuous system where every output feeds the next input.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   SEASON N                                                          │
│                                                                     │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    │
│   │  Season  │───▶│   OTB &  │───▶│   Buy    │───▶│Allocation│    │
│   │  Setup   │    │  Range   │    │ Planning │    │ Engine   │    │
│   └──────────┘    └──────────┘    └──────────┘    └──────────┘    │
│                                                          │          │
│   ┌──────────┐    ┌──────────┐    ┌──────────┐          │          │
│   │ Post-    │◀───│Inventory │◀───│In-Season │◀─────────┘          │
│   │ Season   │    │  Health  │    │ Actions  │                     │
│   │ Analysis │    └──────────┘    └──────────┘                     │
│   └──────────┘                                                      │
│         │                                                           │
│         │  Learnings feed Season N+1 planning defaults              │
│         │  ┌ Store grades updated                                   │
│         │  ├ Attribute weights recalibrated                         │
│         │  ├ OTB timing adjusted from actuals                       │
│         │  └ Allocation rules refined from transfer data            │
│         ▼                                                           │
│   SEASON N+1 (starts smarter)                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

No competitor closes this loop architecturally. Increff surfaces post-season reports. Toolio has performance dashboards. Neither feeds outcomes back into planning defaults automatically. In Kyros, that feedback is the product.

---

## 6. Platform Architecture

### System Overview

```
                              ┌─────────────────┐
                              │  Load Balancer  │
                              │    (Nginx)      │
                              └────────┬────────┘
                                       │
               ┌───────────────────────┼───────────────────────┐
               │                       │                       │
     ┌─────────▼──────┐     ┌─────────▼──────┐     ┌─────────▼──────┐
     │   Frontend     │     │   Frontend     │     │   Frontend     │
     │  (Next.js 14)  │     │  (Next.js 14)  │     │  (Next.js 14)  │
     └─────────┬──────┘     └─────────┬──────┘     └─────────┬──────┘
               │                       │                       │
               └───────────────────────┼───────────────────────┘
                                       │
                              ┌────────▼────────┐
                              │   API Gateway   │
                              └────────┬────────┘
                                       │
               ┌───────────────────────┼───────────────────────┐
               │                       │                       │
     ┌─────────▼──────┐     ┌─────────▼──────┐     ┌─────────▼──────┐
     │    Backend     │     │    Backend     │     │    Backend     │
     │   (FastAPI)    │     │   (FastAPI)    │     │   (FastAPI)    │
     └─────────┬──────┘     └─────────┬──────┘     └─────────┬──────┘
               │                       │                       │
               └───────────────────────┼───────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
           ┌────────▼───┐    ┌────────▼───┐    ┌────────▼───┐
           │ PostgreSQL │    │   Redis    │    │    S3 /    │
           │    (DB)    │    │  (Cache)   │    │Object Store│
           └────────────┘    └────────────┘    └────────────┘
```

### Design Principles

**Stateless services** — Backend nodes hold no session state. Horizontal scaling is linear. A load spike at allocation time does not require re-architecture.

**Database as source of truth** — Redis is ephemeral. Every cache can be rebuilt from Postgres. No business logic lives outside the primary database.

**Event-driven where it matters** — OTB recalculation, alert generation, and recommendation updates are event-triggered via internal message queues, not polling. When a PO is raised, OTB updates in under 500ms.

**Graceful degradation** — If the recommendation engine is slow, the rest of the platform works. If the forecasting job hasn't run, planners see the last known state with a clear staleness indicator.

---

## 7. Core Capabilities

### Phase 1 — Foundation Complete

The operational backbone. Authentication, season lifecycle management, organizational structure (clusters, locations), data ingestion via CSV, and a baseline analytics dashboard.

**Season Workflow State Machine:**
```
Created ──▶ Locations Defined ──▶ Plan Uploaded ──▶ OTB Uploaded ──▶ Range Uploaded ──▶ Locked
```

Each transition is enforced. A season cannot reach Locked without completing every upstream step. This is not a suggestion — it is a system constraint. Buying cannot begin on an incomplete plan.

**Delivered:**
- JWT authentication with RBAC (admin, planner, buyer, allocator, viewer)
- Season, cluster, and location management
- CSV ingestion for season plans, OTB plans, and range intent
- Purchase order and GRN tracking (view mode)
- Analytics dashboard with summary KPIs

---

### Phase 2 — OTB Management and Range Planning

Static OTB uploads become a live, dynamic position that updates as orders are placed.

**OTB Formula:**
```
OTB = Planned Sales + Planned Closing Stock − Opening Stock − On Order
```

This is calculated in real-time, at category × month × cluster granularity. When a buyer raises a PO, OTB updates within 500ms via WebSocket broadcast. No refresh required. No stale numbers.

**Key differentiators:**
- OTB transfer workflow between categories with approval chain
- Alert system for exhaustion, underutilization, and category imbalance
- Visual range builder with drag-and-drop attribute matrix
- Prior-season range comparison with variance highlighting
- Range approval workflow: Draft → Submitted → Approved → Locked

---

### Phase 3 — Buy Planning and Order Management

Full purchase order lifecycle from hit-wise buy planning through GRN reconciliation.

**Hit-wise planning** — A "hit" is a buying decision unit: a specific product story assigned to a vendor with an OTB allocation and risk grade (A = proven, B = moderate, C = new). Risk-graded buying makes conservative vs. aggressive positioning an explicit, documented decision — not a gut call.

**OTB validation is a hard gate** — A PO cannot be submitted if it would push category OTB negative. The system warns at 50% consumption and blocks at the limit. Cancelled POs immediately release OTB back to the category.

**GRN reconciliation** — Every receipt is matched line-by-line against the original PO. Variances above 10% require documented reason. The system closes PO lines automatically when fully received and flags open lines that are overdue.

---

### Phase 4 — Allocation and Planogram Management

The allocation engine is where Kyros diverges most sharply from competitors.

**Planogram-aware allocation** — Most systems calculate allocation from sales history. Kyros adds a hard constraint layer: display capacity by store and category. If a store has 40 style slots for kurtas and the allocation engine wants to send 60 styles, it cannot. The system respects physical reality.

**Allocation factors:**
| Factor | Weight | Source |
|---|---|---|
| Historical sales performance | High | Season plan actuals |
| Store grade (A/B/C) | High | Calculated quarterly |
| Display capacity | High | Planogram data |
| Attribute performance by cluster | Medium | Attribute performance table |
| Current inventory position | Medium | Live position |
| Climate / regional suitability | Medium | Location attributes |

**Algorithm flow:**
```
For each style in allocation batch:
  1. Base quantity by store grade split (A: 50%, B: 35%, C: 15%)
  2. Adjust for historical attribute ROS at store cluster
  3. Apply display capacity ceiling
  4. Adjust for current inventory position
  5. Round to pack size
  6. Validate: total allocation = available quantity
```

**Allocation simulation** — Before committing, allocators can run "what-if" scenarios: change grade weights, adjust capacity, test priority rules. Compare scenarios side-by-side. Save named scenarios. Kyros shows the projected outcome of each. Decisions made with evidence.

---

### Phase 5 — In-Season Performance and Actions

Real-time performance monitoring with action recommendations that have teeth.

**Core metrics calculated daily:**
| Metric | Formula |
|---|---|
| ROS (Rate of Sale) | Units Sold ÷ Store Weeks |
| Sell-Through | Units Sold ÷ Units Received |
| Stock Cover | Stock Units ÷ Weekly ROS |
| Aging | Days Since GRN |
| Markdown Rate | Markdown Value ÷ Original Value |

**Performance classification — the 5-cell matrix:**
| Classification | ROS | Sell-Through | Action |
|---|---|---|---|
| Star | High | High | Reorder, expand distribution |
| Potential | High | Low | Transfer in, push inventory |
| Steady | Medium | Medium | Monitor |
| Dog | Low | Low | Markdown, transfer out |
| Problem | Low | High stock | Urgent markdown |

**Recommendation engine** runs daily at 4 AM. For every style × location combination, it evaluates performance metrics, classifies position, and generates ranked recommendations. Planners see a prioritized action queue — not a raw data dump. Every recommendation shows its trigger metrics and projected impact. Accept, reject, or modify. The system learns from rejections.

---

### Phase 6 — Inventory Health and Range Exposure

The question Phase 5 asks is "how are products selling?" Phase 6 asks a harder question: **"where is all our inventory and is any of it dying silently?"**

**Range exposure tracking** — A product is worthless sitting in a warehouse. Kyros tracks every SKU from GRN to first store arrival. If a style has been received for more than 14 days and hasn't reached a single store, the system flags it. Styles sitting in warehouse longer than 7 days are automatically surfaced to the allocator queue.

**Exposure status:**
| Status | Definition | Trigger |
|---|---|---|
| Not Exposed | Received, not in any store | Alert at 7 days |
| Partially Exposed | In some stores, not all planned | Review at 14 days |
| Fully Exposed | In all planned stores | Target state |
| Over Exposed | More stores than planned | Capacity check |

**Inventory health score** — A single composite score (0–100) calculated daily across four dimensions: age health (30%), distribution health (25%), exposure health (25%), productivity health (20%). A score below 60 triggers automatic alerts. Category scores are benchmarked against historical norms.

---

### Phase 7 — Post-Season Analytics and Learning Loop

The phase that makes every future season better than the last.

**What most platforms do:** Generate a post-season report. Planner reads it. Makes mental notes. Starts next season from scratch.

**What Kyros does:** Generate the analysis, score every attribute and store, produce ranked recommendations for next season, and — when the planner accepts them — automatically update next season's planning defaults.

**Accepted recommendations cascade:**
| Learning Source | Feeds Into |
|---|---|
| Category performance score | Budget allocation weights for N+1 |
| Cluster learnings | Allocation grade split percentages |
| Attribute scores | Range architecture style count targets |
| Store grade accuracy | Store grade reassignment |
| OTB timing variance | Receipt calendar defaults |

The first season on Kyros, a brand plans with their own historical knowledge. The third season, they plan with their own historical knowledge plus two seasons of system-corrected learnings. That compounding is not a feature. It is the product.

---

## 8. Technical Specification

### Technology Stack

#### Backend
| Component | Technology | Version |
|---|---|---|
| Framework | FastAPI | 0.109+ |
| Language | Python | 3.11+ |
| ORM | SQLAlchemy | 2.0+ |
| Migrations | Alembic | 1.13+ |
| Server | Uvicorn | 0.27+ |
| Validation | Pydantic | 2.x |
| Auth | python-jose | 3.x |
| Password hashing | passlib + bcrypt | 1.7+ |
| Task queue | Celery + Redis | 5.x |
| WebSocket | FastAPI WebSocket | Native |

#### Frontend
| Component | Technology | Version |
|---|---|---|
| Framework | Next.js | 14.x |
| Language | TypeScript | 5.x |
| UI | React | 18.x |
| Styling | Tailwind CSS | 3.x |
| Forms | React Hook Form | 7.x |
| Validation | Zod | 3.x |
| State | React Context + SWR | Native |
| Charts | Recharts | 2.x |

#### Data Layer
| Component | Technology | Version |
|---|---|---|
| Primary Database | PostgreSQL | 15+ |
| Cache / Queue | Redis | 7+ |
| Object Storage | S3-compatible | — |
| Search (Phase 5+) | Elasticsearch | 8+ |

#### Infrastructure
| Component | Technology |
|---|---|
| Containerization | Docker |
| Orchestration | Kubernetes |
| Reverse Proxy | Nginx |
| CI/CD | GitHub Actions |
| Cloud | AWS / GCP |

---

## 9. API Design

### Philosophy

Every function in Kyros is accessible via REST API. No exceptions. No SFTP workarounds. No "contact your account manager for integration support." If you can do it in the UI, you can do it via API.

This is a deliberate market position. Both primary competitors have no public API. Kyros is API-first from day one.

### Standards

- RESTful design — resources as nouns, actions as HTTP methods
- URI versioning — `/api/v1/`
- Snake_case JSON properties
- Cursor-based pagination for large result sets
- Consistent error envelope across all endpoints
- OpenAPI 3.0 specification auto-generated and publicly hosted

### Standard Response Envelope
```json
{
  "data": {},
  "meta": {
    "page": 1,
    "per_page": 20,
    "total": 847,
    "total_pages": 43
  }
}
```

### Standard Error Envelope
```json
{
  "error": {
    "code": "OTB_EXCEEDED",
    "message": "Purchase order value exceeds available OTB for category",
    "details": {
      "available_otb": 450000.00,
      "requested_value": 680000.00,
      "category": "Kurta",
      "month": "2025-03"
    }
  }
}
```

### Core Endpoint Surface

| Domain | Endpoints | Notes |
|---|---|---|
| Authentication | 5 | Login, register, refresh, logout, profile |
| Seasons | 6 | Full CRUD + status transition |
| Clusters | 5 | Full CRUD + activation |
| Locations | 5 | Full CRUD + bulk CSV import |
| Plans | 4 | Season plan, OTB plan upload and retrieval |
| OTB | 5 | Position, consumption, adjustments, forecast |
| Range | 5 | Architecture, submit, approve, compare |
| Purchase Orders | 7 | Full lifecycle + timeline |
| Vendors | 5 | CRUD + performance metrics |
| GRNs | 4 | Create, list, details, pending |
| Allocations | 6 | Calculate, approve, override lines, simulate |
| Performance | 5 | Summary, styles, stores, matrix, trends |
| Alerts | 4 | List, detail, action, dismiss |
| Transfers | 6 | Full lifecycle |
| Markdowns | 6 | Full lifecycle + calendar |
| Inventory | 6 | Position, distribution, aging, health score |
| Range Exposure | 4 | Summary, unexposed, detail, push |
| Analysis | 8 | Season analysis, variance, attributes, recommendations |
| Webhooks | 3 | Register, list, delete |

### Rate Limits

| Category | Limit |
|---|---|
| Authentication | 10 req/min |
| Read operations | 100 req/min |
| Write operations | 30 req/min |
| File uploads | 5 req/min |
| Analytics / reports | 20 req/min |

### WebSocket Events

Real-time events broadcast to connected clients without polling:

| Event | Trigger | Payload |
|---|---|---|
| `otb.updated` | PO created, confirmed, or cancelled | OTB position by category |
| `otb.alert` | OTB threshold crossed | Alert details + severity |
| `allocation.calculated` | Engine completes recommendation run | Allocation ID + summary |
| `alert.new` | Performance alert generated | Alert type + affected styles |
| `transfer.status` | Transfer state changes | Transfer ID + new status |

---

## 10. Data Model

### Core Schema

#### Users
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'viewer',
    is_active BOOLEAN DEFAULT TRUE,
    is_verified BOOLEAN DEFAULT FALSE,
    last_login TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### Seasons
```sql
CREATE TABLE seasons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    season_code VARCHAR(20) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'created',
    -- Status: created | locations_defined | plan_uploaded |
    --         otb_uploaded | range_uploaded | locked | closed
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### OTB Positions (Dynamic)
```sql
CREATE TABLE otb_positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id UUID NOT NULL REFERENCES seasons(id),
    category_id UUID REFERENCES categories(id),
    month DATE NOT NULL,
    planned_otb DECIMAL(15,2),
    consumed_otb DECIMAL(15,2),
    available_otb DECIMAL(15,2),
    last_calculated TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### Allocations
```sql
CREATE TABLE allocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    season_id UUID NOT NULL REFERENCES seasons(id),
    grn_id UUID REFERENCES grns(id),
    allocation_date DATE NOT NULL,
    status VARCHAR(50) DEFAULT 'pending',
    -- Status: pending | calculated | in_review | modified | approved | shipped | complete
    created_by UUID REFERENCES users(id),
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE allocation_lines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    allocation_id UUID NOT NULL REFERENCES allocations(id),
    location_id UUID NOT NULL REFERENCES locations(id),
    sku_id VARCHAR(50) NOT NULL,
    recommended_quantity INTEGER NOT NULL,
    final_quantity INTEGER NOT NULL,
    override_reason TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### Performance Snapshots
```sql
CREATE TABLE performance_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_date DATE NOT NULL,
    location_id UUID REFERENCES locations(id),
    sku_id VARCHAR(50) NOT NULL,
    units_sold INTEGER DEFAULT 0,
    units_on_hand INTEGER DEFAULT 0,
    ros DECIMAL(10,4),
    sell_through DECIMAL(5,2),
    stock_cover DECIMAL(5,2),
    aging_days INTEGER,
    lost_sales_adjusted BOOLEAN DEFAULT FALSE,
    -- Kyros-specific: flags whether demand was corrected for stockout periods
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_perf_date ON performance_snapshots(snapshot_date);
CREATE INDEX idx_perf_location ON performance_snapshots(location_id);
CREATE INDEX idx_perf_sku ON performance_snapshots(sku_id);
```

#### Season Learnings (The Closed Loop Tables)
```sql
CREATE TABLE attribute_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES season_analyses(id),
    attribute_type VARCHAR(50) NOT NULL,
    attribute_value VARCHAR(100) NOT NULL,
    planned_sales DECIMAL(15,2),
    actual_sales DECIMAL(15,2),
    planned_margin DECIMAL(5,2),
    actual_margin DECIMAL(5,2),
    ros DECIMAL(10,4),
    sell_through DECIMAL(5,2),
    performance_score INTEGER,
    -- > 120: Increase investment | 80-120: Maintain | < 80: Reduce
    recommendation VARCHAR(50),
    applied_to_next_season BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE season_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL REFERENCES season_analyses(id),
    recommendation_area VARCHAR(50) NOT NULL,
    current_value VARCHAR(100),
    recommended_value VARCHAR(100),
    expected_impact TEXT,
    confidence_level VARCHAR(20),
    priority INTEGER,
    status VARCHAR(20) DEFAULT 'pending',
    accepted_by UUID REFERENCES users(id),
    accepted_at TIMESTAMP WITH TIME ZONE,
    applied_to_season_id UUID REFERENCES seasons(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Indexing Strategy

```sql
-- Season lookups
CREATE INDEX idx_seasons_status ON seasons(status);
CREATE INDEX idx_seasons_dates ON seasons(start_date, end_date);

-- Location hierarchy
CREATE INDEX idx_locations_cluster ON locations(cluster_id);
CREATE INDEX idx_locations_type ON locations(location_type);

-- Planning data
CREATE INDEX idx_season_plans_season ON season_plans(season_id);
CREATE INDEX idx_otb_plans_season_month ON otb_plans(season_id, month);
CREATE INDEX idx_otb_positions_season_category ON otb_positions(season_id, category_id);

-- Order tracking
CREATE INDEX idx_purchase_orders_season ON purchase_orders(season_id);
CREATE INDEX idx_purchase_orders_status ON purchase_orders(status);
CREATE INDEX idx_grns_po ON grns(po_id);

-- Performance (high-volume tables)
CREATE INDEX idx_perf_snapshot_date ON performance_snapshots(snapshot_date);
CREATE INDEX idx_perf_snapshot_location ON performance_snapshots(location_id);
CREATE INDEX idx_perf_snapshot_sku ON performance_snapshots(sku_id);

-- Allocation
CREATE INDEX idx_allocation_lines_allocation ON allocation_lines(allocation_id);
CREATE INDEX idx_allocation_lines_location ON allocation_lines(location_id);
```

### Data Retention

| Category | Retention | Archive Strategy |
|---|---|---|
| Transaction data | 7 years | Annual cold storage archive |
| Audit logs | 5 years | Quarterly archive |
| Performance snapshots | 3 years | Annual archive |
| Session data | 30 days | Auto-expiry in Redis |
| Temp calculations | 7 days | Automated cleanup job |

---

## 11. Security & Compliance

### Authentication

- JWT access tokens — 30-minute expiration, HS256
- Refresh tokens — 7-day expiration, HttpOnly cookie
- bcrypt password hashing — cost factor 12
- MFA support — TOTP-based
- Failed login attempt logging and rate limiting

### Role-Based Access Control

| Role | Seasons | Plans | POs | Allocation | Users |
|---|---|---|---|---|---|
| Admin | CRUD | CRUD | CRUD | CRUD | CRUD |
| Planner | CRUD | CRUD | Read | Read | Read |
| Buyer | Read | Read | CRUD | Read | Read |
| Allocator | Read | Read | Read | CRUD | Read |
| Viewer | Read | Read | Read | Read | — |

### Data Security

| Layer | Method |
|---|---|
| In transit | TLS 1.3 |
| At rest (DB) | AES-256 |
| At rest (files) | AES-256 |
| Secrets | AWS Secrets Manager / env vars |
| Audit logging | All mutations logged: user, timestamp, before/after |

### Application Security

- Parameterized queries via SQLAlchemy (no raw SQL)
- Input validation via Pydantic (backend) and Zod (frontend)
- React XSS prevention + CSP headers
- CSRF token-based protection
- Dependency vulnerability scanning in CI pipeline

---

## 12. Infrastructure

### Production Environment

| Component | Spec | Count |
|---|---|---|
| Frontend (Next.js) | t3.medium, 2 vCPU, 4 GB | 2 |
| Backend (FastAPI) | t3.large, 2 vCPU, 8 GB | 3 |
| Database (PostgreSQL) | r6g.large, 2 vCPU, 16 GB | 1 primary + 1 replica |
| Cache (Redis) | t3.small, 2 vCPU, 2 GB | 1 |
| Load Balancer | ALB | 1 |

### Availability

| Metric | Target |
|---|---|
| Uptime (business hours) | 99.5% |
| RTO | 4 hours |
| RPO | 1 hour |
| Planned maintenance window | Max 4 hours/month, off-peak |

### Backup Strategy

| Component | Frequency | Retention | Location |
|---|---|---|---|
| PostgreSQL | Continuous WAL + daily snapshot | 30 days | Cross-region S3 |
| File storage | Daily | 90 days | Cross-region S3 |
| Configuration | On every change | 1 year | Git |

### Scheduled Background Jobs

| Job | Schedule | Purpose |
|---|---|---|
| Inventory position snapshot | Daily 1 AM | Capture stock positions |
| Performance snapshot | Daily 2 AM | Calculate daily metrics |
| Alert generation | Daily 3 AM | Evaluate thresholds |
| Recommendation engine | Daily 4 AM | Generate action recommendations |
| OTB recalculation | Event-driven | Triggered on every PO change |
| Health score calculation | Daily 4 AM | Composite inventory health |
| Prevention scan | Daily 5 AM | Identify at-risk inventory |

---

## 13. Integrations

### Integration Philosophy

Kyros integrates forward, not through middleware. Every integration is API-to-API. File drops are supported for legacy systems but are not the default.

### Supported Integration Patterns

| Pattern | Use Case | Latency |
|---|---|---|
| REST API (push) | Real-time POS sales data | < 1 second |
| REST API (pull) | Kyros consuming WMS inventory | Configurable |
| Webhook | Kyros publishing events to external systems | < 500ms |
| CSV/SFTP | Legacy ERP systems | Batch, scheduled |

### Integration Surface

| System Type | Direction | Data |
|---|---|---|
| POS (PoS systems) | Inbound | Daily sales, returns |
| WMS | Bidirectional | Inventory positions, GRN confirmation |
| ERP (SAP, Oracle) | Bidirectional | PO creation, financial sync |
| Vendor Portal | Outbound | PO submission, status updates |
| Logistics / 3PL | Bidirectional | Shipment tracking |
| BI Tools | Outbound | Reporting data export |
| Finance Systems | Outbound | Invoice reconciliation |

### Webhook Events Published

```json
{
  "event": "season.status_changed",
  "timestamp": "2025-10-15T09:30:00Z",
  "payload": {
    "season_id": "uuid",
    "from_status": "plan_uploaded",
    "to_status": "otb_uploaded"
  }
}
```

Events: `season.*`, `po.*`, `grn.*`, `allocation.*`, `transfer.*`, `markdown.*`, `alert.*`

---

## 14. Performance Standards

### Response Time Targets

| Operation | Target | Maximum |
|---|---|---|
| Simple read | 100ms | 500ms |
| Complex query | 500ms | 2s |
| Write operation | 200ms | 1s |
| OTB recalculation (on PO change) | < 500ms | 1s |
| Allocation engine (100 stores) | < 5s | 10s |
| Allocation engine (500 stores) | < 20s | 40s |
| Report generation | < 10s | 60s |
| File upload (10MB CSV) | < 5s | 30s |
| WebSocket broadcast | < 100ms | 500ms |

### Throughput Targets

| Metric | Target |
|---|---|
| Concurrent users | 500 |
| Requests per second | 1,000 |
| Background jobs per hour | 500 |
| File uploads per hour | 100 |

### Scalability Targets

| Dimension | Year 1 | Year 3 |
|---|---|---|
| Active brands | 50 | 500 |
| Locations | 5,000 | 50,000 |
| SKUs | 500,000 | 5,000,000 |
| Daily transaction records | 1M | 50M |
| Concurrent users | 500 | 5,000 |

---

## 15. Roadmap

### Phase 1 — Foundation Complete (10 weeks)
Authentication, season lifecycle, cluster/location management, CSV data ingestion, PO/GRN tracking, analytics dashboard.

### Phase 2 — OTB and Range Planning (8–10 weeks)
Dynamic OTB engine, real-time consumption tracking, range builder, approval workflow, WebSocket broadcasting.

### Phase 3 — Buy Planning and Order Management (6–8 weeks)
Hit-wise buy planning, full PO lifecycle, vendor management, GRN reconciliation, OTB consumption dashboard.

### Phase 4 — Allocation and Planogram Management (10–12 weeks)
Allocation recommendation engine, planogram-aware constraints, store grading, simulation and scenario comparison, rules engine.

### Phase 5 — In-Season Performance and Actions (8–10 weeks)
Performance snapshots, classification engine, alert system, recommendation queue, transfer and markdown workflows.

### Phase 6 — Inventory Health and Range Exposure (6–8 weeks)
Inventory position tracking, aging analysis, range exposure monitoring, health score, dead stock prevention.

### Phase 7 — Post-Season Analytics and Learning Loop (6–8 weeks)
Season closeout, budget vs. actual analysis, attribute scoring, store learnings, recommendation engine feeding Season N+1.

---

## 16. Success Metrics

### Platform Health

| Metric | Target |
|---|---|
| System availability | 99.5% |
| API P95 response time | < 500ms |
| OTB calculation latency on PO change | < 500ms |
| Alert generation completeness | 100% of catalog daily |

### Business Outcomes (Per Customer)

| Metric | Target |
|---|---|
| Reduction in aged stock | 25% within 2 seasons |
| First allocation accuracy | > 75% (no transfer required) |
| Transfer rate | < 20% of allocation volume |
| Markdown rate reduction | 15% within 2 seasons |
| Planning cycle time reduction | 30% within 1 season |
| OTB accuracy (plan vs. actual) | Within 5% |
| Time to range exposure | < 7 days average |
| Inventory turn improvement | 15% within 2 seasons |

### Adoption Metrics

| Metric | Target |
|---|---|
| Time to first value (live plan) | < 2 weeks from onboarding |
| Daily active usage rate | > 80% of licensed users |
| Feature utilization | All core features within 30 days |
| Recommendation acceptance rate | > 60% |
| Season-over-season planning accuracy improvement | > 10% YoY |

---

## Appendix: Glossary

| Term | Definition |
|---|---|
| OTB (Open-to-Buy) | Budget available for purchasing. Calculated as: Planned Sales + Planned Closing Stock − Opening Stock − On Order |
| ROS (Rate of Sale) | Units sold per store per week. The primary velocity metric |
| Sell-Through | Percentage of received inventory that has been sold |
| Stock Cover | Weeks of inventory on hand at current ROS |
| Hit | A buying decision unit — a product story assigned to a vendor with OTB allocation and risk grade |
| GRN (Goods Receipt Note) | Document recording receipt of goods against a PO |
| Planogram | Defined display capacity by store, category, and fixture type |
| Range | The full assortment of products planned for a season |
| Allocation | Distribution of received inventory across store locations |
| Cluster | Grouping of stores with similar characteristics for planning and allocation purposes |
| Lost Sales Correction | Statistical adjustment to demand history that accounts for periods when a SKU was out of stock — ensuring forecasts reflect true demand rather than supply-constrained actuals |
| Health Score | Composite inventory metric (0–100) across age, distribution, exposure, and productivity dimensions |

---

*Kyros — Built for the brands that are ready to stop guessing.*
