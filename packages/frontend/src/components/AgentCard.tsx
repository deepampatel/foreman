/**
 * Agent card — shows agent name, role, status with live indicator.
 */

import type { Agent } from "../api/types";

interface AgentCardProps {
  agent: Agent;
}

const STATUS_COLORS: Record<string, string> = {
  idle: "#6b7280",
  working: "#10b981",
  paused: "#f59e0b",
};

export function AgentCard({ agent }: AgentCardProps) {
  return (
    <div className="agent-card">
      <div className="agent-header">
        <span
          className="agent-status-dot"
          style={{ backgroundColor: STATUS_COLORS[agent.status] || "#6b7280" }}
        />
        <span className="agent-name">{agent.name}</span>
      </div>
      <div className="agent-meta">
        <span className="agent-role">{agent.role}</span>
        <span className="agent-model">{agent.model.split("-").slice(0, 2).join(" ")}</span>
      </div>
      <div className="agent-status-text">{agent.status}</div>
    </div>
  );
}
