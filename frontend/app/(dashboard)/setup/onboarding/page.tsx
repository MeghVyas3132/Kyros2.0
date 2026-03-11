"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { SetupTabs } from "@/components/shared/SetupTabs";
import { Button } from "@/components/ui/Button";
import { apiRequest } from "@/lib/api";

interface ReservationTypeRow {
  id: string;
  code: string;
  label: string;
  deducts_from_first_allocation: boolean;
  display_order: number;
  is_active: boolean;
}

interface OnboardingSettingsResponse {
  config: Record<string, unknown>;
  reservation_types: ReservationTypeRow[];
  supported_upload_mappings: string[];
}

export default function SetupOnboardingPage() {
  const { data, mutate } = useSWR<OnboardingSettingsResponse>(
    "/api/v1/onboarding/settings",
    (path: string) => apiRequest<OnboardingSettingsResponse>(path)
  );

  const config = data?.config ?? {};
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [selectedUploadType, setSelectedUploadType] = useState<string>("STORE_GRADES");
  const [fieldName, setFieldName] = useState("");
  const [columnName, setColumnName] = useState("");

  const gradeMappingText = useMemo(
    () => JSON.stringify((config.grade_mapping as Record<string, string> | undefined) ?? {}, null, 2),
    [config.grade_mapping]
  );
  const storeGroupMappingText = useMemo(
    () =>
      JSON.stringify(
        (config.store_group_mapping as Record<string, string | null> | undefined) ?? {},
        null,
        2
      ),
    [config.store_group_mapping]
  );
  const riskMappingText = useMemo(
    () =>
      JSON.stringify(
        ((config.allocation as Record<string, unknown> | undefined)?.risk_group_mapping as
          | Record<string, string>
          | undefined) ?? {},
        null,
        2
      ),
    [config.allocation]
  );

  const [gradeJson, setGradeJson] = useState(gradeMappingText);
  const [storeGroupJson, setStoreGroupJson] = useState(storeGroupMappingText);
  const [riskJson, setRiskJson] = useState(riskMappingText);

  useEffect(() => {
    setGradeJson(gradeMappingText);
  }, [gradeMappingText]);
  useEffect(() => {
    setStoreGroupJson(storeGroupMappingText);
  }, [storeGroupMappingText]);
  useEffect(() => {
    setRiskJson(riskMappingText);
  }, [riskMappingText]);

  const currentColumnMappings =
    ((config.column_mappings as Record<string, Record<string, string> | undefined> | undefined) ??
      {})[selectedUploadType] ?? {};
  const [reservationCode, setReservationCode] = useState("");
  const [reservationLabel, setReservationLabel] = useState("");

  const saveConfig = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const parsedGrade = JSON.parse(gradeJson);
      const parsedStoreGroup = JSON.parse(storeGroupJson);
      const parsedRisk = JSON.parse(riskJson);

      await apiRequest<{ config: Record<string, unknown> }>("/api/v1/onboarding/settings", {
        method: "PUT",
        body: JSON.stringify({
          config_patch: {
            grade_mapping: parsedGrade,
            store_group_mapping: parsedStoreGroup,
            allocation: {
              risk_group_mapping: parsedRisk,
            },
          },
        }),
      });
      setMessage("Onboarding settings saved");
      await mutate();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  };

  const saveColumnMapping = async () => {
    if (!fieldName || !columnName) return;
    setSaving(true);
    setMessage(null);
    try {
      const next = { ...(currentColumnMappings ?? {}), [fieldName]: columnName };
      await apiRequest(`/api/v1/onboarding/column-mappings/${selectedUploadType}`, {
        method: "POST",
        body: JSON.stringify({ mapping: next }),
      });
      setFieldName("");
      setColumnName("");
      setMessage("Column mapping saved");
      await mutate();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save column mapping");
    } finally {
      setSaving(false);
    }
  };

  const addReservationType = async () => {
    if (!reservationCode || !reservationLabel) return;
    setSaving(true);
    setMessage(null);
    try {
      await apiRequest("/api/v1/onboarding/reservation-types", {
        method: "POST",
        body: JSON.stringify({
          code: reservationCode,
          label: reservationLabel,
          deducts_from_first_allocation: true,
          is_active: true,
          display_order: (data?.reservation_types.length ?? 0) + 1,
        }),
      });
      setReservationCode("");
      setReservationLabel("");
      setMessage("Reservation type added");
      await mutate();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to add reservation type");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <PageHeader
        title="Setup · Onboarding Configuration"
        subtitle="Persist mappings and allocation configuration per brand"
      />
      <SetupTabs />

      {message ? (
        <div className="rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          {message}
        </div>
      ) : null}

      <div className="grid grid-cols-3 gap-4">
        <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">Grade Mapping</h2>
          <textarea
            className="mt-2 h-40 w-full rounded-md border border-slate-300 px-2 py-1 font-mono text-xs"
            value={gradeJson}
            onChange={(event) => setGradeJson(event.target.value)}
          />
        </section>

        <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
            Store Group Mapping
          </h2>
          <textarea
            className="mt-2 h-40 w-full rounded-md border border-slate-300 px-2 py-1 font-mono text-xs"
            value={storeGroupJson}
            onChange={(event) => setStoreGroupJson(event.target.value)}
          />
        </section>

        <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
            Risk Group Mapping
          </h2>
          <textarea
            className="mt-2 h-40 w-full rounded-md border border-slate-300 px-2 py-1 font-mono text-xs"
            value={riskJson}
            onChange={(event) => setRiskJson(event.target.value)}
          />
        </section>
      </div>

      <Button disabled={saving} onClick={saveConfig}>
        Save Onboarding Config
      </Button>

      <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">Column Mappings</h2>
        <div className="mt-2 flex flex-wrap items-end gap-2">
          <label className="text-xs text-slate-700">
            Upload Type
            <select
              className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
              value={selectedUploadType}
              onChange={(event) => setSelectedUploadType(event.target.value)}
            >
              {(data?.supported_upload_mappings ?? []).map((uploadType) => (
                <option key={uploadType} value={uploadType}>
                  {uploadType}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs text-slate-700">
            Semantic Field
            <input
              className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
              value={fieldName}
              onChange={(event) => setFieldName(event.target.value)}
              placeholder="e.g. grade"
            />
          </label>
          <label className="text-xs text-slate-700">
            Source Column
            <input
              className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
              value={columnName}
              onChange={(event) => setColumnName(event.target.value)}
              placeholder="e.g. Store Grade - Prod Price Band"
            />
          </label>
          <Button variant="secondary" disabled={saving || !fieldName || !columnName} onClick={saveColumnMapping}>
            Save Mapping
          </Button>
        </div>
        <pre className="mt-3 overflow-auto rounded-md border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
          {JSON.stringify(currentColumnMappings, null, 2)}
        </pre>
      </section>

      <section className="rounded-xl border border-slate-300 bg-white p-4 shadow-sm">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700">
          Reservation Types
        </h2>
        <div className="mt-2 flex items-end gap-2">
          <label className="text-xs text-slate-700">
            Code
            <input
              className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
              value={reservationCode}
              onChange={(event) => setReservationCode(event.target.value)}
              placeholder="ECOM"
            />
          </label>
          <label className="text-xs text-slate-700">
            Label
            <input
              className="mt-1 block rounded-md border border-slate-300 bg-white px-2 py-1 text-sm"
              value={reservationLabel}
              onChange={(event) => setReservationLabel(event.target.value)}
              placeholder="E-Commerce Reserve"
            />
          </label>
          <Button variant="secondary" disabled={saving || !reservationCode || !reservationLabel} onClick={addReservationType}>
            Add
          </Button>
        </div>
        <div className="mt-3 overflow-auto rounded-md border border-slate-200">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">Code</th>
                <th className="px-3 py-2">Label</th>
                <th className="px-3 py-2">Deducts</th>
                <th className="px-3 py-2">Active</th>
              </tr>
            </thead>
            <tbody>
              {(data?.reservation_types ?? []).map((row) => (
                <tr key={row.id} className="border-t border-slate-200">
                  <td className="px-3 py-2">{row.code}</td>
                  <td className="px-3 py-2">{row.label}</td>
                  <td className="px-3 py-2">{row.deducts_from_first_allocation ? "Yes" : "No"}</td>
                  <td className="px-3 py-2">{row.is_active ? "Yes" : "No"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
