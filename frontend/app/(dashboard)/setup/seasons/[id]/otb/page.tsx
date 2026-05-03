"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";

import { ApiError, apiRequest } from "@/lib/api";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Season {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
}

interface OTBRow {
  id?: string;
  category: string;
  month: string; // ISO date "YYYY-MM-DD"
  planned_sales: number;
  planned_closing_stock: number;
  opening_stock: number;
  on_order: number;
  otb_value?: number;
}

interface SuggestCategory {
  category: string;
  last_actual_revenue: number;
  last_actual_units: number;
  growth_factor: number;
  suggested_planned_sales: number;
  narration: string;
}

interface SuggestResponse {
  season_id: string;
  growth_factor: number;
  categories: SuggestCategory[];
  totals: {
    last_actual_revenue: number;
    suggested_planned_sales: number;
  };
  note: string;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtCurrency(n: number): string {
  if (n === 0) return "₹0";
  if (Math.abs(n) >= 1_00_00_000) return `₹${(n / 1_00_00_000).toFixed(2)} Cr`;
  if (Math.abs(n) >= 1_00_000) return `₹${(n / 1_00_000).toFixed(2)} L`;
  return `₹${n.toLocaleString()}`;
}

function rowKey(category: string, month: string): string {
  return `${category}::${month}`;
}

// ─── Suggest Panel ───────────────────────────────────────────────────────────

function SuggestPanel({
  seasonId,
  onApply,
}: {
  seasonId: string;
  onApply: (cats: SuggestCategory[], month: string) => void;
}) {
  const [growth, setGrowth] = useState<string>("1.10");
  const [month, setMonth] = useState<string>("");
  const [resp, setResp] = useState<SuggestResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSuggest = useCallback(async () => {
    const g = parseFloat(growth);
    if (Number.isNaN(g) || g < 0.5 || g > 3.0) {
      setError("Growth factor must be between 0.5 and 3.0");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await apiRequest<SuggestResponse>(
        `/api/v1/seasons/${seasonId}/otb/suggest`,
        {
          method: "POST",
          body: JSON.stringify({ growth_factor: g }),
        }
      );
      setResp(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load suggestions.");
    } finally {
      setLoading(false);
    }
  }, [seasonId, growth]);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <div className="mb-3 flex items-baseline justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">
            Suggest OTB from last season
          </h2>
          <p className="text-xs text-slate-500">
            History-driven hint, not a decision. AI explains the rationale.
          </p>
        </div>
        <span className="text-[11px] text-slate-400">
          Source: SalesData × growth factor
        </span>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-slate-700">
            Growth factor
          </span>
          <input
            type="number"
            step="0.05"
            min="0.5"
            max="3.0"
            value={growth}
            onChange={(e) => setGrowth(e.target.value)}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          />
          <span className="mt-1 block text-[10px] text-slate-400">
            1.10 = 10% growth · 0.95 = 5% decline · clamp 0.5–3.0
          </span>
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-slate-700">
            Apply to month
          </span>
          <input
            type="date"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          />
          <span className="mt-1 block text-[10px] text-slate-400">
            Suggested values are written into this month's row when you click Apply.
          </span>
        </label>
        <div className="flex items-end">
          <button
            onClick={runSuggest}
            disabled={loading}
            className="w-full rounded-md bg-slate-900 px-3 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? "Computing…" : "Suggest from history"}
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {resp && (
        <div className="mt-4">
          <div className="mb-3 flex items-baseline justify-between">
            <p className="text-xs text-slate-500">{resp.note}</p>
            <p className="text-xs font-medium text-slate-700">
              Total suggested:{" "}
              <span className="font-semibold text-slate-900">
                {fmtCurrency(resp.totals.suggested_planned_sales)}
              </span>{" "}
              <span className="text-slate-400">
                (LY actual {fmtCurrency(resp.totals.last_actual_revenue)})
              </span>
            </p>
          </div>

          {resp.categories.length === 0 ? (
            <p className="rounded-md bg-slate-50 px-3 py-3 text-xs text-slate-500">
              No sales history available — upload last season&apos;s sales to enable
              suggestions.
            </p>
          ) : (
            <div className="space-y-2">
              {resp.categories.map((cat) => (
                <div
                  key={cat.category}
                  className="flex items-start justify-between gap-4 rounded-md border border-slate-200 bg-slate-50 px-3 py-2.5"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-semibold text-slate-900">{cat.category}</span>
                      <span className="rounded-full bg-white px-2 py-0.5 text-[10px] font-medium text-slate-600 border border-slate-200">
                        ×{cat.growth_factor.toFixed(2)}
                      </span>
                    </div>
                    <p className="mt-1 text-[11px] text-slate-600 leading-relaxed">
                      {cat.narration}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-sm font-bold tabular-nums text-slate-900">
                      {fmtCurrency(cat.suggested_planned_sales)}
                    </p>
                    <p className="text-[10px] text-slate-400">
                      LY {fmtCurrency(cat.last_actual_revenue)}
                    </p>
                  </div>
                </div>
              ))}

              <button
                onClick={() => {
                  if (!month) {
                    setError("Pick a month first.");
                    return;
                  }
                  onApply(resp.categories, month);
                }}
                disabled={!month}
                className="mt-2 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Apply all to {month || "(pick month)"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── OTB Grid ─────────────────────────────────────────────────────────────────

function OTBGrid({
  seasonId,
  rows,
  draft,
  setDraft,
  saving,
  onSave,
}: {
  seasonId: string;
  rows: OTBRow[];
  draft: Map<string, OTBRow>;
  setDraft: (next: Map<string, OTBRow>) => void;
  saving: boolean;
  onSave: () => void;
}) {
  const allRows = useMemo(() => {
    // Merge persisted rows with draft additions, draft wins.
    const map = new Map<string, OTBRow>();
    for (const r of rows) map.set(rowKey(r.category, r.month), r);
    for (const [k, r] of draft.entries()) map.set(k, r);
    return Array.from(map.values()).sort((a, b) => {
      if (a.month !== b.month) return a.month.localeCompare(b.month);
      return a.category.localeCompare(b.category);
    });
  }, [rows, draft]);

  const [newCategory, setNewCategory] = useState("");
  const [newMonth, setNewMonth] = useState("");

  const updateField = (
    cat: string,
    month: string,
    field: keyof OTBRow,
    value: string
  ) => {
    const num = value === "" ? 0 : parseFloat(value);
    if (Number.isNaN(num)) return;
    const key = rowKey(cat, month);
    const existing =
      draft.get(key) ?? rows.find((r) => r.category === cat && r.month === month);
    if (!existing) return;
    const next = new Map(draft);
    next.set(key, { ...existing, [field]: num });
    setDraft(next);
  };

  const addRow = () => {
    if (!newCategory.trim() || !newMonth) return;
    const key = rowKey(newCategory.trim(), newMonth);
    if (
      rows.some((r) => r.category === newCategory.trim() && r.month === newMonth) ||
      draft.has(key)
    )
      return;
    const next = new Map(draft);
    next.set(key, {
      category: newCategory.trim(),
      month: newMonth,
      planned_sales: 0,
      planned_closing_stock: 0,
      opening_stock: 0,
      on_order: 0,
    });
    setDraft(next);
    setNewCategory("");
    setNewMonth("");
  };

  const isDirty = (r: OTBRow) =>
    draft.has(rowKey(r.category, r.month));

  const otbValue = (r: OTBRow) =>
    r.planned_sales + r.planned_closing_stock - r.opening_stock - r.on_order;

  return (
    <div className="rounded-xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">OTB grid</h2>
          <p className="text-xs text-slate-500">
            One row per (category, month). OTB = planned_sales + closing − opening −
            on_order.
          </p>
        </div>
        <button
          onClick={onSave}
          disabled={saving || draft.size === 0}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? "Saving…" : `Save ${draft.size} change${draft.size === 1 ? "" : "s"}`}
        </button>
      </div>

      <div className="overflow-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Category</th>
              <th className="px-4 py-2 font-medium">Month</th>
              <th className="px-4 py-2 font-medium text-right">Planned Sales</th>
              <th className="px-4 py-2 font-medium text-right">+ Closing Stock</th>
              <th className="px-4 py-2 font-medium text-right">− Opening Stock</th>
              <th className="px-4 py-2 font-medium text-right">− On Order</th>
              <th className="px-4 py-2 font-medium text-right">= OTB</th>
            </tr>
          </thead>
          <tbody>
            {allRows.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-xs text-slate-400">
                  No OTB rows yet. Add one below or use the Suggest panel above.
                </td>
              </tr>
            ) : (
              allRows.map((r) => {
                const dirty = isDirty(r);
                return (
                  <tr
                    key={rowKey(r.category, r.month)}
                    className={`border-t border-slate-100 ${
                      dirty ? "bg-amber-50/40" : ""
                    }`}
                  >
                    <td className="px-4 py-2 font-medium text-slate-800">
                      {r.category}
                    </td>
                    <td className="px-4 py-2 text-slate-600">{r.month}</td>
                    {(
                      [
                        "planned_sales",
                        "planned_closing_stock",
                        "opening_stock",
                        "on_order",
                      ] as const
                    ).map((field) => (
                      <td key={field} className="px-2 py-1.5 text-right">
                        <input
                          type="number"
                          step="1"
                          value={r[field] || 0}
                          onChange={(e) =>
                            updateField(r.category, r.month, field, e.target.value)
                          }
                          className="w-28 rounded border border-transparent px-2 py-1 text-right text-sm tabular-nums hover:border-slate-300 focus:border-slate-500 focus:bg-white focus:outline-none"
                        />
                      </td>
                    ))}
                    <td className="px-4 py-2 text-right font-bold tabular-nums text-slate-900">
                      {fmtCurrency(otbValue(r))}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-end gap-3 border-t border-slate-200 bg-slate-50/60 px-5 py-3">
        <label className="block">
          <span className="mb-1 block text-[11px] font-medium text-slate-600">
            New category
          </span>
          <input
            type="text"
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            placeholder="e.g. Kurtis"
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-slate-500 focus:outline-none"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-[11px] font-medium text-slate-600">
            Month
          </span>
          <input
            type="date"
            value={newMonth}
            onChange={(e) => setNewMonth(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-slate-500 focus:outline-none"
          />
        </label>
        <button
          onClick={addRow}
          disabled={!newCategory.trim() || !newMonth}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          + Add row
        </button>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function SeasonOTBPage() {
  const params = useParams<{ id: string }>();
  const seasonId = params.id;

  const { data: seasons } = useSWR<Season[]>("/api/v1/seasons", (path: string) =>
    apiRequest<Season[]>(path)
  );
  const season = (seasons ?? []).find((s) => s.id === seasonId) ?? null;

  const { data: rows, mutate: mutateRows } = useSWR<OTBRow[]>(
    `/api/v1/seasons/${seasonId}/otb`,
    (path: string) => apiRequest<OTBRow[]>(path)
  );

  const [draft, setDraft] = useState<Map<string, OTBRow>>(new Map());
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const persistDraft = useCallback(async () => {
    if (draft.size === 0) return;
    setSaving(true);
    try {
      const payload = Array.from(draft.values()).map((r) => ({
        category: r.category,
        month: r.month,
        planned_sales: r.planned_sales,
        planned_closing_stock: r.planned_closing_stock,
        opening_stock: r.opening_stock,
        on_order: r.on_order,
      }));
      await apiRequest(`/api/v1/seasons/${seasonId}/otb`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setDraft(new Map());
      await mutateRows();
      // workflow-state may have advanced from DRAFT → PLANNING
      await globalMutate(`/api/v1/seasons/${seasonId}/workflow-state`);
      setToast(`Saved ${payload.length} OTB row${payload.length === 1 ? "" : "s"}.`);
      window.setTimeout(() => setToast(null), 2200);
    } catch (err) {
      setToast(
        err instanceof ApiError
          ? `Save failed: ${err.message}`
          : "Save failed. Try again."
      );
      window.setTimeout(() => setToast(null), 3500);
    } finally {
      setSaving(false);
    }
  }, [draft, seasonId, mutateRows]);

  const applySuggestions = useCallback(
    (cats: SuggestCategory[], month: string) => {
      const next = new Map(draft);
      for (const c of cats) {
        const key = rowKey(c.category, month);
        const existing =
          draft.get(key) ??
          (rows ?? []).find((r) => r.category === c.category && r.month === month);
        next.set(key, {
          ...(existing ?? {
            category: c.category,
            month,
            planned_sales: 0,
            planned_closing_stock: 0,
            opening_stock: 0,
            on_order: 0,
          }),
          planned_sales: c.suggested_planned_sales,
        });
      }
      setDraft(next);
      setToast(
        `Applied ${cats.length} suggestion${cats.length === 1 ? "" : "s"} to ${month}. Review and Save.`
      );
      window.setTimeout(() => setToast(null), 3000);
    },
    [draft, rows]
  );

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">
            {season ? season.name : "Season"} · OTB
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            Open-To-Buy budget per category × month. The Suggest panel below uses
            last-season actuals × growth factor; nothing is written until you Save.
          </p>
        </div>
        <Link
          href="/setup/seasons"
          className="text-xs text-slate-500 underline hover:text-slate-700"
        >
          ← Back to Seasons
        </Link>
      </div>

      <SuggestPanel seasonId={seasonId} onApply={applySuggestions} />

      <OTBGrid
        seasonId={seasonId}
        rows={rows ?? []}
        draft={draft}
        setDraft={setDraft}
        saving={saving}
        onSave={persistDraft}
      />

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
