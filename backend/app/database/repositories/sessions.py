"""
Research Session Repository for InfoScope AI.
Handles CRUD and status lifecycle operations for public.research_sessions.
Enforces multi-tenant isolation via authenticated user ID derivation and RLS.
"""

import uuid
from typing import Dict, Any, List, Optional, Union
from fastapi import Depends

from app.database.client import PostgrestClient, get_db_client
from app.database.repositories.base import BaseRepository
from app.database.exceptions import EntityNotFoundError, DatabaseAuthenticationError


VALID_SESSION_STATUSES = frozenset({"pending", "collecting", "analyzing", "completed", "failed"})
VALID_SEARCH_PROVIDERS = frozenset({"tavily", "both", "openrouter"})


class ResearchSessionRepository(BaseRepository):
    """
    Repository for managing public.research_sessions in Supabase PostgREST.
    Strictly derives user_id from the verified AuthenticatedUser and prevents cross-user access.
    """

    def __init__(self, client: PostgrestClient):
        super().__init__(client=client, table_name="research_sessions", id_column="id")
        user_id = client.user_id
        if not user_id:
            raise DatabaseAuthenticationError(
                "Cannot initialize ResearchSessionRepository without verified user credentials."
            )
        self.user_id = user_id

    async def create_session(
        self,
        *,
        research_query: str,
        title: Optional[str] = None,
        search_provider: str = "tavily",
        search_metadata: Optional[Dict[str, Any]] = None,
        status: str = "pending",
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a new research session for the authenticated user.
        user_id is strictly derived from verified JWT.
        """
        if not research_query or not research_query.strip():
            raise ValueError("research_query cannot be empty.")

        if status not in VALID_SESSION_STATUSES:
            raise ValueError(
                f"Invalid session status '{status}'. Must be one of {sorted(VALID_SESSION_STATUSES)}"
            )

        if search_provider not in VALID_SEARCH_PROVIDERS:
            raise ValueError(
                f"Invalid search provider '{search_provider}'. Must be one of {sorted(VALID_SEARCH_PROVIDERS)}"
            )

        payload: Dict[str, Any] = {
            "user_id": self.user_id,
            "research_query": research_query.strip(),
            "title": title.strip() if title and title.strip() else "Untitled Research Session",
            "status": status,
            "search_provider": search_provider,
            "search_metadata": search_metadata or {},
        }
        if session_id:
            payload["id"] = str(session_id)

        return await self.insert(payload)

    async def get_session(self, session_id: Union[str, uuid.UUID]) -> Dict[str, Any]:
        """
        Retrieves a session by ID, ensuring it belongs to the authenticated user.
        Raises EntityNotFoundError if not found or unauthorized.
        """
        sid = str(session_id)
        records = await self.client.get(
            self.table_name,
            params={
                "id": f"eq.{sid}",
                "user_id": f"eq.{self.user_id}",
            },
        )
        if not records or not isinstance(records, list) or len(records) == 0:
            raise EntityNotFoundError(f"Research session '{sid}' was not found.")
        return records[0]

    async def get_session_optional(self, session_id: Union[str, uuid.UUID]) -> Optional[Dict[str, Any]]:
        """
        Retrieves a session by ID, or returns None if not found or unauthorized.
        """
        sid = str(session_id)
        records = await self.client.get(
            self.table_name,
            params={
                "id": f"eq.{sid}",
                "user_id": f"eq.{self.user_id}",
            },
        )
        if isinstance(records, list) and len(records) > 0:
            return records[0]
        return None

    async def list_user_sessions(
        self,
        *,
        status: Optional[str] = None,
        search_provider: Optional[str] = None,
        limit: Optional[int] = 50,
        offset: Optional[int] = 0,
        order: str = "created_at.desc",
    ) -> List[Dict[str, Any]]:
        """
        Lists research sessions belonging to the authenticated user.
        Supports pagination, filtering by status, and sorting by created_at.
        """
        filters: Dict[str, Any] = {"user_id": self.user_id}
        if status:
            if status not in VALID_SESSION_STATUSES:
                raise ValueError(
                    f"Invalid status filter '{status}'. Must be one of {sorted(VALID_SESSION_STATUSES)}"
                )
            filters["status"] = status
        if search_provider:
            if search_provider not in VALID_SEARCH_PROVIDERS:
                raise ValueError(
                    f"Invalid search_provider filter '{search_provider}'. Must be one of {sorted(VALID_SEARCH_PROVIDERS)}"
                )
            filters["search_provider"] = search_provider

        return await self.list(
            filters=filters,
            limit=limit,
            offset=offset,
            order=order,
        )

    async def update_session(
        self,
        session_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Updates session details for a session owned by the authenticated user.
        Strips any frontend-provided user_id, id, or timestamps to prevent tampering.
        Raises EntityNotFoundError if session not found or not owned by user.
        """
        if not data:
            raise ValueError("Update data cannot be empty.")

        # Defense-in-depth: Never allow updating user_id, id, or created_at
        safe_data = {
            k: v for k, v in data.items()
            if k not in ("id", "user_id", "created_at", "updated_at")
        }
        if not safe_data:
            raise ValueError("No updatable fields provided.")

        if "status" in safe_data and safe_data["status"] not in VALID_SESSION_STATUSES:
            raise ValueError(
                f"Invalid session status '{safe_data['status']}'. Must be one of {sorted(VALID_SESSION_STATUSES)}"
            )

        if "search_provider" in safe_data and safe_data["search_provider"] not in VALID_SEARCH_PROVIDERS:
            raise ValueError(
                f"Invalid search provider '{safe_data['search_provider']}'. Must be one of {sorted(VALID_SEARCH_PROVIDERS)}"
            )

        if "coverage_score" in safe_data and safe_data["coverage_score"] is not None:
            score = safe_data["coverage_score"]
            if not isinstance(score, int) or score < 0 or score > 100:
                raise ValueError("coverage_score must be an integer between 0 and 100.")

        sid = str(session_id)
        result = await self.client.patch(
            self.table_name,
            json=safe_data,
            params={
                "id": f"eq.{sid}",
                "user_id": f"eq.{self.user_id}",
            },
            headers={"Prefer": "return=representation"},
        )
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        raise EntityNotFoundError(f"Research session '{sid}' was not found.")

    async def update_session_status(
        self,
        session_id: Union[str, uuid.UUID],
        status: str,
        *,
        search_metadata: Optional[Dict[str, Any]] = None,
        summary: Optional[str] = None,
        coverage_score: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Convenience method for updating lifecycle status and diagnostic metadata."""
        update_data: Dict[str, Any] = {"status": status}
        if search_metadata is not None:
            update_data["search_metadata"] = search_metadata
        if summary is not None:
            update_data["summary"] = summary
        if coverage_score is not None:
            update_data["coverage_score"] = coverage_score

        return await self.update_session(session_id, update_data)

    async def delete_session(self, session_id: Union[str, uuid.UUID]) -> Dict[str, Any]:
        """
        Deletes a session owned by the authenticated user.
        Raises EntityNotFoundError if session not found or not owned by user.
        """
        sid = str(session_id)
        result = await self.client.delete(
            self.table_name,
            params={
                "id": f"eq.{sid}",
                "user_id": f"eq.{self.user_id}",
            },
            headers={"Prefer": "return=representation"},
        )
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        raise EntityNotFoundError(f"Research session '{sid}' was not found.")

    async def count_user_sessions(self, *, status: Optional[str] = None) -> int:
        """Returns the total number of sessions owned by the authenticated user."""
        filters: Dict[str, Any] = {"user_id": self.user_id}
        if status:
            filters["status"] = status
        return await self.count(filters=filters)


def get_research_session_repository(
    client: PostgrestClient = Depends(get_db_client),
) -> ResearchSessionRepository:
    """FastAPI dependency yielding a user-scoped ResearchSessionRepository."""
    return ResearchSessionRepository(client)
