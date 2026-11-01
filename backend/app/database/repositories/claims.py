"""
Claims Repository for InfoScope AI.
Handles persistence, verification status updates, and confidence filtering for public.claims.
Enforces multi-tenant isolation, source-session integrity, and Supabase RLS.
"""

import uuid
from typing import Dict, Any, List, Optional, Union
from fastapi import Depends

from app.database.client import PostgrestClient, get_db_client
from app.database.repositories.base import BaseRepository
from app.database.exceptions import EntityNotFoundError, DatabaseAuthenticationError


VALID_CLAIM_STATUSES = frozenset({"verified", "conflicting", "unverified", "refuted"})


class ClaimsRepository(BaseRepository):
    """
    Repository for managing public.claims in Supabase PostgREST.
    Ensures claims are linked to valid sources and sessions owned by the authenticated user.
    """

    def __init__(self, client: PostgrestClient):
        super().__init__(client=client, table_name="claims", id_column="id")
        user_id = client.user_id
        if not user_id:
            raise DatabaseAuthenticationError(
                "Cannot initialize ClaimsRepository without verified user credentials."
            )
        self.user_id = user_id

    def _validate_confidence(self, confidence: Any) -> Optional[float]:
        """Validates that confidence_score satisfies CHECK constraint (0.00 <= confidence_score <= 1.00)."""
        if confidence is None:
            return None
        try:
            val = float(confidence)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid confidence_score '{confidence}'. Must be a number between 0.00 and 1.00.")

        if val < 0.0 or val > 1.0:
            raise ValueError(f"Confidence score '{val}' out of bounds. Must be between 0.00 and 1.00.")
        return round(val, 2)

    def _build_claim_payload(
        self,
        session_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validates and constructs schema-compatible payload for claims."""
        claim_text = (data.get("claim_text") or "").strip()
        if not claim_text:
            raise ValueError("claim_text cannot be empty.")

        source_id = data.get("source_id")
        if not source_id:
            raise ValueError("source_id cannot be empty.")

        status = data.get("status") or "unverified"
        if status not in VALID_CLAIM_STATUSES:
            raise ValueError(
                f"Invalid claim status '{status}'. Must be one of {sorted(VALID_CLAIM_STATUSES)}"
            )

        confidence = self._validate_confidence(data.get("confidence_score"))

        payload: Dict[str, Any] = {
            "session_id": str(session_id),
            "source_id": str(source_id),
            "user_id": self.user_id,
            "claim_text": claim_text,
            "context_snippet": data.get("context_snippet"),
            "confidence_score": confidence,
            "status": status,
            "extracted_keywords": data.get("extracted_keywords") or [],
            "metadata": data.get("metadata") or {},
        }
        if "id" in data and data["id"]:
            payload["id"] = str(data["id"])

        return payload

    async def create_claim(
        self,
        session_id: Union[str, uuid.UUID],
        source_id: Union[str, uuid.UUID],
        *,
        claim_text: str,
        context_snippet: Optional[str] = None,
        confidence_score: Optional[float] = None,
        status: str = "unverified",
        extracted_keywords: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        claim_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Creates a single claim associated with a source and session."""
        claim_data = {
            "source_id": source_id,
            "claim_text": claim_text,
            "context_snippet": context_snippet,
            "confidence_score": confidence_score,
            "status": status,
            "extracted_keywords": extracted_keywords,
            "metadata": metadata,
        }
        if claim_id:
            claim_data["id"] = str(claim_id)

        payload = self._build_claim_payload(session_id, claim_data)
        return await self.insert(payload)

    async def create_claims_batch(
        self,
        session_id: Union[str, uuid.UUID],
        claims: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Batch creates multiple claims for a session."""
        if not claims:
            return []
        items = [self._build_claim_payload(session_id, c) for c in claims]
        return await self.insert_many(items)

    async def get_claims_by_session(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        status: Optional[str] = None,
        min_confidence: Optional[float] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: str = "created_at.desc",
    ) -> List[Dict[str, Any]]:
        """Retrieves claims for a session with optional status and confidence filtering."""
        sid = str(session_id)
        filters: Dict[str, Any] = {
            "session_id": sid,
            "user_id": self.user_id,
        }
        if status:
            if status not in VALID_CLAIM_STATUSES:
                raise ValueError(
                    f"Invalid claim status filter '{status}'. Must be one of {sorted(VALID_CLAIM_STATUSES)}"
                )
            filters["status"] = status

        if min_confidence is not None:
            val = self._validate_confidence(min_confidence)
            filters["confidence_score"] = f"gte.{val}"

        return await self.list(
            filters=filters,
            limit=limit,
            offset=offset,
            order=order,
        )

    async def get_claim_by_id(
        self,
        claim_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Retrieves a single claim by primary key and verified user_id."""
        cid = str(claim_id)
        params: Dict[str, Any] = {
            "id": f"eq.{cid}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        records = await self.client.get(self.table_name, params=params)
        if not records or not isinstance(records, list) or len(records) == 0:
            raise EntityNotFoundError(f"Claim '{cid}' was not found.")
        return records[0]

    async def get_claims_by_source(
        self,
        source_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
        *,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves all claims extracted from a specific source."""
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

    async def update_claim(
        self,
        claim_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Updates claim fields, sanitizing un-updatable keys."""
        if not data:
            raise ValueError("Update data cannot be empty.")

        safe_data = {
            k: v for k, v in data.items()
            if k not in ("id", "session_id", "user_id", "created_at", "updated_at")
        }
        if not safe_data:
            raise ValueError("No updatable fields provided.")

        if "status" in safe_data and safe_data["status"] not in VALID_CLAIM_STATUSES:
            raise ValueError(
                f"Invalid claim status '{safe_data['status']}'. Must be one of {sorted(VALID_CLAIM_STATUSES)}"
            )

        if "confidence_score" in safe_data and safe_data["confidence_score"] is not None:
            safe_data["confidence_score"] = self._validate_confidence(safe_data["confidence_score"])

        cid = str(claim_id)
        params: Dict[str, Any] = {
            "id": f"eq.{cid}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        result = await self.client.patch(
            self.table_name,
            json=safe_data,
            params=params,
            headers={"Prefer": "return=representation"},
        )
        if isinstance(result, list) and len(result) > 0:
            return result[0]
        raise EntityNotFoundError(f"Claim '{cid}' was not found.")

    async def update_claim_status(
        self,
        claim_id: Union[str, uuid.UUID],
        status: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Convenience method for updating the verification status of a claim."""
        return await self.update_claim(claim_id, {"status": status}, session_id=session_id)

    async def delete_claim(
        self,
        claim_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Deletes a claim by primary key and verified user_id."""
        cid = str(claim_id)
        params: Dict[str, Any] = {
            "id": f"eq.{cid}",
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
        raise EntityNotFoundError(f"Claim '{cid}' was not found.")


def get_claims_repository(
    client: PostgrestClient = Depends(get_db_client),
) -> ClaimsRepository:
    """FastAPI dependency yielding a user-scoped ClaimsRepository."""
    return ClaimsRepository(client)
