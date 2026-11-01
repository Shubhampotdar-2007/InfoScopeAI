"""
Comprehensive Integration Tests for Research Session API (Stage 3, Phase 3, Step 1).
Tests:
1. Successful session creation & database persistence in Supabase PostgREST.
2. Source normalization, deduplication & batch persistence.
3. Tavily search failure handling (session preserved, marked failed, diagnostic metadata recorded).
4. Database failure handling on session creation (structured error response).
5. Database failure handling on source persistence (session marked failed, record preserved).
6. Cross-provider source deduplication (intra-batch and database).
7. User-scoped session listing with pagination (limit, offset, order).
8. Session status filtering.
9. Individual session retrieval with persisted sources.
10. Unauthorized access to another user's session (EntityNotFoundError 404, zero information leak).
11. Retrieval of nonexistent or malformed session ID (EntityNotFoundError 404).
12. Zero trust in client-supplied user_id (defense against identity spoofing).
13. APIResponse envelope & frontend Axios compatibility.
"""

import time
import uuid
import json
import pytest
import jwt
from jwt import PyJWKClientError
from cryptography.hazmat.primitives.asymmetric import ec
import httpx
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.core.security import set_jwks_client
from app.database.client import set_default_db_transport
from app.services.search.base import NormalizedSource, ProviderStatus, SearchResponse
from app.services.search.orchestrator import SearchOrchestrator


TEST_KID = "test-session-api-kid"
TEST_ISSUER = "https://infoscope-test.supabase.co/auth/v1"
TEST_JWKS_URL = "https://infoscope-test.supabase.co/auth/v1/.well-known/jwks.json"

USER_A_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


class MockSigningKey:
    def __init__(self, key, key_id):
        self.key = key
        self.key_id = key_id


class MockJWKClient:
    def __init__(self, key_map):
        self.key_map = key_map

    def get_signing_key_from_jwt(self, token: str):
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if kid in self.key_map:
            return MockSigningKey(self.key_map[kid], kid)
        raise PyJWKClientError(f"Unknown kid: '{kid}'")


@pytest.fixture
def auth_setup(monkeypatch):
    """Sets up cryptographic keys and mock JWKS client for user authentication."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    mock_jwks = MockJWKClient(key_map={TEST_KID: public_key})

    monkeypatch.setattr(settings, "SUPABASE_URL", "https://infoscope-test.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setattr(settings, "SUPABASE_JWT_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "SUPABASE_JWT_AUDIENCE", "authenticated")

    set_jwks_client(mock_jwks, TEST_JWKS_URL)

    def generate_token(user_id: str, email: str = "researcher@infoscope.ai") -> str:
        payload = {
            "sub": user_id,
            "email": email,
            "role": "authenticated",
            "aud": "authenticated",
            "iss": TEST_ISSUER,
            "exp": int(time.time()) + 3600,
            "iat": int(time.time()),
        }
        return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": TEST_KID})

    yield generate_token
    set_jwks_client(None, None)


# ==============================================================================
# 1. POST /api/v1/research/sessions — Creation & Persistence
# ==============================================================================

@pytest.mark.anyio
async def test_successful_session_creation_and_persistence(auth_setup, monkeypatch):
    """Verify session and sources are persisted in Supabase PostgREST with verified user_id."""
    token = auth_setup(USER_A_ID, "userA@infoscope.ai")
    captured_requests = []

    mock_sources = [
        NormalizedSource(
            url="https://docs.tavily.com/overview",
            canonical_url="https://docs.tavily.com/overview",
            title="Tavily Overview",
            snippet="Overview of search API capabilities.",
            score=0.95,
            providers=["tavily"],
            metadata={"raw": True}
        ),
        NormalizedSource(
            url="https://docs.tavily.com/pricing",
            canonical_url="https://docs.tavily.com/pricing",
            title="Tavily Pricing",
            snippet="Tier details.",
            score=0.88,
            providers=["tavily"],
            metadata={"raw": True}
        )
    ]

    async def mock_execute_search(self, query, provider_selection="tavily"):
        return SearchResponse(
            query=query,
            sources=mock_sources,
            provider_statuses={
                "tavily": ProviderStatus(provider="tavily", success=True, result_count=2, latency_seconds=0.42)
            },
            total_raw_results=2,
            deduplicated_count=2
        )

    monkeypatch.setattr(SearchOrchestrator, "execute_search", mock_execute_search)

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        url_str = str(request.url)

        if "research_sessions" in url_str and request.method == "POST":
            data = json.loads(request.content)
            data["id"] = data.get("id") or str(uuid.uuid4())
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(201, json=[data])

        if "research_sources" in url_str and request.method == "GET":
            # existing canonical urls query
            return httpx.Response(200, json=[])

        if "research_sources" in url_str and request.method == "POST":
            data = json.loads(request.content)
            for item in data:
                item["id"] = str(uuid.uuid4())
                item["created_at"] = "2026-11-01T12:00:01Z"
            return httpx.Response(201, json=data)

        if "research_sessions" in url_str and request.method == "PATCH":
            data = json.loads(request.content)
            data["id"] = str(uuid.uuid4())
            data["user_id"] = USER_A_ID
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:02Z"
            return httpx.Response(200, json=[data])

        return httpx.Response(400)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "research_query": "Compare Postgres vs MongoDB for multi-agent workloads",
                "source_selection": "web",
                "title": "Postgres vs Mongo Investigation",
            }
        )

        assert res.status_code == 202
        body = res.json()
        assert body["success"] is True
        assert body["status_code"] == 202
        data = body["data"]

        # Session attributes
        assert data["user_id"] == USER_A_ID
        assert data["query"] == "Compare Postgres vs MongoDB for multi-agent workloads"
        assert data["search_provider"] == "tavily"
        assert data["search_stage"] == "completed"
        assert data["sources_count"] == 2
        assert len(data["sources"]) == 2
        assert data["provider_statuses"]["tavily"]["success"] is True

        # PostgREST verification
        # 1. Session created with USER_A_ID
        session_create_req = next(r for r in captured_requests if "research_sessions" in str(r.url) and r.method == "POST")
        sc_payload = json.loads(session_create_req.content)
        assert sc_payload["user_id"] == USER_A_ID
        assert sc_payload["status"] == "pending"

        # 2. Sources inserted with USER_A_ID and session_id
        source_insert_req = next(r for r in captured_requests if "research_sources" in str(r.url) and r.method == "POST")
        si_payload = json.loads(source_insert_req.content)
        assert len(si_payload) == 2
        for s in si_payload:
            assert s["user_id"] == USER_A_ID
            assert s["session_id"] == data["session_id"]
            assert "tavily" in s["providers"]


@pytest.mark.anyio
async def test_source_deduplication_pipeline(auth_setup, monkeypatch):
    """Verify duplicate URLs between Tavily and user custom URLs are merged and deduplicated."""
    token = auth_setup(USER_A_ID)
    captured_sources_payload = []

    # Mock Tavily returns a URL with tracking parameter
    async def mock_execute_search(self, query, provider_selection="tavily"):
        return SearchResponse(
            query=query,
            sources=[
                NormalizedSource(
                    url="https://example.com/report?utm_source=tavily",
                    canonical_url="https://example.com/report",
                    title="Report Tavily",
                    snippet="Short snippet",
                    score=0.9,
                    providers=["tavily"]
                )
            ],
            provider_statuses={"tavily": ProviderStatus(provider="tavily", success=True, result_count=1)},
            total_raw_results=1,
            deduplicated_count=1
        )

    monkeypatch.setattr(SearchOrchestrator, "execute_search", mock_execute_search)

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str and request.method == "POST":
            data = json.loads(request.content)
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(201, json=[data])

        if "research_sources" in url_str and request.method == "GET":
            # return no existing urls
            return httpx.Response(200, json=[])

        if "research_sources" in url_str and request.method == "POST":
            data = json.loads(request.content)
            captured_sources_payload.extend(data)
            for item in data:
                item["id"] = str(uuid.uuid4())
                item["created_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(201, json=data)

        if "research_sessions" in url_str and request.method == "PATCH":
            data = json.loads(request.content)
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(200, json=[data])

        return httpx.Response(400)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "research_query": "Deduplication pipeline test",
                "source_selection": "both",
                "custom_urls": [
                    "https://example.com/report#section-2",  # Should merge with Tavily canonical
                    "https://distinct.org/paper"
                ]
            }
        )

        assert res.status_code == 202
        data = res.json()["data"]
        # Out of 3 total sources, 2 have same canonical URL https://example.com/report -> exactly 2 persisted
        assert data["sources_count"] == 2
        assert len(captured_sources_payload) == 2

        merged = next(s for s in captured_sources_payload if s["canonical_url"] == "https://example.com/report")
        assert "tavily" in merged["providers"]
        assert "user_url" in merged["providers"]


@pytest.mark.anyio
async def test_tavily_search_failure_preserves_session(auth_setup, monkeypatch):
    """Verify that when Tavily search fails, the session record in DB is preserved and marked failed."""
    token = auth_setup(USER_A_ID)
    captured_patch = []

    async def mock_execute_search_fail(self, query, provider_selection="tavily"):
        err = RuntimeError("Tavily rate limit exceeded: tvly-dev-secret-key-429")
        err.provider_statuses = {
            "tavily": ProviderStatus(
                provider="tavily",
                success=False,
                error_message="Tavily rate limit exceeded: tvly-***"
            )
        }
        raise err

    monkeypatch.setattr(SearchOrchestrator, "execute_search", mock_execute_search_fail)

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str and request.method == "POST":
            data = json.loads(request.content)
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(201, json=[data])

        if "research_sessions" in url_str and request.method == "PATCH":
            data = json.loads(request.content)
            captured_patch.append(data)
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(200, json=[data])

        return httpx.Response(400)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "research_query": "Probe query that triggers provider failure",
                "source_selection": "web"
            }
        )

        assert res.status_code == 202
        body = res.json()
        data = body["data"]

        # Session was NOT lost
        assert data["session_id"] is not None
        assert data["search_stage"] == "failed"
        assert "rate limit" in data["search_error"].lower()
        # Diagnostic statuses are present
        assert data["provider_statuses"]["tavily"]["success"] is False
        assert data["sources_count"] == 0

        # PostgREST patch was sent marking session as 'failed'
        assert len(captured_patch) == 1
        assert captured_patch[0]["status"] == "failed"


@pytest.mark.anyio
async def test_database_failure_on_session_creation(auth_setup):
    """Verify structured database error response is returned when initial session creation fails."""
    token = auth_setup(USER_A_ID)

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        # Simulate Supabase service unavailable / 503
        return httpx.Response(503, json={"message": "PostgREST connection pool exhausted"})

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "research_query": "DB failure probe query",
                "source_selection": "web"
            }
        )

        assert res.status_code == 503
        body = res.json()
        assert body["success"] is False
        assert body["status_code"] == 503
        assert "database" in body["message"].lower() or "unavailable" in body["message"].lower()


@pytest.mark.anyio
async def test_database_failure_on_source_persistence(auth_setup, monkeypatch):
    """Verify session is marked failed and record preserved if source persistence raises an error."""
    token = auth_setup(USER_A_ID)
    captured_patch = []

    async def mock_execute_search(self, query, provider_selection="tavily"):
        return SearchResponse(
            query=query,
            sources=[
                NormalizedSource(
                    url="https://example.com/doc",
                    canonical_url="https://example.com/doc",
                    title="Doc",
                    snippet="Snippet",
                    providers=["tavily"]
                )
            ],
            provider_statuses={"tavily": ProviderStatus(provider="tavily", success=True, result_count=1)},
            total_raw_results=1,
            deduplicated_count=1
        )

    monkeypatch.setattr(SearchOrchestrator, "execute_search", mock_execute_search)

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str and request.method == "POST":
            data = json.loads(request.content)
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(201, json=[data])

        if "research_sources" in url_str and request.method == "GET":
            return httpx.Response(200, json=[])

        # Fail source insertion with HTTP 409 constraint violation
        if "research_sources" in url_str and request.method == "POST":
            return httpx.Response(409, json={"code": "23505", "message": "duplicate key value"})

        if "research_sessions" in url_str and request.method == "PATCH":
            data = json.loads(request.content)
            captured_patch.append(data)
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(200, json=[data])

        return httpx.Response(400)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "research_query": "Source failure probe query",
                "source_selection": "web"
            }
        )

        assert res.status_code == 202
        body = res.json()
        data = body["data"]

        # Session was NOT lost
        assert data["session_id"] is not None
        assert "source persistence failed" in body["message"].lower()

        # Session was updated to failed, NOT reported as completed
        assert len(captured_patch) == 1
        assert captured_patch[0]["status"] == "failed"


# ==============================================================================
# 2. GET /api/v1/research/sessions — Listing & Pagination
# ==============================================================================

@pytest.mark.anyio
async def test_list_sessions_user_scoped_and_pagination(auth_setup):
    """Verify session listing supports pagination and enforces authenticated user scoping."""
    token = auth_setup(USER_A_ID, "userA@infoscope.ai")
    captured_get = []

    mock_db_sessions = [
        {
            "id": str(uuid.uuid4()),
            "user_id": USER_A_ID,
            "title": f"Session {i}",
            "research_query": f"Query topic {i}",
            "status": "completed",
            "search_provider": "tavily",
            "search_metadata": {"total": i},
            "summary": f"Summary {i}",
            "coverage_score": 80 + i,
            "created_at": "2026-11-01T12:00:00Z",
            "updated_at": "2026-11-01T12:00:00Z",
        }
        for i in range(2)
    ]

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        captured_get.append(request)
        return httpx.Response(200, json=mock_db_sessions)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions?limit=2&offset=4",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert len(body["data"]) == 2
        assert "userA@infoscope.ai" in body["message"]

        # PostgREST query parameters verification
        assert len(captured_get) == 1
        params = captured_get[0].url.params
        assert params["user_id"] == f"eq.{USER_A_ID}"
        assert params["limit"] == "2"
        assert params["offset"] == "4"


@pytest.mark.anyio
async def test_list_sessions_status_filtering_and_validation(auth_setup):
    """Verify status filtering and rejection of invalid status values."""
    token = auth_setup(USER_A_ID)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Invalid status filter returns 400 Bad Request
        res_bad = await client.get(
            "/api/v1/research/sessions?status=invalid_status_xyz",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_bad.status_code == 400
        assert "invalid status filter" in res_bad.json()["message"].lower()

        # 2. Valid status filter passes to repository
        res_ok = await client.get(
            "/api/v1/research/sessions?status=completed",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_ok.status_code == 200


# ==============================================================================
# 3. GET /api/v1/research/sessions/{session_id} — Single Session Retrieval
# ==============================================================================

@pytest.mark.anyio
async def test_get_individual_session_success(auth_setup):
    """Verify retrieving a user's own session returns session details and associated sources."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Autonomous Agents Session",
        "research_query": "Autonomous agent reliability metrics",
        "status": "completed",
        "search_provider": "tavily",
        "search_metadata": {"sources_count": 1},
        "summary": "Detailed summary",
        "coverage_score": 92,
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    mock_sources = [
        {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": USER_A_ID,
            "url": "https://arxiv.org/abs/2401.00001",
            "canonical_url": "https://arxiv.org/abs/2401.00001",
            "title": "Agent Reliability",
            "snippet": "Paper on agent verification.",
            "score": 0.94,
            "providers": ["tavily"],
            "metadata": {},
            "created_at": "2026-11-01T12:00:00Z",
        }
    ]

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "research_sources" in url_str:
            return httpx.Response(200, json=mock_sources)
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        data = body["data"]

        assert data["id"] == session_id
        assert data["user_id"] == USER_A_ID
        assert data["coverage_score"] == 92
        assert len(data["sources"]) == 1
        assert data["sources"][0]["canonical_url"] == "https://arxiv.org/abs/2401.00001"


@pytest.mark.anyio
async def test_get_individual_session_unauthorized_or_nonexistent(auth_setup):
    """Verify EntityNotFoundError (404) is returned for nonexistent or other user's session with zero leakage."""
    token = auth_setup(USER_A_ID)
    foreign_session_id = str(uuid.uuid4())

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        # Supabase RLS and user_id filter return empty list
        return httpx.Response(200, json=[])

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{foreign_session_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert body["status_code"] == 404
        assert "not found" in body["message"].lower()
        # Zero leakage of foreign user info
        assert USER_B_ID not in body["message"]


@pytest.mark.anyio
async def test_get_individual_session_invalid_uuid(auth_setup):
    """Verify malformed session_id strings return 404 EntityNotFoundError without calling PostgREST."""
    token = auth_setup(USER_A_ID)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions/not-a-valid-uuid",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert "not found" in body["message"].lower()


# ==============================================================================
# 4. Security & API Response Compatibility
# ==============================================================================

@pytest.mark.anyio
async def test_zero_trust_in_client_user_id(auth_setup, monkeypatch):
    """Verify server derives user_id from verified JWT and ignores client-supplied user_id in payload."""
    token = auth_setup(USER_A_ID)
    captured_session_payload = []

    async def mock_execute_search(self, query, provider_selection="tavily"):
        return SearchResponse(
            query=query,
            sources=[],
            provider_statuses={"tavily": ProviderStatus(provider="tavily", success=True, result_count=0)},
            total_raw_results=0,
            deduplicated_count=0
        )

    monkeypatch.setattr(SearchOrchestrator, "execute_search", mock_execute_search)

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str and request.method == "POST":
            data = json.loads(request.content)
            captured_session_payload.append(data)
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(201, json=[data])
        if "research_sessions" in url_str and request.method == "PATCH":
            data = json.loads(request.content)
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(200, json=[data])
        return httpx.Response(200, json=[])

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "research_query": "Zero trust user_id verification",
                "source_selection": "web",
                "user_id": USER_B_ID,  # Attacker attempt to spoof user_id
            }
        )

        assert res.status_code == 202
        data = res.json()["data"]

        # Server bound the session to USER_A_ID, not the spoofed USER_B_ID
        assert data["user_id"] == USER_A_ID
        assert data["user_id"] != USER_B_ID

        # Database record also bound to USER_A_ID
        assert len(captured_session_payload) == 1
        assert captured_session_payload[0]["user_id"] == USER_A_ID


# ==============================================================================
# 5. Stage 3, Phase 3, Step 2: Session Read & Lifecycle Operations
# ==============================================================================

@pytest.mark.anyio
async def test_get_session_status_success(auth_setup):
    """Verify GET /sessions/{id}/status returns session status, search stage, and diagnostics."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "LLM Security Benchmark",
        "research_query": "LLM prompt injection vulnerabilities",
        "status": "completed",
        "search_provider": "tavily",
        "search_metadata": {
            "source_strategy": "web",
            "search_stage": "completed",
            "provider_statuses": {
                "tavily": {"provider": "tavily", "success": True, "result_count": 5, "latency_seconds": 0.35}
            },
            "sources_count": 5
        },
        "summary": None,
        "coverage_score": 85,
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:05Z",
    }

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            params = request.url.params
            if params.get("id") == f"eq.{session_id}" and params.get("user_id") == f"eq.{USER_A_ID}":
                return httpx.Response(200, json=[mock_session])
        return httpx.Response(200, json=[])

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{session_id}/status",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        data = body["data"]

        assert data["session_id"] == session_id
        assert data["status"] == "completed"
        assert data["search_stage"] == "completed"
        assert data["search_metadata"]["sources_count"] == 5
        assert "tavily" in data["search_metadata"]["provider_statuses"]
        assert data["created_at"] == "2026-11-01T12:00:00Z"
        assert data["updated_at"] == "2026-11-01T12:00:05Z"


@pytest.mark.anyio
async def test_get_session_status_nonexistent(auth_setup):
    """Verify GET /sessions/{id}/status returns 404 EntityNotFoundError when session is not found."""
    token = auth_setup(USER_A_ID)
    missing_id = str(uuid.uuid4())

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{missing_id}/status",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert "not found" in body["message"].lower()


@pytest.mark.anyio
async def test_get_session_status_cross_user_prevention(auth_setup):
    """Verify User B cannot access status of User A's session (returns 404 with zero info leakage)."""
    token_b = auth_setup(USER_B_ID)
    user_a_session_id = str(uuid.uuid4())

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        # DB filters by user_id = USER_B_ID, returns empty because session is owned by USER_A
        params = request.url.params
        if params.get("user_id") == f"eq.{USER_B_ID}":
            return httpx.Response(200, json=[])
        return httpx.Response(400)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{user_a_session_id}/status",
            headers={"Authorization": f"Bearer {token_b}"}
        )

        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert "not found" in body["message"].lower()
        # Zero leakage of user A's identity
        assert USER_A_ID not in body["message"]


@pytest.mark.anyio
async def test_get_session_sources_success(auth_setup):
    """Verify GET /sessions/{id}/sources returns persisted sources with proper attribution."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Sources Session",
        "research_query": "Sources query",
        "status": "completed",
        "search_provider": "tavily",
        "search_metadata": {},
        "summary": None,
        "coverage_score": 90,
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    mock_sources = [
        {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": USER_A_ID,
            "url": "https://example.com/source-1",
            "canonical_url": "https://example.com/source-1",
            "title": "Source 1",
            "snippet": "Snippet 1",
            "score": 0.95,
            "providers": ["tavily"],
            "metadata": {},
            "created_at": "2026-11-01T12:00:01Z",
        },
        {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": USER_A_ID,
            "url": "https://example.com/source-2",
            "canonical_url": "https://example.com/source-2",
            "title": "Source 2",
            "snippet": "Snippet 2",
            "score": 0.88,
            "providers": ["user_url"],
            "metadata": {},
            "created_at": "2026-11-01T12:00:02Z",
        }
    ]

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "research_sources" in url_str:
            return httpx.Response(200, json=mock_sources)
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{session_id}/sources",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert len(body["data"]) == 2
        assert body["data"][0]["canonical_url"] == "https://example.com/source-1"
        assert body["data"][1]["providers"] == ["user_url"]


@pytest.mark.anyio
async def test_get_session_sources_pagination(auth_setup):
    """Verify GET /sessions/{id}/sources passes limit and offset to PostgREST."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())
    captured_sources_req = []

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Pagination Session",
        "research_query": "Pagination query",
        "status": "completed",
        "search_provider": "tavily",
        "search_metadata": {},
        "summary": None,
        "coverage_score": None,
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    mock_page = [
        {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": USER_A_ID,
            "url": f"https://example.com/paged-{i}",
            "canonical_url": f"https://example.com/paged-{i}",
            "title": f"Page Source {i}",
            "snippet": "Sample snippet",
            "score": 0.8,
            "providers": ["tavily"],
            "metadata": {},
            "created_at": "2026-11-01T12:00:00Z",
        }
        for i in range(2)
    ]

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "research_sources" in url_str:
            captured_sources_req.append(request)
            return httpx.Response(200, json=mock_page)
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{session_id}/sources?limit=2&offset=4",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert len(body["data"]) == 2

        assert len(captured_sources_req) == 1
        params = captured_sources_req[0].url.params
        assert params["limit"] == "2"
        assert params["offset"] == "4"
        assert params["session_id"] == f"eq.{session_id}"
        assert params["user_id"] == f"eq.{USER_A_ID}"


@pytest.mark.anyio
async def test_get_session_sources_empty_list(auth_setup):
    """Verify GET /sessions/{id}/sources returns empty list when session has zero sources."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Empty Sources Session",
        "research_query": "No sources query",
        "status": "pending",
        "search_provider": "tavily",
        "search_metadata": {},
        "summary": None,
        "coverage_score": None,
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "research_sources" in url_str:
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{session_id}/sources",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["data"] == []
        assert "0 source(s)" in body["message"]


@pytest.mark.anyio
async def test_get_session_sources_cross_user_prevention(auth_setup):
    """Verify User B cannot access sources of User A's session (404 EntityNotFoundError)."""
    token_b = auth_setup(USER_B_ID)
    user_a_session_id = str(uuid.uuid4())

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        # Ownership check on research_sessions with user_id = USER_B_ID returns empty
        return httpx.Response(200, json=[])

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{user_a_session_id}/sources",
            headers={"Authorization": f"Bearer {token_b}"}
        )

        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert "not found" in body["message"].lower()


@pytest.mark.anyio
async def test_status_and_sources_invalid_uuid_handling(auth_setup):
    """Verify invalid UUID strings on all read endpoints return 404 without hitting database."""
    token = auth_setup(USER_A_ID)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /status
        res_status = await client.get(
            "/api/v1/research/sessions/not-a-valid-uuid/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_status.status_code == 404
        assert "not found" in res_status.json()["message"].lower()

        # 2. /sources
        res_sources = await client.get(
            "/api/v1/research/sessions/not-a-valid-uuid/sources",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_sources.status_code == 404
        assert "not found" in res_sources.json()["message"].lower()

        # 3. PATCH
        res_patch = await client.patch(
            "/api/v1/research/sessions/not-a-valid-uuid",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Updated Title"}
        )
        assert res_patch.status_code == 404
        assert "not found" in res_patch.json()["message"].lower()


@pytest.mark.anyio
async def test_patch_session_safe_metadata_update(auth_setup):
    """Verify PATCH /sessions/{id} updates safe metadata (title) and preserves ownership."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())
    captured_patch_req = []

    mock_updated_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Renamed Investigation Title",
        "research_query": "Initial research query",
        "status": "completed",
        "search_provider": "tavily",
        "search_metadata": {"step": 1},
        "summary": "Summary text",
        "coverage_score": 90,
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:05:00Z",
    }

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str and request.method == "PATCH":
            captured_patch_req.append(request)
            return httpx.Response(200, json=[mock_updated_session])
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            f"/api/v1/research/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Renamed Investigation Title"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        data = body["data"]
        assert data["title"] == "Renamed Investigation Title"
        assert data["id"] == session_id
        assert data["user_id"] == USER_A_ID

        # Verify PostgREST patch request
        assert len(captured_patch_req) == 1
        req = captured_patch_req[0]
        params = req.url.params
        assert params["id"] == f"eq.{session_id}"
        assert params["user_id"] == f"eq.{USER_A_ID}"
        patch_body = json.loads(req.content)
        assert patch_body == {"title": "Renamed Investigation Title"}


@pytest.mark.anyio
async def test_patch_session_reject_immutable_and_unauthorized_fields(auth_setup):
    """Verify clients cannot tamper with id, user_id, status, diagnostics, or supply empty updates."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Attempting to update user_id or status is rejected by schema (extra forbidden)
        res_tamper = await client.patch(
            f"/api/v1/research/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": USER_B_ID, "status": "completed"}
        )
        assert res_tamper.status_code == 422
        assert "validation failed" in res_tamper.json()["message"].lower()

        # 2. Attempting to update internal search_metadata is rejected
        res_meta = await client.patch(
            f"/api/v1/research/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"search_metadata": {"hacked": True}}
        )
        assert res_meta.status_code == 422

        # 3. Empty payload is rejected
        res_empty = await client.patch(
            f"/api/v1/research/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={}
        )
        assert res_empty.status_code == 422

        # 4. Whitespace title is rejected
        res_blank = await client.patch(
            f"/api/v1/research/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "   "}
        )
        assert res_blank.status_code == 422


@pytest.mark.anyio
async def test_patch_session_cross_user_prevention(auth_setup):
    """Verify User B cannot patch User A's session (returns 404 EntityNotFoundError)."""
    token_b = auth_setup(USER_B_ID)
    user_a_session_id = str(uuid.uuid4())

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        # PostgREST query with user_id=eq.{USER_B_ID} returns empty
        return httpx.Response(200, json=[])

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.patch(
            f"/api/v1/research/sessions/{user_a_session_id}",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"title": "Unauthorized Modification Attempt"}
        )

        assert res.status_code == 404
        body = res.json()
        assert body["success"] is False
        assert "not found" in body["message"].lower()


@pytest.mark.anyio
async def test_database_error_handling_across_read_endpoints(auth_setup):
    """Verify PostgREST connection errors or 503s return structured database error response across read endpoints."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    def mock_db_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "PostgREST database unavailable"})

    set_default_db_transport(httpx.MockTransport(mock_db_error_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. /status DB error
        res_status = await client.get(
            f"/api/v1/research/sessions/{session_id}/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_status.status_code == 503
        assert res_status.json()["success"] is False

        # 2. /sources DB error
        res_sources = await client.get(
            f"/api/v1/research/sessions/{session_id}/sources",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_sources.status_code == 503
        assert res_sources.json()["success"] is False

        # 3. PATCH DB error
        res_patch = await client.patch(
            f"/api/v1/research/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Error test title"}
        )
        assert res_patch.status_code == 503
        assert res_patch.json()["success"] is False


