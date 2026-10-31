"""
Health Check Schemas for InfoScope AI Backend.
Note: Health checks indicate server liveness and system metadata; they do not perform or claim user authentication.
"""

from typing import Optional, Dict
from pydantic import BaseModel, Field


class HealthData(BaseModel):
    status: str = Field(default="healthy", description="Current service health status")
    service: str = Field(default="InfoScope AI Backend", description="Service identifier")
    version: str = Field(description="Service semantic version")
    environment: str = Field(description="Current deployment environment (e.g. development, production)")
    uptime_seconds: float = Field(description="Seconds since service startup")
    details: Optional[Dict[str, str]] = Field(
        default_factory=lambda: {
            "api_version": "v1",
            "auth_support": "Supabase JWT",
            "database_target": "Supabase PostgreSQL"
        },
        description="Subsystem status metadata (no authentication claims)"
    )
