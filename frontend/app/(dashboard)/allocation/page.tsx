"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiRequest } from "@/lib/api";
import { AllocationSession } from "@/types";

const STATUS_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  DRAFT: { label: "Draft", color: "text-slate-600", bg: "bg-slate-100" },
  GENERATING: { label: "Generating", color: "text-blue-600", bg: "bg-blue-100" },
  FAILED: { label: "Failed", color: "text-red-600", bg: "bg-red-100" },
  UNDER_REVIEW: { label: "Under Review", color: "text-amber-600", bg: "bg-amber-100" },
  APPROVED: { label: "Approved", color: "text-emerald-600", bg: "bg-emerald-100" },
  DISPATCHED: { label: "Dispatched", color: "text-slate-600", bg: "bg-slate-100" },
};
type StatusFilter = "all" | "generating" | "failed" | "under_review" | "approved" | "dispatched";

interface AllocationWithGRN extends AllocationSession {
  grn?: {
    grn_code: string;
    total_units: number;
    total_skus: number;
  };
}

export default function AllocationsPage() {
  const [allocations, setAllocations] = useState<AllocationWithGRN[]>([]);
  const [filteredAllocations, setFilteredAllocations] = useState<AllocationWithGRN[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  // Load allocations on mount and poll every 5 seconds
  useEffect(() => {
    let mounted = true;

    const fetchAllocations = async () => {
      try {
        setError(null);
        const response = await apiRequest<AllocationWithGRN[]>("/api/v1/allocation/sessions", {
          method: "GET",
        });
        if (mounted) {
          setAllocations(Array.isArray(response) ? response : []);
          setLoading(false);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load allocations");
          setAllocations([]);
          setLoading(false);
        }
      }
    };

    fetchAllocations();
    const interval = setInterval(fetchAllocations, 5000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  // Filter allocations whenever allocations, search, or status filter changes
  useEffect(() => {
    let filtered = allocations;

    // Filter by status
    if (statusFilter !== "all") {
      filtered = filtered.filter(
        (a) => a.status?.toUpperCase() === statusFilter.toUpperCase()
      );
    }

    // Filter by search term
    if (searchTerm) {
      const term = searchTerm.toLowerCase();
      filtered = filtered.filter(
        (a) =>
          a.grn?.grn_code?.toLowerCase().includes(term) ||
          a.id?.toLowerCase().includes(term)
      );
    }

    // Sort by generated_at descending
    const sorted = filtered.sort((a, b) => {
      const dateA = new Date(a.generated_at || 0).getTime();
      const dateB = new Date(b.generated_at || 0).getTime();
      return dateB - dateA;
    });

    setFilteredAllocations(sorted);
  }, [allocations, statusFilter, searchTerm]);

  const formatDate = (date: string | null | undefined) => {
    if (!date) return "—";
    return new Date(date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-semibold text-slate-900">Allocations</h1>
        <p className="mt-1 text-sm text-slate-600">
          Manage and view all stock allocations across your stores
        </p>
      </div>

      {/* Filters */}
      <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {/* Search */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Search
            </label>
            <input
              type="text"
              placeholder="Search by GRN code or ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="mt-2 block w-full rounded-lg border border-slate-200 px-3 py-2 text-sm placeholder-slate-400 focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
            />
          </div>

          {/* Status Filter */}
          <div>
            <label className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
              Status
            </label>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
              className="mt-2 block w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-slate-900 focus:outline-none focus:ring-1 focus:ring-slate-900"
            >
              <option value="all">All Statuses</option>
              <option value="draft">Draft</option>
              <option value="generating">Generating</option>
              <option value="under_review">Under Review</option>
              <option value="failed">Failed</option>
              <option value="approved">Approved</option>
              <option value="dispatched">Dispatched</option>
            </select>
          </div>
        </div>
      </div>

      {/* Results */}
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4">
          <div className="flex gap-3">
            <svg className="h-5 w-5 flex-shrink-0 text-red-600" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
            <div>
              <p className="text-sm font-medium text-red-900">Failed to load allocations</p>
              <p className="mt-1 text-xs text-red-700">{error}</p>
            </div>
          </div>
        </div>
      )}
      {loading ? (
        <div className="rounded-xl border border-slate-200 bg-white p-12 text-center">
          <div className="inline-flex h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-slate-900" />
          <p className="mt-3 text-sm text-slate-600">Loading allocations...</p>
        </div>
      ) : filteredAllocations.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-12 text-center">
          <svg
            className="mx-auto h-12 w-12 text-slate-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M20 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z"
            />
          </svg>
          <p className="mt-3 font-medium text-slate-900">No allocations found</p>
          <p className="mt-1 text-sm text-slate-600">
            {allocations.length === 0
              ? "Start by uploading a Buy Plan and GRN to create your first allocation"
              : "Try adjusting your search filters"}
          </p>
          {allocations.length === 0 && (
            <Link
              href="/ingestion"
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              Upload Data
            </Link>
          )}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full divide-y divide-slate-200">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                  GRN Code
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                  Status
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600">
                  Units
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600">
                  Stores
                </th>
                <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-600">
                  Generated
                </th>
                <th className="px-6 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-600">
                  Action
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {filteredAllocations.map((allocation) => {
                const statusConfig =
                  STATUS_CONFIG[allocation.status || "DRAFT"] || STATUS_CONFIG.DRAFT;
                return (
                  <tr key={allocation.id} className="hover:bg-slate-50 transition">
                    <td className="px-6 py-4">
                      <div className="text-sm font-medium text-slate-900">
                        {allocation.grn?.grn_code || "—"}
                      </div>
                      <div className="mt-0.5 text-xs text-slate-500 font-mono">
                        {allocation.id}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ${statusConfig.bg} ${statusConfig.color}`}
                      >
                        {statusConfig.label}
                        {allocation.status === "GENERATING" && (
                          <svg
                            className="ml-1.5 h-3 w-3 animate-spin"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                            />
                          </svg>
                        )}
                      </span>
                      {allocation.status === "FAILED" && allocation.failure_reason ? (
                        <p className="mt-1 max-w-sm text-xs text-red-700">{allocation.failure_reason}</p>
                      ) : null}
                    </td>
                    <td className="px-6 py-4 text-right text-sm font-medium text-slate-900">
                      {allocation.grn?.total_units?.toLocaleString() || "—"}
                    </td>
                    <td className="px-6 py-4 text-right text-sm font-medium text-slate-900">
                      {allocation.total_stores || "—"}
                    </td>
                    <td className="px-6 py-4 text-sm text-slate-600">
                      {formatDate(allocation.generated_at)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        {allocation.status === "FAILED" ? (
                          <button
                            onClick={async () => {
                              await apiRequest("/api/v1/allocation/generate", {
                                method: "POST",
                                body: JSON.stringify({ grn_id: allocation.grn_id }),
                              });
                            }}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 transition"
                          >
                            Retry
                          </button>
                        ) : null}
                        {["UNDER_REVIEW", "APPROVED", "DISPATCHED"].includes(allocation.status || "") ? (
                          <a
                            href={`http://localhost:8000/api/v1/allocation/sessions/${allocation.id}/export`}
                            download={`allocation-${allocation.grn?.grn_code || allocation.id}.csv`}
                            className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 transition"
                          >
                            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                            </svg>
                            Download CSV
                          </a>
                        ) : null}
                        <Link
                          href={`/grn/${allocation.grn_id}`}
                          className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 transition"
                        >
                          View
                          <svg
                            className="h-3.5 w-3.5"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M9 5l7 7-7 7"
                            />
                          </svg>
                        </Link>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
