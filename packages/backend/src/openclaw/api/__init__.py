"""API route aggregation.

All routers registered here get mounted in main.py.
"""

from fastapi import APIRouter

from openclaw.api.dispatch import router as dispatch_router
from openclaw.api.git import router as git_router
from openclaw.api.health import router as health_router
from openclaw.api.human_requests import router as human_requests_router
from openclaw.api.reviews import router as reviews_router
from openclaw.api.sessions import router as sessions_router
from openclaw.api.tasks import router as tasks_router
from openclaw.api.teams import router as teams_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router, tags=["health"])
api_router.include_router(teams_router, tags=["teams", "agents", "repos"])
api_router.include_router(tasks_router, tags=["tasks", "messages"])
api_router.include_router(git_router, tags=["git"])
api_router.include_router(sessions_router, tags=["sessions", "costs"])
api_router.include_router(human_requests_router, tags=["human-requests"])
api_router.include_router(reviews_router, tags=["reviews", "merge"])
api_router.include_router(dispatch_router, tags=["dispatch"])
