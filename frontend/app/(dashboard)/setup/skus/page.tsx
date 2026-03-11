"use client";

import { FormEvent, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { SetupTabs } from "@/components/shared/SetupTabs";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiRequest } from "@/lib/api";

type SKUItem = {
  id: string;
  sku_code: string;
  style_name: string;
  category: string;
  fabric?: string | null;
  mrp?: number | null;
};

export default function SetupSKUsPage() {
  const { data, mutate } = useSWR<SKUItem[]>("/api/v1/skus", (path: string) =>
    apiRequest<SKUItem[]>(path)
  );

  const [skuCode, setSkuCode] = useState("");
  const [styleCode, setStyleCode] = useState("");
  const [styleName, setStyleName] = useState("");
  const [category, setCategory] = useState("");
  const [fabric, setFabric] = useState("");
  const [mrp, setMrp] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await apiRequest("/api/v1/skus", {
        method: "POST",
        body: JSON.stringify({
          sku_code: skuCode.trim().toUpperCase(),
          style_code: styleCode.trim() || skuCode.trim().toUpperCase(),
          style_name: styleName.trim(),
          category: category.trim(),
          fabric: fabric.trim() || null,
          mrp: mrp ? Number(mrp) : null,
        }),
      });
      await mutate();
      setSkuCode("");
      setStyleCode("");
      setStyleName("");
      setCategory("");
      setFabric("");
      setMrp("");
      setMessage("SKU created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to create SKU.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Setup · SKUs" />
      <SetupTabs />

      <form
        className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 text-sm md:grid-cols-6"
        onSubmit={onSubmit}
      >
        <div>
          <label className="text-xs font-semibold text-slate-500">SKU code</label>
          <Input value={skuCode} onChange={(event) => setSkuCode(event.target.value)} placeholder="CWS6KS11160A" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">Style code</label>
          <Input value={styleCode} onChange={(event) => setStyleCode(event.target.value)} placeholder="CWS6KS11160" />
        </div>
        <div className="md:col-span-2">
          <label className="text-xs font-semibold text-slate-500">Style name</label>
          <Input value={styleName} onChange={(event) => setStyleName(event.target.value)} placeholder="Kaftan Suit" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">Category</label>
          <Input value={category} onChange={(event) => setCategory(event.target.value)} placeholder="Kurta" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">Fabric</label>
          <Input value={fabric} onChange={(event) => setFabric(event.target.value)} placeholder="Cotton" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">MRP</label>
          <Input value={mrp} onChange={(event) => setMrp(event.target.value)} placeholder="1299" />
        </div>
        <div className="md:col-span-6 flex items-center gap-3">
          <Button type="submit" disabled={saving || !skuCode || !styleName || !category}>
            Add SKU
          </Button>
          {message ? <span className="text-xs text-slate-500">{message}</span> : null}
        </div>
      </form>

      <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">SKU</th>
              <th className="px-3 py-2">Style</th>
              <th className="px-3 py-2">Category</th>
              <th className="px-3 py-2">Fabric</th>
              <th className="px-3 py-2">MRP</th>
            </tr>
          </thead>
          <tbody>
            {(data ?? []).slice(0, 100).map((row) => (
              <tr key={row.id} className="border-t border-slate-100">
                <td className="px-3 py-2">{row.sku_code}</td>
                <td className="px-3 py-2">{row.style_name}</td>
                <td className="px-3 py-2">{row.category}</td>
                <td className="px-3 py-2">{row.fabric ?? ""}</td>
                <td className="px-3 py-2">₹{row.mrp ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
