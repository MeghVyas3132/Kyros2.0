"use client";

import useSWR from "swr";

import { apiRequest } from "@/lib/api";

export function usePerformanceStyles(query: string) {
  const key =
    query.includes("season_id=") && !query.endsWith("season_id=")
      ? `/api/v1/performance/styles${query}`
      : null;
  return useSWR<Array<Record<string, unknown>>>(
    key,
    (path: string) => apiRequest<Array<Record<string, unknown>>>(path)
  );
}

export function usePerformanceStores(query: string) {
  const key =
    query.includes("season_id=") && !query.endsWith("season_id=")
      ? `/api/v1/performance/stores${query}`
      : null;
  return useSWR<Array<Record<string, unknown>>>(
    key,
    (path: string) => apiRequest<Array<Record<string, unknown>>>(path)
  );
}
