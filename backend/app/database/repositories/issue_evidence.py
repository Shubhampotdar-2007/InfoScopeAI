"""
Issue Evidence Repository for InfoScope AI.
Handles persistence, linking, and polarity tracking for public.issue_evidence.
Enforces multi-tenant isolation, composite session foreign keys, and Supabase RLS.
"""

import uuid
from typing import Dict, Any, List, Optional, Union
from fastapi import Depends

from app.database.client import PostgrestClient, get_db_client
from app.database.repositories.base import BaseRepository
from app.database.exceptions import EntityNotFoundError, DatabaseAuthenticationError


VALID_EVIDENCE_POLARITIES = frozenset({"supports", "contradicts", "neutral", "unbacked"})


class IssueEvidenceRepository(BaseRepository):
    """
    Repository for managing public.issue_evidence in Supabase PostgREST.
    Ensures evidence links issues, claims, and sources within the same authenticated user session.
    """

    def __init__(self, client: PostgrestClient):
        super().__init__(client=client, table_name="issue_evidence", id_column="id")
        user_id = client.user_id
        if not user_id:
            raise DatabaseAuthenticationError(
                "Cannot initialize IssueEvidenceRepository without verified user credentials."
            )
        self.user_id = user_id

    def _build_evidence_payload(
        self,
        session_id: Union[str, uuid.UUID],
        issue_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validates and constructs schema-compatible payload for issue_evidence."""
        source_id = data.get("source_id")
        if not source_id:
            raise ValueError("source_id cannot be empty.")

        evidence_text = (data.get("evidence_text") or "").strip()
        if not evidence_text:
            raise ValueError("evidence_text cannot be empty.")

        polarity = data.get("polarity") or "contradicts"
        if polarity not in VALID_EVIDENCE_POLARITIES:
            raise ValueError(
                f"Invalid polarity '{polarity}'. Must be one of {sorted(VALID_EVIDENCE_POLARITIES)}"
            )

        payload: Dict[str, Any] = {
            "session_id": str(session_id),
            "issue_id": str(issue_id),
            "source_id": str(source_id),
            "user_id": self.user_id,
            "polarity": polarity,
            "evidence_text": evidence_text,
            "explanation": data.get("explanation"),
        }
        if data.get("claim_id"):
            payload["claim_id"] = str(data["claim_id"])
        if "id" in data and data["id"]:
            payload["id"] = str(data["id"])

        return payload

    async def create_evidence(
        self,
        session_id: Union[str, uuid.UUID],
        issue_id: Union[str, uuid.UUID],
        source_id: Union[str, uuid.UUID],
        *,
        evidence_text: str,
        polarity: str = "contradicts",
        claim_id: Optional[Union[str, uuid.UUID]] = None,
        explanation: Optional[str] = None,
        evidence_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Creates a single evidence entry linking an issue to a source/claim."""
        data = {
            "source_id": source_id,
            "claim_id": claim_id,
            "polarity": polarity,
            "evidence_text": evidence_text,
            "explanation": explanation,
        }
        if evidence_id:
            data["id"] = str(evidence_id)

        payload = self._build_evidence_payload(session_id, issue_id, data)
        return await self.insert(payload)

    async def create_evidence_batch(
        self,
        session_id: Union[str, uuid.UUID],
        issue_id: Union[str, uuid.UUID],
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Batch creates multiple evidence entries for an issue."""
        if not items:
            return []
        payloads = [self._build_evidence_payload(session_id, issue_id, item) for item in items]
        return await self.insert_many(payloads)

    async def get_evidence_by_issue(
        self,
        issue_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves all evidence associated with a specific issue."""
        iid = str(issue_id)
        filters: Dict[str, Any] = {
            "issue_id": iid,
            "user_id": self.user_id,
        }
        if session_id:
            filters["session_id"] = str(session_id)

        return await self.list(
            filters=filters,
            limit=limit,
            offset=offset,
            order="created_at.asc",
        )

    async def get_evidence_by_source(
        self,
        source_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves all evidence linked to a specific research source."""
        src_id = str(source_id)
        filters: Dict[str, Any] = {
            "source_id": src_id,
            "user_id": self.user_id,
        }
        if session_id:
            filters["session_id"] = str(session_id)

        return await self.list(
            filters=filters,
            limit=limit,
            offset=offset,
            order="created_at.asc",
        )

    async def get_evidence_by_id(
        self,
        evidence_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Retrieves a single evidence record by primary key and verified user_id."""
        eid = str(evidence_id)
        params: Dict[str, Any] = {
            "id": f"eq.{eid}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        records = await self.client.get(self.table_name, params=params)
        if not records or not isinstance(records, list) or len(records) == 0:
            raise EntityNotFoundError(f"Issue evidence '{eid}' was not found.")
        return records[0]

    async def delete_evidence(
        self,
        evidence_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Deletes an evidence entry by primary key and verified user_id."""
        eid = str(evidence_id)
        params: Dict[str, Any] = {
            "id": f"eq.{eid}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        result = await self.client.delete(
            self.table_name,
            params=params,
            headers={"Prefer": "return=representation"},
        )
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        raise EntityNotFoundError(f"Issue evidence '{eid}' was not found.")


def get_issue_evidence_repository(
    client: PostgrestClient = Depends(get_db_client),
) -> IssueEvidenceRepository:
    """FastAPI dependency yielding a user-scoped IssueEvidenceRepository."""
    return IssueEvidenceRepository(client)
