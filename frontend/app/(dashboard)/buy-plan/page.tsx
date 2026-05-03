"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { mutate } from "swr";

import { apiRequest, ApiError } from "@/lib/api";
import { useBuyPlans, useBuyPlanReconciliation } from "@/lib/hooks/useBuyPlans";
import { useSeasons } from "@/lib/hooks/useSeasons";
import { BuyPlanFileWithStats } from "@/types/buy_plan";

// ─── OTB usage cell ────────────────────────────────────────────────────────────
function OTBUsageCell({ fileId }: { fileId: string }) {
  const { data: recon, isLoading } = useBuyPlanReconciliation(fileId);

  if (isLoading) {
    return <div className="h-4 w-24 animate-pulse rounded bg-slate-100" />;
  }

  if (!recon || recon.total_otb === 0) {
    return <span className="text-xs text-slate-400">No OTB data</span>;
  }

  const pct = Math.min(recon.overall_usage_pct, 100);
  const overrun = recon.overall_usage_pct > 100;
  const amber = recon.overall_usage_pct >= 80 && !overrun;

  const barColor = overrun ? "bg-red-500" : amber ? "bg-amber-400" : "bg-emerald-500";
  const textColor = overrun ? "text-red-600" : amber ? "text-amber-600" : "text-emerald-600";

  return (
    <div className="flex items-center gap-2">
      <div className="h-2 w-24 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs font-medium ${textColor}`}>
        {recon.overall_usage_pct.toFixed(1)}%
      </span>
    </div>
  );
}

// ─── New Plan modal ───────────────────────────────────────────────────────────
function NewPlanModal({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const { data: seasons } = useSeasons();
  const [name, setName] = useState("");
  const [seasonId, setSeasonId] = useState<string>("");
  const [notes, setNotes] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      const created = await apiRequest<BuyPlanFileWithStats>("/api/v1/buy-plans", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          season_id: seasonId || null,
          notes: notes.trim() || null,
        }),
      });
      // Refresh list and navigate to detail
      await mutate("/api/v1/buy-plans");
      router.push(`/buy-plan/${created.id}`);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not create buy plan. Please try again."
      );
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-xl"
      >
        <div className="mb-4">
          <h2 className="text-base font-semibold text-slate-900">New Buy Plan</h2>
          <p className="mt-1 text-xs text-slate-500">
            Start with an empty plan. Add lines manually or import a CSV later.
          </p>
        </div>

        <div className="space-y-4">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-700">
              Plan Name <span className="text-red-500">*</span>
            </span>
            <input
              autoFocus
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. SS26 Master Plan"
              maxLength={255}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              required
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-700">
              Season <span className="text-slate-400">(optional)</span>
            </span>
            <select
              value={seasonId}
              onChange={(e) => setSeasonId(e.target.value)}
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            >
              <option value="">— No season —</option>
              {(seasons ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.status})
                </option>
              ))}
            </select>
            <span className="mt-1 block text-[11px] text-slate-400">
              Linking a season enables OTB reconciliation.
            </span>
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-700">
              Notes <span className="text-slate-400">(optional)</span>
            </span>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Anything worth remembering about this plan…"
              rows={2}
              className="w-full resize-none rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
            />
          </label>

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </div>
          )}
        </div>

        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            disabled={submitting}
            className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !name.trim()}
            className="rounded-md bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Creating…" : "Create Plan"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────
export default function BuyPlanListPage() {
  const { data: plans, isLoading } = useBuyPlans();
  const [showNew, setShowNew] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Buy Plans</h1>
          <p className="mt-1 text-sm text-slate-500">
            What you&apos;ve committed to buy this season.
          </p>
        </div>
        <button
          onClick={() => setShowNew(true)}
          className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-3.5 py-2 text-sm font-semibold text-white hover:bg-slate-800"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Plan
        </button>
      </div>

      {!isLoading && (plans ?? []).length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
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
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01"
            />
          </svg>
          <p className="mt-2 font-medium text-slate-700">No buy plans yet</p>
          <p className="mt-1 text-sm text-slate-500">
            Create one with the button above, or upload a Buy File in the{" "}
            <Link href="/ingestion" className="font-medium text-slate-900 underline">
              Upload Data
            </Link>{" "}
            section.
          </p>
        </div>
      ) : null}

      {isLoading || (plans ?? []).length > 0 ? (
        <div className="overflow-auto rounded-xl border border-slate-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs text-slate-500">
              <tr>
                <th className="px-5 py-3 font-medium">Plan Name</th>
                <th className="px-5 py-3 font-medium">Season</th>
                <th className="px-5 py-3 font-medium text-right">Total Styles</th>
                <th className="px-5 py-3 font-medium text-right">Total Units</th>
                <th className="px-5 py-3 font-medium">OTB Usage</th>
                <th className="px-5 py-3 font-medium" />
              </tr>
            </thead>
            <tbody>
              {isLoading
                ? Array.from({ length: 4 }).map((_, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      <td className="px-5 py-3" colSpan={6}>
                        <div className="h-5 animate-pulse rounded bg-slate-100" />
                      </td>
                    </tr>
                  ))
                : (plans ?? []).map((plan: BuyPlanFileWithStats) => (
                    <tr
                      key={plan.id}
                      className="border-t border-slate-100 hover:bg-slate-50/60"
                    >
                      <td className="px-5 py-3 font-medium text-slate-800">{plan.name}</td>
                      <td className="px-5 py-3 text-slate-600">
                        {plan.season_id ? (
                          <span className="inline-flex rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                            {plan.season_id.slice(0, 8)}…
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-5 py-3 text-right font-medium text-slate-800">
                        {plan.total_styles.toLocaleString()}
                      </td>
                      <td className="px-5 py-3 text-right font-medium text-slate-800">
                        {plan.total_units.toLocaleString()}
                      </td>
                      <td className="px-5 py-3">
                        <OTBUsageCell fileId={plan.id} />
                      </td>
                      <td className="px-5 py-3 text-right">
                        <Link
                          href={`/buy-plan/${plan.id}`}
                          className="inline-flex items-center gap-1 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-medium text-white hover:bg-slate-800"
                        >
                          View →
                        </Link>
                      </td>
                    </tr>
                  ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {showNew && <NewPlanModal onClose={() => setShowNew(false)} />}
    </div>
  );
}
