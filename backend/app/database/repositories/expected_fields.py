"""
Expected Fields Repository for InfoScope AI.
Handles CRUD, coverage criteria tracking, and completeness scoring for public.expected_fields.
Enforces multi-tenant isolation via authenticated user ID derivation and RLS.
"""

import uuid
from decimal import Decimal
from typing import Dict, Any, List, Optional, Union
from fastapi import Depends

from app.database.client import PostgrestClient, get_db_client
from app.database.repositories.base import BaseRepository
from app.database.exceptions import EntityNotFoundError, DatabaseAuthenticationError


VALID_EXPECTED_FIELD_STATUSES = frozenset({"missing", "partially_covered", "covered"})


class ExpectedFieldsRepository(BaseRepository):
    """
    Repository for managing public.expected_fields in Supabase PostgREST.
    Guarantees user isolation and validates weights according to database constraints.
    """

    def __init__(self, client: PostgrestClient):
        super().__init__(client=client, table_name="expected_fields", id_column="id")
        user_id = client.user_id
        if not user_id:
            raise DatabaseAuthenticationError(
                "Cannot initialize ExpectedFieldsRepository without verified user credentials."
            )
        self.user_id = user_id

    def _validate_weight(self, weight: Any) -> float:
        """Validates that weight satisfies the CHECK constraint (0.00 <= weight <= 5.00)."""
        try:
            val = float(weight)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid weight '{weight}'. Must be a number between 0.00 and 5.00.")

        if val < 0.0 or val > 5.0:
            raise ValueError(f"Weight '{val}' out of bounds. Must be between 0.00 and 5.00.")
        return val

    def _build_field_payload(
        self,
        session_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validates and constructs schema-compatible payload for expected_fields."""
        field_name = (data.get("field_name") or "").strip()
        if not field_name:
            raise ValueError("field_name cannot be empty.")

        status = data.get("status") or "missing"
        if status not in VALID_EXPECTED_FIELD_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of {sorted(VALID_EXPECTED_FIELD_STATUSES)}"
            )

        weight = self._validate_weight(data.get("weight", 1.00))

        payload: Dict[str, Any] = {
            "session_id": str(session_id),
            "user_id": self.user_id,
            "field_name": field_name,
            "field_category": data.get("field_category") or "general",
            "description": data.get("description"),
            "is_required": bool(data.get("is_required", True)),
            "weight": round(weight, 2),
            "status": status,
        }
        if "id" in data and data["id"]:
            payload["id"] = str(data["id"])

        return payload

    async def create_expected_field(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        field_name: str,
        field_category: str = "general",
        description: Optional[str] = None,
        is_required: bool = True,
        weight: float = 1.00,
        status: str = "missing",
        field_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Creates a single expected research field for a session."""
        field_data = {
            "field_name": field_name,
            "field_category": field_category,
            "description": description,
            "is_required": is_required,
            "weight": weight,
            "status": status,
        }
        if field_id:
            field_data["id"] = str(field_id)

        payload = self._build_field_payload(session_id, field_data)
        return await self.insert(payload)

    async def create_expected_fields_batch(
        self,
        session_id: Union[str, uuid.UUID],
        fields: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Batch creates multiple expected fields for a session."""
        if not fields:
            return []
        items = [self._build_field_payload(session_id, f) for f in fields]
        return await self.insert_many(items)

    async def get_fields_by_session(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: str = "created_at.asc",
    ) -> List[Dict[str, Any]]:
        """Retrieves expected fields for a session owned by the authenticated user."""
        sid = str(session_id)
        filters: Dict[str, Any] = {
            "session_id": sid,
            "user_id": self.user_id,
        }
        if status:
            if status not in VALID_EXPECTED_FIELD_STATUSES:
                raise ValueError(
                    f"Invalid status filter '{status}'. Must be one of {sorted(VALID_EXPECTED_FIELD_STATUSES)}"
                )
            filters["status"] = status

        return await self.list(
            filters=filters,
            limit=limit,
            offset=offset,
            order=order,
        )

    async def get_field_by_id(
        self,
        field_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Retrieves an expected field by primary key and verified user_id."""
        fid = str(field_id)
        params: Dict[str, Any] = {
            "id": f"eq.{fid}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        records = await self.client.get(self.table_name, params=params)
        if not records or not isinstance(records, list) or len(records) == 0:
            raise EntityNotFoundError(f"Expected field '{fid}' was not found.")
        return records[0]

    async def update_expected_field(
        self,
        field_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Updates expected field details, sanitizing un-updatable keys."""
        if not data:
            raise ValueError("Update data cannot be empty.")

        safe_data = {
            k: v for k, v in data.items()
            if k not in ("id", "session_id", "user_id", "created_at", "updated_at")
        }
        if not safe_data:
            raise ValueError("No updatable fields provided.")

        if "status" in safe_data and safe_data["status"] not in VALID_EXPECTED_FIELD_STATUSES:
            raise ValueError(
                f"Invalid status '{safe_data['status']}'. Must be one of {sorted(VALID_EXPECTED_FIELD_STATUSES)}"
            )

        if "weight" in safe_data:
            safe_data["weight"] = self._validate_weight(safe_data["weight"])

        fid = str(field_id)
        params: Dict[str, Any] = {
            "id": f"eq.{fid}",
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
        raise EntityNotFoundError(f"Expected field '{fid}' was not found.")

    async def update_coverage_status(
        self,
        field_id: Union[str, uuid.UUID],
        status: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Convenience method for updating the status of an expected field."""
        return await self.update_expected_field(field_id, {"status": status}, session_id=session_id)

    async def delete_expected_field(
        self,
        field_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Deletes an expected field by primary key and verified user_id."""
        fid = str(field_id)
        params: Dict[str, Any] = {
            "id": f"eq.{fid}",
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
        raise EntityNotFoundError(f"Expected field '{fid}' was not found.")

    async def calculate_coverage_statistics(
        self,
        session_id: Union[str, uuid.UUID],
    ) -> Dict[str, Any]:
        """
        Calculates completeness and weighted coverage statistics for all fields in a session.
        Returns total_fields, status counts, total weight, and coverage_score (0-100).
        """
        fields = await self.get_fields_by_session(session_id)
        total_fields = len(fields)
        if total_fields == 0:
            return {
                "total_fields": 0,
                "covered_fields": 0,
                "partially_covered_fields": 0,
                "missing_fields": 0,
                "coverage_score": 0,
                "total_weight": 0.0,
                "covered_weight": 0.0,
            }

        covered_count = 0
        partially_covered_count = 0
        missing_count = 0
        total_weight = 0.0
        weighted_points = 0.0

        for f in fields:
            w = float(f.get("weight") or 1.0)
            st = f.get("status")
            total_weight += w

            if st == "covered":
                covered_count += 1
                weighted_points += w
            elif st == "partially_covered":
                partially_covered_count += 1
                weighted_points += w * 0.5
            else:
                missing_count += 1

        score = round((weighted_points / total_weight) * 100) if total_weight > 0 else 0
        score = max(0, min(100, score))

        return {
            "total_fields": total_fields,
            "covered_fields": covered_count,
            "partially_covered_fields": partially_covered_count,
            "missing_fields": missing_count,
            "coverage_score": score,
            "total_weight": round(total_weight, 2),
            "covered_weight": round(weighted_points, 2),
        }


def get_expected_fields_repository(
    client: PostgrestClient = Depends(get_db_client),
) -> ExpectedFieldsRepository:
    """FastAPI dependency yielding a user-scoped ExpectedFieldsRepository."""
    return ExpectedFieldsRepository(client)
