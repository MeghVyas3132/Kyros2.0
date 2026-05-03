# 09 — Gap Analysis: Current System vs KYROS MVP

Audit as of 2026-04-24. Grounded in the actual code, not the aspirational CLAUDE.md.

The short answer: **the allocation brain is disproportionately developed against an almost non-existent planning body**. A retailer cannot complete a full pre-season cycle today. What they can do is upload a buy file someone else prepared in Excel, receive it, and allocate it — which is the bottom third of the loop.

---

## Section 1 — Current System Capabilities (What Actually Works)

Evaluated against the end-to-end flow: Season → OTB → Buy Plan → GRN → Allocation → Review.

### 1.1 Season Setup
- **Exists**: yes — [backend/app/routers/seasons.py:24-53](backend/app/routers/seasons.py#L24-L53), [frontend/app/(dashboard)/setup/seasons/page.tsx](frontend/app/%28dashboard%29/setup/seasons/page.tsx).
- **Usable**: yes — create, list, update season with name, start/end date, categories list.
- **Complete**: **no** —
  - `SeasonStatus` enum has only `PLANNING / ACTIVE / CLOSED` ([models/season.py:11-14](backend/app/models/season.py#L11-L14)). No granular states for BUYING / RECEIVING / ALLOCATING.
  - Status is not enforced anywhere — a season can stay in `PLANNING` forever while GRNs and allocations are generated.
  - No `weeks_remaining` computation, no channel splits, no category seed from library.
- **Can a retailer use it?** Yes for naming a season, no for coordinating the planning cycle inside it.

### 1.2 Budget / OTB
- **Exists**: yes — [routers/seasons.py:72-113](backend/app/routers/seasons.py#L72-L113), [models/season.py:30-47](backend/app/models/season.py#L30-L47).
- **Usable**: yes — save/read per `(season, category, month)` row.
- **Complete**: **no** —
  - `otb_value` is a Postgres computed column (`planned_sales + closing − opening − on_order`). Good. But that's the only "logic" in OTB.
  - No rollup (season total, month total, category total, mix %).
  - No validation on `planned_sales` (can be 0, negative, absurdly inflated).
  - No overrun detection, no comparison to last season, no reserve/opening-order % knob.
  - No UI beyond raw grid (per CLAUDE.md — no OTB calculator page).
- **Can a retailer use it?** As a data table, yes. As a budget planning tool, no — it's a spreadsheet with a computed cell.

### 1.3 Data Ingestion
- **Exists**: yes — [routers/ingestion.py](backend/app/routers/ingestion.py) (508 lines), [services/ingestion/processor.py](backend/app/services/ingestion/processor.py) (~1,400 lines).
- **Usable**: yes — 5 file types (SALES, STORE_GRADES, SIZE_GUIDE, BUY_FILE, GRN) with auto-column-mapping.
- **Complete**: mostly — synthetic week spreading works, stockout inference partial.
- **Gaps**:
  - No data-quality gates that block progression (e.g. "<12 weeks of sales → warn but do not block buy plan").
  - Errors are logged but surfaced only at `/api/v1/ingestion/uploads/{id}/errors`; the UI does not foreground them well.
  - No reconciliation view: "these SKUs in your buy file are missing from your SKU master".
- **Can a retailer use it?** Yes for ingesting clean data. For dirty real-world data, only with hand-holding.

### 1.4 Buy Plan  — **the biggest gap**
- **Exists**: partially — model and ingestion path only.
- **What exists**:
  - `BuyPlanFile` and `BuyPlanLine` ORM models ([models/buy_plan.py](backend/app/models/buy_plan.py)).
  - Fields on `BuyPlanLine`: `sku_id`, `store_group_rule`, `style_risk_group`, `total_buy_qty`, `expected_first_allocation_qty`. That's it.
  - Ingestion handler `_upsert_buy_file()` populates rows when a BUY_FILE CSV is uploaded ([processor.py:1147-1340](backend/app/services/ingestion/processor.py#L1147-L1340)).
  - `grn_lines.buy_plan_line_id` FK exists ([models/grn.py:40](backend/app/models/grn.py#L40)) — GRN links back to buy plan.
  - Allocation engine reads `buy_plan_map[grn_line.buy_plan_line_id].store_group_rule` to override store eligibility ([engine.py:293-294](backend/app/services/allocation/engine.py#L293-L294)).
- **What does NOT exist**:
  - **No `buy_plan.py` router** — confirmed by directory listing. No CRUD API.
  - **No frontend page** — no `/buy-plan` route.
  - **No schemas** for BuyPlan create/update.
  - **No fields** for vendor, expected delivery week, unit cost, MOQ, planned price, season linkage in the create flow — the model has `season_id` on `BuyPlanFile` but nothing else that maps to commercial reality.
  - **No OTB check** — buy plan qty is stored without any validation against the season's OTB.
  - **No reconciliation** — no view showing "your buy plan exceeds OTB by ₹1.2Cr".
- **Can a retailer use it?** Only by preparing a buy file in Excel, uploading it, and trusting that it got parsed. They cannot view it, edit it, or reason about it inside Kyros. This is the **philosophical hole** at the center of the product.

### 1.5 GRN
- **Exists**: yes — [routers/grn.py](backend/app/routers/grn.py) (113 lines), UI at [frontend/app/(dashboard)/grn/](frontend/app/%28dashboard%29/grn/).
- **Usable**: yes — create GRN, add lines, manage reservations, view detail, block deletion when active allocation exists.
- **Complete**: mostly for its scope —
  - Works as an inventory receipt.
  - Links to buy plan line **only if ingestion populated the FK**; manual GRN creation does not prompt for buy plan line.
- **Gaps**:
  - No "receive against buy plan" view where planner sees "Buy plan says 500 of K-047, GRN received 430 — 14% short, chase?"
  - No warning if GRN arrives without a buy plan reference (warehouse is disconnected from planning intent).
- **Can a retailer use it?** Yes, but disconnected from the plan that preceded it.

### 1.6 Allocation
- **Exists**: yes — and then some. ~4,500 lines across [services/allocation/](backend/app/services/allocation/) (engine 1,671; demand 1,236; benchmark 319; health 412; size_curve 285; store_profile 398; cap 174; intelligence 114; explainer 106; story_concentration 70; simulator 67; guardrails 57).
- **Usable**: yes — Celery-dispatched generation, async session lifecycle, line-level overrides, simulator, export.
- **Complete**: over-complete — the engine encodes sophistication (style DNA, cannibalization dampening, affinity multipliers, stockout correction, 4-tier demand fallback, per-store size curves) that exceeds what pilot merchandisers can audit.
- **Gaps**:
  - `ai_reasoning` JSON has ~20 fields — no human-readable sentence layer.
  - Health score and benchmark are QA tools, currently readable by users but with no UX framing.
  - No explanation of what Tier was used in plain English; merchandiser must decode `demand_source: "GRADE_AVG"`.
- **Can a retailer use it?** Yes mechanically. No with confidence — the output is not auditable by a non-technical planner.

### 1.7 Review / Approval
- **Exists**: yes — [routers/allocation.py](backend/app/routers/allocation.py) (801 lines) handles lines, override, approve, export.
- **Usable**: yes — line-level override with reason, approve, CSV export.
- **Complete**: partially —
  - Free-text override reason, no structured taxonomy → no learning signal post-season.
  - No summary rollup view (totals by store / category / grade / risk) before approval.
  - No diff view ("lines with >30% variance from AI rec").
  - Post-approval immutability works (status transitions block regeneration).
- **Can a retailer use it?** Yes for line-by-line work. No for the "approve 5,000 lines with confidence" problem every pilot faces.

---

## Section 2 — Gap Analysis per Module

### 2.1 Season Setup
| Gap | Type | Impact |
|-----|------|--------|
| `SeasonStatus` has only 3 states | Model | Cannot gate workflow transitions |
| No state-machine enforcement | Logic | Season can be "PLANNING" forever with allocations happening |
| No channel split | Model | Cannot model retail vs ecom differently |
| No `weeks_remaining` field | Model / Logic | Every engine call recomputes; planner can't see at-a-glance |

### 2.2 Budget / OTB
| Gap | Type | Impact |
|-----|------|--------|
| No season / category / month rollup endpoint | API | UI cannot show totals without N+1 client joins |
| No overrun validation vs buy plan | Logic | OTB is "advisory" — buy can exceed it silently |
| No calculator (last-season-driven suggestions) | Logic / UI | Manual entry; no anchor to actuals |
| No reserve / opening-order % knob | Model / UI | Cannot express "hold 30% for chase" |
| No category-mix % or YoY delta view | UI | Planner cannot see category drift |

### 2.3 Data Ingestion
| Gap | Type | Impact |
|-----|------|--------|
| No data-quality gate | Logic | Allocation runs on <4 weeks of history with no warning |
| Error surface weak | UI | 770 rejected rows discovered only by checking a sub-endpoint |
| No SKU-master reconciliation | Logic | Unknown SKUs silently dropped |

### 2.4 Buy Plan — **THE BLOCKER**
| Gap | Type | Impact |
|-----|------|--------|
| No `buy_plan.py` router | API | No way to view, edit, create, delete buy plans |
| No `/buy-plan` frontend page | UI | Planner cannot interact with the plan as a plan |
| Model missing commercial fields (vendor, delivery week, cost, MOQ) | Model | Cannot reconcile buy against OTB in ₹, only in units |
| No OTB link at edit time | Logic | Cannot warn "this buy exceeds Kurtis-April OTB by ₹40L" |
| No MOQ / concentration / depth validations | Logic | Plan can breach category caps silently |
| No "create buy plan from scratch" workflow | UI / Logic | Only CSV upload; a brand who wants to design inside Kyros cannot |
| No BuyPlanLine ↔ Season ownership view | UI | Planner cannot answer "what's the SS26 plan?" |

### 2.5 GRN
| Gap | Type | Impact |
|-----|------|--------|
| No "GRN against buy plan" reconciliation view | UI | Short shipments undetected |
| Manual GRN creation doesn't prompt buy plan line | UI / Logic | Breaks the allocation engine's store_group override path |
| No reserve-types UI surface (they exist in model) | UI | Reservation setup requires admin API |

### 2.6 Allocation
| Gap | Type | Impact |
|-----|------|--------|
| No plain-English explanation layer | Presentation | Planner cannot audit ⇒ will not trust ⇒ will not replace Excel |
| Too many exposed toggles / internals | UX | Cognitive overload for pilot users |
| Health score shown to users | UX | QA tool leaked to user-facing view |
| No "exception review" mode | UX | Planner reviews randomly, not by risk |

### 2.7 Review / Approval
| Gap | Type | Impact |
|-----|------|--------|
| Free-text override reasons | Logic / UX | No structured learning signal |
| No summary rollup pre-approval | UX | Approval happens on trust, not on math |
| No bulk operations | UX | 5,000-line review is manual |

---

## Section 3 — Philosophical Misalignment

### 3.1 We built the back half before the front half
The allocation engine is 4,500 lines of intelligence sitting on top of an OTB table with no math and a buy plan with no API. This is the core misalignment: the product can **distribute** decisions that were made elsewhere, but cannot help you **make** them.

A retailer's first question is *"what should I buy?"* Kyros today answers *"here's how to allocate what you already bought."* That is not wrong, but it is the second question.

### 3.2 Sophistication before trust
The engine encodes cannibalization dampening, affinity multipliers, style DNA matching, and 4-tier demand fallback. These are technically impressive and mathematically defensible. They are also **unauditable** by a merchandiser who opens the product for the first time.

Trust requires simplicity. A pilot user needs to look at an allocation recommendation and say "yes, I see why Store X got 21 units." They will not reach that clarity through a 20-field `ai_reasoning` JSON. The engine built trust-destroying complexity before it built any trust-building simplicity.

### 3.3 Tools, not a workflow
The frontend has independent pages (`/grn`, `/allocation`, `/ingestion`, `/setup/seasons`, `/setup/onboarding`). Each is a capable tool. None of them tell the planner *what to do next*. There is no "Step 3 of 6" shell, no state-gated progression, no onboarding wizard that takes a brand from zero to first approved allocation in one session.

A brand evaluating Kyros in a 2-hour demo sees a toolkit and asks "which tool do I open first?" That question has no answer today except "this one, then this one, then this one" delivered verbally by the demoer. The **narrative is not in the product**.

### 3.4 Planning artifacts populated only via CSV
`BuyPlanFile` exists only as a side effect of CSV upload. There is no domain model where "a buy plan is a first-class planning artifact that a merchandiser creates, iterates on, shares for review, and commits." It is a data table that happens to be written to when a file is ingested.

This reveals an unconscious assumption: that planning happens outside Kyros and Kyros ingests the result. But MVP's promise is that planning happens **inside** Kyros. Until a buy plan can be created, edited, versioned, and committed as a first-class artifact, we are still an allocation tool with a CSV importer, not a planning platform.

### 3.5 Season status is not a workflow state
The `SeasonStatus` enum has 3 values. The real planning workflow has at least 6–8 states. Nothing in the codebase enforces ordering (OTB before buy, buy before GRN, GRN before allocation). A brand can run allocation on a season with no OTB and no buy plan. Nothing stops them — and nothing informs them that they probably should not.

---

## Section 4 — Top 5 MVP Blockers

Ranked by what most directly blocks a real pilot from completing a full cycle.

### Blocker 1 — Buy Plan Management Surface
**What is missing**:
- `buy_plan.py` router with CRUD endpoints
- `/buy-plan` frontend page (list, detail, edit, create-from-scratch)
- Commercial fields on `BuyPlanLine` (vendor_id, expected_delivery_week, planned_cost, moq)
- OTB ↔ buy-plan reconciliation view

**Why it blocks MVP**:
Without this, "planning" in Kyros is a file upload. A VP cannot iterate on a plan, cannot compare scenarios, cannot see OTB usage as they adjust depth, cannot ask "what changed since last week?"

**What breaks without it**:
- The upstream loop is broken — there is no product for the buy decision
- GRN ↔ BuyPlan linkage is fragile (requires every GRN to originate from CSV ingestion of the same file that populated the buy plan)
- Allocation engine's `store_group_rule` override path fails silently when buy_plan_line_id is NULL
- The pilot brand reverts to Excel for the one workflow that matters most

### Blocker 2 — OTB as a Live Constraint, not a Table
**What is missing**:
- Season / category / month rollup endpoints
- Real-time OTB-vs-buy delta computation
- Overrun warnings in buy plan UI
- Reserve / opening-order % knob
- Last-season-anchored OTB calculator (even a naïve "LY × (1 + growth)" would be a start)

**Why it blocks MVP**:
OTB is supposed to be the single thing Excel structurally cannot do well. Kyros today stores OTB the same way Excel does — as a set of cells. The coupling to buy plan is what makes OTB valuable, and that coupling does not exist in the API or the UI.

**What breaks without it**:
- The structural advantage over Excel evaporates
- Buy plan can silently blow the budget
- Planner has no way to simulate "shift ₹50L kurtis → dresses"

### Blocker 3 — Workflow Shell (Guided 6-Step Progression)
**What is missing**:
- A persistent top-level shell showing current season's progress through the 6 steps
- State transitions on Season (DRAFT → PLANNING → BUYING → RECEIVING → ALLOCATING → IN_SEASON → CLOSED)
- Gating logic (cannot generate allocation if season has no OTB and no buy plan)
- A single "What should I do next?" entry point on the dashboard

**Why it blocks MVP**:
A pilot brand being onboarded asks "where do I start?" Today the answer is "click around, here's what each tool does." That does not survive a VP demo. The product needs to **teach the workflow**, not leave the user to reverse-engineer it.

**What breaks without it**:
- Onboarding in a single session is impossible
- Brands cherry-pick tools and miss upstream requirements
- No structural reinforcement of "don't allocate without a buy plan"

### Blocker 4 — Plain-English Allocation Explanation
**What is missing**:
- Derived `ai_reasoning_human` sentence per allocation line (2–3 sentences, no jargon)
- Simple confidence badge (HIGH / MEDIUM / LOW) with a tooltip that explains the tier
- Exception-first review mode: low confidence, high-variance, out-of-band flags surfaced at top

**Why it blocks MVP**:
Trust is the product. If the pilot merchandiser cannot read a line and explain the recommendation to the CEO in one breath, the product gets filed under "AI black box" and replaced with Excel.

**What breaks without it**:
- Pilot rejects the recommendations regardless of accuracy
- Overrides skyrocket not because the math is wrong, but because the math is unreadable
- The engine's sophistication becomes a liability, not an asset

### Blocker 5 — Summary Review View + Structured Override Reasons
**What is missing**:
- Pre-approval summary dashboard (totals by store, category, grade, risk, region)
- Override reason as a controlled vocabulary dropdown, not free text
- Bulk operations on filtered subsets

**Why it blocks MVP**:
A 5,000-line allocation cannot be audited line-by-line. Planners need a bird's-eye view to build confidence before approving. And without structured override reasons, every override is a lost learning signal — the post-season review has nothing to work with.

**What breaks without it**:
- Approvals are rubber-stamps or paralyzed reviews
- Post-season learning loop has no input data
- Override patterns that reveal systematic engine errors remain invisible

---

## Section 5 — Prioritized Build Plan

### Phase 1 — Critical (must fix before any real pilot)

**P1-1: Buy Plan CRUD + UI** — 3–5 engineering weeks
- `routers/buy_plan.py`: list, detail, create, update, delete plan; add/remove/bulk-edit lines
- Extend `BuyPlanLine` model: `vendor_id`, `expected_delivery_week`, `planned_cost_per_unit`, `moq`, `planned_price_per_unit`
- `/buy-plan` Next.js page: list view + detail/edit
- Live OTB reconciliation bar (category × month usage %)
- Alembic migration for new fields

**P1-2: OTB ↔ Buy Plan Coupling** — 1–2 weeks (parallelizable with P1-1)
- `GET /seasons/{id}/otb/summary`: rollups by season, category, month
- `GET /seasons/{id}/otb/reconciliation`: OTB vs sum(buy plan in same bucket)
- Overrun warnings in buy plan UI
- Reserve % knob in brand_settings or at season level

**P1-3: Guided Workflow Shell** — 1–2 weeks
- Expand `SeasonStatus` enum: add BUYING, RECEIVING, ALLOCATING, IN_SEASON
- State transition rules in seasons router (gate based on upstream completion)
- Top-bar workflow component in frontend: Step 1 of 6 with completion checks
- Dashboard "What should I do next?" widget

**P1-4: Plain-English Allocation Explanation** — 1 week
- `explainer.py`: add `reasoning_human` field derived from existing JSON
- Update allocation review UI to lead with human sentence; push JSON behind "Details"
- Simple confidence badge replacing current tier labels

**P1-5: Structured Override Reasons** — 3–5 days
- `override_reason_code` enum (GRADE_DRIFT, LOCAL_TREND, VENDOR_DELAY, CATEGORY_SHIFT, STORE_CLOSURE, OTHER)
- Dropdown in UI + required selection
- Migration for existing rows (best-effort mapping from free text, rest → OTHER)

**Total Phase 1 runway**: ~6–9 engineering weeks with 2 engineers.

---

### Phase 2 — Stability (trust-and-usability polish)

**P2-1: Summary Review Dashboard** — 1 week
- Rollups by store / category / grade / risk on session detail
- Exception-first panel (low confidence, cover-target violations, grade violations)

**P2-2: Data Quality Gates** — 1 week
- Ingestion-time assertions: "<12 wks sales → WARN", "no `was_in_stock` → WARN", "SKU master missing for X% of sales rows → BLOCK"
- Reconciliation report surfaced in UI (not buried in a sub-endpoint)

**P2-3: GRN vs Buy Plan Reconciliation View** — 3–5 days
- "GRN received vs buy plan expected" delta per style
- Flag short shipments as chase candidates

**P2-4: OTB Calculator (History-Driven)** — 1–2 weeks
- `POST /seasons/{id}/otb/suggest`: given last-season actuals + growth factor, propose monthly OTB
- UI "Suggest" button per category row
- Snapshot/compare mode

**P2-5: Bulk Operations on Allocation Lines** — 3–5 days
- Filter + bulk override
- Apply single reason code to many lines

---

### Phase 3 — Advanced (already built, but hide or simplify for MVP)

**P3-1: Simplify or Hide Engine Internals for Pilot Users**
- Hide cannibalization dampening as a user-facing toggle (keep on by default at 0.75)
- Hide affinity multipliers (keep on)
- Hide style DNA tier in UI labels (collapse to "Analogue-based estimate")
- Health score: backend-only; do not show to pilot users

**P3-2: Simulator Hardening**
- Exists in `simulator.py` (67 lines) — plumbing done, UX is not
- Post-MVP: "save scenario", "compare side-by-side"

**P3-3: Performance Tracking Polish**
- Routes exist but no strong pre-season use
- Revisit after first full season completes

**P3-4: Assortment Builder (P2+)**
- Full style-list design UX — not needed for pilots who bring their own buy file

**P3-5: Learning Loop**
- Design Phase 2, build post-first-season

---

## Section 6 — Code-Level Findings

Specific, file-linked observations.

### Missing
| Artifact | Location that should exist | Impact |
|----------|---------------------------|--------|
| `buy_plan.py` router | `backend/app/routers/buy_plan.py` | No CRUD API for BuyPlan |
| `buy_plan.py` schemas | `backend/app/schemas/buy_plan.py` | No request/response validation |
| `/buy-plan` page | `frontend/app/(dashboard)/buy-plan/page.tsx` | No UI surface |
| `/buy-plan/[id]` page | `frontend/app/(dashboard)/buy-plan/[id]/page.tsx` | No detail/edit surface |
| OTB summary endpoint | `seasons.py` — add `GET /seasons/{id}/otb/summary` | No rollups |
| OTB reconciliation endpoint | `seasons.py` — add `GET /seasons/{id}/otb/reconciliation` | No OTB-vs-buy delta |
| OTB calculator endpoint | `seasons.py` — add `POST /seasons/{id}/otb/suggest` | No history-driven suggestions |
| Workflow state endpoint | `seasons.py` — `GET /seasons/{id}/workflow-state` | No "step 3 of 6" data |

### Incomplete Models
| Model | Missing Fields | Why It Matters |
|-------|----------------|----------------|
| `BuyPlanLine` ([models/buy_plan.py](backend/app/models/buy_plan.py)) | `vendor_id`, `expected_delivery_week`, `planned_cost_per_unit`, `moq`, `planned_price_per_unit`, `planned_margin_pct` | Cannot reconcile in ₹, cannot flag MOQ gaps, cannot project margin |
| `SeasonStatus` ([models/season.py:11-14](backend/app/models/season.py#L11-L14)) | Missing `DRAFT`, `BUYING`, `RECEIVING`, `ALLOCATING`, `IN_SEASON` | Cannot gate workflow |
| `AllocationLine.override_reason` ([per CLAUDE.md](CLAUDE.md)) | Needs `override_reason_code` enum alongside free text | Free text = no learning |

### Disconnected Services / Weak Coupling
- **BuyPlan ↔ Allocation coupling is brittle**: `engine.py:293` uses `buy_plan_line_id` only as an optional override. If the GRN was created manually (not via CSV ingestion), `buy_plan_line_id` is NULL and the override path is skipped. Nothing warns the user.
- **Season ↔ GRN**: `grns.season_id` is set by `_upsert_buy_file()` during ingestion ([processor.py:1292](backend/app/services/ingestion/processor.py#L1292)) but not required on manual GRN creation. Orphaned GRNs are possible.
- **OTB is entirely decoupled from buy plan** at the API level. The Postgres computed column computes a number; nothing consumes it in a validation chain.

### Unused or Under-Used Logic
- **`simulator.py`** (67 lines) — wired to a POST endpoint but not surfaced in a user-facing way. Currently more of a debug tool than a product feature.
- **`benchmark.py`** (319 lines) — generates a QA report (override rate, grade compliance, utilization, etc.). Valuable to the Kyros team; too much to show pilot users directly.
- **`health.py`** (412 lines) — verdict is attached to allocation sessions. User-facing in CLAUDE.md but should be backend-only for MVP per the design principle in [06](06_mvp_priorities.md).
- **`story_concentration.py`** (70 lines) — cannibalization dampening. On by default, no user-visible knob. Would be safer to hide entirely in MVP.
- **`performance_snapshot.py` task** — runs weekly, populates `performance_snapshots`. Not visualized anywhere that a pilot brand will use in pre-season.

### Ingestion-Only Paths (Fragile)
- `BuyPlanFile`, `BuyPlanLine` can **only** be populated via `_upsert_buy_file()` in processor. No alternate create path exists. If a brand wants to design a buy plan inside Kyros, they can't.
- `grn_lines.buy_plan_line_id` is populated **only** inside `_upsert_buy_file()` when the BUY_FILE CSV also contains GRN-receipt rows ([processor.py:1302-1340](backend/app/services/ingestion/processor.py#L1302-L1340)). Manual GRN creation via `/api/v1/grns` does not set this FK.

---

## Section 7 — Final Verdict

### The Question
> Can a retailer today complete a full pre-season planning cycle using this system?

### The Answer
**No.**

### Why, Precisely

A complete pre-season cycle requires:

1. ✅ Create a season
2. ⚠️ Set OTB *that has consequences downstream* — **fails**: OTB is stored but never enforced
3. ❌ Build a buy plan inside the product — **fails**: no router, no UI, only CSV upload
4. ⚠️ Reconcile buy plan against OTB — **fails**: no reconciliation endpoint
5. ✅ Receive a GRN
6. ✅ Run allocation
7. ⚠️ Audit the recommendations — **partially fails**: reasoning is machine-readable, not human-readable
8. ⚠️ Override with structured feedback — **partially fails**: free text only, no learning signal
9. ✅ Approve + export

Three of nine steps fail outright. Two more fail partially. The three that pass (season creation, GRN, allocation mechanics) are the ones Kyros already leaned into.

### What a Pilot Sees Today
A pilot brand walks in with an Excel buy plan prepared by their merchant. They upload the CSV. They upload sales history and grades. They create a GRN. They run allocation. They review recommendations and get confused by the 20-field reasoning JSON. They override 30–50% of lines based on gut feel. They export the CSV and hand it to the warehouse.

The planning work — the ₹10Cr decision — **happened in Excel before they arrived**. Kyros allocated the consequence.

### What Needs to Change for the Answer to Become "Yes"
Phase 1 (6–9 weeks, 2 engineers) flips three of the five failing steps to passing:
- Buy plan CRUD + UI (step 3)
- OTB-vs-buy reconciliation (step 4)
- Plain-English allocation explanation (step 7)
- Structured override reasons (step 8)
- Guided workflow shell (wraps all of it)

After Phase 1, a retailer can sit down in Kyros and do the full loop. The allocation engine's sophistication, which today is trapped behind a missing front half, becomes the product's differentiator rather than its awkward center of gravity.

### The One-Sentence Verdict
**Kyros today is a sophisticated allocator with a CSV front door. MVP requires making it a planning system that happens to also allocate. That is a sequencing problem, not an algorithmic one — and the six to nine weeks to fix it are the highest-leverage engineering hours available.**
