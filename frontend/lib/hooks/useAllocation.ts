"use client";

import useSWR from "swr";

import { apiRequest } from "@/lib/api";
import { AllocationLine, AllocationSession } from "@/types";

export interface AllocationSessionDetail {
  session: AllocationSession;
  lines: AllocationLine[];
  lines_total?: number;
  lines_returned?: number;
  lines_offset?: number;
  lines_has_more?: boolean;
}

interface UseAllocationSessionOptions {
  lineLimit?: number;
  lineOffset?: number;
}

export function useAllocationSession(sessionId: string | null, options?: UseAllocationSessionOptions) {
  const lineLimit = options?.lineLimit ?? 2000;
  const lineOffset = options?.lineOffset ?? 0;
  const key = sessionId
    ? `/api/v1/allocation/sessions/${sessionId}?line_limit=${lineLimit}&line_offset=${lineOffset}`
    : null;

  return useSWR<AllocationSessionDetail>(
    key,
    (path: string) =>
      apiRequest<AllocationSessionDetail>(path, {
        timeoutMs: 45000,
        retryCount: 1,
      })
  );
}
