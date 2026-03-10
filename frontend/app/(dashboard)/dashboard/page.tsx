"use client";

import Link from "next/link";

import { AlertBanner } from "@/components/shared/AlertBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { useAlertCount, useAlerts } from "@/lib/hooks/useAlerts";
import { useGRNs } from "@/lib/hooks/useGrns";

export default function DashboardPage() {
  const { data: alerts } = useAlertCount();
  const { data: alertItems } = useAlerts();
  const { data: grns } = useGRNs();

  const pending = (grns ?? []).find((grn) => grn.status === "RECEIVED");

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" subtitle="Daily planning command center" />
      <AlertBanner count={alerts} />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-300/80 bg-white/90 p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.12em] text-slate-500">Unread Alerts</p>
          <p className="mt-1 text-3xl font-semibold text-slate-950">{alerts?.unread ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-300/80 bg-white/90 p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.12em] text-slate-500">Recent GRNs</p>
          <p className="mt-1 text-3xl font-semibold text-slate-950">{grns?.slice(0, 2).length ?? 0}</p>
        </div>
        <div className="rounded-xl border border-slate-300/80 bg-white/90 p-4 shadow-sm">
          <p className="text-xs uppercase tracking-[0.12em] text-slate-500">Pending Allocation</p>
          <p className="mt-1 text-3xl font-semibold text-slate-950">{pending ? 1 : 0}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="rounded-xl border border-slate-300/80 bg-white/90 p-4 shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-slate-700">Recent GRNs</h2>
          <div className="mt-3 space-y-2 text-sm">
            {(grns ?? []).slice(0, 5).map((grn) => (
              <div
                key={grn.id}
                className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50/60 px-3 py-2"
              >
                <span className="font-medium text-slate-800">
                  {grn.grn_code} · {grn.status}
                </span>
                <Link className="text-slate-700 underline-offset-2 hover:underline" href={`/grn/${grn.id}`}>
                  Open
                </Link>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-slate-300/80 bg-white/90 p-4 shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-[0.08em] text-slate-700">Active Alert Messages</h2>
          <div className="mt-3 space-y-2">
            {(alertItems ?? []).slice(0, 4).map((alert) => (
              <div key={alert.id} className="rounded-md border border-slate-200 bg-slate-50/70 px-3 py-2 text-sm">
                <p className="font-medium text-slate-900">{alert.title}</p>
                <p className="text-slate-600">{alert.message}</p>
              </div>
            ))}
            {!alertItems || alertItems.length === 0 ? (
              <p className="rounded-md border border-slate-200 bg-slate-50/70 px-3 py-2 text-sm text-slate-600">
                No active alerts.
              </p>
            ) : null}
          </div>
        </div>
      </div>

      {pending ? (
        <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Pending allocation: {pending.grn_code}.{" "}
          <Link className="font-medium underline underline-offset-2" href={`/grn/${pending.id}`}>
            Generate now
          </Link>
        </div>
      ) : null}
    </div>
  );
}
