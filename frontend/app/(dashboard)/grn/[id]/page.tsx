"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { AllocationTable } from "@/components/allocation/AllocationTable";
import { ExplainabilityPanel } from "@/components/allocation/ExplainabilityPanel";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/Button";
import { apiRequest } from "@/lib/api";
import { useGRN } from "@/lib/hooks/useGrns";
import { useAllocationSession } from "@/lib/hooks/useAllocation";
import { AllocationLine, AllocationSession, SimulationResult, StoryConcentration } from "@/types";

export default function GRNDetailPage() {
  const params = useParams<{ id: string }>();
  const grnId = params.id;

  const { data: grn } = useGRN(grnId);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const { data: allocation, mutate } = useAllocationSession(sessionId);

  const [selectedLine, setSelectedLine] = useState<AllocationLine | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [simulations, setSimulations] = useState<Record<string, SimulationResult>>({});
  const [storyConcentration, setStoryConcentration] = useState<StoryConcentration[]>([]);
  const [loading, setLoading] = useState(false);
  const simTimerRef = useRef<number | null>(null);

  const status = allocation?.session?.status ?? (grn?.status === "RECEIVED" ? "DRAFT" : "UNDER_REVIEW");

  useEffect(() => {
    if (!grnId) return;
    void apiRequest<{ id: string }>(`/api/v1/allocation/sessions/by-grn/${grnId}`)
      .then((session) => setSessionId(session.id))
      .catch(() => {
        setSessionId(null);
      });
  }, [grnId]);

  useEffect(() => {
    if (!allocation?.lines) return;
    const next: Record<string, number> = {};
    allocation.lines.forEach((line) => {
      next[line.id] = line.final_qty ?? line.ai_recommended_qty;
    });
    setQuantities(next);
  }, [allocation?.lines]);

  useEffect(
    () => () => {
      if (simTimerRef.current) {
        window.clearTimeout(simTimerRef.current);
      }
    },
    []
  );

  useEffect(() => {
    if (!sessionId || !selectedLine) {
      setStoryConcentration([]);
      return;
    }
    void apiRequest<StoryConcentration[]>(
      `/api/v1/allocation/sessions/${sessionId}/stores/${selectedLine.store_id}/story-concentration`
    )
      .then((rows) => setStoryConcentration(rows))
      .catch(() => setStoryConcentration([]));
  }, [sessionId, selectedLine]);

  const handleGenerate = async () => {
    if (!grnId) return;
    setLoading(true);
    try {
      const session = await apiRequest<AllocationSession>("/api/v1/allocation/generate", {
        method: "POST",
        body: JSON.stringify({ grn_id: grnId }),
      });
      setSessionId(session.id);
    } finally {
      setLoading(false);
    }
  };

  const runSimulation = useCallback(async (line: AllocationLine, quantity: number) => {
    const result = await apiRequest<SimulationResult>("/api/v1/allocation/simulate", {
      method: "POST",
      body: JSON.stringify({
        store_id: line.store_id,
        sku_id: line.sku_id,
        quantity,
      }),
    });
    setSimulations((prev) => ({ ...prev, [line.id]: result }));
  }, []);

  const handleChangeQty = useCallback(
    (line: AllocationLine, qty: number) => {
      setQuantities((prev) => ({ ...prev, [line.id]: qty }));
      if (simTimerRef.current) {
        window.clearTimeout(simTimerRef.current);
      }
      simTimerRef.current = window.setTimeout(() => {
        void runSimulation(line, qty);
      }, 300);

      void apiRequest(`/api/v1/allocation/lines/${line.id}`, {
        method: "PUT",
        body: JSON.stringify({
          final_qty: qty,
          override_reason: qty !== line.ai_recommended_qty ? line.override_reason ?? "STORE_REQUEST" : null,
          override_notes: line.override_notes,
        }),
      }).then(() => mutate());
    },
    [mutate, runSimulation]
  );

  const handleOverrideReason = useCallback(
    (line: AllocationLine, reason: string) => {
      const qty = quantities[line.id] ?? line.ai_recommended_qty;
      void apiRequest(`/api/v1/allocation/lines/${line.id}`, {
        method: "PUT",
        body: JSON.stringify({
          final_qty: qty,
          override_reason: reason,
          override_notes: line.override_notes,
        }),
      }).then(() => mutate());
    },
    [mutate, quantities]
  );

  const handleApprove = async () => {
    if (!sessionId) return;
    await apiRequest(`/api/v1/allocation/sessions/${sessionId}/approve`, { method: "POST" });
    await mutate();
  };

  const canExport = status === "APPROVED" && !!sessionId;

  const handleExport = async () => {
    if (!sessionId) return;
    const token = localStorage.getItem("kyros_access_token");
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/v1/allocation/sessions/${sessionId}/export`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} }
    );
    if (!response.ok) return;
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `allocation-${sessionId}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title={grn ? `${grn.grn_code} · ${grn.total_units} units · ${grn.total_skus} SKUs` : "GRN"}
        subtitle="Allocation review"
        actions={
          <>
            <StatusBadge label={status} />
            {!sessionId ? (
              <Button onClick={handleGenerate} disabled={loading}>
                {loading ? "Generating..." : "Generate Allocation"}
              </Button>
            ) : null}
            {sessionId ? (
              <Button className="bg-emerald-700 text-white hover:bg-emerald-800" onClick={handleApprove}>
                Approve All
              </Button>
            ) : null}
            {canExport ? (
              <button
                onClick={handleExport}
                className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-100"
              >
                Export Transfer List
              </button>
            ) : null}
          </>
        }
      />

      {!sessionId ? (
        <div className="rounded-xl border border-slate-300 bg-white p-6 text-sm text-slate-600 shadow-sm">
          Click <strong>Generate Allocation</strong> to run the engine.
        </div>
      ) : (
        <div className="grid grid-cols-12 gap-4">
          <div className="col-span-8">
            <AllocationTable
              lines={allocation?.lines ?? []}
              selectedLineId={selectedLine?.id ?? null}
              quantities={quantities}
              onSelect={(line) => setSelectedLine(line)}
              onChangeQty={handleChangeQty}
              onOverrideReason={handleOverrideReason}
              simulations={simulations}
            />
          </div>
          <div className="col-span-4">
            <ExplainabilityPanel line={selectedLine} storyConcentration={storyConcentration} />
          </div>
        </div>
      )}
    </div>
  );
}
