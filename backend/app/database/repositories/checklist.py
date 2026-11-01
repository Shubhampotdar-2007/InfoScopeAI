"""
Checklist Repository for InfoScope AI.
Handles persistence, verification status tracking, completion timestamps, and reopening for public.checklist_items.
Enforces multi-tenant isolation, cross-session issue consistency, and Supabase RLS.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from fastapi import Depends

from app.database.client import PostgrestClient, get_db_client
from app.database.repositories.base import BaseRepository
from app.database.exceptions import EntityNotFoundError, DatabaseAuthenticationError


VALID_CHECKLIST_PRIORITIES = frozenset({"low", "medium", "high", "urgent"})
VALID_CHECKLIST_STATUSES = frozenset({"pending", "in_progress", "completed", "skipped"})


class ChecklistRepository(BaseRepository):
    """
    Repository for managing public.checklist_items in Supabase PostgREST.
    Guarantees user isolation and manages task completion lifecycle and timestamps.
    """

    def __init__(self, client: PostgrestClient):
        super().__init__(client=client, table_name="checklist_items", id_column="id")
        user_id = client.user_id
        if not user_id:
            raise DatabaseAuthenticationError(
                "Cannot initialize ChecklistRepository without verified user credentials."
            )
        self.user_id = user_id

    def _build_item_payload(
        self,
        session_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validates and constructs schema-compatible payload for checklist_items."""
        task_description = (data.get("task_description") or "").strip()
        if not task_description:
            raise ValueError("task_description cannot be empty.")

        priority = data.get("priority") or "medium"
        if priority not in VALID_CHECKLIST_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{priority}'. Must be one of {sorted(VALID_CHECKLIST_PRIORITIES)}"
            )

        status = data.get("status") or "pending"
        if status not in VALID_CHECKLIST_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of {sorted(VALID_CHECKLIST_STATUSES)}"
            )

        completed_at = data.get("completed_at")
        if status == "completed" and not completed_at:
            completed_at = datetime.now(timezone.utc).isoformat()
        elif status != "completed":
            completed_at = None

        payload: Dict[str, Any] = {
            "session_id": str(session_id),
            "user_id": self.user_id,
            "task_description": task_description,
            "priority": priority,
            "status": status,
            "verification_notes": data.get("verification_notes"),
            "completed_at": completed_at,
        }
        if data.get("issue_id"):
            payload["issue_id"] = str(data["issue_id"])
        if "id" in data and data["id"]:
            payload["id"] = str(data["id"])

        return payload

    async def create_item(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        task_description: str,
        priority: str = "medium",
        status: str = "pending",
        issue_id: Optional[Union[str, uuid.UUID]] = None,
        verification_notes: Optional[str] = None,
        item_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Creates a single prioritized verification task for a session."""
        item_data = {
            "task_description": task_description,
            "priority": priority,
            "status": status,
            "issue_id": issue_id,
            "verification_notes": verification_notes,
        }
        if item_id:
            item_data["id"] = str(item_id)

        payload = self._build_item_payload(session_id, item_data)
        return await self.insert(payload)

    async def create_items_batch(
        self,
        session_id: Union[str, uuid.UUID],
        items: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Batch creates multiple checklist items for a session."""
        if not items:
            return []
        payloads = [self._build_item_payload(session_id, item) for item in items]
        return await self.insert_many(payloads)

    async def get_items_by_session(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        priority: Optional[str] = None,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: str = "created_at.asc",
    ) -> List[Dict[str, Any]]:
        """Retrieves checklist items for a session with optional priority and status filtering."""
        sid = str(session_id)
        filters: Dict[str, Any] = {
            "session_id": sid,
            "user_id": self.user_id,
        }
        if priority:
            if priority not in VALID_CHECKLIST_PRIORITIES:
                raise ValueError(
                    f"Invalid priority filter '{priority}'. Must be one of {sorted(VALID_CHECKLIST_PRIORITIES)}"
                )
            filters["priority"] = priority

        if status:
            if status not in VALID_CHECKLIST_STATUSES:
                raise ValueError(
                    f"Invalid status filter '{status}'. Must be one of {sorted(VALID_CHECKLIST_STATUSES)}"
                )
            filters["status"] = status

        return await self.list(
            filters=filters,
            limit=limit,
            offset=offset,
            order=order,
        )

    async def get_item_by_id(
        self,
        item_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Retrieves a checklist item by primary key and verified user_id."""
        cid = str(item_id)
        params: Dict[str, Any] = {
            "id": f"eq.{cid}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        records = await self.client.get(self.table_name, params=params)
        if not records or not isinstance(records, list) or len(records) == 0:
            raise EntityNotFoundError(f"Checklist item '{cid}' was not found.")
        return records[0]

    async def update_item(
        self,
        item_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Updates checklist item details, sanitizing un-updatable keys."""
        if not data:
            raise ValueError("Update data cannot be empty.")

        safe_data = {
            k: v for k, v in data.items()
            if k not in ("id", "session_id", "user_id", "created_at", "updated_at")
        }
        if not safe_data:
            raise ValueError("No updatable fields provided.")

        if "priority" in safe_data and safe_data["priority"] not in VALID_CHECKLIST_PRIORITIES:
            raise ValueError(
                f"Invalid priority '{safe_data['priority']}'. Must be one of {sorted(VALID_CHECKLIST_PRIORITIES)}"
            )

        if "status" in safe_data and safe_data["status"] not in VALID_CHECKLIST_STATUSES:
            raise ValueError(
                f"Invalid status '{safe_data['status']}'. Must be one of {sorted(VALID_CHECKLIST_STATUSES)}"
            )

        # Handle completed_at timestamp consistency
        if "status" in safe_data:
            new_status = safe_data["status"]
            if new_status == "completed" and "completed_at" not in safe_data:
                safe_data["completed_at"] = datetime.now(timezone.utc).isoformat()
            elif new_status != "completed":
                safe_data["completed_at"] = None

        cid = str(item_id)
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
        raise EntityNotFoundError(f"Checklist item '{cid}' was not found.")

    async def update_task_description(
        self,
        item_id: Union[str, uuid.UUID],
        task_description: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Updates the task description of a checklist item."""
        desc = (task_description or "").strip()
        if not desc:
            raise ValueError("task_description cannot be empty.")
        return await self.update_item(item_id, {"task_description": desc}, session_id=session_id)

    async def update_priority(
        self,
        item_id: Union[str, uuid.UUID],
        priority: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Updates the priority of a checklist item."""
        return await self.update_item(item_id, {"priority": priority}, session_id=session_id)

    async def update_status(
        self,
        item_id: Union[str, uuid.UUID],
        status: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Updates the status of a checklist item."""
        return await self.update_item(item_id, {"status": status}, session_id=session_id)

    async def update_verification_notes(
        self,
        item_id: Union[str, uuid.UUID],
        notes: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Stores verification notes on a checklist item."""
        return await self.update_item(item_id, {"verification_notes": notes}, session_id=session_id)

    async def mark_completed(
        self,
        item_id: Union[str, uuid.UUID],
        *,
        verification_notes: Optional[str] = None,
        completed_at: Optional[str] = None,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Marks a checklist item as completed and records completion timestamp."""
        ts = completed_at or datetime.now(timezone.utc).isoformat()
        update_data: Dict[str, Any] = {
            "status": "completed",
            "completed_at": ts,
        }
        if verification_notes is not None:
            update_data["verification_notes"] = verification_notes

        return await self.update_item(item_id, update_data, session_id=session_id)

    async def reopen_item(
        self,
        item_id: Union[str, uuid.UUID],
        *,
        status: str = "in_progress",
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Reopens a completed checklist item and clears the completion timestamp."""
        if status not in ("pending", "in_progress"):
            raise ValueError(f"Reopened task status must be 'pending' or 'in_progress', got '{status}'.")

        update_data = {
            "status": status,
            "completed_at": None,
        }
        return await self.update_item(item_id, update_data, session_id=session_id)

    async def delete_item(
        self,
        item_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Deletes a checklist item by primary key and verified user_id."""
        cid = str(item_id)
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
        raise EntityNotFoundError(f"Checklist item '{cid}' was not found.")


def get_checklist_repository(
    client: PostgrestClient = Depends(get_db_client),
) -> ChecklistRepository:
    """FastAPI dependency yielding a user-scoped ChecklistRepository."""
    return ChecklistRepository(client)
