/**
 * HTTP client for the OpenClaw backend API.
 *
 * Learn: This is the bridge between MCP tools and our REST API.
 * Every MCP tool calls a method here, which makes an HTTP request
 * to the backend. Clean separation of protocol (MCP) from transport (HTTP).
 *
 * Grows with each phase as new API endpoints are added.
 */

const API_URL = process.env.OPENCLAW_API_URL || "http://localhost:8000";

interface RequestOptions {
  method?: string;
  body?: unknown;
  params?: Record<string, string>;
}

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const url = new URL(path, API_URL);

  if (opts.params) {
    for (const [key, value] of Object.entries(opts.params)) {
      url.searchParams.set(key, value);
    }
  }

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };

  // Future: add API key auth header
  // if (process.env.OPENCLAW_API_KEY) {
  //   headers["Authorization"] = `Bearer ${process.env.OPENCLAW_API_KEY}`;
  // }

  const resp = await fetch(url.toString(), {
    method: opts.method || "GET",
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });

  if (!resp.ok) {
    const error = await resp.text();
    throw new Error(`API error ${resp.status}: ${error}`);
  }

  return resp.json() as Promise<T>;
}

// ─── Phase 0: Health ───────────────────────────────────────

export async function ping(): Promise<Record<string, unknown>> {
  return request("/api/v1/health");
}

// ─── Phase 1: Teams / Agents / Repos ───────────────────────

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

export interface TeamDetail extends Team {
  agents: Agent[];
  repositories: Repo[];
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

export interface Repo {
  id: string;
  team_id: string;
  name: string;
  local_path: string;
  default_branch: string;
  config: Record<string, unknown>;
  created_at: string;
}

export async function listOrgs(): Promise<Org[]> {
  return request("/api/v1/orgs");
}

export async function createOrg(name: string, slug: string): Promise<Org> {
  return request("/api/v1/orgs", { method: "POST", body: { name, slug } });
}

export async function listTeams(orgId: string): Promise<Team[]> {
  return request(`/api/v1/orgs/${orgId}/teams`);
}

export async function createTeam(
  orgId: string,
  name: string,
  slug: string
): Promise<Team> {
  return request(`/api/v1/orgs/${orgId}/teams`, {
    method: "POST",
    body: { name, slug },
  });
}

export async function getTeam(teamId: string): Promise<TeamDetail> {
  return request(`/api/v1/teams/${teamId}`);
}

export async function listAgents(teamId: string): Promise<Agent[]> {
  return request(`/api/v1/teams/${teamId}/agents`);
}

export async function createAgent(
  teamId: string,
  name: string,
  role: string = "engineer",
  model: string = "claude-sonnet-4-20250514",
  config: Record<string, unknown> = {}
): Promise<Agent> {
  return request(`/api/v1/teams/${teamId}/agents`, {
    method: "POST",
    body: { name, role, model, config },
  });
}

export async function listRepos(teamId: string): Promise<Repo[]> {
  return request(`/api/v1/teams/${teamId}/repos`);
}

export async function registerRepo(
  teamId: string,
  name: string,
  localPath: string,
  defaultBranch: string = "main",
  config: Record<string, unknown> = {}
): Promise<Repo> {
  return request(`/api/v1/teams/${teamId}/repos`, {
    method: "POST",
    body: { name, local_path: localPath, default_branch: defaultBranch, config },
  });
}

// ─── Phase 2: Tasks / Messages ─────────────────────────────

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

export interface Msg {
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

export async function createTask(
  teamId: string,
  title: string,
  opts: {
    description?: string;
    priority?: string;
    assignee_id?: string;
    dri_id?: string;
    depends_on?: number[];
    repo_ids?: string[];
    tags?: string[];
  } = {}
): Promise<Task> {
  return request(`/api/v1/teams/${teamId}/tasks`, {
    method: "POST",
    body: { title, ...opts },
  });
}

export async function listTasks(
  teamId: string,
  opts: { status?: string; assignee_id?: string; limit?: number } = {}
): Promise<Task[]> {
  const params: Record<string, string> = {};
  if (opts.status) params.status = opts.status;
  if (opts.assignee_id) params.assignee_id = opts.assignee_id;
  if (opts.limit) params.limit = String(opts.limit);
  return request(`/api/v1/teams/${teamId}/tasks`, { params });
}

export async function getTask(taskId: number): Promise<Task> {
  return request(`/api/v1/tasks/${taskId}`);
}

export async function updateTask(
  taskId: number,
  updates: { title?: string; description?: string; priority?: string; tags?: string[] }
): Promise<Task> {
  return request(`/api/v1/tasks/${taskId}`, {
    method: "PATCH",
    body: updates,
  });
}

export async function changeTaskStatus(
  taskId: number,
  status: string,
  actorId?: string
): Promise<Task> {
  return request(`/api/v1/tasks/${taskId}/status`, {
    method: "POST",
    body: { status, actor_id: actorId },
  });
}

export async function assignTask(
  taskId: number,
  assigneeId: string
): Promise<Task> {
  return request(`/api/v1/tasks/${taskId}/assign`, {
    method: "POST",
    body: { assignee_id: assigneeId },
  });
}

export async function getTaskEvents(taskId: number): Promise<TaskEvent[]> {
  return request(`/api/v1/tasks/${taskId}/events`);
}

export async function sendMessage(
  teamId: string,
  senderId: string,
  senderType: string,
  recipientId: string,
  recipientType: string,
  content: string,
  taskId?: number
): Promise<Msg> {
  return request(`/api/v1/teams/${teamId}/messages`, {
    method: "POST",
    body: {
      sender_id: senderId,
      sender_type: senderType,
      recipient_id: recipientId,
      recipient_type: recipientType,
      content,
      task_id: taskId,
    },
  });
}

export async function getInbox(
  agentId: string,
  opts: { unprocessed_only?: boolean; limit?: number } = {}
): Promise<Msg[]> {
  const params: Record<string, string> = {};
  if (opts.unprocessed_only !== undefined)
    params.unprocessed_only = String(opts.unprocessed_only);
  if (opts.limit) params.limit = String(opts.limit);
  return request(`/api/v1/agents/${agentId}/inbox`, { params });
}

// ─── Phase 3: Git ──────────────────────────────────────────
// (added in Phase 3)

// ... grows with each phase
