# 06 — MVP Priorities: Must-Have vs Nice-to-Have

The MVP exists to validate one hypothesis:

> **"Can we get a fashion brand to make a better pre-season allocation decision using Kyros than they would make in Excel — and trust the output enough to replace their spreadsheet?"**

Every feature gets evaluated against that hypothesis. If it doesn't move the needle on *trust × better decision*, it doesn't ship in MVP.

---

## Must-Have (P0 — Ships for Pilot)

### MH1 — Complete Planning Loop End-to-End
The single biggest MVP gap is that a brand cannot complete a planning cycle in Kyros today. They stop at "we already have a buy file from our vendor, now what?"

Needed:
- Buy Plan API (CRUD for BuyPlan, BuyPlanLine)
- Buy Plan UI (table view, edit, OTB reconciliation bar)
- Buy Plan ↔ GRN linkage (when GRN is created, reference the plan it fulfills)
- Guided workflow shell (1/6 → 6/6 progress)

**Why P0**: without this, the brand has no coherent narrative. They cannot be onboarded in one session. The allocation engine's sophistication is wasted on disconnected inputs.

### MH2 — OTB → Buy Plan Coupling
OTB entry already exists. Buy plan does not check against OTB. At minimum:
- Live category usage bar in Buy Planner
- Hard-warn on category overrun
- Month-level OTB drill-down

**Why P0**: this is the *one thing Excel fundamentally cannot do well*. If Kyros doesn't show OTB-vs-buy in real time, we don't have a structural advantage over a spreadsheet.

### MH3 — Data Ingestion (Sales, Grades, Size, GRN)
Already works. MVP additions:
- Better error surfacing (currently buried)
- "What was skipped and why" report
- Data quality gates that block progression if thresholds not met (sales history <12 weeks, grades missing for >30% of stores, etc.)

### MH4 — Allocation Engine — Simplified Explanation
Engine works. The reasoning JSON is too complex for pilot merchandisers.

Needed:
- Human-readable sentence per allocation line: *"Store Mumbai-MG Road gets 18 units because it sold 3.0 units/week last season (grade A, kurti category). This gives 6 weeks of cover."*
- Confidence badge (HIGH/MEDIUM/LOW) — simple label, no score
- Demand source badge (Store History / Cluster / Grade / Analogue)

**Why P0**: trust requires auditability. A merchandiser who cannot explain the recommendation to their CEO will not use the product.

### MH5 — Line-Level Override with Structured Reason
Override already works with free-text reason. MVP upgrade:
- Reason dropdown: "Store grade drift", "Known local trend", "Vendor delay", "Category shift", "Other + text"
- Override history kept (audit trail)
- Bulk override operations (apply change across filtered subset)

**Why P0**: override capture is the learning-loop input. Without structured reasons, we cannot do residual analysis post-season.

### MH6 — Summary Review View
Currently the review page is line-level only. Planners cannot eyeball totals before approving.

Needed:
- Totals by store, category, risk group, grade
- Top/bottom stores by allocation
- Out-of-band flags (stores with 0 allocation, stores exceeding cover target)

### MH7 — CSV Export for WMS
Already works. No changes.

### MH8 — Guided 6-Step Workflow
Bind existing pages into a narrative:
1. Season setup ✓
2. OTB entered ✓
3. Data ingested ✓
4. Buy plan locked ✓
5. Allocation generated ✓
6. Approved + exported ✓

**Why P0**: this is what makes onboarding possible in one sitting. Without it, Kyros is a toolbox, not a system.

---

## Nice-to-Have (P1 — Post-Pilot, Pre-GA)

### NH1 — OTB Calculator (from history)
Currently OTB is manual entry. P1 adds:
- "Suggest OTB" button: computes from last-season actuals × growth factor × category mix target
- Scenario save/compare

### NH2 — Assortment Builder
Full style-list design UX before buy planning. Most brands already bring a buy file, so this is workflow polish, not validation-critical.

### NH3 — What-If Simulator (harden existing)
Already exists for allocation. Extend to:
- "What if I shift ₹50L from kurtis to dresses?" → recomputes buy plan depth, projects allocation shift
- Save as named scenario; compare side-by-side

### NH4 — Chase Recommender
In-season signal > threshold → suggest replenishment. Requires in-season performance data, which is post-pilot by definition.

### NH5 — Store Grade Auto-Suggest
Given last season's ROS × rent, propose updated grades. Currently grades are entered manually.

### NH6 — Cover Target Editor (UI)
Settings exist in DB. UI doesn't. Pilot can live with defaults.

### NH7 — Cluster Management UI
Clusters exist in DB. Managed via API/seed. Pilot uses defaults.

### NH8 — Health Analyzer as User-Facing Panel
Currently backend-only. Eventually surface it — *carefully* — with redesigned UX that doesn't overwhelm.

---

## P2 — Differentiator Features (Later)

### D1 — Learning Loop
Season N actuals feed Season N+1 defaults:
- Update ROS baselines from actual sellthrough
- Flag stores where allocation accuracy was poor → grade adjustment signal
- Analyze override accuracy — did overrides help or hurt?

This is Kyros's long-term moat. Every season on the platform should produce better defaults for the next. But it requires one full season of data before it can kick in, so it can't be an MVP feature.

### D2 — In-Season Performance Tracking
Weekly ROS trends, sellthrough %, stockout/overstock alerts.

### D3 — Transfer Orders
Mid-season stock rebalancing between stores.

### D4 — Markdown Strategy
End-of-season pricing waterfalls.

### D5 — Planogram Constraints
Space-based allocation caps.

---

## Explicitly Cut From MVP

### Cut C1 — Style DNA Matching (as user-facing)
Keep as internal demand fallback (Tier 4), but do not expose as a product feature. It is too complex for pilot merchandisers to audit.

### Cut C2 — Cannibalization Dampening (as user-facing)
Keep on by default (factor 0.65–0.90). Do not surface as a toggle. Mentioning "cannibalization" to a merchandiser without deep UX work produces confusion, not trust.

### Cut C3 — Affinity Multipliers (as user-facing)
Same — on by default, not exposed.

### Cut C4 — Cold-Start / Supply-Led Mode
Most pilot brands have 1+ season of data. Cold-start is an edge case we don't need to optimize for.

### Cut C5 — Alert Generation
In-season feature. No pilot value pre-season.

### Cut C6 — Multi-Tenant / Multi-Country
Pilots are single-brand India. YAGNI.

### Cut C7 — POS/WMS Integration
CSV export is sufficient. API integration is a year-2 problem.

### Cut C8 — Health Score as User-Facing
Backend QA tool. Users don't need a "quality score" — they need to understand the recommendation. The score will surface eventually, but only after we've done UX work to make it actionable rather than anxiety-inducing.

---

## The Hardest Cut — Allocation Sophistication

The allocation engine today has 1672 lines of logic. MVP should **not** add any more. Specifically:

- Do not add new demand tiers
- Do not add new scoring inputs
- Do not add new constraint layers

The P0 work is to **build the upstream that makes existing sophistication valid** (buy plan, OTB linkage) and to **simplify the user-facing explanation** of what the engine already does.

A VP will not trust a black box that outputs perfect math. They will trust a transparent system that outputs good-enough math they can follow line by line.

---

## Validation Criteria — How We Know MVP Is Done

A pilot brand must be able to:

1. Create a season in <5 minutes
2. Enter OTB for 6–10 categories in <30 minutes
3. Upload last season's sales, grades, and size guide — all ingested with >95% row acceptance
4. Load their SS26 buy plan (CSV or UI) and see OTB reconciliation
5. Upload a GRN and trigger allocation
6. Get allocation back within 2 minutes
7. Review the recommendations with clear per-line reasoning
8. Override 5–15% of lines with structured reasons
9. Approve and export CSV
10. Complete steps 1–9 in a single 2-hour working session with a planner and a VP

If all ten happen, and the VP says *"yes, I would use this instead of my Excel"*, MVP has done its job. Every feature not needed for those ten steps is wrong to build now.
