"""
Base models and abstractions for search providers.
Defines the common normalized source structure and abstract search interface.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, ConfigDict


class NormalizedSource(BaseModel):
    """Common normalized source representation across all providers."""
    url: str = Field(..., description="Original URL returned by the provider")
    canonical_url: str = Field(..., description="Canonicalized URL used for cross-provider deduplication")
    title: str = Field(default="Untitled Source", description="Source or webpage title")
    snippet: str = Field(default="", description="Snippet, summary, or extracted citation text")
    score: Optional[float] = Field(default=None, description="Relevance or confidence score if available")
    providers: List[str] = Field(default_factory=list, description="List of providers returning this source (e.g. ['tavily'])")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Provider-specific raw metadata, citations, and annotations")

    model_config = ConfigDict(populate_by_name=True)


class ProviderStatus(BaseModel):
    """Execution status and diagnostics for a specific provider."""
    provider: str
    success: bool
    result_count: int = 0
    latency_seconds: float = 0.0
    error_message: Optional[str] = None


class SearchResponse(BaseModel):
    """Consolidated search execution result containing sources and diagnostics."""
    query: str
    sources: List[NormalizedSource] = Field(default_factory=list)
    provider_statuses: Dict[str, ProviderStatus] = Field(default_factory=dict)
    total_raw_results: int = 0
    deduplicated_count: int = 0


class BaseSearchProvider(ABC):
    """Abstract base class for all search providers."""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> List[NormalizedSource]:
        """
        Asynchronously search for sources matching the query.
        Returns a list of NormalizedSource instances.
        Must handle its own error recovery or raise cleanly.
        """
        pass
