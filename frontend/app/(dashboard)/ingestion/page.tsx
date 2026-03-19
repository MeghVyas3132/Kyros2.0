"use client";

import { useState } from "react";
import useSWR from "swr";

import { SmartUploadCard } from "@/components/ingestion/SmartUploadCard";
import { UploadDropzone } from "@/components/ingestion/UploadDropzone";
import { apiRequest } from "@/lib/api";

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

export default function IngestionPage() {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [activeType, setActiveType] = useState<UploadType | null>(null);
  const { data: uploads, mutate } = useSWR<Array<Record<string, unknown>>>(
    "/api/v1/ingestion/uploads",
    (path: string) => apiRequest<Array<Record<string, unknown>>>(path)
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
