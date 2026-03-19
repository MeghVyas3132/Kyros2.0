"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { AllocationTable } from "@/components/allocation/AllocationTable";
import { ExplainabilityPanel } from "@/components/allocation/ExplainabilityPanel";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { apiRequest } from "@/lib/api";
import { useGRN } from "@/lib/hooks/useGrns";
import { useAllocationSession } from "@/lib/hooks/useAllocation";
import { AllocationLine, AllocationSession, SimulationResult, StoryConcentration } from "@/types";

const FRIENDLY_STATUS: Record<string, string> = {
  DRAFT: "Draft",
  GENERATING: "Generating…",
  UNDER_REVIEW: "Under Review",
  APPROVED: "Approved",
  DISPATCHED: "Dispatched",
};

export default function GRNDetailPage() {
  const params = useParams<{ id: string }>();
  const grnId = params.id;

  const { data: grn } = useGRN(grnId);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const { data: allocation, mutate } = useAllocationSession(sessionId);

  const [selectedLine, setSelectedLine] = useState<AllocationLine | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [simulations, setSimulations] = useState<Record<string, SimulationResult>>({});
  const [storyConcentration, setStoryConcentration] = useState<StoryConcentration[]>([]);
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const simTimerRef = useRef<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const status = allocation?.session?.status ?? sessionStatus ?? (grn?.status === "RECEIVED" ? "DRAFT" : "UNDER_REVIEW");

  // Poll for session status while GENERATING
  useEffect(() => {
    if (status !== "GENERATING" || !sessionId) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    pollRef.current = setInterval(() => {
      void apiRequest<{ id: string; status: string }>(`/api/v1/allocation/sessions/by-grn/${grnId}`)
        .then((session) => {
          setSessionStatus(session.status);
          if (session.status !== "GENERATING") {
            void mutate();
            if (pollRef.current) clearInterval(pollRef.current);
          }
        })
        .catch(() => {});
    }, 3000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [status, sessionId, grnId, mutate]);

  useEffect(() => {
    if (!grnId) return;
    setCheckingSession(true);
    void apiRequest<{ id: string; status: string }>(`/api/v1/allocation/sessions/by-grn/${grnId}`)
      .then((session) => {
        setSessionId(session.id);
        setSessionStatus(session.status);
        setCheckingSession(false);
      })
      .catch(() => {
        // No session exists yet - this is normal for newly received stock
        setSessionId(null);
        setSessionStatus(null);
        setCheckingSession(false);
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
      const session = await apiRequest<AllocationSession & { status: string }>(
        "/api/v1/allocation/generate",
        {
          method: "POST",
          body: JSON.stringify({ grn_id: grnId }),
        }
      );
      setSessionId(session.id);
      setSessionStatus(session.status);
      // polling useEffect will take over from here
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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            {grn ? `${grn.grn_code}` : "Stock Receipt"}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {grn
              ? `${Number(grn.total_units).toLocaleString()} total units · ${grn.total_skus} styles`
              : "Loading..."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge label={FRIENDLY_STATUS[status] ?? status} />
          {!sessionId || status === "DRAFT" ? (
            <button
              onClick={handleGenerate}
              disabled={loading || status === "GENERATING"}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50 transition-colors flex items-center gap-2"
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                <path d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" />
              </svg>
              {loading || status === "GENERATING" ? "Generating…" : "Generate Allocation"}
            </button>
          ) : null}
          {sessionId && status === "UNDER_REVIEW" ? (
            <button
              onClick={handleApprove}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 transition-colors flex items-center gap-2"
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
              </svg>
              Approve All
            </button>
          ) : null}
          {canExport ? (
            <button
              onClick={handleExport}
              className="rounded-md border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 transition-colors flex items-center gap-2"
            >
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" />
              </svg>
              Export Transfer List
            </button>
          ) : null}
        </div>
      </div>

      {/* Allocation content */}
      {checkingSession ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <svg className="mx-auto h-8 w-8 animate-spin text-slate-400" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <p className="mt-3 font-medium text-slate-700">Checking for existing allocations…</p>
          <p className="mt-1 text-sm text-slate-500">
            Retrieving allocation status for {grn?.grn_code ?? "this shipment"}.
          </p>
        </div>
      ) : status === "GENERATING" ? (
        <div className="rounded-xl border border-dashed border-blue-200 bg-blue-50 px-6 py-16 text-center">
          <svg className="mx-auto h-8 w-8 animate-spin text-blue-500" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
          </svg>
          <p className="mt-3 font-medium text-blue-800">Generating allocation…</p>
          <p className="mt-1 text-sm text-blue-600">
            The AI engine is distributing {grn ? `${Number(grn.total_units).toLocaleString()} units across ${grn.total_skus ?? ""} styles` : "stock"}.
            This may take a few minutes for large shipments.
          </p>
          <div className="mx-auto mt-4 h-1.5 w-48 overflow-hidden rounded-full bg-blue-100">
            <div className="h-full w-1/3 animate-pulse rounded-full bg-blue-500" />
          </div>
        </div>
      ) : !sessionId || status === "DRAFT" ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
          <svg className="mx-auto h-8 w-8 text-slate-400" fill="currentColor" viewBox="0 0 20 20">
            <path d="M13 6a3 3 0 11-6 0 3 3 0 016 0zM18 8a2 2 0 11-4 0 2 2 0 014 0zM14 15a4 4 0 00-8 0v2h8v-2zM6 8a2 2 0 11-4 0 2 2 0 014 0zM16 18v-2a4 4 0 00-8 0v2h8z" />
          </svg>
          <p className="mt-2 font-medium text-slate-700">Ready to allocate</p>
          <p className="mt-1 text-sm text-slate-500">
            Click <strong>Generate Allocation</strong> above and the AI engine will distribute stock across your stores based on demand, grades, and size curves.
          </p>
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
