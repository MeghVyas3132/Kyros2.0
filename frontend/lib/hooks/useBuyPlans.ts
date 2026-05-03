"use client";

import useSWR from "swr";

import { apiRequest } from "@/lib/api";
import {
  BuyPlanFileWithStats,
  BuyPlanLine,
  BuyPlanReconciliation,
} from "@/types/buy_plan";

export function useBuyPlans(seasonId?: string) {
  const url = seasonId
    ? `/api/v1/buy-plans?season_id=${seasonId}`
    : "/api/v1/buy-plans";
  return useSWR<BuyPlanFileWithStats[]>(url, (path: string) =>
    apiRequest<BuyPlanFileWithStats[]>(path)
  );
}

export function useBuyPlan(fileId: string | null) {
  return useSWR<BuyPlanFileWithStats>(
    fileId ? `/api/v1/buy-plans/${fileId}` : null,
    (path: string) => apiRequest<BuyPlanFileWithStats>(path)
  );
}

export function useBuyPlanLines(fileId: string | null) {
  return useSWR<BuyPlanLine[]>(
    fileId ? `/api/v1/buy-plans/${fileId}/lines` : null,
    (path: string) => apiRequest<BuyPlanLine[]>(path)
  );
}

export function useBuyPlanReconciliation(fileId: string | null) {
  return useSWR<BuyPlanReconciliation>(
    fileId ? `/api/v1/buy-plans/${fileId}/reconcile` : null,
    (path: string) => apiRequest<BuyPlanReconciliation>(path)
  );
}
