"""
Issues Repository for InfoScope AI.
Handles persistence, filtering, and status transitions for detected contradictions, gaps, and ambiguities.
Enforces multi-tenant isolation and composite session foreign keys.
"""

import uuid
from typing import Dict, Any, List, Optional, Union
from fastapi import Depends

from app.database.client import PostgrestClient, get_db_client
from app.database.repositories.base import BaseRepository
from app.database.exceptions import EntityNotFoundError, DatabaseAuthenticationError


VALID_ISSUE_TYPES = frozenset({"contradiction", "unbacked_claim", "gap", "outdated_source", "ambiguity"})
VALID_SEVERITIES = frozenset({"low", "medium", "high", "critical"})
VALID_ISSUE_STATUSES = frozenset({"open", "investigating", "resolved", "dismissed"})


class IssuesRepository(BaseRepository):
    """
    Repository for managing public.issues in Supabase PostgREST.
    Guarantees user isolation and validates issue types, severities, and lifecycle states.
    """

    def __init__(self, client: PostgrestClient):
        super().__init__(client=client, table_name="issues", id_column="id")
        user_id = client.user_id
        if not user_id:
            raise DatabaseAuthenticationError(
                "Cannot initialize IssuesRepository without verified user credentials."
            )
        self.user_id = user_id

    def _build_issue_payload(
        self,
        session_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validates and constructs schema-compatible payload for issues."""
        issue_type = data.get("issue_type")
        if issue_type not in VALID_ISSUE_TYPES:
            raise ValueError(
                f"Invalid issue_type '{issue_type}'. Must be one of {sorted(VALID_ISSUE_TYPES)}"
            )

        severity = data.get("severity") or "medium"
        if severity not in VALID_SEVERITIES:
            raise ValueError(
                f"Invalid severity '{severity}'. Must be one of {sorted(VALID_SEVERITIES)}"
            )

        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("title cannot be empty.")

        description = (data.get("description") or "").strip()
        if not description:
            raise ValueError("description cannot be empty.")

        status = data.get("status") or "open"
        if status not in VALID_ISSUE_STATUSES:
            raise ValueError(
                f"Invalid issue status '{status}'. Must be one of {sorted(VALID_ISSUE_STATUSES)}"
            )

        payload: Dict[str, Any] = {
            "session_id": str(session_id),
            "user_id": self.user_id,
            "issue_type": issue_type,
            "severity": severity,
            "title": title,
            "description": description,
            "status": status,
            "metadata": data.get("metadata") or {},
        }
        if "id" in data and data["id"]:
            payload["id"] = str(data["id"])

        return payload

    async def create_issue(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        issue_type: str,
        title: str,
        description: str,
        severity: str = "medium",
        status: str = "open",
        metadata: Optional[Dict[str, Any]] = None,
        issue_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Creates a single detected issue for a session."""
        issue_data = {
            "issue_type": issue_type,
            "severity": severity,
            "title": title,
            "description": description,
            "status": status,
            "metadata": metadata,
        }
        if issue_id:
            issue_data["id"] = str(issue_id)

        payload = self._build_issue_payload(session_id, issue_data)
        return await self.insert(payload)

    async def get_issues_by_session(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        issue_type: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: str = "created_at.desc",
    ) -> List[Dict[str, Any]]:
        """Retrieves issues for a session with optional filtering by type, severity, and status."""
        sid = str(session_id)
        filters: Dict[str, Any] = {
            "session_id": sid,
            "user_id": self.user_id,
        }
        if issue_type:
            if issue_type not in VALID_ISSUE_TYPES:
                raise ValueError(
                    f"Invalid issue_type filter '{issue_type}'. Must be one of {sorted(VALID_ISSUE_TYPES)}"
                )
            filters["issue_type"] = issue_type

        if severity:
            if severity not in VALID_SEVERITIES:
                raise ValueError(
                    f"Invalid severity filter '{severity}'. Must be one of {sorted(VALID_SEVERITIES)}"
                )
            filters["severity"] = severity

        if status:
            if status not in VALID_ISSUE_STATUSES:
                raise ValueError(
                    f"Invalid status filter '{status}'. Must be one of {sorted(VALID_ISSUE_STATUSES)}"
                )
            filters["status"] = status

        return await self.list(
            filters=filters,
            limit=limit,
            offset=offset,
            order=order,
        )

    async def get_issue_by_id(
        self,
        issue_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Retrieves an issue by primary key and verified user_id."""
        iid = str(issue_id)
        params: Dict[str, Any] = {
            "id": f"eq.{iid}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        records = await self.client.get(self.table_name, params=params)
        if not records or not isinstance(records, list) or len(records) == 0:
            raise EntityNotFoundError(f"Issue '{iid}' was not found.")
        return records[0]

    async def update_issue(
        self,
        issue_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Updates issue details, sanitizing un-updatable keys."""
        if not data:
            raise ValueError("Update data cannot be empty.")

        safe_data = {
            k: v for k, v in data.items()
            if k not in ("id", "session_id", "user_id", "created_at", "updated_at")
        }
        if not safe_data:
            raise ValueError("No updatable fields provided.")

        if "issue_type" in safe_data and safe_data["issue_type"] not in VALID_ISSUE_TYPES:
            raise ValueError(
                f"Invalid issue_type '{safe_data['issue_type']}'. Must be one of {sorted(VALID_ISSUE_TYPES)}"
            )

        if "severity" in safe_data and safe_data["severity"] not in VALID_SEVERITIES:
            raise ValueError(
                f"Invalid severity '{safe_data['severity']}'. Must be one of {sorted(VALID_SEVERITIES)}"
            )

        if "status" in safe_data and safe_data["status"] not in VALID_ISSUE_STATUSES:
            raise ValueError(
                f"Invalid issue status '{safe_data['status']}'. Must be one of {sorted(VALID_ISSUE_STATUSES)}"
            )

        iid = str(issue_id)
        params: Dict[str, Any] = {
            "id": f"eq.{iid}",
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
        raise EntityNotFoundError(f"Issue '{iid}' was not found.")

    async def update_issue_status(
        self,
        issue_id: Union[str, uuid.UUID],
        status: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Convenience method for updating the lifecycle status of an issue."""
        return await self.update_issue(issue_id, {"status": status}, session_id=session_id)

    async def delete_issue(
        self,
        issue_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Deletes an issue by primary key and verified user_id."""
        iid = str(issue_id)
        params: Dict[str, Any] = {
            "id": f"eq.{iid}",
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
        raise EntityNotFoundError(f"Issue '{iid}' was not found.")

    async def get_issue_evidence(
        self,
        issue_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieves all evidence records associated with this issue."""
        iid = str(issue_id)
        params: Dict[str, Any] = {
            "issue_id": f"eq.{iid}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        records = await self.client.get("issue_evidence", params=params)
        return records if isinstance(records, list) else []


def get_issues_repository(
    client: PostgrestClient = Depends(get_db_client),
) -> IssuesRepository:
    """FastAPI dependency yielding a user-scoped IssuesRepository."""
    return IssuesRepository(client)
