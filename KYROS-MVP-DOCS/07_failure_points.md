# 07 — Failure Points

Where pre-season planning breaks in real retail companies. These failures are what Kyros must either prevent, detect, or gracefully handle. A system that doesn't know its failure modes designs around its best case — which is not the case it will encounter.

---

## Category A — Data Failures

### F-A1 — Missing `was_in_stock` Flag
**What happens**: sales history has units_sold per week but no in-stock indicator. Weeks where the item was out of stock record 0 sold, which naively lowers ROS.

**Consequence**: hero styles look mediocre. Next season's buy is under-sized on winners — the single most expensive silent error in retail.

**How Kyros handles it**:
- Flag absence of `was_in_stock` at ingestion time with severity WARNING
- Use heuristic: if a SKU has 0 sales for 2+ consecutive weeks surrounded by positive sales, infer stockout
- In the pilot data: this field is entirely missing; we infer from gap pattern

### F-A2 — No Weekly Granularity
**What happens**: sales are aggregated to month or season level.

**Consequence**: no seasonality signal, no mid-season stockout detection.

**How Kyros handles it**: synthetic week spreading — split totals across 8 synthetic weeks (see `processor.py:469-475`). This is a floor, not a solution; the brand must eventually provide weekly data.

### F-A3 — Stale Store Master
**What happens**: closed stores still marked active. Opened stores missing.

**Consequence**: allocation sends units to stores that cannot sell them; newly-opened high-potential stores get zero allocation.

**How Kyros handles it**:
- `is_active` flag required at ingestion
- Reconciliation report at session start: "X stores in master not in recent sales data — confirm they are active?"

### F-A4 — SKU Master Duplicates
**What happens**: same physical SKU has two codes (vendor SKU vs internal SKU).

**Consequence**: sales history splits across codes; ROS halved; demand under-estimated.

**How Kyros handles it**:
- Dedup detection on ingestion (same style_code + size + color + price)
- Raise for manual merge before proceeding

### F-A5 — Grade Assignments Are Political
**What happens**: store grades are influenced by franchise relationships, not ROS. A poorly-performing store owned by a major franchisee gets A+ grade anyway.

**Consequence**: allocation overfeeds underperforming stores; under-feeds grading-victim stores that actually sell.

**How Kyros handles it**:
- Show grade vs computed ROS-based grade side-by-side
- Flag divergence >2 grade levels
- Do not auto-override (politics win), but surface the discrepancy

---

## Category B — Planning Failures

### F-B1 — OTB Set Top-Down Without Category Sanity Check
**What happens**: "Growth target +10% → total OTB +10% → each category +10%."

**Consequence**: categories with falling demand get more budget; rising categories get less. Mix drifts away from reality.

**How Kyros handles it**:
- Show per-category growth implied by OTB delta
- Flag categories with >15% deviation from last-season contribution share
- Do not auto-correct (strategic pushes may justify the skew)

### F-B2 — Planned Sales Inflated to Justify Desired Buy
**What happens**: buyer wants to buy ₹2Cr of a category. Planner back-solves planned_sales to make OTB math support it.

**Consequence**: OTB becomes a rationalization, not a constraint. Discipline is theater.

**How Kyros handles it**:
- Show planned_sales vs last-actuals vs next-year growth benchmark
- Flag if planned_sales > last-actuals × 1.25 without documented strategic reason
- Track OTB changes in audit log

### F-B3 — On-Order Not Tracked
**What happens**: POs placed for ongoing categories (core replenishment) aren't reflected in on_order. OTB math reads low.

**Consequence**: planner computes more OTB available than actually is. Total commitment overshoots budget.

**How Kyros handles it**:
- On-order field is required in OTB; block OTB finalization if empty
- Integration with PO system (or CSV upload) to populate

### F-B4 — Last Season's Closing = This Season's Opening Assumption
**What happens**: planner assumes opening stock is "whatever didn't sell" without counting actual inventory.

**Consequence**: real opening stock is higher or lower than assumed; OTB over- or under-computed by that delta.

**How Kyros handles it**:
- Opening stock must tie back to a warehouse inventory count, not a computed residual
- Flag if opening stock > 30% of planned sales (likely carryover bloat)

---

## Category C — Buy Failures

### F-C1 — Vendor MOQ Forces Over-Buy
**What happens**: buyer wants 300 units of a test style. Vendor MOQ is 1000.

**Consequence**: either cancel the style, or buy 1000 — tripling the bet on an unproven idea.

**How Kyros handles it**:
- MOQ captured per style; system flags when style depth < MOQ
- Recommendation: "aggregate with similar styles under same fabric to reach MOQ" or "cut from plan"
- Does not silently allow 300-unit buy on a 1000 MOQ vendor

### F-C2 — Late Fabric Arrival
**What happens**: fabric delayed 3–4 weeks. POs can't be cut. Goods land 60% into full-price window.

**Consequence**: that style's full-price sell-through window collapses; markdown pressure immediate.

**How Kyros handles it**:
- Expected delivery week per buy plan line
- Flag styles with delivery > 30% into season
- Recommend cutting depth for late arrivals (less to markdown)

### F-C3 — Concentration Risk Ignored
**What happens**: 40% of category budget in 3 styles from 1 vendor.

**Consequence**: if that vendor slips or those styles flop, category is devastated.

**How Kyros handles it**:
- Concentration warnings: any style >10%, any vendor >25%, any fabric >30%
- Block approval of buy plan with >1 CRITICAL concentration without sign-off

### F-C4 — Test Style Budget Creep
**What happens**: "one more test won't hurt." By end of planning, 8% of budget is test styles.

**Consequence**: test styles have worst sellthrough; budget leaks into markdown.

**How Kyros handles it**:
- Test style allocation cap at category level (e.g. max 5% of category OTB)
- Warning when crossed

---

## Category D — Allocation Failures

### F-D1 — Fair-Share Default
**What happens**: in Excel, allocation defaults to "total units / store count = equal split."

**Consequence**: A+ stores get under-served, C stores get over-served. Typical 8–12% sellthrough loss.

**How Kyros handles it**: the engine never does fair-share — scoring is always demand-weighted. But the UI must educate the merchandiser that "equal split" is the wrong intuition.

### F-D2 — Size Curve Assumed Uniform
**What happens**: category size curve (e.g. 15% S, 30% M, 30% L, 20% XL, 5% XXL) applied to every store.

**Consequence**: southern stores stock-out on S/M, overstock on XL. Northern stores opposite.

**How Kyros handles it**:
- Store-specific size ratios if ≥26 weeks history
- Fallback to category curve
- Show which stores are using which curve in allocation review

### F-D3 — Allocation Run on Partial GRN
**What happens**: GRN partial (60% of PO received), allocation run anyway.

**Consequence**: top stores get lion's share of first tranche, second tranche has nothing left for them — order of arrival determines distribution.

**How Kyros handles it**:
- Warn if GRN units < PO units by >20%
- Option to "plan for full PO, allocate only received" (reserves future units by store)

### F-D4 — Override Reasons Unrecorded
**What happens**: planner overrides 40% of lines with "manual adjustment" as the only note.

**Consequence**: no learning signal — next season, we don't know which overrides were right.

**How Kyros handles it**:
- Structured override reason dropdown
- Override audit report at end of season (was the override closer to actual than AI rec?)

### F-D5 — Planner Only Reviews Top 20 Lines
**What happens**: planner scans top 20 lines, approves, ignores the other 5,000.

**Consequence**: systematic errors in the tail go undetected until customer complaints or end-of-season markdown.

**How Kyros handles it**:
- Exception-first review: surface lines with low confidence, unusual cover, or grade violations
- "Approve all others" still requires explicit action, not timeout

---

## Category E — Process Failures

### F-E1 — Plan Made By Team A, Execution By Team B
**What happens**: merchandising team makes the plan. Buying team cuts POs. Warehouse team allocates. Each has their own spreadsheet, each makes independent adjustments.

**Consequence**: the plan that exits planning is not the plan that hits stores.

**How Kyros handles it**:
- Single data model across modules
- State transitions with required sign-offs
- Audit log shows which role changed which field when

### F-E2 — No Post-Season Residual Review
**What happens**: season ends. Everyone moves on to next season. Last season's plan vs actuals is never compared.

**Consequence**: same assumptions, same errors, forever.

**How Kyros handles it** (post-MVP):
- Automatic residual report at season close
- Variance by category, store, style
- Feed back into next season's ROS baselines

### F-E3 — Last-Minute VP Changes
**What happens**: VP looks at plan day before PO cut, changes category mix by 20%.

**Consequence**: plan loses coherence; all downstream math still reflects old mix; reconciliation is manual and error-prone.

**How Kyros handles it**:
- Changes propagate automatically across OTB → assortment → buy
- "Draft vs Committed" plan states; only committed goes to PO
- Diff view: "what changed since last commit?"

### F-E4 — Excel Version Drift
**What happens**: `plan_v3_FINAL.xlsx`, `plan_v3_FINAL_USE_THIS.xlsx`, `plan_v3_vendor.xlsx` circulating.

**Consequence**: execution happens against a version that may be stale.

**How Kyros handles it**: single source of truth in Postgres. No "files" to email. The URL is the plan.

---

## Category F — Assumption Failures

### F-F1 — "Last Season = This Season"
**What happens**: ROS baselines carry forward without adjustment.

**Consequence**: ignores macro shifts, competitor launches, weather variance, festival calendar changes.

**How Kyros handles it**:
- Growth factor per category (editable)
- Flag categories where last-season had unusual events (mark in data)
- In MVP: document the assumption; don't attempt to model macro yet

### F-F2 — "New Stores Behave Like Cluster Average"
**What happens**: new store assumed to sell at cluster ROS.

**Consequence**: new stores typically outperform cluster first 8 weeks (novelty) then regress. Both under- and over-allocation common.

**How Kyros handles it**:
- Mark stores with opening_date < 90 days as NEW
- Use different fallback for new stores (grade-level average × conservative multiplier)
- Don't use new-store data as signal until 8+ weeks

### F-F3 — "Style DNA Predicts Like-for-Like"
**What happens**: new style's demand projected from analogue styles.

**Consequence**: sometimes right, often off by 30–50%. Style DNA has ceiling accuracy.

**How Kyros handles it**:
- Confidence tag = LOW on all Tier 4 demands
- Cap Tier 4 allocation at conservative depth
- Concentrate in top 5 stores (don't spread a guess widely)

---

## How Kyros Should Communicate Failures

The product's UX responsibility is to **make these failures loud**, not to silently work around them.

- Severity levels: **BLOCKER** (stop progression), **WARNING** (proceed with acknowledgment), **INFO** (FYI)
- Every warning has a suggested action
- Every blocker has a clear path to resolution
- Nothing silently auto-corrects what the planner should decide

A system that silently fixes bad data is a system that nobody trusts — the planner has no mental model of what actually happened.
