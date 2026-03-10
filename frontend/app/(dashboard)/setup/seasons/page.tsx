"use client";

import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { apiRequest } from "@/lib/api";

export default function SetupSeasonsPage() {
  const { data } = useSWR<Array<Record<string, unknown>>>(
    "/api/v1/seasons",
    (path: string) => apiRequest<Array<Record<string, unknown>>>(path)
  );

  return (
    <div className="space-y-4">
      <PageHeader title="Setup · Seasons" />
      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
        {(data ?? []).map((season) => (
          <div key={String(season.id)} className="mb-2 rounded border border-slate-100 px-3 py-2">
            <div className="font-medium text-slate-900">{String(season.name)}</div>
            <div className="text-xs text-slate-500">
              {String(season.start_date)} to {String(season.end_date)} · {String(season.status)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
