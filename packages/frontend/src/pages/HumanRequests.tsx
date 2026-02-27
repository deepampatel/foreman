/**
 * Human Requests page — full-page view for managing human-in-the-loop requests.
 *
 * Learn: Filterable by status (pending/resolved/expired). Shows all requests
 * for the team with inline response forms for pending ones.
 */

import { useState } from "react";
import { HumanRequestCard } from "../components/HumanRequestCard";
import { useAgents, useHumanRequests, useRespondToRequest } from "../hooks/useApi";
import { useTeamSocket } from "../hooks/useTeamSocket";

interface HumanRequestsProps {
  teamId: string;
}

const FILTERS = [
  { label: "Pending", value: "pending" },
  { label: "Resolved", value: "resolved" },
  { label: "Expired", value: "expired" },
  { label: "All", value: undefined },
] as const;

export function HumanRequests({ teamId }: HumanRequestsProps) {
  useTeamSocket(teamId);

  const [statusFilter, setStatusFilter] = useState<string | undefined>(
    "pending"
  );
  const { data: requests } = useHumanRequests(teamId, statusFilter);
  const { data: agents } = useAgents(teamId);
  const respondMutation = useRespondToRequest(teamId);

  const handleRespond = (requestId: number, response: string) => {
    respondMutation.mutate({ requestId, response });
  };

  return (
    <div className="hr-page">
      <h1>Human Requests</h1>

      {/* Filter tabs */}
      <div className="hr-filters">
        {FILTERS.map((f) => (
          <button
            key={f.label}
            className={`hr-filter-btn ${
              statusFilter === f.value ? "hr-filter-active" : ""
            }`}
            onClick={() => setStatusFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {/* Request list */}
      <div className="hr-list">
        {requests?.map((req) => (
          <HumanRequestCard
            key={req.id}
            request={req}
            agents={agents}
            onRespond={handleRespond}
            isResponding={respondMutation.isPending}
          />
        ))}
        {requests?.length === 0 && (
          <p className="empty-state">
            No {statusFilter || ""} requests found.
          </p>
        )}
      </div>
    </div>
  );
}
