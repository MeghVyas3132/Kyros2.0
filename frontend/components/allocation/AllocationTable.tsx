"use client";

import { useCallback } from "react";

import { StatusBadge } from "@/components/shared/StatusBadge";
import { AllocationLine } from "@/types";
import { SimulationResult } from "@/types";

interface Props {
  lines: AllocationLine[];
  selectedLineId: string | null;
  quantities: Record<string, number>;
  simulations: Record<string, SimulationResult>;
  onSelect: (line: AllocationLine) => void;
  onChangeQty: (line: AllocationLine, qty: number) => void;
  onOverrideReason: (line: AllocationLine, reason: string) => void;
}

const OVERRIDE_REASONS = [
  "STORE_REQUEST",
  "VENDOR_CONSTRAINT",
  "LOCAL_EVENT",
  "GUT_FEEL",
  "OTHER",
];

export function AllocationTable({
  lines,
  selectedLineId,
  quantities,
  simulations,
  onSelect,
  onChangeQty,
  onOverrideReason,
}: Props) {
  const handleChange = useCallback(
    (line: AllocationLine, value: string) => {
      const num = Number(value);
      if (!Number.isNaN(num)) onChangeQty(line, num);
    },
    [onChangeQty]
  );

  return (
    <div className="overflow-auto rounded-xl border border-slate-300 bg-white/95 shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="sticky top-0 bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-600">
          <tr>
            <th className="px-3 py-2">Store</th>
            <th className="px-3 py-2">SKU</th>
            <th className="px-3 py-2">Rec</th>
            <th className="px-3 py-2">Final</th>
            <th className="px-3 py-2">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {lines.map((line) => {
            const current = quantities[line.id] ?? line.final_qty ?? line.ai_recommended_qty;
            const overridden = current !== line.ai_recommended_qty;
            const simulation = simulations[line.id];
            return (
              <tr
                key={line.id}
                onClick={() => onSelect(line)}
                className={`cursor-pointer border-t border-slate-200 ${
                  selectedLineId === line.id ? "bg-slate-100" : "hover:bg-slate-50/70"
                }`}
              >
                <td className="px-3 py-2">
                  <p className="font-medium text-slate-900">{line.store_name ?? line.store_id.slice(0, 8)}</p>
                  <p className="text-xs text-slate-600">
                    {line.store_code ?? "NA"}{line.store_city ? ` · ${line.store_city}` : ""}
                  </p>
                </td>
                <td className="px-3 py-2 text-slate-700">
                  <p className="font-medium text-slate-900">{line.style_name ?? line.sku_id.slice(0, 8)}</p>
                  <p className="text-xs text-slate-600">
                    {line.sku_size ?? "-"} · {line.sku_fabric ?? "-"} · {line.sku_code ?? "NA"}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1 text-[10px]">
                    {line.sku_store_group_rule ? (
                      <span className="rounded-full border border-amber-300 bg-amber-100 px-2 py-0.5 font-medium text-amber-900">
                        {line.sku_store_group_rule}
                      </span>
                    ) : null}
                    {line.sku_resolved_risk_level ? (
                      <span className="rounded-full border border-slate-300 bg-slate-100 px-2 py-0.5 font-medium text-slate-700">
                        {line.sku_resolved_risk_level}
                      </span>
                    ) : null}
                    {line.sku_story ? (
                      <span className="rounded-full border border-slate-300 bg-white px-2 py-0.5 font-medium text-slate-700">
                        {line.sku_story}
                      </span>
                    ) : null}
                  </div>
                  {line.grn_available_for_first_allocation != null && line.grn_units_received != null ? (
                    <p className="mt-1 text-[11px] text-slate-500">
                      Available {line.grn_available_for_first_allocation} / Received {line.grn_units_received}
                    </p>
                  ) : null}
                </td>
                <td className="px-3 py-2 font-semibold text-slate-900">{line.ai_recommended_qty}</td>
                <td className="px-3 py-2">
                  <input
                    className="w-20 rounded-md border border-slate-400 bg-white px-2 py-1 font-medium text-slate-900 shadow-sm outline-none focus:border-slate-700"
                    type="number"
                    value={current}
                    onClick={(event) => event.stopPropagation()}
                    onChange={(event) => handleChange(line, event.target.value)}
                  />
                  {simulation ? (
                    <div className="mt-1 text-xs text-slate-600">
                      {simulation.weeks_cover} weeks cover · ~
                      {Math.round(simulation.projected_sellthrough_eow * 100)}% sell-through
                      {simulation.fills_display_capacity ? " · Fills display capacity" : ""}
                    </div>
                  ) : null}
                  {overridden ? (
                    <select
                      className="mt-1 block w-full rounded-md border border-slate-300 bg-slate-50 px-2 py-1 text-xs text-slate-800 outline-none focus:border-slate-600"
                      value={line.override_reason ?? "STORE_REQUEST"}
                      onClick={(event) => event.stopPropagation()}
                      onChange={(event) => onOverrideReason(line, event.target.value)}
                    >
                      {OVERRIDE_REASONS.map((reason) => (
                        <option key={reason} value={reason}>
                          {reason}
                        </option>
                      ))}
                    </select>
                  ) : null}
                </td>
                <td className="px-3 py-2">
                  <StatusBadge label={line.ai_confidence ?? "LOW"} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
