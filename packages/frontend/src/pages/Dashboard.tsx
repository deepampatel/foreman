/**
 * Dashboard page — overview of team activity, stats, and agents.
 *
 * Learn: The dashboard uses TanStack Query hooks for data fetching
 * and useTeamSocket for real-time updates. When a WebSocket event
 * arrives, the relevant query cache is invalidated and the UI
 * re-renders with fresh data.
 */

import { AgentCard } from "../components/AgentCard";
import { StatCard } from "../components/StatCard";
import { TaskCard } from "../components/TaskCard";
import { useAgents, useCosts, useTasks } from "../hooks/useApi";
import { useTeamSocket } from "../hooks/useTeamSocket";

interface DashboardProps {
  teamId: string;
}

export function Dashboard({ teamId }: DashboardProps) {
  // Real-time updates via WebSocket
  useTeamSocket(teamId);

  const { data: tasks } = useTasks(teamId);
  const { data: agents } = useAgents(teamId);
  const { data: costs } = useCosts(teamId);

  const activeTasks = tasks?.filter(
    (t) => !["done", "cancelled"].includes(t.status)
  );
  const workingAgents = agents?.filter((a) => a.status === "working");

  return (
    <div className="dashboard">
      <h1>Dashboard</h1>

      {/* Stats Row */}
      <div className="stats-row">
        <StatCard
          label="Active Tasks"
          value={activeTasks?.length ?? 0}
        />
        <StatCard
          label="Working Agents"
          value={`${workingAgents?.length ?? 0} / ${agents?.length ?? 0}`}
        />
        <StatCard
          label="Cost (7d)"
          value={`$${(costs?.total_cost_usd ?? 0).toFixed(2)}`}
        />
        <StatCard
          label="Sessions (7d)"
          value={costs?.session_count ?? 0}
        />
      </div>

      {/* Agents Section */}
      <section className="dashboard-section">
        <h2>Agents</h2>
        <div className="agent-grid">
          {agents?.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))}
          {agents?.length === 0 && (
            <p className="empty-state">No agents configured</p>
          )}
        </div>
      </section>

      {/* Active Tasks Section */}
      <section className="dashboard-section">
        <h2>Active Tasks</h2>
        <div className="task-list">
          {activeTasks?.map((task) => (
            <TaskCard key={task.id} task={task} agents={agents} />
          ))}
          {activeTasks?.length === 0 && (
            <p className="empty-state">No active tasks</p>
          )}
        </div>
      </section>

      {/* Cost Breakdown */}
      {costs && costs.per_agent.length > 0 && (
        <section className="dashboard-section">
          <h2>Cost Breakdown (7d)</h2>
          <div className="cost-table">
            <table>
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Sessions</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {costs.per_agent.map((a) => (
                  <tr key={a.agent_id}>
                    <td>{a.agent_name}</td>
                    <td>{a.sessions}</td>
                    <td>${a.cost_usd.toFixed(4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
