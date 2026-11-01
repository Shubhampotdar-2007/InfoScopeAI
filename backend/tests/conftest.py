"""
Pytest configuration and global fixtures for InfoScope AI backend tests.
Provides default mock transport for PostgREST test requests to infoscope-test.supabase.co.
"""

import json
import uuid
import pytest
import httpx

from app.database.client import set_default_db_transport


@pytest.fixture(autouse=True)
def mock_test_supabase_transport():
    """
    Autouse fixture that routes PostgREST requests targeted at https://infoscope-test.supabase.co
    through an in-memory mock handler, preventing network connection failures in unit tests.
    """
    def mock_postgrest_handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        method = request.method.upper()

        if "infoscope-test.supabase.co" not in url_str:
            return httpx.Response(404, json={"message": "Not found"})

        # 1. public.research_sessions
        if "research_sessions" in url_str:
            if method == "POST":
                try:
                    body = json.loads(request.content)
                except Exception:
                    body = {}
                if isinstance(body, dict):
                    if not body.get("id"):
                        body["id"] = str(uuid.uuid4())
                    body["created_at"] = body.get("created_at") or "2026-11-01T12:00:00Z"
                    body["updated_at"] = body.get("updated_at") or "2026-11-01T12:00:00Z"
                    return httpx.Response(201, json=[body])
                elif isinstance(body, list):
                    for item in body:
                        if not item.get("id"):
                            item["id"] = str(uuid.uuid4())
                        item["created_at"] = item.get("created_at") or "2026-11-01T12:00:00Z"
                        item["updated_at"] = item.get("updated_at") or "2026-11-01T12:00:00Z"
                    return httpx.Response(201, json=body)
                return httpx.Response(201, json=[])

            elif method == "GET":
                params = request.url.params
                id_param = params.get("id")
                if id_param and id_param.startswith("eq."):
                    sid = id_param[3:]
                    return httpx.Response(200, json=[{
                        "id": sid,
                        "user_id": params.get("user_id", "eq.test-user").replace("eq.", ""),
                        "title": "Test Session",
                        "research_query": "Test query topic",
                        "status": "pending",
                        "search_provider": "tavily",
                        "search_metadata": {},
                        "summary": None,
                        "coverage_score": None,
                        "created_at": "2026-11-01T12:00:00Z",
                        "updated_at": "2026-11-01T12:00:00Z",
                    }])
                return httpx.Response(200, json=[])

            elif method == "PATCH":
                try:
                    body = json.loads(request.content)
                except Exception:
                    body = {}
                params = request.url.params
                id_param = params.get("id", "eq.default-id").replace("eq.", "")
                user_id_param = params.get("user_id", "eq.test-user").replace("eq.", "")
                merged = {
                    "id": id_param if id_param != "default-id" else str(uuid.uuid4()),
                    "user_id": user_id_param,
                    "title": "Test Session",
                    "research_query": "Test query topic",
                    "status": "pending",
                    "search_provider": "tavily",
                    "search_metadata": {},
                    "summary": None,
                    "coverage_score": None,
                    "created_at": "2026-11-01T12:00:00Z",
                    "updated_at": "2026-11-01T12:00:00Z",
                }
                merged.update(body)
                return httpx.Response(200, json=[merged])

            elif method == "DELETE":
                return httpx.Response(200, json=[{"id": "deleted"}])

        # 2. public.research_sources
        if "research_sources" in url_str:
            if method == "POST":
                try:
                    body = json.loads(request.content)
                except Exception:
                    body = []
                if isinstance(body, list):
                    out = []
                    for item in body:
                        c = dict(item)
                        if not c.get("id"):
                            c["id"] = str(uuid.uuid4())
                        c["created_at"] = "2026-11-01T12:00:00Z"
                        out.append(c)
                    return httpx.Response(201, json=out)
                elif isinstance(body, dict):
                    c = dict(body)
                    if not c.get("id"):
                        c["id"] = str(uuid.uuid4())
                    c["created_at"] = "2026-11-01T12:00:00Z"
                    return httpx.Response(201, json=[c])
                return httpx.Response(201, json=[])

            elif method == "GET":
                return httpx.Response(200, json=[])

        # 3. public.expected_fields
        if "expected_fields" in url_str:
            if method == "POST":
                try:
                    body = json.loads(request.content)
                except Exception:
                    body = {}
                if isinstance(body, dict):
                    if not body.get("id"):
                        body["id"] = str(uuid.uuid4())
                    body["created_at"] = "2026-11-01T12:00:00Z"
                    body["updated_at"] = "2026-11-01T12:00:00Z"
                    return httpx.Response(201, json=[body])
                elif isinstance(body, list):
                    for item in body:
                        if not item.get("id"):
                            item["id"] = str(uuid.uuid4())
                        item["created_at"] = "2026-11-01T12:00:00Z"
                        item["updated_at"] = "2026-11-01T12:00:00Z"
                    return httpx.Response(201, json=body)
                return httpx.Response(201, json=[])

            elif method == "GET":
                params = request.url.params
                id_param = params.get("id")
                if id_param and id_param.startswith("eq."):
                    fid = id_param[3:]
                    return httpx.Response(200, json=[{
                        "id": fid,
                        "session_id": params.get("session_id", "eq.sess-1").replace("eq.", ""),
                        "user_id": params.get("user_id", "eq.test-user").replace("eq.", ""),
                        "field_name": "Test Field",
                        "field_category": "general",
                        "description": "Test field description",
                        "is_required": True,
                        "weight": 1.00,
                        "status": "missing",
                        "created_at": "2026-11-01T12:00:00Z",
                        "updated_at": "2026-11-01T12:00:00Z",
                    }])
                return httpx.Response(200, json=[])

            elif method == "PATCH":
                try:
                    body = json.loads(request.content)
                except Exception:
                    body = {}
                params = request.url.params
                fid = params.get("id", "eq.field-1").replace("eq.", "")
                merged = {
                    "id": fid,
                    "session_id": params.get("session_id", "eq.sess-1").replace("eq.", ""),
                    "user_id": params.get("user_id", "eq.test-user").replace("eq.", ""),
                    "field_name": "Test Field",
                    "field_category": "general",
                    "description": "Test field description",
                    "is_required": True,
                    "weight": 1.00,
                    "status": "missing",
                    "created_at": "2026-11-01T12:00:00Z",
                    "updated_at": "2026-11-01T12:00:00Z",
                }
                merged.update(body)
                return httpx.Response(200, json=[merged])

            elif method == "DELETE":
                params = request.url.params
                fid = params.get("id", "eq.field-1").replace("eq.", "")
                return httpx.Response(200, json=[{"id": fid}])

        return httpx.Response(200, json=[])

    mock_transport = httpx.MockTransport(mock_postgrest_handler)
    set_default_db_transport(mock_transport)
    yield mock_transport
    set_default_db_transport(None)
