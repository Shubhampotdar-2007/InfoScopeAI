"""
Asynchronous Supabase PostgREST Client for InfoScope AI.
Communicates with Supabase PostgREST at {SUPABASE_URL}/rest/v1/.
Forwards verified user JWT in Authorization header and anon key in apikey header.
Reuses connection pool via httpx.AsyncClient and strictly prevents service-role key usage.
"""

from typing import Optional, Dict, Any
import httpx
import jwt
from fastapi import Depends

from app.core.config import settings
from app.core.security import AuthenticatedUser, get_current_user
from app.database.exceptions import (
    DatabaseError,
    DatabaseAuthenticationError,
    parse_postgrest_error,
)


_shared_client: Optional[httpx.AsyncClient] = None
_default_transport: Optional[httpx.AsyncBaseTransport] = None


def is_service_role_key(token: Optional[str]) -> bool:
    """Checks whether a token contains the service_role claim without cryptographic verification."""
    if not token or not isinstance(token, str):
        return False
    try:
        payload = jwt.decode(token.strip(), options={"verify_signature": False})
        return payload.get("role") == "service_role"
    except Exception:
        return False


def get_db_http_client() -> httpx.AsyncClient:
    """
    Returns or lazily creates a shared, pooled httpx.AsyncClient.
    Avoids creating a new client per query and manages keep-alive connections.
    """
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0)
        timeout = httpx.Timeout(settings.DATABASE_TIMEOUT_SECONDS, connect=5.0)
        if _default_transport is not None:
            _shared_client = httpx.AsyncClient(transport=_default_transport, limits=limits, timeout=timeout)
        else:
            _shared_client = httpx.AsyncClient(limits=limits, timeout=timeout)
    return _shared_client


def set_default_db_transport(transport: Optional[httpx.AsyncBaseTransport] = None) -> None:
    """Helper to set or reset a default transport (e.g. MockTransport) for testing."""
    global _default_transport, _shared_client
    _default_transport = transport
    if _shared_client is not None and not _shared_client.is_closed:
        # Client will be recreated with the new transport on next get_db_http_client call
        _shared_client = None


async def close_db_http_client() -> None:
    """Closes the shared httpx.AsyncClient on application shutdown."""
    global _shared_client
    if _shared_client is not None and not _shared_client.is_closed:
        await _shared_client.aclose()
    _shared_client = None


class PostgrestClient:
    """
    Asynchronous user-scoped client communicating with Supabase PostgREST.
    Ensures zero trust in frontend user IDs by forwarding verified JWT tokens
    and using Supabase anon/publishable key as the apikey header.
    Never logs authorization headers or credentials.
    """

    def __init__(
        self,
        access_token: Optional[str] = None,
        user: Optional[AuthenticatedUser] = None,
        base_url: Optional[str] = None,
        anon_key: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ):
        # 1. Resolve and validate user access token
        resolved_token = None
        if user is not None and getattr(user, "access_token", None):
            resolved_token = user.access_token
        elif access_token:
            resolved_token = access_token.strip()

        if not resolved_token:
            raise DatabaseAuthenticationError(
                "User access token is required for user-scoped database operations."
            )

        if is_service_role_key(resolved_token):
            raise DatabaseAuthenticationError(
                "Accidental service-role key usage detected. The service-role key cannot be used as a user access token."
            )

        self.access_token = resolved_token
        self.user = user

        # 2. Resolve and validate Supabase anon / publishable key
        resolved_anon = (anon_key or settings.supabase_anon_key or "").strip()
        if not resolved_anon:
            raise DatabaseAuthenticationError(
                "Supabase anon/publishable key is not configured. Normal database operations require the anon key."
            )

        if is_service_role_key(resolved_anon):
            raise DatabaseAuthenticationError(
                "Accidental service-role key usage detected. The service-role key cannot be used as an apikey for user-scoped database operations."
            )

        self.anon_key = resolved_anon

        # 3. Resolve PostgREST base URL
        resolved_url = (base_url or settings.postgrest_url or "").strip().rstrip("/")
        if not resolved_url:
            raise DatabaseError(
                "Supabase PostgREST base URL is not configured.",
                status_code=500,
            )

        self.base_url = resolved_url
        self._http_client = http_client

    @property
    def user_id(self) -> str:
        """Returns the verified user ID from the user object or access token sub claim."""
        if self.user and self.user.user_id:
            return str(self.user.user_id)
        if self.access_token:
            try:
                payload = jwt.decode(self.access_token, options={"verify_signature": False})
                sub = payload.get("sub")
                if sub:
                    return str(sub)
            except Exception:
                pass
        return ""

    def __repr__(self) -> str:
        # Never log or expose credentials or access tokens
        user_id = self.user_id or "unspecified"
        return f"<PostgrestClient base_url={self.base_url!r} user_id={user_id!r}>"

    async def __aenter__(self) -> "PostgrestClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    async def request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        """
        Executes an authenticated HTTP request to Supabase PostgREST.
        Injects the apikey (anon key) and Authorization: Bearer (user JWT).
        Maps HTTP error codes safely to structured DatabaseErrors.
        """
        client = self._http_client or get_db_http_client()
        clean_endpoint = endpoint.lstrip("/")
        url = f"{self.base_url}/{clean_endpoint}" if clean_endpoint else self.base_url

        req_headers = {
            "apikey": self.anon_key,
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
        }
        if json is not None:
            req_headers["Content-Type"] = "application/json"
        if headers:
            req_headers.update(headers)

        try:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json,
                headers=req_headers,
            )
        except httpx.TimeoutException as exc:
            raise DatabaseError(
                "Database operation timed out.",
                status_code=504,
            ) from exc
        except httpx.RequestError as exc:
            raise DatabaseError(
                "Unable to connect to database service.",
                status_code=503,
            ) from exc

        if response.status_code >= 400:
            raise parse_postgrest_error(response)

        return response

    async def get(
        self,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Executes a GET request and returns parsed JSON response."""
        response = await self.request("GET", endpoint, params=params, headers=headers)
        return self._parse_json_response(response)

    async def post(
        self,
        endpoint: str,
        *,
        json: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Executes a POST request and returns parsed JSON response."""
        response = await self.request("POST", endpoint, params=params, json=json, headers=headers)
        return self._parse_json_response(response)

    async def patch(
        self,
        endpoint: str,
        *,
        json: Optional[Any] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Executes a PATCH request and returns parsed JSON response."""
        response = await self.request("PATCH", endpoint, params=params, json=json, headers=headers)
        return self._parse_json_response(response)

    async def delete(
        self,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """Executes a DELETE request and returns parsed JSON response."""
        response = await self.request("DELETE", endpoint, params=params, headers=headers)
        return self._parse_json_response(response)

    def _parse_json_response(self, response: httpx.Response) -> Any:
        """Parses JSON content safely, handling empty bodies and malformed responses."""
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except Exception as exc:
            raise DatabaseError(
                "Malformed JSON response received from database service.",
                status_code=response.status_code,
            ) from exc


def get_db_client(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> PostgrestClient:
    """FastAPI dependency that returns a PostgrestClient scoped to the authenticated user."""
    return PostgrestClient(user=current_user)
