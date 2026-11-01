"""
Security and Authentication Module for InfoScope AI.
Provides Supabase ES256 JWT verification using project JWKS public keys.
Ensures zero trust in client-supplied body user IDs.
"""

from typing import Optional, Dict, Any
import jwt
from jwt import PyJWKClient, PyJWKClientError, PyJWKClientConnectionError, PyJWKError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security_bearer = HTTPBearer(auto_error=False)

_jwks_client: Optional[PyJWKClient] = None
_jwks_client_url: Optional[str] = None


class AuthenticatedUser:
    """Represents a verified Supabase user extracted from a valid JWT."""
    def __init__(
        self,
        user_id: str,
        email: Optional[str] = None,
        role: Optional[str] = None,
        raw_payload: Optional[Dict[str, Any]] = None,
        access_token: Optional[str] = None,
    ):
        self.user_id = user_id
        self.email = email
        self.role = role
        self.raw_payload = raw_payload or {}
        self.access_token = access_token

    def __repr__(self) -> str:
        # Never log or expose the access token in repr or string conversions
        return f"<AuthenticatedUser id={self.user_id} email={self.email}>"


def get_jwks_client() -> PyJWKClient:
    """
    Returns an in-memory cached PyJWKClient instance configured for Supabase JWKS.
    Supports key rotation and automatic cache refresh on unknown key ID.
    """
    global _jwks_client, _jwks_client_url
    url = settings.jwks_url
    if not url:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_URL is not configured on the backend. Unable to resolve JWKS endpoint.",
        )
    if _jwks_client is None or _jwks_client_url != url:
        _jwks_client = PyJWKClient(
            url,
            cache_keys=True,
            max_cached_keys=16,
            cache_jwk_set=True,
            lifespan=settings.SUPABASE_JWKS_CACHE_SECONDS,
            timeout=settings.SUPABASE_JWKS_TIMEOUT_SECONDS,
        )
        _jwks_client_url = url
    return _jwks_client


def set_jwks_client(client: Optional[PyJWKClient] = None, url: Optional[str] = None) -> None:
    """Helper to set or reset the JWKS client (primarily for testing and cache reset)."""
    global _jwks_client, _jwks_client_url
    _jwks_client = client
    _jwks_client_url = url


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> AuthenticatedUser:
    """
    Dependency that extracts and verifies Supabase JWT access token using ES256 JWKS.
    Throws 401 Unauthorized if token is missing, expired, invalid, or forged.
    Throws 503 Service Unavailable if JWKS endpoint cannot be reached.
    Never relies on client-provided body parameters for user identity.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided. Include a valid Supabase Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials.strip()

    # 1. Parse unverified JWT header
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed JWT token: Invalid header format.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Enforce ES256 algorithm allow-list (Never trust arbitrary algorithm from token)
    alg = header.get("alg")
    if not alg or alg.upper() != "ES256":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: Unsupported algorithm '{alg}'. Only ES256 is allowed.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 3. Enforce presence of Key ID ('kid')
    kid = header.get("kid")
    if not kid or not str(kid).strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: Missing 'kid' (Key ID) in header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Resolve signing public key via PyJWKClient (supports key rotation / refresh)
    jwks_client = get_jwks_client()
    try:
        signing_key = jwks_client.get_signing_key_from_jwt(token)
    except PyJWKClientConnectionError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify token: Authentication server JWKS lookup failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (PyJWKClientError, PyJWKError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: Unknown or unresolvable key ID ('{kid}').",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 5. Cryptographically verify signature, expiration, audience, issuer, and sub
    verify_aud = bool(settings.SUPABASE_JWT_AUDIENCE and settings.SUPABASE_JWT_AUDIENCE.strip() != "*")
    expected_aud = settings.SUPABASE_JWT_AUDIENCE.strip() if verify_aud else None

    verify_iss = bool(settings.jwt_issuer and settings.jwt_issuer.strip() != "*")
    expected_iss = settings.jwt_issuer.strip() if verify_iss else None

    decode_options = {
        "verify_signature": True,
        "verify_exp": True,
        "verify_aud": verify_aud,
        "verify_iss": verify_iss,
        "require": ["exp", "sub", "iss", "aud"]
    }

    try:
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],
            audience=expected_aud,
            issuer=expected_iss,
            options=decode_options
        )

        user_id = payload.get("sub")
        if not user_id or not str(user_id).strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing user identifier ('sub' claim).",
                headers={"WWW-Authenticate": "Bearer"},
            )

        email = payload.get("email")
        role = payload.get("role", "authenticated")

        return AuthenticatedUser(
            user_id=str(user_id),
            email=email,
            role=role,
            raw_payload=payload,
            access_token=token,
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please refresh your session.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidAudienceError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: Invalid audience.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidIssuerError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: Invalid issuer.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token: Signature verification failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
