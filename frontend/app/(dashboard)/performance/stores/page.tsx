"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { StorePerformanceTable } from "@/components/performance/StorePerformanceTable";
import { Input } from "@/components/ui/Input";
import { apiRequest } from "@/lib/api";
import { usePerformanceStores } from "@/lib/hooks/usePerformance";

interface SeasonItem {
  id: string;
  name: string;
}

export default function PerformanceStoresPage() {
  const [seasonId, setSeasonId] = useState("");
  const [clusterId, setClusterId] = useState("");
  const { data: seasons } = useSWR<SeasonItem[]>("/api/v1/seasons", (path: string) =>
    apiRequest<SeasonItem[]>(path)
  );

  useEffect(() => {
    if (!seasonId && seasons && seasons.length > 0) {
      setSeasonId(seasons[0].id);
    }
  }, [seasonId, seasons]);

  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (seasonId) params.set("season_id", seasonId);
    if (clusterId) params.set("cluster_id", clusterId);
    return `?${params.toString()}`;
  }, [seasonId, clusterId]);

  const { data } = usePerformanceStores(query);

  const handleExport = async () => {
    const token = localStorage.getItem("kyros_access_token");
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/v1/performance/stores${query}${query.includes("?") ? "&" : "?"}export=true`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} }
    );
    if (!response.ok) return;
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `store-performance-${seasonId || "all"}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Store Health</h1>
        <p className="mt-1 text-sm text-slate-500">
          Monitor sell-through and weeks of cover at each store to spot issues early.
        </p>
      </div>

      {/* Filters */}
      <div className="grid grid-cols-3 gap-3">
        <select
          className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400 focus:ring-1 focus:ring-slate-400"
          value={seasonId}
          onChange={(e) => setSeasonId(e.target.value)}
        >
          <option value="">All Seasons</option>
          {(seasons ?? []).map((season) => (
            <option key={season.id} value={season.id}>
              {season.name}
            </option>
          ))}
        </select>
        <Input placeholder="Filter by cluster…" value={clusterId} onChange={(e) => setClusterId(e.target.value)} />
        <button
          onClick={handleExport}
          className="inline-flex items-center justify-center rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd" /></svg>
          Export CSV
        </button>
      </div>

      <StorePerformanceTable rows={(data as Array<Record<string, unknown>>) ?? []} />
    </div>
  );
}
