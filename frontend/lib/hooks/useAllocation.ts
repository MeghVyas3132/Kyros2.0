"use client";

import useSWR from "swr";

import { apiRequest } from "@/lib/api";
import { AllocationLine, AllocationSession } from "@/types";

export interface AllocationSessionDetail {
  session: AllocationSession;
  lines: AllocationLine[];
}

export function useAllocationSession(sessionId: string | null) {
  return useSWR<AllocationSessionDetail>(
    sessionId ? `/api/v1/allocation/sessions/${sessionId}` : null,
    (path: string) => apiRequest<AllocationSessionDetail>(path)
  );
}
