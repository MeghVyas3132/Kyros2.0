"use client";

import { FormEvent, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { SetupTabs } from "@/components/shared/SetupTabs";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiRequest } from "@/lib/api";

type ClusterItem = {
  id: string;
  name: string;
  description?: string | null;
};

export default function SetupClustersPage() {
  const { data, mutate } = useSWR<ClusterItem[]>("/api/v1/clusters", (path: string) =>
    apiRequest<ClusterItem[]>(path)
  );

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      await apiRequest("/api/v1/clusters", {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), description: description.trim() || null }),
      });
      await mutate();
      setName("");
      setDescription("");
      setMessage("Cluster created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to create cluster.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Setup · Clusters" />
      <SetupTabs />

      <form
        className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 text-sm md:grid-cols-3"
        onSubmit={onSubmit}
      >
        <div>
          <label className="text-xs font-semibold text-slate-500">Cluster name</label>
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="South Metro" />
        </div>
        <div className="md:col-span-2">
          <label className="text-xs font-semibold text-slate-500">Description</label>
          <Input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="High traffic premium malls"
          />
        </div>
        <div className="md:col-span-3 flex items-center gap-3">
          <Button type="submit" disabled={saving || !name}>
            Create cluster
          </Button>
          {message ? <span className="text-xs text-slate-500">{message}</span> : null}
        </div>
      </form>

      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-700">
        {(data ?? []).map((row) => (
          <div key={row.id} className="mb-2 rounded border border-slate-100 px-3 py-2">
            <div className="font-medium">{row.name}</div>
            <div className="text-xs text-slate-500">{row.description ?? ""}</div>
          </div>
        ))}
        {(data ?? []).length === 0 ? (
          <div className="text-xs text-slate-500">No clusters yet. Create one above.</div>
        ) : null}
      </div>
    </div>
  );
}
