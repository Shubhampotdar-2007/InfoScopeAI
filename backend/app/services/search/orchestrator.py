"""
Search Orchestrator service.
Executes web retrieval using Tavily as the sole search provider.
Normalizes results, measures latency, and handles errors with detailed diagnostics.
"""

import time
from typing import List, Dict, Optional
from app.core.config import settings
from app.services.search.base import (
    BaseSearchProvider,
    NormalizedSource,
    ProviderStatus,
    SearchResponse,
)
from app.services.search.tavily import TavilySearchProvider
from app.services.search.normalizer import merge_and_deduplicate_sources


class SearchOrchestrator:
    """
    Coordinates web search execution using Tavily as the sole search provider.
    """

    def __init__(
        self,
        tavily_provider: Optional[BaseSearchProvider] = None,
        max_results_per_provider: Optional[int] = None,
        max_total_results: Optional[int] = None,
    ):
        self.tavily = tavily_provider or TavilySearchProvider()
        self.max_results_per_provider = max_results_per_provider or settings.SEARCH_MAX_RESULTS_PER_PROVIDER
        self.max_total_results = max_total_results or settings.SEARCH_MAX_TOTAL_RESULTS

    async def _execute_provider_search(
        self,
        provider: BaseSearchProvider,
        query: str,
        limit: int
    ) -> tuple[str, List[NormalizedSource], ProviderStatus]:
        """Safely executes Tavily search and measures latency and status."""
        start_time = time.time()
        provider_name = provider.provider_name
        try:
            sources = await provider.search(query, max_results=limit)
            latency = round(time.time() - start_time, 3)
            status = ProviderStatus(
                provider=provider_name,
                success=True,
                result_count=len(sources),
                latency_seconds=latency,
                error_message=None
            )
            return provider_name, sources, status
        except Exception as exc:
            latency = round(time.time() - start_time, 3)
            # Mask sensitive API keys in error message if present
            raw_err = str(exc)
            safe_err = self._sanitize_error_message(raw_err)
            status = ProviderStatus(
                provider=provider_name,
                success=False,
                result_count=0,
                latency_seconds=latency,
                error_message=safe_err
            )
            return provider_name, [], status

    @staticmethod
    def _sanitize_error_message(message: str) -> str:
        """Strips out accidental keys or internal sensitive tokens."""
        if not message:
            return "Unknown provider error"
        import re
        sanitized = message
        sanitized = re.sub(r'(tvly-[a-zA-Z0-9_\-]+)', 'tvly-***', sanitized)
        sanitized = re.sub(r'(Bearer\s+[a-zA-Z0-9_\-\.]+)', 'Bearer ***', sanitized)
        return sanitized

    async def execute_search(
        self,
        query: str,
        provider_selection: Optional[str] = "tavily",
    ) -> SearchResponse:
        """
        Executes web search using Tavily as the sole provider.
        """
        provider_statuses: Dict[str, ProviderStatus] = {}

        prov_name, sources, status = await self._execute_provider_search(
            self.tavily, query, self.max_results_per_provider
        )
        provider_statuses[prov_name] = status

        if not status.success:
            err = RuntimeError(f"Tavily search provider failed: {status.error_message}")
            err.provider_statuses = provider_statuses
            raise err

        # Deduplicate and merge sources
        deduplicated = merge_and_deduplicate_sources(
            sources,
            max_total_results=self.max_total_results
        )

        return SearchResponse(
            query=query,
            sources=deduplicated,
            provider_statuses=provider_statuses,
            total_raw_results=len(sources),
            deduplicated_count=len(deduplicated),
        )
