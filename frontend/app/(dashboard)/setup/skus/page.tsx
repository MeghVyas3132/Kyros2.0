"use client";

import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { apiRequest } from "@/lib/api";

export default function SetupSKUsPage() {
  const { data } = useSWR<Array<Record<string, unknown>>>(
    "/api/v1/skus",
    (path: string) => apiRequest<Array<Record<string, unknown>>>(path)
  );

  return (
    <div className="space-y-4">
      <PageHeader title="Setup · SKUs" />
      <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">SKU</th>
              <th className="px-3 py-2">Style</th>
              <th className="px-3 py-2">Category</th>
              <th className="px-3 py-2">Fabric</th>
              <th className="px-3 py-2">MRP</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).slice(0, 100).map((row) => (
              <tr key={String(row.id)} className="border-t border-slate-100">
                <td className="px-3 py-2">{String(row.sku_code)}</td>
                <td className="px-3 py-2">{String(row.style_name)}</td>
                <td className="px-3 py-2">{String(row.category)}</td>
                <td className="px-3 py-2">{String(row.fabric)}</td>
                <td className="px-3 py-2">₹{String(row.mrp)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
