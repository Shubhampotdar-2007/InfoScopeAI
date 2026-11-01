"""
Test Suite for Core Research Repositories (Stage 3, Phase 2, Step 2A).
Tests:
1. ResearchSessionRepository:
   - Creation with verified user_id derivation and zero trust in client IDs.
   - Retrieval by ID (found vs EntityNotFoundError).
   - User-scoped listing with pagination and ordering.
   - Updates (details and status) with anti-tampering sanitization.
   - Deletion.
   - Validation of status and provider values.
2. ResearchSourceRepository:
   - Single source insertion.
   - Batch source insertion.
   - Retrieval by session and by ID.
   - Canonical URL deduplication (database and intra-batch).
   - Composite foreign key error handling (fk_research_sources_session_user).
3. Dependency injection and header verification.
"""

import uuid
import json
import pytest
import jwt
import httpx

from app.core.security import AuthenticatedUser
from app.database import (
    PostgrestClient,
    EntityNotFoundError,
    DatabaseConstraintError,
    DatabaseAuthenticationError,
    ResearchSessionRepository,
    ResearchSourceRepository,
    get_research_session_repository,
    get_research_source_repository,
)


TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
OTHER_USER_ID = "00000000-0000-0000-0000-000000000002"
TEST_ANON_KEY = "anon-key-test"


def create_user_client(user_id: str = TEST_USER_ID, transport: httpx.AsyncBaseTransport = None) -> PostgrestClient:
    """Helper to create a PostgrestClient bound to a verified AuthenticatedUser."""
    token = jwt.encode(
        {"sub": user_id, "role": "authenticated", "aud": "authenticated"},
        "a_super_secret_test_key_at_least_32_bytes_long",
        algorithm="HS256",
    )
    user = AuthenticatedUser(user_id=user_id, email=f"{user_id}@example.com", access_token=token)
    mock_http = httpx.AsyncClient(transport=transport) if transport else None
    return PostgrestClient(
        user=user,
        anon_key=TEST_ANON_KEY,
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )


# ==============================================================================
# 1. ResearchSessionRepository Tests
# ==============================================================================

@pytest.mark.anyio
async def test_session_creation():
    captured_requests = []
    session_id = str(uuid.uuid4())

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        if request.method == "POST" and "research_sessions" in str(request.url):
            data = json.loads(request.content)
            data["id"] = session_id
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(201, json=[data])
        return httpx.Response(400)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSessionRepository(client)

    session = await repo.create_session(
        research_query="Autonomous AI in Healthcare",
        title="Healthcare AI Investigation",
        search_provider="tavily",
        search_metadata={"step": 1},
    )

    assert session["id"] == session_id
    assert session["research_query"] == "Autonomous AI in Healthcare"
    assert session["title"] == "Healthcare AI Investigation"
    assert session["status"] == "pending"
    assert session["user_id"] == TEST_USER_ID

    # Verify request payload & headers
    assert len(captured_requests) == 1
    req = captured_requests[0]
    payload = json.loads(req.content)
    assert payload["user_id"] == TEST_USER_ID  # Strictly derived from user
    assert req.headers["prefer"] == "return=representation"
    assert req.headers["apikey"] == TEST_ANON_KEY
    assert req.headers["authorization"] == f"Bearer {client.access_token}"


@pytest.mark.anyio
async def test_session_creation_validation():
    client = create_user_client()
    repo = ResearchSessionRepository(client)

    # Empty query
    with pytest.raises(ValueError, match="research_query cannot be empty"):
        await repo.create_session(research_query="   ")

    # Invalid status
    with pytest.raises(ValueError, match="Invalid session status"):
        await repo.create_session(research_query="Valid", status="unknown_status")

    # Invalid provider
    with pytest.raises(ValueError, match="Invalid search provider"):
        await repo.create_session(research_query="Valid", search_provider="unsupported_provider")


@pytest.mark.anyio
async def test_session_retrieval_and_not_found():
    session_id = str(uuid.uuid4())
    mock_record = {
        "id": session_id,
        "user_id": TEST_USER_ID,
        "research_query": "Quantum Computing",
        "title": "Quantum",
        "status": "pending",
    }

    def mock_handler(request: httpx.Request):
        url = str(request.url)
        if f"id=eq.{session_id}" in url and f"user_id=eq.{TEST_USER_ID}" in url:
            return httpx.Response(200, json=[mock_record])
        return httpx.Response(200, json=[])

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSessionRepository(client)

    # Found
    session = await repo.get_session(session_id)
    assert session["id"] == session_id
    assert session["user_id"] == TEST_USER_ID

    # Optional found
    opt_session = await repo.get_session_optional(session_id)
    assert opt_session is not None

    # Not found raises EntityNotFoundError
    with pytest.raises(EntityNotFoundError):
        await repo.get_session(str(uuid.uuid4()))

    # Optional not found returns None
    assert await repo.get_session_optional(str(uuid.uuid4())) is None


@pytest.mark.anyio
async def test_user_scoped_session_listing():
    captured_requests = []
    records = [{"id": str(uuid.uuid4()), "user_id": TEST_USER_ID, "title": f"S{i}"} for i in range(3)]

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        return httpx.Response(200, json=records)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSessionRepository(client)

    results = await repo.list_user_sessions(status="completed", limit=10, offset=5, order="created_at.desc")

    assert len(results) == 3
    assert len(captured_requests) == 1
    url = str(captured_requests[0].url)
    assert f"user_id=eq.{TEST_USER_ID}" in url
    assert "status=eq.completed" in url
    assert "limit=10" in url
    assert "offset=5" in url
    assert "order=created_at.desc" in url


@pytest.mark.anyio
async def test_session_update_and_anti_tampering():
    session_id = str(uuid.uuid4())
    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        data = json.loads(request.content)
        data["id"] = session_id
        data["user_id"] = TEST_USER_ID
        return httpx.Response(200, json=[data])

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSessionRepository(client)

    # Attempt to tamper with user_id or id in payload
    updated = await repo.update_session(
        session_id,
        {
            "title": "Legitimate Title Update",
            "coverage_score": 90,
            "user_id": OTHER_USER_ID,  # Must be stripped!
            "id": str(uuid.uuid4()),    # Must be stripped!
        },
    )

    assert updated["title"] == "Legitimate Title Update"
    assert len(captured_requests) == 1
    sent_payload = json.loads(captured_requests[0].content)
    assert "user_id" not in sent_payload  # Stripped
    assert "id" not in sent_payload        # Stripped
    assert sent_payload["title"] == "Legitimate Title Update"
    assert sent_payload["coverage_score"] == 90

    # Test update_session_status convenience method
    status_updated = await repo.update_session_status(
        session_id,
        status="completed",
        summary="Executive Summary",
        coverage_score=95,
    )
    assert status_updated is not None


@pytest.mark.anyio
async def test_session_deletion():
    session_id = str(uuid.uuid4())
    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        url = str(request.url)
        if f"id=eq.{session_id}" in url and f"user_id=eq.{TEST_USER_ID}" in url:
            return httpx.Response(200, json=[{"id": session_id}])
        return httpx.Response(200, json=[])

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSessionRepository(client)

    # Successful deletion
    deleted = await repo.delete_session(session_id)
    assert deleted["id"] == session_id

    # Not found deletion raises EntityNotFoundError
    with pytest.raises(EntityNotFoundError):
        await repo.delete_session(str(uuid.uuid4()))


# ==============================================================================
# 2. ResearchSourceRepository Tests
# ==============================================================================

@pytest.mark.anyio
async def test_source_insertion():
    session_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        data = json.loads(request.content)
        data["id"] = source_id
        return httpx.Response(201, json=[data])

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSourceRepository(client)

    source = await repo.insert_source(
        session_id=session_id,
        source={
            "url": "https://example.com/ai-report?utm=1",
            "canonical_url": "https://example.com/ai-report",
            "title": "AI Report 2026",
            "snippet": "Key insights on AI agents.",
            "score": 0.95,
            "providers": ["tavily"],
            "metadata": {"source_type": "web"},
        },
    )

    assert source["id"] == source_id
    assert source["session_id"] == session_id
    assert source["user_id"] == TEST_USER_ID
    assert source["canonical_url"] == "https://example.com/ai-report"

    # Verify payload
    payload = json.loads(captured_requests[0].content)
    assert payload["session_id"] == session_id
    assert payload["user_id"] == TEST_USER_ID  # Strictly bound


@pytest.mark.anyio
async def test_source_batch_insertion():
    session_id = str(uuid.uuid4())
    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        items = json.loads(request.content)
        for i, item in enumerate(items):
            item["id"] = str(uuid.uuid4())
        return httpx.Response(201, json=items)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSourceRepository(client)

    batch_sources = [
        {"url": f"https://example.com/doc/{i}", "title": f"Doc {i}"}
        for i in range(3)
    ]

    inserted = await repo.insert_sources_batch(session_id, batch_sources)
    assert len(inserted) == 3
    assert all(s["session_id"] == session_id for s in inserted)
    assert all(s["user_id"] == TEST_USER_ID for s in inserted)

    # Empty batch returns [] without HTTP call
    assert await repo.insert_sources_batch(session_id, []) == []
    assert len(captured_requests) == 1


@pytest.mark.anyio
async def test_sources_retrieval_by_session_and_id():
    session_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())
    mock_sources = [
        {"id": source_id, "session_id": session_id, "user_id": TEST_USER_ID, "title": "Source 1"},
        {"id": str(uuid.uuid4()), "session_id": session_id, "user_id": TEST_USER_ID, "title": "Source 2"},
    ]

    def mock_handler(request: httpx.Request):
        url = str(request.url)
        if f"id=eq.{source_id}" in url:
            return httpx.Response(200, json=[mock_sources[0]])
        if f"session_id=eq.{session_id}" in url:
            return httpx.Response(200, json=mock_sources)
        return httpx.Response(200, json=[])

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSourceRepository(client)

    # List by session
    results = await repo.get_sources_by_session(session_id, limit=10)
    assert len(results) == 2

    # Get by ID
    single = await repo.get_source_by_id(source_id, session_id=session_id)
    assert single["id"] == source_id

    # Not found raises EntityNotFoundError
    with pytest.raises(EntityNotFoundError):
        await repo.get_source_by_id(str(uuid.uuid4()))


@pytest.mark.anyio
async def test_canonical_url_deduplication():
    session_id = str(uuid.uuid4())

    existing_sources = [
        {"canonical_url": "https://example.com/already-stored-1"},
        {"canonical_url": "https://example.com/already-stored-2"},
    ]
    captured_batch_inserts = []

    def mock_handler(request: httpx.Request):
        url = str(request.url)
        if request.method == "GET" and "select=canonical_url" in url:
            return httpx.Response(200, json=existing_sources)
        if request.method == "POST":
            items = json.loads(request.content)
            captured_batch_inserts.extend(items)
            return httpx.Response(201, json=items)
        return httpx.Response(400)

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSourceRepository(client)

    # 1. Existing URLs retrieval
    existing_set = await repo.get_existing_canonical_urls(session_id)
    assert "https://example.com/already-stored-1" in existing_set
    assert "https://example.com/already-stored-2" in existing_set

    # 2. Ingest batch with:
    #   - 1 already in DB
    #   - 1 new URL
    #   - 1 duplicate of the new URL within the same batch (intra-batch duplicate)
    batch = [
        {"url": "https://example.com/already-stored-1", "title": "Old Source"},
        {"url": "https://example.com/brand-new", "canonical_url": "https://example.com/brand-new", "title": "New 1"},
        {"url": "https://example.com/brand-new?ref=duplicate", "canonical_url": "https://example.com/brand-new", "title": "New 1 Dup"},
    ]

    inserted = await repo.insert_sources_deduplicated(session_id, batch)

    # Only 1 unique new source must be inserted!
    assert len(inserted) == 1
    assert inserted[0]["canonical_url"] == "https://example.com/brand-new"
    assert len(captured_batch_inserts) == 1

    # 3. If all sources already exist, no insert is performed
    all_duplicate_batch = [
        {"url": "https://example.com/already-stored-1"},
        {"url": "https://example.com/already-stored-2"},
    ]
    res = await repo.insert_sources_deduplicated(session_id, all_duplicate_batch)
    assert res == []


@pytest.mark.anyio
async def test_composite_foreign_key_error_handling():
    """
    Tests handling of PostgreSQL composite foreign key violation
    fk_research_sources_session_user when referencing a session that doesn't exist or belongs to another user.
    """
    foreign_session_id = str(uuid.uuid4())

    def mock_handler(request: httpx.Request):
        # PostgREST returns 409 Conflict with Postgres code 23503 for foreign key violation
        return httpx.Response(
            409,
            json={
                "code": "23503",
                "message": 'insert or update on table "research_sources" violates foreign key constraint "fk_research_sources_session_user"',
                "details": f'Key (session_id, user_id)=({foreign_session_id}, {TEST_USER_ID}) is not present in table "research_sessions".',
            },
        )

    client = create_user_client(transport=httpx.MockTransport(mock_handler))
    repo = ResearchSourceRepository(client)

    with pytest.raises(DatabaseConstraintError) as exc_info:
        await repo.insert_source(
            session_id=foreign_session_id,
            source={"url": "https://example.com/forbidden", "title": "Forbidden Source"},
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.details == {"code": "23503"}
    assert "referenced database record does not exist" in str(exc_info.value.message).lower()


# ==============================================================================
# 3. Dependency Injection & Repository Initialization Tests
# ==============================================================================

def test_repository_dependency_injection():
    client = create_user_client()

    session_repo = get_research_session_repository(client)
    assert isinstance(session_repo, ResearchSessionRepository)
    assert session_repo.user_id == TEST_USER_ID
    assert session_repo.table_name == "research_sessions"

    source_repo = get_research_source_repository(client)
    assert isinstance(source_repo, ResearchSourceRepository)
    assert source_repo.user_id == TEST_USER_ID
    assert source_repo.table_name == "research_sources"


def test_repository_unauthenticated_client_rejection():
    # If client has no user and no access_token
    unauthenticated_client = PostgrestClient.__new__(PostgrestClient)
    unauthenticated_client.user = None
    unauthenticated_client.access_token = None

    with pytest.raises(DatabaseAuthenticationError):
        ResearchSessionRepository(unauthenticated_client)

    with pytest.raises(DatabaseAuthenticationError):
        ResearchSourceRepository(unauthenticated_client)
