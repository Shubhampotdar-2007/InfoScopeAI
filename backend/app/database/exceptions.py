"""
Database Exceptions Module for InfoScope AI.
Provides structured, safe exceptions mapping from PostgREST HTTP responses
without leaking internal database credentials, schemas, or connection strings.
"""

from typing import Optional, Any
import httpx


class DatabaseError(Exception):
    """Base exception for all database and PostgREST operations."""

    def __init__(
        self,
        message: str = "A database error occurred.",
        status_code: int = 500,
        details: Optional[Any] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} status_code={self.status_code} message={self.message!r}>"


class EntityNotFoundError(DatabaseError):
    """Raised when a requested database entity or record is not found."""

    def __init__(
        self,
        message: str = "Requested database entity was not found.",
        status_code: int = 404,
        details: Optional[Any] = None,
    ):
        super().__init__(message=message, status_code=status_code, details=details)


class DatabaseConstraintError(DatabaseError):
    """Raised when a database integrity constraint (unique, check, foreign key, not null) is violated."""

    def __init__(
        self,
        message: str = "Database constraint violation occurred.",
        status_code: int = 409,
        details: Optional[Any] = None,
    ):
        super().__init__(message=message, status_code=status_code, details=details)


class DatabaseAuthenticationError(DatabaseError):
    """Raised when database authentication or authorization (JWT, RLS, apikey) fails."""

    def __init__(
        self,
        message: str = "Database authentication or authorization failed.",
        status_code: int = 401,
        details: Optional[Any] = None,
    ):
        super().__init__(message=message, status_code=status_code, details=details)


def parse_postgrest_error(response: httpx.Response) -> DatabaseError:
    """
    Parses a PostgREST error response and returns an appropriate structured DatabaseError.
    Sanitizes error details to avoid exposing sensitive internal SQL details or credentials.
    """
    status_code = response.status_code

    try:
        data = response.json()
    except Exception:
        data = {}

    pg_code: Optional[str] = None
    if isinstance(data, dict):
        raw_code = data.get("code")
        if raw_code is not None:
            pg_code = str(raw_code).strip()

    # 401 Unauthorized (JWT invalid, expired, or missing)
    if status_code == 401:
        return DatabaseAuthenticationError(
            message="Database authentication failed. Access token is invalid or expired.",
            status_code=401,
        )

    # 403 Forbidden (RLS violation or insufficient permissions)
    if status_code == 403:
        return DatabaseAuthenticationError(
            message="Database access denied by security policies.",
            status_code=403,
        )

    # 404 Not Found
    if status_code == 404:
        return EntityNotFoundError(
            message="Requested database entity was not found.",
            status_code=404,
        )

    # 409 Conflict or PostgreSQL Class 23 Integrity Constraint Violations
    if status_code == 409 or (pg_code and pg_code.startswith("23")):
        if pg_code == "23505":
            msg = "A record with this identifier or unique attribute already exists."
        elif pg_code == "23503":
            msg = "Referenced database record does not exist."
        elif pg_code == "23502":
            msg = "A required database field is missing or null."
        elif pg_code == "23514":
            msg = "Database check constraint validation failed."
        else:
            msg = "Database integrity constraint violation."

        return DatabaseConstraintError(
            message=msg,
            status_code=409,
            details={"code": pg_code} if pg_code else None,
        )

    # 400 Bad Request
    if status_code == 400:
        return DatabaseError(
            message="Database request is invalid.",
            status_code=400,
            details={"code": pg_code} if pg_code else None,
        )

    # 500+ Internal Server / Gateway Errors
    if status_code >= 500:
        return DatabaseError(
            message="Database service is temporarily unavailable.",
            status_code=status_code,
        )

    # Fallback
    return DatabaseError(
        message="Database operation failed.",
        status_code=status_code,
    )
