/**
 * Tasks page — kanban-style board grouped by status.
 */

import { TaskCard } from "../components/TaskCard";
import { useAgents, useTasks } from "../hooks/useApi";
import { useTeamSocket } from "../hooks/useTeamSocket";
import { STATUS_LABELS, type TaskStatus } from "../api/types";

interface TasksProps {
  teamId: string;
}

const KANBAN_COLUMNS: TaskStatus[] = [
  "todo",
  "in_progress",
  "in_review",
  "in_approval",
  "merging",
  "done",
];

export function Tasks({ teamId }: TasksProps) {
  useTeamSocket(teamId);

  const { data: tasks, isLoading } = useTasks(teamId);
  const { data: agents } = useAgents(teamId);

  if (isLoading) return <div className="loading">Loading tasks...</div>;

  return (
    <div className="tasks-page">
      <h1>Tasks</h1>
      <div className="kanban-board">
        {KANBAN_COLUMNS.map((status) => {
          const columnTasks = tasks?.filter((t) => t.status === status) ?? [];
          return (
            <div key={status} className="kanban-column">
              <div className="kanban-header">
                <span className="kanban-title">
                  {STATUS_LABELS[status]}
                </span>
                <span className="kanban-count">{columnTasks.length}</span>
              </div>
              <div className="kanban-cards">
                {columnTasks.map((task) => (
                  <TaskCard key={task.id} task={task} agents={agents} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
