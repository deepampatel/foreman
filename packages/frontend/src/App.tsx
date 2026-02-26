/**
 * Root application component with routing.
 *
 * Learn: Uses React Router v7 for page navigation.
 * Team selection is managed via URL params and local state.
 * The sidebar provides navigation between dashboard sections.
 */

import { useState } from "react";
import { Routes, Route, NavLink, Navigate } from "react-router-dom";
import { useOrgs, useTeams } from "./hooks/useApi";
import { Dashboard } from "./pages/Dashboard";
import { Tasks } from "./pages/Tasks";
import "./App.css";

function App() {
  const { data: orgs } = useOrgs();
  const [orgId, setOrgId] = useState<string>("");
  const { data: teams } = useTeams(orgId || undefined);
  const [teamId, setTeamId] = useState<string>("");

  // Auto-select first org and team
  if (orgs?.length && !orgId) {
    setOrgId(orgs[0].id);
  }
  if (teams?.length && !teamId) {
    setTeamId(teams[0].id);
  }

  return (
    <div className="app">
      {/* Sidebar */}
      <nav className="sidebar">
        <div className="sidebar-brand">
          <h1>OpenClaw</h1>
        </div>

        {/* Team selector */}
        <div className="sidebar-section">
          <label className="sidebar-label">Team</label>
          {teams?.length ? (
            <select
              className="team-select"
              value={teamId}
              onChange={(e) => setTeamId(e.target.value)}
            >
              {teams.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          ) : (
            <span className="sidebar-empty">No teams</span>
          )}
        </div>

        {/* Navigation */}
        <div className="sidebar-nav">
          <NavLink to="/dashboard" className="nav-link">
            Dashboard
          </NavLink>
          <NavLink to="/tasks" className="nav-link">
            Tasks
          </NavLink>
        </div>
      </nav>

      {/* Main content */}
      <main className="main-content">
        {teamId ? (
          <Routes>
            <Route path="/dashboard" element={<Dashboard teamId={teamId} />} />
            <Route path="/tasks" element={<Tasks teamId={teamId} />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>
        ) : (
          <div className="empty-state-page">
            <h2>Welcome to OpenClaw</h2>
            <p>Create an organization and team to get started.</p>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
