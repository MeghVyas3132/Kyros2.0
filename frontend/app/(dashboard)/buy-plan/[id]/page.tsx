"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { mutate } from "swr";

import { apiRequest, ApiError } from "@/lib/api";
import {
  useBuyPlan,
  useBuyPlanLines,
  useBuyPlanReconciliation,
} from "@/lib/hooks/useBuyPlans";
import {
  BuyPlanLine,
  BuyPlanLineUpdate,
  OTBReconciliationRow,
  StyleGroup,
} from "@/types/buy_plan";

// ─── Toast ────────────────────────────────────────────────────────────────────

function Toast({
  message,
  type,
}: {
  message: string;
  type: "success" | "error";
}) {
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium text-white shadow-lg transition-all ${
        type === "success" ? "bg-emerald-600" : "bg-red-600"
      }`}
    >
      {type === "success" ? (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      )}
      {message}
    </div>
  );
}

// ─── OTB Reconciliation Bar ───────────────────────────────────────────────────

function OTBReconciliationBar({
  rows,
  totalOtb,
  totalCommitted,
  overallUsagePct,
}: {
  rows: OTBReconciliationRow[];
  totalOtb: number;
  totalCommitted: number;
  overallUsagePct: number;
}) {
  const overrunCount = rows.filter((r) => r.is_overrun).length;

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-slate-900">OTB Budget vs Committed</h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Total OTB: <span className="font-medium text-slate-700">£{totalOtb.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            {" · "}
            Committed: <span className="font-medium text-slate-700">£{totalCommitted.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
            {" · "}
            Usage: <span className={`font-medium ${overallUsagePct > 100 ? "text-red-600" : overallUsagePct >= 80 ? "text-amber-600" : "text-emerald-600"}`}>
              {overallUsagePct.toFixed(1)}%
            </span>
          </p>
        </div>
        {overrunCount > 0 && (
          <div className="flex items-center gap-1.5 rounded-lg bg-red-50 px-3 py-1.5 text-xs font-semibold text-red-600 border border-red-200">
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            {overrunCount} {overrunCount === 1 ? "category exceeds" : "categories exceed"} OTB budget
          </div>
        )}
      </div>

      <div className="space-y-2">
        {rows.map((row) => {
          const pct = Math.min(row.otb_usage_pct, 100);
          const barColor = row.is_overrun
            ? "bg-red-500"
            : row.otb_usage_pct >= 80
            ? "bg-amber-400"
            : "bg-emerald-500";
          const textColor = row.is_overrun
            ? "text-red-600"
            : row.otb_usage_pct >= 80
            ? "text-amber-600"
            : "text-emerald-600";

          return (
            <div key={row.category} className="flex items-center gap-3">
              <span className="w-28 shrink-0 text-xs font-medium text-slate-700 truncate">
                {row.category}
              </span>
              <span className="w-20 shrink-0 text-right text-xs text-slate-500">
                £{row.buy_plan_cost.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </span>
              <span className="w-20 shrink-0 text-right text-xs text-slate-400">
                / £{row.otb_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </span>
              <div className="flex-1 h-2 overflow-hidden rounded-full bg-slate-100">
                <div
                  className={`h-full rounded-full transition-all ${barColor}`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className={`w-12 shrink-0 text-right text-xs font-semibold ${textColor}`}>
                {row.otb_usage_pct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Inline editable cell ─────────────────────────────────────────────────────

function InlineCell({
  value,
  type,
  onSave,
  className,
}: {
  value: string | number | null;
  type: "text" | "number" | "date";
  onSave: (newValue: string) => void;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<string>("");

  const displayValue =
    value === null || value === undefined
      ? "—"
      : type === "number" && typeof value === "number"
      ? value.toLocaleString()
      : String(value);

  const startEditing = () => {
    setDraft(value === null || value === undefined ? "" : String(value));
    setEditing(true);
  };

  const commit = () => {
    setEditing(false);
    if (draft !== String(value ?? "")) {
      onSave(draft);
    }
  };

  if (editing) {
    return (
      <input
        autoFocus
        type={type}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") setEditing(false);
        }}
        className={`w-full rounded border border-slate-300 bg-white px-2 py-0.5 text-sm focus:border-slate-500 focus:outline-none ${className ?? ""}`}
      />
    );
  }

  return (
    <button
      onClick={startEditing}
      className={`w-full text-left hover:text-slate-900 cursor-text rounded px-1 py-0.5 hover:bg-slate-100 transition-colors ${
        value === null || value === undefined ? "text-slate-400" : "text-slate-700"
      } ${className ?? ""}`}
    >
      {displayValue}
    </button>
  );
}

// ─── Group lines by style ─────────────────────────────────────────────────────

function groupByStyle(lines: BuyPlanLine[]): StyleGroup[] {
  const map = new Map<string, StyleGroup>();

  for (const line of lines) {
    const key = line.style_code ?? line.sku_id;
    const existing = map.get(key);
    if (existing) {
      existing.lines.push(line);
      existing.total_buy_qty += line.total_buy_qty ?? 0;
      // Prefer non-null values for shared fields
      if (!existing.vendor_name && line.vendor_name) existing.vendor_name = line.vendor_name;
      if (!existing.expected_delivery_week && line.expected_delivery_week)
        existing.expected_delivery_week = line.expected_delivery_week;
      if (existing.planned_cost_per_unit === null && line.planned_cost_per_unit !== null)
        existing.planned_cost_per_unit = line.planned_cost_per_unit;
      if (existing.moq === null && line.moq !== null) existing.moq = line.moq;
      if (existing.planned_price_per_unit === null && line.planned_price_per_unit !== null)
        existing.planned_price_per_unit = line.planned_price_per_unit;
      if (existing.planned_margin_pct === null && line.planned_margin_pct !== null)
        existing.planned_margin_pct = line.planned_margin_pct;
    } else {
      map.set(key, {
        style_code: line.style_code ?? "—",
        style_name: line.style_name,
        category: line.category,
        price_band: line.price_band,
        style_risk_group: line.style_risk_group,
        colour: line.colour,
        vendor_name: line.vendor_name,
        expected_delivery_week: line.expected_delivery_week,
        planned_cost_per_unit: line.planned_cost_per_unit,
        moq: line.moq,
        planned_price_per_unit: line.planned_price_per_unit,
        planned_margin_pct: line.planned_margin_pct,
        total_buy_qty: line.total_buy_qty ?? 0,
        lines: [line],
      });
    }
  }

  return Array.from(map.values());
}

// ─── Add Line modal ───────────────────────────────────────────────────────────

interface SkuOption {
  id: string;
  sku_code: string;
  style_code: string;
  style_name: string | null;
  category: string | null;
  size: string | null;
  colour: string | null;
  price_band: string | null;
}

const RISK_GROUPS = ["PROVEN", "CONFIDENT", "EXPERIMENTAL"] as const;

function AddLineModal({
  fileId,
  onClose,
  onSaved,
}: {
  fileId: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [search, setSearch] = useState("");
  const [skuResults, setSkuResults] = useState<SkuOption[]>([]);
  const [searching, setSearching] = useState(false);
  const [selectedSku, setSelectedSku] = useState<SkuOption | null>(null);

  const [totalBuyQty, setTotalBuyQty] = useState<string>("");
  const [vendorName, setVendorName] = useState("");
  const [storeGroupRule, setStoreGroupRule] = useState("");
  const [styleRiskGroup, setStyleRiskGroup] = useState<string>("");
  const [deliveryWeek, setDeliveryWeek] = useState("");
  const [costPerUnit, setCostPerUnit] = useState("");
  const [pricePerUnit, setPricePerUnit] = useState("");
  const [moq, setMoq] = useState("");
  const [marginPct, setMarginPct] = useState("");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Debounced SKU search
  useEffect(() => {
    if (selectedSku) return; // freeze search once a pick is made
    const trimmed = search.trim();
    if (trimmed.length < 2) {
      setSkuResults([]);
      return;
    }
    setSearching(true);
    const t = window.setTimeout(() => {
      void apiRequest<SkuOption[]>(
        `/api/v1/skus?search=${encodeURIComponent(trimmed)}&page_size=20`
      )
        .then((rows) => setSkuResults(rows ?? []))
        .catch(() => setSkuResults([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => window.clearTimeout(t);
  }, [search, selectedSku]);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!selectedSku) {
      setError("Pick a SKU first.");
      return;
    }
    const qty = parseInt(totalBuyQty, 10);
    if (Number.isNaN(qty) || qty <= 0) {
      setError("Total Buy Qty must be a positive number.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await apiRequest(`/api/v1/buy-plans/${fileId}/lines`, {
        method: "POST",
        body: JSON.stringify({
          sku_id: selectedSku.id,
          total_buy_qty: qty,
          vendor_name: vendorName.trim() || null,
          store_group_rule: storeGroupRule.trim() || null,
          style_risk_group: styleRiskGroup || null,
          expected_delivery_week: deliveryWeek || null,
          planned_cost_per_unit: costPerUnit === "" ? null : parseFloat(costPerUnit),
          planned_price_per_unit: pricePerUnit === "" ? null : parseFloat(pricePerUnit),
          moq: moq === "" ? null : parseInt(moq, 10),
          planned_margin_pct: marginPct === "" ? null : parseFloat(marginPct),
        }),
      });
      onSaved();
      onClose();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not add line. Please try again."
      );
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-xl rounded-xl border border-slate-200 bg-white p-6 shadow-xl"
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-base font-semibold text-slate-900">Add line to plan</h2>
            <p className="mt-1 text-xs text-slate-500">
              Pick a SKU, set the buy quantity, and optionally fill commercial fields.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="text-slate-400 hover:text-slate-600"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-3">
          {/* SKU picker */}
          <div className="relative">
            <span className="mb-1 block text-xs font-medium text-slate-700">
              SKU <span className="text-red-500">*</span>
            </span>
            {selectedSku ? (
              <div className="flex items-center justify-between gap-2 rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm">
                <span className="font-mono text-xs text-slate-800">{selectedSku.sku_code}</span>
                <span className="flex-1 truncate text-slate-700">
                  {selectedSku.style_name ?? selectedSku.style_code}{" "}
                  <span className="text-slate-400">
                    {selectedSku.size ? `· ${selectedSku.size}` : ""}{" "}
                    {selectedSku.colour ? `· ${selectedSku.colour}` : ""}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedSku(null);
                    setSearch("");
                    setSkuResults([]);
                  }}
                  className="text-xs text-slate-500 hover:text-slate-700 underline"
                >
                  change
                </button>
              </div>
            ) : (
              <>
                <input
                  autoFocus
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Type SKU code, style code, or style name…"
                  className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
                />
                {searching ? (
                  <p className="mt-1 text-[11px] text-slate-400">Searching…</p>
                ) : null}
                {!searching && skuResults.length > 0 && (
                  <ul className="mt-1 max-h-40 overflow-auto rounded-md border border-slate-200 bg-white shadow-sm">
                    {skuResults.map((s) => (
                      <li
                        key={s.id}
                        onClick={() => setSelectedSku(s)}
                        className="cursor-pointer px-3 py-1.5 text-xs hover:bg-slate-50"
                      >
                        <span className="font-mono text-[11px] text-slate-500">{s.sku_code}</span>{" "}
                        <span className="text-slate-800">
                          {s.style_name ?? s.style_code}
                        </span>{" "}
                        <span className="text-slate-400">
                          {s.size ? `· ${s.size}` : ""} {s.category ? `· ${s.category}` : ""}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                {!searching && search.length >= 2 && skuResults.length === 0 ? (
                  <p className="mt-1 text-[11px] text-slate-400">No matches.</p>
                ) : null}
              </>
            )}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">
                Total Buy Qty <span className="text-red-500">*</span>
              </span>
              <input
                type="number"
                min="1"
                value={totalBuyQty}
                onChange={(e) => setTotalBuyQty(e.target.value)}
                required
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">
                Risk Group
              </span>
              <select
                value={styleRiskGroup}
                onChange={(e) => setStyleRiskGroup(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              >
                <option value="">—</option>
                {RISK_GROUPS.map((g) => (
                  <option key={g} value={g}>
                    {g}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">Vendor</span>
              <input
                type="text"
                value={vendorName}
                onChange={(e) => setVendorName(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">Delivery Week</span>
              <input
                type="date"
                value={deliveryWeek}
                onChange={(e) => setDeliveryWeek(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">Cost / Unit</span>
              <input
                type="number"
                step="0.01"
                value={costPerUnit}
                onChange={(e) => setCostPerUnit(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">Price / Unit</span>
              <input
                type="number"
                step="0.01"
                value={pricePerUnit}
                onChange={(e) => setPricePerUnit(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              />
            </label>

            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">MOQ</span>
              <input
                type="number"
                min="0"
                value={moq}
                onChange={(e) => setMoq(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-slate-700">Margin %</span>
              <input
                type="number"
                step="0.01"
                value={marginPct}
                onChange={(e) => setMarginPct(e.target.value)}
                className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
              />
            </label>
          </div>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-slate-700">
              Store Group Rule <span className="text-slate-400">(optional)</span>
            </span>
            <input
              type="text"
              value={storeGroupRule}
              onChange={(e) => setStoreGroupRule(e.target.value)}
              placeholder="e.g. METRO, ALL, A_GRADE_ONLY"
              className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
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
            disabled={submitting || !selectedSku || !totalBuyQty}
            className="rounded-md bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submitting ? "Adding…" : "Add Line"}
          </button>
        </div>
      </form>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function BuyPlanDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const fileId = params.id;

  const { data: plan, isLoading: planLoading } = useBuyPlan(fileId);
  const { data: lines, isLoading: linesLoading } = useBuyPlanLines(fileId);
  const {
    data: recon,
    isLoading: reconLoading,
    mutate: mutateRecon,
  } = useBuyPlanReconciliation(fileId);

  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>("");
  const [riskFilter, setRiskFilter] = useState<string>("");
  const [confirmingDeletePlan, setConfirmingDeletePlan] = useState(false);
  const [deletingStyle, setDeletingStyle] = useState<string | null>(null);
  const [showAddLine, setShowAddLine] = useState(false);

  const showToast = useCallback(
    (message: string, type: "success" | "error") => {
      setToast({ message, type });
      setTimeout(() => setToast(null), 2500);
    },
    []
  );

  const handleDeletePlan = useCallback(async () => {
    try {
      await apiRequest(`/api/v1/buy-plans/${fileId}`, { method: "DELETE" });
      await mutate("/api/v1/buy-plans");
      router.push("/buy-plan");
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Could not delete plan.";
      showToast(msg, "error");
      setConfirmingDeletePlan(false);
    }
  }, [fileId, router, showToast]);

  const handleDeleteStyleGroup = useCallback(
    async (styleCode: string, lineIds: string[]) => {
      setDeletingStyle(styleCode);
      try {
        // Delete every size-line for this style. Sequential to surface a
        // useful error if a single delete fails.
        for (const lineId of lineIds) {
          await apiRequest(`/api/v1/buy-plans/${fileId}/lines/${lineId}`, {
            method: "DELETE",
          });
        }
        await mutate(`/api/v1/buy-plans/${fileId}/lines`);
        await mutateRecon();
        showToast(`Removed ${styleCode}`, "success");
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : "Could not remove style.";
        showToast(msg, "error");
      } finally {
        setDeletingStyle(null);
      }
    },
    [fileId, mutateRecon, showToast]
  );

  const handleFieldSave = useCallback(
    async (lineId: string, field: keyof BuyPlanLineUpdate, rawValue: string) => {
      let value: string | number | null = rawValue === "" ? null : rawValue;

      // Type coercion
      if (
        field === "planned_cost_per_unit" ||
        field === "planned_price_per_unit" ||
        field === "planned_margin_pct"
      ) {
        value = rawValue === "" ? null : parseFloat(rawValue);
      } else if (field === "total_buy_qty" || field === "moq") {
        value = rawValue === "" ? null : parseInt(rawValue, 10);
      }

      const update: BuyPlanLineUpdate = { [field]: value };

      try {
        await apiRequest(`/api/v1/buy-plans/${fileId}/lines/${lineId}`, {
          method: "PATCH",
          body: JSON.stringify(update),
        });
        showToast("Saved", "success");
        // Refresh lines and reconciliation
        mutate(`/api/v1/buy-plans/${fileId}/lines`);
        mutateRecon();
      } catch {
        showToast("Error saving — please try again", "error");
      }
    },
    [fileId, mutateRecon, showToast]
  );

  // Unique filter options
  const categories = useMemo(() => {
    if (!lines) return [];
    return Array.from(new Set(lines.map((l) => l.category).filter(Boolean) as string[])).sort();
  }, [lines]);

  const riskGroups = useMemo(() => {
    if (!lines) return [];
    return Array.from(
      new Set(lines.map((l) => l.style_risk_group).filter(Boolean) as string[])
    ).sort();
  }, [lines]);

  // Grouped + filtered style rows
  const styleGroups = useMemo(() => {
    if (!lines) return [];
    const filtered = lines.filter((l) => {
      if (categoryFilter && l.category !== categoryFilter) return false;
      if (riskFilter && l.style_risk_group !== riskFilter) return false;
      return true;
    });
    return groupByStyle(filtered);
  }, [lines, categoryFilter, riskFilter]);

  const isLoading = planLoading || linesLoading;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          {planLoading ? (
            <div className="h-7 w-64 animate-pulse rounded bg-slate-100" />
          ) : (
            <h1 className="text-2xl font-semibold text-slate-900">
              {plan?.name ?? "Buy Plan"}
            </h1>
          )}
          <p className="mt-1 text-sm text-slate-500">
            Review and edit style-level buy commitments. Click any cell to edit inline.
          </p>
        </div>
        {!planLoading && (
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowAddLine(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
            >
              <svg
                className="h-3.5 w-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              Add Line
            </button>
            <button
              onClick={() => setConfirmingDeletePlan(true)}
              className="inline-flex items-center gap-1.5 rounded-md border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 hover:bg-red-50"
            >
              <svg
                className="h-3.5 w-3.5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6M1 7h22M9 7V4a2 2 0 012-2h2a2 2 0 012 2v3"
                />
              </svg>
              Delete plan
            </button>
          </div>
        )}
      </div>

      {/* OTB Reconciliation Bar */}
      {reconLoading ? (
        <div className="h-32 animate-pulse rounded-xl bg-slate-100" />
      ) : recon && recon.rows.length > 0 ? (
        <OTBReconciliationBar
          rows={recon.rows}
          totalOtb={recon.total_otb}
          totalCommitted={recon.total_committed}
          overallUsagePct={recon.overall_usage_pct}
        />
      ) : null}

      {/* Filters */}
      <div className="flex items-center gap-3">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
        >
          <option value="">All categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>

        <select
          value={riskFilter}
          onChange={(e) => setRiskFilter(e.target.value)}
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-700 focus:border-slate-400 focus:outline-none"
        >
          <option value="">All risk groups</option>
          {riskGroups.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>

        {(categoryFilter || riskFilter) && (
          <button
            onClick={() => {
              setCategoryFilter("");
              setRiskFilter("");
            }}
            className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-500 hover:bg-slate-50"
          >
            Clear filters
          </button>
        )}

        <span className="ml-auto text-xs text-slate-400">
          {styleGroups.length} {styleGroups.length === 1 ? "style" : "styles"}
        </span>
      </div>

      {/* Main table */}
      <div className="overflow-auto rounded-xl border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">Style Code</th>
              <th className="px-4 py-3 font-medium">Style Name</th>
              <th className="px-4 py-3 font-medium">Category</th>
              <th className="px-4 py-3 font-medium">Price Band</th>
              <th className="px-4 py-3 font-medium">Risk Group</th>
              <th className="px-4 py-3 font-medium">Vendor</th>
              <th className="px-4 py-3 font-medium text-right">Units</th>
              <th className="px-4 py-3 font-medium text-right">Cost/Unit</th>
              <th className="px-4 py-3 font-medium text-right">Total Cost</th>
              <th className="px-4 py-3 font-medium">Delivery Week</th>
              <th className="px-4 py-3 font-medium text-right">MOQ</th>
              <th className="px-2 py-3 font-medium" />
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 6 }).map((_, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-4 py-3" colSpan={12}>
                      <div className="h-5 animate-pulse rounded bg-slate-100" />
                    </td>
                  </tr>
                ))
              : styleGroups.map((group) => {
                  const belowMoq =
                    group.moq !== null &&
                    group.total_buy_qty < group.moq;
                  const noVendor = !group.vendor_name;
                  const totalCost =
                    group.planned_cost_per_unit !== null
                      ? group.total_buy_qty * group.planned_cost_per_unit
                      : null;

                  // Row highlight: red > amber
                  const rowClass = noVendor
                    ? "border-t border-slate-100 bg-red-50/40 hover:bg-red-50/60"
                    : belowMoq
                    ? "border-t border-slate-100 bg-amber-50/40 hover:bg-amber-50/60"
                    : "border-t border-slate-100 hover:bg-slate-50/60";

                  // Representative line — first line, for patch calls on shared fields
                  const firstLine = group.lines[0];

                  return (
                    <tr key={group.style_code} className={rowClass}>
                      <td className="px-4 py-2.5 font-mono text-xs font-medium text-slate-800">
                        {group.style_code}
                      </td>
                      <td className="px-4 py-2.5 text-slate-700 max-w-[180px] truncate">
                        {group.style_name ?? "—"}
                      </td>
                      <td className="px-4 py-2.5 text-slate-600">
                        {group.category ?? "—"}
                      </td>
                      <td className="px-4 py-2.5 text-slate-600">
                        {group.price_band ?? "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        {group.style_risk_group ? (
                          <span className="inline-flex rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                            {group.style_risk_group}
                          </span>
                        ) : (
                          <span className="text-slate-400">—</span>
                        )}
                      </td>
                      <td className="px-4 py-2.5 min-w-[130px]">
                        <InlineCell
                          value={group.vendor_name}
                          type="text"
                          onSave={(v) =>
                            Promise.all(
                              group.lines.map((l) =>
                                handleFieldSave(l.id, "vendor_name", v)
                              )
                            )
                          }
                        />
                      </td>
                      <td className="px-4 py-2.5 text-right min-w-[80px]">
                        <InlineCell
                          value={group.total_buy_qty}
                          type="number"
                          onSave={(v) =>
                            // For units, distribute across all size lines by patching the first one
                            handleFieldSave(firstLine.id, "total_buy_qty", v)
                          }
                          className="text-right"
                        />
                      </td>
                      <td className="px-4 py-2.5 text-right min-w-[90px]">
                        <InlineCell
                          value={
                            group.planned_cost_per_unit !== null
                              ? group.planned_cost_per_unit
                              : null
                          }
                          type="number"
                          onSave={(v) =>
                            Promise.all(
                              group.lines.map((l) =>
                                handleFieldSave(l.id, "planned_cost_per_unit", v)
                              )
                            )
                          }
                          className="text-right"
                        />
                      </td>
                      <td className="px-4 py-2.5 text-right text-slate-700">
                        {totalCost !== null
                          ? `£${totalCost.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
                          : "—"}
                      </td>
                      <td className="px-4 py-2.5 min-w-[130px]">
                        <InlineCell
                          value={group.expected_delivery_week}
                          type="date"
                          onSave={(v) =>
                            Promise.all(
                              group.lines.map((l) =>
                                handleFieldSave(l.id, "expected_delivery_week", v)
                              )
                            )
                          }
                        />
                      </td>
                      <td className="px-4 py-2.5 text-right min-w-[70px]">
                        <InlineCell
                          value={group.moq}
                          type="number"
                          onSave={(v) =>
                            Promise.all(
                              group.lines.map((l) =>
                                handleFieldSave(l.id, "moq", v)
                              )
                            )
                          }
                          className="text-right"
                        />
                      </td>
                      <td className="px-2 py-2.5 text-right">
                        <button
                          onClick={() => {
                            if (
                              window.confirm(
                                `Remove ${group.style_code} from this plan? This deletes all ${group.lines.length} size line(s).`
                              )
                            ) {
                              void handleDeleteStyleGroup(
                                group.style_code,
                                group.lines.map((l) => l.id)
                              );
                            }
                          }}
                          disabled={deletingStyle === group.style_code}
                          aria-label={`Remove ${group.style_code}`}
                          className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 disabled:opacity-50"
                          title="Remove style from plan"
                        >
                          <svg
                            className="h-4 w-4"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M6 18L18 6M6 6l12 12"
                            />
                          </svg>
                        </button>
                      </td>
                    </tr>
                  );
                })}
          </tbody>
        </table>

        {!isLoading && styleGroups.length === 0 && (
          <div className="px-5 py-10 text-center text-sm text-slate-500">
            No lines match the current filters.
          </div>
        )}
      </div>

      {/* Legend */}
      {!isLoading && styleGroups.length > 0 && (
        <div className="flex items-center gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-amber-100 border border-amber-300" />
            Below MOQ
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-3 rounded-sm bg-red-100 border border-red-300" />
            No vendor set
          </span>
        </div>
      )}

      {/* Toast */}
      {toast && <Toast message={toast.message} type={toast.type} />}

      {/* Add Line modal */}
      {showAddLine && (
        <AddLineModal
          fileId={fileId}
          onClose={() => setShowAddLine(false)}
          onSaved={async () => {
            await mutate(`/api/v1/buy-plans/${fileId}/lines`);
            await mutateRecon();
            showToast("Line added", "success");
          }}
        />
      )}

      {/* Delete-plan confirmation */}
      {confirmingDeletePlan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
          <div className="w-full max-w-md rounded-xl border border-slate-200 bg-white p-6 shadow-xl">
            <h2 className="text-base font-semibold text-slate-900">
              Delete this buy plan?
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              This permanently removes <span className="font-medium">{plan?.name}</span>{" "}
              and all of its lines. GRNs and allocations linked to those lines will lose
              their buy-plan reference but remain in place.
            </p>
            <div className="mt-5 flex items-center justify-end gap-2">
              <button
                onClick={() => setConfirmingDeletePlan(false)}
                className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                onClick={() => void handleDeletePlan()}
                className="rounded-md bg-red-600 px-4 py-1.5 text-xs font-semibold text-white hover:bg-red-700"
              >
                Delete plan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
