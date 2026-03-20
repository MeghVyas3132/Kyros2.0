"use client";

import { AllocationLine, StoryConcentration } from "@/types";

interface Props {
  line: AllocationLine | null;
  storyConcentration?: StoryConcentration[];
}

export function ExplainabilityPanel({ line, storyConcentration = [] }: Props) {
  if (!line) {
    return (
      <div className="rounded-xl border border-slate-300 bg-white/95 p-4 text-sm text-slate-500 shadow-sm">
        Select a row to view AI reasoning.
      </div>
    );
  }

  const reasoning = line.ai_reasoning;
  const toNumber = (value: number | string | null | undefined, fallback = 0): number => {
    if (typeof value === "number") return value;
    if (typeof value === "string") {
      const token = value.trim().split(" ", 1)[0].replace("%", "");
      const parsed = Number(token);
      return Number.isFinite(parsed) ? parsed : fallback;
    }
    return fallback;
  };

  const storeRos = toNumber(reasoning.store_ros_attribute, reasoning.weekly_ros ?? 0);
  const clusterRos = toNumber(reasoning.cluster_avg_ros_attribute, storeRos);
  const minusCover = reasoning.weeks_cover_minus_25 ?? reasoning.weeks_cover_at_minus_25pct;
  const plusCover = reasoning.weeks_cover_plus_25 ?? reasoning.weeks_cover_at_plus_25pct;
  const rosDelta = reasoning.ros_vs_cluster_pct >= 0 ? `+${reasoning.ros_vs_cluster_pct}` : `${reasoning.ros_vs_cluster_pct}`;

  return (
    <div className="rounded-xl border border-slate-300 bg-white/95 p-4 shadow-sm">
      <h3 className="mb-1 text-sm font-semibold uppercase tracking-[0.08em] text-slate-700">Explainability</h3>
      <p className="mb-4 text-sm text-slate-900">
        {line.store_name ?? line.store_code} · {line.style_name ?? line.sku_code} {line.sku_size ?? ""}
      </p>

      <div className="space-y-3 text-sm">
        <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
          <p className="font-medium text-slate-900">Demand Signal</p>
          <p className="text-slate-700">
            ROS {storeRos.toFixed(1)} vs cluster {clusterRos.toFixed(1)} ({rosDelta}%)
          </p>
          <p className="text-slate-700">Current cover {reasoning.current_stock_cover_days.toFixed(1)} days</p>
          {reasoning.narrative_demand ? <p className="mt-1 text-slate-600">{reasoning.narrative_demand}</p> : null}
          {reasoning.stockout_correction_applied ? (
            <p className="mt-1 text-amber-700">
              Stockout-corrected ROS applied{reasoning.lost_sales_estimate != null ? ` (lost sales est. ${reasoning.lost_sales_estimate})` : ""}.
            </p>
          ) : null}
        </div>

        <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
          <p className="font-medium text-slate-900">Projection</p>
          <p className="text-slate-700">Recommended cover {reasoning.weeks_cover_at_recommended.toFixed(1)} weeks</p>
          <p className="text-slate-700">
            Minus 25%: {minusCover.toFixed(1)} weeks · Plus 25%: {plusCover.toFixed(1)} weeks
          </p>
          <p className="text-slate-700">Season remaining {reasoning.season_weeks_remaining} weeks</p>
          {reasoning.cover_target_weeks != null ? (
            <p className="text-slate-700">Target cover used by model: {reasoning.cover_target_weeks} weeks</p>
          ) : null}
          {reasoning.narrative_adjustments ? <p className="mt-1 text-slate-600">{reasoning.narrative_adjustments}</p> : null}
        </div>

        <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
          <p className="font-medium text-slate-900">Constraints</p>
          <p className="text-slate-700">Display capacity available: {reasoning.display_capacity_available}</p>
          <p className="text-slate-700">
            Climate match: {reasoning.climate_match ? "Yes" : "No"} · Stockout risk at lower qty:{" "}
            {reasoning.stockout_risk_at_lower_qty ? "High" : "Low"}
          </p>
          {reasoning.narrative_cap ? <p className="mt-1 text-slate-600">{reasoning.narrative_cap}</p> : null}
        </div>

        <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
          <p className="font-medium text-slate-900">Confidence</p>
          <p className="text-slate-700">
            {line.ai_confidence ?? "LOW"} confidence from {reasoning.data_sample_size} comparable store-weeks
          </p>
          <p className="text-slate-700">{reasoning.confidence_basis}</p>
        </div>

        {reasoning.category_affinity || reasoning.fabric_affinity ? (
          <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
            <p className="font-medium text-slate-900">Store Profile</p>
            <p className="text-slate-700">
              Category affinity: {reasoning.category_affinity ?? "N/A"} · Fabric affinity: {reasoning.fabric_affinity ?? "N/A"}
            </p>
          </div>
        ) : null}

        <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
          <p className="font-medium text-slate-900">Allocation Ceiling</p>
          <p className="text-slate-700">Total received: {line.grn_units_received ?? 0}</p>
          {(line.grn_reservations ?? []).length > 0 ? (
            <div className="mt-1 space-y-1 text-slate-700">
              {(line.grn_reservations ?? []).map((reservation) => (
                <p key={`${reservation.code}-${reservation.label}`}>
                  {reservation.label}: {reservation.reserved_qty}
                </p>
              ))}
            </div>
          ) : (
            <div className="mt-1 space-y-1 text-slate-700">
              <p>E-Commerce reserve: {line.grn_ecom_reserved_qty ?? 0}</p>
              <p>ARS reserve: {line.grn_ars_reserved_qty ?? 0}</p>
            </div>
          )}
          <p className="mt-1 text-slate-900">
            Available for first allocation: {line.grn_available_for_first_allocation ?? 0}
          </p>
        </div>

        <div className="rounded-md border border-slate-200 bg-slate-50/80 p-3">
          <p className="font-medium text-slate-900">Story Concentration</p>
          {storyConcentration.length === 0 ? (
            <p className="text-slate-700">No story concentration data for this store yet.</p>
          ) : (
            <div className="mt-1 space-y-1">
              {storyConcentration.map((item) => (
                <p key={item.story} className="text-slate-700">
                  {item.story}: {item.style_count} styles{" "}
                  {item.is_high ? (
                    <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-900">
                      High
                    </span>
                  ) : null}
                </p>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
