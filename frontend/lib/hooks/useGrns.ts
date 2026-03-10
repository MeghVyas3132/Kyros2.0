"use client";

import useSWR from "swr";

import { apiRequest } from "@/lib/api";
import { GRN } from "@/types";

export function useGRNs() {
  return useSWR<GRN[]>("/api/v1/grns", (path: string) => apiRequest<GRN[]>(path));
}

export function useGRN(id: string | undefined) {
  return useSWR<GRN & { lines: Array<{ id: string; sku_id: string; units_received: number }> }>(
    id ? `/api/v1/grns/${id}` : null,
    (path: string) =>
      apiRequest<GRN & { lines: Array<{ id: string; sku_id: string; units_received: number }> }>(path)
  );
}
