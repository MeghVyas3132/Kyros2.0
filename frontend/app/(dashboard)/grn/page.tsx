"use client";

import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { PageHeader } from "@/components/shared/PageHeader";
import { StatusBadge } from "@/components/shared/StatusBadge";
import { useGRNs } from "@/lib/hooks/useGrns";

export default function GRNListPage() {
  const { data: grns, isLoading } = useGRNs();

  return (
    <div>
      <PageHeader title="GRNs" subtitle="Goods received notes" />
      <div className="overflow-auto rounded-xl border border-slate-300 bg-white/95 shadow-sm">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">GRN Code</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Supplier</th>
              <th className="px-3 py-2">Units</th>
              <th className="px-3 py-2">SKUs</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i} className="border-t border-slate-200">
                    <td className="px-3 py-2" colSpan={7}>
                      <div className="h-5 animate-pulse rounded bg-slate-200" />
                    </td>
                  </tr>
                ))
              : (grns ?? []).map((grn) => (
                  <tr key={grn.id} className="border-t border-slate-200 hover:bg-slate-50/70">
                    <td className="px-3 py-2 font-medium">{grn.grn_code}</td>
                    <td className="px-3 py-2">{grn.grn_date}</td>
                    <td className="px-3 py-2">{grn.supplier_name}</td>
                    <td className="px-3 py-2">{grn.total_units}</td>
                    <td className="px-3 py-2">{grn.total_skus}</td>
                    <td className="px-3 py-2">
                      <StatusBadge label={grn.status} />
                    </td>
                    <td className="px-3 py-2">
                      <Link href={`/grn/${grn.id}`}>
                        <Button variant="secondary">
                          {grn.status === "RECEIVED"
                            ? "Generate Allocation"
                            : grn.status === "ALLOCATED"
                            ? "Review Allocation"
                            : "View"}
                        </Button>
                      </Link>
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
