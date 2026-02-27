/**
 * Settings page — team configuration form.
 *
 * Learn: Displays and edits team settings via GET/PATCH /settings/teams/{id}.
 * Uses controlled form inputs with local state, submitted via mutation.
 */

import { useState, useEffect } from "react";
import { useTeamSettings, useUpdateTeamSettings } from "../hooks/useApi";

interface SettingsProps {
  teamId: string;
}

export function Settings({ teamId }: SettingsProps) {
  const { data: teamSettings, isLoading } = useTeamSettings(teamId);
  const updateMut = useUpdateTeamSettings(teamId);

  const [form, setForm] = useState<Record<string, unknown>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (teamSettings?.settings) {
      setForm(teamSettings.settings);
    }
  }, [teamSettings]);

  const handleChange = (key: string, value: unknown) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    updateMut.mutate(form, {
      onSuccess: () => setSaved(true),
    });
  };

  if (isLoading) {
    return <div className="loading">Loading settings...</div>;
  }

  return (
    <div className="settings-page">
      <h1>Team Settings</h1>
      {teamSettings && (
        <p className="settings-team-name">{teamSettings.team_name}</p>
      )}

      <form className="settings-form" onSubmit={handleSubmit}>
        {/* Cost Limits */}
        <div className="settings-section">
          <h2>Cost Controls</h2>
          <div className="settings-field">
            <label>Daily Cost Limit (USD)</label>
            <input
              type="number"
              step="0.01"
              value={(form.daily_cost_limit_usd as number) ?? ""}
              onChange={(e) =>
                handleChange(
                  "daily_cost_limit_usd",
                  e.target.value ? Number(e.target.value) : null
                )
              }
              placeholder="No limit"
            />
          </div>
          <div className="settings-field">
            <label>Per-Task Cost Limit (USD)</label>
            <input
              type="number"
              step="0.01"
              value={(form.task_cost_limit_usd as number) ?? ""}
              onChange={(e) =>
                handleChange(
                  "task_cost_limit_usd",
                  e.target.value ? Number(e.target.value) : null
                )
              }
              placeholder="No limit"
            />
          </div>
        </div>

        {/* Agent Configuration */}
        <div className="settings-section">
          <h2>Agent Defaults</h2>
          <div className="settings-field">
            <label>Default Model</label>
            <input
              type="text"
              value={(form.default_model as string) ?? ""}
              onChange={(e) =>
                handleChange("default_model", e.target.value || null)
              }
              placeholder="claude-sonnet-4-20250514"
            />
          </div>
          <div className="settings-field">
            <label>Branch Prefix</label>
            <input
              type="text"
              value={(form.branch_prefix as string) ?? ""}
              onChange={(e) =>
                handleChange("branch_prefix", e.target.value || null)
              }
              placeholder="task/"
            />
          </div>
        </div>

        {/* Workflow */}
        <div className="settings-section">
          <h2>Workflow</h2>
          <div className="settings-field settings-toggle">
            <label>
              <input
                type="checkbox"
                checked={(form.require_review as boolean) ?? true}
                onChange={(e) =>
                  handleChange("require_review", e.target.checked)
                }
              />
              Require code review before merge
            </label>
          </div>
          <div className="settings-field settings-toggle">
            <label>
              <input
                type="checkbox"
                checked={(form.auto_merge as boolean) ?? false}
                onChange={(e) =>
                  handleChange("auto_merge", e.target.checked)
                }
              />
              Auto-merge after approval
            </label>
          </div>
        </div>

        <div className="settings-actions">
          <button
            type="submit"
            className="settings-save-btn"
            disabled={updateMut.isPending}
          >
            {updateMut.isPending ? "Saving..." : "Save Settings"}
          </button>
          {saved && <span className="settings-saved">Saved!</span>}
          {updateMut.isError && (
            <span className="settings-error">
              Error: {updateMut.error?.message}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}
