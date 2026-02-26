/**
 * Task card — shows task title, status, priority, and assignee.
 */

import type { Agent, Task } from "../api/types";
import { PRIORITY_COLORS, STATUS_LABELS, type Priority, type TaskStatus } from "../api/types";

interface TaskCardProps {
  task: Task;
  agents?: Agent[];
}

export function TaskCard({ task, agents }: TaskCardProps) {
  const assignee = agents?.find((a) => a.id === task.assignee_id);
  const statusLabel = STATUS_LABELS[task.status as TaskStatus] || task.status;
  const priorityColor = PRIORITY_COLORS[task.priority as Priority] || "#6b7280";

  return (
    <div className="task-card">
      <div className="task-header">
        <span className="task-id">#{task.id}</span>
        <span
          className="task-priority"
          style={{ color: priorityColor }}
        >
          {task.priority}
        </span>
      </div>
      <div className="task-title">{task.title}</div>
      <div className="task-footer">
        <span className={`task-status task-status-${task.status}`}>
          {statusLabel}
        </span>
        {assignee && (
          <span className="task-assignee">{assignee.name}</span>
        )}
      </div>
      {task.tags.length > 0 && (
        <div className="task-tags">
          {task.tags.map((tag) => (
            <span key={tag} className="task-tag">{tag}</span>
          ))}
        </div>
      )}
    </div>
  );
}
