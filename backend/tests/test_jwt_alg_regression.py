"""
Regression and Verification Test Suite for Supabase ES256 JWKS JWT Authentication.

Covers all 10 required test scenarios:
1. Valid ES256 Supabase JWT succeeds.
2. Missing authentication token returns HTTP 401.
3. Expired JWT is rejected (HTTP 401).
4. Invalid signature is rejected (HTTP 401).
5. Unsupported JWT algorithm is rejected (HTTP 401).
6. Unknown kid is rejected (HTTP 401).
7. Incorrect audience is rejected (HTTP 401).
8. Incorrect issuer is rejected (HTTP 401).
9. JWKS lookup failures are handled safely (HTTP 503).
10. JWKS caching works correctly.
"""

import time
import uuid
import base64
import pytest
import jwt
from jwt import PyJWKClient, PyJWKClientError, PyJWKClientConnectionError
from cryptography.hazmat.primitives.asymmetric import ec
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.core.security import get_jwks_client, set_jwks_client


TEST_ISSUER = "https://infoscope-test.supabase.co/auth/v1"
TEST_JWKS_URL = "https://infoscope-test.supabase.co/auth/v1/.well-known/jwks.json"
TEST_KID = "test-es256-key-id-001"


def int_to_b64(n: int, length: int = 32) -> str:
    """Helper to convert big endian integers to unpadded base64url."""
    b = n.to_bytes(length, byteorder="big")
    return base64.urlsafe_b64encode(b).decode("utf-8").rstrip("=")


class MockSigningKey:
    def __init__(self, key, key_id):
        self.key = key
        self.key_id = key_id


class MockJWKClient:
    """In-memory mock for PyJWKClient avoiding external network requests."""
    def __init__(self, key_map=None, should_fail_connection=False):
        self.key_map = key_map or {}
        self.should_fail_connection = should_fail_connection
        self.lookup_call_count = 0

    def get_signing_key_from_jwt(self, token: str):
        self.lookup_call_count += 1
        if self.should_fail_connection:
            raise PyJWKClientConnectionError("Connection to JWKS endpoint failed.")
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if kid in self.key_map:
            return MockSigningKey(self.key_map[kid], kid)
        raise PyJWKClientError(f"Unable to find a signing key that matches: '{kid}'")


@pytest.fixture
def ec_key_pair():
    """Generates an Elliptic Curve P-256 key pair for ES256 tests."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key, TEST_KID


@pytest.fixture
def setup_mock_jwks(ec_key_pair, monkeypatch):
    """Configures settings and mock JWKS client for testing."""
    private_key, public_key, kid = ec_key_pair
    mock_client = MockJWKClient(key_map={kid: public_key})
    
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://infoscope-test.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_JWKS_URL", TEST_JWKS_URL)
    monkeypatch.setattr(settings, "SUPABASE_JWT_ISSUER", TEST_ISSUER)
    monkeypatch.setattr(settings, "SUPABASE_JWT_AUDIENCE", "authenticated")
    
    set_jwks_client(mock_client, TEST_JWKS_URL)
    yield mock_client
    set_jwks_client(None, None)


def create_es256_token(
    private_key,
    user_id: str = None,
    email: str = "researcher@infoscope.ai",
    audience: str = "authenticated",
    issuer: str = TEST_ISSUER,
    expires_in: int = 3600,
    kid: str = TEST_KID,
    algorithm: str = "ES256",
) -> str:
    """Generates a signed Supabase ES256 JWT access token."""
    uid = user_id or str(uuid.uuid4())
    now = int(time.time())
    payload = {
        "sub": uid,
        "email": email,
        "role": "authenticated",
        "aud": audience,
        "iss": issuer,
        "exp": now + expires_in,
        "iat": now,
        "app_metadata": {"provider": "email"},
        "user_metadata": {"full_name": "Test User"},
    }
    headers = {"kid": kid} if kid else {}
    return jwt.encode(payload, private_key, algorithm=algorithm, headers=headers)


@pytest.mark.anyio
async def test_1_valid_es256_jwt_succeeds(ec_key_pair, setup_mock_jwks):
    """1. Valid ES256 Supabase JWT succeeds with 200 OK."""
    private_key, _, kid = ec_key_pair
    token = create_es256_token(private_key, kid=kid)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert isinstance(data["data"], list)


@pytest.mark.anyio
async def test_2_missing_authentication_token_returns_401():
    """2. Missing authentication token returns HTTP 401."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/research/sessions")
        assert res.status_code == 401
        data = res.json()
        assert data["success"] is False
        assert "credentials were not provided" in data["message"].lower()


@pytest.mark.anyio
async def test_3_expired_jwt_is_rejected(ec_key_pair, setup_mock_jwks):
    """3. Expired JWT is rejected with HTTP 401."""
    private_key, _, kid = ec_key_pair
    expired_token = create_es256_token(private_key, expires_in=-300, kid=kid)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert res.status_code == 401
        data = res.json()
        assert "expired" in data["message"].lower()


@pytest.mark.anyio
async def test_4_invalid_signature_is_rejected(ec_key_pair, setup_mock_jwks):
    """4. Invalid signature is rejected with HTTP 401."""
    # Sign with a different, unauthorized private key
    unauthorized_private_key = ec.generate_private_key(ec.SECP256R1())
    forged_token = create_es256_token(unauthorized_private_key, kid=TEST_KID)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {forged_token}"}
        )
        assert res.status_code == 401
        data = res.json()
        assert "signature verification failed" in data["message"].lower()


@pytest.mark.anyio
async def test_5_unsupported_jwt_algorithm_is_rejected(setup_mock_jwks):
    """5. Unsupported JWT algorithms (HS256, none) are rejected with HTTP 401."""
    # Create an HS256 token
    hs256_token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated", "exp": int(time.time()) + 3600, "iss": TEST_ISSUER},
        "some-symmetric-secret-key-32-bytes",
        algorithm="HS256",
        headers={"kid": TEST_KID}
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {hs256_token}"}
        )
        assert res.status_code == 401
        data = res.json()
        assert "unsupported algorithm" in data["message"].lower()


@pytest.mark.anyio
async def test_6_unknown_kid_is_rejected(ec_key_pair, setup_mock_jwks):
    """6. Unknown kid is rejected with HTTP 401."""
    private_key, _, _ = ec_key_pair
    token = create_es256_token(private_key, kid="unknown-nonexistent-kid-999")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        data = res.json()
        assert "unknown or unresolvable key id" in data["message"].lower()


@pytest.mark.anyio
async def test_7_incorrect_audience_is_rejected(ec_key_pair, setup_mock_jwks):
    """7. Incorrect audience is rejected with HTTP 401."""
    private_key, _, kid = ec_key_pair
    token = create_es256_token(private_key, audience="wrong-audience-scope", kid=kid)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        data = res.json()
        assert "invalid audience" in data["message"].lower()


@pytest.mark.anyio
async def test_8_incorrect_issuer_is_rejected(ec_key_pair, setup_mock_jwks):
    """8. Incorrect issuer is rejected with HTTP 401."""
    private_key, _, kid = ec_key_pair
    token = create_es256_token(private_key, issuer="https://untrusted-issuer.com/auth/v1", kid=kid)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 401
        data = res.json()
        assert "invalid issuer" in data["message"].lower()


@pytest.mark.anyio
async def test_9_jwks_lookup_failure_handled_safely(ec_key_pair, setup_mock_jwks):
    """9. JWKS lookup failures return HTTP 503 safely."""
    private_key, _, kid = ec_key_pair
    failing_client = MockJWKClient(should_fail_connection=True)
    set_jwks_client(failing_client, TEST_JWKS_URL)

    token = create_es256_token(private_key, kid=kid)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get(
            "/api/v1/research/sessions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res.status_code == 503
        data = res.json()
        assert "jwks lookup failed" in data["message"].lower()

    set_jwks_client(None, None)


def test_10_jwks_caching_and_client_reuse(monkeypatch):
    """10. JWKS client is cached in-memory and reused across calls with same URL."""
    set_jwks_client(None, None)
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://cached-project.supabase.co")

    client1 = get_jwks_client()
    client2 = get_jwks_client()

    assert client1 is client2
    assert client1.uri == "https://cached-project.supabase.co/auth/v1/.well-known/jwks.json"

    # Reset
    set_jwks_client(None, None)
