"""
Research Source Repository for InfoScope AI.
Handles source persistence, cross-provider canonical URL deduplication, and session queries.
Enforces multi-tenant isolation and composite foreign key integrity.
"""

import uuid
from typing import Dict, Any, List, Optional, Union, Set
from fastapi import Depends

from app.database.client import PostgrestClient, get_db_client
from app.database.repositories.base import BaseRepository
from app.database.exceptions import EntityNotFoundError, DatabaseAuthenticationError


class ResearchSourceRepository(BaseRepository):
    """
    Repository for managing public.research_sources in Supabase PostgREST.
    Strictly derives user_id from the verified AuthenticatedUser and enforces
    composite foreign key consistency with research_sessions(id, user_id).
    """

    def __init__(self, client: PostgrestClient):
        super().__init__(client=client, table_name="research_sources", id_column="id")
        user_id = client.user_id
        if not user_id:
            raise DatabaseAuthenticationError(
                "Cannot initialize ResearchSourceRepository without verified user credentials."
            )
        self.user_id = user_id

    def _build_source_payload(
        self,
        session_id: Union[str, uuid.UUID],
        source: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Validates and normalizes source dictionary into schema-compatible payload.
        Ensures user_id and session_id are strictly bound to the authenticated user context.
        """
        url = (source.get("url") or "").strip()
        if not url:
            raise ValueError("Source 'url' cannot be empty.")

        canonical_url = (source.get("canonical_url") or url).strip()

        payload: Dict[str, Any] = {
            "session_id": str(session_id),
            "user_id": self.user_id,
            "url": url,
            "canonical_url": canonical_url,
            "title": source.get("title") or "Untitled Source",
            "snippet": source.get("snippet"),
            "score": source.get("score"),
            "providers": source.get("providers") or ["tavily"],
            "metadata": source.get("metadata") or {},
        }
        if "id" in source and source["id"]:
            payload["id"] = str(source["id"])

        return payload

    async def insert_source(
        self,
        session_id: Union[str, uuid.UUID],
        source: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Inserts a single research source for a given session.
        Respects composite foreign key (session_id, user_id) -> research_sessions(id, user_id).
        """
        payload = self._build_source_payload(session_id, source)
        return await self.insert(payload)

    async def insert_sources_batch(
        self,
        session_id: Union[str, uuid.UUID],
        sources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Batch inserts multiple sources for a given session.
        Ensures all items are strictly bound to the authenticated user.
        """
        if not sources:
            return []
        items = [self._build_source_payload(session_id, s) for s in sources]
        return await self.insert_many(items)

    async def get_sources_by_session(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: str = "created_at.asc",
    ) -> List[Dict[str, Any]]:
        """
        Retrieves all sources belonging to a research session owned by the authenticated user.
        Supports pagination and ordering.
        """
        sid = str(session_id)
        filters = {
            "session_id": sid,
            "user_id": self.user_id,
        }
        return await self.list(
            filters=filters,
            limit=limit,
            offset=offset,
            order=order,
        )

    async def get_source_by_id(
        self,
        source_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves a single source by ID, scoped to the authenticated user and optional session.
        Raises EntityNotFoundError if not found.
        """
        src_id = str(source_id)
        params: Dict[str, Any] = {
            "id": f"eq.{src_id}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        records = await self.client.get(self.table_name, params=params)
        if not records or not isinstance(records, list) or len(records) == 0:
            raise EntityNotFoundError(f"Research source '{src_id}' was not found.")
        return records[0]

    async def get_existing_canonical_urls(
        self,
        session_id: Union[str, uuid.UUID],
    ) -> Set[str]:
        """
        Returns the set of all canonical URLs currently stored for the specified session.
        Used for fast deduplication before ingesting new sources.
        """
        sid = str(session_id)
        records = await self.client.get(
            self.table_name,
            params={
                "session_id": f"eq.{sid}",
                "user_id": f"eq.{self.user_id}",
                "select": "canonical_url",
            },
        )
        if not records or not isinstance(records, list):
            return set()
        return {
            r["canonical_url"]
            for r in records
            if isinstance(r, dict) and "canonical_url" in r and r["canonical_url"]
        }

    async def insert_sources_deduplicated(
        self,
        session_id: Union[str, uuid.UUID],
        sources: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Deduplicates sources by canonical_url against both the database and intra-batch,
        then inserts only the new unique sources.
        Returns the list of newly created source records.
        """
        if not sources:
            return []

        existing_urls = await self.get_existing_canonical_urls(session_id)
        seen_urls = set(existing_urls)
        unique_to_insert: List[Dict[str, Any]] = []

        for src in sources:
            url = (src.get("url") or "").strip()
            c_url = (src.get("canonical_url") or url).strip()
            if not c_url:
                continue

            if c_url in seen_urls:
                continue

            seen_urls.add(c_url)
            unique_to_insert.append(src)

        if not unique_to_insert:
            return []

        return await self.insert_sources_batch(session_id, unique_to_insert)

    async def count_sources_by_session(
        self,
        session_id: Union[str, uuid.UUID],
    ) -> int:
        """Returns the total number of sources stored for a session."""
        sid = str(session_id)
        return await self.count(filters={"session_id": sid, "user_id": self.user_id})


def get_research_source_repository(
    client: PostgrestClient = Depends(get_db_client),
) -> ResearchSourceRepository:
    """FastAPI dependency yielding a user-scoped ResearchSourceRepository."""
    return ResearchSourceRepository(client)
