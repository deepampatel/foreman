"""Async SQLAlchemy engine and session factory.

Learn: SQLAlchemy 2.0 async mode — create_async_engine for connection pooling,
AsyncSession for per-request database access, dependency injection via FastAPI.

Unlike Delegate's raw sqlite3.connect() calls scattered everywhere, we have
one engine with connection pooling and proper session lifecycle.
"""

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from openclaw.config import settings

# Connection pool: min 5, max 20 connections.
# echo=True in dev to see SQL queries.
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=15,
)

# Session factory — each request gets its own session.
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a session per request, auto-closes."""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
