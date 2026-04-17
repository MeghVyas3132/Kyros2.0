from collections import defaultdict
from dataclasses import dataclass, field
from math import ceil
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AllocationLine, Store, SKU


@dataclass
class HealthReport:
    score: int = 0
    label: str = "CRITICAL"
    sub_scores: Dict[str, float] = field(default_factory=dict)
    risks: List[Dict[str, Any]] = field(default_factory=list)
    top_recommendations: List[str] = field(default_factory=list)
    
    def to_json(self):
        return {
            "score": self.score,
            "label": self.label,
            "sub_scores": self.sub_scores,
            "risks": self.risks,
            "top_recommendations": self.top_recommendations,
        }

class AllocationHealthAnalyzer:
    """Computes Allocation Health, sub-score metrics, and risks based on v2 Design."""
    
    def __init__(self, session_id: UUID, brand_id: UUID, db: AsyncSession):
        self.session_id = session_id
        self.brand_id = brand_id
        self.db = db
        
        
    def get_context(self) -> Dict[str, Any]:
        """Provides context on the season maturity and distribution for decision-making."""
        return {
            "is_cold_start": True,  # Placeholder until linked to season
            "season_week": 1,
            "total_season_weeks": 16,
            "demand_confidence_mix": {
                "historical": 0.0,
                "dna": 0.8,
            }
        }
    
    async def analyze(self) -> HealthReport:
        # Load all needed data
        # We will stream the non-zero lines and zero lines that had demand
        stmt = select(
            AllocationLine.store_id,
            AllocationLine.sku_id,
            AllocationLine.final_qty,
            AllocationLine.ai_reasoning,
            AllocationLine.ai_projections,
            AllocationLine.ai_confidence
        ).where(AllocationLine.session_id == self.session_id)
        
        result = await self.db.execute(stmt)
        lines = result.all()  # Depending on volume, might need chunking in production
        
        # 1. Evaluate Metrics
        coverage_metrics = self._compute_coverage(lines)
        alignment_metrics = self._compute_alignment(lines)
        balance_metrics = self._compute_balance(lines)
        presentation_metrics = self._compute_presentation(lines)
        confidence_metrics = self._compute_confidence(lines)
        
        # 2. Score Computation Base
        WEIGHTS = {
            "coverage": 0.30,
            "demand_align": 0.25,
            "confidence": 0.20,
            "presentation": 0.15,
            "balance": 0.10,
        }
        
        sub_scores = {
            "coverage": coverage_metrics["score"],
            "demand_align": alignment_metrics["score"],
            "balance": balance_metrics["score"],
            "presentation": presentation_metrics["score"],
            "confidence": confidence_metrics["score"],
        }
        
        base_score = sum(WEIGHTS[m] * sub_scores[m] for m in WEIGHTS)
        
        # 3. Detect Risks
        # Will expand this
        risks = []
        
        # 4. Hard Penalties
        final_score, penalties = self._apply_hard_penalties(base_score, coverage_metrics, presentation_metrics, lines)
        for p in penalties:
            risks.append({"type": "HARD_PENALTY", "severity": "CRITICAL", "explanation": p})
            
        final_score = max(0, min(100, int(final_score)))
        
        # 5. Determine Label
        if final_score >= 75:
            label = "SAFE"
        elif final_score >= 55:
            label = "CAUTION"
        elif final_score >= 35:
            label = "RISKY"
        else:
            label = "CRITICAL"
        
        recommendations_sys = generate_recommendations(risks, cov_m, self.get_context())
        
        return HealthReport(
            score=final_score,
            label=label,
            sub_scores=sub_scores,
            risks=risks,
            top_recommendations=[r["action"] for r in recommendations_sys]
        )
        
    def _compute_coverage(self, lines) -> Dict[str, Any]:
        healthy = 0
        lean = 0
        overstock = 0
        stockout = 0
        dead = 0
        total = 0
        
        for row in lines:
            reasoning = row.ai_reasoning or {}
            ros = reasoning.get("weekly_ros", 0)
            if ros <= 0:
                continue
            
            # Skip fallback for coverage calc
            if reasoning.get("ros_source") == "minimum_presentation":
                continue
                
            qty = row.final_qty or 0
            cover = qty / ros
            
            total += 1
            if cover < 2:
                stockout += 1
            elif cover < 4:
                lean += 1
            elif cover <= 8:
                healthy += 1
            elif cover <= 12:
                overstock += 1
            else:
                dead += 1
                
        if total == 0:
            return {"score": 50.0, "total": 0}
            
        score = (
            (healthy / total) * 1.0 +
            (lean / total) * 0.6 +
            (overstock / total) * 0.4
        ) * 100
        
        return {
            "score": score,
            "pct_stockout": stockout / total,
            "total": total
        }

    def _compute_alignment(self, lines) -> Dict[str, Any]:
        aligned = 0
        severely_under = 0
        total = 0
        for row in lines:
            # Only evaluate lines that had actual demand (not just fallback 0s)
            proj = row.ai_projections or {}
            raw_demand = proj.get("total_demand_before_cap", 0)
            if raw_demand <= 0:
                continue
            ratio = row.final_qty / raw_demand if raw_demand > 0 else 0
            if ratio < 0.3:
                severely_under += 1
            elif 0.7 <= ratio <= 1.2:
                aligned += 1
            total += 1
        
        if total == 0:
            return {"score": 50.0, "pct_aligned": 0.0, "pct_severely_under": 0.0}
        score = max(0, (aligned / total) * 100 - (severely_under / total) * 30)
        return {"score": score, "pct_aligned": aligned/total, "pct_severely_under": severely_under/total}

    def _compute_balance(self, lines) -> Dict[str, Any]:
        # Simplify balance by looking at spread across stores
        from collections import defaultdict
        store_qty = defaultdict(int)
        for row in lines:
            store_qty[row.store_id] += row.final_qty
            
        qtys = sorted(store_qty.values(), reverse=True)
        if not qtys:
            return {"score": 50.0}
            
        total_qty = sum(qtys)
        top5_pct = sum(qtys[:5]) / total_qty if total_qty > 0 else 0
        
        # Simple skew threshold scoring
        if top5_pct < 0.4:
            score = 100
        elif top5_pct < 0.6:
            score = 70
        else:
            score = 30
            
        return {"score": score, "top5_pct": top5_pct}
        
    def _compute_presentation(self, lines) -> Dict[str, Any]:
        from collections import defaultdict
        # Map store -> total units (since lines lacks style_id directly, store total is a good proxy for overall depth)
        # A more precise way is to use sku_id grouped by style, but style_code is in SKUs table.
        # We will approximate depth by grouping by (store_id, string_prefix_of_sku) or just store_id
        store_style_qty = defaultdict(int)
        for row in lines:
            if row.final_qty > 0:
                # We can group by store_id and ai_reasoning's narrative cap if possible, or just assume sku_id prefix is style
                # Actually, engine outputs style-level ai_projections!
                store_style_qty[row.store_id] += row.final_qty
                
        thin = 0
        marginal = 0
        adequate = 0
        for qty in store_style_qty.values():
            if qty <= 2:
                thin += 1
            elif qty <= 4:
                marginal += 1
            else:
                adequate += 1
                
        total = len(store_style_qty)
        if total == 0:
            return {"score": 50.0, "pct_thin": 0.0}
            
        score = ((adequate/total)*1.0 + (marginal/total)*0.5) * 100
        return {"score": score, "pct_thin": thin/total}
        
    def _compute_confidence(self, lines) -> Dict[str, Any]:
        high, med, low = 0, 0, 0
        total = 0
        for row in lines:
            # We only care about confidence for lines we actually allocated
            if row.final_qty > 0:
                c = row.ai_confidence or "LOW"
                if c == "HIGH": high += 1
                elif c == "MEDIUM": med += 1
                else: low += 1
                total += 1
                
        if total == 0:
            return {"score": 50.0}
        
        score = ((high/total)*1.0 + (med/total)*0.6 + (low/total)*0.2) * 100
        return {"score": score, "pct_low": low/total}

    def _apply_hard_penalties(self, base_score, cov_m, pres_m, lines) -> tuple[float, List[str]]:
        score = base_score
        penalties = []
        
        # P1: Stockout risk
        if cov_m.get("pct_stockout", 0) > 0.15:
            penalty = min(20, int(cov_m["pct_stockout"] * 50))
            score -= penalty
            penalties.append(f"-{penalty} pts: High stockout risk")
            
        # P2: Thin allocation
        pct_thin = pres_m.get("pct_thin", 0)
        if pct_thin > 0.40:
            penalty = min(15, int((pct_thin - 0.40) * 50))
            score -= penalty
            penalties.append(f"-{penalty} pts: {pct_thin*100:.0f}% of allocations are un-sellably thin")
            
        return score, penalties

def compute_decision(health_score: int, risks: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    if health_score >= 75:
        verdict = "APPROVE"
        action = "Safe to release. All metrics within acceptable range."
    elif health_score >= 55:
        verdict = "APPROVE_WITH_CAUTION"
        action = "Release to Tier 1-2 stores. Hold remainder centrally for Week 2 re-run."
    elif health_score >= 35:
        verdict = "REVIEW_REQUIRED"
        action = "Do not release. Manual override or strategy change required."
    else:
        verdict = "REJECT"
        action = "CRITICAL FAIL. Inventory too thin to sell. Change depth strategy."

    reasons = [r.get("explanation", r.get("type")) for r in risks[:3]]

    return {
        "verdict": verdict,
        "health_score": health_score,
        "why": reasons,
        "action": action,
        "hold_recommendation": 30 if verdict == "APPROVE_WITH_CAUTION" else 0,
    }

def generate_recommendations(risks: List[Dict[str, Any]], metrics: Dict[str, Any], context: Dict[str, Any]) -> List[Dict[str, Any]]:
    recs = []
    
    for risk in risks:
        if risk["type"] == "HARD_PENALTY" and "thin" in risk.get("explanation", ""):
            recs.append({
                "priority": 1,
                "action": "Activate MVA enforcement (min 3 units/store) under depth_first strategy",
                "impact": "Eliminates thin allocations, ensuring stores can actually display stock",
            })
        elif risk["type"] == "HARD_PENALTY" and "stockout" in risk.get("explanation", ""):
            recs.append({
                "priority": 2,
                "action": "Increase buffer for Tier 1 stores",
                "impact": "Prevents immediate stockouts at top volume doors",
            })
            
    # Default recs if empty
    if not recs:
        recs.append({
            "priority": 3,
            "action": "Monitor sell-through in Week 1-2",
            "impact": "Validates DNA analogue matching for new styles",
        })
        
    recs.sort(key=lambda x: x["priority"])
    return recs
