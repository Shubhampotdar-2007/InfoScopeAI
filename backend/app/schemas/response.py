"""
Standardized API Response Schemas for consistent JSON envelope.
"""

from typing import Generic, TypeVar, Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict

T = TypeVar("T")


class APIResponse(BaseModel, Generic[T]):
    """Standard unified response wrapper for all API endpoints."""
    success: bool = Field(default=True, description="Indicates whether the request succeeded")
    status_code: int = Field(default=200, description="HTTP status code")
    message: str = Field(default="Success", description="Human-readable result or error message")
    data: Optional[T] = Field(default=None, description="Response payload")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the response"
    )

    model_config = ConfigDict(
        populate_by_name=True,
    )


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None
