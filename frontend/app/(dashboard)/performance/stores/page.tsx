"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
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
    <div className="space-y-4">
      <PageHeader title="Performance · Stores" subtitle="Store-level sell-through and cover" />
      <div className="grid grid-cols-3 gap-2">
        <select
          className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none focus:border-slate-600"
          value={seasonId}
          onChange={(e) => setSeasonId(e.target.value)}
        >
          <option value="">Select season</option>
          {(seasons ?? []).map((season) => (
            <option key={season.id} value={season.id}>
              {season.name}
            </option>
          ))}
        </select>
        <Input placeholder="Cluster ID" value={clusterId} onChange={(e) => setClusterId(e.target.value)} />
        <button
          onClick={handleExport}
          className="inline-flex items-center justify-center rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-semibold text-slate-900 hover:bg-slate-50"
        >
          Export CSV
        </button>
      </div>
      <StorePerformanceTable rows={(data as Array<Record<string, unknown>>) ?? []} />
    </div>
  );
}
