"use client";

import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError, apiRequest } from "@/lib/api";

interface PendingSheet {
  sheet_name: string;
  detected_sheet_type: string;
  detected_upload_type: string | null;
  classifier_confidence: number;
  mapping_confidence: number;
  available_columns: string[];
  suggested_mapping: Record<string, string>;
  missing_fields: string[];
  low_confidence_required_fields: string[];
}

interface MappingRequiredDetails {
  file_name: string;
  min_confidence: number;
  sheets: PendingSheet[];
}

interface SmartUploadResponse {
  file_name: string;
  queued_uploads: Array<{
    upload_id: string;
    upload_type: string;
    filename: string;
    status: string;
  }>;
  sheets: Array<Record<string, unknown>>;
}

interface SheetDecision {
  skip: boolean;
  upload_type: string | null;
  mapping: Record<string, string>;
}

interface Props {
  onUploaded: () => void;
}

export function SmartUploadCard({ onUploaded }: Props) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState<MappingRequiredDetails | null>(null);
  const [decisions, setDecisions] = useState<Record<string, SheetDecision>>({});

  const queueSummary = useMemo(() => {
    if (!pending) return null;
    return pending.sheets
      .map((sheet) => `${sheet.sheet_name} -> ${sheet.detected_upload_type ?? "SKIP"}`)
      .join(" | ");
  }, [pending]);

  const buildDefaultDecisions = (details: MappingRequiredDetails): Record<string, SheetDecision> => {
    const next: Record<string, SheetDecision> = {};
    details.sheets.forEach((sheet) => {
      next[sheet.sheet_name] = {
        skip: false,
        upload_type: sheet.detected_upload_type,
        mapping: { ...sheet.suggested_mapping },
      };
      const unresolved = [...sheet.missing_fields, ...sheet.low_confidence_required_fields];
      unresolved.forEach((field) => {
        if (!(field in next[sheet.sheet_name].mapping)) {
          next[sheet.sheet_name].mapping[field] = "";
        }
      });
    });
    return next;
  };

  const doUpload = async (
    file: File,
    sheetDecisions: Record<string, SheetDecision> | null = null
  ) => {
    setLoading(true);
    setMessage(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      if (sheetDecisions) {
        formData.append("sheet_mapping_json", JSON.stringify(sheetDecisions));
      }

      const response = await apiRequest<SmartUploadResponse>("/api/v1/ingestion/smart-upload", {
        method: "POST",
        body: formData,
      });
      setPending(null);
      setDecisions({});
      setSelectedFile(null);
      const queuedCount = response.queued_uploads.length;
      setMessage(`Smart upload queued ${queuedCount} ingestion job${queuedCount === 1 ? "" : "s"}.`);
      onUploaded();
    } catch (error) {
      if (error instanceof ApiError && error.code === "MAPPING_REQUIRED" && error.details) {
        const details = error.details as MappingRequiredDetails;
        setPending(details);
        setDecisions(buildDefaultDecisions(details));
        setMessage("We need one-time field confirmation before ingesting this workbook.");
      } else {
        setMessage(error instanceof Error ? error.message : "Smart upload failed");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
        Smart Upload
      </h2>
      <p className="mt-1 text-sm text-slate-600">
        Upload one pilot workbook. Kyros auto-detects sheet type and mappings, and asks only for
        unclear fields.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <label className="cursor-pointer">
          <input
            className="hidden"
            type="file"
            accept=".xlsx,.xlsm,.csv"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              setSelectedFile(file);
              void doUpload(file);
            }}
          />
          <span className="rounded-md bg-slate-900 px-3 py-2 text-sm font-semibold text-white">
            {loading ? "Processing..." : "Upload Workbook"}
          </span>
        </label>
        {selectedFile ? <span className="text-xs text-slate-500">{selectedFile.name}</span> : null}
      </div>

      {message ? (
        <p className="mt-2 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-700">
          {message}
        </p>
      ) : null}

      {pending ? (
        <div className="mt-3 space-y-3 rounded-lg border border-amber-300 bg-amber-50 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">
            Confirmation Required
          </p>
          <p className="text-xs text-amber-900">
            Minimum confidence is {pending.min_confidence}. Review only highlighted fields below.
          </p>
          {queueSummary ? <p className="text-xs text-amber-900">{queueSummary}</p> : null}

          {pending.sheets.map((sheet) => {
            const decision = decisions[sheet.sheet_name];
            if (!decision) return null;
            const unresolved = [...sheet.missing_fields, ...sheet.low_confidence_required_fields];

            return (
              <div key={sheet.sheet_name} className="rounded-md border border-amber-200 bg-white p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-800">{sheet.sheet_name}</p>
                    <p className="text-xs text-slate-600">
                      Detected: {sheet.detected_sheet_type} ({sheet.detected_upload_type ?? "N/A"}) ·
                      classifier {sheet.classifier_confidence}
                    </p>
                  </div>
                  <label className="inline-flex items-center gap-2 text-xs text-slate-700">
                    <input
                      type="checkbox"
                      checked={decision.skip}
                      onChange={(event) =>
                        setDecisions((prev) => ({
                          ...prev,
                          [sheet.sheet_name]: { ...prev[sheet.sheet_name], skip: event.target.checked },
                        }))
                      }
                    />
                    Skip this sheet
                  </label>
                </div>

                {!decision.skip ? (
                  <div className="mt-3 grid gap-2 md:grid-cols-2">
                    {unresolved.map((field) => (
                      <label key={`${sheet.sheet_name}-${field}`} className="text-xs text-slate-700">
                        <span className="mb-1 block font-medium text-slate-800">{field}</span>
                        <select
                          value={decision.mapping[field] ?? ""}
                          onChange={(event) =>
                            setDecisions((prev) => ({
                              ...prev,
                              [sheet.sheet_name]: {
                                ...prev[sheet.sheet_name],
                                mapping: {
                                  ...prev[sheet.sheet_name].mapping,
                                  [field]: event.target.value,
                                },
                              },
                            }))
                          }
                          className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-xs"
                        >
                          <option value="">Select column</option>
                          {sheet.available_columns.map((column) => (
                            <option key={`${field}-${column}`} value={column}>
                              {column}
                            </option>
                          ))}
                        </select>
                      </label>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          })}

          <div className="flex items-center gap-2">
            <Button
              disabled={
                loading ||
                !selectedFile ||
                pending.sheets.some((sheet) => {
                  const decision = decisions[sheet.sheet_name];
                  if (!decision || decision.skip) return false;
                  const unresolved = [...sheet.missing_fields, ...sheet.low_confidence_required_fields];
                  return unresolved.some((field) => !decision.mapping[field]);
                })
              }
              onClick={() => {
                if (!selectedFile) return;
                void doUpload(selectedFile, decisions);
              }}
            >
              Confirm And Ingest
            </Button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
