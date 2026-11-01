"""
Schemas for Research Sessions and Gap Detection Queries.
Provides strong validation for input queries, source modes, and session responses.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, field_validator


class SourceSelection(str, Enum):
    WEB = "web"
    URLS = "urls"
    BOTH = "both"


class SearchProviderEnum(str, Enum):
    TAVILY = "tavily"


class ResearchSessionBase(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255, description="Optional title for the research session")
    research_query: str = Field(..., min_length=3, max_length=1000, description="The research topic or question to investigate")
    source_selection: SourceSelection = Field(default=SourceSelection.BOTH, description="Information source strategy")
    search_provider: SearchProviderEnum = Field(default=SearchProviderEnum.TAVILY, description="Web search provider strategy: tavily")
    custom_urls: Optional[List[HttpUrl]] = Field(default=[], description="List of validated custom URLs when source is 'urls' or 'both'")

    @field_validator("search_provider", mode="before")
    @classmethod
    def validate_search_provider(cls, v: object) -> str:
        # Sole provider is tavily; coerce any legacy input ('both', 'openrouter') gracefully
        return "tavily"

    @field_validator("custom_urls")
    @classmethod
    def validate_urls_limit(cls, v: Optional[List[HttpUrl]]) -> Optional[List[HttpUrl]]:
        if v and len(v) > 20:
            raise ValueError("A maximum of 20 custom URLs can be analyzed per session.")
        return v


class ResearchSessionCreate(ResearchSessionBase):
    pass


class SourceItemResponse(BaseModel):
    id: Optional[UUID] = None
    session_id: Optional[UUID] = None
    url: str
    canonical_url: str
    title: str
    snippet: Optional[str] = None
    score: Optional[float] = None
    providers: List[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ProviderStatusResponse(BaseModel):
    provider: str
    success: bool
    result_count: int = 0
    latency_seconds: float = 0.0
    error_message: Optional[str] = None


class ResearchSessionResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    research_query: str
    status: str
    search_provider: str = "tavily"
    search_metadata: Optional[dict] = Field(default_factory=dict, description="Search execution metadata and diagnostics")
    summary: Optional[str] = None
    coverage_score: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResearchSessionDetailResponse(ResearchSessionResponse):
    sources: List[SourceItemResponse] = Field(
        default_factory=list,
        description="Persisted sources associated with this research session"
    )


class ResearchSessionStatusResponse(BaseModel):
    session_id: UUID
    id: Optional[UUID] = None
    status: str
    search_stage: Optional[str] = None
    search_metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Search execution metadata and diagnostics")
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResearchSessionUpdate(BaseModel):
    title: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=255,
        description="Updated research session title"
    )

    model_config = ConfigDict(extra="forbid")


# ==============================================================================
# Expected Fields & Coverage Schemas (Stage 3, Phase 3, Step 3)
# ==============================================================================

class ExpectedFieldBase(BaseModel):
    field_name: str = Field(..., min_length=1, max_length=150, description="Name of the expected research dimension")
    field_category: str = Field(default="general", min_length=1, max_length=100, description="Category grouping for the dimension")
    description: Optional[str] = Field(default=None, description="Detailed criteria or questions to answer for this field")
    is_required: bool = Field(default=True, description="Whether this dimension is strictly required")
    weight: float = Field(default=1.00, ge=0.00, le=5.00, description="Completeness weight between 0.00 and 5.00")


class ExpectedFieldCreate(ExpectedFieldBase):
    status: Optional[str] = Field(default="missing", description="Initial coverage status: missing, partially_covered, covered")

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> str:
        if v is not None:
            v_clean = v.strip().lower()
            if v_clean not in ("missing", "partially_covered", "covered"):
                raise ValueError("status must be one of 'missing', 'partially_covered', or 'covered'.")
            return v_clean
        return "missing"


class ExpectedFieldUpdate(BaseModel):
    field_name: Optional[str] = Field(default=None, min_length=1, max_length=150, description="Updated field name")
    description: Optional[str] = Field(default=None, description="Updated description")
    weight: Optional[float] = Field(default=None, ge=0.00, le=5.00, description="Updated weight between 0.00 and 5.00")

    model_config = ConfigDict(extra="forbid")


class ExpectedFieldResponse(BaseModel):
    id: UUID
    session_id: UUID
    user_id: UUID
    field_name: str
    field_category: str = "general"
    description: Optional[str] = None
    is_required: bool = True
    weight: float = 1.00
    status: str = "missing"
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResearchCoverageResponse(BaseModel):
    session_id: UUID
    total_fields: int = 0
    covered_fields: int = 0
    partially_covered_fields: int = 0
    missing_fields: int = 0
    coverage_score: int = Field(default=0, ge=0, le=100, description="Completeness score between 0 and 100")
    total_weight: float = 0.0
    covered_weight: float = 0.0
    fields: List[ExpectedFieldResponse] = Field(default_factory=list, description="Per-field coverage breakdown")

    model_config = ConfigDict(from_attributes=True)

