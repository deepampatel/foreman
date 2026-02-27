"""Codex adapter — spawns OpenAI Codex CLI as a subprocess.

Learn: Codex is OpenAI's coding agent CLI. It supports:
- Full-auto mode for non-interactive operation
- MCP server configuration via config file
- Working directory context for repo-aware coding

The adapter follows the same pattern as Claude Code:
write temp MCP config → spawn subprocess → handle timeout → return result.
"""

import json
import os
import shutil
import tempfile

from openclaw.agent.adapters.base import AdapterConfig, AdapterResult, AgentAdapter


class CodexAdapter(AgentAdapter):
    """Adapter for OpenAI Codex CLI."""

    @property
    def name(self) -> str:
        return "codex"

    def validate_environment(self) -> tuple[bool, str]:
        """Check that the `codex` binary is available."""
        if shutil.which("codex"):
            return True, "Codex CLI found"
        return (
            False,
            "Codex CLI not found on PATH. "
            "Install with: npm install -g @openai/codex",
        )

    def build_prompt(
        self,
        task_title: str,
        task_description: str,
        agent_id: str,
        team_id: str,
        task_id: int,
    ) -> str:
        """Build the prompt for Codex with Entourage MCP tool instructions."""
        return f"""You are an Entourage engineer agent working on a task.

TASK #{task_id}: {task_title}

DESCRIPTION:
{task_description}

INSTRUCTIONS:
You have access to Entourage MCP tools for task management and coordination.
Work on the task using your normal coding abilities (read files, write files,
run commands, etc.) and use these Entourage MCP tools as needed:

1. TASK STATUS: When you start working, the task is already in_progress.
   When you're done, call:
   mcp__entourage__change_task_status(task_id={task_id}, status="in_review", actor_id="{agent_id}")

2. HUMAN INPUT: If you need a decision from a human, call:
   mcp__entourage__ask_human(
     team_id="{team_id}", agent_id="{agent_id}",
     kind="question", question="your question here",
     task_id={task_id}, wait=true
   )
   This will BLOCK until the human responds, then return their answer.

3. MESSAGES: To communicate with other agents, call:
   mcp__entourage__send_message(
     team_id="{team_id}", sender_id="{agent_id}",
     recipient_id="<other_agent_id>", body="your message"
   )

4. COMMENTS: To add notes to the task, call:
   mcp__entourage__add_task_comment(task_id={task_id}, body="your comment")

YOUR IDENTITY:
- agent_id: {agent_id}
- team_id: {team_id}
- task_id: {task_id}

Focus on completing the task. Write clean, tested code. When done, move
the task to in_review status.
"""

    async def run(self, prompt: str, config: AdapterConfig) -> AdapterResult:
        """Spawn Codex CLI with our MCP server configured.

        Learn: Codex supports MCP configuration similar to Claude Code.
        We write a temp config and pass it via --mcp-config flag.
        """
        # Write temporary MCP config
        mcp_config = {
            "mcpServers": {
                "entourage": {
                    "command": config.mcp_server_command[0],
                    "args": config.mcp_server_command[1:],
                    "env": {
                        "OPENCLAW_API_URL": config.api_url,
                    },
                }
            }
        }

        config_dir = tempfile.mkdtemp(prefix="entourage-mcp-")
        config_path = os.path.join(config_dir, "mcp-config.json")

        try:
            with open(config_path, "w") as f:
                json.dump(mcp_config, f)

            cmd = [
                "codex",
                "--full-auto",  # Non-interactive mode
                "--mcp-config",
                config_path,
                prompt,
            ]

            return await self._run_subprocess(cmd, config)

        finally:
            try:
                os.unlink(config_path)
                os.rmdir(config_dir)
            except OSError:
                pass
