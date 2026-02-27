"""Claude Code adapter — spawns Claude Code CLI as a subprocess.

Learn: Claude Code is Anthropic's coding agent CLI. It supports:
- --print: Non-interactive mode (reads prompt, works, prints output, exits)
- --mcp-config: JSON file describing MCP servers to connect to
- --allowedTools: Restrict which tools the agent can use
- --max-turns: Safety limit on agentic loop iterations

The adapter writes a temporary MCP config file that points Claude Code
at our MCP server. When Claude Code calls ask_human(wait=true), the
MCP tool blocks until a human responds — enabling seamless human-in-the-loop.
"""

import json
import os
import shutil
import tempfile

from openclaw.agent.adapters.base import AdapterConfig, AdapterResult, AgentAdapter


class ClaudeCodeAdapter(AgentAdapter):
    """Adapter for Claude Code CLI (claude command)."""

    @property
    def name(self) -> str:
        return "claude_code"

    def validate_environment(self) -> tuple[bool, str]:
        """Check that the `claude` binary is available."""
        if shutil.which("claude"):
            return True, "Claude Code CLI found"
        return (
            False,
            "Claude Code CLI not found on PATH. "
            "Install with: npm install -g @anthropic-ai/claude-code",
        )

    def build_prompt(
        self,
        task_title: str,
        task_description: str,
        agent_id: str,
        team_id: str,
        task_id: int,
    ) -> str:
        """Build the prompt that tells Claude Code how to use Entourage MCP tools.

        Learn: The prompt gives Claude Code all the context it needs:
        - What task to work on
        - Which MCP tools to call and when
        - How to handle human-in-the-loop (ask_human with wait=true)
        - When to signal completion
        """
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
        """Spawn Claude Code with our MCP server configured.

        Learn: We write a temp MCP config file, then run:
        claude --print --mcp-config <path> --allowedTools "mcp__entourage__*" <prompt>

        Claude Code spawns our MCP server as a child process (stdio transport).
        The MCP server makes HTTP calls to our backend API.
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

        # Create temp file in working directory for clean cleanup
        config_dir = tempfile.mkdtemp(prefix="entourage-mcp-")
        config_path = os.path.join(config_dir, "mcp-config.json")

        try:
            with open(config_path, "w") as f:
                json.dump(mcp_config, f)

            # Build command
            cmd = [
                "claude",
                "--print",  # Non-interactive: print result and exit
                "--mcp-config",
                config_path,
                "--allowedTools",
                "mcp__entourage__*",  # Only allow our MCP tools
                "--max-turns",
                "100",  # Safety limit
                prompt,
            ]

            # Run using the shared subprocess helper
            return await self._run_subprocess(cmd, config)

        finally:
            # Clean up temp config
            try:
                os.unlink(config_path)
                os.rmdir(config_dir)
            except OSError:
                pass
