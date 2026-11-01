"""
Tests for InfoScope AI Tavily-Only Search Architecture.
Covers:
1. URL canonicalization and source deduplication.
2. Tavily provider unit tests (success, missing API key, 401 invalid key, 429 rate limit, timeout, empty results, 500 error).
3. Orchestrator unit tests with Tavily as the sole provider.
4. Error handling and provider status diagnostics.
5. End-to-end endpoint /api/v1/research/sessions testing with mocked Tavily search.
"""

import time
import pytest
import httpx
from unittest.mock import AsyncMock, patch

from app.services.search.base import NormalizedSource, BaseSearchProvider, SearchResponse, ProviderStatus
from app.services.search.normalizer import canonicalize_url, merge_and_deduplicate_sources
from app.services.search.tavily import TavilySearchProvider
from app.services.search.orchestrator import SearchOrchestrator
from app.main import app
from app.core.config import settings


# ---------------------------------------------------------------------------
# Unit Tests: URL Canonicalization and Deduplication
# ---------------------------------------------------------------------------

def test_canonicalize_url():
    """Verify URL canonicalization strips tracking params, fragments, and trailing slashes."""
    raw1 = "https://EXAMPLE.COM/articles/llm-agent/?utm_source=twitter&utm_medium=social#heading-1"
    raw2 = "http://example.com:80/articles/llm-agent"
    raw3 = "https://example.com/articles/llm-agent?ref=hackernews"

    c1 = canonicalize_url(raw1)
    c2 = canonicalize_url(raw2)
    c3 = canonicalize_url(raw3)

    assert c1 == "https://example.com/articles/llm-agent"
    assert c2 == "http://example.com/articles/llm-agent"
    assert c3 == "https://example.com/articles/llm-agent"


def test_merge_and_deduplicate_sources():
    """Verify that multiple sources with the same canonical URL are deduplicated and merged."""
    tavily_source = NormalizedSource(
        url="https://example.com/ai-report?utm_source=tavily",
        canonical_url="https://example.com/ai-report",
        title="AI Report 2026 - Comprehensive Review",
        snippet="Short Tavily snippet about AI agents.",
        score=0.92,
        providers=["tavily"],
        metadata={"tavily": {"score": 0.92}}
    )

    custom_source = NormalizedSource(
        url="https://example.com/ai-report#citation-1",
        canonical_url="https://example.com/ai-report",
        title="AI Report 2026",
        snippet="Much longer and more descriptive snippet from custom research target.",
        score=None,
        providers=["user_url"],
        metadata={"source_type": "user_provided"}
    )

    distinct_source = NormalizedSource(
        url="https://arxiv.org/abs/2308.08155",
        canonical_url="https://arxiv.org/abs/2308.08155",
        title="Multi-Agent Breakthroughs",
        snippet="Arxiv paper snippet.",
        score=0.85,
        providers=["tavily"],
        metadata={}
    )

    merged = merge_and_deduplicate_sources([tavily_source, custom_source, distinct_source])

    assert len(merged) == 2

    # Find the merged item
    target = next(s for s in merged if s.canonical_url == "https://example.com/ai-report")
    assert "tavily" in target.providers
    assert "user_url" in target.providers
    # Richer snippet was preserved
    assert "longer and more descriptive" in target.snippet
    # Score was preserved
    assert target.score == 0.92
    # Metadata merged
    assert "tavily" in target.metadata


# ---------------------------------------------------------------------------
# Tavily Provider Unit Tests with Mocked HTTP Responses
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tavily_provider_success():
    """Verify Tavily provider parses results properly."""
    provider = TavilySearchProvider(api_key="tvly-test-key")

    mock_response = {
        "results": [
            {
                "url": "https://docs.infoscope.ai/intro",
                "title": "InfoScope Overview",
                "content": "InfoScope AI is a multi-source gap detection engine.",
                "score": 0.98,
                "published_date": "2026-10-31"
            }
        ]
    }

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = httpx.Response(200, json=mock_response, request=httpx.Request("POST", "https://api.tavily.com/search"))
        mock_post.return_value = mock_resp

        results = await provider.search("InfoScope gap detection", max_results=5)
        assert len(results) == 1
        assert results[0].url == "https://docs.infoscope.ai/intro"
        assert results[0].providers == ["tavily"]
        assert results[0].score == 0.98


@pytest.mark.anyio
async def test_tavily_provider_missing_api_key(monkeypatch):
    """Verify missing or placeholder Tavily API key raises ValueError."""
    monkeypatch.setattr(settings, "TAVILY_API_KEY", "")
    for bad_key in ["", "   ", "tvly-your-api-key-here", None]:
        provider = TavilySearchProvider(api_key=bad_key)
        with pytest.raises(ValueError) as exc_info:
            await provider.search("test query")
        assert "Tavily API key is not configured" in str(exc_info.value)


@pytest.mark.anyio
async def test_tavily_provider_invalid_key_401():
    """Verify HTTP 401 returns clear authentication failed ValueError."""
    provider = TavilySearchProvider(api_key="tvly-invalid-key")
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = httpx.Response(401, json={"detail": "Unauthorized"}, request=httpx.Request("POST", "https://api.tavily.com/search"))
        mock_post.return_value = mock_resp

        with pytest.raises(ValueError) as exc_info:
            await provider.search("test query")
        assert "invalid API key" in str(exc_info.value)


@pytest.mark.anyio
async def test_tavily_provider_rate_limit_429():
    """Verify HTTP 429 returns rate limit exceeded RuntimeError."""
    provider = TavilySearchProvider(api_key="tvly-valid-key")
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = httpx.Response(429, json={"detail": "Too Many Requests"}, request=httpx.Request("POST", "https://api.tavily.com/search"))
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError) as exc_info:
            await provider.search("test query")
        assert "rate limit exceeded" in str(exc_info.value)


@pytest.mark.anyio
async def test_tavily_provider_timeout():
    """Verify timeout exception raises TimeoutError."""
    provider = TavilySearchProvider(api_key="tvly-valid-key", timeout=0.1)
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.side_effect = httpx.TimeoutException("Connection timed out")

        with pytest.raises(TimeoutError) as exc_info:
            await provider.search("test query")
        assert "timed out after" in str(exc_info.value)


@pytest.mark.anyio
async def test_tavily_provider_empty_results():
    """Verify empty or missing results array returns empty NormalizedSource list without error."""
    provider = TavilySearchProvider(api_key="tvly-valid-key")
    for payload in [{"results": []}, {}, {"results": None}]:
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_resp = httpx.Response(200, json=payload, request=httpx.Request("POST", "https://api.tavily.com/search"))
            mock_post.return_value = mock_resp

            results = await provider.search("obscure zero result query")
            assert results == []


@pytest.mark.anyio
async def test_tavily_provider_http_500():
    """Verify HTTP 500 server error raises RuntimeError."""
    provider = TavilySearchProvider(api_key="tvly-valid-key")
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_resp = httpx.Response(500, text="Internal Server Error", request=httpx.Request("POST", "https://api.tavily.com/search"))
        mock_post.return_value = mock_resp

        with pytest.raises(RuntimeError) as exc_info:
            await provider.search("test query")
        assert "HTTP 500" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Orchestrator Tests (Tavily Sole Provider)
# ---------------------------------------------------------------------------

class MockTavilyProvider(BaseSearchProvider):
    def __init__(self, return_sources=None, fail=False, fail_type="runtime", delay=0.0):
        super().__init__("tavily")
        self.return_sources = return_sources or []
        self.fail = fail
        self.fail_type = fail_type
        self.delay = delay

    async def search(self, query: str, max_results: int = 5):
        if self.delay > 0:
            import asyncio
            await asyncio.sleep(self.delay)
        if self.fail:
            if self.fail_type == "timeout":
                raise TimeoutError("Tavily request timed out after 15.0 seconds.")
            elif self.fail_type == "auth":
                raise ValueError("Tavily authentication failed: invalid API key (401).")
            else:
                raise RuntimeError("Tavily API responded with HTTP 500.")
        return self.return_sources[:max_results]


@pytest.mark.anyio
async def test_orchestrator_tavily_success():
    """Verify orchestrator executes Tavily provider and returns normalized SearchResponse."""
    src = NormalizedSource(
        url="https://docs.tavily.com/search",
        canonical_url="https://docs.tavily.com/search",
        title="Tavily Docs",
        snippet="Grounded AI search API.",
        providers=["tavily"]
    )
    provider = MockTavilyProvider(return_sources=[src])
    orchestrator = SearchOrchestrator(tavily_provider=provider)

    response = await orchestrator.execute_search("autonomous agents")

    assert len(response.sources) == 1
    assert response.sources[0].url == "https://docs.tavily.com/search"
    assert "tavily" in response.provider_statuses
    assert response.provider_statuses["tavily"].success is True
    assert response.provider_statuses["tavily"].result_count == 1
    assert "openrouter" not in response.provider_statuses


@pytest.mark.anyio
async def test_orchestrator_tavily_timeout():
    """Verify orchestrator properly captures Tavily timeout and attaches provider statuses."""
    provider = MockTavilyProvider(fail=True, fail_type="timeout")
    orchestrator = SearchOrchestrator(tavily_provider=provider)

    with pytest.raises(RuntimeError) as exc_info:
        await orchestrator.execute_search("slow query")

    err = exc_info.value
    assert "Tavily search provider failed" in str(err)
    assert hasattr(err, "provider_statuses")
    assert err.provider_statuses["tavily"].success is False
    assert "timed out" in err.provider_statuses["tavily"].error_message


@pytest.mark.anyio
async def test_orchestrator_tavily_auth_failure():
    """Verify orchestrator properly handles Tavily authentication error."""
    provider = MockTavilyProvider(fail=True, fail_type="auth")
    orchestrator = SearchOrchestrator(tavily_provider=provider)

    with pytest.raises(RuntimeError) as exc_info:
        await orchestrator.execute_search("auth query")

    err = exc_info.value
    assert "invalid API key" in str(err)
    assert err.provider_statuses["tavily"].success is False


# ---------------------------------------------------------------------------
# API Route Integration Tests with Mocked Tavily Search
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_api_route_creates_session_with_tavily(monkeypatch):
    """
    Verify POST /api/v1/research/sessions uses Tavily as sole provider
    and returns properly formatted session response.
    """
    from httpx import AsyncClient, ASGITransport
    import jwt
    from cryptography.hazmat.primitives.asymmetric import ec
    from app.core.security import set_jwks_client

    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    test_kid = "tavily-sole-kid"
    test_iss = "https://infoscope-test.supabase.co/auth/v1"

    monkeypatch.setattr(settings, "SUPABASE_URL", "https://infoscope-test.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_JWKS_URL", "https://infoscope-test.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setattr(settings, "SUPABASE_JWT_ISSUER", test_iss)
    monkeypatch.setattr(settings, "SUPABASE_JWT_AUDIENCE", "authenticated")

    class MockKey:
        key = public_key
        key_id = test_kid

    class MockJWKClient:
        def get_signing_key_from_jwt(self, t):
            return MockKey()

    set_jwks_client(MockJWKClient(), settings.jwks_url)

    token = jwt.encode(
        {"sub": "user-tavily-audit", "email": "audit@infoscope.ai", "aud": "authenticated", "iss": test_iss, "exp": int(time.time()) + 3600},
        private_key,
        algorithm="ES256",
        headers={"kid": test_kid}
    )

    mock_sources = [
        NormalizedSource(
            url="https://docs.tavily.com/quickstart",
            canonical_url="https://docs.tavily.com/quickstart",
            title="Tavily Quickstart",
            snippet="Getting started with Tavily Search.",
            providers=["tavily"]
        )
    ]

    async def mock_execute_search(self, query, provider_selection="tavily"):
        return SearchResponse(
            query=query,
            sources=mock_sources,
            provider_statuses={
                "tavily": ProviderStatus(provider="tavily", success=True, result_count=1),
            },
            total_raw_results=1,
            deduplicated_count=1
        )

    monkeypatch.setattr(SearchOrchestrator, "execute_search", mock_execute_search)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "research_query": "Compare autonomous AI agents",
                "source_selection": "web"
            }
        )

        assert res.status_code == 202
        data = res.json()["data"]
        assert data["search_provider"] == "tavily"
        assert data["sources_count"] == 1
        assert data["sources"][0]["providers"] == ["tavily"]
        assert "tavily" in data["provider_statuses"]
        assert data["provider_statuses"]["tavily"]["success"] is True
        assert "openrouter" not in data["provider_statuses"]
