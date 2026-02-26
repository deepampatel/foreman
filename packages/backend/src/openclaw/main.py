"""FastAPI application factory.

Learn: App factory pattern — create_app() returns a configured FastAPI
instance. Lifespan manages startup/shutdown (database, Redis, etc.).
Middleware, CORS, and routers all registered here.

Unlike Delegate's 3400-line web.py monolith, this stays clean —
each concern lives in its own module.
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openclaw import __version__
from openclaw.api import api_router
from openclaw.config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle.

    Learn: FastAPI lifespan replaces on_event("startup") / on_event("shutdown").
    Anything before `yield` runs at startup, after `yield` runs at shutdown.
    """
    logger.info(
        "openclaw.starting",
        version=__version__,
        environment=settings.environment,
        port=settings.port,
    )

    # Future phases add:
    # - Alembic auto-migration check
    # - Redis connection pool
    # - Background task dispatcher

    yield

    # Shutdown
    logger.info("openclaw.shutdown")

    # Future: close engine, Redis pool, etc.
    from openclaw.db.engine import engine
    await engine.dispose()


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="OpenClaw Platform",
        description="AI Developer Productivity Platform — management layer for OpenClaw agents",
        version=__version__,
        lifespan=lifespan,
    )

    # CORS — allow frontend dev server
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Alternative frontend port
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routes
    app.include_router(api_router)

    return app


# Default app instance (used by uvicorn: openclaw.main:app)
app = create_app()
