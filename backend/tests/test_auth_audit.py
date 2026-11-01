"""
Authentication and Authorization Integration Audit Test Suite for InfoScope AI.
Covers:
1. Unauthenticated request rejection (401 Unauthorized)
2. Malformed, expired, and tampered token rejection (401 Unauthorized)
3. Authenticated request access with valid Supabase ES256 JWT (200 OK / 202 Accepted)
4. User ID derivation strictly from verified JWT (zero trust in request body)
5. Supabase JWT structure, ES256 signing algorithm, and audience compatibility
6. Database Row Level Security (RLS) SQL policies verification
"""

import time
import uuid
from pathlib import Path
import jwt
from jwt import PyJWKClientError
from cryptography.hazmat.primitives.asymmetric import ec
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.core.security import set_jwks_client


AUDIT_KID = "audit-supabase-es256-kid"
AUDIT_ISSUER = "https://infoscope-test.supabase.co/auth/v1"
AUDIT_JWKS_URL = "https://infoscope-test.supabase.co/auth/v1/.well-known/jwks.json"


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
        raise PyJWKClientError(f"Unable to find key with kid: '{kid}'")


@pytest.fixture(autouse=True)
def setup_audit_environment(monkeypatch):
    """Configures settings for audit tests."""
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://infoscope-test.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_JWKS_URL", AUDIT_JWKS_URL)
    monkeypatch.setattr(settings, "SUPABASE_JWT_ISSUER", AUDIT_ISSUER)
    monkeypatch.setattr(settings, "SUPABASE_JWT_AUDIENCE", "authenticated")


@pytest.fixture
def ec_key_pair():
    """Generates an Elliptic Curve P-256 key pair for ES256 audit tests."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def mock_jwks_client(ec_key_pair):
    """Sets up an in-memory MockJWKClient with the test public key."""
    _, public_key = ec_key_pair
    client = MockJWKClient(key_map={AUDIT_KID: public_key})
    set_jwks_client(client, AUDIT_JWKS_URL)
    yield client
    set_jwks_client(None, None)


@pytest.fixture
def generate_supabase_jwt(ec_key_pair, mock_jwks_client):
    """Generates a valid Supabase ES256 JWT access token."""
    private_key, _ = ec_key_pair

    def _create_token(
        user_id: str = None,
        email: str = "researcher@infoscope.ai",
        role: str = "authenticated",
        audience: str = "authenticated",
        expires_in: int = 3600,
        signing_key = None,
        kid: str = AUDIT_KID,
        algorithm: str = "ES256",
        issuer: str = AUDIT_ISSUER,
    ) -> str:
        key = signing_key or private_key
        uid = user_id or str(uuid.uuid4())
        now = int(time.time())
        payload = {
            "sub": uid,
            "email": email,
            "role": role,
            "aud": audience,
            "exp": now + expires_in,
            "iat": now,
            "iss": issuer,
            "app_metadata": {"provider": "email", "providers": ["email"]},
            "user_metadata": {"full_name": "InfoScope Auditor"},
        }
        headers = {"kid": kid} if kid else {}
        return jwt.encode(payload, key, algorithm=algorithm, headers=headers)

    return _create_token


@pytest.mark.anyio
async def test_protected_endpoints_reject_unauthenticated_requests():
    """Verify that protected research endpoints reject unauthenticated requests with 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET /api/v1/research/sessions
        get_res = await client.get("/api/v1/research/sessions")
        assert get_res.status_code == 401
        get_json = get_res.json()
        assert get_json["success"] is False
        assert "credentials were not provided" in get_json["message"]

        # POST /api/v1/research/sessions
        post_res = await client.post("/api/v1/research/sessions", json={
            "research_query": "Unauthenticated probe query",
            "source_selection": "web"
        })
        assert post_res.status_code == 401
        post_json = post_res.json()
        assert post_json["success"] is False
        assert "credentials were not provided" in post_json["message"]


@pytest.mark.anyio
async def test_protected_endpoints_reject_tampered_and_expired_tokens(generate_supabase_jwt):
    """Verify that invalid tokens (expired, forged signature, malformed) are rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Expired token
        expired_token = generate_supabase_jwt(expires_in=-300)
        res_expired = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert res_expired.status_code == 401
        assert "expired" in res_expired.json()["message"].lower()

        # 2. Forged signature (signed with different EC private key)
        attacker_key = ec.generate_private_key(ec.SECP256R1())
        forged_token = generate_supabase_jwt(signing_key=attacker_key)
        res_forged = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {forged_token}"}
        )
        assert res_forged.status_code == 401
        assert "signature verification failed" in res_forged.json()["message"].lower()

        # 3. Malformed token string
        res_malformed = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": "Bearer not-a-valid-jwt-token"}
        )
        assert res_malformed.status_code == 401
        assert "invalid" in res_malformed.json()["message"].lower() or "malformed" in res_malformed.json()["message"].lower()


@pytest.mark.anyio
async def test_authenticated_user_accesses_protected_endpoints(generate_supabase_jwt):
    """Verify that valid authenticated requests successfully access protected endpoints."""
    test_uid = str(uuid.uuid4())
    test_email = "audited-researcher@infoscope.ai"
    token = generate_supabase_jwt(user_id=test_uid, email=test_email)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET sessions
        get_res = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert get_res.status_code == 200
        get_json = get_res.json()
        assert get_json["success"] is True
        assert test_email in get_json["message"]
        assert isinstance(get_json["data"], list)

        # POST session
        post_res = await client.post(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "research_query": "What are the latest breakthroughs in LLM multi-agent architectures?",
                "source_selection": "both",
                "custom_urls": ["https://arxiv.org/abs/2308.08155"]
            }
        )
        assert post_res.status_code == 202
        post_json = post_res.json()
        assert post_json["success"] is True
        assert post_json["data"]["user_id"] == test_uid
        assert post_json["data"]["status"] == "pending"


@pytest.mark.anyio
async def test_user_id_derived_from_jwt_zero_trust_in_body(generate_supabase_jwt):
    """
    CRITICAL SECURITY CHECK:
    Verify that user IDs are derived strictly from the verified JWT 'sub' claim
    and NEVER trusted from client request bodies.
    """
    legitimate_uid = "11111111-1111-1111-1111-111111111111"
    spoofed_uid = "99999999-9999-9999-9999-999999999999"

    token = generate_supabase_jwt(user_id=legitimate_uid, email="legit@infoscope.ai")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Client maliciously injects spoofed user_id into payload
        malicious_payload = {
            "research_query": "Security boundary verification test",
            "source_selection": "web",
            "user_id": spoofed_uid,  # Attempted identity spoofing
        }

        res = await client.post(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json=malicious_payload
        )
        assert res.status_code == 202
        res_data = res.json()["data"]

        # Assert server derived user_id from token, NOT the malicious body
        assert res_data["user_id"] == legitimate_uid
        assert res_data["user_id"] != spoofed_uid


def test_database_rls_schema_policies():
    """
    Verify that database/schema.sql explicitly enables Row Level Security (RLS)
    and enforces user-level isolation across SELECT, INSERT, UPDATE, and DELETE.
    """
    schema_path = Path(__file__).resolve().parent.parent.parent / "database" / "schema.sql"
    assert schema_path.exists(), f"Schema file missing at {schema_path}"

    schema_sql = schema_path.read_text(encoding="utf-8")

    # 1. Table references auth.users
    assert "REFERENCES auth.users(id)" in schema_sql

    # 2. RLS is explicitly enabled
    assert "ALTER TABLE public.research_sessions ENABLE ROW LEVEL SECURITY;" in schema_sql

    # 3. User isolation policies using auth.uid()
    assert 'CREATE POLICY "Users can view own research sessions"' in schema_sql
    assert "USING (auth.uid() = user_id)" in schema_sql

    assert 'CREATE POLICY "Users can insert own research sessions"' in schema_sql
    assert "WITH CHECK (auth.uid() = user_id)" in schema_sql

    assert 'CREATE POLICY "Users can update own research sessions"' in schema_sql
    assert "USING (auth.uid() = user_id)" in schema_sql

    assert 'CREATE POLICY "Users can delete own research sessions"' in schema_sql
