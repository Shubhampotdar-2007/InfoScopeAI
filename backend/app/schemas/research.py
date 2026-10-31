"""
Schemas for Research Sessions and Gap Detection Queries.
Provides strong validation for input queries, source modes, and session responses.
"""

from enum import Enum
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, field_validator


class SourceSelection(str, Enum):
    WEB = "web"
    URLS = "urls"
    BOTH = "both"


class ResearchSessionBase(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255, description="Optional title for the research session")
    research_query: str = Field(..., min_length=3, max_length=1000, description="The research topic or question to investigate")
    source_selection: SourceSelection = Field(default=SourceSelection.BOTH, description="Information source strategy")
    custom_urls: Optional[List[HttpUrl]] = Field(default=[], description="List of validated custom URLs when source is 'urls' or 'both'")

    @field_validator("custom_urls")
    @classmethod
    def validate_urls_limit(cls, v: Optional[List[HttpUrl]]) -> Optional[List[HttpUrl]]:
        if v and len(v) > 20:
            raise ValueError("A maximum of 20 custom URLs can be analyzed per session.")
        return v


class ResearchSessionCreate(ResearchSessionBase):
    pass


class ResearchSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    research_query: str
    status: str
    summary: Optional[str] = None
    coverage_score: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
