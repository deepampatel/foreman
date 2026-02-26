#!/usr/bin/env node
/**
 * OpenClaw MCP Server — the primary interface for OpenClaw agents.
 *
 * Learn: MCP (Model Context Protocol) is how AI agents discover and use tools.
 * This server exposes our platform's capabilities as MCP tools that any
 * MCP-compatible agent (OpenClaw, Claude, etc.) can call.
 *
 * Runs via stdio transport: OPENCLAW_API_URL=http://localhost:8000 node dist/index.js
 *
 * Tools grow with each phase:
 *   Phase 0: ping
 *   Phase 1: list_teams, get_team, list_agents, list_repos
 *   Phase 2: create_task, list_tasks, get_task, change_task_status, send_message, ...
 *   Phase 3: get_task_diff, get_task_files, ...
 *   Phase 4: start_session, record_usage, check_budget, run_command, read_file, ...
 *   Phase 7: ask_human, respond_to_request, ...
 *   Phase 8: approve_task, reject_task, ...
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import * as client from "./client.js";

const server = new McpServer({
  name: "openclaw",
  version: "0.1.0",
});

// ═══════════════════════════════════════════════════════════
// Phase 0: Foundation
// ═══════════════════════════════════════════════════════════

server.tool(
  "ping",
  "Check if the OpenClaw platform is reachable and healthy.",
  {},
  async () => {
    try {
      const health = await client.ping();
      return {
        content: [
          {
            type: "text",
            text: JSON.stringify(health, null, 2),
          },
        ],
      };
    } catch (error) {
      return {
        content: [
          {
            type: "text",
            text: `Error: ${error instanceof Error ? error.message : String(error)}`,
          },
        ],
        isError: true,
      };
    }
  }
);

// ═══════════════════════════════════════════════════════════
// Phase 1: Teams / Agents / Repos
// ═══════════════════════════════════════════════════════════

/**
 * Helper: wraps a function with try/catch → MCP response format.
 * Every tool returns either { content: [...] } or { content: [...], isError: true }.
 */
function toolHandler(fn: () => Promise<unknown>) {
  return async () => {
    try {
      const result = await fn();
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
      };
    } catch (error) {
      return {
        content: [
          {
            type: "text" as const,
            text: `Error: ${error instanceof Error ? error.message : String(error)}`,
          },
        ],
        isError: true,
      };
    }
  };
}

// ─── Organizations ──────────────────────────────────────────

server.tool(
  "list_orgs",
  "List all organizations.",
  {},
  toolHandler(() => client.listOrgs())
);

server.tool(
  "create_org",
  "Create a new organization.",
  { name: z.string().describe("Organization name"), slug: z.string().describe("URL-friendly slug (lowercase, hyphens)") },
  async (params) => {
    try {
      const org = await client.createOrg(params.name, params.slug);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(org, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

// ─── Teams ──────────────────────────────────────────────────

server.tool(
  "list_teams",
  "List all teams in an organization.",
  { org_id: z.string().describe("Organization UUID") },
  async (params) => {
    try {
      const teams = await client.listTeams(params.org_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(teams, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "create_team",
  "Create a new team in an organization. Auto-provisions a manager agent.",
  {
    org_id: z.string().describe("Organization UUID"),
    name: z.string().describe("Team name"),
    slug: z.string().describe("URL-friendly slug"),
  },
  async (params) => {
    try {
      const team = await client.createTeam(params.org_id, params.name, params.slug);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(team, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "get_team",
  "Get team details including agents and repositories.",
  { team_id: z.string().describe("Team UUID") },
  async (params) => {
    try {
      const team = await client.getTeam(params.team_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(team, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

// ─── Agents ─────────────────────────────────────────────────

server.tool(
  "list_agents",
  "List all agents in a team.",
  { team_id: z.string().describe("Team UUID") },
  async (params) => {
    try {
      const agents = await client.listAgents(params.team_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(agents, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "create_agent",
  "Create a new agent in a team.",
  {
    team_id: z.string().describe("Team UUID"),
    name: z.string().describe("Agent name"),
    role: z.string().describe("Agent role: manager, engineer, or reviewer").default("engineer"),
    model: z.string().describe("LLM model to use").default("claude-sonnet-4-20250514"),
  },
  async (params) => {
    try {
      const agent = await client.createAgent(
        params.team_id,
        params.name,
        params.role,
        params.model
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(agent, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

// ─── Repositories ───────────────────────────────────────────

server.tool(
  "list_repos",
  "List all repositories registered with a team.",
  { team_id: z.string().describe("Team UUID") },
  async (params) => {
    try {
      const repos = await client.listRepos(params.team_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(repos, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "register_repo",
  "Register a git repository with a team.",
  {
    team_id: z.string().describe("Team UUID"),
    name: z.string().describe("Repository name"),
    local_path: z.string().describe("Local filesystem path to the repo"),
    default_branch: z.string().describe("Default branch name").default("main"),
  },
  async (params) => {
    try {
      const repo = await client.registerRepo(
        params.team_id,
        params.name,
        params.local_path,
        params.default_branch
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(repo, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

// ═══════════════════════════════════════════════════════════
// Phase 2: Tasks / Messages
// ═══════════════════════════════════════════════════════════

// ─── Tasks ──────────────────────────────────────────────────

server.tool(
  "create_task",
  "Create a new task for a team. Starts in 'todo' status. Auto-generates a branch name.",
  {
    team_id: z.string().describe("Team UUID"),
    title: z.string().describe("Task title"),
    description: z.string().describe("Task description").default(""),
    priority: z.enum(["low", "medium", "high", "critical"]).describe("Task priority").default("medium"),
    assignee_id: z.string().describe("Agent UUID to assign").optional(),
    depends_on: z.array(z.number()).describe("Task IDs this task depends on").default([]),
    tags: z.array(z.string()).describe("Tags for categorization").default([]),
  },
  async (params) => {
    try {
      const task = await client.createTask(params.team_id, params.title, {
        description: params.description,
        priority: params.priority,
        assignee_id: params.assignee_id,
        depends_on: params.depends_on,
        tags: params.tags,
      });
      return {
        content: [{ type: "text" as const, text: JSON.stringify(task, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "list_tasks",
  "List tasks for a team. Can filter by status and assignee.",
  {
    team_id: z.string().describe("Team UUID"),
    status: z.string().describe("Filter by status (todo, in_progress, in_review, etc.)").optional(),
    assignee_id: z.string().describe("Filter by assigned agent UUID").optional(),
  },
  async (params) => {
    try {
      const tasks = await client.listTasks(params.team_id, {
        status: params.status,
        assignee_id: params.assignee_id,
      });
      return {
        content: [{ type: "text" as const, text: JSON.stringify(tasks, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "get_task",
  "Get detailed info about a single task.",
  { task_id: z.number().describe("Task ID") },
  async (params) => {
    try {
      const task = await client.getTask(params.task_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(task, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "update_task",
  "Update task fields (title, description, priority, tags). Does NOT change status.",
  {
    task_id: z.number().describe("Task ID"),
    title: z.string().describe("New title").optional(),
    description: z.string().describe("New description").optional(),
    priority: z.enum(["low", "medium", "high", "critical"]).describe("New priority").optional(),
    tags: z.array(z.string()).describe("New tags").optional(),
  },
  async (params) => {
    try {
      const task = await client.updateTask(params.task_id, {
        title: params.title,
        description: params.description,
        priority: params.priority,
        tags: params.tags,
      });
      return {
        content: [{ type: "text" as const, text: JSON.stringify(task, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "change_task_status",
  "Change task status. Validates transitions (can't skip steps) and enforces DAG dependencies.",
  {
    task_id: z.number().describe("Task ID"),
    status: z.enum(["todo", "in_progress", "in_review", "in_approval", "merging", "done", "cancelled"]).describe("New status"),
    actor_id: z.string().describe("UUID of the agent/user making the change").optional(),
  },
  async (params) => {
    try {
      const task = await client.changeTaskStatus(params.task_id, params.status, params.actor_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(task, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "assign_task",
  "Assign an agent to work on a task.",
  {
    task_id: z.number().describe("Task ID"),
    assignee_id: z.string().describe("Agent UUID to assign"),
  },
  async (params) => {
    try {
      const task = await client.assignTask(params.task_id, params.assignee_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(task, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "get_task_events",
  "Get the event history for a task — immutable audit trail of all changes.",
  { task_id: z.number().describe("Task ID") },
  async (params) => {
    try {
      const events = await client.getTaskEvents(params.task_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(events, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

// ─── Messages ───────────────────────────────────────────────

server.tool(
  "send_message",
  "Send a message to an agent or user. Used for inter-agent communication.",
  {
    team_id: z.string().describe("Team UUID"),
    sender_id: z.string().describe("Sender UUID"),
    sender_type: z.enum(["agent", "user"]).describe("Sender type"),
    recipient_id: z.string().describe("Recipient UUID"),
    recipient_type: z.enum(["agent", "user"]).describe("Recipient type"),
    content: z.string().describe("Message content"),
    task_id: z.number().describe("Related task ID").optional(),
  },
  async (params) => {
    try {
      const msg = await client.sendMessage(
        params.team_id,
        params.sender_id,
        params.sender_type,
        params.recipient_id,
        params.recipient_type,
        params.content,
        params.task_id
      );
      return {
        content: [{ type: "text" as const, text: JSON.stringify(msg, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "get_inbox",
  "Get an agent's inbox — unprocessed messages waiting for them.",
  {
    agent_id: z.string().describe("Agent UUID"),
    unprocessed_only: z.boolean().describe("Only return unprocessed messages").default(true),
  },
  async (params) => {
    try {
      const messages = await client.getInbox(params.agent_id, {
        unprocessed_only: params.unprocessed_only,
      });
      return {
        content: [{ type: "text" as const, text: JSON.stringify(messages, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

// ═══════════════════════════════════════════════════════════
// Phase 3: Git — Worktrees, Diffs, Files
// ═══════════════════════════════════════════════════════════

server.tool(
  "create_worktree",
  "Create a git worktree for a task. Each task gets its own branch and isolated checkout.",
  {
    task_id: z.number().describe("Task ID"),
    repo_id: z.string().describe("Repository UUID"),
  },
  async (params) => {
    try {
      const info = await client.createWorktree(params.task_id, params.repo_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(info, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "get_worktree",
  "Get info about a task's git worktree (path, branch, exists).",
  {
    task_id: z.number().describe("Task ID"),
    repo_id: z.string().describe("Repository UUID"),
  },
  async (params) => {
    try {
      const info = await client.getWorktreeInfo(params.task_id, params.repo_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(info, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "remove_worktree",
  "Remove a task's git worktree (after merge or cancellation).",
  {
    task_id: z.number().describe("Task ID"),
    repo_id: z.string().describe("Repository UUID"),
  },
  async (params) => {
    try {
      const result = await client.removeWorktree(params.task_id, params.repo_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(result, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "get_task_diff",
  "Get the full git diff of a task's branch vs the default branch.",
  {
    task_id: z.number().describe("Task ID"),
    repo_id: z.string().describe("Repository UUID"),
  },
  async (params) => {
    try {
      const result = await client.getTaskDiff(params.task_id, params.repo_id);
      return {
        content: [{ type: "text" as const, text: result.diff || "(no changes)" }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "get_changed_files",
  "List files changed on a task's branch (with additions/deletions count).",
  {
    task_id: z.number().describe("Task ID"),
    repo_id: z.string().describe("Repository UUID"),
  },
  async (params) => {
    try {
      const files = await client.getChangedFiles(params.task_id, params.repo_id);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(files, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "read_file",
  "Read a file from a task's branch (without needing the worktree checked out).",
  {
    task_id: z.number().describe("Task ID"),
    repo_id: z.string().describe("Repository UUID"),
    path: z.string().describe("File path relative to repo root"),
  },
  async (params) => {
    try {
      const result = await client.getFileContent(params.task_id, params.repo_id, params.path);
      return {
        content: [{ type: "text" as const, text: result.content }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

server.tool(
  "get_commits",
  "Get the commit log for a task's branch (commits not on the default branch).",
  {
    task_id: z.number().describe("Task ID"),
    repo_id: z.string().describe("Repository UUID"),
    limit: z.number().describe("Max commits to return").default(20),
  },
  async (params) => {
    try {
      const commits = await client.getCommitLog(params.task_id, params.repo_id, params.limit);
      return {
        content: [{ type: "text" as const, text: JSON.stringify(commits, null, 2) }],
      };
    } catch (error) {
      return {
        content: [{ type: "text" as const, text: `Error: ${error instanceof Error ? error.message : String(error)}` }],
        isError: true,
      };
    }
  }
);

// ═══════════════════════════════════════════════════════════
// Phase 4+: More tools added per phase
// ═══════════════════════════════════════════════════════════

// ─── Start server ──────────────────────────────────────────

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  console.error("MCP server error:", error);
  process.exit(1);
});
