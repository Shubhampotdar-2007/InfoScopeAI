"""
API Routes Package.
Aggregates all modular route blueprints.
"""

from fastapi import APIRouter
from app.api.routes import health, research

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(research.router)
