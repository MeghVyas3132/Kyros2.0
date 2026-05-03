"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { SetupTabs } from "@/components/shared/SetupTabs";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { apiRequest } from "@/lib/api";

type SeasonItem = {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
  categories?: string[];
};

const STATUS_OPTIONS = [
  "DRAFT",
  "PLANNING",
  "BUYING",
  "RECEIVING",
  "ALLOCATING",
  "IN_SEASON",
  "CLOSED",
];

const ACTIVE_LIKE = new Set(["PLANNING", "BUYING", "RECEIVING", "ALLOCATING", "IN_SEASON"]);

export default function SetupSeasonsPage() {
  const searchParams = useSearchParams();
  const isFirstRun = searchParams?.get("first") === "1";

  const { data, mutate } = useSWR<SeasonItem[]>("/api/v1/seasons", (path: string) =>
    apiRequest<SeasonItem[]>(path)
  );

  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [status, setStatus] = useState("PLANNING");
  const [categories, setCategories] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    setMessage(null);
    try {
      const payload = {
        name: name.trim(),
        start_date: startDate,
        end_date: endDate,
        status,
        categories: categories
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
      };
      await apiRequest("/api/v1/seasons", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await mutate();
      setName("");
      setStartDate("");
      setEndDate("");
      setStatus("PLANNING");
      setCategories("");
      setMessage("Season created.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to create season.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader title="Setup · Seasons" />

      {isFirstRun && (data ?? []).length === 0 ? (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900">
          <p className="font-semibold">Welcome to Kyros — let&rsquo;s set up your first season.</p>
          <p className="mt-1 text-blue-800">
            Every plan, buy file, and allocation in Kyros is scoped to a season.
            Define one below (e.g. <code className="rounded bg-blue-100 px-1">SS26</code> with
            its start and end dates) and you&rsquo;ll be able to upload data and run
            allocations from the next step.
          </p>
        </div>
      ) : null}
      <SetupTabs />

      <form
        className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 text-sm md:grid-cols-5"
        onSubmit={onSubmit}
      >
        <div>
          <label className="text-xs font-semibold text-slate-500">Season name</label>
          <Input value={name} onChange={(event) => setName(event.target.value)} placeholder="SS26" />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">Start date</label>
          <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">End date</label>
          <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">Status</label>
          <select
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs font-semibold text-slate-500">Categories (comma separated)</label>
          <Input
            value={categories}
            onChange={(event) => setCategories(event.target.value)}
            placeholder="Kurta, Dress"
          />
        </div>
        <div className="md:col-span-5 flex items-center gap-3">
          <Button type="submit" disabled={saving || !name || !startDate || !endDate}>
            Create season
          </Button>
          {message ? <span className="text-xs text-slate-500">{message}</span> : null}
        </div>
      </form>

      <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
        {(data ?? []).map((season) => (
          <div
            key={season.id}
            className="mb-2 flex items-center justify-between gap-4 rounded border border-slate-100 px-3 py-2"
          >
            <div>
              <div className="font-medium text-slate-900">{season.name}</div>
              <div className="text-xs text-slate-500">
                {season.start_date} to {season.end_date} ·{" "}
                <span
                  className={
                    ACTIVE_LIKE.has(season.status)
                      ? "font-semibold text-emerald-700"
                      : "text-slate-500"
                  }
                >
                  {season.status}
                </span>
              </div>
            </div>
            <Link
              href={`/setup/seasons/${season.id}/otb`}
              className="rounded-md border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
            >
              Open OTB →
            </Link>
          </div>
        ))}
        {(data ?? []).length === 0 ? (
          <div className="text-xs text-slate-500">No seasons yet. Create one above.</div>
        ) : null}
      </div>
    </div>
  );
}
