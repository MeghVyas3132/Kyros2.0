import useSWR from "swr";
import { apiRequest } from "@/lib/api";

interface Season {
  id: string;
  brand_id: string;
  name: string;
  start_date: string;
  end_date: string;
  status: string;
  categories: string[] | null;
  created_at: string;
  updated_at: string;
}

interface WorkflowStep {
  step: number;
  label: string;
  description: string;
  is_complete: boolean;
  is_current: boolean;
  is_blocked: boolean;
  action_label: string | null;
  action_url: string | null;
}

interface WorkflowState {
  season_id: string;
  season_name: string;
  current_status: string;
  current_step: number;
  total_steps: number;
  steps: WorkflowStep[];
  next_step: {
    step: number;
    label: string;
    action_label: string;
    action_url: string;
  } | null;
}

const ACTIVE_STATUSES = new Set(["PLANNING", "BUYING", "RECEIVING", "ALLOCATING"]);

export function useSeasons() {
  return useSWR<Season[]>("/api/v1/seasons", (url: string) =>
    apiRequest<Season[]>(url)
  );
}

export function useActiveSeasonId(): string | null {
  const { data } = useSeasons();
  if (!data) return null;
  const active = data.find((s) => ACTIVE_STATUSES.has(s.status));
  return active?.id ?? null;
}

export function useWorkflowState(seasonId: string | null) {
  return useSWR<WorkflowState>(
    seasonId ? `/api/v1/seasons/${seasonId}/workflow-state` : null,
    (url: string) => apiRequest<WorkflowState>(url)
  );
}
