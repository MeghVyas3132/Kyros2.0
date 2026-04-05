"use client";

import { AllocationLine, AllocationReasoning } from "@/types";

interface Props {
  line: AllocationLine | null;
  skuName?: string;
  styleRiskGroup?: string;
}

const SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL", "2XL", "3XL", "28", "30", "32", "34", "36", "38", "40", "42"];

export function ExplainabilityPanel({ line, skuName, styleRiskGroup }: Props) {
  if (!line) {
    return (
      <div className="p-4 text-sm text-slate-500">
        Select a row to view reasoning.
      </div>
    );
  }

  const r = line.ai_reasoning as AllocationReasoning | null;
  if (!r) {
    return <div className="p-4 text-sm text-slate-500">No reasoning data available for this line.</div>;
  }

  const reasoning = r;
  const ros = reasoning?.weekly_ros ?? reasoning?.raw_weekly_ros ?? 0;
  const rawRos = reasoning?.raw_weekly_ros ?? reasoning?.weekly_ros ?? 0;
  const excluded = reasoning?.excluded_by_capacity ?? false;
  const exclusionReason = reasoning?.exclusion_reason ?? null;
  const coverTargetWeeks = reasoning?.cover_target_weeks ?? 0;
  const storeGrade = reasoning?.store_grade ?? "-";
  const weeksCoverRecommended = reasoning?.weeks_cover_at_recommended ?? 0;
  const stockoutWeek = reasoning?.stockout_week ?? null;
  const lostSalesEstimate = reasoning?.lost_sales_estimate ?? null;
  const narrativeDemand = reasoning?.narrative_demand ?? "Demand narrative unavailable.";
  const confidenceBasis = reasoning?.confidence_basis ?? "Confidence basis unavailable.";
  const narrativeAdjustments = reasoning?.narrative_adjustments ?? "Adjustment narrative unavailable.";
  const narrativeCap = reasoning?.narrative_cap ?? "Inventory narrative unavailable.";
  const sizeDistributionSource = reasoning?.size_distribution_source ?? "unknown";

  const sizeSplitEntries = Object.entries(reasoning?.size_split ?? {}).sort(([a], [b]) => {
    const ai = SIZE_ORDER.indexOf(a);
    const bi = SIZE_ORDER.indexOf(b);
    return (ai === -1 ? 999 : ai) - (bi === -1 ? 999 : bi);
  });
  const sizeSplitTotal = sizeSplitEntries.reduce((sum, [, n]) => sum + n, 0);

  return (
    <div className="space-y-5 p-4 text-sm">
      <div className="grid grid-cols-2 gap-3 rounded-lg border bg-slate-50/70 p-4">
        <div>
          <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Target Cover</p>
          <p className="text-3xl font-bold tabular-nums">{coverTargetWeeks}w</p>
          <p className="mt-1 text-xs text-slate-500">{styleRiskGroup ?? "-"} × Grade {storeGrade}</p>
        </div>
        <div>
          <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Allocated</p>
          <p className="text-3xl font-bold tabular-nums">{weeksCoverRecommended}w</p>
          <p className="mt-1 text-xs text-slate-500">at {line.final_qty} units</p>
        </div>
      </div>

      {(reasoning?.is_stockout_corrected ?? false) && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-amber-800">Stockout correction applied</p>
          <p className="text-amber-700">
            Store stocked out around week {stockoutWeek ?? "?"}.
            {lostSalesEstimate != null ? <> Estimated {Math.round(lostSalesEstimate)} lost units.</> : null} Demand corrected from <strong>{rawRos.toFixed(1)}</strong> to <strong>{ros.toFixed(1)}</strong> units/week.
          </p>
        </div>
      )}

      <div>
        <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Demand Basis</p>
        <p className="text-slate-900 leading-relaxed">{narrativeDemand}</p>
        <p className="mt-1 text-xs text-slate-500">{confidenceBasis}</p>
      </div>

      <div>
        <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Store Adjustment</p>
        <p className="text-slate-900 leading-relaxed">{narrativeAdjustments}</p>
      </div>

      <div>
        <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Inventory</p>
        <p className="text-slate-900 leading-relaxed">{narrativeCap}</p>
      </div>

      {sizeSplitEntries.length > 0 && (
        <div>
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">
            Size Split <span className="normal-case font-normal">({sizeDistributionSource.replace(/_/g, " ")})</span>
          </p>
          <div className="space-y-1.5">
            {sizeSplitEntries.map(([size, qty]) => {
              const pct = sizeSplitTotal > 0 ? Math.round((qty / sizeSplitTotal) * 100) : 0;
              return (
                <div key={size} className="flex items-center gap-2">
                  <span className="w-7 shrink-0 text-right text-xs text-slate-500">{size}</span>
                  <div className="h-1.5 flex-1 rounded-full bg-slate-200">
                    <div className="h-1.5 rounded-full bg-slate-900 transition-all" style={{ width: `${pct}%` }} />
                  </div>
                  <span className="w-16 shrink-0 text-right text-xs text-slate-500">{qty} ({pct}%)</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {excluded && exclusionReason && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3">
          <p className="mb-1 text-xs font-medium uppercase tracking-wide text-red-800">Excluded by display capacity</p>
          <p className="text-red-700">{exclusionReason}</p>
        </div>
      )}

      {/* Affinity signals — show when populated by Phase 2 engine */}
      {(r.category_affinity != null || r.fabric_affinity != null) && (
        <div className="border-t pt-4 space-y-2">
          <p className="text-xs uppercase tracking-wide text-slate-500">Store affinity</p>
          {r.category_affinity != null && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-600">
                {r.category_affinity_label ?? "Category"} affinity
              </span>
              <span className={`font-semibold ${
                r.category_affinity > 1.1 ? "text-emerald-700" :
                r.category_affinity < 0.9 ? "text-amber-700" : "text-slate-700"
              }`}>
                {r.category_affinity.toFixed(2)}×
              </span>
            </div>
          )}
          {r.fabric_affinity != null && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-600">
                {r.fabric_affinity_label ?? "Fabric"} affinity
              </span>
              <span className={`font-semibold ${
                r.fabric_affinity > 1.1 ? "text-emerald-700" :
                r.fabric_affinity < 0.9 ? "text-amber-700" : "text-slate-700"
              }`}>
                {r.fabric_affinity.toFixed(2)}×
              </span>
            </div>
          )}
          {r.affinity_adjustment_units != null && r.affinity_adjustment_units !== 0 && (
            <p className="text-xs text-slate-500">
              Affinity adjusted demand by {r.affinity_adjustment_units > 0 ? "+" : ""}
              {r.affinity_adjustment_units} units
            </p>
          )}
        </div>
      )}

      {/* Style DNA match — show when populated */}
      {r.style_dna_match && (
        <div className="border-t pt-4 space-y-1">
          <p className="text-xs uppercase tracking-wide text-slate-500">Style DNA match</p>
          <p className="text-sm text-slate-700">
            Matched to <span className="font-medium font-mono text-slate-900">
              {r.style_dna_match.matched_style_code}
            </span>
          </p>
          {r.style_dna_match.similarity_score != null && (
            <p className="text-xs text-slate-500">
              {Math.round(r.style_dna_match.similarity_score * 100)}% similar
            </p>
          )}
        </div>
      )}

      {/* Cannibalization — show when applied */}
      {r.cannibalization_factor != null && r.cannibalization_factor < 1 && (
        <div className="rounded-md border border-slate-200 bg-slate-50 p-3 border-t mt-2">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-600 mb-1">
            Story concentration
          </p>
          <p className="text-xs text-slate-700">{r.cannibalization_reason}</p>
          <p className="text-xs text-slate-500 mt-0.5">
            Factor applied: {r.cannibalization_factor.toFixed(2)}×
            {r.colourways_in_story_at_store != null
              ? ` (${r.colourways_in_story_at_store} competing colourways)`
              : ""}
          </p>
        </div>
      )}

      {/* Placeholder — only shown when nothing above is populated */}
      {r.category_affinity == null &&
       r.fabric_affinity == null &&
       !r.style_dna_match &&
       r.cannibalization_factor == null && (
        <div className="border-t pt-4 opacity-40">
          <p className="text-xs text-slate-500">
            Affinity and DNA signals will appear here once store profiles are built.
          </p>
        </div>
      )}
    </div>
  );
}
