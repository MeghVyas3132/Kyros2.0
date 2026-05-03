# 05 — KYROS MVP Design

Translating the decision model into a product. This doc defines modules, data models, and the high-level algorithms that each module runs.

Treat this as the **system architecture for the planning brain**. The technical architecture (FastAPI, Postgres, Celery) is already documented in [../CLAUDE.md](../CLAUDE.md); this doc focuses on the *shape of the decisions* the system must support.

---

## Module Map

```
┌─────────────────────────────────────────────────────────────┐
│                       SEASON SETUP                          │
│  Create season → weeks → status lifecycle                   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                   BUDGET PLANNER (OTB)                      │
│  Category × Month grid → OTB = sales + closing − opening    │
│  − on_order. Overrun warnings. Reserve for chase.           │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                   ASSORTMENT BUILDER                        │
│  Style list by category × price band × risk group.          │
│  Depth targets auto-computed from OTB + store count.        │
│  Width vs depth slider. OTB reconciliation live.            │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                   STORE STRATEGY                            │
│  Grade per (store × category × price band).                 │
│  Climate zones, clusters, eligibility rules.                │
│  Cover target editor per (grade × risk).                    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                      BUY PLANNER                            │
│  Style → total units → vendor → expected delivery.          │
│  OTB check, MOQ check, depth vs demand reconciliation.      │
│  Opening-order % dial (reserve for chase).                  │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                       INGESTION                             │
│  Sales history, grades, size guide, GRN.                    │
│  CSV auto-mapping, validation, progress.                    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                  ALLOCATION ENGINE                          │
│  GRN → store × SKU distribution.                            │
│  4-tier demand, stockout correction, confidence tiers.      │
│  Explainable reasoning.                                     │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                  REVIEW & APPROVE                           │
│  Line-level override, rationale capture, CSV export to WMS. │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│              (Post-MVP) LEARNING LOOP                       │
│  Actuals → residuals → next-season defaults.                │
└─────────────────────────────────────────────────────────────┘
```

---

## Module Specifications

### M1 — Season Setup
**Purpose**: establish the time container for every downstream decision.

**Fields**:
- name, start_date, end_date, weeks_remaining
- status: DRAFT → PLANNING → BUYING → RECEIVING → ALLOCATING → IN_SEASON → CLOSED
- channel splits (retail / ecom / wholesale) — optional in MVP

**State transitions** are gated by upstream completion:
- Cannot enter BUYING without OTB signed off
- Cannot enter RECEIVING without buy plan POs
- Cannot enter ALLOCATING without GRN

**Already exists** in the codebase (partial). Missing: state machine enforcement.

---

### M2 — Budget Planner (OTB)

**Purpose**: allocate season capital across category × month.

**Core screen**: a grid of Category rows × Month columns. Cells contain:
- Planned Sales (input)
- Opening Stock (inherited from prior season close)
- Planned Closing Stock (input)
- On Order (auto-pulled from existing POs)
- OTB (derived, read-only)

**Features**:
- Total row per category summing month values
- Total column per month across categories
- % contribution columns for category mix
- Warn when total OTB exceeds season budget cap
- Reserve knob: "opening order %" sets how much of OTB can be committed in buy plan vs held for chase

**Output contract**: `season_otb` rows written; feeds Buy Planner's spending ceiling.

**Currently**: model exists, input UI exists, but no calculation logic, no reserve knob. P0.

---

### M3 — Assortment Builder (P1, placeholder in MVP)

**Purpose**: define the **shape** of the buy before quantities.

**View**: style list with:
- category, sub-category, price band, risk group
- target depth (editable)
- target store count (editable)
- projected OTB usage (auto-computed)
- demand analogue reference (if new style)

**Reconciliation**: live bar showing category OTB usage as the list grows. Red above 100%.

**MVP reality**: the pilot brand already has a buy file they bring. MVP can skip assortment design — we accept their style list as-is and validate it downstream. True assortment design is a P1 product.

---

### M4 — Store Strategy

**Purpose**: make the store × product demand map explicit.

**Sub-screens**:
1. **Grade matrix**: stores × categories heatmap. Grade editable. Auto-suggest from last season ROS with rent normalization.
2. **Cover target editor**: 4×4 grid (grade × risk group) with editable weeks of cover. Defaults from engine constants.
3. **Cluster management**: group stores for fallback demand averaging.
4. **Climate zone assignment**: filter eligibility for seasonal assortments.

**Outputs**: `store_product_grades`, `clusters`, `brand_settings.cover_targets`.

**Currently**: grades work. Cluster and climate zone exist in schema. Cover target editor doesn't exist as UI.

---

### M5 — Buy Planner

**Purpose**: turn the assortment list into concrete PO-ready quantities.

**Core screen**: style-level table with:
- style code, category, price band, risk group
- recommended depth (auto from demand × stores × cover)
- buyer override depth
- vendor, MOQ, expected delivery week
- OTB usage (row and category cumulative)
- Warning badges: MOQ below plan, OTB overrun, concentration risk

**Actions**:
- "Reconcile to OTB" button — scales depth proportionally to fit
- "Chase reserve" toggle — holds X% of planned buy as post-season-start chase
- CSV import from vendor quotes (common workflow)

**Currently**: `buy_plan` model exists. No API router. No UI. **P0 — the biggest gap in the product.**

---

### M6 — Ingestion

**Purpose**: bulk-load the inputs the decision system needs.

Already works. Five file types: SALES, STORE_GRADES, SIZE_GUIDE, BUY_FILE, GRN.

**MVP improvement**: add validation results surface — what was ingested, what was rejected, what was ambiguous. Currently errors are buried.

---

### M7 — Allocation Engine

**Purpose**: distribute received inventory to stores based on demand math.

Already built and over-built. See [../CLAUDE.md](../CLAUDE.md) for engine internals. Key MVP adjustments:

- **Simplify explanation payload**: `ai_reasoning` JSON is 20 fields. Merchandisers need 3 sentences. Add a `ai_reasoning_human` string derived from the JSON.
- **Hide advanced toggles**: cannibalization dampening, affinity multipliers, style DNA — keep on by default, don't expose as user controls
- **Health score — backend only**: don't surface to user in MVP. The score is a QA tool.

---

### M8 — Review & Approve

**Purpose**: let the merchandiser audit, override, and finalize.

Already works at line level. MVP additions:
- **Summary view**: totals by store, category, grade, risk group
- **Override reasons** captured structurally (dropdown + free text), not just free text
- **Export CSV** for WMS (already exists)
- **Post-approval lock**: once approved, session is immutable; changes require a new session

---

### M9 — Guided Workflow (Shell)

**Purpose**: bind modules into a single narrative a brand can complete in one sitting.

**UI**: persistent top bar showing "Step X of 6" with:
1. Season setup ✓
2. OTB entered ✓
3. Data ingested (sales, grades, size) ✓
4. Buy plan locked ✓
5. GRN → allocation generated ✓
6. Approved & exported

Each step gates the next. A brand can't skip to allocation without OTB and buy plan. This is **philosophical** — we are teaching the brand the workflow, not letting them cherry-pick tools.

**Currently**: each page is standalone. P0 to wire the shell.

---

## Data Models (Summary)

Full schema in [../CLAUDE.md](../CLAUDE.md). Planning-layer models:

```
Season (1) ──┬── SeasonOTB (N: category × month)
             ├── BuyPlan (1) ── BuyPlanLine (N: style)
             └── AllocationSession (N: one per GRN)
                                      │
                                      └── AllocationLine (N: store × SKU)

Brand (1) ──┬── Store (N) ── StoreProductGrade (N: per category)
            ├── Cluster (N)
            ├── SKU (N)
            ├── SizeGuide (N)
            ├── BrandSettings (1)
            └── GRN (N) ── GRNLine (N: per SKU)
```

Missing in implementation:
- `BuyPlanLine` has no API
- `Season → BuyPlan` linkage not enforced
- `BuyPlanLine → GRNLine` reference does not exist (GRN is disconnected from buy intent)

---

## Core Algorithms (High-Level)

### A1 — Demand Projection per (Store, SKU)

```python
def project_demand(store, sku, history, clusters, grade_map):
    # Tier 1
    if store_has_sku_history(store, sku, min_weeks=8):
        ros = stockout_corrected_ros(store, sku)
        return Demand(ros=ros, tier="STORE_HIST", confidence="HIGH")

    # Tier 2
    cluster = clusters.get(store.cluster_id)
    if cluster and cluster_has_sku_history(cluster, sku):
        ros = cluster_avg_ros(cluster, sku)
        return Demand(ros=ros, tier="CLUSTER", confidence="MEDIUM")

    # Tier 3
    grade = grade_map[(store.id, sku.category)]
    if grade_has_sku_history(grade, sku):
        ros = grade_avg_ros(grade, sku)
        return Demand(ros=ros, tier="GRADE", confidence="MEDIUM")

    # Tier 4
    analogues = style_dna_match(sku, top_n=5)
    if analogues:
        ros = weighted_avg_ros(analogues, store)
        return Demand(ros=ros, tier="STYLE_DNA", confidence="LOW")

    # Tier 5
    return Demand(ros=0, units=min_presentation_qty, tier="FLOOR", confidence="LOW")
```

### A2 — Store Prioritization

```python
def score_store(store, sku):
    ros_norm    = minmax_norm(store.ros_for_category[sku.category])
    grade_w     = grade_weight(store.grade_for(sku.category, sku.price_band))
    cover_inv   = 1.0 - minmax_norm(store.current_cover[sku.style])
    return 0.50 * ros_norm + 0.25 * grade_w + 0.25 * cover_inv
```

### A3 — Allocation Distribution

```python
def allocate(sku, available_units, eligible_stores, settings):
    strategy = detect_strategy(sku.risk_group, eligible_stores)

    if strategy == "EXPERIMENTAL":
        eligible_stores = top_n_by_score(eligible_stores, n=settings.experimental_max_stores)

    demands = {s.id: project_demand(s, sku).ros *
                     settings.cover_targets[sku.risk_group][s.grade]
               for s in eligible_stores}

    demands = apply_affinity(demands, eligible_stores, sku)
    demands = apply_cannibalization(demands, sku.story)

    total = sum(demands.values())
    if total > available_units:
        scale = available_units / total
        demands = {k: v * scale for k, v in demands.items()}

    demands = enforce_mva(demands, settings.min_presentation_qty)
    return split_across_sizes(demands, sku, size_curves)
```

### A4 — Risk Scoring

```python
def score_session(session):
    return {
        "coverage":         coverage_score(session),          # % of demand met
        "demand_alignment": alignment_score(session),         # recommended vs projected
        "balance":          variance_score(session),          # spread across grades
        "presentation":     presentation_score(session),      # min qty compliance
        "confidence":       confidence_mix_score(session),    # % high/med/low
        "verdict":          verdict_from_scores(...)          # SAFE/CAUTION/RISKY/CRITICAL
    }
```

---

## What Gets Built in MVP

The minimum to complete the planning loop end-to-end:

1. **Buy Plan API + UI** (new) — closes the biggest gap
2. **Guided workflow shell** (new) — binds modules
3. **OTB overrun warnings in Buy Planner** (new) — the coupling the spreadsheet can't do
4. **Simplified allocation explanation** (refactor existing) — auditability
5. **Structured override reasons** (refactor existing) — learning signal
6. **Summary review view** (new) — approval confidence

Everything else — assortment builder, OTB calculator, chase recommender, learning loop — is P1+. See [06](06_mvp_priorities.md) for the justification.
