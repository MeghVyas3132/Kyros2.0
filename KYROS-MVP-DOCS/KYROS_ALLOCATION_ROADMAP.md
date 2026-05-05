# Kyros Allocation Engine — Product Roadmap
### From Rule-Based MVP to VP-Approvable Intelligence

**Last Updated:** March 2026  
**Scope:** Allocation Engine (Phase 1 of Kyros Platform)  
**Horizon:** 6 months post-pilot launch

---

## The North Star

A VP of Merchandising at a 100–500 store Indian fashion brand opens Kyros on the first day of season allocation. She looks at the output for 10 minutes. She approves it.

Not because she was told to trust it. Not because she ran out of time to check it herself. Because the numbers match her intuition on the stores she knows well, the system surfaces one insight she hadn't thought of, and every number has a clear explanation she can defend to her team.

That is the bar. This document is the plan to get there.

---

## Current State vs. Target State — Master Comparison

| Dimension | What Exists Today | What We Need |
|-----------|------------------|--------------|
| **Demand estimation** | Raw historical average ROS | Stockout-corrected true demand |
| **New style handling** | Minimum presentation qty (2 units) | Style DNA matching to similar historical styles |
| **Store differentiation** | Grade-based (A+/A/B/C) | Behaviour-profiled (affinity, velocity archetype, size curve) |
| **Allocation framing** | Units-based | Cover-day based (weeks of cover at opening) |
| **Story awareness** | Informational only | Cannibalization-adjusted per story |
| **Size allocation** | Brand-level size guide | Store-specific size curves |
| **Explainability** | ROS source, scale factor | Full reasoning chain per allocation line |
| **Confidence signals** | HIGH / MEDIUM / LOW | Grounded confidence with specific source attribution |
| **In-season reaction** | None | Week-1 sell-through triggers |
| **VP trust** | Needs significant review | Approvable on first look |

---

## Part 1 — The Honest Assessment of Today

### What Is Working

The foundation is solid. The plumbing is correct.

- Store group rules are enforced correctly (A+ Only, A+ & A, All Stores etc.)
- ARS and ECOM reservations are properly deducted from available inventory
- Inventory cap exists — total allocated per SKU cannot exceed available units
- Confidence scoring exists (HIGH / MEDIUM / LOW)
- Explainability panel renders per allocation line
- Approval and CSV export flow works end to end
- The system processes 3,536 styles × 162 stores in under 2 minutes

### What Is Broken or Weak

**The demand signal is unreliable.**  
Raw historical ROS is used without any correction for stockouts. Stores that sold out in week 3 of SS25 show low ROS because they had no inventory to sell for 17 weeks. The engine interprets this as low demand and under-allocates them in SS26. The opposite of the correct behaviour.

**New styles have no real forecast.**  
442 styles in the SS26 buy file. A meaningful portion are new designs with no SS25 history. Today they all get minimum presentation quantity — a flat default that ignores fabric, category, price band, and everything else that would inform a sensible forecast.

**All stores of the same grade are treated identically.**  
An A-grade store in Indiranagar Bangalore and an A-grade store in Lucknow receive identical base allocations. They almost certainly have different category preferences, size distributions, and velocity profiles. The grade is a revenue proxy, not a behaviour descriptor.

**Size allocation is a brand-level average.**  
The size guide says "M is 30% of Kurta volume." This is an average across all stores. Stores in south Bangalore genuinely skew S/M. Stores in UP genuinely skew L/XL/2XL. Sending the same size ratio to all stores guarantees leftover stock in the wrong sizes everywhere.

**There is no story-level thinking.**  
When 4 colourways of the same Dola Silk kurta go to the same store, they compete with each other on the floor. The engine treats them as independent, which over-allocates the story as a whole at that store.

**The explainability is mechanical, not narrative.**  
Today the panel shows numbers — ROS value, scale factor, grade. It does not tell a story. A VP cannot look at it and understand why one store got 14 units and another got 8.

---

## Part 2 — The Roadmap

### Phase 0 — Foundations (Current Sprint, 2 Weeks)
*Already in progress. Complete before any pilots.*

**Goal:** Make what exists correct and stable before building on top of it.

| Item | Status | Priority |
|------|--------|----------|
| Inventory cap — total per SKU = available qty | ✅ Done | — |
| Season linkage for synthetic GRN | Pending confirmation | P0 |
| Size curve wired into engine | Pending confirmation | P0 |
| Ingestion performance (281K rows in <90 sec) | In progress | P0 |
| Celery auto-restart and retry policy | Done | — |
| Progress bar during upload | In progress | P1 |

**Exit criteria:** Two pilot files upload in under 2 minutes. Allocation runs. Total allocated per SKU equals available. CSV export downloads correctly. No errors in production logs.

---

### Phase 1 — Trust Foundation (Weeks 3–6)
*The minimum to clear the VP trust barrier at a live pilot.*

**Goal:** Make the output feel like it understands the brand's business.

---

#### 1.1 — Lost Sales Correction

**What it is:**  
Detect when a store stocked out mid-season and correct the ROS upward to estimate true demand rather than observed sales.

**Why it matters:**  
This is the single highest-ROI change in the entire roadmap. Every brand's best stores stocked out in SS25. Those stores are currently being penalised by the engine for having "low ROS." Lost sales correction fixes this and produces immediately visible changes in allocation for premium stores.

**What the VP sees:**  
> *"100 FT Indiranagar stocked out in week 4 of SS25 across 12 Kurta styles. Estimated lost revenue: ₹3.2 lakh. Opening allocation corrected upward to account for suppressed sell-through."*

This statement, surfaced in a dashboard callout before the allocation review screen, will stop a VP in her tracks. Nothing builds credibility faster than quantifying losses she already suspected but never had data to prove.

**What changes in the output:**  
- A+ and A stores with SS25 stockouts receive 20–40% more units than the uncorrected engine recommends
- Confidence score for those lines changes from LOW to MEDIUM or HIGH
- The explainability panel shows "stockout-corrected demand" as the source

**Complexity:** Medium. Requires knowing end-of-week inventory levels from SS25, which should exist in the sales data if we capture it during ingestion.

---

#### 1.2 — Cover-Day Allocation Framing

**What it is:**  
Replace units-based allocation targets with cover-day targets. Instead of "how many units should this store get," ask "how many weeks of cover should this store open with."

**Why it matters:**  
Every VP thinks in weeks of cover. It is the natural unit of her mental model. When you show her "6 weeks of cover for A+ stores, 4 weeks for A stores," she immediately understands and can challenge it if she disagrees. When you show her "14 units," she has to do mental maths to evaluate it.

**Cover targets by grade and style risk:**

| Style Risk | A+ | A | B | C |
|-----------|----|----|----|----|
| PROVEN | 7 weeks | 5 weeks | 4 weeks | 3 weeks |
| CONFIDENT | 6 weeks | 5 weeks | 3 weeks | 2 weeks |
| EXPERIMENTAL | 4 weeks | 3 weeks | 2 weeks | 0 (excluded) |

**What changes in the output:**  
The recommended qty column label changes to show "X weeks cover" alongside the unit count. The explainability panel shows the cover target and the ROS that produced it. The VP can change the cover target globally (a settings input) and see the allocation recalculate instantly.

**Complexity:** Low. This is a reframing of the existing calculation, not a new algorithm.

---

#### 1.3 — Store-Specific Size Curves

**What it is:**  
Calculate size distribution from SS25 actual sales per store and product category, rather than using the brand-level size guide for all stores.

**Why it matters:**  
Size is where most brands bleed inventory at end-of-season. They have too many XS in Mumbai and too many XL in Lucknow. A system that sends the right size mix to each store is immediately, visibly valuable — she can see it in the allocation CSV without needing any explanation.

**How it works:**  
For each store × product category, calculate the actual sell-through by size from SS25 data. Normalise to percentages. Use this as the size curve for that store in SS26. Fall back to the brand size guide only if insufficient history exists (fewer than 50 units sold in that category at that store last season).

**What changes in the output:**  
Size split in the allocation line reflects the store's actual historical preference, not the brand average. Stores in south India get more S/M. Stores in north/central India get more L/XL/2XL.

**Complexity:** Low-Medium. The data exists in SS25 sales history. It's a GROUP BY query per store × category × size.

---

### Phase 2 — Intelligence Layer (Weeks 7–10)
*The layer that makes the output feel smart, not just correct.*

**Goal:** Surface insights the VP didn't already know. Make the system feel like it has studied her business.

---

#### 2.1 — Style DNA Matching

**What it is:**  
For every new style in the SS26 buy file, find the most similar historical styles based on a feature vector (fabric, category, construction, price band, store group rule, silhouette) and use their corrected ROS as the demand prior.

**Why it matters:**  
Every new style currently gets minimum presentation quantity. After this change, a new Cotton Flex Printed Kurta in the Rs 1,400 price band targeted at All Stores gets a forecast derived from the 5 most similar styles from SS25. The numbers are immediately more credible because they're grounded in actual performance of comparable styles.

**What the VP sees in explainability:**  
> *"No SS25 history for CWS6KU61728A. Matched to 5 similar Cotton Flex Printed Kurtas from SS25 (avg similarity 91%). Blended ROS: 2.4 units/week at A+ stores. Best match: CWS5KU61066A (94% similar, 2.6 units/week SS25)."*

She will immediately look up CWS5KU61066A and either confirm or challenge. Either reaction means she is engaged with the output, which is what you want.

**Complexity:** Medium. Requires building a style feature vector and a similarity index. No machine learning needed — weighted cosine similarity on a handful of categorical and continuous features is sufficient.

---

#### 2.2 — Store Behaviour Profiling

**What it is:**  
Build a behavioural profile for each store from SS25 sales history that captures: category affinity (does this store over-index on Kurta vs. Pant?), fabric affinity (does it over-index on premium fabrics?), price band sweet spot, size distribution, and velocity archetype (Fast Fashion, Steady Performer, Late Bloomer, Premium Seeker).

**Why it matters:**  
Grade tells you revenue. Profile tells you behaviour. Two A-grade stores with different profiles should receive different assortments. A system that knows Nexus Shantiniketan over-indexes on Modal Chanderi at 1.4x brand average and adjusts accordingly is a system that has studied the brand.

**The archetypes:**

| Archetype | Description | Allocation implication |
|-----------|-------------|----------------------|
| Fast Fashion | High week-1 velocity, sells out early | Higher opening qty, smaller ARS reserve |
| Steady Performer | Consistent velocity across season | Standard cover targets |
| Late Bloomer | Slow start, picks up mid-season | Lower opening qty, larger ARS reserve |
| Premium Seeker | Over-indexes on higher price bands | Bias toward premium fabrics and embroidery |
| Value Hunter | Over-indexes on lower price bands | Bias toward Cotton and Rayon basics |

**What changes in the output:**  
Base allocation is adjusted upward or downward based on store-level affinity for the style's category and fabric. Each adjustment is visible in the explainability panel with the affinity score and historical basis.

**Complexity:** Medium. Profiles are built once after SS25 ingestion using GROUP BY queries and stored as JSON in the stores table. They do not require real-time computation.

---

#### 2.3 — Cannibalization Detection Within Stories

**What it is:**  
When multiple styles within the same story (e.g., 4 colourways of Desert Storm Printed in the same season) are allocated to the same store, reduce each style's allocation to account for in-store competition.

**Why it matters:**  
A store has finite floor space and finite customers. Sending 4 colourways at full allocation means each one will sell at roughly 60% of its standalone rate. A system that knows this and allocates accordingly produces better sell-through and less end-of-season residual.

**How the reduction works:**  
Within a story, styles are ranked by expected demand. The hero style (highest demand) keeps its full allocation. Each subsequent colourway in the same fabric × construction group is reduced by a cannibalization factor. The factor is steeper for same-fabric same-construction (0.65) than for same-story different-fabric (0.88).

**What the VP sees:**  
> *"CWS6KS11135B (Desert Storm, colour B) reduced from 18 to 12 units at 100 FT Indiranagar. Reason: 3 other Desert Storm Printed colourways allocated to this store. Cannibalization factor applied: 0.65."*

**Complexity:** Low-Medium. The story and sub-story fields already exist on SKUs. This is a post-processing step after base allocations are calculated.

---

### Phase 3 — The Explainability Product (Weeks 11–12)
*The layer that makes approvals possible.*

**Goal:** Every allocation line tells a complete story. Zero black boxes.

---

#### 3.1 — Full Reasoning Chain in Explainability Panel

The explainability panel needs to show the complete chain of logic for every allocation line in plain English. Not just numbers — a narrative.

**Current panel:**
```
ROS: 2.4    Source: store_historical    Confidence: HIGH
Scale factor: 0.87    Grade: A+    Multiplier: 1.25
```

**Target panel:**
```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STORE:  100 FT INDIRANAGAR BANGALORE  (A+ grade, Kurta)
STYLE:  CWS6KU61728A — Cotton Flex Printed Kurta

DEMAND BASIS
  Source:         SS25 store history (stockout-corrected)
  Raw ROS:        2.1 units/week (observed)
  Corrected ROS:  2.6 units/week (stocked out week 4, SS25)
  Cover target:   6 weeks (A+ store, CONFIDENT style)
  Base demand:    2.6 × 6 = 15.6 → 16 units

STORE ADJUSTMENTS
  Cotton Flex affinity at this store: 1.3x brand avg  → +3 units
  Cannibalization (4 colourways, same story):         → -3 units
  Adjusted demand:  16 units

INVENTORY CAP
  Total demand across all stores: 2,847 units
  Available for first allocation:  2,480 units
  Scale factor applied: 0.87
  Final qty: 16 × 0.87 = 13.9 → 14 units

SIZE SPLIT (store-specific curve)
  XS: 1  S: 3  M: 4  L: 4  XL: 2  = 14 units

CONFIDENCE: HIGH  (store history found, stockout-corrected)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**Complexity:** Low. This is a UI change that assembles data already stored in `ai_projections` JSONB. The data exists; the presentation does not.

---

#### 3.2 — Season-Level Dashboard Callouts

Before the allocation review table, show a summary dashboard with 4–6 insight cards:

| Card | Content |
|------|---------|
| Lost Revenue Recovered | "SS25 stockouts suppressed ₹X lakh in sales. SS26 allocation corrected for 23 stores." |
| New Style Coverage | "147 new styles matched to SS25 analogues. 12 styles with low confidence — review recommended." |
| Story Concentration Risk | "3 stories have 20+ styles each. Cannibalization adjustments applied." |
| Size Correction Applied | "34 stores received custom size curves. Most affected: UP stores (more L/XL) and KAR stores (more S/M)." |
| Under-covered Stores | "8 B-grade stores receiving fewer than 3 weeks cover due to inventory constraints." |

These cards are the VP's first impression of the allocation. They set the frame before she looks at a single line item.

**Complexity:** Low. All of these numbers are byproducts of the allocation run and can be aggregated into a summary object stored alongside the allocation record.

---

### Phase 4 — In-Season Intelligence (Weeks 13–20)
*Only begins after the first full season of data runs through Kyros.*

**Goal:** Close the loop between opening allocation and in-season performance. Make Kyros indispensable throughout the season, not just at opening.

---

#### 4.1 — Week-1 Sell-Through Triggers

Once stores begin selling, week-1 sell-through rate is the single most predictive signal for full-season performance. A style selling 35%+ in week 1 will almost certainly sell out. A style at 5% in week 1 is headed for a markdown.

**Triggers to implement:**

| Signal | Threshold | Action |
|--------|-----------|--------|
| High velocity | Week-1 sell-through > 35% | Flag for ARS replenishment. Alert merchandiser. |
| Very high velocity | Week-1 sell-through > 50% | Urgent replenishment. Flag for buy top-up. |
| Low velocity | Week-1 sell-through < 8% | Flag for redistribution to higher-performing stores. |
| Very low velocity | Week-1 sell-through < 4% | Markdown recommendation. Redistribute immediately. |
| Size imbalance | One size at 0% sell-through while others are >30% | Size rebalancing recommendation. |

**What the VP sees:**  
A notification feed in the Kyros dashboard, updated weekly, showing the styles that need attention and the recommended action. She does not need to pull reports — the system comes to her.

**Complexity:** High. Requires weekly sales data ingestion (not just season-opening), a trigger evaluation engine, and a notification system. This is a meaningfully larger scope than the allocation engine.

---

#### 4.2 — Inter-Store Transfer Recommendations

Based on sell-through performance in weeks 2–4, recommend transferring inventory from under-performing stores to over-performing ones before the mid-season markdown window.

This is a separate product feature but builds directly on the allocation engine's store behaviour profiles and demand estimates. The stores that were allocated correctly at opening will still have residual from cancelled sales. The recommendation engine matches surplus to deficit.

**Complexity:** High. Out of scope for MVP. Included for roadmap completeness.

---

## Part 3 — Competitive Position

### Where Increff Is Stronger Today

| Dimension | Increff | Kyros After Phase 2 |
|-----------|---------|---------------------|
| Stockout correction | Yes | Yes (Phase 1) |
| Cover-day framing | Yes | Yes (Phase 1) |
| Style matching | Basic | Richer feature set |
| Store clustering | Yes (2+ seasons) | Profiling without full clustering |
| Explainability | Minimal | Full reasoning chain |

### Where Kyros Will Be Stronger After Phase 2

| Dimension | Increff | Kyros |
|-----------|---------|-------|
| Explainability | Black box output | Full reasoning chain, auditable |
| Narrative per line | None | Plain English explanation |
| VP-facing dashboard | Data tables | Insight cards + callouts |
| Cannibalization detection | Not surfaced to user | Visible in explainability |
| Positioning | Calculator | Thinking partner |

**The honest truth about Increff:** Their core algorithm is strong. You are not going to out-algorithm them in 6 months. What you can do is out-communicate them. Their output is a spreadsheet of numbers with no explanation. Yours will be a reasoned recommendation with a complete audit trail.

For a VP who needs to defend her allocation decisions to her MD, that audit trail is worth more than a marginally better algorithm.

---

## Part 4 — What We Are Not Building (And Why)

| Feature | Why We're Not Building It |
|---------|--------------------------|
| Store clustering (k-means) | Needs 2 seasons of data. Profiles achieve 80% of the value with 1 season. |
| Google Trends / external signals | Too noisy without significant validation infrastructure. Risk of false confidence. |
| Price optimisation | Different product. Different buyer. Different sales cycle. Not Phase 1. |
| Buy planning | Upstream of allocation. Different problem. Different stakeholder. Phase 3 or 4. |
| Replenishment engine (full) | Needs weekly data feeds from brand ERP. Complex integration. Post-pilot. |
| Transfer recommendations | Requires in-season data. Phase 4. |
| Markdown optimisation | Requires pricing authority from brand. Significant change management. Future. |

---

## Part 5 — Build Sequencing Summary

```
TODAY          WEEK 4         WEEK 8         WEEK 12        WEEK 20
  │               │               │               │               │
  ▼               ▼               ▼               ▼               ▼

Phase 0        Phase 1        Phase 2        Phase 3        Phase 4
Foundations    Trust          Intelligence   Explainability  In-Season
               Foundation     Layer          Product

- Fix cap      - Lost sales   - Style DNA    - Full panel    - Week-1
- Season ID      correction     matching       narrative       triggers
- Size curve   - Cover-day    - Store        - Dashboard     - Transfer
  wired          framing        profiling      callouts        recs
- Ingest       - Store-level  - Canniba-
  performance    size curves    lization

              ─────────────────────────────────────────────────────
              PILOT LAUNCH                                   
              Target: 2–3 paying pilots by end of Phase 1   
```

---

## Part 6 — Pilot Conversion Strategy

The roadmap above is the technical plan. But the real question is: what does a pilot need to see at each phase to convert to a paying contract?

**At Phase 1 launch (Week 6):**  
Show the lost revenue callout first. Before she looks at a single allocation line. "Your best 8 stores stocked out last season. Here is the estimated lost revenue. Here is how we've corrected for it in SS26." If that number resonates — and it will, because she already knows those stores ran dry — you have her attention for everything that follows.

**At Phase 2 launch (Week 10):**  
Show her a new style with a DNA-matched forecast and tell her which historical style it's based on. Ask her if she agrees with the match. She will engage. She will probably disagree on one and agree on four. That disagreement is a product conversation, not a rejection — it means she's using the system seriously.

**At Phase 3 launch (Week 12):**  
Give her the full explainability panel and ask her to find a line she disagrees with. Then ask her to use the override function and note why she overrode it. Those override reasons are gold — they tell you exactly what the model is still missing.

**The metric that matters for conversion:**  
Override rate. If she overrides fewer than 15% of lines in the second pilot run compared to the first, the model is earning trust. That trend line is your closing argument for a paid contract.

---

## Appendix — Intelligence Layer Components Summary

| Component | Phase | Complexity | VP Impact |
|-----------|-------|------------|-----------|
| Stockout / lost sales correction | 1 | Medium | ⭐⭐⭐⭐⭐ |
| Cover-day framing | 1 | Low | ⭐⭐⭐⭐ |
| Store-specific size curves | 1 | Low-Medium | ⭐⭐⭐⭐ |
| Style DNA matching | 2 | Medium | ⭐⭐⭐⭐ |
| Store behaviour profiling | 2 | Medium | ⭐⭐⭐⭐ |
| Cannibalization detection | 2 | Low-Medium | ⭐⭐⭐ |
| Full explainability panel | 3 | Low | ⭐⭐⭐⭐⭐ |
| Dashboard insight cards | 3 | Low | ⭐⭐⭐⭐ |
| Week-1 sell-through triggers | 4 | High | ⭐⭐⭐⭐⭐ |
| Inter-store transfer recommendations | 4 | High | ⭐⭐⭐ |

---

*This document is a living plan. It should be reviewed and updated after each pilot engagement based on what the VP challenged, what she approved without question, and what she asked for that wasn't there.*
