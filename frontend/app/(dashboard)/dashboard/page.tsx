"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { apiRequest } from "@/lib/api";
import { useAlertCount, useAlerts } from "@/lib/hooks/useAlerts";
import { useGRNs } from "@/lib/hooks/useGrns";
import { useActiveSeasonId, useSeasons, useWorkflowState } from "@/lib/hooks/useSeasons";

interface AllocationSessionLite {
  id: string;
  status: string;
}

interface AllocationInsights {
  lost_sales_correction: {
    stores_corrected: number;
    estimated_recovered_units: number;
    headline: string;
    subtext: string;
  };
  under_covered_stores: {
    count: number;
    headline: string;
  };
  confidence_breakdown: {
    high: number;
    moderate: number;
    low: number;
  };
  total_lines: number;
  total_units_allocated: number;
}

export default function DashboardPage() {
  const router = useRouter();
  const { data: alerts } = useAlertCount();
  const { data: alertItems } = useAlerts();
  const { data: grns } = useGRNs();
  const { data: seasons, isLoading: seasonsLoading } = useSeasons();
  const activeSeasonId = useActiveSeasonId();
  const { data: workflow } = useWorkflowState(activeSeasonId);
  const [insights, setInsights] = useState<AllocationInsights | null>(null);

  // First-season gate: if a fresh tenant has zero seasons, the planning
  // workflow can't start (buy-file ingest, allocation, OTB all require a
  // season). Bounce them to /setup/seasons with a banner so the very first
  // thing they do after login is define their season.
  useEffect(() => {
    if (!seasonsLoading && Array.isArray(seasons) && seasons.length === 0) {
      router.replace("/setup/seasons?first=1");
    }
  }, [seasons, seasonsLoading, router]);

  useEffect(() => {
    let cancelled = false;

    async function loadInsights() {
      try {
        const allocations = await apiRequest<AllocationSessionLite[]>("/api/v1/allocation/sessions");
        const latestSession = allocations.find(
          (a) => a.status === "UNDER_REVIEW" || a.status === "APPROVED"
        );
        if (!latestSession) {
          if (!cancelled) setInsights(null);
          return;
        }

        const data = await apiRequest<AllocationInsights>(
          `/api/v1/allocation/${latestSession.id}/insights`
        );
        if (!cancelled) setInsights(data);
      } catch {
        if (!cancelled) setInsights(null);
      }
    }

    void loadInsights();
    return () => {
      cancelled = true;
    };
  }, []);

  const pending = (grns ?? []).find((grn) => grn.status === "RECEIVED");
  const hasData = (grns ?? []).length > 0;

  return (
    <div className="space-y-6">
      {/* Welcome Header */}
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Good morning</h1>
        <p className="mt-1 text-sm text-slate-500">
          Here&apos;s your daily planning overview.
        </p>
      </div>

      {/* What to do next */}
      {workflow && (
        <div className="rounded-xl border border-slate-200 bg-white px-5 py-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">
            {workflow.season_name} · Next step
          </p>
          {workflow.next_step ? (
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  Step {workflow.next_step.step}: {workflow.next_step.label}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {workflow.steps.find((s) => s.step === workflow.next_step!.step)?.description}
                </p>
              </div>
              <Link
                href={workflow.next_step.action_url}
                className="shrink-0 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-700 transition-colors"
              >
                {workflow.next_step.action_label}
              </Link>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-emerald-700">
              <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span className="text-sm font-medium">Season complete — ready for in-season tracking</span>
            </div>
          )}
        </div>
      )}

      {/* Getting Started Guide (shown when no data) */}
      {!hasData ? (
        <div className="rounded-xl border-2 border-dashed border-blue-200 bg-blue-50/60 p-6">
          <div className="flex items-center gap-3">
            <svg className="h-6 w-6 flex-shrink-0 text-blue-600" fill="currentColor" viewBox="0 0 20 20">
              <path d="M5 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2H5zM15 3a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2V5a2 2 0 00-2-2h-2zM5 13a2 2 0 00-2 2v2a2 2 0 002 2h2a2 2 0 002-2v-2a2 2 0 00-2-2H5z" />
            </svg>
            <h2 className="text-lg font-semibold text-blue-900">Getting Started</h2>
          </div>
          <p className="mt-2 text-sm text-blue-700">
            Upload your planning workbook to get started. Kyros will automatically detect
            store grades, buy plans, size guides, and more.
          </p>
          <div className="mt-4 flex items-center gap-3">
            <Link
              href="/ingestion"
              className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 transition-colors"
            >
              Upload Your First File
            </Link>
            <span className="text-xs text-blue-600">
              Supports .xlsx, .xlsm, and .csv files
            </span>
          </div>
        </div>
      ) : null}

      {/* Alert Banner */}
      {alerts && alerts.unread > 0 ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4">
          <div className="flex items-center gap-3">
            <svg className="h-5 w-5 flex-shrink-0 text-amber-600" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            <div>
              <p className="text-sm font-semibold text-amber-900">
                {alerts.unread} alert{alerts.unread !== 1 ? "s" : ""} need your attention
              </p>
              <p className="text-xs text-amber-700">
                {alerts.high > 0 ? `${alerts.high} high priority · ` : ""}
                {alerts.medium > 0 ? `${alerts.medium} medium · ` : ""}
                {alerts.low > 0 ? `${alerts.low} low` : ""}
              </p>
            </div>
          </div>
        </div>
      ) : null}

      {/* Quick Stats */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Active Alerts</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{alerts?.unread ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Stock Receipts
          </p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{(grns ?? []).length}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Pending Allocation
          </p>
          <p className="mt-2 text-3xl font-bold text-slate-900">{pending ? "Yes" : "None"}</p>
        </div>
      </div>

      {insights ? (
        <div className="grid grid-cols-1 gap-4 mb-1 md:grid-cols-3">
          <div className="rounded-lg border p-4">
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Stockout Recovery</p>
            <p className="text-2xl font-bold">+{insights.lost_sales_correction.estimated_recovered_units}</p>
            <p className="mt-1 text-sm text-slate-500">{insights.lost_sales_correction.headline}</p>
            <p className="mt-1 text-xs text-slate-500">{insights.lost_sales_correction.subtext}</p>
          </div>

          <div className="rounded-lg border p-4">
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Constrained Stores</p>
            <p className="text-2xl font-bold">{insights.under_covered_stores.count}</p>
            <p className="mt-1 text-sm text-slate-500">{insights.under_covered_stores.headline}</p>
          </div>

          <div className="rounded-lg border p-4">
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">Signal Confidence</p>
            <div className="mt-2 flex gap-3">
              <span className="text-sm">
                <span className="font-bold text-green-700">{insights.confidence_breakdown.high}</span>
                <span className="ml-1 text-xs text-slate-500">high</span>
              </span>
              <span className="text-sm">
                <span className="font-bold text-amber-600">{insights.confidence_breakdown.moderate}</span>
                <span className="ml-1 text-xs text-slate-500">mod</span>
              </span>
              <span className="text-sm">
                <span className="font-bold text-red-500">{insights.confidence_breakdown.low}</span>
                <span className="ml-1 text-xs text-slate-500">low</span>
              </span>
            </div>
          </div>
        </div>
      ) : null}

      {/* Pending Allocation CTA */}
      {pending ? (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <svg className="h-5 w-5 flex-shrink-0 text-emerald-600" fill="currentColor" viewBox="0 0 20 20">
                <path d="M2 3a1 1 0 011-1h2.153a1 1 0 01.986.797l.291 1.45a1 1 0 00.963.806h10.516a1 1 0 00.963-.806l.291-1.45a1 1 0 01.986-.797H17a1 1 0 011 1v14a1 1 0 01-1 1H3a1 1 0 01-1-1V3z" />
              </svg>
              <div>
                <p className="text-sm font-semibold text-emerald-900">
                  New stock ready to allocate: {pending.grn_code}
                </p>
                <p className="text-xs text-emerald-700">
                  {pending.total_units} units across {pending.total_skus} SKUs
                </p>
              </div>
            </div>
            <Link
              href={`/grn/${pending.id}`}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 transition-colors"
            >
              Generate Allocation
            </Link>
          </div>
        </div>
      ) : null}

      {/* Two-Column Content */}
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
        {/* Recent Stock Receipts */}
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-700">Recent Stock Receipts</h2>
            <Link href="/grn" className="text-xs text-slate-500 hover:text-slate-700">
              View all →
            </Link>
          </div>
          <div className="mt-3 space-y-2">
            {(grns ?? []).length === 0 ? (
              <p className="py-4 text-center text-sm text-slate-400">
                No stock received yet. Upload a Buy Plan to get started.
              </p>
            ) : (
              (grns ?? []).slice(0, 5).map((grn) => (
                <Link
                  key={grn.id}
                  href={`/grn/${grn.id}`}
                  className="flex items-center justify-between rounded-lg border border-slate-100 px-3 py-2.5 text-sm hover:bg-slate-50"
                >
                  <div>
                    <span className="font-medium text-slate-800">{grn.grn_code}</span>
                    <span className="ml-2 text-slate-400">
                      {grn.total_units} units · {grn.total_skus} SKUs
                    </span>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                    grn.status === "RECEIVED"
                      ? "bg-amber-100 text-amber-700"
                      : "bg-emerald-100 text-emerald-700"
                  }`}>
                    {grn.status === "RECEIVED" ? "Needs Allocation" : grn.status}
                  </span>
                </Link>
              ))
            )}
          </div>
        </div>

        {/* Active Alerts */}
        <div className="rounded-xl border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-700">Active Alerts</h2>
          <div className="mt-3 space-y-2">
            {!alertItems || alertItems.length === 0 ? (
              <div className="py-4 text-center">
                <svg className="mx-auto h-8 w-8 text-emerald-400" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
                </svg>
                <p className="mt-2 text-sm text-slate-400">All clear! No active alerts.</p>
              </div>
            ) : (
              alertItems.slice(0, 5).map((alert) => (
                <div
                  key={alert.id}
                  className="rounded-lg border border-slate-100 px-3 py-2.5 text-sm"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${
                        alert.severity === "HIGH"
                          ? "bg-red-500"
                          : alert.severity === "MEDIUM"
                          ? "bg-amber-500"
                          : "bg-blue-400"
                      }`}
                    />
                    <span className="font-medium text-slate-800">{alert.title}</span>
                  </div>
                  <p className="mt-1 pl-4 text-xs text-slate-500">{alert.message}</p>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
