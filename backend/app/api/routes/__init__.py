"""Route registration."""

from fastapi import APIRouter

from backend.app.api.routes import admin, health, notifications, status

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(status.router)
api_router.include_router(admin.router)
api_router.include_router(notifications.router)
