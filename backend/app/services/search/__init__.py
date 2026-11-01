"""
Search services package.
"""

from app.services.search.base import (
    BaseSearchProvider,
    NormalizedSource,
    ProviderStatus,
    SearchResponse,
)
from app.services.search.tavily import TavilySearchProvider
from app.services.search.normalizer import canonicalize_url, merge_and_deduplicate_sources
from app.services.search.orchestrator import SearchOrchestrator

__all__ = [
    "BaseSearchProvider",
    "NormalizedSource",
    "ProviderStatus",
    "SearchResponse",
    "TavilySearchProvider",
    "canonicalize_url",
    "merge_and_deduplicate_sources",
    "SearchOrchestrator",
]
