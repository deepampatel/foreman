"""Application configuration via environment variables.

Uses pydantic-settings to load config from env vars with OPENCLAW_ prefix.
No YAML files, no file-based config — just env vars (12-factor app style).

Learn: pydantic-settings auto-loads from environment, validates types,
provides defaults. Much cleaner than Delegate's YAML config.py.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All app configuration. Set via OPENCLAW_* env vars."""

    # Database
    database_url: str = (
        "postgresql+asyncpg://openclaw:openclaw_dev@localhost:5433/openclaw"
    )

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic API (for built-in agent runner)
    anthropic_api_key: str = ""

    # Auth
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # Server
    environment: str = "development"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8000

    # Agent defaults
    default_agent_model: str = "claude-sonnet-4-20250514"
    max_concurrent_agents: int = 32

    model_config = {"env_prefix": "OPENCLAW_"}


# Singleton — import this everywhere
settings = Settings()
