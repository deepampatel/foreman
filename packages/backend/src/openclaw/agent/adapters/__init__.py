"""Agent adapter registry — pluggable coding agent backends.

Learn: Entourage dispatches to external coding agents via adapters.
Each adapter knows how to spawn a specific tool (Claude Code, Codex, Aider)
as a subprocess, configure it with our MCP server, and handle the lifecycle.

The registry provides a simple interface:
    adapter = get_adapter("claude_code")
    result = await adapter.run(prompt, config)

Agents specify their adapter via the config JSONB column:
    agent.config["adapter"] = "claude_code"  # default
"""

from openclaw.agent.adapters.base import (
    AdapterConfig,
    AdapterResult,
    AgentAdapter,
)
from openclaw.agent.adapters.claude_code import ClaudeCodeAdapter

__all__ = [
    "AgentAdapter",
    "AdapterConfig",
    "AdapterResult",
    "get_adapter",
    "list_adapters",
    "register_adapter",
]

# ─── Registry ──────────────────────────────────────────────

_ADAPTERS: dict[str, type[AgentAdapter]] = {
    "claude_code": ClaudeCodeAdapter,
}


def get_adapter(name: str) -> AgentAdapter:
    """Get an adapter instance by name.

    Raises ValueError if the adapter is not registered.
    """
    cls = _ADAPTERS.get(name)
    if not cls:
        available = ", ".join(sorted(_ADAPTERS.keys()))
        raise ValueError(f"Unknown adapter '{name}'. Available: {available}")
    return cls()


def list_adapters() -> list[str]:
    """List registered adapter names."""
    return sorted(_ADAPTERS.keys())


def register_adapter(name: str, adapter_cls: type[AgentAdapter]) -> None:
    """Register a custom adapter.

    Learn: This allows teams to add their own adapters without
    modifying the core codebase. Just call:
        register_adapter("my_tool", MyToolAdapter)
    """
    _ADAPTERS[name] = adapter_cls
