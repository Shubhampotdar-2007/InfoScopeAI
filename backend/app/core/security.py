"""
Security and Authentication Module for InfoScope AI.
Provides Supabase JWT verification and current user extraction.
Ensures zero trust in client-supplied body user IDs.
"""

from typing import Optional, Dict, Any
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

security_bearer = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """Represents a verified Supabase user extracted from a valid JWT."""
    def __init__(self, user_id: str, email: Optional[str] = None, role: Optional[str] = None, raw_payload: Optional[Dict[str, Any]] = None):
        self.user_id = user_id
        self.email = email
        self.role = role
        self.raw_payload = raw_payload or {}

    def __repr__(self) -> str:
        return f"<AuthenticatedUser id={self.user_id} email={self.email}>"


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
) -> AuthenticatedUser:
    """
    Dependency that extracts and verifies Supabase JWT token.
    Throws 401 Unauthorized if token is missing, expired, or invalid.
    Never relies on client-provided body parameters for user identity.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided. Include a valid Supabase Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    # If Supabase JWT Secret is not set in environment yet, inform clearly
    if not settings.SUPABASE_JWT_SECRET or settings.SUPABASE_JWT_SECRET == "your-supabase-jwt-secret-here":
        # In early development without secret configured, decode unverified header/payload for diagnostics or reject
        try:
            # Check if payload can be decoded without signature for debugging warning
            unverified_payload = jwt.decode(token, options={"verify_signature": False})
            user_id = unverified_payload.get("sub")
            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token structure: missing 'sub' subject claim.",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            # In strict production mode, missing JWT secret must be configured
            # For local setup guidance, we raise a helpful error:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="SUPABASE_JWT_SECRET is not configured on the backend. Please set SUPABASE_JWT_SECRET in backend/.env to verify user tokens.",
            )
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Malformed JWT token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    try:
        # Verify token with Supabase JWT Secret
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=[settings.SUPABASE_JWT_ALGORITHM],
            audience=settings.SUPABASE_JWT_AUDIENCE,
            options={"verify_exp": True, "verify_aud": True}
        )

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token is missing user identifier ('sub' claim).",
                headers={"WWW-Authenticate": "Bearer"},
            )

        email = payload.get("email")
        role = payload.get("role", "authenticated")

        return AuthenticatedUser(
            user_id=user_id,
            email=email,
            role=role,
            raw_payload=payload
        )

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please refresh your session.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
