/**
 * TanStack Query hooks — typed data fetching for all API endpoints.
 *
 * Learn: Each hook wraps a TanStack useQuery/useMutation call.
 * The query key determines caching and invalidation. WebSocket
 * events trigger invalidation via useTeamSocket.
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import type { Agent, CostSummary, Org, Task, Team } from "../api/types";

// ─── Organizations ─────────────────────────────────────

export function useOrgs() {
  return useQuery({
    queryKey: ["orgs"],
    queryFn: () => apiClient.get<Org[]>("/api/v1/orgs"),
  });
}

// ─── Teams ─────────────────────────────────────────────

export function useTeams(orgId: string | undefined) {
  return useQuery({
    queryKey: ["teams", orgId],
    queryFn: () => apiClient.get<Team[]>(`/api/v1/orgs/${orgId}/teams`),
    enabled: !!orgId,
  });
}

// ─── Agents ────────────────────────────────────────────

export function useAgents(teamId: string | undefined) {
  return useQuery({
    queryKey: ["agents", teamId],
    queryFn: () => apiClient.get<Agent[]>(`/api/v1/teams/${teamId}/agents`),
    enabled: !!teamId,
    refetchInterval: 10_000, // Poll every 10s for agent status changes
  });
}

// ─── Tasks ─────────────────────────────────────────────

export function useTasks(
  teamId: string | undefined,
  filters?: { status?: string; assignee_id?: string }
) {
  return useQuery({
    queryKey: ["tasks", teamId, filters],
    queryFn: () => {
      const params: Record<string, string> = {};
      if (filters?.status) params.status = filters.status;
      if (filters?.assignee_id) params.assignee_id = filters.assignee_id;
      return apiClient.get<Task[]>(`/api/v1/teams/${teamId}/tasks`, params);
    },
    enabled: !!teamId,
    refetchInterval: 15_000,
  });
}

export function useTask(taskId: number | undefined) {
  return useQuery({
    queryKey: ["task", taskId],
    queryFn: () => apiClient.get<Task>(`/api/v1/tasks/${taskId}`),
    enabled: !!taskId,
  });
}

// ─── Costs ─────────────────────────────────────────────

export function useCosts(teamId: string | undefined, days: number = 7) {
  return useQuery({
    queryKey: ["costs", teamId, days],
    queryFn: () =>
      apiClient.get<CostSummary>(`/api/v1/teams/${teamId}/costs`, {
        days: String(days),
      }),
    enabled: !!teamId,
    refetchInterval: 30_000,
  });
}
