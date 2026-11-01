"""
Tavily Search Provider implementation.
Directly communicates with the Tavily Search API and normalizes results.
"""

from typing import List, Optional
import httpx
from app.core.config import settings
from app.services.search.base import BaseSearchProvider, NormalizedSource
from app.services.search.normalizer import canonicalize_url


class TavilySearchProvider(BaseSearchProvider):
    """Integrates with the Tavily Search API for real-time web retrieval."""

    API_URL = "https://api.tavily.com/search"

    def __init__(self, api_key: Optional[str] = None, timeout: Optional[float] = None):
        super().__init__(provider_name="tavily")
        self.api_key = api_key if api_key is not None else settings.TAVILY_API_KEY
        self.timeout = timeout if timeout is not None else (getattr(settings, "TAVILY_TIMEOUT_SECONDS", None) or settings.SEARCH_TIMEOUT_SECONDS)


    async def search(self, query: str, max_results: int = 5) -> List[NormalizedSource]:
        """
        Executes a search via Tavily and returns normalized sources.
        """
        clean_key = (self.api_key or "").strip()
        if not clean_key or clean_key.startswith("tvly-your-"):
            raise ValueError("Tavily API key is not configured. Please set TAVILY_API_KEY in backend/.env.")

        payload = {
            "api_key": clean_key,
            "query": query.strip(),
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {clean_key}",
        }

        try:
            httpx_timeout = httpx.Timeout(self.timeout, connect=min(10.0, float(self.timeout)))
            async with httpx.AsyncClient(timeout=httpx_timeout) as client:
                response = await client.post(self.API_URL, json=payload, headers=headers)
                if response.status_code == 401:
                    raise ValueError("Tavily authentication failed: invalid API key.")
                elif response.status_code == 429:
                    raise RuntimeError("Tavily rate limit exceeded.")
                elif response.status_code >= 400:
                    raise RuntimeError(f"Tavily search API returned HTTP {response.status_code}: {response.text}")

                data = response.json()
        except httpx.TimeoutException as exc:
            raise TimeoutError(f"Tavily request timed out after {self.timeout} seconds.") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Tavily network connection error: {exc}") from exc

        results = data.get("results") or []
        normalized: List[NormalizedSource] = []

        for item in results:
            if not isinstance(item, dict):
                continue
            raw_url = item.get("url")
            if not raw_url:
                continue

            c_url = canonicalize_url(raw_url)
            normalized.append(
                NormalizedSource(
                    url=raw_url,
                    canonical_url=c_url,
                    title=item.get("title") or "Untitled Tavily Result",
                    snippet=item.get("content") or item.get("snippet") or "",
                    score=float(item.get("score")) if item.get("score") is not None else None,
                    providers=["tavily"],
                    metadata={
                        "tavily": {
                            "score": item.get("score"),
                            "published_date": item.get("published_date"),
                        }
                    }
                )
            )

        return normalized

