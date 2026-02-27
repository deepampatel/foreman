"""Aider adapter — spawns Aider CLI in non-interactive mode.

Learn: Aider is a terminal-based AI pair programming tool. It supports:
- --message: Pass an initial instruction without interactive prompts
- --yes-always: Auto-accept all changes (non-interactive)
- --no-auto-commits: Let Entourage manage git commits
- Multiple LLM backends (Claude, GPT-4, etc.) via ANTHROPIC_API_KEY/OPENAI_API_KEY

Key difference from Claude Code / Codex:
Aider does NOT support MCP natively. Instead, the prompt includes REST API
instructions so the agent can call Entourage endpoints directly via shell
commands. This is less seamless than MCP but still enables task management
and human-in-the-loop workflows.
"""

import shutil

from openclaw.agent.adapters.base import AdapterConfig, AdapterResult, AgentAdapter


class AiderAdapter(AgentAdapter):
    """Adapter for Aider CLI (aider-chat)."""

    @property
    def name(self) -> str:
        return "aider"

    def validate_environment(self) -> tuple[bool, str]:
        """Check that the `aider` binary is available."""
        if shutil.which("aider"):
            return True, "Aider CLI found"
        return (
            False,
            "Aider CLI not found on PATH. "
            "Install with: pip install aider-chat",
        )

    def build_prompt(
        self,
        task_title: str,
        task_description: str,
        agent_id: str,
        team_id: str,
        task_id: int,
        role: str = "engineer",
        conventions: list[dict] | None = None,
        context: dict | None = None,
    ) -> str:
        """Build the prompt for Aider with REST API instructions.

        Learn: Since Aider doesn't support MCP, we embed curl-based API
        instructions in the prompt. The agent can run these as shell commands
        to update task status, ask humans, and send messages.
        """
        return f"""You are an Entourage engineer agent working on a task.

TASK #{task_id}: {task_title}

DESCRIPTION:
{task_description}

INSTRUCTIONS:
Work on the task using your normal coding abilities. When you need to
interact with the Entourage platform, run these commands in the shell:

1. MARK TASK DONE (when you finish coding):
   curl -s -X POST http://localhost:8000/api/v1/tasks/{task_id}/status \\
     -H "Content-Type: application/json" \\
     -d '{{"status": "in_review", "actor_id": "{agent_id}"}}'

2. ASK A HUMAN (when you need a decision):
   curl -s -X POST http://localhost:8000/api/v1/human-requests \\
     -H "Content-Type: application/json" \\
     -d '{{"team_id": "{team_id}", "agent_id": "{agent_id}", "task_id": {task_id}, "kind": "question", "question": "YOUR QUESTION HERE"}}'

3. ADD A COMMENT to the task:
   curl -s -X POST http://localhost:8000/api/v1/tasks/{task_id}/comments \\
     -H "Content-Type: application/json" \\
     -d '{{"body": "YOUR COMMENT HERE"}}'

4. SEND A MESSAGE to another agent:
   curl -s -X POST http://localhost:8000/api/v1/teams/{team_id}/messages \\
     -H "Content-Type: application/json" \\
     -d '{{"sender_id": "{agent_id}", "sender_type": "agent", "recipient_id": "AGENT_UUID", "recipient_type": "agent", "content": "YOUR MESSAGE"}}'

YOUR IDENTITY:
- agent_id: {agent_id}
- team_id: {team_id}
- task_id: {task_id}

Focus on completing the task. Write clean, tested code. When done, run
the curl command to move the task to in_review status.
"""

    async def run(self, prompt: str, config: AdapterConfig) -> AdapterResult:
        """Spawn Aider in non-interactive mode.

        Learn: Aider's --message flag provides an initial instruction.
        --yes-always avoids interactive prompts. --no-auto-commits lets
        Entourage control the git workflow.
        """
        cmd = [
            "aider",
            "--message",
            prompt,
            "--yes-always",  # Don't prompt for confirmation
            "--no-auto-commits",  # Let Entourage manage commits
            "--no-git",  # Don't initialize git (worktree already exists)
        ]

        # Pass API URL so curl commands in the prompt can reach the backend
        config.env_overrides.setdefault("OPENCLAW_API_URL", config.api_url)

        return await self._run_subprocess(cmd, config)
