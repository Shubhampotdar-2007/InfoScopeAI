"""
Test Suite for Database Foundation Layer (Stage 3, Phase 2, Step 1).
Tests:
1. Verified JWT access-token propagation to AuthenticatedUser.
2. Safe access-token representation (no leak in __repr__).
3. Correct apikey (anon) and Authorization (Bearer <user_token>) headers in PostgrestClient.
4. Prevention of accidental service-role key usage (as access token, anon key, or config fallback).
5. HTTP connection reuse across queries and graceful cleanup on close.
6. Successful PostgREST responses parsing.
7. Empty response handling (empty list, 204 No Content).
8. HTTP 401 and 403 error handling -> DatabaseAuthenticationError.
9. HTTP 404 error handling -> EntityNotFoundError.
10. HTTP 409 conflict and PostgreSQL Class 23 constraint error handling -> DatabaseConstraintError.
11. Malformed JSON and server error handling -> DatabaseError.
12. BaseRepository CRUD operations (insert, insert_many, get_by_id, list, update, delete, count).
13. BaseRepository identifier and query parameter safety validation.
"""

import time
import uuid
import json
import pytest
import jwt
from cryptography.hazmat.primitives.asymmetric import ec
import httpx

from app.core.config import settings
from app.core.security import (
    AuthenticatedUser,
    get_current_user,
    set_jwks_client,
)
from app.database import (
    DatabaseError,
    EntityNotFoundError,
    DatabaseConstraintError,
    DatabaseAuthenticationError,
    PostgrestClient,
    get_db_http_client,
    close_db_http_client,
    is_service_role_key,
    BaseRepository,
)
from app.database.repositories.base import validate_identifier, format_filter_value


TEST_KID = "test-database-es256-kid"
TEST_ISSUER = "https://test-db.supabase.co/auth/v1"
TEST_JWKS_URL = "https://test-db.supabase.co/auth/v1/.well-known/jwks.json"
TEST_ANON_KEY = "dummy-anon-key-not-service-role"


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
        raise jwt.PyJWKClientError(f"Unable to find key with kid: '{kid}'")


@pytest.fixture
def ec_key_pair():
    """Generates an Elliptic Curve P-256 key pair for ES256 tests."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def mock_jwks(ec_key_pair, monkeypatch):
    """Sets up settings and in-memory MockJWKClient."""
    _, public_key = ec_key_pair
    client = MockJWKClient(key_map={TEST_KID: public_key})
    set_jwks_client(client, TEST_JWKS_URL)

    monkeypatch.setattr(settings, "SUPABASE_URL", "https://test-db.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setattr(settings, "SUPABASE_JWT_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "SUPABASE_JWT_AUDIENCE", "authenticated")
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", TEST_ANON_KEY)

    yield client

    set_jwks_client(None, None)


def create_signed_token(private_key, user_id="user-123", email="user@example.com", expires_in=3600):
    now = int(time.time())
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "iss": TEST_ISSUER,
        "role": "authenticated",
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": TEST_KID})


# ==============================================================================
# 1. AuthenticatedUser Token Retention & No Leak
# ==============================================================================

def test_authenticated_user_access_token_retention():
    secret_token = "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCJ9.dummy_token_secret"
    user = AuthenticatedUser(
        user_id="user-xyz-456",
        email="test@example.com",
        role="authenticated",
        access_token=secret_token,
    )
    assert user.user_id == "user-xyz-456"
    assert user.access_token == secret_token
    # Crucial security check: Token must never be leaked in __repr__
    repr_str = repr(user)
    assert secret_token not in repr_str
    assert "user-xyz-456" in repr_str


@pytest.mark.anyio
async def test_verified_jwt_access_token_propagation(ec_key_pair, mock_jwks):
    """Verifies get_current_user retains the verified access token and sub claim."""
    private_key, _ = ec_key_pair
    token = create_signed_token(private_key, user_id="sub-verified-999", email="verified@example.com")

    from fastapi.security import HTTPAuthorizationCredentials
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    user = await get_current_user(creds)
    assert user.user_id == "sub-verified-999"
    assert user.email == "verified@example.com"
    assert user.access_token == token
    assert token not in repr(user)


# ==============================================================================
# 2. Correct apikey & Authorization Headers
# ==============================================================================

@pytest.mark.anyio
async def test_postgrest_client_correct_headers():
    captured_requests = []

    def mock_handler(request: httpx.Request):
        captured_requests.append(request)
        return httpx.Response(200, json=[{"id": "rec-1"}])

    mock_transport = httpx.MockTransport(mock_handler)
    mock_http = httpx.AsyncClient(transport=mock_transport)

    client = PostgrestClient(
        access_token="user-jwt-token-abc",
        anon_key="anon-key-123",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    await client.get("research_sessions")

    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req.headers["apikey"] == "anon-key-123"
    assert req.headers["authorization"] == "Bearer user-jwt-token-abc"
    assert req.headers["accept"] == "application/json"
    assert str(req.url) == "https://test.supabase.co/rest/v1/research_sessions"

    # Test POST adds Content-Type
    await client.post("research_sessions", json={"query": "test query"})
    assert len(captured_requests) == 2
    post_req = captured_requests[1]
    assert post_req.headers["content-type"] == "application/json"
    assert post_req.headers["apikey"] == "anon-key-123"
    assert post_req.headers["authorization"] == "Bearer user-jwt-token-abc"

    # Repr must not expose credentials
    assert "user-jwt-token-abc" not in repr(client)
    assert "anon-key-123" not in repr(client)

    await mock_http.aclose()


# ==============================================================================
# 3. Prevention of Accidental Service-Role Key Use
# ==============================================================================

def test_service_role_key_detection():
    service_role_payload = {"role": "service_role", "sub": "admin-1"}
    test_hmac_secret = "a_super_secret_test_key_at_least_32_bytes_long"
    service_role_jwt = jwt.encode(service_role_payload, test_hmac_secret, algorithm="HS256")

    anon_payload = {"role": "anon", "sub": "anon-1"}
    anon_jwt = jwt.encode(anon_payload, test_hmac_secret, algorithm="HS256")

    user_payload = {"role": "authenticated", "sub": "user-1"}
    user_jwt = jwt.encode(user_payload, test_hmac_secret, algorithm="HS256")

    assert is_service_role_key(service_role_jwt) is True
    assert is_service_role_key(anon_jwt) is False
    assert is_service_role_key(user_jwt) is False
    assert is_service_role_key(None) is False
    assert is_service_role_key("invalid-token") is False


def test_reject_service_role_as_access_token():
    test_hmac_secret = "a_super_secret_test_key_at_least_32_bytes_long"
    service_role_payload = {"role": "service_role", "sub": "admin"}
    service_role_jwt = jwt.encode(service_role_payload, test_hmac_secret, algorithm="HS256")

    with pytest.raises(DatabaseAuthenticationError) as exc_info:
        PostgrestClient(
            access_token=service_role_jwt,
            anon_key="valid-anon-key",
            base_url="https://test.supabase.co/rest/v1",
        )
    assert "service-role" in str(exc_info.value).lower()


def test_reject_service_role_as_anon_key():
    test_hmac_secret = "a_super_secret_test_key_at_least_32_bytes_long"
    service_role_payload = {"role": "service_role", "sub": "admin"}
    service_role_jwt = jwt.encode(service_role_payload, test_hmac_secret, algorithm="HS256")

    with pytest.raises(DatabaseAuthenticationError) as exc_info:
        PostgrestClient(
            access_token="valid-user-token",
            anon_key=service_role_jwt,
            base_url="https://test.supabase.co/rest/v1",
        )
    assert "service-role" in str(exc_info.value).lower()


def test_config_prevents_silent_service_role_fallback(monkeypatch):
    test_hmac_secret = "a_super_secret_test_key_at_least_32_bytes_long"
    service_role_jwt = jwt.encode({"role": "service_role"}, test_hmac_secret, algorithm="HS256")

    # If SUPABASE_ANON_KEY is not set and SUPABASE_KEY is a service-role key:
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", "")
    monkeypatch.setattr(settings, "SUPABASE_KEY", service_role_jwt)

    # settings.supabase_anon_key must NOT return the service role key
    assert settings.supabase_anon_key == ""

    # If SUPABASE_ANON_KEY is set to a service-role key, it must be rejected
    monkeypatch.setattr(settings, "SUPABASE_ANON_KEY", service_role_jwt)
    assert settings.supabase_anon_key == ""


def test_missing_access_token_raises_auth_error():
    with pytest.raises(DatabaseAuthenticationError):
        PostgrestClient(
            access_token="",
            anon_key="valid-anon",
            base_url="https://test.supabase.co/rest/v1",
        )


# ==============================================================================
# 4. Connection Reuse and Cleanup
# ==============================================================================

@pytest.mark.anyio
async def test_connection_reuse_and_cleanup():
    client1 = get_db_http_client()
    client2 = get_db_http_client()

    # Reusable connection pool - same client instance
    assert client1 is client2
    assert not client1.is_closed

    # Cleanup
    await close_db_http_client()
    assert client1.is_closed

    # New client created after closing
    client3 = get_db_http_client()
    assert client3 is not client1
    assert not client3.is_closed
    await close_db_http_client()


# ==============================================================================
# 5. Successful Database Responses & Empty Responses
# ==============================================================================

@pytest.mark.anyio
async def test_successful_responses():
    sample_data = [{"id": "1", "title": "Session 1"}, {"id": "2", "title": "Session 2"}]

    def mock_handler(request: httpx.Request):
        return httpx.Response(200, json=sample_data)

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="token",
        anon_key="anon",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    data = await client.get("research_sessions")
    assert data == sample_data
    await mock_http.aclose()


@pytest.mark.anyio
async def test_empty_responses():
    def mock_handler(request: httpx.Request):
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json=[])

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="token",
        anon_key="anon",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    # Empty list
    get_res = await client.get("research_sessions")
    assert get_res == []

    # 204 No Content
    del_res = await client.delete("research_sessions")
    assert del_res is None

    await mock_http.aclose()


# ==============================================================================
# 6. HTTP 401 and 403 Handling
# ==============================================================================

@pytest.mark.anyio
async def test_http_401_handling():
    def mock_handler(request: httpx.Request):
        return httpx.Response(401, json={"message": "JWT expired"})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="token",
        anon_key="anon",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    with pytest.raises(DatabaseAuthenticationError) as exc_info:
        await client.get("research_sessions")
    assert exc_info.value.status_code == 401
    await mock_http.aclose()


@pytest.mark.anyio
async def test_http_403_handling():
    def mock_handler(request: httpx.Request):
        return httpx.Response(403, json={"message": "permission denied for table research_sessions"})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="token",
        anon_key="anon",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    with pytest.raises(DatabaseAuthenticationError) as exc_info:
        await client.get("research_sessions")
    assert exc_info.value.status_code == 403
    await mock_http.aclose()


# ==============================================================================
# 7. HTTP 404 and 409 Handling
# ==============================================================================

@pytest.mark.anyio
async def test_http_404_handling():
    def mock_handler(request: httpx.Request):
        return httpx.Response(404, json={"message": "table not found"})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="token",
        anon_key="anon",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    with pytest.raises(EntityNotFoundError) as exc_info:
        await client.get("unknown_table")
    assert exc_info.value.status_code == 404
    await mock_http.aclose()


@pytest.mark.anyio
async def test_http_409_handling():
    def mock_handler(request: httpx.Request):
        return httpx.Response(
            409,
            json={
                "code": "23505",
                "message": 'duplicate key value violates unique constraint "idx_user_query"',
                "details": "Key (user_id, research_query)=(...) already exists.",
            },
        )

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="token",
        anon_key="anon",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    with pytest.raises(DatabaseConstraintError) as exc_info:
        await client.post("research_sessions", json={"query": "duplicate"})
    assert exc_info.value.status_code == 409
    assert exc_info.value.details == {"code": "23505"}
    await mock_http.aclose()


# ==============================================================================
# 8. Database Constraint Errors (Class 23 SQLSTATE)
# ==============================================================================

@pytest.mark.anyio
@pytest.mark.parametrize(
    "pg_code,expected_msg_substring",
    [
        ("23505", "unique"),
        ("23503", "exist"),
        ("23502", "null"),
        ("23514", "check constraint"),
    ],
)
async def test_database_constraint_error_codes(pg_code, expected_msg_substring):
    def mock_handler(request: httpx.Request):
        return httpx.Response(
            400,
            json={"code": pg_code, "message": "Constraint violation", "details": "detail text"},
        )

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="token",
        anon_key="anon",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    with pytest.raises(DatabaseConstraintError) as exc_info:
        await client.post("test_table", json={"val": "invalid"})
    assert exc_info.value.status_code == 409
    assert expected_msg_substring.lower() in exc_info.value.message.lower()
    await mock_http.aclose()


# ==============================================================================
# 9. Malformed Responses and Server Errors
# ==============================================================================

@pytest.mark.anyio
async def test_malformed_json_response():
    def mock_handler(request: httpx.Request):
        return httpx.Response(200, content=b"Malformed Non-JSON Content")

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="token",
        anon_key="anon",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    with pytest.raises(DatabaseError) as exc_info:
        await client.get("test_table")
    assert "malformed" in str(exc_info.value).lower()
    await mock_http.aclose()


@pytest.mark.anyio
async def test_server_error_response():
    def mock_handler(request: httpx.Request):
        return httpx.Response(500, json={"message": "Postgres crash"})

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="token",
        anon_key="anon",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )

    with pytest.raises(DatabaseError) as exc_info:
        await client.get("test_table")
    assert exc_info.value.status_code == 500
    await mock_http.aclose()


# ==============================================================================
# 10. Base Repository CRUD Operations
# ==============================================================================

@pytest.mark.anyio
async def test_base_repository_crud():
    sample_id = str(uuid.uuid4())
    created_record = {"id": sample_id, "title": "Test Title", "status": "pending"}

    def mock_handler(request: httpx.Request):
        method = request.method
        url = str(request.url)

        if method == "POST":
            assert request.headers.get("prefer") == "return=representation"
            data = json.loads(request.content)
            if isinstance(data, list):
                return httpx.Response(201, json=data)
            return httpx.Response(201, json=[created_record])

        elif method == "GET":
            if f"id=eq.{sample_id}" in url:
                return httpx.Response(200, json=[created_record])
            if "id=eq.missing-id" in url:
                return httpx.Response(200, json=[])
            if "limit=0" in url:
                return httpx.Response(200, headers={"Content-Range": "*/25"}, json=[])
            return httpx.Response(200, json=[created_record])

        elif method == "PATCH":
            assert request.headers.get("prefer") == "return=representation"
            if f"id=eq.{sample_id}" in url:
                updated = dict(created_record)
                updated.update(json.loads(request.content))
                return httpx.Response(200, json=[updated])
            return httpx.Response(200, json=[])

        elif method == "DELETE":
            assert request.headers.get("prefer") == "return=representation"
            if f"id=eq.{sample_id}" in url:
                return httpx.Response(200, json=[created_record])
            return httpx.Response(200, json=[])

        return httpx.Response(400)

    mock_http = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))
    client = PostgrestClient(
        access_token="user-token",
        anon_key="anon-key",
        base_url="https://test.supabase.co/rest/v1",
        http_client=mock_http,
    )
    repo = BaseRepository(client=client, table_name="research_sessions")

    # 1. Insert
    inserted = await repo.insert({"title": "Test Title", "status": "pending"})
    assert inserted["id"] == sample_id
    assert inserted["title"] == "Test Title"

    # 2. Insert Many
    batch = await repo.insert_many([{"title": "B1"}, {"title": "B2"}])
    assert len(batch) == 2

    # 3. Get by ID
    fetched = await repo.get_by_id(sample_id)
    assert fetched["id"] == sample_id

    # 4. Get by ID (not found) -> EntityNotFoundError
    with pytest.raises(EntityNotFoundError):
        await repo.get_by_id("missing-id")

    # 5. Get by ID Optional
    assert await repo.get_by_id_optional(sample_id) is not None
    assert await repo.get_by_id_optional("missing-id") is None

    # 6. List with filters, limit, offset, order
    results = await repo.list(
        filters={"status": "pending", "title": "eq.Test Title"},
        limit=10,
        offset=0,
        order="created_at.desc",
    )
    assert len(results) == 1

    # 7. Update
    updated = await repo.update(sample_id, {"status": "completed"})
    assert updated["status"] == "completed"

    with pytest.raises(EntityNotFoundError):
        await repo.update("missing-id", {"status": "completed"})

    # 8. Delete
    deleted = await repo.delete(sample_id)
    assert deleted["id"] == sample_id

    with pytest.raises(EntityNotFoundError):
        await repo.delete("missing-id")

    # 9. Count
    total_count = await repo.count(filters={"status": "pending"})
    assert total_count == 25

    await mock_http.aclose()


# ==============================================================================
# 11. Identifier Validation & Query Parameter Safety
# ==============================================================================

def test_identifier_validation():
    # Valid identifiers
    assert validate_identifier("research_sessions") == "research_sessions"
    assert validate_identifier("user_id") == "user_id"
    assert validate_identifier("col_123") == "col_123"

    # Invalid identifiers (SQL injection prevention)
    with pytest.raises(ValueError):
        validate_identifier("table; DROP TABLE users;--")

    with pytest.raises(ValueError):
        validate_identifier("table name with spaces")

    with pytest.raises(ValueError):
        validate_identifier("123startswithnumber")

    with pytest.raises(ValueError):
        validate_identifier("user-id")

    with pytest.raises(ValueError):
        validate_identifier("")


def test_format_filter_values():
    assert format_filter_value(None) == "is.null"
    assert format_filter_value(True) == "eq.true"
    assert format_filter_value(False) == "eq.false"
    assert format_filter_value(42) == "eq.42"
    assert format_filter_value(3.14) == "eq.3.14"
    assert format_filter_value("pending") == "eq.pending"
    assert format_filter_value("eq.pending") == "eq.pending"
    assert format_filter_value("neq.failed") == "neq.failed"
    assert format_filter_value(["a", "b", "c"]) == "in.(a,b,c)"
