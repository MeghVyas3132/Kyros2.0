"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/Button";
import { apiRequest } from "@/lib/api";
import type { SignupRequestRow, SignupStatus, User } from "@/types";

type Tab = SignupStatus | "ALL";
const TABS: Tab[] = ["PENDING", "APPROVED", "REJECTED", "ALL"];

export default function SuperAdminPage() {
  const [user, setUser] = useState<User | null>(null);
  const [tab, setTab] = useState<Tab>("PENDING");
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const raw = window.localStorage.getItem("kyros_user");
      setUser(raw ? (JSON.parse(raw) as User) : null);
    } catch {
      setUser(null);
    }
  }, []);

  const queryUrl = useMemo(() => {
    const base = "/api/v1/admin/signup-requests";
    return tab === "ALL" ? base : `${base}?status=${tab}`;
  }, [tab]);

  const { data, error, isLoading, mutate } = useSWR<SignupRequestRow[]>(
    user?.role === "SUPER_ADMIN" ? queryUrl : null,
    (path: string) => apiRequest<SignupRequestRow[]>(path)
  );

  if (user && user.role !== "SUPER_ADMIN") {
    return (
      <div className="space-y-4">
        <PageHeader title="Super Admin" />
        <div className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-900">
          This page is reserved for the platform super-admin. Your role is{" "}
          <code className="rounded bg-amber-100 px-1">{user.role}</code>.
        </div>
      </div>
    );
  }

  const approve = async (id: string) => {
    setBusyId(id);
    setActionError(null);
    try {
      await apiRequest(`/api/v1/admin/signup-requests/${id}/approve`, { method: "POST" });
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Approve failed");
    } finally {
      setBusyId(null);
    }
  };

  const reject = async (id: string) => {
    setBusyId(id);
    setActionError(null);
    try {
      await apiRequest(`/api/v1/admin/signup-requests/${id}`, { method: "DELETE" });
      await mutate();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Reject failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-4">
      <PageHeader
        title="Super Admin · Pilot Onboarding"
        subtitle="Review brand signup applications. Approve to provision the workspace, reject to dismiss the request."
      />

      <div className="flex items-center gap-2">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
              tab === t
                ? "bg-slate-900 text-white"
                : "border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
            }`}
          >
            {t}
          </button>
        ))}
        <span className="ml-auto text-xs text-slate-500">
          {data ? `${data.length} request${data.length === 1 ? "" : "s"}` : ""}
        </span>
      </div>

      {actionError ? (
        <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {actionError}
        </div>
      ) : null}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
        {isLoading ? (
          <div className="p-6 text-sm text-slate-500">Loading…</div>
        ) : error ? (
          <div className="p-6 text-sm text-red-600">
            Failed to load: {error instanceof Error ? error.message : String(error)}
          </div>
        ) : !data || data.length === 0 ? (
          <div className="p-6 text-sm text-slate-500">No requests in this state.</div>
        ) : (
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Brand
                </th>
                <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Applicant
                </th>
                <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Contact
                </th>
                <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Submitted
                </th>
                <th className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Status
                </th>
                <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((row) => (
                <tr key={row.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">{row.brand_name}</div>
                    <div className="text-xs text-slate-500">slug: {row.brand_slug}</div>
                    {row.company_size ? (
                      <div className="text-xs text-slate-500">{row.company_size}</div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    <div className="font-medium text-slate-900">{row.full_name}</div>
                    <div className="text-xs text-slate-500">{row.email}</div>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    {row.contact_phone ?? "—"}
                    {row.notes ? (
                      <div className="mt-1 max-w-xs italic text-slate-500">
                        “{row.notes}”
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    {new Date(row.created_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-3">
                    <StatusPill status={row.status} />
                    {row.reviewed_at ? (
                      <div className="mt-1 text-xs text-slate-500">
                        reviewed {new Date(row.reviewed_at).toLocaleString()}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-right">
                    {row.status === "PENDING" ? (
                      <div className="flex items-center justify-end gap-2">
                        <Button
                          variant="primary"
                          disabled={busyId === row.id}
                          onClick={() => approve(row.id)}
                        >
                          {busyId === row.id ? "…" : "Approve"}
                        </Button>
                        <Button
                          variant="danger"
                          disabled={busyId === row.id}
                          onClick={() => reject(row.id)}
                        >
                          Reject
                        </Button>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: SignupStatus }) {
  const styles: Record<SignupStatus, string> = {
    PENDING: "bg-amber-100 text-amber-800 border border-amber-200",
    APPROVED: "bg-emerald-100 text-emerald-800 border border-emerald-200",
    REJECTED: "bg-slate-100 text-slate-700 border border-slate-200",
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${styles[status]}`}>
      {status}
    </span>
  );
}
