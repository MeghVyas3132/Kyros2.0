"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import useSWR from "swr";

import { AllocationTable } from "@/components/allocation/AllocationTable";
import { ExplainabilityPanel } from "@/components/allocation/ExplainabilityPanel";
import { ScenarioSimulator } from "@/components/allocation/ScenarioSimulator";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { ApiError, apiRequest } from "@/lib/api";
import { useGRN } from "@/lib/hooks/useGrns";
import { useAllocationSession } from "@/lib/hooks/useAllocation";

type DecisionAction = {
  id: string;
  category: string;
  title: string;
  description: string;
  impact: "HIGH" | "MEDIUM" | "LOW";
  confidence: "HIGH" | "MEDIUM" | "LOW";
  data_backing: string;
};
type DecisionSummary = {
  classification: "DATA" | "STRATEGY" | "HEALTHY";
  summary: string;
  actions: DecisionAction[];
  aggregates: Record<string, unknown>;
};
import {
  AllocationBenchmarkReport,
  AllocationInsights,
  AllocationLine,
  AllocationSession,
  OverrideReasonCode,
  OVERRIDE_REASON_LABELS,
  SimulationResult,
} from "@/types";

const CONFIDENCE_COLORS: Record<string, string> = {
  HIGH: "bg-emerald-100 text-emerald-700",
  MEDIUM: "bg-amber-100 text-amber-700",
  LOW: "bg-red-100 text-red-700",
};

const CONFIDENCE_TOOLTIPS: Record<string, string> = {
  HIGH: "Based on this store's own sales history",
  MEDIUM: "Based on cluster or grade average",
  LOW: "Estimated from similar styles or minimum display",
};

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

// ─── Track B: Approval Summary ──

interface Exception {
  line: AllocationLine;
  kind: "low_confidence" | "under_cover" | "over_cover" | "excluded" | "stockout_risk";
  detail: string;
}

function buildExceptions(lines: AllocationLine[]): Exception[] {
  const out: Exception[] = [];
  for (const line of lines) {
    const reasoning = (line.ai_reasoning ?? {}) as Record<string, unknown>;
    const coverTarget = Number(reasoning?.cover_target_weeks ?? 0);
    const coverAtRec = Number(reasoning?.weeks_cover_at_recommended ?? 0);
    const excluded = Boolean(reasoning?.excluded_by_capacity);
    const stockoutRisk = Boolean(reasoning?.stockout_risk_at_lower_qty);

    if (excluded) {
      out.push({
        line,
        kind: "excluded",
        detail:
          (reasoning?.exclusion_reason as string | undefined) ??
          "Excluded by display capacity.",
      });
      continue; // a line excluded is the dominant signal
    }
    if (line.ai_confidence === "LOW") {
      out.push({
        line,
        kind: "low_confidence",
        detail:
          "Demand source is a fallback (analogue or minimum display). Verify before approving.",
      });
    }
    if (coverTarget > 0 && coverAtRec > 0 && coverAtRec < coverTarget * 0.6) {
      out.push({
        line,
        kind: "under_cover",
        detail: `Only ${coverAtRec.toFixed(1)}w of cover vs ${coverTarget}w target — possible stockout.`,
      });
    } else if (coverTarget > 0 && coverAtRec > coverTarget * 1.5) {
      out.push({
        line,
        kind: "over_cover",
        detail: `${coverAtRec.toFixed(1)}w of cover vs ${coverTarget}w target — overstock risk.`,
      });
    }
    if (stockoutRisk) {
      out.push({
        line,
        kind: "stockout_risk",
        detail: "Stockout risk flagged at lower quantity.",
      });
    }
  }
  return out;
}

const KIND_LABEL: Record<Exception["kind"], { label: string; tone: string }> = {
  low_confidence: { label: "Low confidence", tone: "bg-amber-100 text-amber-800" },
  under_cover: { label: "Under cover", tone: "bg-red-100 text-red-800" },
  over_cover: { label: "Over cover", tone: "bg-amber-100 text-amber-800" },
  excluded: { label: "Excluded", tone: "bg-slate-200 text-slate-700" },
  stockout_risk: { label: "Stockout risk", tone: "bg-red-100 text-red-800" },
};

function ApprovalSummary({
  lines,
  onSelectLine,
}: {
  lines: AllocationLine[];
  onSelectLine?: (line: AllocationLine) => void;
}) {
  const exceptions = useMemo(() => buildExceptions(lines), [lines]);

  const stats = useMemo(() => {
    let totalUnits = 0;
    let totalOverridden = 0;
    let totalLowConfidence = 0;
    const byGrade: Record<string, number> = {};
    const byCategory: Record<string, number> = {};
    const byRisk: Record<string, number> = {};
    const byStore: Record<string, { name: string; city: string | null; units: number }> = {};
    const skuSet = new Set<string>();

    for (const line of lines) {
      const qty = line.final_qty ?? line.ai_recommended_qty ?? 0;
      if (qty <= 0) continue;
      totalUnits += qty;
      skuSet.add(line.sku_id);

      if (line.was_overridden) totalOverridden += 1;
      if (line.ai_confidence === "LOW") totalLowConfidence += 1;

      const reasoning = (line.ai_reasoning ?? {}) as Record<string, unknown>;
      const grade = String(reasoning?.store_grade ?? "?");
      byGrade[grade] = (byGrade[grade] ?? 0) + qty;

      const cat = line.sku_category ?? "Uncategorised";
      byCategory[cat] = (byCategory[cat] ?? 0) + qty;

      const risk = line.sku_style_risk_group ?? line.sku_resolved_risk_level ?? "—";
      byRisk[risk] = (byRisk[risk] ?? 0) + qty;

      const sid = line.store_id;
      if (!byStore[sid]) {
        byStore[sid] = {
          name: line.store_name ?? line.store_code ?? sid.slice(0, 8),
          city: line.store_city ?? null,
          units: 0,
        };
      }
      byStore[sid].units += qty;
    }

    const topStores = Object.values(byStore)
      .sort((a, b) => b.units - a.units)
      .slice(0, 5);

    return {
      totalUnits,
      totalLines: lines.length,
      totalSkus: skuSet.size,
      storesCount: Object.keys(byStore).length,
      totalOverridden,
      totalLowConfidence,
      byGrade,
      byCategory,
      byRisk,
      topStores,
    };
  }, [lines]);

  const fmt = (n: number) => n.toLocaleString();
  const pct = (n: number) => (stats.totalUnits > 0 ? ((n / stats.totalUnits) * 100).toFixed(1) : "0.0");

  const gradeOrder = ["A+", "A", "B", "C", "?"];
  const sortedGrades = Object.keys(stats.byGrade).sort(
    (a, b) => gradeOrder.indexOf(a) - gradeOrder.indexOf(b)
  );

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-slate-900">Approval summary</h2>
        <span className="text-[11px] text-slate-400">
          Sanity-check totals before you approve
        </span>
      </div>

      {/* Headline stats */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg bg-slate-50 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Total units</p>
          <p className="mt-0.5 text-2xl font-bold tabular-nums text-slate-900">
            {fmt(stats.totalUnits)}
          </p>
        </div>
        <div className="rounded-lg bg-slate-50 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Stores receiving</p>
          <p className="mt-0.5 text-2xl font-bold tabular-nums text-slate-900">
            {fmt(stats.storesCount)}
          </p>
        </div>
        <div className="rounded-lg bg-slate-50 px-4 py-3">
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Distinct SKUs</p>
          <p className="mt-0.5 text-2xl font-bold tabular-nums text-slate-900">
            {fmt(stats.totalSkus)}
          </p>
        </div>
        <div
          className={`rounded-lg px-4 py-3 ${
            stats.totalOverridden / Math.max(stats.totalLines, 1) > 0.3
              ? "bg-amber-50"
              : "bg-slate-50"
          }`}
        >
          <p className="text-[11px] uppercase tracking-wide text-slate-500">Overrides</p>
          <p className="mt-0.5 text-2xl font-bold tabular-nums text-slate-900">
            {fmt(stats.totalOverridden)}{" "}
            <span className="text-xs font-normal text-slate-500">
              ({fmt(stats.totalLowConfidence)} low-conf)
            </span>
          </p>
        </div>
      </div>

      {/* Breakdowns */}
      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div>
          <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">By store grade</p>
          <div className="space-y-1">
            {sortedGrades.map((g) => (
              <div key={g} className="flex items-center gap-2 text-xs">
                <span className="w-8 shrink-0 font-semibold text-slate-700">{g}</span>
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className="h-full rounded-full bg-slate-700"
                    style={{ width: `${pct(stats.byGrade[g])}%` }}
                  />
                </div>
                <span className="w-20 shrink-0 text-right tabular-nums text-slate-600">
                  {fmt(stats.byGrade[g])}{" "}
                  <span className="text-slate-400">({pct(stats.byGrade[g])}%)</span>
                </span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">By category</p>
          <div className="space-y-1">
            {Object.entries(stats.byCategory)
              .sort(([, a], [, b]) => b - a)
              .slice(0, 6)
              .map(([cat, n]) => (
                <div key={cat} className="flex items-center gap-2 text-xs">
                  <span className="w-24 shrink-0 truncate text-slate-700">{cat}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-slate-700"
                      style={{ width: `${pct(n)}%` }}
                    />
                  </div>
                  <span className="w-20 shrink-0 text-right tabular-nums text-slate-600">
                    {fmt(n)} <span className="text-slate-400">({pct(n)}%)</span>
                  </span>
                </div>
              ))}
          </div>
        </div>
        <div>
          <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">By risk group</p>
          <div className="space-y-1">
            {Object.entries(stats.byRisk)
              .sort(([, a], [, b]) => b - a)
              .map(([risk, n]) => (
                <div key={risk} className="flex items-center gap-2 text-xs">
                  <span className="w-24 shrink-0 truncate text-slate-700">{risk}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-slate-700"
                      style={{ width: `${pct(n)}%` }}
                    />
                  </div>
                  <span className="w-20 shrink-0 text-right tabular-nums text-slate-600">
                    {fmt(n)} <span className="text-slate-400">({pct(n)}%)</span>
                  </span>
                </div>
              ))}
          </div>
        </div>
      </div>

      {/* Top 5 stores */}
      {stats.topStores.length > 0 && (
        <div className="mt-5">
          <p className="mb-2 text-[11px] uppercase tracking-wide text-slate-500">
            Top 5 stores by units
          </p>
          <div className="space-y-1">
            {stats.topStores.map((s, i) => (
              <div key={i} className="flex items-center gap-2 text-xs">
                <span className="flex-1 truncate text-slate-700">
                  {s.name}
                  {s.city ? <span className="text-slate-400"> · {s.city}</span> : null}
                </span>
                <span className="w-20 shrink-0 text-right tabular-nums text-slate-700">
                  {fmt(s.units)}
                </span>
                <span className="w-12 shrink-0 text-right text-slate-400">
                  {pct(s.units)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Exceptions tab */}
      <ExceptionsList exceptions={exceptions} onSelectLine={onSelectLine} />
    </div>
  );
}

function ExceptionsList({
  exceptions,
  onSelectLine,
}: {
  exceptions: Exception[];
  onSelectLine?: (line: AllocationLine) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  if (exceptions.length === 0) {
    return (
      <div className="mt-5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
        <p className="text-xs font-medium text-emerald-800">
          ✓ No exceptions flagged. All lines look within tolerance.
        </p>
      </div>
    );
  }

  const visible = showAll ? exceptions : exceptions.slice(0, 8);
  const hiddenCount = exceptions.length - visible.length;

  return (
    <div className="mt-5">
      <div className="mb-2 flex items-baseline justify-between">
        <p className="text-[11px] uppercase tracking-wide text-slate-500">
          Exceptions ({exceptions.length})
        </p>
        <p className="text-[10px] text-slate-400">
          Click a row to inspect in the lines table
        </p>
      </div>
      <div className="overflow-hidden rounded-lg border border-slate-200">
        <table className="min-w-full text-xs">
          <thead className="bg-slate-50 text-left text-[10px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">Store</th>
              <th className="px-3 py-2 font-medium">Style</th>
              <th className="px-3 py-2 font-medium text-right">Qty</th>
              <th className="px-3 py-2 font-medium">Detail</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((ex, i) => {
              const k = KIND_LABEL[ex.kind];
              const qty = ex.line.final_qty ?? ex.line.ai_recommended_qty ?? 0;
              return (
                <tr
                  key={i}
                  onClick={() => onSelectLine?.(ex.line)}
                  className="cursor-pointer border-t border-slate-100 hover:bg-slate-50"
                >
                  <td className="px-3 py-1.5">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold ${k.tone}`}
                    >
                      {k.label}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-slate-700">
                    {ex.line.store_name ?? ex.line.store_code ?? "—"}
                    {ex.line.store_city ? (
                      <span className="text-slate-400"> · {ex.line.store_city}</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-[11px] text-slate-700">
                    {ex.line.style_name ?? ex.line.sku_code ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 text-right tabular-nums text-slate-700">
                    {qty}
                  </td>
                  <td className="px-3 py-1.5 text-slate-600">{ex.detail}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {hiddenCount > 0 ? (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-xs text-slate-600 underline hover:text-slate-900"
        >
          Show {hiddenCount} more exception{hiddenCount === 1 ? "" : "s"}
        </button>
      ) : null}
    </div>
  );
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

  // Decision summary — the VP-facing 3-5 actions. Only fetched once the
  // session has a health_score; before that the endpoint returns 409.
  const decisionKey =
    sessionId && (allocation?.session?.health_score ?? null) !== null
      ? `/api/v1/allocation/sessions/${sessionId}/decision-summary`
      : null;
  const { data: decisionSummary } = useSWR<DecisionSummary>(
    decisionKey,
    (path: string) => apiRequest<DecisionSummary>(path),
  );

  const [selectedLine, setSelectedLine] = useState<AllocationLine | null>(null);
  const [quantities, setQuantities] = useState<Record<string, number>>({});
  const [simulations, setSimulations] = useState<Record<string, SimulationResult>>({});
  const [insights, setInsights] = useState<AllocationInsights | null>(null);
  const [benchmark, setBenchmark] = useState<AllocationBenchmarkReport | null>(null);
  const [overrideReasonCode, setOverrideReasonCode] = useState<OverrideReasonCode | "">("");
  const [loading, setLoading] = useState(false);
  const [checkingSession, setCheckingSession] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);
  const [statusRefreshError, setStatusRefreshError] = useState<string | null>(null);
  const simTimerRef = useRef<number | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const status = allocation?.session?.status ?? sessionStatus ?? (grn?.status === "RECEIVED" ? "DRAFT" : "UNDER_REVIEW");

  // ── Track A: pre-allocation sanity check ──
  type SanityResp = {
    grn_id: string;
    ready: boolean;
    blockers: string[];
    warnings: string[];
    facts: {
      weeks_of_sales: number;
      grn_sku_count: number;
      grn_skus_with_history: number;
      grn_categories: string[];
      active_stores: number;
      stores_with_grades_for_grn_categories: number;
      buy_plan_count: number;
    };
    narration: string;
  };
  const [sanity, setSanity] = useState<SanityResp | null>(null);
  const [sanityLoading, setSanityLoading] = useState(false);

  useEffect(() => {
    if (!grnId) return;
    if (sessionId && status !== "DRAFT") return; // only relevant pre-generation
    setSanityLoading(true);
    void apiRequest<SanityResp>(`/api/v1/allocation/sanity-check?grn_id=${grnId}`)
      .then((data) => setSanity(data))
      .catch(() => setSanity(null))
      .finally(() => setSanityLoading(false));
  }, [grnId, sessionId, status]);

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
          override_reason_code: overrideReasonCode || null,
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
    [mutate, overrideReasonCode]
  );

  const handleOverrideReason = useCallback(
    (line: AllocationLine, code: OverrideReasonCode) => {
      const qty = quantities[line.id] ?? line.ai_recommended_qty;
      void apiRequest(`/api/v1/allocation/lines/${line.id}`, {
        method: "PUT",
        body: JSON.stringify({
          final_qty: qty,
          // Per-row dropdown writes the structured code directly.
          // Free-text override_reason kept for backward-compat with legacy rows.
          override_reason_code: code,
          override_reason: line.override_reason ?? null,
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
              disabled={
                loading ||
                status === "GENERATING" ||
                Boolean(sanity && !sanity.ready)
              }
              title={
                sanity && !sanity.ready
                  ? `Resolve blockers before generating: ${sanity.blockers.join("; ")}`
                  : undefined
              }
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
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

      {/* Track A: pre-allocation sanity check */}
      {(!sessionId || status === "DRAFT") && (sanity || sanityLoading) ? (
        <div
          className={`rounded-xl border px-5 py-4 ${
            sanity?.blockers?.length
              ? "border-red-200 bg-red-50"
              : sanity?.warnings?.length
              ? "border-amber-200 bg-amber-50"
              : "border-emerald-200 bg-emerald-50"
          }`}
        >
          <div className="flex items-start gap-3">
            <span
              className={`mt-0.5 inline-flex h-5 w-5 items-center justify-center rounded-full text-xs font-semibold ${
                sanity?.blockers?.length
                  ? "bg-red-100 text-red-700"
                  : sanity?.warnings?.length
                  ? "bg-amber-100 text-amber-700"
                  : "bg-emerald-100 text-emerald-700"
              }`}
              aria-hidden
            >
              {sanity?.blockers?.length ? "!" : sanity?.warnings?.length ? "?" : "✓"}
            </span>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-slate-900">
                {sanityLoading
                  ? "Checking data readiness…"
                  : sanity?.blockers?.length
                  ? "Allocation cannot run yet"
                  : sanity?.warnings?.length
                  ? "Allocation can run, with caveats"
                  : "Data looks ready"}
              </p>
              {sanity?.narration ? (
                <p className="mt-1 text-sm text-slate-700 leading-relaxed">
                  {sanity.narration}
                </p>
              ) : null}
              {sanity?.blockers?.length ? (
                <ul className="mt-2 space-y-1 text-xs text-red-800">
                  {sanity.blockers.map((b, i) => (
                    <li key={i}>• {b}</li>
                  ))}
                </ul>
              ) : null}
              {sanity?.warnings?.length ? (
                <ul className="mt-2 space-y-1 text-xs text-amber-800">
                  {sanity.warnings.map((w, i) => (
                    <li key={i}>• {w}</li>
                  ))}
                </ul>
              ) : null}
              {sanity?.facts ? (
                <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                  <span>{sanity.facts.weeks_of_sales} wk sales history</span>
                  <span>
                    {sanity.facts.grn_skus_with_history}/{sanity.facts.grn_sku_count} GRN SKUs with history
                  </span>
                  <span>
                    {sanity.facts.stores_with_grades_for_grn_categories}/{sanity.facts.active_stores} stores graded
                  </span>
                  {sanity.facts.buy_plan_count > 0 && <span>Buy plan ✓</span>}
                </div>
              ) : null}
            </div>
          </div>
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
              {/* DECISION SUMMARY — what a VP should see first. Renders
                  ABOVE the AI Verdict / metric tiles by design: the spec
                  for this page is "what should I do?", not "what happened?".
                  Metrics still live below for the curious planner. */}
              {decisionSummary ? (
                <div
                  className={`rounded-xl border p-5 shadow-sm ${
                    decisionSummary.classification === "HEALTHY"
                      ? "border-emerald-200 bg-emerald-50"
                      : decisionSummary.classification === "DATA"
                      ? "border-red-200 bg-red-50"
                      : "border-amber-200 bg-amber-50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">
                        Decision summary
                      </p>
                      <h2 className="mt-1 text-lg font-semibold text-slate-900">
                        {decisionSummary.classification === "HEALTHY"
                          ? "Plan is releasable"
                          : decisionSummary.classification === "DATA"
                          ? "Fix the inputs first"
                          : "Plan needs strategy adjustment"}
                      </h2>
                      <p className="mt-2 max-w-3xl text-sm text-slate-700">
                        {decisionSummary.summary}
                      </p>
                    </div>
                    <span
                      className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${
                        decisionSummary.classification === "HEALTHY"
                          ? "border-emerald-300 bg-emerald-100 text-emerald-800"
                          : decisionSummary.classification === "DATA"
                          ? "border-red-300 bg-red-100 text-red-800"
                          : "border-amber-300 bg-amber-100 text-amber-800"
                      }`}
                    >
                      {decisionSummary.classification === "HEALTHY"
                        ? "Healthy"
                        : decisionSummary.classification === "DATA"
                        ? "Data issue"
                        : "Strategy issue"}
                    </span>
                  </div>

                  {decisionSummary.actions.length > 0 ? (
                    <ol className="mt-4 space-y-2">
                      {decisionSummary.actions.map((action, idx) => (
                        <li
                          key={action.id}
                          className="rounded-lg border border-white/60 bg-white/80 p-3"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex flex-1 items-start gap-3">
                              <span
                                className={`flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-semibold ${
                                  action.impact === "HIGH"
                                    ? "bg-slate-900 text-white"
                                    : action.impact === "MEDIUM"
                                    ? "bg-slate-200 text-slate-800"
                                    : "bg-slate-100 text-slate-600"
                                }`}
                              >
                                {idx + 1}
                              </span>
                              <div>
                                <p className="text-sm font-semibold text-slate-900">
                                  {action.title}
                                </p>
                                <p className="mt-1 text-sm text-slate-700">
                                  {action.description}
                                </p>
                                <p className="mt-1 text-[11px] text-slate-500">
                                  <span className="font-mono">{action.data_backing}</span>
                                </p>
                              </div>
                            </div>
                            <div className="flex flex-shrink-0 flex-col items-end gap-1 text-[11px]">
                              <span
                                className={`rounded-full px-2 py-0.5 font-medium ${
                                  action.impact === "HIGH"
                                    ? "bg-red-100 text-red-700"
                                    : action.impact === "MEDIUM"
                                    ? "bg-amber-100 text-amber-700"
                                    : "bg-slate-100 text-slate-600"
                                }`}
                              >
                                Impact: {action.impact.toLowerCase()}
                              </span>
                              <span className="text-slate-500">
                                Confidence: {action.confidence.toLowerCase()}
                              </span>
                              <span className="rounded-md border border-slate-200 bg-white px-1.5 py-0.5 text-slate-600">
                                {action.category}
                              </span>
                            </div>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : null}
                </div>
              ) : null}

              {allocation?.session?.health_score !== undefined && allocation?.session?.health_score !== null && (
                <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden">
                  <div className={`p-4 border-b ${
                    allocation.session.decision?.verdict === "APPROVE" ? "bg-emerald-50 border-emerald-100" :
                    allocation.session.decision?.verdict === "APPROVE_WITH_CAUTION" ? "bg-amber-50 border-amber-100" :
                    "bg-red-50 border-red-100"
                  }`}>
                    <div className="flex items-center justify-between gap-4">
                      <div className="flex-1">
                        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 mb-1">AI Verdict</p>
                        <h2 className="text-xl font-bold text-slate-900">{allocation.session.decision?.verdict?.replace(/_/g, ' ') || "REVIEW REQUIRED"}</h2>
                        <p className="text-sm mt-1 text-slate-700">{allocation.session.decision?.action}</p>
                        {allocation.session.decision?.blocked_reason ? (
                          <div className="mt-3 rounded-md bg-white/70 p-3 border border-red-200">
                            {(() => {
                              const fc = allocation.session.decision?.failure_class;
                              if (!fc || fc === "NONE") return null;
                              const label =
                                fc === "DATA_QUALITY"
                                  ? "Data problem"
                                  : fc === "ELIGIBILITY"
                                  ? "Eligibility problem"
                                  : "Strategy problem";
                              const tone =
                                fc === "DATA_QUALITY"
                                  ? "bg-red-100 text-red-800 border-red-200"
                                  : fc === "ELIGIBILITY"
                                  ? "bg-amber-100 text-amber-800 border-amber-200"
                                  : "bg-violet-100 text-violet-800 border-violet-200";
                              return (
                                <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${tone} mb-2`}>
                                  {label}
                                </span>
                              );
                            })()}
                            <p className="text-xs font-semibold uppercase tracking-wide text-red-700 mb-1">Why this is blocked</p>
                            <p className="text-sm text-slate-900">{allocation.session.decision.blocked_reason}</p>
                            {allocation.session.decision.fix ? (
                              <>
                                <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700 mt-2 mb-1">How to fix</p>
                                <p className="text-sm text-slate-900">{allocation.session.decision.fix}</p>
                              </>
                            ) : null}
                          </div>
                        ) : null}
                        {(() => {
                          const ld = allocation.session.decision?.line_diagnostics ?? {};
                          const allocated = Number(ld.allocated_units ?? 0);
                          const received = Number(ld.received_units ?? 0);
                          const stores = Number(ld.distinct_stores_with_allocation ?? 0);
                          const totalStores = Number(ld.total_active_stores ?? 0);
                          if (received <= 0 && totalStores <= 0) return null;
                          const pct = received > 0 ? (allocated / received) * 100 : 0;
                          return (
                            <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                              <span className={`rounded-full px-2 py-0.5 font-medium ${pct < 10 ? "bg-red-100 text-red-800" : pct < 50 ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                                {allocated.toLocaleString()} of {received.toLocaleString()} units allocated ({pct.toFixed(1)}%)
                              </span>
                              {totalStores > 0 ? (
                                <span className={`rounded-full px-2 py-0.5 font-medium ${stores / Math.max(totalStores, 1) < 0.5 ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-700"}`}>
                                  {stores} of {totalStores} stores receiving
                                </span>
                              ) : null}
                              {ld.sku_overlap_with_sales_pct !== undefined && ld.sku_overlap_with_sales_pct !== null ? (
                                <span className={`rounded-full px-2 py-0.5 font-medium ${Number(ld.sku_overlap_with_sales_pct) < 0.05 ? "bg-red-100 text-red-800" : "bg-slate-100 text-slate-700"}`}>
                                  GRN ↔ sales overlap: {(Number(ld.sku_overlap_with_sales_pct) * 100).toFixed(1)}%
                                </span>
                              ) : null}
                              {ld.signal_grade ? (
                                <span className={`rounded-full px-2 py-0.5 font-medium ${ld.signal_grade === "HIGH" ? "bg-emerald-100 text-emerald-800" : ld.signal_grade === "MEDIUM" ? "bg-amber-100 text-amber-800" : "bg-red-100 text-red-800"}`}>
                                  Signal: {String(ld.signal_grade).toLowerCase()}
                                </span>
                              ) : null}
                            </div>
                          );
                        })()}
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

              <div className="flex items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-2.5">
                <label className="text-xs font-medium text-slate-600 whitespace-nowrap">Override reason:</label>
                <select
                  value={overrideReasonCode}
                  onChange={(e) => setOverrideReasonCode(e.target.value as OverrideReasonCode | "")}
                  className="w-56 rounded-md border border-slate-300 px-3 py-1.5 text-sm bg-white"
                >
                  <option value="">Select reason...</option>
                  {(Object.entries(OVERRIDE_REASON_LABELS) as [OverrideReasonCode, string][]).map(([code, label]) => (
                    <option key={code} value={code}>{label}</option>
                  ))}
                </select>
                <span className="text-xs text-slate-400">Applied when you change a quantity</span>
              </div>

              {(allocation?.lines?.length ?? 0) > 0 ? (
                <ApprovalSummary
                  lines={allocation?.lines ?? []}
                  onSelectLine={(line) => setSelectedLine(line)}
                />
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
