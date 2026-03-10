"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApiError, apiRequest } from "@/lib/api";

interface Props {
  uploadType:
    | "SALES"
    | "INVENTORY"
    | "GRN"
    | "STORE_MASTER"
    | "SKU_MASTER"
    | "STORE_GRADES"
    | "SIZE_GUIDE"
    | "BUY_FILE"
    | "RESERVATION_TYPES";
  onUploaded: () => void;
}

interface MappingRequiredDetails {
  upload_type: string;
  missing_fields: string[];
  available_columns: string[];
  mappable_fields: string[];
}

export function UploadDropzone({ uploadType, onUploaded }: Props) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [mappingRequired, setMappingRequired] = useState<MappingRequiredDetails | null>(null);
  const [manualMapping, setManualMapping] = useState<Record<string, string>>({});

  const onFile = async (file: File, mapping: Record<string, string> | null = null) => {
    setLoading(true);
    setMessage(null);
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("upload_type", uploadType);
      if (mapping && Object.keys(mapping).length > 0) {
        formData.append("column_mapping_json", JSON.stringify(mapping));
      }
      await apiRequest<{ upload_id: string; status: string }>("/api/v1/ingestion/upload", {
        method: "POST",
        body: formData,
      });
      setMessage("Upload queued");
      setMappingRequired(null);
      setManualMapping({});
      setSelectedFile(null);
      onUploaded();
    } catch (error) {
      if (error instanceof ApiError && error.code === "MAPPING_REQUIRED" && error.details) {
        const details = error.details as MappingRequiredDetails;
        setMappingRequired(details);
        const nextMapping: Record<string, string> = {};
        details.missing_fields.forEach((field) => {
          nextMapping[field] = "";
        });
        setManualMapping(nextMapping);
        setSelectedFile(file);
        setMessage("Column mapping required before upload can continue.");
      } else {
        setMessage(error instanceof Error ? error.message : "Upload failed");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-dashed border-slate-300 bg-white p-4">
      <label className="cursor-pointer text-sm text-slate-700">
        <input
          className="hidden"
          type="file"
          accept=".csv"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void onFile(file);
          }}
        />
        <span className="rounded-md bg-slate-900 px-3 py-2 font-medium text-white">
          {loading ? "Uploading..." : `Upload ${uploadType} CSV`}
        </span>
      </label>
      {message ? <p className="mt-2 text-xs text-slate-600">{message}</p> : null}

      {mappingRequired ? (
        <div className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-amber-800">
            Column Mapping Required
          </p>
          <p className="mt-1 text-xs text-amber-900">
            We could not map {mappingRequired.missing_fields.join(", ")} automatically.
          </p>
          <div className="mt-2 grid gap-2">
            {mappingRequired.missing_fields.map((field) => (
              <label key={field} className="text-xs text-slate-700">
                <span className="mb-1 block font-medium text-slate-800">{field}</span>
                <select
                  value={manualMapping[field] ?? ""}
                  onChange={(event) =>
                    setManualMapping((prev) => ({ ...prev, [field]: event.target.value }))
                  }
                  className="w-full rounded-md border border-slate-300 bg-white px-2 py-1 text-xs"
                >
                  <option value="">Select a column</option>
                  {mappingRequired.available_columns.map((column) => (
                    <option key={`${field}-${column}`} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <div className="mt-2">
            <Button
              disabled={
                loading ||
                !selectedFile ||
                mappingRequired.missing_fields.some((field) => !manualMapping[field])
              }
              onClick={() => {
                if (!selectedFile) return;
                void onFile(selectedFile, manualMapping);
              }}
            >
              Save Mapping And Upload
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
