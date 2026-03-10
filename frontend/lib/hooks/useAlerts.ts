"use client";

import useSWR from "swr";

import { apiRequest } from "@/lib/api";
import { Alert, AlertCount } from "@/types";

export function useAlertCount() {
  return useSWR<AlertCount>("/api/v1/alerts/count", (path: string) => apiRequest<AlertCount>(path));
}

export function useAlerts() {
  return useSWR<Alert[]>("/api/v1/alerts", (path: string) => apiRequest<Alert[]>(path));
}
