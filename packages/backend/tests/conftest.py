"""Test fixtures — isolated DB sessions that rollback after each test.

Learn: Testing pattern for async SQLAlchemy + FastAPI + asyncpg:

1. Each test gets its own engine + connection + transaction (function-scoped)
2. The session uses join_transaction_mode="create_savepoint" so that
   when the service layer calls commit(), it creates a SAVEPOINT, not a real commit.
3. After the test, we rollback the outer transaction — all test data vanishes.

This gives us fast, isolated tests without any cross-test pollution.
"""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from openclaw.config import settings
from openclaw.db.engine import get_db
from openclaw.main import app


TEST_DB_URL = settings.database_url


@pytest_asyncio.fixture()
async def db_session():
    """Per-test session with automatic rollback via savepoints.

    Creates a fresh engine+connection+transaction per test.
    join_transaction_mode="create_savepoint" means every session.commit()
    becomes a SAVEPOINT. After the test, the outer transaction rolls back.
    """
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()
    await engine.dispose()


@pytest_asyncio.fixture()
async def client(db_session):
    """HTTP client with the app's get_db overridden to use our test session."""

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
