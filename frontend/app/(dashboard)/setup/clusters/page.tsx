"use client";

import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { apiRequest } from "@/lib/api";

export default function SetupClustersPage() {
  const { data } = useSWR<Array<Record<string, unknown>>>(
    "/api/v1/clusters",
    (path: string) => apiRequest<Array<Record<string, unknown>>>(path)
  );

  return (
    <div className="space-y-4">
      <PageHeader title="Setup · Clusters" />
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">
        {(data ?? []).map((row) => (
          <div key={String(row.id)} className="mb-2 rounded border border-slate-100 px-3 py-2">
            <div className="font-medium">{String(row.name)}</div>
            <div className="text-xs text-slate-500">{String(row.description ?? "")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
