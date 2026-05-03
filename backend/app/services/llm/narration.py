"""Domain-aware narrators built on top of the Groq client.

Each narrator owns:
  1. A system prompt scoped to one domain (allocation reasoning, OTB
     suggestion, data sanity warnings, etc.).
  2. A formatter that turns structured KYROS data into a compact user
     message.
  3. A deterministic fallback string the caller will always receive even
     if the LLM is disabled or every key fails.

The Groq client is shared across narrators via the singleton in
``groq_client.py``, so round-robin rotation and the LRU cache work
across all use-cases.
"""
from __future__ import annotations

import json
from typing import Any

from app.services.allocation.explainer import generate_human_reasoning
from app.services.llm.groq_client import get_groq_client

# ─── Allocation line ─────────────────────────────────────────────────────────

ALLOC_SYSTEM_PROMPT = """You are a retail merchandising assistant helping a buyer at an Indian fashion brand audit allocation recommendations.

Rules:
- Always 2-3 sentences. Plain English. No jargon, no markdown.
- Stay strictly within the supplied facts. Do NOT invent numbers.
- Lead with WHY this store gets this many units, not WHAT.
- If `is_stockout_corrected` is true, mention it briefly — recorded sales understate true demand.
- If scale_factor < 1.0, mention that supply was capped.
- Always end with the cover outcome ("X weeks of cover").
- The reader is a merchandising planner, not a data scientist."""


def _build_alloc_user_prompt(reasoning: dict[str, Any]) -> str:
    """Compact factual recap fed to the LLM. JSON keeps numeric precision."""
    keep = {
        k: reasoning.get(k)
        for k in (
            "weekly_ros",
            "ros_source",
            "store_grade",
            "cover_target_weeks",
            "weeks_cover_at_recommended",
            "is_stockout_corrected",
            "stockout_correction_applied",
            "scale_factor",
            "raw_demand_units",
            "narrative_demand",
            "narrative_adjustments",
            "narrative_cap",
            "stockout_week",
            "lost_sales_estimate",
        )
        if reasoning.get(k) is not None
    }
    return (
        "Narrate this allocation recommendation in 2-3 sentences.\n"
        f"Facts: {json.dumps(keep, separators=(',', ':'))}"
    )


async def narrate_allocation_line(reasoning: dict[str, Any]) -> str:
    """Generate the LLM-narrated explanation for one allocation line.

    Falls back to the deterministic template (`generate_human_reasoning`)
    when the LLM is disabled or every Groq attempt fails.
    """
    fallback = generate_human_reasoning(reasoning)
    client = get_groq_client()
    if not client.enabled:
        return fallback
    return await client.narrate(
        system_prompt=ALLOC_SYSTEM_PROMPT,
        user_prompt=_build_alloc_user_prompt(reasoning),
        fallback=fallback,
        max_tokens=150,
        temperature=0.2,
    )


# ─── Pre-allocation sanity check (Track A) ───────────────────────────────────

SANITY_SYSTEM_PROMPT = """You are a retail merchandising assistant flagging data quality issues before an allocation is generated.

Rules:
- 1-2 sentences. Plain English.
- Lead with the most consequential issue.
- Be specific about which step is blocked or risky.
- Do NOT invent numbers; only use what is supplied.
- The reader will decide whether to proceed; help them weigh the risk."""


def _sanity_fallback(facts: dict[str, Any]) -> str:
    blockers = facts.get("blockers") or []
    warnings = facts.get("warnings") or []
    if blockers:
        return f"Blocked: {blockers[0]}. Resolve before running allocation."
    if warnings:
        return f"Warning: {warnings[0]}. Allocation may produce low-confidence recommendations."
    return "Data looks sufficient to run allocation."


async def narrate_sanity_check(facts: dict[str, Any]) -> str:
    fallback = _sanity_fallback(facts)
    client = get_groq_client()
    if not client.enabled:
        return fallback
    return await client.narrate(
        system_prompt=SANITY_SYSTEM_PROMPT,
        user_prompt=(
            "Summarise the merchandiser-facing risk implied by this data check.\n"
            f"Facts: {json.dumps(facts, separators=(',', ':'))}"
        ),
        fallback=fallback,
        max_tokens=120,
        temperature=0.2,
    )


# ─── OTB suggestion (Track C) ─────────────────────────────────────────────────

OTB_SYSTEM_PROMPT = """You are a retail merchandising assistant explaining an OTB (open-to-buy) suggestion to a planner.

Rules:
- 2 sentences. Plain English.
- Mention the basis (last season actuals × growth factor).
- Note what the planner should sanity-check before committing.
- No jargon. No markdown."""


def _otb_fallback(facts: dict[str, Any]) -> str:
    cat = facts.get("category", "this category")
    last = facts.get("last_season_actual_sales", 0)
    growth = facts.get("growth_factor", 1.0)
    suggested = facts.get("suggested_planned_sales", 0)
    return (
        f"Suggested {cat} planned sales: ₹{suggested:,.0f} "
        f"(last season actual ₹{last:,.0f} × {growth:.2f} growth factor). "
        "Adjust if you expect category-specific shifts not captured by the growth assumption."
    )


async def narrate_otb_suggestion(facts: dict[str, Any]) -> str:
    fallback = _otb_fallback(facts)
    client = get_groq_client()
    if not client.enabled:
        return fallback
    return await client.narrate(
        system_prompt=OTB_SYSTEM_PROMPT,
        user_prompt=(
            "Explain this OTB suggestion in 2 sentences a planner can defend to their CFO.\n"
            f"Facts: {json.dumps(facts, separators=(',', ':'))}"
        ),
        fallback=fallback,
        max_tokens=120,
        temperature=0.2,
    )
