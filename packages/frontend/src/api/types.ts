/**
 * Shared API types — mirrors the backend Pydantic schemas.
 */

export interface Org {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface Team {
  id: string;
  org_id: string;
  name: string;
  slug: string;
  created_at: string;
}

export interface Agent {
  id: string;
  team_id: string;
  name: string;
  role: string;
  model: string;
  config: Record<string, unknown>;
  status: string;
  created_at: string;
}

export interface Task {
  id: number;
  team_id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  dri_id: string | null;
  assignee_id: string | null;
  depends_on: number[];
  repo_ids: string[];
  tags: string[];
  branch: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface TaskEvent {
  id: number;
  type: string;
  data: Record<string, unknown>;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Message {
  id: number;
  team_id: string;
  sender_id: string;
  sender_type: string;
  recipient_id: string;
  recipient_type: string;
  task_id: number | null;
  content: string;
  created_at: string;
}

export interface Session {
  id: number;
  agent_id: string;
  task_id: number | null;
  started_at: string;
  ended_at: string | null;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
  model: string | null;
  error: string | null;
}

export interface CostSummary {
  team_id: string;
  period_days: number;
  total_cost_usd: number;
  total_tokens_in: number;
  total_tokens_out: number;
  session_count: number;
  per_agent: { agent_id: string; agent_name: string; cost_usd: number; sessions: number }[];
  per_model: { model: string | null; cost_usd: number; sessions: number }[];
}

export type TaskStatus =
  | "todo"
  | "in_progress"
  | "in_review"
  | "in_approval"
  | "merging"
  | "done"
  | "cancelled";

export type Priority = "low" | "medium" | "high" | "critical";

export const STATUS_LABELS: Record<TaskStatus, string> = {
  todo: "To Do",
  in_progress: "In Progress",
  in_review: "In Review",
  in_approval: "Approval",
  merging: "Merging",
  done: "Done",
  cancelled: "Cancelled",
};

export const PRIORITY_COLORS: Record<Priority, string> = {
  low: "#6b7280",
  medium: "#3b82f6",
  high: "#f59e0b",
  critical: "#ef4444",
};
