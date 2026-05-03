# 10 — How KYROS Uses AI

A direct, code-grounded answer to the question: *what role does AI actually play in KYROS MVP?*

---

## TL;DR

**KYROS today uses zero machine learning and zero LLMs.** Verified against the codebase: no `anthropic`, no `openai`, no `sklearn`, no `torch`, no `transformers`, no embeddings, no `model.fit()` anywhere.

The `ai_` prefix on fields like `ai_recommended_qty`, `ai_confidence`, `ai_reasoning` is **branding, not architecture**. Every "AI" output in the product is the result of **deterministic merchandising rules + statistical aggregation** over historical data.

This is by design and it is the right design for MVP.

---

## What "AI" Actually Means in the Code Today

A line-by-line classification of what the engine actually does:

| Component | File | What It Really Is | ML/AI? |
|-----------|------|-------------------|--------|
| 4-tier demand fallback | [demand.py](backend/app/services/allocation/demand.py) | Lookup + weighted averaging of historical ROS | No |
| ROS computation | [demand.py](backend/app/services/allocation/demand.py) | `units_sold / weeks_in_stock` | No |
| Stockout correction | [demand.py](backend/app/services/allocation/demand.py) | Pattern detection (consecutive zero-sale weeks) | No |
| Store scoring | [engine.py](backend/app/services/allocation/engine.py) / [intelligence.py](backend/app/services/allocation/intelligence.py) | `0.5 × ros + 0.25 × grade + 0.25 × cover` linear combo | No |
| Cover target lookup | [constants.py](backend/app/services/allocation/constants.py) | Static dict keyed by `(risk, grade)` | No |
| Size split | [size_curve.py](backend/app/services/allocation/size_curve.py) | Ratio application from history or defaults | No |
| Cannibalization dampening | [story_concentration.py](backend/app/services/allocation/story_concentration.py) | Multiplicative factor 0.65–0.90 by story count | No |
| Affinity multipliers | [store_profile.py](backend/app/services/allocation/store_profile.py) | Lookup-based scaling | No |
| Style DNA matching | [demand.py](backend/app/services/allocation/demand.py) | Attribute-based similarity (fabric, price, risk, color) | No (rule-based) |
| Health scoring | [health.py](backend/app/services/allocation/health.py) | Composite formula over coverage / balance / confidence | No |
| Confidence tiers | [demand.py](backend/app/services/allocation/demand.py) | Categorical label based on data tier used | No |

**Total**: ~4,500 lines of allocation code, zero of which call a model.

---

## Why This Is Correct for MVP

The MVP thesis is **trust through auditability**, not sophistication. A merchandiser who overrides a recommendation must be able to follow the math line-by-line. Three properties matter:

1. **Determinism** — same inputs always produce the same output
2. **Auditability** — every output traces back to a specific rule
3. **Stability** — engine behavior doesn't drift between runs

ML and LLMs violate at least one of these. Adding them today would make pilot adoption *harder*, not easier.

A pilot VP looking at a recommendation does not want "the model says 21." They want "21 units because Mumbai Juhu sold 4.2 units/week and we target 7 weeks of cover for A+ stores on proven styles." The first is unfalsifiable. The second is a position the VP can take to their CEO.

---

## Where AI Genuinely Adds Value in MVP

There is exactly **one** place where an LLM helps without breaking auditability.

### The Explanation Layer

Today, `ai_reasoning` is a ~20-field JSON blob:
```json
{
  "demand_source": "STORE_HIST",
  "tier": 1,
  "weeks_history": 34,
  "ros_raw": 4.2,
  "ros_corrected": 4.2,
  "stockout_detected": false,
  "cover_target_weeks": 7,
  "affinity_multiplier": 1.0,
  "cannibalization_factor": 1.0,
  "scale_factor": 0.714,
  ...
}
```

A merchandiser cannot read this. Today there is no plain-English summary.

An LLM call (Claude Haiku 4.5, ~50 output tokens per line) can deterministically transform the JSON into:

> "Mumbai Juhu (A+ store) gets 21 units because it sold 4.2 units per week of kurtis last season. With a 7-week cover target for A+ stores, this lands at 21 after scaling for available inventory. Confidence: HIGH (based on 34 weeks of own-store history)."

**Why this is safe**:
- The LLM doesn't make decisions — it narrates pre-computed math
- Output is constrained to facts already in the source JSON
- Errors would be stylistic, not financial
- Cached per `(session_id, line_id)` — generated once, immutable
- Auditable: planner can compare the sentence against the JSON and catch hallucinations

**Implementation note**:
- ~5,000 allocation lines per session × 50 tokens × ~$0.0001/1K tokens (Haiku output) = ~$0.025 per session
- Trivial cost. High user-value.
- Use prompt caching: the system prompt + JSON schema is identical across lines

This is the **only** place AI should enter MVP.

---

## Where AI Should NOT Be Used in MVP

Hard rules. Each one is a position the product cannot give up without losing the thing pilots are buying.

| Layer | Why Not |
|-------|---------|
| **Demand projection** | Must stay rule-based. Adding ML here hides cause. Planner cannot answer "why is this number what it is?" |
| **Allocation distribution** | Must stay deterministic. A planner cannot audit "the model decided X." |
| **Confidence scoring** | Must derive from data quantity (weeks of history, store coverage), not from model uncertainty. The latter is opaque. |
| **Override classification** | Use a controlled-vocabulary dropdown. LLM categorization breaks the structured-learning signal. |
| **OTB calculation** | Keep as transparent arithmetic. A VP must defend OTB to their CFO. |
| **Style → store eligibility** | Stay rule-based (store_group_rule, climate, grade). ML would be unauditable for a question that has hard answers. |

Adding AI to any of these in MVP turns a system the VP can defend into a system the VP cannot.

---

## Where AI Genuinely Fits Post-MVP

After **one full season** of data on the platform, four ML/LLM layers become legitimate:

### A. Demand Forecasting (Replaces 4-Tier Fallback)
- **What**: time-series model (Prophet, gradient-boosted trees) trained per category × store
- **Output**: distributional forecast (P10 / P50 / P90), not point estimate
- **Constraint**: must publish feature importance per prediction so planner can audit
- **Replaces**: tiers 1–4 of demand.py
- **Keeps**: tier 5 (min_presentation_qty) as floor

### B. Style DNA Embeddings (Replaces Attribute Matching)
- **What**: text-embedding model on style descriptions, fabric notes, design briefs
- **Why**: attribute-based matching breaks down on truly novel styles; embeddings generalize better
- **Constraint**: top-K matches with similarity scores must be visible to the planner

### C. Anomaly Detection
- **What**: ML-driven flagging of stores/styles that deviate from cluster behavior
- **Use case**: surfaces issues a planner wouldn't notice manually (a B-store quietly performing like an A+ store on dresses)
- **Output**: ranked exception list with reason codes

### D. Onboarding & Conversational Helper
- **What**: LLM helper for messy CSV ingestion (column mapping suggestions, validation error explanations) and natural-language filters ("show me overstock candidates in C-grade stores")
- **Why**: lowest-risk LLM use because the planner verifies the action before it executes

### E. Post-Season Residual Analysis (Differentiator)
- **What**: LLM-summarized post-season report combining quantitative residuals with structured override reasons
- **Output**: "Planners systematically over-allocated dresses to north India by ~12% — likely cause: festive calendar misalignment between Bengal and Punjab"
- **Why this is high leverage**: turns Kyros from a planning tool into a learning system. The moat compounds every season.

None of A–E **replace** the deterministic core. They sit on top of it as overlays the planner can opt into.

---

## The Naming / Branding Question

The codebase says `ai_recommended_qty`, `ai_confidence`, `ai_reasoning`. This is technically misleading today.

Two options:

| Option | Pro | Con |
|--------|-----|-----|
| **Rename** to `engine_recommended_qty`, etc. | Honest | Loses marketing; requires migration; messes with allocation API contract |
| **Keep `ai_` prefix; add real AI progressively** (explanation layer first, forecasting later) | Marketing language stays consistent; naming becomes accurate as features land | Today's naming overstates what's there |

The pragmatic choice is **Option 2**. Ship the LLM explanation layer in Phase 1 (it's the cheapest, highest-leverage AI work) — at that point the `ai_reasoning` field genuinely contains AI output, and the name stops being a lie.

---

## The Honest Tagline

KYROS is not "AI-powered allocation." That phrase, used today, is overclaiming.

The honest version:

> **Deterministic merchandising math, with AI where it makes the math more readable.**

That is what KYROS is today. That is what it should be in MVP. That is what the pilot brands will actually trust.

The phrase "AI-powered" can come back as a real claim once forecasting (Post-MVP layer A) is shipped — when there *is* a learned model in the loop. Until then, calling rule-based logic "AI" is a credibility risk: a sophisticated retail VP will see through it in five minutes and discount the product accordingly.

---

## Summary Matrix

| Layer | Today (Reality) | MVP Goal | Post-MVP (P2+) |
|-------|-----------------|----------|----------------|
| Demand projection | Rule-based 4-tier fallback | Same | ML forecasting (Prophet / GBM) |
| Allocation math | Deterministic rules | Same | Same (forever) |
| Explanation | Raw JSON | **LLM-narrated sentence** | Same |
| Style matching | Attribute similarity | Same | Text embeddings |
| Anomaly detection | None | None | ML-driven |
| Onboarding helper | None | None | LLM-assisted |
| Override classification | Free text | Controlled dropdown | LLM-augmented categorization |
| Post-season learning | None | None | LLM-summarized residual analysis |
| OTB calculation | Manual arithmetic | Manual + history-anchored suggestion | Stays deterministic |
| Confidence scoring | Tier-based label | Same | Add data-quantity-based numeric |

The bold cell is the only AI work that should ship inside MVP. Everything else is post-pilot.
