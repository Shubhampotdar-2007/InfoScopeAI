"""
Health and Diagnostic API Route.
Provides system uptime, environment info, and service health status.
Does not perform or require user authentication.
"""

import time
from fastapi import APIRouter, status
from app.schemas.response import APIResponse
from app.schemas.health import HealthData
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["Health & Status"])

# Application start time marker for calculating server uptime
START_TIME = time.time()


@router.get(
    "",
    response_model=APIResponse[HealthData],
    status_code=status.HTTP_200_OK,
    summary="Service Health Check",
    description="Returns backend service health status, version, uptime, and environment metadata. (Public endpoint, does not authenticate users)."
)
async def check_health() -> APIResponse[HealthData]:
    """Health check endpoint providing uptime and operational state."""
    uptime = round(time.time() - START_TIME, 2)
    health_payload = HealthData(
        status="healthy",
        service=settings.PROJECT_NAME,
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        uptime_seconds=uptime,
        details={
            "api_prefix": settings.API_V1_STR,
            "auth_strategy": "Supabase JWT",
            "cors_configured": "true",
            "debug_mode": str(settings.DEBUG).lower()
        }
    )

    return APIResponse(
        success=True,
        status_code=status.HTTP_200_OK,
        message="InfoScope AI backend is operational.",
        data=health_payload
    )
