"""API route aggregation.

All routers registered here get mounted in main.py.
"""

from fastapi import APIRouter

from openclaw.api.health import router as health_router
from openclaw.api.tasks import router as tasks_router
from openclaw.api.teams import router as teams_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(teams_router, tags=["teams", "agents", "repos"])
api_router.include_router(tasks_router, tags=["tasks", "messages"])

# Future phases add more routers:
# api_router.include_router(events_router, tags=["events"])
# etc.
