# KYROS MVP — Pre-Season Planning Design Docs

Internal system design documentation for KYROS's pre-season merchandising OS. These are not user docs — they are the reasoning blueprint behind the product.

---

## Reading Order

| # | Document | What It Covers |
|---|----------|----------------|
| 01 | [Pre-Season Planning — Fundamentals](01_pre_season_planning_fundamentals.md) | What pre-season planning actually is, viewed as capital allocation under uncertainty. The irreversibility problem. Risks, blast radius, why it exists. |
| 02 | [Core Decision System](02_core_decision_system.md) | The five decision layers a VP owns — OTB, Assortment, Store Strategy, Buy Quantity, Timing. How each works, what the trade-offs are. |
| 03 | [System Interdependency](03_system_interdependency.md) | How the five layers are coupled. Why Excel-based planning fails — not as a tooling complaint, but as a structural argument. |
| 04 | [Decision Modeling — Kyros View](04_decision_modeling.md) | The system reduced to inputs → transformations → outputs. What data we need, what math happens, what decisions come out. |
| 05 | [KYROS MVP Design](05_kyros_mvp_design.md) | Modules, data models, and core algorithms — translated from decision model into product shape. |
| 06 | [MVP Priorities — Must-Have vs Nice-to-Have](06_mvp_priorities.md) | What ships to validate PMF. What gets cut. The justification for cutting. |
| 07 | [Failure Points](07_failure_points.md) | Where planning breaks in real retail. Where data is unreliable. Where assumptions silently collapse. |
| 08 | [Walkthrough — 100 Stores, 1000 Styles, ₹10Cr](08_walkthrough_example.md) | End-to-end worked example. How decisions flow. How Kyros's outputs change what a VP would do. |
| 09 | [Gap Analysis — Current Code vs MVP](09_gap_analysis.md) | Audit of the actual codebase (2026-04-24). Module-by-module status, top 5 blockers, prioritized build plan, code-level findings. |
| 10 | [How KYROS Uses AI](10_ai_role_in_kyros.md) | Honest answer: zero ML/LLMs today. The `ai_` prefix is branding. Where AI genuinely fits in MVP (explanation layer only) and where it should NOT be used. |

---

## The Frame

KYROS is not a dashboard. It is a **decision system**. The right mental model is:

> A VP at a ₹100Cr brand commits ~70% of next season's inventory capital six months before a single unit is sold. The consumer signal they are betting on does not yet exist. Once committed, the capital is non-refundable. Once goods arrive, only markdown can reverse mistakes — at 30–50% margin cost.
>
> Kyros's job is to make that committed bet defensibly better than Excel — while being auditable enough that the VP trusts replacing their spreadsheet with it.

Every design decision in these docs traces back to that frame.

---

## Where The Current Code Stands

See [../CLAUDE.md](../CLAUDE.md) for the implemented state as of 2026-04-22:

- Allocation engine (the **back half** of the loop) is built and over-engineered.
- Everything upstream (season → OTB → buy plan) is either missing or manual.
- Pilot brands cannot use Kyros end-to-end because they cannot answer "what should I buy?" — only "here's what arrived, allocate it."

These docs define what the **whole loop** should look like, not just what is coded today.
