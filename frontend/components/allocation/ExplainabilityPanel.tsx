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

      <div className="space-y-2 border-t pt-4 opacity-50">
        <p className="text-xs uppercase tracking-wide text-slate-500">Coming next</p>
        <p className="text-xs text-slate-500">Style DNA matching · Category and fabric affinity · Cannibalization scoring</p>
      </div>
    </div>
  );
}
