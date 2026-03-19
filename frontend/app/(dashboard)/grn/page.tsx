"use client";

import Link from "next/link";

import { StatusBadge } from "@/components/shared/StatusBadge";
import { useGRNs } from "@/lib/hooks/useGrns";

const STATUS_LABEL: Record<string, string> = {
  RECEIVED: "New — Ready for Allocation",
  ALLOCATED: "Allocation Done",
  APPROVED: "Approved",
  DISPATCHED: "Dispatched to Stores",
};

export default function GRNListPage() {
  const { data: grns, isLoading } = useGRNs();

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Stock Received</h1>
        <p className="mt-1 text-sm text-slate-500">
          Each row is a stock shipment received at the warehouse. Generate and review allocations before dispatching to stores.
        </p>
      </div>

      {/* Empty state */}
      {!isLoading && (grns ?? []).length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
          <svg className="mx-auto h-12 w-12 text-slate-400" fill="currentColor" viewBox="0 0 20 20">
            <path d="M2 3a1 1 0 011-1h2.153a1 1 0 01.986.797l.291 1.45a1 1 0 00.963.806h10.516a1 1 0 00.963-.806l.291-1.45a1 1 0 01.986-.797H17a1 1 0 011 1v14a1 1 0 01-1 1H3a1 1 0 01-1-1V3z" />
          </svg>
          <p className="mt-2 font-medium text-slate-700">No stock receipts yet</p>
          <p className="mt-1 text-sm text-slate-500">
            Upload a Buy Plan or GRN file in the{" "}
            <Link href="/ingestion" className="font-medium text-slate-900 underline">
              Upload Data
            </Link>{" "}
            section to get started.
          </p>
        </div>
      ) : null}

      {/* Table */}
      {(isLoading || (grns ?? []).length > 0) ? (
        <div className="overflow-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-5 py-3 font-medium">Receipt Code</th>
                <th className="px-5 py-3 font-medium">Date</th>
                <th className="px-5 py-3 font-medium">Supplier</th>
                <th className="px-5 py-3 font-medium text-right">Total Units</th>
                <th className="px-5 py-3 font-medium text-right">Styles</th>
                <th className="px-5 py-3 font-medium">Status</th>
                <th className="px-5 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {isLoading
                ? Array.from({ length: 4 }).map((_, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="px-5 py-3" colSpan={7}>
                        <div className="h-5 animate-pulse rounded bg-slate-100" />
                      </td>
                    </tr>
                  ))
                : (grns ?? []).map((grn) => (
                    <tr key={grn.id} className="border-t border-slate-100 hover:bg-slate-50/60">
                      <td className="px-5 py-3 font-medium text-slate-800">{grn.grn_code}</td>
                      <td className="px-5 py-3 text-slate-600">{grn.grn_date}</td>
                      <td className="px-5 py-3 text-slate-600">{grn.supplier_name ?? "—"}</td>
                      <td className="px-5 py-3 text-right font-medium text-slate-800">
                        {Number(grn.total_units).toLocaleString()}
                      </td>
                      <td className="px-5 py-3 text-right text-slate-600">{grn.total_skus}</td>
                      <td className="px-5 py-3">
                        <StatusBadge label={STATUS_LABEL[grn.status] ?? grn.status} />
                      </td>
                      <td className="px-5 py-3 text-right">
                        <Link
                          href={`/grn/${grn.id}`}
                          className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
                        >
                          {grn.status === "RECEIVED"
                            ? "Generate Allocation →"
                            : grn.status === "ALLOCATED"
                            ? "Review & Approve →"
                            : "View Details →"}
                        </Link>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
