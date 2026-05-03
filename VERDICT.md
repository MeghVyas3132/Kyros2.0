# KYROS MVP — Production Readiness Verdict

_Generated: 2026-04-28 · Phases delivered: 1 → 4 · Phases deferred: 5 → 7 (require ERP/WMS/POS)_

## TL;DR

Phases 1–4 of the Kyros MVP are wired end-to-end, exercised against synthetic pilot data (~3,500 SKUs, ~75,000 sales rows, 184 stores, 1,258 planogram cells), and covered by a green test suite. Phases 5–7 depend on external ERP / WMS / POS feeds and are deferred until those integrations are in place.


## 1. Phase Status

| Phase | Scope | Status |
|---|---|---|
| 1 — Foundation | Auth, 4-role RBAC, SUPER_ADMIN onboarding queue, season lifecycle, ingestion, dashboard | ✅ Complete |
| 2 — OTB & Range | Live OTB calc, reconciliation, range/buy gates | ✅ Complete |
| 3 — Buy Planning | Buy plan CRUD, OTB-aware lines, GRN linkage | ✅ Complete |
| 4 — Allocation & Planogram | Engine, capacity ceiling, reasoning, simulator, override, CSV export | ✅ Complete |
| 5 — In-Season Performance | Daily ROS / sell-through / 5-cell matrix, action queue | ⏸ Deferred (needs POS feed) |
| 6 — Inventory Health | Range exposure, health score, alerts | ⏸ Deferred (needs WMS feed) |
| 7 — Post-Season Learning | Residual analysis, learned defaults | ⏸ Deferred (needs full season of in-season data) |

### 1.1 Onboarding flow (new)

Pilots self-serve via `/signup` (public). Submissions land in a `signup_requests` queue in **PENDING** state — no Brand / User exists yet. The platform's **SUPER_ADMIN** (single seeded operator: `admin@shriemlabs.com`) reviews the queue at `/super-admin` and either approves (creates Brand + ADMIN user, applicant can log in) or rejects (marks REJECTED for audit). Pending applicants who try to log in get HTTP 403 `SIGNUP_PENDING`. SUPER_ADMIN cannot run tenant-scoped operations — every brand-scoped endpoint returns `SUPER_ADMIN_TENANT_BLOCKED` if hit by a SUPER_ADMIN, preventing the operator from accidentally polluting a sentinel brand.

## 2. Synthetic Pilot — Pipeline Run

Source files at repo root:

- `SS26 Master File For Allocation V12.xlsx` — buy file (3,536 SKU rows, 19 cols), SS25 sales history (281,460 rows, 14 cols), size guide (80 rows)
- `Store Grading.xlsx` — 4,788 (store × product × price-band → grade) rows

### 2.1 Ingestion

| Stage | Records ingested | Notes |
|---|---:|---|
| Store grades | 4788 | Bootstrapped 162 stores from grading file |
| Size guide | 80 | All 80 size-guide rows accepted |
| Buy file (SKUs + buy plan) | 3536 SKUs / 3536 buy-plan lines | Source: SS26 BUY FILE sheet |
| Sales history | 75896 rows (108,865 units) over 8 synthetic weeks | `week_start_date` synthesized for 63,471 rows (no date column in source) |
| Display capacity | 1258 (store × category) cells | Heuristic: A+ → 80 styles, A → 60, B → 40, C → 25 |
| Inventory snapshot | 41762 rows | Built for season open date |
| Store profiles | 184 | Velocity archetype + behavior |

### 2.2 Allocation Run

- Synthetic GRN: top 25 styles by buy qty × all sizes = 200 SKU lines, 24,486 units received.
- Engine runtime: **185.74s** end-to-end across 36,800 (store × SKU) candidate lines.

### 2.3 KPIs

| Metric | Value | Pass criteria |
|---|---|---|
| Lines with positive qty | 13,423 / 36,800 (36.5%) | > 5% (engine routes selectively) |
| Distinct stores receiving stock | 184 / 184 | ≥ 80% of active stores |
| Distinct styles allocated | 25 / 25 | All GRN styles or close |
| Units allocated / received | 15,520 / 24,486 (63.4%) | 50–80% (rest held for follow-up) |
| Top-10% store concentration | 23.7% of allocated units | < 40% (no extreme skew) |
| Display-capacity violations (units) | 0 | **must = 0** |
| Display-capacity violations (styles) | 0 | **must = 0** |
| Reasoning coverage | 100.0% of positive lines have a narrative | ≥ 95% |
| Weeks-of-cover P50 / P90 | 6.9 / 11.0 | matches cover-target band |

**Confidence-tier distribution** (positive lines):

- `LOW` — 13,423 lines (100.0%)

**Demand-tier (`ros_source`) distribution**:

- `minimum_presentation` — 9,982 lines (74.4%)
- `style_dna_analogue` — 3,441 lines (25.6%)

## 3. Test Suite

Pytest summary: `127 passed, 4 skipped, 2 warnings in 10.56s`

| Result | Count |
|---|---:|
| Passed | 127 |
| Failed | 0 |
| Skipped | 4 |
| Errors | 0 |
| Duration | 12.37s |

### 3.1 Coverage by area

| Area | Test files |
|---|---|
| Auth + bootstrap + multi-tenant | `test_auth_bootstrap.py`, `test_api/test_multi_tenant.py` |
| Onboarding (signup queue, SUPER_ADMIN approve/reject, login gating) | `test_api/test_signup_flow.py` |
| Upload runner failure capture | `test_api/test_upload_runner_failure.py` |
| Ingestion (mapping, understanding) | `test_ingestion_mapping.py`, `test_data_understanding.py` |
| OTB / sanity / reconciliation | `test_api/test_otb.py`, `test_api/test_sanity_and_otb.py` |
| Buy plan | `test_api/test_buy_plan.py` |
| Six-step workflow E2E | `test_api/test_e2e_workflow.py` |
| Allocation engine (distribution, cover, story) | `test_allocation_distribution.py`, `test_cover_framing.py`, `test_story_threshold.py`, `test_size_curve.py`, `test_allocation_benchmark.py` |
| Demand + stockout + reasoning | `test_stockout_correction.py`, `test_reasoning_contract.py`, `test_allocation/*.py` |
| Allocation API (override, generate, e2e) | `test_api/test_allocation_override.py`, `test_e2e_allocation.py` |
| Phase 4 — capacity, CSV export, season fallback | `test_api/test_allocation_phase4.py` |
| Phase 4 — surface (capacity CRUD, story concentration, by-GRN) | `test_api/test_phase4_surface.py` |
| Celery failure / engine guardrails | `test_celery_failure.py` |
| LLM (Groq client + admin) | `test_api/test_groq_client.py`, `test_api/test_admin_llm.py` |

## 4. Production Readiness Checklist

| Item | Status | Notes |
|---|---|---|
| Migration chain runs clean from empty DB | ✅ | 0001 → 0012 (Alembic verified) |
| Self-serve signup + super-admin approval | ✅ | Public `/auth/signup` queues, SUPER_ADMIN approves; live API smoke + 9 tests |
| SUPER_ADMIN cannot run tenant operations | ✅ | All write endpoints return `SUPER_ADMIN_TENANT_BLOCKED` (403) — frontend redirects to `/super-admin` |
| Upload failures surface to the UI (no stuck PROCESSING rows) | ✅ | Runner persists `error_summary.fatal_error` + `traceback` on subprocess crash |
| Multi-tenant isolation enforced | ✅ | 8 isolation tests covering seasons, OTB, buy plan, workflow |
| RBAC: ADMIN / PLANNER / VIEWER | ✅ | Tested across buy-plan and admin endpoints |
| Allocation engine: capacity respected | ✅ | 0 unit + 0 style violations on synthetic run |
| Allocation engine: reasoning coverage | ✅ | All positive lines emit narrative chunks (`narrative_demand`, `narrative_cap`, `narrative_adjustments`) |
| CSV export | ✅ | `/sessions/{id}/export` streams (with optional zero-quantity inclusion) |
| Celery failure handling | ✅ | FAILED status + retry logic + UNDER_REVIEW guard |
| Groq LLM key rotation | ✅ | Round-robin, cache flush, refresh endpoint, admin status |
| Six-step workflow state machine | ✅ | Cannot regress; each milestone advances the gate |
| External integrations (ERP / WMS / POS) | ⏸ | Deferred — replace synthetic pipeline with live feeds before Phase 5 |
| Production secrets & monitoring | ⚠ | `.env` placeholders; rotate JWT + Groq keys before deploy; wire CloudWatch / Prometheus |
| Load test at full scale (≥ 500 stores × 5K SKU) | ⚠ | Engine ran 184 stores × 200 SKUs in 185.74s; full pilot scale untested |

## 5. Known Gaps / Follow-ups

1. **LLM narrations**: confidence currently dominated by `LOW` because SS26 buy styles have no per-SKU SS25 history (different style codes). Once Groq keys are wired and a real pilot brand brings two seasons of overlapping styles, expect tier mix to shift toward `MEDIUM`/`HIGH` and `ros_source` to concentrate on `store_history` and `cluster_avg`.
2. **Saved scenarios**: `simulate_quantity` is per-line. A persistent `AllocationScenario` table for side-by-side comparison is not yet shipped — the simulator endpoint covers the MVP scope.
3. **Frontend Phase 4 polish**: `ScenarioSimulator` and `ExplainabilityPanel` components exist; the GRN review page renders override + reason capture and consumes the reasoning payload. UI smoke tests are out of scope here.
4. **Sales date fidelity**: synthetic SS25 sales has no date column, so the ingestion pipeline spreads units across 8 synthetic weeks. Real pilot brands must provide `week_start_date` for the demand engine to use temporal signal.

## 6. Sign-off

Phases 1–4 ship as a coherent allocation system: data in → planogram-aware recommendation out → reviewed/overridden → CSV exported. The pipeline produced valid recommendations for all 25 GRN styles across 184 stores within the cover and capacity envelope, with 0 hard-constraint violations. Once Groq keys are added (drop-in env var), the LLM-narration layer activates without any code change. The system is ready for a controlled pilot.
