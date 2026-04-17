"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { AllocationTable } from "@/components/allocation/AllocationTable";
import { ExplainabilityPanel } from "@/components/allocation/ExplainabilityPanel";
import { ScenarioSimulator } from "@/components/allocation/ScenarioSimulator";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { ApiError, apiRequest } from "@/lib/api";
import { useGRN } from "@/lib/hooks/useGrns";
import { useAllocationSession } from "@/lib/hooks/useAllocation";
import {
  AllocationBenchmarkReport,
  AllocationInsights,
  AllocationLine,
  AllocationSession,
  SimulationResult,
} from "@/types";

const FRIENDLY_STATUS: Record<string, string> = {
  DRAFT: "Draft",
  GENERATING: "Generating…",
  FAILED: "Failed",
  UNDER_REVIEW: "Under Review",
  APPROVED: "Approved",
  DISPATCHED: "Dispatched",
};

function errorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

export default function GRNDetailPage() {
  const params = useParams<{ id: string }>();
  const grnId = params.id;

  const { data: grn } = useGRN(grnId);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "lines">("overview");
  const [lineLimit, setLineLimit] = useState(500);
  const {
    data: allocation,
    error: allocationError,
    mutate,
  } = useAllocationSession(sessionId, { lineLimit, lineOffset: 0 });

  const [selectedLine, setSelectedLine] = useState<AllocationLine | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [simulations, setSimulations] = useState<Record<string, SimulationResult>>({});
  const [insights, setInsights] = useState<AllocationInsights | null>(null);
  const [benchmark, setBenchmark] = useState<AllocationBenchmarkReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [statusRefreshError, setStatusRefreshError] = useState<string | null>(null);
  const simTimerRef = useRef<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const status = allocation?.session?.status ?? sessionStatus ?? (grn?.status === "RECEIVED" ? "DRAFT" : "UNDER_REVIEW");

  useEffect(() => {
    setLineLimit(500);
  }, [sessionId]);

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
          setCheckingSession(false);
          setStatusRefreshError(null);
          setSessionStatus(session.status);
          if (session.status !== "GENERATING") {
            void mutate();
            if (pollRef.current) clearInterval(pollRef.current);
          }
        })
        .catch((error) => {
          setStatusRefreshError(errorMessage(error, "Could not refresh allocation status. Retrying..."));
        });
    }, 5000);
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
        setStatusRefreshError(null);
        setActionError(null);
        setCheckingSession(false);
      })
      .catch((error) => {
        const message = errorMessage(error, "Could not check allocation session status.");
        const isMissingSession =
          error instanceof ApiError &&
          (error.code === "HTTP_404" || error.code === "NOT_FOUND");
        if (isMissingSession) {
          // No session exists yet - this is normal for newly received stock
          setSessionId(null);
          setSessionStatus(null);
          setActionError(null);
        } else {
          setActionError(message);
        }
        setCheckingSession(false);
      });
  }, [grnId]);

  // Fetch insights when session is under review or approved
  useEffect(() => {
    if (!sessionId) return;
    if (!["UNDER_REVIEW", "APPROVED"].includes(status)) return;
    let cancelled = false;
    void apiRequest<AllocationInsights>(`/api/v1/allocation/${sessionId}/insights`)
      .then((data) => {
        if (!cancelled) setInsights(data);
      })
      .catch(() => {
        if (!cancelled) setInsights(null);
      });
    return () => { cancelled = true; };
  }, [sessionId, status]);

  useEffect(() => {
    if (!sessionId || !["UNDER_REVIEW", "APPROVED", "DISPATCHED"].includes(status)) {
      setBenchmark(null);
      return;
    }
    let cancelled = false;
    void apiRequest<AllocationBenchmarkReport>(`/api/v1/allocation/sessions/${sessionId}/benchmark`)
      .then((data) => {
        if (!cancelled) setBenchmark(data);
      })
      .catch(() => {
        if (!cancelled) setBenchmark(null);
      });
    return () => { cancelled = true; };
  }, [sessionId, status]);

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
      setActionError(null);
      // We already have a concrete session now, so stop showing the
      // "checking existing allocations" state even if initial lookup lags.
      setCheckingSession(false);
      // polling useEffect will take over from here
    } catch (error) {
      setActionError(errorMessage(error, "Could not start allocation generation."));
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
    },
    [runSimulation]
  );

  const handleCommitQty = useCallback(
    (line: AllocationLine, qty: number) => {
      void apiRequest(`/api/v1/allocation/lines/${line.id}`, {
        method: "PUT",
        body: JSON.stringify({
          final_qty: qty,
          override_reason: qty !== line.ai_recommended_qty ? line.override_reason ?? "STORE_REQUEST" : null,
          override_notes: line.override_notes,
        }),
      })
        .then(() => {
          setActionError(null);
          void mutate();
        })
        .catch((error) => {
          setActionError(errorMessage(error, "Could not save quantity override."));
        });
    },
    [mutate]
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
      })
        .then(() => {
          setActionError(null);
          void mutate();
        })
        .catch((error) => {
          setActionError(errorMessage(error, "Could not save override reason."));
        });
    },
    [mutate, quantities]
  );

  const handleApprove = async () => {
    if (!sessionId) return;
    try {
      await apiRequest(`/api/v1/allocation/sessions/${sessionId}/approve`, { method: "POST" });
      setActionError(null);
      await mutate();
    } catch (error) {
      setActionError(errorMessage(error, "Could not approve this allocation session."));
    }
  };

  const canExport = status === "APPROVED" && !!sessionId;

  const handleExport = async () => {
    if (!sessionId) return;
    const token = localStorage.getItem("kyros_access_token");
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/v1/allocation/sessions/${sessionId}/export`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} }
      );
      if (!response.ok) {
        setActionError("Could not export transfer list.");
        return;
      }
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `allocation-${sessionId}.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
      setActionError(null);
    } catch {
      setActionError("Could not export transfer list.");
    }
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

      {actionError ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <p className="text-sm font-medium text-red-900">Action failed</p>
          <p className="mt-1 text-xs text-red-700">{actionError}</p>
        </div>
      ) : null}

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
          {statusRefreshError ? (
            <p className="mt-3 text-xs text-blue-700">{statusRefreshError}</p>
          ) : null}
        </div>
      ) : status === "FAILED" ? (
        <div className="rounded-xl border border-dashed border-red-300 bg-red-50 px-6 py-16 text-center">
          <svg className="mx-auto h-8 w-8 text-red-500" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm-1-4a1 1 0 102 0 1 1 0 00-2 0zm.293-8.707a1 1 0 011.414 0L10 5.586l.293-.293a1 1 0 111.414 1.414L11.414 7l.293.293a1 1 0 01-1.414 1.414L10 8.414l-.293.293a1 1 0 01-1.414-1.414L8.586 7l-.293-.293a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
          <p className="mt-3 font-medium text-red-800">Allocation generation failed</p>
          <p className="mt-1 text-sm text-red-700">
            {allocation?.session?.failure_reason ?? "The worker could not complete this allocation run."}
          </p>
          <button
            onClick={handleGenerate}
            disabled={loading}
            className="mt-4 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
          >
            {loading ? "Retrying..." : "Retry Allocation"}
          </button>
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
        <div className="space-y-6">
          {/* Tabs Navigation */}
          <div className="border-b border-slate-200">
            <nav className="-mb-px flex space-x-6" aria-label="Tabs">
              <button
                onClick={() => setActiveTab("overview")}
                className={`whitespace-nowrap border-b-2 py-3 px-1 text-sm font-medium ${
                  activeTab === "overview"
                    ? "border-slate-900 text-slate-900"
                    : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700"
                }`}
              >
                Intelligence Dashboard
              </button>
              <button
                onClick={() => setActiveTab("lines")}
                className={`whitespace-nowrap border-b-2 py-3 px-1 text-sm font-medium ${
                  activeTab === "lines"
                    ? "border-slate-900 text-slate-900"
                    : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-700"
                }`}
              >
                Allocation Lines {(allocation?.lines_total ?? 0).toLocaleString()}
              </button>
            </nav>
          </div>

          {activeTab === "overview" && (
            <div className="space-y-6">
              {allocation?.session?.health_score !== undefined && allocation?.session?.health_score !== null && (
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className={`p-4 border-b ${
                    allocation.session.decision?.verdict === "APPROVE" ? "bg-emerald-50 border-emerald-100" :
                    allocation.session.decision?.verdict === "APPROVE_WITH_CAUTION" ? "bg-amber-50 border-amber-100" :
                    "bg-red-50 border-red-100"
                  }`}>
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">AI Verdict</p>
                        <h2 className="text-xl font-bold text-slate-900">{allocation.session.decision?.verdict?.replace(/_/g, ' ') || "REVIEW REQUIRED"}</h2>
                        <p className="text-sm mt-1 text-slate-700">{allocation.session.decision?.action}</p>
                      </div>
                      <div className="text-right">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">Health Score</p>
                        <p className={`text-4xl font-bold ${
                           allocation.session.health_score >= 75 ? "text-emerald-600" :
                           allocation.session.health_score >= 55 ? "text-amber-600" : "text-red-600"
                        }`}>
                          {allocation.session.health_score} <span className="text-xl text-slate-400">/ 100</span>
                        </p>
                      </div>
                    </div>
                  </div>
                  <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4 bg-white">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900 mb-3">Core Metrics</h3>
                      <div className="space-y-3">
                        {allocation.session.health_report?.sub_scores && Object.entries(allocation.session.health_report.sub_scores).map(([key, val]: any) => (
                           <div key={key} className="flex items-center justify-between">
                             <span className="text-xs uppercase text-slate-600 font-medium">{key}</span>
                             <div className="flex items-center gap-2">
                               <div className="w-32 bg-slate-100 rounded-full h-1.5">
                                 <div className={`h-1.5 rounded-full ${val >= 80 ? 'bg-emerald-500' : val >= 60 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${Math.min(100, Math.max(0, val))}%` }}></div>
                               </div>
                               <span className="text-xs font-bold text-slate-700 w-8 text-right">{Math.round(val)}</span>
                             </div>
                           </div>
                        ))}
                      </div>
                    </div>
                    <div>
                       <h3 className="text-sm font-semibold text-slate-900 mb-3">Top Recommendations</h3>
                       <ul className="space-y-2">
                         {allocation.session.health_report?.top_recommendations?.map((rec: string, i: number) => (
                           <li key={i} className="flex gap-2 text-sm text-slate-700 items-start">
                              <svg className="h-4 w-4 text-blue-500 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" /></svg>
                              <span>{rec}</span>
                           </li>
                         ))}
                       </ul>
                    </div>
                  </div>
                </div>
              )}

              {/* Insights cards */}
              {insights && (
                <div className="grid grid-cols-3 gap-3">
                  <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-amber-800 mb-1">
                      Stockout correction
                    </p>
                    <p className="text-2xl font-bold text-amber-900">
                      +{insights.lost_sales_correction.estimated_recovered_units} units
                    </p>
                    <p className="text-xs text-amber-700 mt-1">
                      {insights.lost_sales_correction.headline}
                    </p>
                    <p className="text-xs text-amber-600 mt-0.5">
                      {insights.lost_sales_correction.subtext}
                    </p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">
                      Constrained stores
                    </p>
                    <p className="text-2xl font-bold text-slate-900">
                      {insights.under_covered_stores.count}
                    </p>
                    <p className="text-xs text-slate-500 mt-1">
                      {insights.under_covered_stores.headline}
                    </p>
                  </div>
                  <div className="rounded-lg border border-slate-200 bg-white p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">
                      Signal confidence
                    </p>
                    <div className="flex items-center gap-4 mt-2">
                      <span className="text-sm">
                        <span className="text-xl font-bold text-emerald-700">
                          {insights.confidence_breakdown.high}
                        </span>
                        <span className="text-xs text-slate-500 ml-1">high</span>
                      </span>
                      <span className="text-sm">
                        <span className="text-xl font-bold text-amber-600">
                          {insights.confidence_breakdown.moderate}
                        </span>
                        <span className="text-xs text-slate-500 ml-1">moderate</span>
                      </span>
                      <span className="text-sm">
                        <span className="text-xl font-bold text-red-500">
                          {insights.confidence_breakdown.low}
                        </span>
                        <span className="text-xs text-slate-500 ml-1">low</span>
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {benchmark ? (
                <div className="rounded-lg border border-slate-200 bg-white p-4">
                  <div className="grid grid-cols-4 gap-3">
                    <div className={`rounded-md border px-3 py-2 ${benchmark.acceptance.overall_pass ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">MVP Gate</p>
                      <p className={`mt-1 text-sm font-semibold ${benchmark.acceptance.overall_pass ? "text-emerald-700" : "text-amber-700"}`}>
                        {benchmark.acceptance.overall_pass ? "Pass" : "Needs tuning"}
                      </p>
                    </div>
                    <div className="rounded-md border border-slate-200 px-3 py-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Quality score</p>
                      <p className="mt-1 text-sm font-semibold text-slate-900">
                        {benchmark.summary.quality_score.toFixed(1)} / 100
                      </p>
                    </div>
                    <div className="rounded-md border border-slate-200 px-3 py-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Override rate</p>
                      <p className="mt-1 text-sm font-semibold text-slate-900">
                        {(benchmark.summary.override_rate * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div className="rounded-md border border-slate-200 px-3 py-2">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Inventory utilization</p>
                      <p className="mt-1 text-sm font-semibold text-slate-900">
                        {(benchmark.summary.inventory_utilization_rate * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                  {benchmark.demand_source_mix.length > 0 ? (
                    <p className="mt-3 text-xs text-slate-500">
                      Demand signal mix:{" "}
                      {benchmark.demand_source_mix
                        .slice(0, 3)
                        .map((item) => `${item.source} ${(item.share * 100).toFixed(0)}%`)
                        .join(" · ")}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          )}

          {activeTab === "lines" && (
            <div className="space-y-4">
              {allocationError ? (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                  <p className="text-sm font-medium text-amber-900">Could not load allocation lines yet.</p>
                  <p className="mt-1 text-xs text-amber-700">
                    {allocationError instanceof Error
                      ? allocationError.message
                      : "The response is taking too long. Try loading a smaller page of lines."}
                  </p>
                </div>
              ) : null}

              {allocation?.lines_total != null && allocation.lines_total > (allocation.lines?.length ?? 0) ? (
                <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                  <p className="text-xs text-slate-700">
                    Showing {allocation.lines.length.toLocaleString()} of {allocation.lines_total.toLocaleString()} lines.
                  </p>
                  {allocation.lines_has_more ? (
                    <button
                      onClick={() => setLineLimit((prev) => prev + 500)}
                      className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100"
                    >
                      Load 500 More
                    </button>
                  ) : null}
                </div>
              ) : null}

              <div className="grid grid-cols-12 gap-4">
                <div className="col-span-8">
                  <AllocationTable
                    lines={allocation?.lines ?? []}
                    selectedLineId={selectedLine?.id ?? null}
                    quantities={quantities}
                    onSelect={(line) => setSelectedLine(line)}
                    onChangeQty={handleChangeQty}
                    onCommitQty={handleCommitQty}
                    onOverrideReason={handleOverrideReason}
                    simulations={simulations}
                  />
                </div>
                <div className="col-span-4">
                  <ExplainabilityPanel
                    line={selectedLine}
                    skuName={selectedLine?.style_name ?? undefined}
                    styleRiskGroup={selectedLine?.sku_style_risk_group ?? undefined}
                  />
                  {selectedLine ? (
                    <>
                      <hr className="my-3 border-slate-200" />
                      <ScenarioSimulator line={selectedLine} />
                    </>
                  ) : null}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
