/**
 * Root application component.
 *
 * Learn: React Router v7 for page routing. TanStack Query for data fetching.
 * This starts minimal and grows with each phase.
 *
 * Phase 0: Just a health check display
 * Phase 5: Full dashboard with tasks, agents, chat, etc.
 */

import { useQuery } from "@tanstack/react-query";
import { apiClient } from "./api/client";

function App() {
  const { data: health, isLoading, error } = useQuery({
    queryKey: ["health"],
    queryFn: () => apiClient.get<Record<string, string>>("/api/v1/health"),
    refetchInterval: 10000,
  });

  return (
    <div style={{ padding: "2rem", maxWidth: "800px", margin: "0 auto" }}>
      <h1 style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>
        OpenClaw Platform
      </h1>
      <p style={{ color: "#888", marginBottom: "2rem" }}>
        AI Developer Productivity — Management Layer for OpenClaw Agents
      </p>

      <div
        style={{
          background: "#1a1a1a",
          borderRadius: "8px",
          padding: "1.5rem",
          border: "1px solid #333",
        }}
      >
        <h2 style={{ fontSize: "1rem", color: "#888", marginBottom: "1rem" }}>
          System Health
        </h2>

        {isLoading && <p>Checking...</p>}

        {error && (
          <p style={{ color: "#ef4444" }}>
            Error: {error instanceof Error ? error.message : "Unknown error"}
          </p>
        )}

        {health && (
          <div style={{ display: "grid", gap: "0.5rem" }}>
            {Object.entries(health).map(([key, value]) => (
              <div
                key={key}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  padding: "0.5rem 0",
                  borderBottom: "1px solid #222",
                }}
              >
                <span style={{ color: "#aaa" }}>{key}</span>
                <span
                  style={{
                    color: value === "ok" || value === "healthy"
                      ? "#22c55e"
                      : "#f59e0b",
                    fontFamily: "monospace",
                  }}
                >
                  {value}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      <p
        style={{
          marginTop: "2rem",
          color: "#555",
          fontSize: "0.85rem",
          textAlign: "center",
        }}
      >
        Phase 0 — Skeleton. Dashboard, tasks, and agents coming in Phase 5.
      </p>
    </div>
  );
}

export default App;
