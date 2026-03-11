"use client";

import { FormEvent, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { SetupTabs } from "@/components/shared/SetupTabs";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiRequest } from "@/lib/api";

type StoreItem = {
  id: string;
  store_code: string;
  store_name: string;
  city?: string | null;
  state?: string | null;
  store_type?: string | null;
  climate_zone?: string | null;
};

export default function SetupStoresPage() {
  const { data, mutate } = useSWR<StoreItem[]>("/api/v1/stores", (path: string) =>
    apiRequest<StoreItem[]>(path)
  );

  const [storeCode, setStoreCode] = useState("");
  const [storeName, setStoreName] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [storeType, setStoreType] = useState("");
  const [climateZone, setClimateZone] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await apiRequest("/api/v1/stores", {
        method: "POST",
        body: JSON.stringify({
          store_code: storeCode.trim().toUpperCase(),
          store_name: storeName.trim(),
          city: city.trim() || null,
          state: state.trim() || null,
          store_type: storeType.trim() || null,
          climate_zone: climateZone.trim() || null,
        }),
      });
      await mutate();
      setStoreCode("");
      setStoreName("");
      setCity("");
      setState("");
      setStoreType("");
      setClimateZone("");
      setMessage("Store created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to create store.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Setup · Stores" subtitle="Basic CRUD table" />
      <SetupTabs />

      <form
        className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 text-sm md:grid-cols-6"
        onSubmit={onSubmit}
      >
        <div>
          <label className="text-xs font-semibold text-slate-500">Store code</label>
          <Input value={storeCode} onChange={(event) => setStoreCode(event.target.value)} placeholder="BLR-01" />
        </div>
        <div className="md:col-span-2">
          <label className="text-xs font-semibold text-slate-500">Store name</label>
          <Input value={storeName} onChange={(event) => setStoreName(event.target.value)} placeholder="MG ROAD" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">City</label>
          <Input value={city} onChange={(event) => setCity(event.target.value)} placeholder="Bengaluru" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">State</label>
          <Input value={state} onChange={(event) => setState(event.target.value)} placeholder="Karnataka" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">Store type</label>
          <Input value={storeType} onChange={(event) => setStoreType(event.target.value)} placeholder="EBO" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">Climate zone</label>
          <Input value={climateZone} onChange={(event) => setClimateZone(event.target.value)} placeholder="Warm" />
        </div>
        <div className="md:col-span-6 flex items-center gap-3">
          <Button type="submit" disabled={saving || !storeCode || !storeName}>
            Add store
          </Button>
          {message ? <span className="text-xs text-slate-500">{message}</span> : null}
        </div>
      </form>

      <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Code</th>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">City</th>
              <th className="px-3 py-2">State</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Climate</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).map((row) => (
              <tr key={row.id} className="border-t border-slate-100">
                <td className="px-3 py-2">{row.store_code}</td>
                <td className="px-3 py-2">{row.store_name}</td>
                <td className="px-3 py-2">{row.city ?? ""}</td>
                <td className="px-3 py-2">{row.state ?? ""}</td>
                <td className="px-3 py-2">{row.store_type ?? ""}</td>
                <td className="px-3 py-2">{row.climate_zone ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
