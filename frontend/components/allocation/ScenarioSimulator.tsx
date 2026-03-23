"use client";

import { useCallback, useMemo, useState } from "react";

import { apiRequest } from "@/lib/api";
import { AllocationLine, AllocationReasoning, SimulationResult } from "@/types";

interface Props {
  line: AllocationLine;
}

export function ScenarioSimulator({ line }: Props) {
  const [qty, setQty] = useState<number>(line.final_qty ?? line.ai_recommended_qty);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [loading, setLoading] = useState(false);

  const reasoning = (line.ai_reasoning as AllocationReasoning | null) ?? null;
  const ros = Number(reasoning?.weekly_ros ?? 0);
  const coverTarget = Number(reasoning?.cover_target_weeks ?? 0);
  const previewWeeks = useMemo(() => (ros > 0 ? (qty / ros).toFixed(1) : "-"), [qty, ros]);

  const simulate = useCallback(async () => {
    if (qty < 0 || qty > 9999) return;
    setLoading(true);
    try {
      const data = await apiRequest<SimulationResult>("/api/v1/allocation/simulate", {
        method: "POST",
        body: JSON.stringify({
          store_id: line.store_id,
          sku_id: line.sku_id,
          quantity: qty,
        }),
      });
      setResult(data);
    } catch {
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [line.sku_id, line.store_id, qty]);

  return (
    <div className="space-y-3 p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">Scenario - What If?</p>
      <div className="flex items-center gap-3">
        <input
          type="number"
          min={0}
          max={9999}
          value={qty}
          onChange={(e) => {
            const v = parseInt(e.target.value, 10);
            if (!Number.isNaN(v)) setQty(v);
          }}
          className="w-24 rounded border px-2 py-1 text-sm tabular-nums"
        />
        <span className="text-sm text-slate-500">units</span>
        <button
          onClick={() => void simulate()}
          disabled={loading}
          className="rounded bg-slate-900 px-3 py-1 text-xs text-white disabled:opacity-50"
        >
          {loading ? "Simulating..." : "Simulate"}
        </button>
      </div>

      {ros > 0 && (
        <p className="text-xs text-slate-500">
          Preview: {previewWeeks}w cover
          {coverTarget > 0 ? (
            <span className={parseFloat(previewWeeks) >= coverTarget ? " text-green-700" : " text-amber-700"}>
              {" "}({parseFloat(previewWeeks) >= coverTarget ? ">=" : "<"} {coverTarget}w target)
            </span>
          ) : null}
        </p>
      )}

      {result && (
        <div className="rounded bg-slate-100 p-3 text-xs space-y-1">
          <p>
            <strong>{result.weeks_cover.toFixed(1)}w cover</strong> at {result.quantity} units
          </p>
          {result.notes ? <p className="text-slate-500">{result.notes}</p> : null}
        </div>
      )}
    </div>
  );
}
