"use client";

import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { apiRequest } from "@/lib/api";

export default function SetupStoresPage() {
  const { data } = useSWR<Array<Record<string, unknown>>>(
    "/api/v1/stores",
    (path: string) => apiRequest<Array<Record<string, unknown>>>(path)
  );

  return (
    <div className="space-y-4">
      <PageHeader title="Setup · Stores" subtitle="Basic CRUD table" />
      <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Code</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">City</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((row) => (
              <tr key={String(row.id)} className="border-t border-slate-100">
                <td className="px-3 py-2">{String(row.store_code)}</td>
                <td className="px-3 py-2">{String(row.store_name)}</td>
                <td className="px-3 py-2">{String(row.city)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
