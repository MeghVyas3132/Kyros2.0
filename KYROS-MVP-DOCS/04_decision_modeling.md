# 04 — Decision Modeling (Kyros View)

The system, reduced to **inputs → transformations → outputs**. This is the schema of the decision brain. Everything in the product serves this model.

---

## Inputs

### A. Historical Sales
| Field | Granularity | Purpose |
|-------|-------------|---------|
| `store_id` | Per store | Compute store-level ROS |
| `sku_id` (→ style, size, category) | Per SKU | Roll up to style and category |
| `week_start_date` | Weekly | Time series for seasonality, stockout detection |
| `units_sold` | Per row | The raw signal |
| `units_realized_revenue` | Per row | Margin and markdown history |
| `was_in_stock` | Per row | Stockout correction — critical |

**Quality requirement**: minimum 26 weeks of history for reliable ROS; 52 weeks preferred for seasonality. Stockout flag is the single most valuable field — without it, winners look like losers.

### B. Store Data
| Field | Purpose |
|-------|---------|
| `store_code`, `store_name`, `city`, `region` | Master |
| `cluster_id` | Grouping for cluster-average fallback |
| `climate_zone` | Filter for seasonal assortments |
| `store_grade` (per category, per price band) | Drives cover targets and allocation weight |
| `is_active`, `opening_date` | Newness flag; filters dead stores |
| `sqft`, `rent_per_month` | Productivity normalization |

### C. Category & SKU Master
| Field | Purpose |
|-------|---------|
| `category`, `sub_category`, `department` | Aggregation levels |
| `price_band` | Price architecture tracking |
| `fabric`, `construction` | Climate eligibility, affinity |
| `style_risk_group` (PROVEN / CONFIDENT / EXPERIMENTAL) | Strategy routing |
| `store_group_rule` | Which grade min + zone the style can go to |
| `story`, `sub_story` | Grouping for cannibalization + VM |

### D. Size Curves
| Granularity | Source |
|-------------|--------|
| Category default | Brand-level size guide |
| Store override | Store's historical size sellthrough |
| Store × category × price band | Deepest granularity (requires 26+ weeks history) |

### E. Budgets
| Field | Purpose |
|-------|---------|
| `season_id`, `category`, `month` | Time & product bucket |
| `planned_sales` | Revenue bet |
| `planned_closing_stock`, `opening_stock` | Inventory balance |
| `on_order` | Vendor commitments |
| `otb_value` | Derived: OTB = planned_sales + closing − opening − on_order |

### F. Brand Settings
| Setting | Default | Purpose |
|---------|---------|---------|
| `min_presentation_qty` | 2 | Allocation floor per store per SKU |
| `opening_order_pct` | 0.65 | % of season OTB committed pre-season |
| `experimental_max_stores` | 10 | Concentration rule |
| `cover_targets[risk_group][grade]` | See engine constants | Weeks of cover |
| `grade_multipliers` | A+:1.1, A:1.0, B:0.9, C:0.75 | Demand scaling |
| `chase_threshold_ros` | 1.5× projection | Auto-flag for replenishment |

---

## Transformations

### T1 — Demand Estimation

Four-tier fallback, per (store × SKU):

```
TIER 1: Store-specific ROS for this SKU (if ≥8 weeks of history)
TIER 2: Cluster-average ROS for this SKU (if cluster has ≥3 stores)
TIER 3: Grade-average ROS for this SKU (always available if category history exists)
TIER 4: Style DNA — top 5 analogous SKUs by fabric/price/risk/color similarity
TIER 5: min_presentation_qty (last resort)
```

Each tier carries a confidence tag: HIGH / MEDIUM / LOW.

### T2 — Stockout Correction

For each (store, SKU, week):
```
If was_in_stock = False AND units_sold = 0:
    Exclude week from ROS denominator
If stockout pattern is mid-season (not end-of-life):
    Re-estimate ROS from pre-stockout weeks only
```

Without this, hero styles look mediocre and get under-bought next season — the single most common silent failure.

### T3 — ROS Normalization

```
weekly_ros = units_sold_in_stock_weeks / count_of_in_stock_weeks
annualized_ros = weekly_ros × 52 (for budget math)
category_ros = Σ SKU ros weighted by active weeks
```

### T4 — Risk Scoring

Per style, compute:
- **Stockout probability**: P(demand > buy_qty) given ROS distribution + cover target
- **Overstock probability**: P(demand < 0.6 × buy_qty) — markdown risk
- **Confidence tier**: function of (history depth × store coverage × demand variance)

### T5 — Store Prioritization

For each SKU × eligible stores:
```
score = 0.50 × normalized_ros
      + 0.25 × grade_weight
      + 0.25 × current_cover_inverse
```

Strategy selection:
- **PROVEN** → distribute to all eligible stores weighted by score
- **CONFIDENT** → top 60% of eligible stores
- **EXPERIMENTAL** → top 5–10 stores (configurable)

### T6 — Demand to Allocation

```
store_demand_i = ROS_i × cover_target[risk, grade_i]
                × affinity_multiplier[store, SKU]
                × (1 − cannibalization_damping[story])

If Σ store_demand > available_units:
    scale_factor = available / Σ demand
    allocated_i = round(store_demand_i × scale_factor)
    Enforce MVQ floor and min presentation
```

### T7 — Size Split

Per store × style:
```
If store has ≥26 weeks of size-level history:
    Use store-specific size curve
Else:
    Use category-default size curve (brand size guide)
Preserve min size coverage (no 0 for core sizes)
```

### T8 — Constraints Layer

At each stage, enforce:
- OTB ceiling per category × month (buy plan can't exceed)
- Vendor MOQ floor (styles below MOQ must aggregate or cut)
- Store group rules (premium styles → A+/A only)
- Climate eligibility
- Grade minimums
- Reservation constraints (e-com, ARS)

---

## Outputs

### O1 — Buy Plan

Per style:
| Field | Example |
|-------|---------|
| `style_code` | K-047 |
| `category` | Kurtis |
| `price_band` | ₹1,500–2,000 |
| `risk_group` | PROVEN |
| `planned_units` | 500 |
| `planned_cost` | ₹200,000 |
| `target_stores` | 42 (A+/A in compatible climate) |
| `target_weeks_cover` | 6 |
| `vendor_id`, `expected_delivery_week` | V-012, Week 2 |
| `demand_confidence` | HIGH (based on 34 weeks history on analogue K-044) |
| `otb_usage_pct` | 5% of kurti OTB |

### O2 — Allocation Plan

Per (store × SKU × session):
| Field | Example |
|-------|---------|
| `store_id`, `sku_id`, `session_id` | S-012, K-047-M, ALC-88 |
| `ai_recommended_qty` | 21 |
| `ai_confidence` | HIGH |
| `ai_reasoning` (JSONB) | Demand tier, ROS source, stockout correction, affinity, cover outcome |
| `ai_projections` | Expected sellthrough, expected stockout week |
| `final_qty` | 21 (or overridden) |
| `was_overridden`, `override_reason` | — |

### O3 — Risk Indicators

Session-level:
- **Coverage score** (0–100): % of demand met
- **Demand alignment**: how well recommendations match projected demand curve
- **Balance**: variance of cover weeks across top vs bottom stores (should be small)
- **Presentation**: % of store × SKU pairs meeting min presentation
- **Confidence mix**: % of lines at HIGH / MEDIUM / LOW
- **Verdict**: SAFE / CAUTION / RISKY / CRITICAL

Plan-level (across season):
- **OTB overrun flags** by category × month
- **Concentration flags** (single-style or single-vendor risk)
- **Depth gaps** (A+ stores under target cover on hero styles)

### O4 — Reactive Levers

Generated during in-season (post-MVP but modeled now):
- **Chase candidates**: styles running at >1.5× projected ROS with available fabric
- **Markdown candidates**: styles at <0.5× projection by week 8
- **Transfer candidates**: stock at C stores that would sell at A stores
- **Replenishment triggers**: core styles below 4-week cover

---

## The End-to-End View

```
Historical Sales  ─┐
Store Master      ─┼──► Demand Estimator ──┐
SKU Master        ─┤                        │
Size Curves       ─┘                        │
                                            ▼
                                    Store Demand Matrix
                                   (store × SKU × units)
                                            │
Budgets ──────────► OTB Planner ────────────┤
                                            ▼
                                     Buy Plan (styles × depth)
                                            │
                                            ▼
                                     Vendor POs / GRN
                                            │
                                            ▼
                                   Allocation Engine
                                            │
                                            ▼
                              Store × SKU Allocation Lines
                                            │
                                            ▼
                                  Review → Approve → Export
                                            │
                                            ▼
                                  In-Season Actuals
                                            │
                                            ▼
                              Residual Analysis → Next Season Defaults
```

Everything in the product is a view over this graph. Every UI, every API, every report projects from this model.

---

## Data Quality — The Often-Ignored Layer

The model's outputs are only as good as inputs. Key quality gates:

| Input | Quality Check |
|-------|---------------|
| Sales history | ≥26 weeks, `was_in_stock` populated, week granularity preserved |
| Store master | No dead stores marked active, grades refreshed within 90 days |
| SKU master | No duplicates across vendor codes, risk group assigned |
| Size guide | Coverage for every active (category × price band), no zero ratios on core sizes |
| OTB | All months populated, on-order reconciled with vendor, cost basis consistent |

A plan computed on bad inputs is a confidently-wrong plan. The system should refuse to proceed past data-quality thresholds rather than silently produce garbage.
