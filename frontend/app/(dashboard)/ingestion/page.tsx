"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";

import { SmartUploadCard } from "@/components/ingestion/SmartUploadCard";
import { UploadDropzone } from "@/components/ingestion/UploadDropzone";
import { apiRequest } from "@/lib/api";
import { useSeasons } from "@/lib/hooks/useSeasons";

const UPLOAD_CATEGORIES = [
  {
    key: "BUY_FILE",
    label: "Buy Plan / Workbook",
    description: "Your season buy plan with styles, quantities, and store assignments",
    icon: "📋",
    recommended: true,
  },
  {
    key: "SALES",
    label: "Sales History",
    description: "Weekly store-level sales data for demand forecasting",
    icon: "�",
  },
  {
    key: "STORE_GRADES",
    label: "Store Grades",
    description: "Store performance grades by product category",
    icon: "⭐",
  },
  {
    key: "SIZE_GUIDE",
    label: "Size Guide",
    description: "Size ratios and rules for each product category",
    icon: "📏",
  },
  {
    key: "GRN",
    label: "Stock Receipt (GRN)",
    description: "Goods received notes for warehouse intake",
    icon: "package",
  },
  {
    key: "STORE_MASTER",
    label: "Store Master",
    description: "Store information — codes, names, cities",
    icon: "🏪",
  },
  {
    key: "SKU_MASTER",
    label: "Product / SKU Master",
    description: "Product catalog with styles, sizes, and prices",
    icon: "👕",
  },
  {
    key: "RESERVATION_TYPES",
    label: "Reservation Types",
    description: "E-commerce and replenishment reserve rules",
    icon: "🔒",
  },
] as const;

type UploadType =
  | "SALES"
  | "INVENTORY"
  | "GRN"
  | "STORE_MASTER"
  | "SKU_MASTER"
  | "STORE_GRADES"
  | "SIZE_GUIDE"
  | "BUY_FILE"
  | "RESERVATION_TYPES";

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  COMPLETED: { label: "Processed", color: "text-emerald-700 bg-emerald-50" },
  PARTIAL: { label: "Partial", color: "text-amber-700 bg-amber-50" },
  FAILED: { label: "Failed", color: "text-red-700 bg-red-50" },
  PROCESSING: { label: "Processing", color: "text-blue-700 bg-blue-50" },
  PENDING: { label: "Queued", color: "text-slate-700 bg-slate-50" },
};

type DataQualityCheck = {
  key: string;
  status: "GREEN" | "AMBER" | "RED";
  title: string;
  detail: string;
};
type DataQualityResponse = {
  readiness: "GREEN" | "AMBER" | "RED";
  readiness_message: string;
  checks: DataQualityCheck[];
  facts: Record<string, unknown>;
};

export default function IngestionPage() {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [activeType, setActiveType] = useState<UploadType | null>(null);
  const { data: uploads, mutate } = useSWR<Array<Record<string, unknown>>>(
    "/api/v1/ingestion/uploads",
    (path: string) => apiRequest<Array<Record<string, unknown>>>(path)
  );
  const { data: seasons, isLoading: seasonsLoading } = useSeasons();
  const noSeasonYet = !seasonsLoading && Array.isArray(seasons) && seasons.length === 0;
  const { data: dataQuality } = useSWR<DataQualityResponse>(
    !noSeasonYet ? "/api/v1/ingestion/data-quality" : null,
    (path: string) => apiRequest<DataQualityResponse>(path),
    { refreshInterval: 8000 }
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Upload Data</h1>
        <p className="mt-1 text-sm text-slate-500">
          Upload your planning files. Kyros will automatically detect the content and process it.
        </p>
      </div>

      {/* First-season gate: buy-file ingest needs a season to attach the
          buy plan to. Block the upload UI until the planner has set one up. */}
      {noSeasonYet ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          <p className="font-semibold">Set up your season first</p>
          <p className="mt-1 text-amber-800">
            Buy plans, OTB, and allocations are scoped to a season. Create one
            before uploading data — otherwise the buy file upload will fail.
          </p>
          <Link
            href="/setup/seasons?first=1"
            className="mt-3 inline-flex items-center gap-1 rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700"
          >
            Go to Setup → Seasons
          </Link>
        </div>
      ) : null}

      {/* Pre-flight readiness — surfaces input quality BEFORE allocation runs.
          The point: catch garbage data while the planner is still on this
          screen, not after the engine spent 3 minutes producing a bad plan. */}
      {dataQuality && (
        <div
          className={`rounded-lg border p-4 text-sm ${
            dataQuality.readiness === "RED"
              ? "border-red-300 bg-red-50 text-red-900"
              : dataQuality.readiness === "AMBER"
              ? "border-amber-300 bg-amber-50 text-amber-900"
              : "border-emerald-300 bg-emerald-50 text-emerald-900"
          }`}
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold text-white ${
                    dataQuality.readiness === "RED"
                      ? "bg-red-500"
                      : dataQuality.readiness === "AMBER"
                      ? "bg-amber-500"
                      : "bg-emerald-500"
                  }`}
                >
                  {dataQuality.readiness === "RED" ? "!" : dataQuality.readiness === "AMBER" ? "•" : "✓"}
                </span>
                <p className="font-semibold">
                  Data readiness: {dataQuality.readiness}
                </p>
              </div>
              <p className="mt-1 text-sm">{dataQuality.readiness_message}</p>
            </div>
          </div>

          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {dataQuality.checks.map((check) => (
              <div
                key={check.key}
                className="rounded-md border border-white/60 bg-white/70 p-3"
              >
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-block h-2 w-2 rounded-full ${
                      check.status === "RED"
                        ? "bg-red-500"
                        : check.status === "AMBER"
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                    }`}
                  />
                  <p className="text-sm font-semibold text-slate-900">
                    {check.title}
                  </p>
                </div>
                <p className="mt-1 text-xs text-slate-700">{check.detail}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Smart Upload — Primary Action */}
      <SmartUploadCard onUploaded={() => void mutate()} />

      {/* Advanced: Upload by Type */}
      <div className="rounded-xl border border-slate-200 bg-white">
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex w-full items-center justify-between px-5 py-4 text-left"
        >
          <div>
            <p className="text-sm font-medium text-slate-700">
              Upload Individual File by Type
            </p>
            <p className="text-xs text-slate-400">
              Use this if you have separate CSV files for each data type
            </p>
          </div>
          <span className="text-sm text-slate-400">{showAdvanced ? "▲" : "▼"}</span>
        </button>

        {showAdvanced ? (
          <div className="border-t border-slate-100 px-5 pb-5">
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {UPLOAD_CATEGORIES.map((cat) => (
                <button
                  key={cat.key}
                  onClick={() => setActiveType(activeType === cat.key ? null : (cat.key as UploadType))}
                  className={`rounded-lg border p-3 text-left transition ${
                    activeType === cat.key
                      ? "border-slate-900 bg-slate-50 ring-1 ring-slate-900"
                      : "border-slate-200 hover:border-slate-300 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{cat.icon}</span>
                    <span className="text-sm font-medium text-slate-800">{cat.label}</span>
                  </div>
                  <p className="mt-1 text-xs text-slate-500">{cat.description}</p>
                  {"recommended" in cat && cat.recommended ? (
                    <span className="mt-2 inline-block rounded bg-blue-100 px-1.5 py-0.5 text-[10px] font-semibold text-blue-700">
                      RECOMMENDED
                    </span>
                  ) : null}
                </button>
              ))}
            </div>

            {activeType ? (
              <div className="mt-4">
                <UploadDropzone uploadType={activeType} onUploaded={() => void mutate()} />
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {/* Upload History */}
      {(uploads ?? []).length > 0 ? (
        <div className="rounded-xl border border-slate-200 bg-white">
          <div className="px-5 py-4">
            <h2 className="text-sm font-semibold text-slate-700">Upload History</h2>
          </div>
          <div className="overflow-auto">
            <table className="min-w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500">
                <tr>
                  <th className="px-5 py-2 text-left font-medium">File</th>
                  <th className="px-5 py-2 text-left font-medium">Type</th>
                  <th className="px-5 py-2 text-left font-medium">Status</th>
                  <th className="px-5 py-2 text-right font-medium">Rows</th>
                </tr>
              </thead>
              <tbody>
                {(uploads ?? []).slice(0, 20).map((upload) => {
                  const statusKey = String(upload.status);
                  const statusInfo = STATUS_MAP[statusKey] ?? { label: statusKey, color: "text-slate-600 bg-slate-50" };
                  const typeInfo = UPLOAD_CATEGORIES.find((c) => c.key === String(upload.upload_type));
                  return (
                    <tr key={String(upload.id)} className="border-t border-slate-100">
                      <td className="px-5 py-2.5 font-medium text-slate-800">{String(upload.filename)}</td>
                      <td className="px-5 py-2.5 text-slate-500">
                        {typeInfo ? `${typeInfo.icon} ${typeInfo.label}` : String(upload.upload_type)}
                      </td>
                      <td className="px-5 py-2.5">
                        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${statusInfo.color}`}>
                          {statusInfo.label}
                        </span>
                      </td>
                      <td className="px-5 py-2.5 text-right text-slate-500">
                        {Number(upload.successful_rows) > 0
                          ? `${upload.successful_rows} processed`
                          : "-"}
                        {Number(upload.failed_rows) > 0
                          ? ` · ${upload.failed_rows} failed`
                          : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </div>
  );
}
