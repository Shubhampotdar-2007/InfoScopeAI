"""
Base Repository for Supabase PostgREST tables.
Provides simple, reusable, type-friendly CRUD operations.
Ensures query parameters are safely encoded and table/column identifiers are strictly validated.
"""

import re
import uuid
from typing import Dict, Any, List, Optional, Union

from app.database.client import PostgrestClient
from app.database.exceptions import EntityNotFoundError, DatabaseError

# Matches valid SQL identifiers (table and column names)
_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Known PostgREST comparison/filter operators
_KNOWN_OPERATORS = (
    "eq.",
    "neq.",
    "gt.",
    "gte.",
    "lt.",
    "lte.",
    "like.",
    "ilike.",
    "is.",
    "in.",
    "cs.",
    "cd.",
    "not.",
)


def validate_identifier(name: str, identifier_type: str = "identifier") -> str:
    """
    Validates that a string is a safe SQL identifier (table name or column name).
    Raises ValueError if the identifier contains invalid characters.
    """
    if not name or not isinstance(name, str) or not _IDENTIFIER_PATTERN.match(name.strip()):
        raise ValueError(
            f"Invalid {identifier_type}: '{name}'. Must consist of alphanumeric characters and underscores only."
        )
    return name.strip()


def format_filter_value(val: Any) -> str:
    """
    Formats a filter value into a valid PostgREST query parameter value.
    Automatically prefixes 'eq.' when no operator is explicitly supplied.
    """
    if val is None:
        return "is.null"
    if isinstance(val, bool):
        return f"eq.{str(val).lower()}"
    if isinstance(val, (int, float)):
        return f"eq.{val}"
    if isinstance(val, (list, tuple, set)):
        items_str = ",".join(str(item) for item in val)
        return f"in.({items_str})"

    val_str = str(val)
    if any(val_str.startswith(op) for op in _KNOWN_OPERATORS):
        return val_str
    return f"eq.{val_str}"


class BaseRepository:
    """
    Generic Base Repository wrapping Supabase PostgREST for a single table.
    Enforces identifier validation and user-scoped query execution via PostgrestClient.
    """

    def __init__(
        self,
        client: PostgrestClient,
        table_name: str,
        id_column: str = "id",
    ):
        self.client = client
        self.table_name = validate_identifier(table_name, "table name")
        self.id_column = validate_identifier(id_column, "id column")

    async def insert(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inserts a single entity and returns the created record.
        Uses PostgREST Prefer: return=representation.
        """
        if not data:
            raise ValueError("Insert payload cannot be empty.")

        for col in data.keys():
            validate_identifier(col, "column identifier")

        result = await self.client.post(
            self.table_name,
            json=data,
            headers={"Prefer": "return=representation"},
        )

        if isinstance(result, list) and len(result) > 0:
            return result[0]
        if isinstance(result, dict):
            return result

        raise DatabaseError(
            f"Failed to retrieve representation after inserting into '{self.table_name}'.",
            status_code=500,
        )

    async def insert_many(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Inserts multiple entities in a single batch request and returns created records.
        """
        if not items:
            return []

        for item in items:
            for col in item.keys():
                validate_identifier(col, "column identifier")

        result = await self.client.post(
            self.table_name,
            json=items,
            headers={"Prefer": "return=representation"},
        )

        if isinstance(result, list):
            return result
        return [result] if result else []

    async def get_by_id(self, id: Union[str, uuid.UUID]) -> Dict[str, Any]:
        """
        Fetches a single entity by primary key.
        Raises EntityNotFoundError if no record matches.
        """
        record = await self.get_by_id_optional(id)
        if record is None:
            raise EntityNotFoundError(
                f"Entity with {self.id_column}='{id}' not found in '{self.table_name}'."
            )
        return record

    async def get_by_id_optional(self, id: Union[str, uuid.UUID]) -> Optional[Dict[str, Any]]:
        """
        Fetches an entity by primary key, or returns None if not found.
        """
        id_str = str(id)
        result = await self.client.get(
            self.table_name,
            params={self.id_column: f"eq.{id_str}"},
        )

        if isinstance(result, list):
            return result[0] if len(result) > 0 else None
        if isinstance(result, dict):
            return result
        return None

    async def list(
        self,
        *,
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lists records from the table matching optional filters with pagination and ordering.
        """
        params: Dict[str, Any] = {}

        if filters:
            for key, val in filters.items():
                validate_identifier(key, "filter column")
                params[key] = format_filter_value(val)

        if limit is not None:
            if limit < 0:
                raise ValueError("Limit must be a non-negative integer.")
            params["limit"] = str(limit)

        if offset is not None:
            if offset < 0:
                raise ValueError("Offset must be a non-negative integer.")
            params["offset"] = str(offset)

        if order is not None:
            # Order format: column, column.asc, column.desc, column.desc.nullsfirst, etc.
            order_col = order.split(".")[0]
            validate_identifier(order_col, "order column")
            params["order"] = order

        result = await self.client.get(
            self.table_name,
            params=params,
        )

        if isinstance(result, list):
            return result
        return [result] if result else []

    async def update(self, id: Union[str, uuid.UUID], data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Updates an entity by primary key and returns the updated record.
        Raises EntityNotFoundError if the entity does not exist or user has no access.
        """
        if not data:
            raise ValueError("Update payload cannot be empty.")

        for col in data.keys():
            validate_identifier(col, "column identifier")

        id_str = str(id)
        result = await self.client.patch(
            self.table_name,
            json=data,
            params={self.id_column: f"eq.{id_str}"},
            headers={"Prefer": "return=representation"},
        )

        if isinstance(result, list) and len(result) > 0:
            return result[0]
        if isinstance(result, dict):
            return result

        raise EntityNotFoundError(
            f"Entity with {self.id_column}='{id}' not found in '{self.table_name}'."
        )

    async def delete(self, id: Union[str, uuid.UUID]) -> Dict[str, Any]:
        """
        Deletes an entity by primary key and returns the deleted record.
        Raises EntityNotFoundError if the entity does not exist or user has no access.
        """
        id_str = str(id)
        result = await self.client.delete(
            self.table_name,
            params={self.id_column: f"eq.{id_str}"},
            headers={"Prefer": "return=representation"},
        )

        if isinstance(result, list) and len(result) > 0:
            return result[0]
        if isinstance(result, dict):
            return result

        raise EntityNotFoundError(
            f"Entity with {self.id_column}='{id}' not found in '{self.table_name}'."
        )

    async def count(self, *, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Returns total count of matching records using PostgREST exact count header.
        """
        params: Dict[str, Any] = {"limit": "0"}

        if filters:
            for key, val in filters.items():
                validate_identifier(key, "filter column")
                params[key] = format_filter_value(val)

        response = await self.client.request(
            "GET",
            self.table_name,
            params=params,
            headers={"Prefer": "count=exact"},
        )

        # Content-Range format: 0-0/42 or */42
        content_range = response.headers.get("content-range") or response.headers.get("Content-Range")
        if content_range and "/" in content_range:
            count_str = content_range.split("/")[-1].strip()
            if count_str.isdigit():
                return int(count_str)
        return 0
