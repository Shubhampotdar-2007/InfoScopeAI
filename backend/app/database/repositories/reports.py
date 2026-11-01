"""
Reports Repository for InfoScope AI.
Handles persistence, metrics updates, and analytical findings for public.reports.
Enforces multi-tenant isolation, composite session foreign keys, and Supabase RLS.
"""

import uuid
from typing import Dict, Any, List, Optional, Union
from fastapi import Depends

from app.database.client import PostgrestClient, get_db_client
from app.database.repositories.base import BaseRepository
from app.database.exceptions import EntityNotFoundError, DatabaseAuthenticationError


VALID_REPORT_STATUSES = frozenset({"draft", "final", "archived"})


class ReportsRepository(BaseRepository):
    """
    Repository for managing public.reports in Supabase PostgREST.
    Ensures synthesized reports are bound to the authenticated user and valid sessions.
    """

    def __init__(self, client: PostgrestClient):
        super().__init__(client=client, table_name="reports", id_column="id")
        user_id = client.user_id
        if not user_id:
            raise DatabaseAuthenticationError(
                "Cannot initialize ReportsRepository without verified user credentials."
            )
        self.user_id = user_id

    def _validate_coverage_score(self, score: Any) -> int:
        """Validates that coverage_score satisfies CHECK constraint (0 <= score <= 100)."""
        try:
            val = int(score)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid coverage_score '{score}'. Must be an integer between 0 and 100.")

        if val < 0 or val > 100:
            raise ValueError(f"coverage_score '{val}' out of bounds. Must be between 0 and 100.")
        return val

    def _validate_metric_counter(self, name: str, counter: Any) -> int:
        """Validates that counter metrics are non-negative integers."""
        try:
            val = int(counter)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid {name} '{counter}'. Must be a non-negative integer.")

        if val < 0:
            raise ValueError(f"{name} '{val}' cannot be negative.")
        return val

    def _build_report_payload(
        self,
        session_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Validates and constructs schema-compatible payload for reports."""
        executive_summary = (data.get("executive_summary") or "").strip()
        if not executive_summary:
            raise ValueError("executive_summary cannot be empty.")

        status = data.get("status") or "draft"
        if status not in VALID_REPORT_STATUSES:
            raise ValueError(
                f"Invalid report status '{status}'. Must be one of {sorted(VALID_REPORT_STATUSES)}"
            )

        coverage_score = self._validate_coverage_score(data.get("coverage_score", 0))

        total_claims = self._validate_metric_counter("total_claims", data.get("total_claims", 0))
        verified_claims = self._validate_metric_counter("verified_claims", data.get("verified_claims", 0))
        conflicting_claims = self._validate_metric_counter("conflicting_claims", data.get("conflicting_claims", 0))
        unbacked_claims = self._validate_metric_counter("unbacked_claims", data.get("unbacked_claims", 0))
        identified_gaps = self._validate_metric_counter("identified_gaps", data.get("identified_gaps", 0))

        findings = data.get("findings")
        if findings is None or not isinstance(findings, dict):
            findings = {}

        recommendations = data.get("recommendations")
        if recommendations is None or not isinstance(recommendations, list):
            recommendations = []

        payload: Dict[str, Any] = {
            "session_id": str(session_id),
            "user_id": self.user_id,
            "title": data.get("title") or "Research Synthesis Report",
            "executive_summary": executive_summary,
            "coverage_score": coverage_score,
            "total_claims": total_claims,
            "verified_claims": verified_claims,
            "conflicting_claims": conflicting_claims,
            "unbacked_claims": unbacked_claims,
            "identified_gaps": identified_gaps,
            "findings": findings,
            "recommendations": recommendations,
            "status": status,
        }
        if "id" in data and data["id"]:
            payload["id"] = str(data["id"])

        return payload

    async def create_report(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        executive_summary: str,
        title: str = "Research Synthesis Report",
        coverage_score: int = 0,
        total_claims: int = 0,
        verified_claims: int = 0,
        conflicting_claims: int = 0,
        unbacked_claims: int = 0,
        identified_gaps: int = 0,
        findings: Optional[Dict[str, Any]] = None,
        recommendations: Optional[List[Any]] = None,
        status: str = "draft",
        report_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Creates a synthesized research report for a session."""
        report_data = {
            "title": title,
            "executive_summary": executive_summary,
            "coverage_score": coverage_score,
            "total_claims": total_claims,
            "verified_claims": verified_claims,
            "conflicting_claims": conflicting_claims,
            "unbacked_claims": unbacked_claims,
            "identified_gaps": identified_gaps,
            "findings": findings,
            "recommendations": recommendations,
            "status": status,
        }
        if report_id:
            report_data["id"] = str(report_id)

        payload = self._build_report_payload(session_id, report_data)
        return await self.insert(payload)

    async def get_reports_by_session(
        self,
        session_id: Union[str, uuid.UUID],
        *,
        status: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: str = "created_at.desc",
    ) -> List[Dict[str, Any]]:
        """Retrieves reports for a session with optional status filtering."""
        sid = str(session_id)
        filters: Dict[str, Any] = {
            "session_id": sid,
            "user_id": self.user_id,
        }
        if status:
            if status not in VALID_REPORT_STATUSES:
                raise ValueError(
                    f"Invalid report status filter '{status}'. Must be one of {sorted(VALID_REPORT_STATUSES)}"
                )
            filters["status"] = status

        return await self.list(
            filters=filters,
            limit=limit,
            offset=offset,
            order=order,
        )

    async def get_report_by_id(
        self,
        report_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Retrieves a single report by primary key and verified user_id."""
        rid = str(report_id)
        params: Dict[str, Any] = {
            "id": f"eq.{rid}",
            "user_id": f"eq.{self.user_id}",
        }
        if session_id:
            params["session_id"] = f"eq.{session_id}"

        records = await self.client.get(self.table_name, params=params)
        if not records or not isinstance(records, list) or len(records) == 0:
            raise EntityNotFoundError(f"Report '{rid}' was not found.")
        return records[0]

    async def update_report(
        self,
        report_id: Union[str, uuid.UUID],
        data: Dict[str, Any],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Updates report details, sanitizing un-updatable keys."""
        if not data:
            raise ValueError("Update data cannot be empty.")

        safe_data = {
            k: v for k, v in data.items()
            if k not in ("id", "session_id", "user_id", "created_at", "updated_at")
        }
        if not safe_data:
            raise ValueError("No updatable fields provided.")

        if "status" in safe_data and safe_data["status"] not in VALID_REPORT_STATUSES:
            raise ValueError(
                f"Invalid report status '{safe_data['status']}'. Must be one of {sorted(VALID_REPORT_STATUSES)}"
            )

        if "coverage_score" in safe_data:
            safe_data["coverage_score"] = self._validate_coverage_score(safe_data["coverage_score"])

        for metric in ("total_claims", "verified_claims", "conflicting_claims", "unbacked_claims", "identified_gaps"):
            if metric in safe_data:
                safe_data[metric] = self._validate_metric_counter(metric, safe_data[metric])

        rid = str(report_id)
        params: Dict[str, Any] = {
            "id": f"eq.{rid}",
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
        raise EntityNotFoundError(f"Report '{rid}' was not found.")

    async def update_metrics(
        self,
        report_id: Union[str, uuid.UUID],
        *,
        coverage_score: Optional[int] = None,
        total_claims: Optional[int] = None,
        verified_claims: Optional[int] = None,
        conflicting_claims: Optional[int] = None,
        unbacked_claims: Optional[int] = None,
        identified_gaps: Optional[int] = None,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Convenience method for updating coverage score and numerical claim metrics."""
        metrics: Dict[str, Any] = {}
        if coverage_score is not None:
            metrics["coverage_score"] = coverage_score
        if total_claims is not None:
            metrics["total_claims"] = total_claims
        if verified_claims is not None:
            metrics["verified_claims"] = verified_claims
        if conflicting_claims is not None:
            metrics["conflicting_claims"] = conflicting_claims
        if unbacked_claims is not None:
            metrics["unbacked_claims"] = unbacked_claims
        if identified_gaps is not None:
            metrics["identified_gaps"] = identified_gaps

        return await self.update_report(report_id, metrics, session_id=session_id)

    async def update_status(
        self,
        report_id: Union[str, uuid.UUID],
        status: str,
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Convenience method for transitioning report status (draft, final, archived)."""
        return await self.update_report(report_id, {"status": status}, session_id=session_id)

    async def delete_report(
        self,
        report_id: Union[str, uuid.UUID],
        session_id: Optional[Union[str, uuid.UUID]] = None,
    ) -> Dict[str, Any]:
        """Deletes a report by primary key and verified user_id."""
        rid = str(report_id)
        params: Dict[str, Any] = {
            "id": f"eq.{rid}",
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
        raise EntityNotFoundError(f"Report '{rid}' was not found.")


def get_reports_repository(
    client: PostgrestClient = Depends(get_db_client),
) -> ReportsRepository:
    """FastAPI dependency yielding a user-scoped ReportsRepository."""
    return ReportsRepository(client)
