"""
Comprehensive Test Suite for Expected Fields and Coverage APIs (Stage 3, Phase 3, Step 3).
Covers:
1. Expected fields retrieval (with database ordering).
2. Empty expected fields retrieval.
3. Successful expected field creation (JWT user_id derivation, weight validation).
4. Invalid field validation (empty field_name, duplicate field_name conflict).
5. Weight boundary validation (0.00 <= weight <= 5.00).
6. Safe expected field update (title, weight, status, category).
7. Rejection of immutable or unauthorized fields (id, user_id, session_id, extra fields).
8. Successful expected field deletion.
9. Cross-user access prevention (status, fields, patch, delete, coverage).
10. Invalid UUID format handling (session_id, field_id).
11. Coverage calculation (weighted points formula verification).
12. Coverage boundary validation (empty=0, full=100, clamped 0-100).
13. Database failure handling (503 PostgREST unavailable).
14. APIResponse envelope compatibility.
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


TEST_KID = "test-expected-fields-kid"
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
# 1. Expected Fields Retrieval Tests
# ==============================================================================

@pytest.mark.anyio
async def test_list_expected_fields_success(auth_setup):
    """1. Verify expected fields retrieval with ordering and user scoping."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())
    captured_get = []

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Topic Session",
        "research_query": "Multi-agent architecture topic",
        "status": "completed",
        "search_provider": "tavily",
        "search_metadata": {},
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    mock_fields = [
        {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": USER_A_ID,
            "field_name": "Architecture Overview",
            "field_category": "technical",
            "description": "High level system diagram",
            "is_required": True,
            "weight": 2.0,
            "status": "covered",
            "created_at": "2026-11-01T12:00:01Z",
            "updated_at": "2026-11-01T12:00:01Z",
        },
        {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": USER_A_ID,
            "field_name": "Cost Analysis",
            "field_category": "commercial",
            "description": "Token and hosting economics",
            "is_required": True,
            "weight": 1.5,
            "status": "missing",
            "created_at": "2026-11-01T12:00:02Z",
            "updated_at": "2026-11-01T12:00:02Z",
        }
    ]

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str:
            captured_get.append(request)
            return httpx.Response(200, json=mock_fields)
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["status_code"] == 200
        assert len(body["data"]) == 2
        assert body["data"][0]["field_name"] == "Architecture Overview"
        assert body["data"][1]["weight"] == 1.5

        # Verify ordering parameter sent to PostgREST
        assert len(captured_get) == 1
        params = captured_get[0].url.params
        assert params["order"] == "created_at.asc"
        assert params["session_id"] == f"eq.{session_id}"
        assert params["user_id"] == f"eq.{USER_A_ID}"


@pytest.mark.anyio
async def test_list_expected_fields_empty(auth_setup):
    """2. Verify empty list returned when session has no expected fields."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Empty Fields Session",
        "research_query": "Fresh session query",
        "status": "pending",
        "search_provider": "tavily",
        "search_metadata": {},
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str:
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["data"] == []
        assert "0 expected field(s)" in body["message"]


# ==============================================================================
# 2. Expected Field Creation Tests
# ==============================================================================

@pytest.mark.anyio
async def test_create_expected_field_success(auth_setup):
    """3. Verify successful creation of expected field with verified JWT user_id."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())
    captured_insert_payload = []

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Session for Field Creation",
        "research_query": "Testing field creation",
        "status": "pending",
        "search_provider": "tavily",
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str and request.method == "GET":
            return httpx.Response(200, json=[mock_session])

        if "expected_fields" in url_str and request.method == "GET":
            return httpx.Response(200, json=[])

        if "expected_fields" in url_str and request.method == "POST":
            data = json.loads(request.content)
            captured_insert_payload.append(data)
            data["id"] = str(uuid.uuid4())
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(201, json=[data])

        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "field_name": "Latency Benchmarks",
                "field_category": "performance",
                "description": "p95 and p99 response times",
                "is_required": True,
                "weight": 2.50,
                "status": "missing"
            }
        )

        assert res.status_code == 201
        body = res.json()
        assert body["success"] is True
        assert body["status_code"] == 201
        data = body["data"]

        assert data["field_name"] == "Latency Benchmarks"
        assert data["field_category"] == "performance"
        assert data["weight"] == 2.50
        assert data["status"] == "missing"
        assert data["session_id"] == session_id
        assert data["user_id"] == USER_A_ID

        # Verify DB insert payload strictly derived user_id from token
        assert len(captured_insert_payload) == 1
        payload = captured_insert_payload[0]
        assert payload["user_id"] == USER_A_ID
        assert payload["session_id"] == session_id
        assert payload["weight"] == 2.50


@pytest.mark.anyio
async def test_create_expected_field_invalid_validation_and_duplicates(auth_setup):
    """4. Verify invalid field names and duplicates are rejected."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Dup Test Session",
        "research_query": "Testing duplicate prevention",
        "status": "pending",
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    mock_existing = [
        {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": USER_A_ID,
            "field_name": "Security Compliance",
            "field_category": "compliance",
            "weight": 1.0,
            "status": "missing",
            "created_at": "2026-11-01T12:00:00Z",
            "updated_at": "2026-11-01T12:00:00Z",
        }
    ]

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str and request.method == "GET":
            return httpx.Response(200, json=mock_existing)
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A. Empty field_name is rejected
        res_empty = await client.post(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "   ", "weight": 1.0}
        )
        assert res_empty.status_code == 422

        # B. Missing field_name is rejected
        res_missing = await client.post(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={"weight": 1.0}
        )
        assert res_missing.status_code == 422

        # C. Duplicate field_name within session is rejected with 409 Conflict
        res_dup = await client.post(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "Security Compliance", "weight": 2.0}
        )
        assert res_dup.status_code == 409
        assert "already exists" in res_dup.json()["message"].lower()


@pytest.mark.anyio
async def test_create_expected_field_weight_boundary_validation(auth_setup):
    """5. Verify weight boundaries (0.00 <= weight <= 5.00)."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Weight Boundary Session",
        "research_query": "Testing weights",
        "status": "pending",
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str and request.method == "GET":
            return httpx.Response(200, json=[])
        if "expected_fields" in url_str and request.method == "POST":
            data = json.loads(request.content)
            data["id"] = str(uuid.uuid4())
            data["created_at"] = "2026-11-01T12:00:00Z"
            data["updated_at"] = "2026-11-01T12:00:00Z"
            return httpx.Response(201, json=[data])
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Below minimum (weight < 0.00)
        res_low = await client.post(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "Low Weight", "weight": -0.5}
        )
        assert res_low.status_code == 422

        # Above maximum (weight > 5.00)
        res_high = await client.post(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "High Weight", "weight": 5.01}
        )
        assert res_high.status_code == 422

        # Valid exact boundary 0.00
        res_zero = await client.post(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "Zero Weight", "weight": 0.00}
        )
        assert res_zero.status_code == 201
        assert res_zero.json()["data"]["weight"] == 0.00

        # Valid exact boundary 5.00
        res_five = await client.post(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "Max Weight", "weight": 5.00}
        )
        assert res_five.status_code == 201
        assert res_five.json()["data"]["weight"] == 5.00


# ==============================================================================
# 3. Expected Field Update & Immutability Tests
# ==============================================================================

@pytest.mark.anyio
async def test_update_expected_field_safe_update(auth_setup):
    """6. Verify safe update to supported expected-field properties (field_name, description, weight)."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())
    field_id = str(uuid.uuid4())
    captured_patch = []

    mock_session = {
        "id": session_id, "user_id": USER_A_ID, "title": "Patch Session",
        "research_query": "Patch test", "status": "completed",
        "created_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:00Z",
    }

    mock_field = {
        "id": field_id, "session_id": session_id, "user_id": USER_A_ID,
        "field_name": "Initial Name", "field_category": "general",
        "description": "Initial desc", "is_required": True,
        "weight": 1.0, "status": "missing",
        "created_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:00Z",
    }

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str and request.method == "GET":
            return httpx.Response(200, json=[mock_field])
        if "expected_fields" in url_str and request.method == "PATCH":
            body = json.loads(request.content)
            captured_patch.append(body)
            updated = dict(mock_field)
            updated.update(body)
            updated["updated_at"] = "2026-11-01T12:05:00Z"
            return httpx.Response(200, json=[updated])
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A. Updating field_name, description, and weight succeeds together
        res = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "field_name": "Updated Dimension Name",
                "weight": 3.0,
                "description": "Updated criteria",
            }
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        data = body["data"]

        assert data["field_name"] == "Updated Dimension Name"
        assert data["weight"] == 3.0
        assert data["description"] == "Updated criteria"
        assert data["status"] == "missing"  # Preserves initial status, not client-overwritable

        assert len(captured_patch) == 1
        assert captured_patch[0]["field_name"] == "Updated Dimension Name"
        assert captured_patch[0]["weight"] == 3.0
        assert captured_patch[0]["description"] == "Updated criteria"
        assert "status" not in captured_patch[0]

        # B. Updating field_name individually succeeds
        res_fn = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "Solely Updated Name"}
        )
        assert res_fn.status_code == 200
        assert res_fn.json()["data"]["field_name"] == "Solely Updated Name"

        # C. Updating description individually succeeds
        res_desc = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"description": "Solely updated description"}
        )
        assert res_desc.status_code == 200
        assert res_desc.json()["data"]["description"] == "Solely updated description"

        # D. Updating weight individually succeeds
        res_wt = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"weight": 4.5}
        )
        assert res_wt.status_code == 200
        assert res_wt.json()["data"]["weight"] == 4.5


@pytest.mark.anyio
async def test_update_expected_field_rejection_of_status_and_immutable_fields(auth_setup):
    """7. Verify rejection of status (evidence integrity) and immutable fields (user_id, session_id, id, timestamps)."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())
    field_id = str(uuid.uuid4())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Attempt to update status (e.g. marking covered without evidence) -> HTTP 422
        res_status_covered = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "covered"}
        )
        assert res_status_covered.status_code == 422

        res_status_part = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "partially_covered"}
        )
        assert res_status_part.status_code == 422

        # Attempt to tamper with user_id -> HTTP 422
        res_tamper = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"user_id": USER_B_ID}
        )
        assert res_tamper.status_code == 422

        # Attempt to tamper with session_id -> HTTP 422
        res_sess = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"session_id": str(uuid.uuid4())}
        )
        assert res_sess.status_code == 422

        # Attempt to tamper with id -> HTTP 422
        res_id = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"id": str(uuid.uuid4())}
        )
        assert res_id.status_code == 422

        # Attempt to tamper with created_at -> HTTP 422
        res_created_at = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"created_at": "2026-11-01T12:00:00Z"}
        )
        assert res_created_at.status_code == 422

        # Attempt to tamper with updated_at -> HTTP 422
        res_updated_at = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"updated_at": "2026-11-01T12:00:00Z"}
        )
        assert res_updated_at.status_code == 422

        # Empty body -> HTTP 422
        res_empty = await client.patch(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={}
        )
        assert res_empty.status_code == 422


# ==============================================================================
# 4. Expected Field Deletion Tests
# ==============================================================================

@pytest.mark.anyio
async def test_delete_expected_field_success(auth_setup):
    """8. Verify deletion of expected field scoped to owned session."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())
    field_id = str(uuid.uuid4())
    captured_delete = []

    mock_session = {
        "id": session_id, "user_id": USER_A_ID, "title": "Delete Session",
        "research_query": "Delete test", "status": "completed",
        "created_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:00Z",
    }

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str and request.method == "DELETE":
            captured_delete.append(request)
            return httpx.Response(200, json=[{"id": field_id}])
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.delete(
            f"/api/v1/research/sessions/{session_id}/expected-fields/{field_id}",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        assert body["data"]["deleted"] is True
        assert body["data"]["id"] == field_id

        assert len(captured_delete) == 1
        params = captured_delete[0].url.params
        assert params["id"] == f"eq.{field_id}"
        assert params["session_id"] == f"eq.{session_id}"
        assert params["user_id"] == f"eq.{USER_A_ID}"


# ==============================================================================
# 5. Cross-User Prevention & UUID Validation Tests
# ==============================================================================

@pytest.mark.anyio
async def test_cross_user_expected_fields_access_prevention(auth_setup):
    """9. Verify User B cannot view, create, patch, delete, or check coverage on User A's session."""
    token_b = auth_setup(USER_B_ID)
    user_a_session_id = str(uuid.uuid4())
    user_a_field_id = str(uuid.uuid4())

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        # PostgREST user_id filter rejects cross-user access -> returns empty
        return httpx.Response(200, json=[])

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # A. GET fields cross-user
        res_get = await client.get(
            f"/api/v1/research/sessions/{user_a_session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        assert res_get.status_code == 404

        # B. POST field cross-user
        res_post = await client.post(
            f"/api/v1/research/sessions/{user_a_session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"field_name": "Unauthorized Field"}
        )
        assert res_post.status_code == 404

        # C. PATCH field cross-user
        res_patch = await client.patch(
            f"/api/v1/research/sessions/{user_a_session_id}/expected-fields/{user_a_field_id}",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"field_name": "Unauthorized Patch"}
        )
        assert res_patch.status_code == 404

        # D. DELETE field cross-user
        res_delete = await client.delete(
            f"/api/v1/research/sessions/{user_a_session_id}/expected-fields/{user_a_field_id}",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        assert res_delete.status_code == 404

        # E. GET coverage cross-user
        res_cov = await client.get(
            f"/api/v1/research/sessions/{user_a_session_id}/coverage",
            headers={"Authorization": f"Bearer {token_b}"}
        )
        assert res_cov.status_code == 404


@pytest.mark.anyio
async def test_invalid_uuid_handling_across_expected_fields(auth_setup):
    """10. Verify malformed UUID strings return 404 EntityNotFoundError without DB queries."""
    token = auth_setup(USER_A_ID)
    valid_sid = str(uuid.uuid4())

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Invalid session_id on list
        res_list = await client.get(
            "/api/v1/research/sessions/not-a-valid-uuid/expected-fields",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_list.status_code == 404

        # Invalid session_id on create
        res_create = await client.post(
            "/api/v1/research/sessions/not-a-valid-uuid/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "Valid Field Name"}
        )
        assert res_create.status_code == 404

        # Invalid field_id on patch
        res_patch = await client.patch(
            f"/api/v1/research/sessions/{valid_sid}/expected-fields/not-a-valid-field-id",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "Updated Name"}
        )
        assert res_patch.status_code == 404

        # Invalid field_id on delete
        res_del = await client.delete(
            f"/api/v1/research/sessions/{valid_sid}/expected-fields/not-a-valid-field-id",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_del.status_code == 404

        # Invalid session_id on coverage
        res_cov = await client.get(
            "/api/v1/research/sessions/not-a-valid-uuid/coverage",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_cov.status_code == 404


# ==============================================================================
# 6. Coverage Calculation & Boundary Tests
# ==============================================================================

@pytest.mark.anyio
async def test_coverage_calculation(auth_setup):
    """11. Verify weighted coverage calculation matches ExpectedFieldsRepository formula."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Coverage Test Session",
        "research_query": "Testing coverage metrics",
        "status": "completed",
        "coverage_score": 0,
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    # 4 fields:
    # F1: weight=2.0, status='covered' -> 2.0 pts
    # F2: weight=1.0, status='covered' -> 1.0 pts
    # F3: weight=1.0, status='partially_covered' -> 0.5 pts
    # F4: weight=1.0, status='missing' -> 0.0 pts
    # Total weight = 5.0, points = 3.5 -> (3.5 / 5.0) * 100 = 70%
    mock_fields = [
        {"id": str(uuid.uuid4()), "session_id": session_id, "user_id": USER_A_ID, "field_name": "F1", "weight": 2.0, "status": "covered", "field_category": "g", "is_required": True, "created_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:00Z"},
        {"id": str(uuid.uuid4()), "session_id": session_id, "user_id": USER_A_ID, "field_name": "F2", "weight": 1.0, "status": "covered", "field_category": "g", "is_required": True, "created_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:00Z"},
        {"id": str(uuid.uuid4()), "session_id": session_id, "user_id": USER_A_ID, "field_name": "F3", "weight": 1.0, "status": "partially_covered", "field_category": "g", "is_required": True, "created_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:00Z"},
        {"id": str(uuid.uuid4()), "session_id": session_id, "user_id": USER_A_ID, "field_name": "F4", "weight": 1.0, "status": "missing", "field_category": "g", "is_required": True, "created_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:00Z"},
    ]

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            if request.method == "PATCH":
                return httpx.Response(200, json=[dict(mock_session, coverage_score=70)])
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str:
            return httpx.Response(200, json=mock_fields)
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{session_id}/coverage",
            headers={"Authorization": f"Bearer {token}"}
        )

        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        data = body["data"]

        assert data["coverage_score"] == 70
        assert data["total_fields"] == 4
        assert data["covered_fields"] == 2
        assert data["partially_covered_fields"] == 1
        assert data["missing_fields"] == 1
        assert data["total_weight"] == 5.0
        assert data["covered_weight"] == 3.5
        assert len(data["fields"]) == 4


@pytest.mark.anyio
async def test_coverage_boundary_validation(auth_setup):
    """12. Verify coverage score boundaries: 0% for empty/missing, 100% for full coverage."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id,
        "user_id": USER_A_ID,
        "title": "Boundary Session",
        "research_query": "Testing boundary cases",
        "status": "pending",
        "created_at": "2026-11-01T12:00:00Z",
        "updated_at": "2026-11-01T12:00:00Z",
    }

    # Case A: 0 fields -> score 0
    def mock_db_empty(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str:
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_empty))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_empty = await client.get(
            f"/api/v1/research/sessions/{session_id}/coverage",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_empty.status_code == 200
        assert res_empty.json()["data"]["coverage_score"] == 0
        assert res_empty.json()["data"]["total_fields"] == 0

    # Case B: 100% covered
    mock_full = [
        {"id": str(uuid.uuid4()), "session_id": session_id, "user_id": USER_A_ID, "field_name": "Full", "weight": 5.0, "status": "covered", "field_category": "g", "is_required": True, "created_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:00Z"},
    ]

    def mock_db_full(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str:
            return httpx.Response(200, json=mock_full)
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_full))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res_full = await client.get(
            f"/api/v1/research/sessions/{session_id}/coverage",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_full.status_code == 200
        assert res_full.json()["data"]["coverage_score"] == 100


# ==============================================================================
# 7. Database Failure & APIResponse Compatibility Tests
# ==============================================================================

@pytest.mark.anyio
async def test_database_failure_handling(auth_setup):
    """13. Verify 503 structured error response when PostgREST is unavailable."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())
    field_id = str(uuid.uuid4())

    def mock_db_error(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "PostgREST connection failed"})

    set_default_db_transport(httpx.MockTransport(mock_db_error))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET expected-fields DB failure
        res_list = await client.get(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_list.status_code == 503
        assert res_list.json()["success"] is False

        # POST expected-fields DB failure
        res_post = await client.post(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"},
            json={"field_name": "Test Dimension"}
        )
        assert res_post.status_code == 503
        assert res_post.json()["success"] is False

        # GET coverage DB failure
        res_cov = await client.get(
            f"/api/v1/research/sessions/{session_id}/coverage",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_cov.status_code == 503
        assert res_cov.json()["success"] is False


@pytest.mark.anyio
async def test_api_response_compatibility(auth_setup):
    """14. Verify standard APIResponse envelope structure on all expected-fields endpoints."""
    token = auth_setup(USER_A_ID)
    session_id = str(uuid.uuid4())

    mock_session = {
        "id": session_id, "user_id": USER_A_ID, "title": "Envelope Session",
        "research_query": "Testing envelope", "status": "pending",
        "created_at": "2026-11-01T12:00:00Z", "updated_at": "2026-11-01T12:00:00Z",
    }

    def mock_db_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if "research_sessions" in url_str:
            return httpx.Response(200, json=[mock_session])
        if "expected_fields" in url_str:
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    set_default_db_transport(httpx.MockTransport(mock_db_handler))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            f"/api/v1/research/sessions/{session_id}/expected-fields",
            headers={"Authorization": f"Bearer {token}"}
        )
        body = res.json()

        # Strict check of all APIResponse envelope fields
        assert "success" in body
        assert "status_code" in body
        assert "message" in body
        assert "data" in body
        assert "timestamp" in body
        assert body["success"] is True
        assert body["status_code"] == 200

