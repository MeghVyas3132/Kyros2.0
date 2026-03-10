"use client";

import { useState } from "react";
import useSWR from "swr";

import { ErrorReport } from "@/components/ingestion/ErrorReport";
import { SmartUploadCard } from "@/components/ingestion/SmartUploadCard";
import { UploadDropzone } from "@/components/ingestion/UploadDropzone";
import { PageHeader } from "@/components/shared/PageHeader";
import { apiRequest } from "@/lib/api";

const TABS = [
  "SALES",
  "INVENTORY",
  "GRN",
  "STORE_MASTER",
  "SKU_MASTER",
  "STORE_GRADES",
  "SIZE_GUIDE",
  "BUY_FILE",
  "RESERVATION_TYPES",
] as const;

type UploadType = (typeof TABS)[number];

export default function IngestionPage() {
  const [activeTab, setActiveTab] = useState<UploadType>("SALES");
  const { data: uploads, mutate } = useSWR<Array<Record<string, unknown>>>(
    "/api/v1/ingestion/uploads",
    (path: string) => apiRequest<Array<Record<string, unknown>>>(path)
  );

  const filtered = (uploads ?? []).filter((upload) => upload.upload_type === activeTab);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Upload Hub"
        subtitle="Smart workbook upload for planners, plus manual upload by type"
      />

      <SmartUploadCard onUploaded={() => void mutate()} />

      <div className="flex gap-2">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`rounded-full border px-3 py-1 text-xs font-semibold ${
              activeTab === tab
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <UploadDropzone uploadType={activeTab} onUploaded={() => void mutate()} />

      <div className="overflow-auto rounded-xl border border-slate-300 bg-white/95 shadow-sm">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-slate-100 text-left text-xs uppercase tracking-wide text-slate-600">
            <tr>
              <th className="px-3 py-2">File</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Success</th>
              <th className="px-3 py-2">Failed</th>
              <th className="px-3 py-2">Errors</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((upload) => (
              <tr key={String(upload.id)} className="border-t border-slate-200 hover:bg-slate-50/70">
                <td className="px-3 py-2">{String(upload.filename)}</td>
                <td className="px-3 py-2">{String(upload.status)}</td>
                <td className="px-3 py-2">{String(upload.successful_rows)}</td>
                <td className="px-3 py-2">{String(upload.failed_rows)}</td>
                <td className="px-3 py-2">
                  {upload.status === "FAILED" || upload.status === "PARTIAL" ? (
                    <ErrorReport uploadId={String(upload.id)} />
                  ) : (
                    "-"
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
