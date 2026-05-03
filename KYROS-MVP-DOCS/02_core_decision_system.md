# 02 — Core Decision System

Pre-season planning reduces to five decision layers. A VP makes each one before any PO is cut. Each layer has its own math, its own failure modes, and its own trade-offs.

These are not sequential — they are **mutually constraining**. You cannot finalize one without iterating the others.

---

## Layer 1 — Budget Allocation (OTB)

### What OTB Actually Is

Open-To-Buy is **the cash envelope that may be committed to inventory** for a given period and product unit.

The canonical equation:

```
OTB (retail value) = Planned Sales + Planned EOP Stock − BOP Stock − On Order
```

Expressed at cost (since buying happens at cost):

```
OTB (cost) = OTB (retail) / (1 + IMU markup)
```

### How Budget Is Split — Three Axes

| Axis | Split | Driver |
|------|-------|--------|
| **Category** | 35–45% top category, 15–25% each for next 2, 5–15% long tail | Historical contribution × strategic push |
| **Channel** | Retail / E-com / Wholesale / Marketplace | Channel-level sellthrough curve differs; e-com needs narrower SKU, deeper core sizes |
| **Time** | Month-by-month across season weeks | Matches expected sell curve (front-loaded for summer, back-loaded for winter) |

### Early vs Late Allocation — The Most Underrated Decision

A disciplined planner does **not** commit 100% of OTB before the season starts.

Typical split:
- **Opening order**: 60–70% of season OTB committed pre-season
- **Chase / reactive**: 20–30% held open to react to in-season signal
- **Reserve**: 5–10% contingency for PO overruns, replacement buys

The opening-order % is a **risk dial**:
- Higher (80%+) in stable categories with predictable demand (core denim, men's basics)
- Lower (50–60%) in trend-heavy categories (women's dresses, seasonal colors)

Getting this dial wrong is a silent killer. Brands that front-load too heavily lose the ability to chase winners; brands that hold too much open get priced out of factory capacity mid-season.

### Risk vs Safety Inside OTB

- **Planned Sales** is the bet. Set too high → overbuy. Set too low → stockouts.
- Rule of thumb: planned sales = (last season actuals × growth factor) — but growth factor must be calibrated category-by-category, not brand-level.
- **Planned EOP Stock** is the other hidden bet. A healthy EOP is 6–10 weeks of forward cover. Higher = excess carryover; lower = starved for next season's BOP.

### Common OTB Failures

1. Planner inflates planned sales to justify a bigger buy they already decided on (OTB becomes a rationalization, not a constraint)
2. On-order is ignored or misstated — brands often forget vendor commitments already in motion
3. OTB is tracked at brand level only, not by category × month; overruns hide until they pile up
4. OTB retail vs cost confusion — mixing markup-inclusive and markup-exclusive numbers in the same sheet

---

## Layer 2 — Assortment Architecture

Once budget is set, the question becomes: **what product shape fills that budget?**

### Width vs Depth

- **Width** = number of unique styles / SKUs
- **Depth** = units per style

For a fixed OTB:
```
Width × Depth × Avg Cost = OTB
```

More width → more options, more choice, more newness — but thinner depth, shorter cover, higher stockout risk per style.

More depth → stronger presence per style, longer cover — but fewer newness opportunities, bigger bet per style.

### Typical Architecture (Indian fashion brand, ₹100Cr)

| Segment | Style Count | % of Buy Units | % of Buy Value | Depth per Style |
|---------|-------------|----------------|----------------|-----------------|
| Hero (proven, high-ROS) | 8–12% of styles | 25–30% | 20–25% | 400–800 units |
| Core (basics, replenishable) | 35–45% of styles | 45–55% | 40–50% | 200–400 units |
| Fashion (seasonal, mid-risk) | 30–40% of styles | 15–20% | 20–25% | 80–150 units |
| Experimental (test) | 8–12% of styles | 3–5% | 5–8% | 30–80 units |

### Price Architecture — Good / Better / Best

A balanced price ladder:
- **Value tier** (40–55% of units): entry price point, basket builder
- **Mid tier** (30–40% of units): core margin engine
- **Premium tier** (8–15% of units): aspirational, protects brand position

Price imbalance is a classic mistake: a brand that over-indexes value erodes margin; one that over-indexes premium starves sellthrough.

### Category Mix

Driven by:
1. **Last season sellthrough** (mechanical — higher ST = more space)
2. **Strategic pushes** (new category expansion, brand direction)
3. **Calendar events** (wedding season, festival, monsoon)
4. **Store mix shifts** (new A+ stores in premium malls → more premium mix)

### New vs Repeat Styles

- **Repeat carryovers**: 20–30% — proven styles continued. Low risk, predictable demand.
- **Line extensions**: 40–50% — variations of known patterns. Medium risk.
- **New introductions**: 20–30% — genuinely new silhouettes, prints, fabrics. High risk.
- **Experimental**: 5–10% — trend bets.

Too few new styles → brand stagnation. Too many → sellthrough collapse (customers have nothing familiar).

### Story / Collection Architecture

Styles group into **stories** (collections) — e.g., "Monsoon Hues", "Festive Edit", "Workwear Core".

Each story has:
- A visual merchandising block in-store
- A marketing narrative
- A budget envelope
- A launch date

Story architecture matters because: stockouts **within** a story kill the story's in-store presentation. If 3 of 6 styles in "Festive Edit" are stocked out in A+ stores by week 4, the VM block looks broken even if total category sellthrough is healthy.

---

## Layer 3 — Store Strategy

### Store Grading

Every brand grades stores, but few do it rigorously.

Good grading is:
- **Multi-dimensional**: by category and price band, not just overall (a mall store may be A+ for women's kurtis and C for denim)
- **ROS-based, rent-adjusted**: (units sold / week) / (rent / week) per sqft
- **Refreshed quarterly**: grade drift is real — catchment shifts, competitor entry

Typical grade distribution:
- **A+**: top 10–15% of stores, 30–40% of revenue
- **A**: next 20–25% of stores, 25–30% of revenue
- **B**: middle 30–40%, 20–25% of revenue
- **C**: bottom 20–30%, 10–15% of revenue

### Demand Distribution Logic

Demand per store ≈ (Store ROS for category) × (Weeks of cover target for grade × risk group) × (style-specific affinity multipliers).

Cover targets typically:
| Grade | Proven styles | Experimental styles |
|-------|---------------|---------------------|
| A+ | 7 weeks | 4 weeks |
| A | 5 weeks | 3 weeks |
| B | 4 weeks | 2 weeks |
| C | 3 weeks | 0 (don't send) |

The "don't send to C for experimental" rule is important — C stores cannot amortize the learning cost of test styles.

### Geographic and Demographic Effects

- **Climate zone**: monsoon regions need quick-dry fabrics; northern winter zones need layering; southern coastal needs cotton/linen dominance
- **Region**: South India skews smaller sizes; North skews larger; West (Mumbai/Pune) skews middle
- **Catchment demographics**: mall stores in tier-1 cities get premium mix; high-street in tier-3 cities get value mix
- **Festival timing**: Onam (Kerala), Durga Puja (Bengal), Karva Chauth (North) drive category spikes — store-level calendar matters

### Concentration vs Spread

This is the single most consequential allocation decision after OTB.

- **PROVEN styles** → wide spread. Every eligible store that meets grade minimum gets units. The goal is maximum reach for known winners.
- **EXPERIMENTAL styles** → concentration. Top 5–10 stores only. Reasons:
  1. Learning signal is clearer from fewer stores with deeper inventory
  2. Fewer stores to pick up damage from a flop
  3. A+ customers are more forgiving of experimental product

Brands that spread experimental styles widely produce thin, unreadable signal and heavy markdown.

### Store Openings Mid-Season

New stores complicate everything:
- They have no historical ROS — must use cluster or grade fallback
- They need opening inventory packs that may be disproportionate
- Their first 4–8 weeks of data are unreliable (novelty effect)

A planner needs to explicitly flag "new store" and use a different allocation heuristic.

---

## Layer 4 — Buy Quantity Strategy

Given OTB envelope × assortment architecture × expected store demand, how many units of each style?

### Depth Per Style

```
Target depth = (Store ROS projection × Weeks of cover × # Eligible stores) + Warehouse reserve
```

Then adjust for:
- Vendor MOQ (often 300–500 minimum)
- Cost per unit (cheaper styles can go deeper)
- Risk tier (experimental capped at 100; hero allowed 500+)

### Hero vs Test Styles

**Hero styles**:
- Must-have depth to support 6–8 weeks of full-price selling in A+ stores
- Replenishable (fabric held by vendor for chase orders)
- Never allowed to stock out in A+ during peak weeks

**Test styles**:
- Minimum Viable Quantity (MVQ) — 5–8 stores × 10–15 units = 50–120 units
- No replenishment plan — if it hits, you scramble; if not, you clear
- Capped at 1–2% of style budget per test

### Vendor Constraints

- MOQ: most vendors won't run a line below 300–500 units
- Lead time: piece-dyed 8–10 weeks, yarn-dyed 10–14, print 6–8 weeks
- Advance payments: 20–30% at PO, 30–40% at fabric-in
- Quality tier: premium vendors have higher MOQ but reliable delivery; tier-2 vendors have lower MOQ but higher slippage risk

A buy plan must reconcile **ideal depth from demand math** with **achievable depth from vendor math**. The gap is filled with compromise — and that compromise is where budget leaks.

### Risk Exposure

Concentration rules (sanity checks):
- No single style >10% of category budget
- No single vendor >25% of category buy
- No single fabric mill >30% of category buy
- No single style's stockout should cost >2% of expected category sellthrough

These are guardrails, not optimization targets.

---

## Layer 5 — Timing Strategy

### Inventory Flow Across the Season

A well-paced season has 3–5 drops:
- **Drop 1** (pre-season week 0): 50–60% of season inventory, covers first 8–10 weeks of sellthrough
- **Drop 2** (week 4–6): 20–25%, refreshes assortment with new fashion
- **Drop 3** (week 8–10): 10–15%, late-season fashion + chase orders on winners
- **Drop 4** (week 14+): 5–10%, clearance support + carryover prep

### Early vs Mid vs Late Drop Trade-offs

| Timing | Pro | Con |
|--------|-----|-----|
| Early-loaded | Captures full-price weeks | Heavy markdown if trend misses |
| Mid-loaded | Balanced exposure | Risks stockout in first 4 weeks |
| Late-loaded | Minimal carryover risk | Misses peak full-price window |

### Cash Flow Implications

- Early-loaded = heavy working capital drag in month 0–2
- Late-loaded = cash flow smoother but markdown-compressed
- Most brands under-weight cash flow implications and plan as if working capital is free

### Markdown Risk

Markdown candidates are identified by week 8–10 (mid-season):
- Styles at <40% of expected sellthrough → first markdown (15–20%)
- Styles at <25% by week 12 → deeper markdown (30–40%)
- Styles carried to next season → either full markdown or warehouse hold

The **timing of first markdown** is a leverage point:
- Too early → cannibalizes full-price sales, trains customer to wait
- Too late → deeper discount needed, higher margin erosion

### Replenishment vs Fixed-Buy

- **Core replenishable styles** (jeans, tees, leggings) — 4–6 week factory turn, reorder as needed
- **Fashion styles** — fixed buy, no replenishment; if it sells, it sells
- **Hero fashion** — soft-replenish: hold fabric with vendor, trigger cut if ROS exceeds threshold

---

## The Interconnection Summary

None of these layers is independent. You cannot:
- Set OTB without a rough assortment shape
- Shape assortment without store demand visibility
- Plan buy quantity without vendor MOQ reality
- Time drops without buy plan delivery schedules

The next doc ([03](03_system_interdependency.md)) formalizes these couplings and explains why Excel-based planning structurally cannot resolve them.
