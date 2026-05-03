# 03 — System Interdependency

The five decision layers are not a pipeline. They are a **constraint graph**. A change in any one propagates to every other. This is what makes pre-season planning structurally hard — and what makes Excel a bad tool for it.

---

## The Dependency Graph

```
         Budget (OTB)
           ↙    ↘
   Assortment ←→ Store Strategy
           ↘    ↙
           Buy Plan
              ↓
        Timing / Flow
              ↓
         Allocation
```

Every edge is a **mutual constraint**, not a one-way dependency.

---

## Coupling 1 — Budget ↔ Assortment

### The Arithmetic
```
OTB (cost) = Style Count × Avg Depth × Avg Cost
```

A category with ₹2Cr OTB, avg cost ₹400, target depth 200 → supports **250 styles**.

Change any variable and the constraint rebalances:
- Raise depth to 300 → style count drops to 167
- Raise avg cost to ₹500 (trade up) → style count drops to 200
- Raise OTB to ₹2.5Cr → style count rises to 312

### The Failure Mode
Brands set OTB first, then design assortment, and discover mid-plan that the math doesn't reconcile:
- "We need 400 styles for good width" — but budget supports 250 at target depth
- Resolution is usually: **cut depth**, which silently creates stockout risk nobody flagged

A good system surfaces this trade-off explicitly, at decision time.

---

## Coupling 2 — Assortment ↔ Store Strategy

### The Arithmetic
Not every style goes to every store.
- Store-group rules (premium styles only in A+ stores)
- Climate rules (heavy fabrics only in north)
- Grade minimums (experimental only in top 10 stores)

Effective store count per style ranges **10 → 162** in a typical brand.

### The Failure Mode
- Buy plan assumes 100 stores per style average
- Actual effective stores = 60 for half the assortment
- Depth math is off by 40% on those styles → either thin cover or excess inventory
- Discovery happens at allocation time, when OTB is already committed

---

## Coupling 3 — Assortment ↔ Buy Plan

### The Arithmetic
Assortment defines what is bought. Buy plan defines how deeply. The constraint:
```
Σ (Style depth × Unit cost) ≤ Category OTB
```

Plus vendor constraints:
- Each style must clear vendor MOQ
- Multi-style POs aggregate to meet MOQ (often 1000–3000 at vendor level)
- Fabric sharing across styles changes MOQ economics

### The Failure Mode
- Style list designed in Excel by a merchandiser
- Buy quantities assigned by a buyer 2 weeks later
- Vendor MOQ negotiations change quantities
- By the time PO is cut, assortment and buy have diverged by 10–20%
- OTB is re-reconciled after the fact, usually by dropping other styles

---

## Coupling 4 — Buy Plan ↔ Allocation

### The Arithmetic
Allocation can only distribute what was bought:
```
Σ (Store_s allocation_i) ≤ Available units_i for every SKU i
```

Pre-allocation reservations (e-com, ARS, key accounts) further reduce available:
```
Available = Units Received − E-com Reserved − ARS Reserved
```

### The Failure Mode
- Buy plan was sized for 100 stores but allocation has 162
- Warehouse reservations eat 15% no one planned for
- Result: A+ stores get thinner cover than intended; the plan quietly fails before allocation even runs

The causality is silent. A VP sees a "thin allocation to top stores" and blames allocation math, when the real error is two steps upstream in buy depth.

---

## Coupling 5 — Timing ↔ Everything

Timing is the sneakiest coupling because its effects appear late.

### Budget × Timing
- Monthly OTB splits assume a drop schedule
- If Drop 1 slips 3 weeks, March OTB is unspent, May OTB is double-stuffed
- Cash flow and markdown window both shift

### Assortment × Timing
- Story launches depend on all styles arriving together
- A 10-style "Festive Edit" launch with 6 styles delayed is a broken story
- Visual merchandising suffers disproportionately

### Buy × Timing
- Short lead time = less buy discipline (no time to reconcile)
- Long lead time = more commitment before signal

### Allocation × Timing
- Allocation run on partial GRN (only 60% of buy arrived) produces misleading store fills
- Late allocation on late GRN misses the full-price window

---

## The Core Claim — Why Excel Fails

Excel fails at pre-season planning not because the spreadsheets are messy, but because the **structural problem is not a ledger problem**. It is a **constrained optimization with uncertainty propagation** problem.

### What Excel Is
Excel is a ledger. Cells record values. Formulas compute derived values. It is excellent for recording decisions already made.

### What Pre-Season Planning Requires
Pre-season planning requires:
1. **Constraint propagation** — if OTB changes, depth must auto-reconcile
2. **Scenario simulation** — "what if I shift ₹50L from kurtis to dresses?"
3. **Demand modeling** — forward ROS projection from history, stockout-corrected
4. **Distribution math** — 162 stores × 3,000 SKUs = 486,000 cells per allocation run
5. **Uncertainty quantification** — confidence intervals, not point estimates
6. **Learning loop** — last season's residuals feeding this season's defaults
7. **Version integrity** — single source of truth, not 14 emailed copies

### The Specific Breakdowns

#### Breakdown 1 — No Constraint Propagation
A buyer adds 200 units to Style X in Sheet "Buy Plan". The OTB sheet doesn't update until someone manually reconciles. By the time reconciliation happens, 15 other changes have landed. The gap between intent and actual widens silently.

#### Breakdown 2 — No Simulation
VP asks: "If we push ₹1Cr more into dresses, where does it come from and what happens to kurti cover?" In Excel, this requires rebuilding the plan. Most brands don't — they make the decision without the simulation and discover the consequence 4 months later.

#### Breakdown 3 — No Forward Demand
Excel cells are filled in by humans. "We plan to sell 4,000 units of Style X" is a guess, not a model. There is no ROS-based forward projection. No stockout correction (if last season stocked out, the recorded sellthrough is suppressed — a naïve plan reads this as low demand and under-buys again).

#### Breakdown 4 — Distribution Done Separately
Allocation is done in a different Excel file (often by a different team), disconnected from the buy plan. The feedback loop "did we have enough to allocate well?" doesn't exist until after the season.

#### Breakdown 5 — No Explicit Uncertainty
An Excel plan says "2,000 units of Style X." It does not say "2,000 ± 500 with 65% confidence; P10 = 1,200, P90 = 2,800." A VP making a ₹100Cr bet deserves the distribution, not just the mean.

#### Breakdown 6 — Learning Gets Lost
Season N Excel plan and Season N actuals live in separate files. Residual analysis is manual and usually skipped under deadline pressure. The brand repeats last year's mistakes because last year's mistakes were never structurally recorded against this year's assumptions.

#### Breakdown 7 — Version Proliferation
`buy_plan_v3_FINAL.xlsx`, `buy_plan_v3_FINAL_USE_THIS.xlsx`, `buy_plan_v3_vendor_final.xlsx`. Different teams work off different versions. Reconciliation is manual and error-prone. Post-season audits often find decisions were executed off a version that was superseded the next day.

---

## What a Decision System Does Differently

A system — not a spreadsheet — resolves these by:

1. **Single data model**: one canonical version of OTB, assortment, buy, allocation. All views project from it.
2. **Automatic propagation**: change OTB → depth budgets recompute → vendor MOQ alerts fire → allocation projections update.
3. **Demand modeling as a service**: ROS-based, stockout-corrected, confidence-tiered. Not hand-entered cells.
4. **Simulation as a primitive**: what-if is a button, not a 3-day spreadsheet rebuild.
5. **Explicit uncertainty**: every projection has a confidence band and a demand source trail.
6. **Residuals captured**: every decision links to its outcome. Season N informs Season N+1 automatically.
7. **Versioning and audit**: every change is logged. Post-season: "who changed what, when, and why?"

---

## Where KYROS Stands on This

KYROS's allocation engine already does (5) and (6) partially — confidence tiers, reasoning trails, health scores. But:

- Budget ↔ assortment ↔ buy is **not coupled** (buy plan has no API, OTB is manual)
- Simulation exists for allocation only, not for buy or assortment
- Learning loop is not implemented
- Versioning exists at the DB level but not exposed

The P0 work is to build the **upstream coupling**, so that the existing downstream sophistication actually has valid inputs to operate on. See [05](05_kyros_mvp_design.md) for the product shape.
